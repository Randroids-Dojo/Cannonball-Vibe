from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform
from typer.testing import CliRunner

from cannonball_map import continental
from cannonball_map.cli import app
from cannonball_map.continental import (
    ANCHOR_SNAP_LIMIT_METERS,
    ENDPOINT_SNAP_TOLERANCE_METERS,
    MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS,
    LockedCandidateLine,
    _derive_transfer_node,
    _solve_segment_edge_path,
    acquire_continental_nhpn_candidates,
    build_nhpn_candidate_selectors,
    derive_continental_edge_path_lock,
    validate_continental_edge_path_lock,
    validate_continental_route_lock,
    validate_continental_transfer_lock,
)
from cannonball_map.lockfile import canonical_sha256

SELECTION_PATH = Path("data/routes/continental/route-selection.v1.json")
CATALOG_PATH = Path("data/sources/catalog.json")
LOCK_PATH = Path("data/sources/continental-route-lock.json")
TRANSFER_POLICY_PATH = Path("data/routes/continental/transfer-node-policy.v1.json")
TRANSFER_LOCK_PATH = Path("data/routes/continental/transfer-node-lock.v1.json")


def _selection() -> dict:
    return json.loads(SELECTION_PATH.read_text(encoding="utf-8"))


def _service_metadata() -> dict:
    return {
        "id": 0,
        "serviceItemId": "4179a784a8d547ac869b14505c168430",
        "objectIdField": "OBJECTID",
        "maxRecordCount": 2_000,
        "editingInfo": {"dataLastEditDate": 1},
        "copyrightText": "U.S. government work available for unrestricted public use.",
    }


class _OneFeatureTransport:
    def post(self, _url: str, form: dict[str, str]) -> dict:
        if form.get("returnCountOnly") == "true":
            return {"count": 1}
        if form.get("returnIdsOnly") == "true":
            return {"objectIdFieldName": "OBJECTID", "objectIds": [1]}
        return {"features": [{"attributes": {"OBJECTID": 1}}]}


def test_candidate_selectors_cover_every_nhpn_segment_and_all_sign_slots() -> None:
    selection = _selection()
    selectors = build_nhpn_candidate_selectors(selection)
    expected = {
        segment["id"]
        for segment in selection["segments"]
        if segment["geometry_status"] == "nhpn_selection_pending"
    }

    assert {selector.segment_id for selector in selectors} == expected
    assert len(selectors) == 12
    assert all("SIGNT1='I'" in selector.predicate for selector in selectors)
    assert all("SIGNT2='I'" in selector.predicate for selector in selectors)
    assert all("SIGNT3='I'" in selector.predicate for selector in selectors)
    eastern_i80 = next(
        selector
        for selector in selectors
        if selector.segment_id == "i80-new-jersey-to-big-springs"
    )
    assert eastern_i80.state_fips == (
        "34",
        "42",
        "39",
        "18",
        "17",
        "19",
        "31",
    )


def test_repository_continental_candidate_lock_validates() -> None:
    payload = validate_continental_route_lock(LOCK_PATH, CATALOG_PATH, SELECTION_PATH)

    assert payload["status"] == "nhpn_candidates_locked_3dep_pending"
    assert payload["nhpn"]["candidate_union"]["expected_count"] > 10_000
    assert payload["elevation"]["status"] == "pending_exact_nhpn_path_geometry"

    with pytest.raises(ValueError, match="not complete"):
        validate_continental_route_lock(
            LOCK_PATH,
            CATALOG_PATH,
            SELECTION_PATH,
            require_complete=True,
        )


def test_acquisition_versions_checkpoint_cache_by_service_metadata(tmp_path: Path) -> None:
    metadata = _service_metadata()

    cache = tmp_path / "cache"
    output = tmp_path / "lock.json"
    payload = acquire_continental_nhpn_candidates(
        SELECTION_PATH,
        CATALOG_PATH,
        output,
        cache,
        transport=_OneFeatureTransport(),
        service_metadata=metadata,
        acquired_at="2026-08-04T01:58:01Z",
    )
    metadata_hash = canonical_sha256(metadata)

    assert payload["nhpn"]["service"]["canonical_metadata_sha256"] == metadata_hash
    assert (cache / metadata_hash / "i80-new-jersey-to-big-springs" / "page-000000.json").is_file()
    assert not (cache / "i80-new-jersey-to-big-springs").exists()
    validate_continental_route_lock(output, CATALOG_PATH, SELECTION_PATH)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", 1, "identity"),
        ("serviceItemId", "changed", "service item changed"),
        ("maxRecordCount", 0, "usable record limit"),
        ("copyrightText", "restricted", "unrestricted public use"),
        ("editingInfo", {}, "data last edit date"),
    ],
)
def test_acquisition_rejects_invalid_live_service_metadata(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    metadata = _service_metadata()
    metadata[field] = value

    with pytest.raises(ValueError, match=message):
        acquire_continental_nhpn_candidates(
            SELECTION_PATH,
            CATALOG_PATH,
            tmp_path / "lock.json",
            tmp_path / "cache",
            transport=_OneFeatureTransport(),
            service_metadata=metadata,
        )


def test_acquisition_rejects_page_size_above_live_limit(tmp_path: Path) -> None:
    metadata = _service_metadata()
    metadata["maxRecordCount"] = 1

    with pytest.raises(ValueError, match="exceeds the live service limit"):
        acquire_continental_nhpn_candidates(
            SELECTION_PATH,
            CATALOG_PATH,
            tmp_path / "lock.json",
            tmp_path / "cache",
            transport=_OneFeatureTransport(),
            service_metadata=metadata,
            page_size=2,
        )


def test_continental_lock_rejects_selector_and_union_drift(tmp_path: Path) -> None:
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    selector_drift = copy.deepcopy(payload)
    selector_drift["nhpn"]["segment_snapshots"][0]["predicate"] = "1=1"
    selector_path = tmp_path / "selector.json"
    selector_path.write_text(json.dumps(selector_drift), encoding="utf-8")
    with pytest.raises(ValueError, match="selector drifted"):
        validate_continental_route_lock(selector_path, CATALOG_PATH, SELECTION_PATH)

    union_drift = copy.deepcopy(payload)
    union_drift["nhpn"]["candidate_union"]["expected_count"] -= 1
    union_path = tmp_path / "union.json"
    union_path.write_text(json.dumps(union_drift), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate union count does not reconcile"):
        validate_continental_route_lock(union_path, CATALOG_PATH, SELECTION_PATH)


def test_continental_lock_rejects_duplicate_segment_snapshot(tmp_path: Path) -> None:
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["nhpn"]["segment_snapshots"].append(
        copy.deepcopy(payload["nhpn"]["segment_snapshots"][0])
    )
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly once"):
        validate_continental_route_lock(duplicate_path, CATALOG_PATH, SELECTION_PATH)


def test_validate_continental_lock_cli_reports_clean_failure(tmp_path: Path) -> None:
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["status"] = "invalid"
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(app, ["validate-continental-lock", str(invalid_path)])

    assert result.exit_code == 1
    assert "continental-lock-invalid:" in result.output
    assert "unsupported status" in result.output
    assert "Traceback" not in result.output


def test_repository_continental_transfer_lock_validates() -> None:
    payload = validate_continental_transfer_lock(
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        SELECTION_PATH,
        LOCK_PATH,
        CATALOG_PATH,
    )

    assert payload["status"] == "transfer_nodes_locked_exact_path_pending"
    assert len(payload["transfer_nodes"]) == 12
    assert max(node["facility_separation_m"] for node in payload["transfer_nodes"]) < 25
    assert payload["next_stage"]["id"] == "exact-westbound-path-solve"


def test_continental_transfer_lock_rejects_evidence_drift(tmp_path: Path) -> None:
    payload = json.loads(TRANSFER_LOCK_PATH.read_text(encoding="utf-8"))
    payload["transfer_nodes"][0]["evidence"][0]["object_id"] = -1
    payload["transfer_nodes_sha256"] = canonical_sha256(payload["transfer_nodes"])
    invalid_path = tmp_path / "invalid-transfer.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="OBJECTID drifted"):
        validate_continental_transfer_lock(
            invalid_path,
            TRANSFER_POLICY_PATH,
            SELECTION_PATH,
            LOCK_PATH,
            CATALOG_PATH,
        )


def test_continental_transfer_lock_rejects_page_hash_drift(tmp_path: Path) -> None:
    payload = json.loads(TRANSFER_LOCK_PATH.read_text(encoding="utf-8"))
    payload["transfer_nodes"][0]["evidence"][0]["page_response_sha256"] = "0" * 64
    payload["transfer_nodes_sha256"] = canonical_sha256(payload["transfer_nodes"])
    invalid_path = tmp_path / "invalid-transfer.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="response hash drifted"):
        validate_continental_transfer_lock(
            invalid_path,
            TRANSFER_POLICY_PATH,
            SELECTION_PATH,
            LOCK_PATH,
            CATALOG_PATH,
        )


def test_continental_transfer_lock_rejects_next_stage_drift(tmp_path: Path) -> None:
    payload = json.loads(TRANSFER_LOCK_PATH.read_text(encoding="utf-8"))
    payload["next_stage"]["id"] = "unexpected"
    invalid_path = tmp_path / "invalid-transfer.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="next stage drifted"):
        validate_continental_transfer_lock(
            invalid_path,
            TRANSFER_POLICY_PATH,
            SELECTION_PATH,
            LOCK_PATH,
            CATALOG_PATH,
        )


def test_transfer_derivation_is_deterministic_for_crossing_candidates() -> None:
    spec = {
        "id": "fixture-transfer",
        "method": "midpoint_between_segments",
        "evidence_segment_ids": ["west-east", "north-south"],
        "search_hint": {"longitude": -100.0, "latitude": 40.0},
        "search_radius_m": 5_000,
        "max_facility_separation_m": 100,
        "research_source_ids": ["fixture-source"],
    }
    response_hash = "1" * 64
    candidates = {
        "west-east": (
            LockedCandidateLine(
                "west-east",
                20,
                response_hash,
                LineString([(-100.01, 40.0), (-99.99, 40.0)]),
            ),
        ),
        "north-south": (
            LockedCandidateLine(
                "north-south",
                10,
                response_hash,
                LineString([(-100.0, 39.99), (-100.0, 40.01)]),
            ),
        ),
    }
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    metric_candidates = {
        segment_id: tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in segment_candidates
        )
        for segment_id, segment_candidates in candidates.items()
    }

    first = _derive_transfer_node(spec, metric_candidates.__getitem__, forward, inverse)
    second = _derive_transfer_node(spec, metric_candidates.__getitem__, forward, inverse)

    assert first == second
    assert first["coordinate"]["longitude"] == pytest.approx(-100.0)
    assert first["coordinate"]["latitude"] == pytest.approx(40.0)
    assert first["facility_separation_m"] == pytest.approx(0.0)


def test_validate_continental_transfers_cli_reports_clean_failure(tmp_path: Path) -> None:
    payload = json.loads(TRANSFER_LOCK_PATH.read_text(encoding="utf-8"))
    payload["status"] = "invalid"
    invalid_path = tmp_path / "invalid-transfer.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["validate-continental-transfers", str(invalid_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "continental-transfers-invalid:" in result.output
    assert "unsupported status" in result.output
    assert "Traceback" not in result.output


EDGE_PATH_LOCK_PATH = Path("data/routes/continental/edge-path-lock.v1.json")


def _tamper(tmp_path: Path, **changes: object) -> Path:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    payload.update(changes)
    target = tmp_path / "edge-path-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _validate(path: Path):
    return validate_continental_edge_path_lock(
        path, TRANSFER_LOCK_PATH, TRANSFER_POLICY_PATH,
        SELECTION_PATH, LOCK_PATH, CATALOG_PATH,
    )


def _metric_line(
    object_id: int,
    coordinates: list[tuple[float, float]],
    lrs: str = "L1",
    part_index: int = 0,
    section: tuple[float, float] = (0.0, 100.0),
    record: tuple[float, float] = (0.0, 1.0),
):
    """Build a locked line already expressed in the metric CRS the solver uses."""
    line = LineString(coordinates)
    candidate = LockedCandidateLine(
        "seg", object_id, "0" * 64, line, lrs,
        section[0], section[1], record[0], record[1], part_index,
    )
    return candidate, line


def test_connectivity_audit_links_a_shared_endpoint_chain() -> None:
    metric_lines = (
        _metric_line(2, [(0.0, 0.0), (100.0, 0.0)]),
        _metric_line(1, [(100.0, 0.0), (200.0, 0.0)]),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (200.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is True
    assert result["object_ids"] == [2, 1]
    assert result["length_meters"] == pytest.approx(200.0)
    # The audit must never imply it established a travel direction.
    assert result["direction_validated"] is False


def test_connectivity_audit_reports_a_gap_instead_of_bridging_it() -> None:
    # A 40 m gap is far wider than the snapping tolerance, so the two chains are
    # separate components and the audit must say so rather than join them.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)]),
        _metric_line(2, [(140.0, 0.0), (240.0, 0.0)]),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (240.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is False
    assert result["connected_component_count"] == 2
    assert "no connected path" in result["failure"]



def test_edge_path_lock_validates_against_its_locked_inputs() -> None:
    payload = validate_continental_edge_path_lock(
        EDGE_PATH_LOCK_PATH, TRANSFER_LOCK_PATH, TRANSFER_POLICY_PATH,
        SELECTION_PATH, LOCK_PATH, CATALOG_PATH,
    )
    assert payload["westbound_selection_validated"] is False
    assert payload["segment_count"] == len(payload["segments"])


def test_edge_path_lock_rejects_a_claimed_direction(tmp_path: Path) -> None:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    connected = next(entry for entry in payload["segments"] if entry.get("connected"))
    connected["direction_validated"] = True
    payload["segments_sha256"] = canonical_sha256(payload["segments"])
    tampered = tmp_path / "edge-path-lock.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="claims a validated direction"):
        validate_continental_edge_path_lock(
            tampered, TRANSFER_LOCK_PATH, TRANSFER_POLICY_PATH,
            SELECTION_PATH, LOCK_PATH, CATALOG_PATH,
        )


def test_edge_path_lock_rejects_a_drifted_segment_digest(tmp_path: Path) -> None:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    payload["segments"][0]["candidate_line_count"] += 1
    tampered = tmp_path / "edge-path-lock.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="segment digest drifted"):
        validate_continental_edge_path_lock(
            tampered, TRANSFER_LOCK_PATH, TRANSFER_POLICY_PATH,
            SELECTION_PATH, LOCK_PATH, CATALOG_PATH,
        )


def test_lock_rejects_a_claimed_westbound_selection(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="claims a validated westbound selection"):
        _validate(_tamper(tmp_path, westbound_selection_validated=True))


def test_lock_rejects_a_widened_snap_tolerance(tmp_path: Path) -> None:
    # Without a ceiling the validator would only compare a lock against its own
    # declared tolerance, so a widened one would validate itself.
    widened = MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS * 25
    with pytest.raises(ValueError, match="outside the permitted range"):
        _validate(_tamper(tmp_path, endpoint_snap_tolerance_m=widened))


def test_lock_rejects_a_non_standard_anchor_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-standard anchor snap limit"):
        _validate(_tamper(tmp_path, anchor_snap_limit_m=ANCHOR_SNAP_LIMIT_METERS * 10))


def test_derivation_refuses_a_tolerance_that_would_invent_connectivity(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="invent connectivity"):
        derive_continental_edge_path_lock(
            SELECTION_PATH, LOCK_PATH, TRANSFER_LOCK_PATH, TRANSFER_POLICY_PATH,
            CATALOG_PATH, Path(".tools/continental/nhpn"),
            tmp_path / "out.json",
            tolerance_meters=MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS * 50,
        )


def test_a_distant_anchor_is_not_reported_as_connectivity() -> None:
    # The chain is fully connected, but the requested anchor sits far off it, so a
    # walk between the nearest graph nodes is not a walk between the anchors.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)]),
        _metric_line(2, [(100.0, 0.0), (200.0, 0.0)]),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines,
        (0.0, ANCHOR_SNAP_LIMIT_METERS * 4), (200.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is False
    assert "anchor snap limit" in result["failure"]




def test_a_multi_part_feature_keeps_both_of_its_parts() -> None:
    # One OBJECTID contributing two geometry parts must yield two graph edges. Keying
    # the graph on the object id alone would silently drop the first part and could
    # break an otherwise connected chain.
    metric_lines = (
        _metric_line(7, [(0.0, 0.0), (100.0, 0.0)], part_index=0),
        _metric_line(7, [(100.0, 0.0), (200.0, 0.0)], part_index=1),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (200.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["graph_edge_count"] == 2
    assert result["connected"] is True
    assert result["edge_count"] == 2
    assert [edge["part_index"] for edge in result["edges"]] == [0, 1]
    assert result["length_meters"] == pytest.approx(200.0)


def test_lock_rejects_a_non_finite_snap_distance(tmp_path: Path) -> None:
    # NaN is not JSON, and every comparison against it is false, so a NaN distance
    # would slide past the tolerance and anchor gates. The digest is recomputed so
    # the test proves the numeric guard rather than the checksum.
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    connected = next(entry for entry in payload["segments"] if entry["connected"])
    connected["maximum_endpoint_snap_distance_m"] = float("nan")
    payload["segments_sha256"] = canonical_sha256(payload["segments"])
    target = tmp_path / "edge-path-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite literal"):
        _validate(target)


def test_lock_rejects_a_non_finite_anchor_distance(tmp_path: Path) -> None:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    connected = next(entry for entry in payload["segments"] if entry["connected"])
    connected["from_transfer_node_snap_distance_m"] = float("inf")
    payload["segments_sha256"] = canonical_sha256(payload["segments"])
    target = tmp_path / "edge-path-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite literal"):
        _validate(target)


def test_non_finite_guard_also_holds_past_the_parse_boundary() -> None:
    # The parse boundary is the first defence; the range checks must refuse a
    # non-finite value on their own too, so neither alone is load-bearing.
    from cannonball_map import continental

    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    payload["endpoint_snap_tolerance_m"] = float("nan")
    original = continental.load_json
    continental.load_json = lambda path: (
        payload if str(path) == str(EDGE_PATH_LOCK_PATH) else original(path)
    )
    try:
        with pytest.raises(ValueError, match="finite numeric snap tolerance"):
            _validate(EDGE_PATH_LOCK_PATH)
    finally:
        continental.load_json = original


def test_a_simple_chain_is_reported_as_chain_interior() -> None:
    # Three records end to end: two interior joins, two chain ends.
    metric_lines = tuple(
        _metric_line(index, [(index * 100.0, 0.0), ((index + 1) * 100.0, 0.0)])
        for index in range(3)
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (300.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["endpoint_degree_histogram"] == {"1": 2, "2": 2}
    assert result["chain_end_count"] == 2
    assert result["chain_interior_fraction"] == pytest.approx(0.5, abs=5e-5)


def test_a_discontinuity_is_reported_as_a_chain_end_separation() -> None:
    # Two chains split by a 40 m break: four chain ends, and the smallest
    # separation between them is the break itself.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)]),
        _metric_line(2, [(140.0, 0.0), (240.0, 0.0)]),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (240.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is False
    assert result["chain_end_count"] == 4
    assert min(result["chain_end_separations_m"]) == pytest.approx(40.0, abs=1e-3)


def test_audit_finding_is_derived_from_the_recorded_segments() -> None:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    interior = [entry["chain_interior_fraction"] for entry in payload["segments"]]
    connected = sum(1 for entry in payload["segments"] if entry["connected"])
    finding = payload["audit_finding"]
    assert f"{round(min(interior) * 100)} to {round(max(interior) * 100)} percent" in finding
    assert f"{len(payload['segments']) - connected} of {len(payload['segments'])}" in finding
    # The superseded claim must not survive anywhere in the artifact.
    assert "paired directional carriageways" not in json.dumps(payload)


def test_contiguity_uses_the_record_extent_not_the_section_extent() -> None:
    """The section extent is shared by every record in a section.

    Judging adjacency by BEGMP and ENDMP counts consecutive pieces of one section
    as adjacent to each other regardless of where they actually sit, which is the
    error that produced the withdrawn paired-carriageway finding. Adjacency must
    come from BEGIN_POIN and END_POINT.
    """
    # Two broken chains. Both records sit in the same section, so their section
    # extents match, but their record extents are far apart: not adjacent.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], section=(0.0, 300.0), record=(0.0, 1.0)),
        _metric_line(2, [(500.0, 0.0), (600.0, 0.0)], section=(0.0, 300.0), record=(280.0, 281.0)),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (600.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is False
    assert result["milepost_contiguous_chain_end_pairs"] == 0

    # Same geometry, but now the record extents do meet: genuinely adjacent.
    adjacent = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], section=(0.0, 300.0), record=(0.0, 1.0)),
        _metric_line(2, [(500.0, 0.0), (600.0, 0.0)], section=(0.0, 300.0), record=(1.0, 2.0)),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, adjacent, (0.0, 0.0), (600.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["milepost_contiguous_chain_end_pairs"] == 1


def _milepost_line(begin: float, end: float) -> LockedCandidateLine:
    return LockedCandidateLine(
        "segment",
        1,
        "0" * 64,
        LineString([(-100.0, 40.0), (-99.99, 40.0)]),
        "KEY",
        0.0,
        0.0,
        begin,
        end,
        0,
    )


def test_milepost_spans_merge_duplicate_and_overlapping_records() -> None:
    """Differencing sorted neighbours reports duplicates and overlaps as breaks.

    The locked candidate set contains both, so contiguity has to be measured as a
    union of intervals rather than by comparing adjacent records.
    """
    spans = continental._merge_milepost_spans(
        [
            _milepost_line(0.0, 10.0),
            _milepost_line(0.0, 10.0),
            _milepost_line(5.0, 15.0),
            _milepost_line(12.0, 20.0),
        ]
    )

    assert spans == [(0.0, 20.0)]


def test_milepost_spans_are_direction_insensitive() -> None:
    """A record recorded against the direction of travel is not a gap."""
    assert continental._merge_milepost_spans(
        [_milepost_line(10.0, 0.0), _milepost_line(20.0, 10.0)]
    ) == [(0.0, 20.0)]


def test_milepost_spans_keep_a_real_gap() -> None:
    spans = continental._merge_milepost_spans(
        [_milepost_line(0.0, 10.0), _milepost_line(30.0, 40.0)]
    )

    assert spans == [(0.0, 10.0), (30.0, 40.0)]


def test_source_milepost_quantum_is_the_published_precision() -> None:
    """NHPN publishes record mileposts to three decimals.

    Exact-equality adjacency rejects records a single quantum apart, which is
    1.61 m and not a gap in the road.
    """
    assert continental.MILEPOST_QUANTUM_MILES == 0.001
    quantum_meters = continental.MILEPOST_QUANTUM_MILES * continental.METRES_PER_MILE
    assert round(quantum_meters, 2) == 1.61


def _probed_record(
    object_id: int,
    low: float,
    high: float,
    *,
    state_fips: str = "34",
    signs: tuple[tuple[str, str], ...] = (("U", "30"),),
) -> continental.ProbedGapRecord:
    return continental.ProbedGapRecord(object_id, state_fips, signs, low, high)


def _gap(segment_id: str = "i80-new-jersey-to-big-springs") -> dict:
    return {
        "segment_id": segment_id,
        "lrs_key": "KEY000000000001",
        "from_milepost": 10.0,
        "to_milepost": 20.0,
        "gap_miles": 10.0,
    }


def _eastern_i80_selector() -> continental.NhpnCandidateSelector:
    return next(
        selector
        for selector in build_nhpn_candidate_selectors(_selection())
        if selector.segment_id == "i80-new-jersey-to-big-springs"
    )


def test_uncovered_spans_clip_merge_and_ignore_outside_extents() -> None:
    spans = continental._uncovered_spans(
        10.0,
        20.0,
        [(0.0, 12.0), (11.0, 13.0), (30.0, 40.0), (15.0, 18.0)],
    )

    assert spans == [(13.0, 15.0), (18.0, 20.0)]


def test_probe_sign_identities_strip_nhpn_space_padding() -> None:
    """NHPN pads empty sign slots with spaces rather than nulls."""
    identities = continental._probe_sign_identities(
        {
            "SIGNT1": "I",
            "SIGNN1": "80",
            "SIGNT2": " ",
            "SIGNN2": " ",
            "SIGNT3": None,
            "SIGNN3": None,
        }
    )

    assert identities == (("I", "80"),)


def test_classify_gap_with_no_records_reports_no_records() -> None:
    result = continental._classify_gap(_gap(), [], _eastern_i80_selector(), frozenset())

    assert result["classification"] == "no_records"
    assert result["overlapping_record_count"] == 0
    assert result["uncovered_miles"] == pytest.approx(10.0)


def test_classify_gap_counts_each_exclusion_reason_once() -> None:
    """Every unacquired overlapping record is attributed to the predicate clause
    that excluded it, and a record that merely touches a boundary is not
    overlapping."""
    records = [
        _probed_record(1, 0.0, 10.0),  # abuts the gap; not overlapping
        _probed_record(2, 10.0, 14.0, state_fips="34", signs=(("U", "30"),)),
        _probed_record(3, 14.0, 17.0, state_fips="08", signs=(("I", "80"),)),
        _probed_record(4, 17.0, 20.0, state_fips="08", signs=(("U", "30"),)),
    ]

    result = continental._classify_gap(
        _gap(), records, _eastern_i80_selector(), frozenset()
    )

    assert result["overlapping_record_count"] == 3
    assert result["records_excluded_by_sign_filter"] == 1
    assert result["records_excluded_by_state_filter"] == 1
    assert result["records_excluded_by_both_filters"] == 1
    assert result["records_matching_predicate_unacquired"] == []
    assert result["classification"] == "fully_covered"
    assert result["signed_routes_found"] == ["I-80", "U-30"]
    assert result["state_fips_found"] == ["08", "34"]


def test_classify_gap_flags_a_predicate_match_absent_from_the_lock() -> None:
    """A record that matches the acquisition predicate yet was not acquired is an
    anomaly, not an exclusion."""
    records = [_probed_record(7, 10.0, 20.0, state_fips="34", signs=(("I", "80"),))]

    result = continental._classify_gap(
        _gap(), records, _eastern_i80_selector(), frozenset()
    )

    assert result["records_matching_predicate_unacquired"] == [7]
    assert result["records_excluded_by_sign_filter"] == 0


def test_classify_gap_does_not_report_a_locked_record_as_excluded() -> None:
    """A record already in the candidate lock was not excluded by anything, even
    when it fails the probing segment's predicate. Shared LRS keys make this
    real: a record locked for one segment can overlap another segment's gap."""
    records = [_probed_record(9, 10.0, 20.0, state_fips="08", signs=(("I", "15"),))]

    result = continental._classify_gap(
        _gap(), records, _eastern_i80_selector(), frozenset({9})
    )

    assert result["records_in_candidate_lock"] == 1
    assert result["records_excluded_by_both_filters"] == 0
    assert result["classification"] == "fully_covered"


def test_classify_gap_tolerates_a_quantum_shortfall_but_not_a_real_one() -> None:
    """A record recorded one milepost quantum inside a gap boundary is the same
    phenomenon as the 32 quantum-sized gaps the audit counted."""
    quantum = continental.MILEPOST_QUANTUM_MILES
    selector = _eastern_i80_selector()

    covered = continental._classify_gap(
        _gap(), [_probed_record(2, 10.0 + quantum, 20.0)], selector, frozenset()
    )
    partial = continental._classify_gap(
        _gap(), [_probed_record(2, 14.0, 20.0)], selector, frozenset()
    )

    assert covered["classification"] == "fully_covered"
    assert partial["classification"] == "partially_covered"
    assert partial["largest_uncovered_miles"] == pytest.approx(4.0)


_PROBE_KEY = "KEY000000000001"


def _candidate_feature(object_id: int, begin: float, end: float) -> dict:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "LRSKEY": _PROBE_KEY,
            "BEGMP": 0.0,
            "ENDMP": 30.0,
            "BEGIN_POIN": begin,
            "END_POINT": end,
            "STFIPS": "34",
            "SIGNT1": "I",
            "SIGNN1": "80",
            "SIGNT2": " ",
            "SIGNN2": " ",
            "SIGNT3": " ",
            "SIGNN3": " ",
        },
        "geometry": {"paths": [[[-100.0 - begin, 40.0], [-100.0 - end, 40.0]]]},
    }


class _GappedCandidateTransport:
    """Two records per segment with a ten-mile milepost gap between them."""

    def post(self, _url: str, form: dict[str, str]) -> dict:
        if form.get("returnCountOnly") == "true":
            return {"count": 2}
        if form.get("returnIdsOnly") == "true":
            return {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2]}
        return {
            "features": [
                _candidate_feature(1, 0.0, 10.0),
                _candidate_feature(2, 20.0, 30.0),
            ]
        }


class _WholeKeyProbeTransport:
    """The whole-key view: both locked records plus the filler between them,
    which carries a different signed route."""

    def __init__(self) -> None:
        self.predicates: list[str] = []

    def post(self, _url: str, form: dict[str, str]) -> dict:
        if "where" in form:
            self.predicates.append(form["where"])
        if form.get("returnCountOnly") == "true":
            return {"count": 3}
        if form.get("returnIdsOnly") == "true":
            return {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2, 3]}
        filler = _candidate_feature(3, 10.0, 20.0)
        filler["attributes"]["SIGNT1"] = "U"
        filler["attributes"]["SIGNN1"] = "30"
        return {
            "features": [
                _candidate_feature(1, 0.0, 10.0),
                _candidate_feature(2, 20.0, 30.0),
                filler,
            ]
        }


def test_gap_probe_classifies_the_filler_and_records_provenance(tmp_path: Path) -> None:
    metadata = _service_metadata()
    cache = tmp_path / "cache"
    lock = tmp_path / "lock.json"
    acquire_continental_nhpn_candidates(
        SELECTION_PATH,
        CATALOG_PATH,
        lock,
        cache,
        transport=_GappedCandidateTransport(),
        service_metadata=metadata,
        acquired_at="2026-08-27T00:00:00Z",
    )
    probe_transport = _WholeKeyProbeTransport()

    payload = continental.probe_continental_milepost_gaps(
        SELECTION_PATH,
        lock,
        CATALOG_PATH,
        cache,
        tmp_path / "probe-cache",
        transport=probe_transport,
        service_metadata=metadata,
        acquired_at="2026-08-27T00:00:00Z",
    )

    # Every segment shares the same key and the same gap, so one whole-key
    # acquisition serves all twelve gap classifications.
    assert payload["gap_count"] == 12
    assert len(payload["key_probes"]) == 1
    probe = payload["key_probes"][0]
    assert probe["predicate"] == f"LRSKEY='{_PROBE_KEY}'"
    assert probe["expected_count"] == 3
    assert set(probe_transport.predicates) == {f"LRSKEY='{_PROBE_KEY}'"}
    assert payload["gaps_fully_covered"] == 12
    assert payload["gaps_no_records"] == 0
    assert payload["predicate_anomaly_count"] == 0
    assert payload["service"]["matches_candidate_lock"] is True
    assert payload["source_policy"]["continental_downloads_committed"] is False
    eastern = next(
        gap
        for gap in payload["gaps"]
        if gap["segment_id"] == "i80-new-jersey-to-big-springs"
    )
    # The filler carries U-30 in New Jersey: inside the declared states, outside
    # the sign filter.
    assert eastern["records_excluded_by_sign_filter"] == 1
    assert eastern["signed_routes_found"] == ["U-30"]
    i15 = next(
        gap
        for gap in payload["gaps"]
        if gap["segment_id"] == "i15-salt-lake-to-cove-fort"
    )
    # The same filler seen from a segment that declares neither the route nor
    # New Jersey fails both filters.
    assert i15["records_excluded_by_both_filters"] == 1
    assert "characterisation" in payload["finding"]


def test_gap_probe_refuses_a_drifted_live_service(tmp_path: Path) -> None:
    """A probe against a drifted service would characterise a different dataset
    than the one the locked gaps were measured in."""
    metadata = _service_metadata()
    cache = tmp_path / "cache"
    lock = tmp_path / "lock.json"
    acquire_continental_nhpn_candidates(
        SELECTION_PATH,
        CATALOG_PATH,
        lock,
        cache,
        transport=_GappedCandidateTransport(),
        service_metadata=metadata,
        acquired_at="2026-08-27T00:00:00Z",
    )
    drifted = {**metadata, "editingInfo": {"dataLastEditDate": 2}}

    with pytest.raises(ValueError, match="drifted"):
        continental.probe_continental_milepost_gaps(
            SELECTION_PATH,
            lock,
            CATALOG_PATH,
            cache,
            tmp_path / "probe-cache",
            transport=_WholeKeyProbeTransport(),
            service_metadata=drifted,
            acquired_at="2026-08-27T00:00:00Z",
        )


def test_geometric_probe_sites_span_components_without_joining_the_graph() -> None:
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)]),
        _metric_line(2, [(140.0, 0.0), (240.0, 0.0)]),
        _metric_line(3, [(300.0, 0.0), (400.0, 0.0)]),
    )

    sites = continental._derive_segment_geometric_probe_sites(
        "seg", metric_lines, (0.0, 0.0), (400.0, 0.0)
    )

    # Three components need two candidate sites. The minimum spanning tree avoids
    # treating the distant first-to-third pair as another alleged road break.
    assert [site["separation_m"] for site in sites] == [40.0, 60.0]
    assert all(site["kind"] == "component_gap" for site in sites)
    assert len(sites) == 2
    # Site derivation is diagnostic only: the authoritative solver remains red.
    assert _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (400.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )["connected"] is False


def test_geometric_probe_sites_include_a_distant_transfer_anchor() -> None:
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)]),
        _metric_line(2, [(100.0, 0.0), (200.0, 0.0)]),
    )

    sites = continental._derive_segment_geometric_probe_sites(
        "seg", metric_lines, (-100.0, 0.0), (200.0, 0.0)
    )

    assert len(sites) == 1
    assert sites[0]["kind"] == "anchor_gap"
    assert sites[0]["anchor_side"] == "from"
    assert sites[0]["separation_m"] == pytest.approx(100.0)


def _spatial_feature(
    object_id: int,
    coordinates: list[tuple[float, float]],
    *,
    sign_type: str = "I",
    sign_number: str = "80",
) -> dict:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "STFIPS": "34",
            "SIGNT1": sign_type,
            "SIGNN1": sign_number,
            "SIGNT2": " ",
            "SIGNN2": " ",
            "SIGNT3": " ",
            "SIGNN3": " ",
        },
        "geometry": {"paths": [[list(coordinate) for coordinate in coordinates]]},
    }


def test_geometric_probe_classifies_an_unacquired_source_connection() -> None:
    identity = Transformer.from_crs("EPSG:5070", "EPSG:5070", always_xy=True)
    site = {
        "kind": "component_gap",
        "from_metric": (100.0, 0.0),
        "to_metric": (140.0, 0.0),
    }
    features = [
        _spatial_feature(1, [(0.0, 0.0), (100.0, 0.0)]),
        _spatial_feature(3, [(100.0, 0.0), (140.0, 0.0)], sign_type="U", sign_number="30"),
        _spatial_feature(2, [(140.0, 0.0), (240.0, 0.0)]),
    ]

    result = continental._classify_spatial_probe_connection(
        site,
        features,
        identity,
        frozenset({1, 2}),
        frozenset({1, 2}),
    )

    assert result["source_connection_found"] is True
    assert result["path_object_ids"] == [3]
    assert result["path_records_unacquired"] == [3]
    assert result["path_records_in_segment_lock"] == []
    assert result["path_signed_routes"] == ["U-30"]


def test_geometric_probe_does_not_bridge_disconnected_nearby_features() -> None:
    identity = Transformer.from_crs("EPSG:5070", "EPSG:5070", always_xy=True)
    site = {
        "kind": "component_gap",
        "from_metric": (100.0, 0.0),
        "to_metric": (140.0, 0.0),
    }
    features = [
        _spatial_feature(1, [(0.0, 0.0), (100.0, 0.0)]),
        _spatial_feature(2, [(140.0, 0.0), (240.0, 0.0)]),
    ]

    result = continental._classify_spatial_probe_connection(
        site,
        features,
        identity,
        frozenset({1, 2}),
        frozenset({1, 2}),
    )

    assert result["source_connection_found"] is False
    assert result["path_object_ids"] == []


def test_component_probe_does_not_use_the_transfer_anchor_snap_limit() -> None:
    """A road merely near both chain ends is not a source-asserted join.

    The 25 m limit belongs only to a locked transfer anchor. Component ends
    retain the 1 m endpoint tolerance that prevents the route graph from
    inventing connectivity.
    """
    identity = Transformer.from_crs("EPSG:5070", "EPSG:5070", always_xy=True)
    site = {
        "kind": "component_gap",
        "from_metric": (100.0, 0.0),
        "to_metric": (140.0, 0.0),
    }

    result = continental._classify_spatial_probe_connection(
        site,
        [_spatial_feature(3, [(110.0, 0.0), (130.0, 0.0)])],
        identity,
        frozenset(),
        frozenset(),
    )

    assert result["from_probe_snap_distance_m"] == pytest.approx(10.0)
    assert result["from_probe_snap_limit_m"] == ENDPOINT_SNAP_TOLERANCE_METERS
    assert result["source_connection_found"] is False


# --- Per-chain-end census at the unconnected segments' break ends --------------


def _metric_identity() -> Transformer:
    """Metric and geographic space coincide, so fabricated metric geometry can
    round-trip through the census's CRS conversions unchanged."""
    return Transformer.from_crs("EPSG:5070", "EPSG:5070", always_xy=True)


def test_chord_bearing_smooths_jitter_and_refuses_degenerate_lines() -> None:
    line = LineString([(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)])
    assert continental._chord_bearing(line, 0.0) == pytest.approx(0.0)
    assert continental._chord_bearing(line, line.length) == pytest.approx(0.0)
    vertical = LineString([(0.0, 0.0), (0.0, 100.0)])
    assert continental._chord_bearing(vertical, 50.0) == pytest.approx(90.0)
    # A zero-length chord carries no direction.
    dot = LineString([(0.0, 0.0), (0.0, 0.0)])
    assert continental._chord_bearing(dot, 0.0) is None


def test_acute_angle_is_undirected_and_wraps_mod_180() -> None:
    assert continental._acute_angle_degrees(0.0, 180.0) == pytest.approx(0.0)
    assert continental._acute_angle_degrees(10.0, -170.0) == pytest.approx(0.0)
    assert continental._acute_angle_degrees(0.0, 90.0) == pytest.approx(90.0)
    assert continental._acute_angle_degrees(350.0, 5.0) == pytest.approx(15.0)


def test_break_feature_tiers_step_from_asserted_join_to_distant() -> None:
    """Each tier is a descriptive lens: an endpoint within the snap tolerance is
    what the source asserting a join looks like, a nearby aligned line without an
    endpoint is a carriageway passing through, and the rest is context."""
    break_point = Point(0.0, 0.0)
    bearing = 0.0
    tolerance = ENDPOINT_SNAP_TOLERANCE_METERS

    def tier(parts: list[LineString]) -> str:
        metrics = continental._break_feature_metrics(break_point, bearing, parts)
        return continental._break_feature_tier(metrics, tolerance)

    assert tier([LineString([(0.5, 0.0), (100.0, 0.0)])]) == "asserted_endpoint_join"
    assert tier([LineString([(20.0, 0.0), (100.0, 0.0)])]) == "near_endpoint_join"
    assert tier([LineString([(-500.0, 20.0), (500.0, 20.0)])]) == "aligned_continuation"
    assert tier([LineString([(20.0, -500.0), (20.0, 500.0)])]) == "connector_or_crossing"
    assert tier([LineString([(-500.0, 400.0), (500.0, 400.0)])]) == "elsewhere_in_window"
    assert tier([]) == "no_geometry"


def _break_probe_feature(
    object_id: int,
    coordinates: list[list[float]],
    *,
    lrs: str = "KEY000000000009",
    state_fips: str = "34",
    sign_type: str = "U",
    sign_number: str = "30",
    begin: float = 0.0,
    end: float = 1.0,
) -> dict:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "LRSKEY": lrs,
            "BEGMP": 0.0,
            "ENDMP": 30.0,
            "BEGIN_POIN": begin,
            "END_POINT": end,
            "STFIPS": state_fips,
            "SIGNT1": sign_type,
            "SIGNN1": sign_number,
            "SIGNT2": " ",
            "SIGNN2": " ",
            "SIGNT3": " ",
            "SIGNN3": " ",
        },
        "geometry": {"paths": [coordinates]},
    }


class _BreakWindowTransport:
    """Returns one fixed neighbourhood for every break-end window and records
    each window envelope it is asked for."""

    def __init__(self, features: list[dict]) -> None:
        self.features = features
        self.envelopes: list[str] = []

    def post(self, _url: str, form: dict[str, str]) -> dict:
        if form.get("returnCountOnly") == "true":
            self.envelopes.append(form.get("geometry", ""))
            return {"count": len(self.features)}
        if form.get("returnIdsOnly") == "true":
            return {
                "objectIdFieldName": "OBJECTID",
                "objectIds": [f["attributes"]["OBJECTID"] for f in self.features],
            }
        return {"features": self.features}


class _ExplodingTransport:
    def post(self, _url: str, form: dict[str, str]) -> dict:
        raise AssertionError("the probe must not touch the network here")


def _broken_segment_lines():
    """Two chains along y=0 split by a 40 m break between x=2000 and x=2040,
    with the anchors at the outer ends."""
    return (
        _metric_line(1, [(0.0, 0.0), (1000.0, 0.0)], lrs="K1", record=(0.0, 0.5)),
        _metric_line(2, [(1000.0, 0.0), (2000.0, 0.0)], lrs="K1", record=(0.5, 1.0)),
        _metric_line(3, [(2040.0, 0.0), (3000.0, 0.0)], lrs="K1", record=(1.0, 1.5)),
        _metric_line(4, [(3000.0, 0.0), (4000.0, 0.0)], lrs="K1", record=(1.5, 2.0)),
    )


def _run_break_end_census(transport, tmp_path: Path, lines=None) -> dict:
    identity = _metric_identity()
    return continental._probe_segment_break_ends(
        "seg",
        "no connected path between the locked transfer nodes",
        lines if lines is not None else _broken_segment_lines(),
        (0.0, 0.0),
        (4000.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
        transport=transport,
        query_url="https://example.test/query",
        probe_root=tmp_path / "break-probe",
        page_size=2_000,
        locked_segments_by_object_id={
            1: ("seg",),
            2: ("seg",),
            3: ("seg",),
            4: ("seg",),
            20: ("other-seg",),
        },
        forward=identity,
        inverse=identity,
    )


def test_break_end_census_excludes_anchor_side_ends_and_probes_only_breaks(
    tmp_path: Path,
) -> None:
    """The chain end of each anchor's component farthest from the opposite anchor
    is the chain continuing beyond the corridor, not a break, so only the two
    facing ends of the 40 m break are probed."""
    transport = _BreakWindowTransport([])
    result = _run_break_end_census(transport, tmp_path)

    assert result["connected_component_count"] == 2
    assert result["from_component_index"] != result["to_component_index"]
    assert result["break_end_count"] == 2
    assert [end["id"] for end in result["break_ends"]] == [
        "end-0000002-00-end",
        "end-0000003-00-start",
    ]
    assert len(transport.envelopes) == 2
    assert {entry["record"]["object_id"] for entry in result["anchor_side_ends"]} == {1, 4}
    assert {entry["anchor"] for entry in result["anchor_side_ends"]} == {"from", "to"}


def test_break_end_census_classifies_every_returned_feature(tmp_path: Path) -> None:
    features = [
        # The segment's own locked records around the break: counted, not detailed.
        _break_probe_feature(
            2, [[1000.0, 0.0], [2000.0, 0.0]], sign_type="I", sign_number="80"
        ),
        _break_probe_feature(
            3, [[2040.0, 0.0], [3000.0, 0.0]], sign_type="I", sign_number="80"
        ),
        # An unsigned filler exactly bridging the break: the source asserting a join.
        _break_probe_feature(10, [[2000.0, 0.0], [2040.0, 0.0]]),
        # A crossing road through the break area.
        _break_probe_feature(11, [[2020.0, -100.0], [2020.0, 100.0]]),
        # A road elsewhere in the window.
        _break_probe_feature(12, [[2000.0, 400.0], [2040.0, 400.0]]),
        # An aligned carriageway passing through without an endpoint here.
        _break_probe_feature(13, [[1500.0, 20.0], [2500.0, 20.0]]),
        # A record locked under a different segment, ending near both break ends.
        _break_probe_feature(20, [[1990.0, -10.0], [2050.0, -10.0]]),
    ]
    transport = _BreakWindowTransport(features)
    result = _run_break_end_census(transport, tmp_path)

    left = result["break_ends"][0]
    assert left["classification"] == "asserted_join_present"
    assert left["own_locked_feature_count"] == 2
    assert left["record"]["state_fips"] == "34"
    assert left["record"]["signed_routes"] == ["I-80"]
    by_id = {feature["object_id"]: feature for feature in left["features"]}
    assert set(by_id) == {10, 11, 12, 13, 20}
    assert by_id[10]["classification"] == "asserted_endpoint_join"
    assert by_id[10]["endpoint_offset_m"] == pytest.approx(0.0)
    assert by_id[11]["classification"] == "connector_or_crossing"
    assert by_id[12]["classification"] == "elsewhere_in_window"
    assert by_id[13]["classification"] == "aligned_continuation"
    assert by_id[13]["alignment_degrees"] == pytest.approx(0.0)
    assert by_id[20]["classification"] == "near_endpoint_join"
    assert by_id[20]["locked_segment_ids"] == ["other-seg"]

    # The pair is the 40 m break, its records are milepost-contiguous, and the
    # bridging filler is seen from both of its ends.
    assert len(result["break_pairs"]) == 1
    pair = result["break_pairs"][0]
    assert pair["end_ids"] == ["end-0000002-00-end", "end-0000003-00-start"]
    assert pair["separation_m"] == pytest.approx(40.0)
    assert pair["milepost_contiguous"] is True
    assert pair["probe_windows_overlap"] is True
    assert 10 in pair["spanning_feature_object_ids"]
    assert 12 not in pair["spanning_feature_object_ids"]
    assert left["nearest_cross_component_end"]["id"] == "end-0000003-00-start"
    assert left["nearest_cross_component_end"]["separation_m"] == pytest.approx(40.0)


def test_break_end_census_reports_a_source_void_beyond_the_lock(tmp_path: Path) -> None:
    """Only the segment's own locked records around the break: the source
    asserts nothing else there, and the census must say so rather than infer."""
    transport = _BreakWindowTransport(
        [
            _break_probe_feature(2, [[1000.0, 0.0], [2000.0, 0.0]]),
            _break_probe_feature(3, [[2040.0, 0.0], [3000.0, 0.0]]),
        ]
    )
    result = _run_break_end_census(transport, tmp_path)

    for end in result["break_ends"]:
        assert end["classification"] == "source_void_beyond_lock"
        assert end["features"] == []
        assert end["own_locked_feature_count"] == 2


def test_break_end_census_resumes_spatial_responses_from_checkpoints(
    tmp_path: Path,
) -> None:
    features = [_break_probe_feature(10, [[2000.0, 0.0], [2040.0, 0.0]])]
    transport = _BreakWindowTransport(features)
    first = _run_break_end_census(transport, tmp_path)
    second = _run_break_end_census(transport, tmp_path)

    assert all(end["probe"]["resumed_pages"] == 0 for end in first["break_ends"])
    assert all(end["probe"]["resumed_pages"] == 1 for end in second["break_ends"])


def test_break_end_census_does_not_invent_breaks_on_a_single_chain(
    tmp_path: Path,
) -> None:
    """A single connected chain between the anchors has two chain ends, both of
    them anchor-side: nothing to probe, and the network must not be touched."""
    lines = (
        _metric_line(1, [(0.0, 0.0), (1000.0, 0.0)], lrs="K1"),
        _metric_line(2, [(1000.0, 0.0), (2000.0, 0.0)], lrs="K1"),
    )
    identity = _metric_identity()
    result = continental._probe_segment_break_ends(
        "seg",
        "a locked transfer anchor is farther than the anchor snap limit",
        lines,
        (0.0, 0.0),
        (2000.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
        transport=_ExplodingTransport(),
        query_url="https://example.test/query",
        probe_root=tmp_path / "break-probe",
        page_size=2_000,
        locked_segments_by_object_id={1: ("seg",), 2: ("seg",)},
        forward=identity,
        inverse=identity,
    )

    assert result["break_end_count"] == 0
    assert result["break_ends"] == []
    assert result["break_pairs"] == []
    assert len(result["anchor_side_ends"]) == 2


def test_break_end_census_refuses_a_drifted_live_service(tmp_path: Path) -> None:
    """A census against a drifted service would characterise a different dataset
    than the one whose breaks it is explaining."""
    drifted = {**_service_metadata(), "editingInfo": {"dataLastEditDate": 2}}
    # The repository lock pins a different metadata hash, so this must refuse
    # before any network or cache access.
    with pytest.raises(ValueError, match="drifted"):
        continental.probe_continental_break_ends(
            SELECTION_PATH,
            LOCK_PATH,
            TRANSFER_LOCK_PATH,
            TRANSFER_POLICY_PATH,
            EDGE_PATH_LOCK_PATH,
            CATALOG_PATH,
            tmp_path / "cache",
            tmp_path / "probe-cache",
            transport=_ExplodingTransport(),
            service_metadata=drifted,
            acquired_at="2026-08-30T00:00:00Z",
        )


def test_break_end_census_finding_is_derived_from_the_probed_ends() -> None:
    segments = [
        {
            "break_ends": [
                {"classification": "asserted_join_present"},
                {"classification": "source_void_beyond_lock"},
            ],
            "break_pairs": [
                {
                    "milepost_contiguous": True,
                    "spanning_feature_object_ids": [10],
                }
            ],
        }
    ]
    finding = continental._break_probe_finding(segments)
    assert "2 break ends" in finding
    assert "1 break ends have an unlocked" in finding
    assert "reporting lenses, not" in finding
    assert continental._break_probe_finding([]) == "No unconnected segments were probed."
