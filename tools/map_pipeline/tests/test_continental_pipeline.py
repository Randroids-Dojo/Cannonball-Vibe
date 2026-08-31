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


def test_an_on_edge_anchor_is_resolved_by_splitting_the_edge() -> None:
    # The Q-034c/d shape: the anchor sits on a locked record's interior, far
    # beyond the anchor snap limit of every record endpoint, so the solve must
    # split that record's edge at the anchor's projection rather than fail or
    # move the anchor. The unchanged 25 m limit still governs: the anchor's
    # perpendicular offset to the record (10 m here) is the recorded distance.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (1000.0, 0.0)]),
        _metric_line(2, [(1000.0, 0.0), (1200.0, 0.0)]),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (300.0, 10.0), (1200.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is True
    splits = result["anchor_edge_splits"]
    assert [
        (split["side"], split["object_id"], split["anchor_offset_m"])
        for split in splits
    ] == [("from", 1, 10.0)]
    assert splits[0]["split_distance_along_part_m"] == pytest.approx(300.0)
    assert result["from_transfer_node_snap_distance_m"] == pytest.approx(10.0)
    # The path traverses only the sub-edge from the split point onward, and the
    # lock records exactly which metre range of the record's part it covers.
    assert result["length_meters"] == pytest.approx(900.0)
    first = result["edges"][0]
    assert first["object_id"] == 1
    assert first["part_range_m"] == [300.0, 1000.0]
    assert first["reversed_for_travel"] is False
    assert "part_range_m" not in result["edges"][1]


def test_a_split_sub_edge_travelled_backwards_is_recorded_reversed() -> None:
    # Leaving the split toward the record's geometric start is travel against
    # its authored direction, exactly like a whole reversed edge.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (1000.0, 0.0)]),
        _metric_line(2, [(0.0, 0.0), (-200.0, 0.0)]),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (400.0, 5.0), (-200.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is True
    first = result["edges"][0]
    assert first["part_range_m"] == [0.0, 400.0]
    assert first["reversed_for_travel"] is True
    assert result["length_meters"] == pytest.approx(600.0)


def test_endpoint_snapping_takes_precedence_over_an_edge_split() -> None:
    # An anchor within the snap limit of a record endpoint resolves onto that
    # endpoint node exactly as before the fallback existed: the ten
    # endpoint-anchored segments' solves must be untouched by construction.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)]),
        _metric_line(2, [(100.0, 0.0), (200.0, 0.0)]),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (3.0, 4.0), (200.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["connected"] is True
    assert "anchor_edge_splits" not in result
    assert result["from_transfer_node_snap_distance_m"] == pytest.approx(5.0)
    assert all("part_range_m" not in edge for edge in result["edges"])


def test_repository_edge_path_lock_records_the_q034_anchor_splits() -> None:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    splits = {
        entry["segment_id"]: [
            (split["side"], split["object_id"]) for split in entry["anchor_edge_splits"]
        ]
        for entry in payload["segments"]
        if entry.get("anchor_edge_splits")
    }
    assert splits == {
        "i78-holland-tunnel-to-i81": [("from", 433412)],
        "i80-new-jersey-to-big-springs": [("from", 431704)],
    }
    for entry in payload["segments"]:
        for split in entry.get("anchor_edge_splits", []):
            assert split["anchor_offset_m"] <= ANCHOR_SNAP_LIMIT_METERS
            assert (
                entry[f"{split['side']}_transfer_node_snap_distance_m"]
                == split["anchor_to_node_distance_m"]
            )


def _tamper_split(tmp_path: Path, mutate) -> Path:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    entry = next(
        entry for entry in payload["segments"] if entry.get("anchor_edge_splits")
    )
    mutate(entry)
    payload["segments_sha256"] = canonical_sha256(payload["segments"])
    target = tmp_path / "edge-path-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_edge_path_lock_rejects_split_tampering(tmp_path: Path) -> None:
    def widen(entry: dict) -> None:
        entry["anchor_edge_splits"][0]["anchor_offset_m"] = (
            ANCHOR_SNAP_LIMIT_METERS * 2
        )

    with pytest.raises(ValueError, match="exceeds the\\s+anchor snap limit"):
        _validate(_tamper_split(tmp_path, widen))

    def sideless(entry: dict) -> None:
        entry["anchor_edge_splits"][0]["side"] = "sideways"

    with pytest.raises(ValueError, match="without a valid side"):
        _validate(_tamper_split(tmp_path, sideless))

    def unlocked_page(entry: dict) -> None:
        entry["anchor_edge_splits"][0]["page_response_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="unlocked page response"):
        _validate(_tamper_split(tmp_path, unlocked_page))

    def drifted_distance(entry: dict) -> None:
        entry["anchor_edge_splits"][0]["anchor_to_node_distance_m"] = 1.5

    with pytest.raises(ValueError, match="does\\s+not match its recorded split"):
        _validate(_tamper_split(tmp_path, drifted_distance))

    def exterior(entry: dict) -> None:
        split = entry["anchor_edge_splits"][0]
        split["split_distance_along_part_m"] = split["part_length_m"] + 1.0

    with pytest.raises(ValueError, match="not interior\\s+to its record part"):
        _validate(_tamper_split(tmp_path, exterior))




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


# --- Interior sweep of the break pairs wider than the census windows -----------


def test_interior_window_centers_tile_the_chord_with_overlap() -> None:
    centers = continental._interior_window_centers((0.0, 0.0), (1854.0, 0.0), 500.0)

    # ceil(1854 / 500) = 4 windows, spaced 463.5 m: each 1000 m window overlaps
    # its neighbours and the joint span covers the whole chord with margin.
    assert len(centers) == 4
    assert centers[0][0] == pytest.approx(231.75)
    assert centers[-1][0] == pytest.approx(1854.0 - 231.75)
    spacing = centers[1][0] - centers[0][0]
    assert spacing <= 500.0
    assert centers[0][0] - 500.0 < 0.0
    assert centers[-1][0] + 500.0 > 1854.0


def test_interior_feature_tiers_step_from_on_axis_to_elsewhere() -> None:
    chord = LineString([(2000.0, 0.0), (3500.0, 0.0)])

    def tier(coordinates: list[tuple[float, float]]) -> str:
        metrics = continental._interior_feature_metrics(
            chord, 0.0, [LineString(coordinates)]
        )
        return continental._interior_feature_tier(metrics)

    assert tier([(2100.0, 5.0), (3400.0, 5.0)]) == "aligned_on_axis"
    assert tier([(2750.0, -200.0), (2750.0, 200.0)]) == "crossing_on_axis"
    assert tier([(2100.0, 400.0), (3400.0, 400.0)]) == "aligned_off_axis"
    assert tier([(2750.0, 300.0), (3050.0, 600.0)]) == "elsewhere_in_window"
    empty = continental._interior_feature_metrics(chord, 0.0, [])
    assert continental._interior_feature_tier(empty) == "no_geometry"


def _sweep_segment(
    transport,
    tmp_path: Path,
    lines,
    to_anchor: tuple[float, float] = (3500.0, 0.0),
) -> dict:
    identity = _metric_identity()
    return continental._sweep_segment_gap_interiors(
        "seg",
        "no connected path between the locked transfer nodes",
        lines,
        (0.0, 0.0),
        to_anchor,
        ENDPOINT_SNAP_TOLERANCE_METERS,
        transport=transport,
        query_url="https://example.test/query",
        probe_root=tmp_path / "interior-sweep",
        page_size=2_000,
        locked_segments_by_object_id={1: ("seg",), 2: ("seg",), 3: ("seg",)},
        forward=identity,
        inverse=identity,
        buffer_meters=500.0,
        minimum_separation_meters=1_000.0,
        maximum_separation_meters=5_000.0,
    )


def _wide_gap_lines():
    """Two chains along y=0 split by a 1.5 km break between x=1000 and x=2500."""
    return (
        _metric_line(1, [(0.0, 0.0), (1000.0, 0.0)], lrs="K1"),
        _metric_line(2, [(2500.0, 0.0), (3500.0, 0.0)], lrs="K1"),
    )


def test_interior_sweep_classifies_a_wide_gap_interior(tmp_path: Path) -> None:
    features = [
        # The segment's own locked chain end: counted, not detailed.
        _break_probe_feature(1, [[0.0, 0.0], [1000.0, 0.0]], sign_type="I"),
        # An unsigned aligned road on the chord through the gap interior.
        _break_probe_feature(30, [[1000.0, 2.0], [2500.0, 2.0]]),
        # A crossing road through the interior.
        _break_probe_feature(31, [[1750.0, -300.0], [1750.0, 300.0]]),
        # An aligned parallel facility away from the chord.
        _break_probe_feature(32, [[1200.0, 300.0], [2400.0, 300.0]]),
    ]
    transport = _BreakWindowTransport(features)
    result = _sweep_segment(transport, tmp_path, _wide_gap_lines())

    assert result["pairs_beyond_sweep_limit"] == []
    assert result["pairs_covered_by_break_end_windows"] == []
    assert len(result["swept_gaps"]) == 1
    gap = result["swept_gaps"][0]
    assert gap["separation_m"] == pytest.approx(1500.0)
    assert gap["window_count"] == 3
    assert gap["classification"] == "mainline_candidate_on_axis"
    assert gap["on_axis_object_ids"] == [30]
    assert gap["own_locked_feature_count"] == 1
    by_id = {feature["object_id"]: feature for feature in gap["features"]}
    assert by_id[30]["classification"] == "aligned_on_axis"
    assert by_id[31]["classification"] == "crossing_on_axis"
    assert by_id[32]["classification"] == "aligned_off_axis"
    # Break-end identities come from the same shared selection the census uses.
    assert gap["end_ids"] == ["end-0000001-00-end", "end-0000002-00-start"]


def test_interior_sweep_reports_an_interior_void(tmp_path: Path) -> None:
    transport = _BreakWindowTransport(
        [_break_probe_feature(1, [[0.0, 0.0], [1000.0, 0.0]], sign_type="I")]
    )
    result = _sweep_segment(transport, tmp_path, _wide_gap_lines())

    gap = result["swept_gaps"][0]
    assert gap["classification"] == "interior_void_beyond_lock"
    assert gap["features"] == []


def test_interior_sweep_records_a_fragment_pairing_beyond_the_limit(
    tmp_path: Path,
) -> None:
    """A 6.6 km pairing measures fragment isolation, not a candidate mainline
    break: it is recorded as beyond the sweep limit and never probed."""
    lines = (
        _metric_line(1, [(0.0, 0.0), (1000.0, 0.0)], lrs="K1"),
        _metric_line(2, [(7600.0, 0.0), (8600.0, 0.0)], lrs="K1"),
    )
    result = _sweep_segment(
        _ExplodingTransport(), tmp_path, lines, to_anchor=(8600.0, 0.0)
    )

    assert result["swept_gaps"] == []
    assert [pair["separation_m"] for pair in result["pairs_beyond_sweep_limit"]] == [6600.0]


def test_interior_sweep_does_not_probe_a_pair_the_census_windows_cover(
    tmp_path: Path,
) -> None:
    """A 40 m pair is fully covered by the census's 500 m end windows: the
    sweep records it and must not touch the network."""
    identity = _metric_identity()
    lines = (
        _metric_line(1, [(0.0, 0.0), (1000.0, 0.0)], lrs="K1"),
        _metric_line(2, [(1040.0, 0.0), (2000.0, 0.0)], lrs="K1"),
    )
    result = continental._sweep_segment_gap_interiors(
        "seg",
        "no connected path between the locked transfer nodes",
        lines,
        (0.0, 0.0),
        (2000.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
        transport=_ExplodingTransport(),
        query_url="https://example.test/query",
        probe_root=tmp_path / "interior-sweep",
        page_size=2_000,
        locked_segments_by_object_id={1: ("seg",), 2: ("seg",)},
        forward=identity,
        inverse=identity,
        buffer_meters=500.0,
        minimum_separation_meters=1_000.0,
        maximum_separation_meters=5_000.0,
    )

    assert result["swept_gaps"] == []
    assert [
        pair["separation_m"] for pair in result["pairs_covered_by_break_end_windows"]
    ] == [40.0]


def test_interior_sweep_resumes_window_responses_from_checkpoints(
    tmp_path: Path,
) -> None:
    transport = _BreakWindowTransport(
        [_break_probe_feature(30, [[1000.0, 0.0], [2500.0, 0.0]])]
    )
    first = _sweep_segment(transport, tmp_path, _wide_gap_lines())
    second = _sweep_segment(transport, tmp_path, _wide_gap_lines())

    assert all(
        window["resumed_pages"] == 0
        for gap in first["swept_gaps"]
        for window in gap["windows"]
    )
    assert all(
        window["resumed_pages"] == 1
        for gap in second["swept_gaps"]
        for window in gap["windows"]
    )


def test_interior_sweep_refuses_a_drifted_live_service(tmp_path: Path) -> None:
    drifted = {**_service_metadata(), "editingInfo": {"dataLastEditDate": 2}}
    with pytest.raises(ValueError, match="drifted"):
        continental.probe_continental_gap_interiors(
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
            acquired_at="2026-08-31T00:00:00Z",
        )


def test_interior_sweep_finding_is_derived_from_the_swept_gaps() -> None:
    segments = [
        {
            "swept_gaps": [
                {"classification": "mainline_candidate_on_axis", "separation_m": 2500.0},
                {"classification": "interior_void_beyond_lock", "separation_m": 3000.0},
            ]
        }
    ]
    finding = continental._interior_sweep_finding(segments)
    assert "2 break-pair interiors" in finding
    assert "5.5 km" in finding
    assert "reporting lenses" in finding
    assert continental._interior_sweep_finding([]) == "No unconnected segments were swept."


# --- NHS probes at the break sites and swept gap interiors (ADR-0026) ----------


def _nhs_service_metadata() -> dict:
    return {
        "id": 0,
        "serviceItemId": "dce9f09392eb474c8ad8e6a78416279b",
        "objectIdField": "OBJECTID",
        "maxRecordCount": 2_000,
        "editingInfo": {"dataLastEditDate": 1},
        "copyrightText": (
            "This NTAD dataset is a work of the United States government and is "
            "available for unrestricted public use."
        ),
    }


def test_nhs_metadata_validation_pins_identity_and_public_domain_text() -> None:
    continental._validate_nhs_service_metadata(_nhs_service_metadata())

    with pytest.raises(ValueError, match="service item changed"):
        continental._validate_nhs_service_metadata(
            {**_nhs_service_metadata(), "serviceItemId": "something-else"}
        )
    with pytest.raises(ValueError, match="public-domain"):
        continental._validate_nhs_service_metadata(
            {**_nhs_service_metadata(), "copyrightText": "All rights reserved."}
        )
    with pytest.raises(ValueError, match="object ID field"):
        continental._validate_nhs_service_metadata(
            {**_nhs_service_metadata(), "objectIdField": "FID"}
        )


def test_nhs_query_url_must_be_inside_the_catalog_allowlist() -> None:
    from cannonball_map.catalog import CatalogSource

    def source(prefixes: tuple[str, ...]) -> CatalogSource:
        return CatalogSource(
            source_id="usdot-ntad-national-highway-system",
            publisher="USDOT",
            license_status="public_domain",
            license_evidence_url="https://example.test/evidence",
            allowed_url_prefixes=prefixes,
            raw={"service_url": "https://services.test/NHS/FeatureServer/0"},
        )

    _, query_url = continental._require_nhs_query_url(
        source(("https://services.test/NHS/FeatureServer/0",))
    )
    assert query_url == "https://services.test/NHS/FeatureServer/0/query"

    with pytest.raises(ValueError, match="outside the catalog allowlist"):
        continental._require_nhs_query_url(
            source(("https://elsewhere.test/NHS/FeatureServer/0",))
        )


def _nhs_feature(
    object_id: int,
    coordinates: list[list[float]],
    *,
    route_id: str = "R1",
    state_fips: str = "35",
    sign_type: str = "I",
    sign_number: str = "40",
    begin: float | None = 0.0,
    end: float | None = 1.0,
) -> dict:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "STFIPS": state_fips,
            "ROUTEID": route_id,
            "SIGNT1": sign_type,
            "SIGNN1": sign_number,
            "LNAME": "TEST ROAD",
            "NHS": 1,
            "STATUS": 1,
            "FACILITYT": "2",
            "BEGINPOINT": begin,
            "ENDPOINT": end,
            "MILES": 1.0,
            "YEAR": 2025,
            "VERSION": "2025.08.08",
            "UPDATE_DAT": "2025-08-08",
        },
        "geometry": {"paths": [coordinates]},
    }


def test_classify_nhs_site_reports_spanning_features_and_route_chains() -> None:
    identity = _metric_identity()
    features = [
        # One record passing within the lens of both ends: spans the site.
        _nhs_feature(1, [[-50.0, 10.0], [1050.0, 10.0]], begin=10.0, end=10.7),
        # A crossing route near neither end.
        _nhs_feature(2, [[500.0, -200.0], [500.0, 200.0]], route_id="R2", sign_type="U"),
        # A two-record chain on one route: one end each, contiguous measures.
        _nhs_feature(3, [[-40.0, 5.0], [400.0, 5.0]], route_id="R3", begin=0.0, end=0.3),
        _nhs_feature(4, [[400.0, 5.0], [1040.0, 5.0]], route_id="R3", begin=0.3, end=0.6),
    ]

    result = continental._classify_nhs_site((0.0, 0.0), (1000.0, 0.0), features, identity)

    assert result["feature_count"] == 4
    assert result["features_spanning_between_ends"] == [1]
    assert result["nhs_carries_between_ends"] is True
    groups = {
        (group["state_fips"], group["route_id"]): group for group in result["route_groups"]
    }
    assert groups[("35", "R1")]["geometry_near_both_ends"] is True
    assert groups[("35", "R2")]["geometry_near_both_ends"] is False
    chain = groups[("35", "R3")]
    assert chain["feature_count"] == 2
    assert chain["geometry_near_both_ends"] is True
    assert chain["measure_spans"] == [[0.0, 0.6]]
    assert chain["largest_measure_gap_miles"] == pytest.approx(0.0)
    by_id = {feature["object_id"]: feature for feature in result["features"]}
    assert by_id[1]["spans_between_ends"] is True
    assert by_id[2]["spans_between_ends"] is False
    assert by_id[1]["alignment_degrees"] == pytest.approx(0.0)
    assert by_id[2]["alignment_degrees"] == pytest.approx(90.0)


def test_classify_nhs_site_reports_an_nhs_void() -> None:
    identity = _metric_identity()
    result = continental._classify_nhs_site((0.0, 0.0), (1000.0, 0.0), [], identity)

    assert result["feature_count"] == 0
    assert result["nhs_carries_between_ends"] is False
    assert result["route_groups"] == []


def test_nhs_probe_refuses_an_expected_metadata_drift(tmp_path: Path) -> None:
    """When the disposition evidence names an expected NHS snapshot, a drifted
    live service must be refused before any cache or network probing."""
    with pytest.raises(ValueError, match="drifted from the expected snapshot"):
        continental.probe_continental_nhs_breaks(
            SELECTION_PATH,
            LOCK_PATH,
            TRANSFER_LOCK_PATH,
            TRANSFER_POLICY_PATH,
            EDGE_PATH_LOCK_PATH,
            CATALOG_PATH,
            tmp_path / "cache",
            tmp_path / "probe-cache",
            transport=_ExplodingTransport(),
            service_metadata=_nhs_service_metadata(),
            expected_metadata_sha256="0" * 64,
            acquired_at="2026-08-31T00:00:00Z",
        )


def test_nhs_probe_refuses_a_service_without_public_domain_status(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="public-domain"):
        continental.probe_continental_nhs_breaks(
            SELECTION_PATH,
            LOCK_PATH,
            TRANSFER_LOCK_PATH,
            TRANSFER_POLICY_PATH,
            EDGE_PATH_LOCK_PATH,
            CATALOG_PATH,
            tmp_path / "cache",
            tmp_path / "probe-cache",
            transport=_ExplodingTransport(),
            service_metadata={
                **_nhs_service_metadata(),
                "copyrightText": "All rights reserved.",
            },
            acquired_at="2026-08-31T00:00:00Z",
        )


def test_nhs_probe_finding_is_derived_from_the_probed_sites() -> None:
    sites = [
        {"nhs": {"nhs_carries_between_ends": True, "feature_count": 3}},
        {"nhs": {"nhs_carries_between_ends": False, "feature_count": 0}},
    ]
    interiors = [{"nhs": {"nhs_carries_between_ends": True, "feature_count": 5}}]
    finding = continental._nhs_probe_finding(sites, interiors)
    assert "2 bounded break sites" in finding
    assert "1 sites and 1 interiors" in finding
    assert "not a snap, join, or selection" in finding


# --- Q-034 per-site disposition record ------------------------------------------


DISPOSITION_PATH = Path("data/routes/continental/break-disposition.v1.json")
NHS_FILL_LOCK_PATH = Path("data/routes/continental/nhs-fill-lock.v1.json")
OVERLAY_LOCK_PATH = Path(
    "data/routes/continental/reconstruction-overlay-lock.v1.json"
)


class _WhereEchoTransport:
    """Serves OBJECTIDs parsed from an ``OBJECTID IN (...)`` predicate."""

    def post(self, _url: str, form: dict[str, str]) -> dict:
        if "objectIds" in form:
            ids = sorted(int(value) for value in form["objectIds"].split(","))
        else:
            where = form.get("where", "")
            ids = sorted(
                int(value)
                for value in where[where.index("(") + 1 : where.index(")")].split(",")
            )
        if form.get("returnCountOnly") == "true":
            return {"count": len(ids)}
        if form.get("returnIdsOnly") == "true":
            return {"objectIdFieldName": "OBJECTID", "objectIds": ids}
        return {
            "features": [
                {
                    "attributes": {"OBJECTID": object_id},
                    "geometry": {"paths": [[[0.0, 0.0], [0.001, 0.001]]]},
                }
                for object_id in ids
            ]
        }


def _fabricated_supplement_inputs(tmp_path: Path) -> tuple[Path, Path, dict]:
    metadata = _service_metadata()
    cache = tmp_path / "cache"
    lock = tmp_path / "lock.json"
    acquire_continental_nhpn_candidates(
        SELECTION_PATH,
        CATALOG_PATH,
        lock,
        cache,
        transport=_OneFeatureTransport(),
        service_metadata=metadata,
        acquired_at="2026-08-04T01:58:01Z",
    )
    disposition = {
        "schema_version": 1,
        "open_question": "Q-034",
        "sites": [
            {
                "site_id": "i80-new-jersey-to-big-springs--component-00-01",
                "segment_id": "i80-new-jersey-to-big-springs",
                "disposition": "nhpn_scoped_acquisition",
                "joining_object_ids": [7],
            }
        ],
    }
    disposition_path = tmp_path / "disposition.json"
    disposition_path.write_text(json.dumps(disposition), encoding="utf-8")
    return lock, disposition_path, metadata


def test_supplement_acquisition_extends_the_lock_without_rewriting_history(
    tmp_path: Path,
) -> None:
    lock, disposition_path, metadata = _fabricated_supplement_inputs(tmp_path)
    original = json.loads(lock.read_text(encoding="utf-8"))
    payload = continental.acquire_continental_nhpn_supplements(
        disposition_path,
        SELECTION_PATH,
        CATALOG_PATH,
        lock,
        tmp_path / "cache",
        lock,
        transport=_WhereEchoTransport(),
        service_metadata=metadata,
        acquired_at="2026-08-31T00:00:00Z",
    )
    assert payload["nhpn"]["segment_snapshots"] == original["nhpn"]["segment_snapshots"]
    supplements = payload["nhpn"]["supplementary_acquisitions"]
    assert [entry["object_ids"] for entry in supplements] == [[7]]
    assert supplements[0]["predicate"] == "OBJECTID IN (7)"
    assert payload["nhpn"]["candidate_union"]["expected_count"] == 2
    metadata_hash = canonical_sha256(metadata)
    checkpoint = (
        tmp_path
        / "cache"
        / metadata_hash
        / "supplementary"
        / "i80-new-jersey-to-big-springs--component-00-01"
        / "page-000000.json"
    )
    assert checkpoint.is_file()
    validate_continental_route_lock(lock, CATALOG_PATH, SELECTION_PATH)


def test_supplement_acquisition_refuses_drift_and_relocking(tmp_path: Path) -> None:
    lock, disposition_path, metadata = _fabricated_supplement_inputs(tmp_path)
    drifted = {**metadata, "editingInfo": {"dataLastEditDate": 2}}
    with pytest.raises(ValueError, match="drifted from the candidate lock"):
        continental.acquire_continental_nhpn_supplements(
            disposition_path,
            SELECTION_PATH,
            CATALOG_PATH,
            lock,
            tmp_path / "cache",
            tmp_path / "out.json",
            transport=_WhereEchoTransport(),
            service_metadata=drifted,
        )
    relocking = {
        "schema_version": 1,
        "open_question": "Q-034",
        "sites": [
            {
                "site_id": "i80-new-jersey-to-big-springs--component-00-01",
                "segment_id": "i80-new-jersey-to-big-springs",
                "disposition": "nhpn_scoped_acquisition",
                "joining_object_ids": [1],
            }
        ],
    }
    disposition_path.write_text(json.dumps(relocking), encoding="utf-8")
    with pytest.raises(ValueError, match="already-locked"):
        continental.acquire_continental_nhpn_supplements(
            disposition_path,
            SELECTION_PATH,
            CATALOG_PATH,
            lock,
            tmp_path / "cache",
            tmp_path / "out.json",
            transport=_WhereEchoTransport(),
            service_metadata=metadata,
        )


def test_route_lock_validator_rejects_supplement_tampering(tmp_path: Path) -> None:
    lock, disposition_path, metadata = _fabricated_supplement_inputs(tmp_path)
    continental.acquire_continental_nhpn_supplements(
        disposition_path,
        SELECTION_PATH,
        CATALOG_PATH,
        lock,
        tmp_path / "cache",
        lock,
        transport=_WhereEchoTransport(),
        service_metadata=metadata,
        acquired_at="2026-08-31T00:00:00Z",
    )
    payload = json.loads(lock.read_text(encoding="utf-8"))

    tampered = copy.deepcopy(payload)
    tampered["nhpn"]["supplementary_acquisitions"][0]["predicate"] = "OBJECTID IN (8)"
    lock.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="predicate drifted"):
        validate_continental_route_lock(lock, CATALOG_PATH, SELECTION_PATH)

    tampered = copy.deepcopy(payload)
    tampered["nhpn"]["supplementary_acquisitions"][0]["disposition"] = "nhs_fill"
    lock.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="disposition ancestry"):
        validate_continental_route_lock(lock, CATALOG_PATH, SELECTION_PATH)

    tampered = copy.deepcopy(payload)
    supplement = copy.deepcopy(tampered["nhpn"]["supplementary_acquisitions"][0])
    supplement["site_id"] = "i80-new-jersey-to-big-springs--component-00-02"
    tampered["nhpn"]["supplementary_acquisitions"].append(supplement)
    lock.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="repeats locked OBJECTIDs"):
        validate_continental_route_lock(lock, CATALOG_PATH, SELECTION_PATH)


def _tampered_fill_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(NHS_FILL_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["sites_sha256"] = canonical_sha256(payload["sites"])
    payload["chain_connectivity_sha256"] = canonical_sha256(
        payload["chain_connectivity"]["segments"]
    )
    target = tmp_path / "nhs-fill-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _validate_fill_lock(path: Path) -> dict:
    return continental.validate_continental_nhs_fill_lock(
        path,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        CATALOG_PATH,
    )


def test_nhs_fill_lock_rejects_semantic_tampering(tmp_path: Path) -> None:
    def gap(payload: dict) -> None:
        payload["sites"][0]["fill_route_groups"][0]["largest_measure_gap_miles"] = 0.5

    with pytest.raises(ValueError, match="measure gap"):
        _validate_fill_lock(_tampered_fill_lock(tmp_path, gap))

    def ancestry(payload: dict) -> None:
        payload["ancestry"]["nhs_centerlines"]["decision"] = "ADR-0001"

    with pytest.raises(ValueError, match="dual ancestry"):
        _validate_fill_lock(_tampered_fill_lock(tmp_path, ancestry))

    def blockers(payload: dict) -> None:
        for entry in payload["chain_connectivity"]["segments"]:
            if not entry["chain_connected_with_fills"]:
                entry["remaining_blockers"] = []
                break

    with pytest.raises(ValueError, match="no.*remaining blockers|remaining blockers"):
        _validate_fill_lock(_tampered_fill_lock(tmp_path, blockers))

    def direction(payload: dict) -> None:
        payload["westbound_selection_validated"] = True

    with pytest.raises(ValueError, match="westbound selection"):
        _validate_fill_lock(_tampered_fill_lock(tmp_path, direction))


def test_implemented_disposition_rejects_unimplemented_scoped_sites(
    tmp_path: Path,
) -> None:
    payload = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    for site in payload["sites"]:
        if site["disposition"] == "nhpn_scoped_acquisition":
            site["joining_object_ids"] = sorted(
                {*site["joining_object_ids"], 999_999_999}
            )
            break
    target = tmp_path / "disposition.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="not implemented by a matching"):
        _validate_disposition(target, NHS_FILL_LOCK_PATH)


def _disposition_payload() -> dict:
    from cannonball_map.manifest import compute_sha256

    edge = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    unconnected = sorted(
        entry["segment_id"] for entry in edge["segments"] if not entry["connected"]
    )
    sites = []
    for index, segment_id in enumerate(unconnected):
        sites.append(
            {
                "site_id": f"{segment_id}--component-00-01",
                "segment_id": segment_id,
                "kind": "component_gap",
                "separation_m": 100.0,
                "evidence_summary": "fabricated for the validator test",
                "disposition": "ambiguous",
                "q034_subitem": f"Q-034{chr(ord('a') + index)}",
                "blocking_question": "fabricated blocking question",
            }
        )
    return {
        "schema_version": 1,
        "status": "dispositions_recorded_lock_revision_pending",
        "decision": _selection()["decision"],
        "authored_at": "2026-08-31T00:00:00Z",
        "open_question": "Q-034",
        "authority": {
            "decision_records": ["ADR-0018", "ADR-0024", "ADR-0026"],
            "owner_directive": "2026-08-30 owner adoption of supplementary sources",
        },
        "route_selection_sha256": compute_sha256(SELECTION_PATH),
        "candidate_lock_sha256": compute_sha256(LOCK_PATH),
        "transfer_lock_sha256": compute_sha256(TRANSFER_LOCK_PATH),
        "edge_path_lock_sha256": compute_sha256(EDGE_PATH_LOCK_PATH),
        "source_policy": {
            "bridging_performed": False,
            "locks_modified": False,
            "openstreetmap_ancestry_allowed": False,
            "tolerance_changed": False,
        },
        "evidence": [
            {"path": "docs/audits/p0-021/2026-08-30-geometric-break-probe.md"},
            {"artifact": ".tools/continental/nhs-break-probe.json", "sha256": "0" * 64},
        ],
        "site_count": len(sites),
        "disposition_counts": {"ambiguous": len(sites)},
        "sites": sites,
        "census_ends": [
            {
                "end_id": "end-0000001-00-end",
                "segment_id": unconnected[0],
                "classification": "beyond_corridor_continuation",
                "note": "fabricated for the validator test",
            }
        ],
        "implementation": {
            "implemented_this_slice": ["evidence acquisition and this record"],
            "deferred_to_lock_revision": ["scoped acquisition into the candidate lock"],
        },
    }


def _write_disposition(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "break-disposition.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _validate_disposition(
    path: Path,
    nhs_fill_lock: Path | None = None,
    overlay_lock: Path | None = None,
) -> dict:
    return continental.validate_continental_break_dispositions(
        path,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        CATALOG_PATH,
        nhs_fill_lock_path=nhs_fill_lock,
        overlay_lock_path=overlay_lock,
    )


def test_break_disposition_record_validates_and_rejects_drift(tmp_path: Path) -> None:
    payload = _disposition_payload()
    validated = _validate_disposition(_write_disposition(tmp_path, payload))
    assert validated["site_count"] == len(payload["sites"])

    with pytest.raises(ValueError, match="unsupported status"):
        _validate_disposition(
            _write_disposition(tmp_path, {**payload, "status": "complete"})
        )
    with pytest.raises(ValueError, match="input hash drifted"):
        _validate_disposition(
            _write_disposition(tmp_path, {**payload, "candidate_lock_sha256": "0" * 64})
        )
    with pytest.raises(ValueError, match="does not cite ADR-0018"):
        _validate_disposition(
            _write_disposition(
                tmp_path,
                {**payload, "authority": {**payload["authority"], "decision_records": []}},
            )
        )


def test_break_disposition_bounds_a_reconstruction_exception(tmp_path: Path) -> None:
    payload = _disposition_payload()
    boundary = {
        "from_coordinate": {"longitude": -96.0, "latitude": 41.2},
        "to_coordinate": {"longitude": -96.0, "latitude": 41.2},
        "length_m": 1.011,
    }
    payload["sites"][0] = {
        **payload["sites"][0],
        "disposition": "bounded_reconstruction_exception",
        "exception": {
            "kind": "authoring_micro_gap",
            "rationale": "milepost-contiguous records a source quantum apart",
            "boundary": boundary,
        },
    }
    payload["disposition_counts"] = {
        "ambiguous": len(payload["sites"]) - 1,
        "bounded_reconstruction_exception": 1,
    }
    assert _validate_disposition(_write_disposition(tmp_path, payload))

    overwide = copy.deepcopy(payload)
    overwide["sites"][0]["exception"]["boundary"]["length_m"] = 320.0
    with pytest.raises(ValueError, match="bounded-exception ceiling"):
        _validate_disposition(_write_disposition(tmp_path, overwide))


def test_break_disposition_rejects_acquiring_already_locked_records(
    tmp_path: Path,
) -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_id = lock["nhpn"]["segment_snapshots"][0]["object_ids"][0]
    payload = _disposition_payload()
    site = {
        **payload["sites"][0],
        "disposition": "nhpn_scoped_acquisition",
        "joining_object_ids": [999_999_999],
        "direction_review": "westbound continuation on the same carriageway",
        "corridor_fit": "unsigned concurrency of the declared route",
    }
    payload["sites"][0] = site
    payload["disposition_counts"] = {
        "ambiguous": len(payload["sites"]) - 1,
        "nhpn_scoped_acquisition": 1,
    }
    assert _validate_disposition(_write_disposition(tmp_path, payload))

    relocked = copy.deepcopy(payload)
    relocked["sites"][0]["joining_object_ids"] = [locked_id]
    with pytest.raises(ValueError, match="already-locked"):
        _validate_disposition(_write_disposition(tmp_path, relocked))


def test_break_disposition_requires_full_segment_coverage(tmp_path: Path) -> None:
    payload = _disposition_payload()
    payload["sites"] = payload["sites"][1:]
    payload["site_count"] = len(payload["sites"])
    payload["disposition_counts"] = {"ambiguous": len(payload["sites"])}
    with pytest.raises(ValueError, match="exactly the unconnected segments"):
        _validate_disposition(_write_disposition(tmp_path, payload))


def test_break_disposition_requires_a_subitem_for_ambiguity(tmp_path: Path) -> None:
    payload = _disposition_payload()
    payload["sites"][0] = {**payload["sites"][0], "q034_subitem": "Q-034"}
    with pytest.raises(ValueError, match="without a Q-034 sub-item"):
        _validate_disposition(_write_disposition(tmp_path, payload))


def test_repository_break_disposition_record_validates() -> None:
    payload = _validate_disposition(
        DISPOSITION_PATH, NHS_FILL_LOCK_PATH, OVERLAY_LOCK_PATH
    )
    assert payload["site_count"] == 14
    assert payload["open_question"] == "Q-034"
    assert payload["status"] == "lock_revision_implemented_topology_closed"
    assert payload["source_policy"]["locks_modified"] is True
    assert payload["disposition_counts"] == {
        "anchor_edge_split": 2,
        "bounded_reconstruction_exception": 2,
        "nhpn_scoped_acquisition": 5,
        "nhs_fill": 5,
    }
    assert "ambiguous" not in payload["disposition_counts"]


def test_implemented_disposition_requires_the_fill_lock() -> None:
    with pytest.raises(ValueError, match="requires the NHS fill lock"):
        _validate_disposition(DISPOSITION_PATH)


def test_closed_disposition_requires_the_overlay_lock() -> None:
    with pytest.raises(ValueError, match="requires the reconstruction overlay lock"):
        _validate_disposition(DISPOSITION_PATH, NHS_FILL_LOCK_PATH)


def test_closed_disposition_rejects_a_remaining_ambiguous_site(tmp_path: Path) -> None:
    payload = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    site = next(
        site for site in payload["sites"] if site["disposition"] == "anchor_edge_split"
    )
    site["disposition"] = "ambiguous"
    site["q034_subitem"] = site.pop("resolved_q034_subitem")
    site["blocking_question"] = "reopened for the validator test"
    payload["disposition_counts"] = {
        "ambiguous": 1,
        "anchor_edge_split": 1,
        "bounded_reconstruction_exception": 2,
        "nhpn_scoped_acquisition": 5,
        "nhs_fill": 5,
    }
    target = tmp_path / "disposition.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="may not carry an ambiguous site"):
        _validate_disposition(target, NHS_FILL_LOCK_PATH, OVERLAY_LOCK_PATH)


def test_closed_disposition_rejects_an_unimplemented_anchor_split(
    tmp_path: Path,
) -> None:
    payload = json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))
    site = next(
        site for site in payload["sites"] if site["disposition"] == "anchor_edge_split"
    )
    site["anchor_split"]["object_id"] = 999_999_999
    target = tmp_path / "disposition.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="matching\\s+anchor edge split"):
        _validate_disposition(target, NHS_FILL_LOCK_PATH, OVERLAY_LOCK_PATH)


def test_repository_nhs_fill_lock_validates() -> None:
    payload = continental.validate_continental_nhs_fill_lock(
        NHS_FILL_LOCK_PATH,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        CATALOG_PATH,
    )
    assert payload["site_count"] == 5
    assert payload["westbound_selection_validated"] is False
    assert payload["ancestry"]["nhs_centerlines"]["decision"] == "ADR-0026"
    chain = payload["chain_connectivity"]
    # i78 chains at the fill stage: the Delaware River fill plus the Q-034c
    # anchor edge split. i80 still waits on its two authored overlays, which
    # bridge in the reconstruction overlay lock, not here.
    assert chain["chained_segment_count"] == 3
    blocked = {
        entry["segment_id"]: entry["remaining_blockers"]
        for entry in chain["segments"]
        if not entry["chain_connected_with_fills"]
    }
    assert set(blocked) == {"i80-new-jersey-to-big-springs"}
    for blockers in blocked.values():
        assert blockers
        assert {blocker["disposition"] for blocker in blockers} == {
            "bounded_reconstruction_exception"
        }
    i78 = next(
        entry
        for entry in chain["segments"]
        if entry["segment_id"] == "i78-holland-tunnel-to-i81"
    )
    assert i78["chain_connected_with_fills"] is True
    assert [
        (split["side"], split["object_id"])
        for split in i78["anchor_edge_splits"]
    ] == [("from", 433412)]


def test_repository_candidate_lock_carries_the_q034_supplements() -> None:
    payload = validate_continental_route_lock(LOCK_PATH, CATALOG_PATH, SELECTION_PATH)
    supplements = payload["nhpn"]["supplementary_acquisitions"]
    by_site = {entry["site_id"]: entry["object_ids"] for entry in supplements}
    assert by_site == {
        "i10-ontario-to-i405--component-00-01": [
            545360, 545363, 545364, 545365, 545366, 545370,
            546470, 546510, 546519, 546522, 546524, 546525, 546526,
            546556, 546557, 546558, 546559, 546568, 546569,
            546571, 546572, 546573, 546574,
        ],
        "i15-salt-lake-to-cove-fort--component-00-01": [43839, 43841],
        "i40-i81-to-barstow--component-00-01": [38597],
        "i40-i81-to-barstow--component-02-04": [218838],
        "i70-denver-to-cove-fort--component-01-02": [59709],
    }
    assert payload["nhpn"]["candidate_union"]["expected_count"] == 15_553


# --- ADR-0018 reconstruction gates: authored micro-gap overlays -----------------


def _overlay_exception_site(
    from_xy: tuple[float, float],
    to_xy: tuple[float, float],
    length: float,
    site_id: str = "seg--component-00-01",
) -> dict:
    return {
        "site_id": site_id,
        "segment_id": "seg",
        "kind": "component_gap",
        "disposition": "bounded_reconstruction_exception",
        "exception": {
            "kind": "authoring_micro_gap",
            "rationale": "fabricated authoring micro-gap",
            "boundary": {
                "from_coordinate": {"longitude": from_xy[0], "latitude": from_xy[1]},
                "to_coordinate": {"longitude": to_xy[0], "latitude": to_xy[1]},
                "length_m": length,
            },
        },
    }


def _author_overlay(site: dict, metric_lines) -> dict:
    return continental._author_overlay_for_site(
        site,
        tuple(metric_lines),
        ENDPOINT_SNAP_TOLERANCE_METERS,
        _metric_identity(),
        [{"path": "docs/audits/p0-021/2026-08-31-per-site-disposition.md"}],
    )


def test_overlay_authoring_passes_every_applicable_gate() -> None:
    # Two records milepost-contiguous on one key, authored 5 m apart: the
    # Omaha shape. The overlay must bind to both chain ends exactly, prove the
    # source's asserted adjacency, and record the heading constraint for the
    # geometry stage rather than adjudicating it at chord scale.
    metric_lines = [
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], record=(0.0, 1.0)),
        _metric_line(2, [(105.0, 0.0), (205.0, 0.0)], record=(1.0, 2.0)),
    ]
    overlay = _author_overlay(
        _overlay_exception_site((100.0, 0.0), (105.0, 0.0), 5.0), metric_lines
    )
    assert overlay["overlay_id"] == "seg--component-00-01--authored-overlay"
    gates = overlay["gates"]
    for name in ("endpoint_position", "length_bound", "source_adjacency", "self_intersection"):
        assert gates[name]["passed"] is True
    assert gates["source_adjacency"]["measured"]["object_ids"] == [1, 2]
    heading = gates["heading_continuity"]
    assert heading["deferred_to"] == "reconstruction-geometry-stage"
    assert heading["measured"]["end_tangent_deviation_degrees"] == pytest.approx(0.0)
    assert gates["deferred"]["gates"] == list(
        continental.RECONSTRUCTION_OVERLAY_DEFERRED_GATES
    )
    assert overlay["geometry"]["length_m"] == pytest.approx(5.0)
    assert {record["end"] for record in overlay["adjoining_records"]} == {"from", "to"}


def test_overlay_authoring_rejects_a_boundary_off_the_chain_ends() -> None:
    metric_lines = [
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], record=(0.0, 1.0)),
        _metric_line(2, [(105.0, 0.0), (205.0, 0.0)], record=(1.0, 2.0)),
    ]
    with pytest.raises(ValueError, match="endpoint_position"):
        _author_overlay(
            _overlay_exception_site((97.0, 0.0), (105.0, 0.0), 8.0), metric_lines
        )


def test_overlay_authoring_rejects_a_gap_the_source_does_not_assert() -> None:
    # Records on the same key but not milepost-contiguous: a real void wearing
    # a micro-gap's size. ADR-0018 forbids authoring over it.
    metric_lines = [
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], record=(0.0, 1.0)),
        _metric_line(2, [(105.0, 0.0), (205.0, 0.0)], record=(1.5, 2.0)),
    ]
    with pytest.raises(ValueError, match="source_adjacency"):
        _author_overlay(
            _overlay_exception_site((100.0, 0.0), (105.0, 0.0), 5.0), metric_lines
        )


def test_overlay_authoring_enforces_the_exception_ceiling() -> None:
    metric_lines = [
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], record=(0.0, 1.0)),
        _metric_line(2, [(140.0, 0.0), (240.0, 0.0)], record=(1.0, 2.0)),
    ]
    with pytest.raises(ValueError, match="length_bound"):
        _author_overlay(
            _overlay_exception_site((100.0, 0.0), (140.0, 0.0), 40.0), metric_lines
        )


def test_overlay_authoring_rejects_a_drifted_pinned_length() -> None:
    metric_lines = [
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], record=(0.0, 1.0)),
        _metric_line(2, [(105.0, 0.0), (205.0, 0.0)], record=(1.0, 2.0)),
    ]
    with pytest.raises(ValueError, match="length_bound"):
        _author_overlay(
            _overlay_exception_site((100.0, 0.0), (105.0, 0.0), 5.5), metric_lines
        )


def _validate_overlay_lock(path: Path) -> dict:
    return continental.validate_continental_reconstruction_overlays(
        path,
        DISPOSITION_PATH,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        NHS_FILL_LOCK_PATH,
        CATALOG_PATH,
    )


def _tampered_overlay_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(OVERLAY_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["overlay_count"] = len(payload["overlays"])
    payload["overlays_sha256"] = canonical_sha256(payload["overlays"])
    payload["chain_connectivity_sha256"] = canonical_sha256(
        payload["chain_connectivity"]["segments"]
    )
    target = tmp_path / "reconstruction-overlay-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_repository_reconstruction_overlay_lock_validates() -> None:
    payload = _validate_overlay_lock(OVERLAY_LOCK_PATH)
    assert payload["decision"] == "ADR-0018"
    assert payload["overlay_count"] == 2
    corridor = payload["corridor"]
    assert corridor["segments_chaining_anchor_to_anchor"] == 12
    assert corridor["segment_count"] == 12
    deviations = {
        overlay["site_id"]: overlay["gates"]["heading_continuity"]["measured"][
            "end_tangent_deviation_degrees"
        ]
        for overlay in payload["overlays"]
    }
    # Omaha continues straight through its 1.011 m gap; the Quad Cities gap
    # sits on the I-80/I-74 interchange corner of I-80's own LRS, and the
    # measured corner is the geometry stage's authoring constraint.
    assert deviations == {
        "i80-new-jersey-to-big-springs--component-00-01": 0.0,
        "i80-new-jersey-to-big-springs--component-01-02": 77.2,
    }
    i80 = next(
        entry
        for entry in payload["chain_connectivity"]["segments"]
        if entry["segment_id"] == "i80-new-jersey-to-big-springs"
    )
    assert i80["chain_connected_with_fills"] is True
    assert i80["overlay_site_ids_on_chain"] == [
        "i80-new-jersey-to-big-springs--component-00-01",
        "i80-new-jersey-to-big-springs--component-01-02",
    ]


def test_overlay_lock_rejects_semantic_tampering(tmp_path: Path) -> None:
    def direction(payload: dict) -> None:
        payload["westbound_selection_validated"] = True

    with pytest.raises(ValueError, match="westbound selection"):
        _validate_overlay_lock(_tampered_overlay_lock(tmp_path, direction))

    def boundary(payload: dict) -> None:
        payload["overlays"][0]["boundary"]["length_m"] = 2.0

    with pytest.raises(ValueError, match="pinned exception boundary"):
        _validate_overlay_lock(_tampered_overlay_lock(tmp_path, boundary))

    def failed_gate(payload: dict) -> None:
        payload["overlays"][0]["gates"]["source_adjacency"]["passed"] = False

    with pytest.raises(ValueError, match="did not pass"):
        _validate_overlay_lock(_tampered_overlay_lock(tmp_path, failed_gate))

    def missing_heading(payload: dict) -> None:
        payload["overlays"][0]["gates"]["heading_continuity"]["measured"] = {}

    with pytest.raises(ValueError, match="measured end-tangent"):
        _validate_overlay_lock(_tampered_overlay_lock(tmp_path, missing_heading))

    def partial_coverage(payload: dict) -> None:
        payload["overlays"] = payload["overlays"][:1]

    with pytest.raises(ValueError, match="cover exactly"):
        _validate_overlay_lock(_tampered_overlay_lock(tmp_path, partial_coverage))

    def unauthored_citation(payload: dict) -> None:
        for entry in payload["chain_connectivity"]["segments"]:
            if entry.get("overlay_site_ids_on_chain"):
                entry["overlay_site_ids_on_chain"].append("seg--component-99-99")

    with pytest.raises(ValueError, match="unauthored overlay"):
        _validate_overlay_lock(_tampered_overlay_lock(tmp_path, unauthored_citation))

    def corridor_drift(payload: dict) -> None:
        payload["corridor"]["continuously_chained_corridor_miles"] += 100.0

    with pytest.raises(ValueError, match="corridor summary"):
        _validate_overlay_lock(_tampered_overlay_lock(tmp_path, corridor_drift))


CONFLATION_LOCK_PATH = Path("data/routes/continental/nhs-conflation-lock.v1.json")
DEM_LOCK_PATH = Path("data/routes/continental/3dep-product-lock.v1.json")


def test_measure_orientation_votes_resolve_forward_and_reversed() -> None:
    neighbour = {
        "object_id": 2,
        "begin": 11.0,
        "end": 12.0,
        "line": LineString([(1600.0, 0.0), (3200.0, 0.0)]),
    }
    forward_target = {
        "object_id": 1,
        "begin": 10.0,
        "end": 11.0,
        "line": LineString([(0.0, 0.0), (1600.0, 0.0)]),
    }
    orientation, evidence = continental._measure_adjacency_votes(
        forward_target, [neighbour], 5.0
    )
    assert orientation == "forward"
    assert [item["vote"] for item in evidence if "vote" in item] == ["forward"]

    reversed_target = {
        "object_id": 3,
        "begin": 10.0,
        "end": 11.0,
        "line": LineString([(1600.0, 0.0), (0.0, 0.0)]),
    }
    orientation, _ = continental._measure_adjacency_votes(
        reversed_target, [neighbour], 5.0
    )
    assert orientation == "reversed"


def test_measure_orientation_orients_a_quantum_short_record() -> None:
    # A 0.001-mile record is shorter than the coincidence tolerance, so both of
    # its ends sit near the neighbour; the strictly closer end still decides.
    target = {
        "object_id": 1,
        "begin": 246.177,
        "end": 246.178,
        "line": LineString([(0.0, 0.0), (1.6, 0.0)]),
    }
    east = {
        "object_id": 2,
        "begin": 246.178,
        "end": 247.0,
        "line": LineString([(1.6, 0.0), (1000.0, 0.0)]),
    }
    orientation, evidence = continental._measure_adjacency_votes(target, [east], 5.0)
    assert orientation == "forward"
    votes = [item for item in evidence if "vote" in item]
    assert votes and votes[0]["endpoint_gap_m"] == 0.0


def test_measure_orientation_refuses_conflicting_votes() -> None:
    target = {
        "object_id": 1,
        "begin": 0.0,
        "end": 1.0,
        "line": LineString([(0.0, 0.0), (1600.0, 0.0)]),
    }
    agreeing = {
        "object_id": 2,
        "begin": 1.0,
        "end": 2.0,
        "line": LineString([(1600.0, 0.0), (3200.0, 0.0)]),
    }
    conflicting = {
        "object_id": 3,
        "begin": 1.0,
        "end": 2.0,
        "line": LineString([(0.0, 0.0), (-1600.0, 0.0)]),
    }
    with pytest.raises(ValueError, match="conflicting measure-orientation"):
        continental._measure_adjacency_votes(target, [agreeing, conflicting], 5.0)


def test_conflation_margin_predicate_escapes_and_bounds() -> None:
    predicate = continental._conflation_margin_predicate("42", "A'B", 1.0, 2.0)
    assert predicate == (
        "STFIPS = '42' AND ROUTEID = 'A''B' AND ENDPOINT > 0.750000 "
        "AND BEGINPOINT < 2.250000"
    )


def test_measure_at_distance_maps_both_orientations() -> None:
    record = {
        "begin": 10.0,
        "end": 12.0,
        "line": LineString([(0.0, 0.0), (100.0, 0.0)]),
        "orientation": "forward",
    }
    assert continental._measure_at_distance(record, 25.0) == pytest.approx(10.5)
    assert continental._measure_at_distance({**record, "orientation": "reversed"}, 25.0) == (
        pytest.approx(11.5)
    )


def test_conflation_span_assembly_clips_orients_and_joins() -> None:
    mile = continental.METRES_PER_MILE
    records = [
        {
            "object_id": 1,
            "begin": 0.0,
            "end": 1.0,
            "line": LineString([(0.0, 0.0), (mile, 0.0)]),
            "orientation": "forward",
        },
        {
            "object_id": 2,
            "begin": 1.0,
            "end": 2.0,
            "line": LineString([(2.0 * mile, 0.0), (mile, 0.0)]),
            "orientation": "reversed",
        },
    ]
    span = continental._assemble_conflation_span(records, 0.5, 1.5)
    assert [piece["measure_range"] for piece in span["pieces"]] == [
        [0.5, 1.0],
        [1.0, 1.5],
    ]
    assert span["max_joint_gap_m"] == 0.0
    assert float(span["line"].length) == pytest.approx(mile, rel=1e-9)
    coordinates = list(span["line"].coords)
    assert coordinates[0][0] == pytest.approx(mile / 2)
    assert coordinates[-1][0] == pytest.approx(1.5 * mile)

    with pytest.raises(ValueError, match="do not cover"):
        continental._assemble_conflation_span(records[:1], 0.5, 1.9)


def test_span_nhpn_agreement_reports_the_void_runs() -> None:
    span_line = LineString([(0.0, 0.0), (1000.0, 0.0)])
    nearby = LineString([(0.0, 5.0), (100.0, 5.0)])
    result = continental._span_nhpn_agreement(span_line, [(None, nearby)], 50.0, 80.0)
    assert result["station_count"] == 21
    assert result["stations_within_nhpn_lens"] == 4
    assert result["stations_beyond_nhpn_lens"] == 17
    assert result["nhpn_void_runs"] == [{"start_m": 200.0, "end_m": 1000.0}]
    assert result["nhpn_agreement"]["max_offset_m"] <= 80.0


def _validate_conflation(path: Path) -> dict:
    return continental.validate_continental_nhs_conflation(
        path,
        NHS_FILL_LOCK_PATH,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        CATALOG_PATH,
    )


def test_repository_nhs_conflation_lock_validates() -> None:
    payload = _validate_conflation(CONFLATION_LOCK_PATH)
    assert payload["site_count"] == 5
    summary = payload["summary"]
    assert summary["seam_count"] == 10
    assert summary["seams_within_bound"] == 10
    assert summary["max_seam_offset_m"] <= continental.CONFLATION_SEAM_OFFSET_BOUND_METERS
    assert (
        summary["max_record_geometry_miles_ratio"]
        <= continental.CONFLATION_GEOMETRY_MILES_AGREEMENT_RATIO
    )
    # The calibrated measure axis is characterised, never absorbed: the i78
    # span's measure extent runs 14.6% past its planimetric geometry.
    i78 = next(site for site in payload["sites"] if site["site_id"].startswith("i78"))
    assert i78["span"]["measure_axis_distortion_ratio"] > 0.1
    # The i15 span is fully NHPN-covered after the Payson acquisition, while
    # the Big-I and Delaware River spans keep their recorded NHPN void runs.
    i15 = next(site for site in payload["sites"] if site["site_id"].startswith("i15"))
    assert i15["span"]["nhpn_void_runs"] == []
    assert summary["sites_with_nhpn_void"] == 3


def _tampered_conflation_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(CONFLATION_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["sites_sha256"] = canonical_sha256(payload["sites"])
    target = tmp_path / "nhs-conflation-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_nhs_conflation_lock_rejects_semantic_tampering(tmp_path: Path) -> None:
    def seam_offset(payload: dict) -> None:
        payload["sites"][0]["seams"][0]["nhs"]["seam_offset_m"] = 80.1

    with pytest.raises(ValueError, match="seam offset violates"):
        _validate_conflation(_tampered_conflation_lock(tmp_path, seam_offset))

    def direction(payload: dict) -> None:
        payload["westbound_selection_validated"] = True

    with pytest.raises(ValueError, match="westbound selection"):
        _validate_conflation(_tampered_conflation_lock(tmp_path, direction))

    def widened_bound(payload: dict) -> None:
        payload["model"]["seam_offset_bound_m"] = 200.0

    with pytest.raises(ValueError, match="model constants drifted"):
        _validate_conflation(_tampered_conflation_lock(tmp_path, widened_bound))

    def dropped_site(payload: dict) -> None:
        payload["sites"] = payload["sites"][1:]
        payload["site_count"] = len(payload["sites"])

    with pytest.raises(ValueError, match="exactly the locked fill sites"):
        _validate_conflation(_tampered_conflation_lock(tmp_path, dropped_site))

    def unlocked_record(payload: dict) -> None:
        payload["sites"][0]["seams"][0]["nhs"]["object_id"] = 999_999_999

    with pytest.raises(ValueError, match="unlocked NHS record"):
        _validate_conflation(_tampered_conflation_lock(tmp_path, unlocked_record))

    def predicate_drift(payload: dict) -> None:
        payload["sites"][0]["margin_acquisition"]["predicate"] += " AND 1=1"

    with pytest.raises(ValueError, match="margin predicate drifted"):
        _validate_conflation(_tampered_conflation_lock(tmp_path, predicate_drift))

    def miles_disagreement(payload: dict) -> None:
        payload["sites"][0]["span"]["records_checked"][0]["geometry_length_m"] *= 2.0

    with pytest.raises(ValueError, match="geometry-MILES"):
        _validate_conflation(_tampered_conflation_lock(tmp_path, miles_disagreement))

    def milepost_outside_interval(payload: dict) -> None:
        correspondence = payload["sites"][0]["seams"][0]["nhpn"]["correspondence"]
        correspondence["milepost_at_seam"] = 9_999.0

    with pytest.raises(ValueError, match="outside its record interval"):
        _validate_conflation(
            _tampered_conflation_lock(tmp_path, milepost_outside_interval)
        )


def test_dem_cell_ids_and_line_cells() -> None:
    assert continental._dem_cell_id((-106, 39)) == "n40w106"
    assert continental._dem_cell_bounds("n40w106") == (-106, 39, -105, 40)
    cells: set[tuple[int, int]] = set()
    continental._cells_intersecting_line(
        LineString([(-105.5, 39.5), (-104.5, 39.5)]), cells
    )
    assert cells == {(-106, 39), (-105, 39)}
    with pytest.raises(ValueError, match="outside CONUS"):
        continental._dem_cell_id((10, 50))
    with pytest.raises(ValueError, match="Invalid 3DEP cell id"):
        continental._dem_cell_bounds("x40w106")


def _dem_item(source_id: str, publication_date: str, **overrides) -> dict:
    item = {
        "sourceId": source_id,
        "title": f"USGS 1/3 Arc Second n40w106 {publication_date}",
        "publicationDate": publication_date,
        "format": "GeoTIFF",
        "extent": "1 x 1 degree",
        "sizeInBytes": 123,
        "downloadURL": (
            "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/"
            f"historical/n40w106/USGS_13_n40w106_{source_id}.tif"
        ),
        "boundingBox": {
            "minX": -106.0006,
            "maxX": -104.9994,
            "minY": 38.9994,
            "maxY": 40.0006,
        },
    }
    item.update(overrides)
    return item


_DEM_PREFIXES = ("https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/",)


def test_dem_product_selection_prefers_latest_then_lexical() -> None:
    items = [
        _dem_item("bbb", "2026-05-28"),
        _dem_item("aaa", "2026-05-28"),
        _dem_item("zzz", "2022-02-16"),
    ]
    selected, candidates = continental._select_dem_product(
        items, (-106, 39), "1 x 1 degree", _DEM_PREFIXES
    )
    assert selected["source_id"] == "aaa"
    assert selected["publication_date"] == "2026-05-28"
    assert len(candidates) == 3


def test_dem_product_selection_filters_and_refuses() -> None:
    non_covering = _dem_item(
        "aaa",
        "2026-05-28",
        boundingBox={"minX": -106.0, "maxX": -105.5, "minY": 39.0, "maxY": 40.0},
    )
    offsite = _dem_item(
        "bbb", "2026-05-28", downloadURL="https://example.com/USGS_13_n40w106.tif"
    )
    wrong_format = _dem_item("ccc", "2026-05-28", format="IMG")
    with pytest.raises(ValueError, match="no covering catalog product"):
        continental._select_dem_product(
            [non_covering, offsite, wrong_format], (-106, 39), "1 x 1 degree", _DEM_PREFIXES
        )


_DEM_FGDC_BODY = (
    "<metadata><horizdn>North American Datum of 1983</horizdn>"
    "<altdatum>North American Vertical Datum of 1988</altdatum>"
    "<altunits>meters</altunits>"
    "<latres>-9.259259269220167e-05</latres>"
    "<longres>9.25925927753796e-05</longres>"
    "<pubdate>20260701</pubdate></metadata>"
)


def test_dem_fgdc_parse_requires_datums_and_cell_size() -> None:
    parsed = continental._parse_dem_fgdc_metadata(_DEM_FGDC_BODY)
    assert parsed["horizontal_datum"] == "North American Datum of 1983"
    assert parsed["vertical_datum"] == "North American Vertical Datum of 1988"
    assert parsed["elevation_units"] == "meters"
    assert parsed["metadata_publication_date"] == "20260701"

    with pytest.raises(ValueError, match="does not state the product datums"):
        continental._parse_dem_fgdc_metadata(
            _DEM_FGDC_BODY.replace("altdatum>", "unstated>")
        )
    with pytest.raises(ValueError, match="not the 1/3 arc-second"):
        continental._parse_dem_fgdc_metadata(
            _DEM_FGDC_BODY.replace("-9.259259269220167e-05", "-1e-04")
        )


def _validate_dem(path: Path) -> dict:
    return continental.validate_continental_3dep_products(
        path,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        NHS_FILL_LOCK_PATH,
        OVERLAY_LOCK_PATH,
        CATALOG_PATH,
    )


def test_repository_3dep_product_lock_validates() -> None:
    payload = _validate_dem(DEM_LOCK_PATH)
    assert payload["product_count"] == payload["corridor"]["cell_count"]
    assert payload["sample_verification"]["sample_count"] == 3
    for product in payload["products"]:
        metadata = product["metadata"]
        assert metadata["horizontal_datum"] == "North American Datum of 1983"
        assert metadata["vertical_datum"] == "North American Vertical Datum of 1988"
        assert metadata["elevation_units"] == "meters"


def _tampered_dem_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(DEM_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["products_sha256"] = canonical_sha256(payload["products"])
    payload["corridor"]["cell_count"] = len(payload["corridor"]["cells"])
    payload["corridor"]["cells_sha256"] = canonical_sha256(payload["corridor"]["cells"])
    target = tmp_path / "3dep-product-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_3dep_lock_rejects_semantic_tampering(tmp_path: Path) -> None:
    def datum_drift(payload: dict) -> None:
        payload["products"][0]["metadata"]["vertical_datum"] = "EGM2008"

    with pytest.raises(ValueError, match="does not state the locked datums"):
        _validate_dem(_tampered_dem_lock(tmp_path, datum_drift))

    def offsite_product(payload: dict) -> None:
        payload["products"][0]["product"]["download_url"] = (
            "https://example.com/USGS_13_n40w106.tif"
        )

    with pytest.raises(ValueError, match="outside the catalog allowlist"):
        _validate_dem(_tampered_dem_lock(tmp_path, offsite_product))

    def stale_selection(payload: dict) -> None:
        payload["products"][0]["discovery"]["candidates"].append(
            {"source_id": "zzz", "publication_date": "2099-01-01"}
        )
        payload["products"][0]["discovery"]["candidate_count"] += 1

    with pytest.raises(ValueError, match="violates the selection policy"):
        _validate_dem(_tampered_dem_lock(tmp_path, stale_selection))

    def dropped_product(payload: dict) -> None:
        payload["products"] = payload["products"][1:]

    with pytest.raises(ValueError, match="one product per corridor cell"):
        _validate_dem(_tampered_dem_lock(tmp_path, dropped_product))

    def sample_size_drift(payload: dict) -> None:
        payload["sample_verification"]["samples"][0]["byte_count"] += 1

    with pytest.raises(ValueError, match="byte count does not match"):
        _validate_dem(_tampered_dem_lock(tmp_path, sample_size_drift))

    def non_deterministic_sample(payload: dict) -> None:
        samples = payload["sample_verification"]["samples"]
        payload["sample_verification"]["samples"] = samples[1:]
        payload["sample_verification"]["sample_count"] = len(samples) - 1

    with pytest.raises(ValueError, match="deterministic sample"):
        _validate_dem(_tampered_dem_lock(tmp_path, non_deterministic_sample))

    def direction(payload: dict) -> None:
        payload["westbound_selection_validated"] = True

    with pytest.raises(ValueError, match="westbound selection"):
        _validate_dem(_tampered_dem_lock(tmp_path, direction))


# --- Westbound directed route lock -------------------------------------------------

DIRECTED_LOCK_PATH = Path("data/routes/continental/directed-route-lock.v1.json")


def _validate_directed(path: Path) -> dict:
    return continental.validate_continental_directed_route_lock(
        path,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        NHS_FILL_LOCK_PATH,
        DISPOSITION_PATH,
        OVERLAY_LOCK_PATH,
        CONFLATION_LOCK_PATH,
        CATALOG_PATH,
    )


def test_repository_directed_route_lock_validates() -> None:
    payload = _validate_directed(DIRECTED_LOCK_PATH)

    assert payload["status"] == continental.DIRECTED_ROUTE_STATUS
    assert payload["segment_count"] == 12
    summary = payload["summary"]
    assert summary["ancestry_counts"] == {
        "nhpn_edge": 12575,
        "nhpn_split_edge": 2,
        "nhs_fill_chord": 3,
        "authored_overlay_chord": 2,
    }
    corridor = payload["corridor"]
    # The directed corridor reproduces the locked chained corridor exactly.
    assert corridor["planimetric_length_miles"] == 6294.1
    assert (
        corridor["planimetric_length_miles"]
        == corridor["chained_corridor_miles_reference"]
    )
    # The authoritative NY-to-LA figure is the canonical anchor-to-anchor
    # geodesic; the portal connectors stay excluded and recorded.
    authoritative = corridor["authoritative_distance"]
    assert authoritative["path_id"] == "central-rockies"
    assert authoritative["geodesic_length_miles"] == 2791.77
    assert {
        entry["segment_id"]
        for entry in authoritative["excluded_endpoint_connectors"]
    } == {"nyc-start-to-i80", "redondo-access-to-finish"}
    # Direction is centerline traversal only; the carriageway stays ADR-0014's.
    assert payload["westbound_selection"]["validated"] is True
    assert payload["westbound_selection"]["carriageway_direction_claimed"] is False
    assert payload["source_policy"]["carriageway_direction_claimed"] is False
    # The two junction backtracks are measured facts of the anchor model.
    backtracks = {
        entry["anchor_id"]: entry["backtrack_length_m"]
        for entry in corridor["junction_continuity"]["backtracks"]
    }
    assert backtracks == {
        "ca-barstow-i40-i15": 485.938,
        "ut-salt-lake-i80-i15": 2337.242,
    }
    # The two fills NHPN already carries stay locked but off the directed chain.
    assert {
        entry["site_id"]
        for entry in corridor["fill_spans"]["locked_but_not_on_directed_chain"]
    } == {
        "i15-salt-lake-to-cove-fort--component-00-02",
        "i40-i81-to-barstow--component-02-03",
    }


def _tampered_directed_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(DIRECTED_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["segments_sha256"] = canonical_sha256(payload["segments"])
    payload["paths_sha256"] = canonical_sha256(payload["paths"])
    target = tmp_path / "directed-route-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_directed_route_lock_rejects_semantic_tampering(tmp_path: Path) -> None:
    def claimed_carriageway(payload: dict) -> None:
        payload["westbound_selection"]["carriageway_direction_claimed"] = True

    with pytest.raises(ValueError, match="expressly not a"):
        _validate_directed(_tampered_directed_lock(tmp_path, claimed_carriageway))

    def widened_miles_bound(payload: dict) -> None:
        payload["model"]["nhpn_miles_aggregate_bound"] = 0.5

    with pytest.raises(ValueError, match="widens or drifts"):
        _validate_directed(_tampered_directed_lock(tmp_path, widened_miles_bound))

    def drifted_pin(payload: dict) -> None:
        payload["edge_path_lock_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="does not match its input"):
        _validate_directed(_tampered_directed_lock(tmp_path, drifted_pin))

    def drifted_element_length(payload: dict) -> None:
        segment = next(
            entry
            for entry in payload["segments"]
            if entry["solve"] == "nhpn_connected"
        )
        segment["elements"][0]["length_m"] += 1.0

    with pytest.raises(ValueError, match="disagrees with its elements"):
        _validate_directed(
            _tampered_directed_lock(tmp_path, drifted_element_length)
        )

    def broken_stationing(payload: dict) -> None:
        segment = payload["segments"][0]
        segment["elements"][1]["cumulative_geodesic_m"] += 1.0

    with pytest.raises(ValueError, match="stationing cascade"):
        _validate_directed(_tampered_directed_lock(tmp_path, broken_stationing))

    def unlocked_record(payload: dict) -> None:
        segment = payload["segments"][0]
        element = next(
            element
            for element in segment["elements"]
            if element["kind"] == "nhpn_edge"
        )
        element["object_id"] = 999_999_999

    with pytest.raises(ValueError, match="unlocked\\s+NHPN record"):
        _validate_directed(_tampered_directed_lock(tmp_path, unlocked_record))

    def drifted_fill_chord(payload: dict) -> None:
        for segment in payload["segments"]:
            for element in segment["elements"]:
                if element["kind"] == "nhs_fill_chord":
                    element["length_m"] += 1.0
                    return

    with pytest.raises(ValueError, match="chord length drifted"):
        _validate_directed(_tampered_directed_lock(tmp_path, drifted_fill_chord))

    def drifted_seam_measure(payload: dict) -> None:
        for segment in payload["segments"]:
            for element in segment["elements"]:
                if element["kind"] == "nhs_fill_chord":
                    element["entry_measure"] += 1.0
                    return

    with pytest.raises(ValueError, match="seam measures drifted"):
        _validate_directed(_tampered_directed_lock(tmp_path, drifted_seam_measure))

    def interpolated_split_milepost(payload: dict) -> None:
        for segment in payload["segments"]:
            for element in segment["elements"]:
                if element["kind"] == "nhpn_split_edge":
                    element["entry_milepost"] = 1.0
                    element["exit_milepost"] = 2.0
                    return

    with pytest.raises(ValueError, match="interpolates a"):
        _validate_directed(
            _tampered_directed_lock(tmp_path, interpolated_split_milepost)
        )

    def drifted_authoritative_distance(payload: dict) -> None:
        payload["corridor"]["authoritative_distance"]["geodesic_length_miles"] += 1.0

    with pytest.raises(ValueError, match="corridor section does not reproduce"):
        _validate_directed(
            _tampered_directed_lock(tmp_path, drifted_authoritative_distance)
        )

    def drifted_trend_census(payload: dict) -> None:
        payload["segments"][0]["milepost_trend"]["decreasing"] += 1
        payload["segments"][0]["milepost_trend"]["increasing"] -= 1

    with pytest.raises(ValueError, match="trend census disagrees"):
        _validate_directed(_tampered_directed_lock(tmp_path, drifted_trend_census))


def test_milepost_trend_and_increasing_runs() -> None:
    assert continental._milepost_trend(2.0, 1.0) == "decreasing"
    assert continental._milepost_trend(1.0, 2.0) == "increasing"
    assert continental._milepost_trend(1.0, 1.0) == "flat"
    assert continental._milepost_trend(None, None) == "unmeasured"

    def element(kind: str, key: str, entry: float | None, exit: float | None) -> dict:
        return {
            "kind": kind,
            "lrs_key": key,
            "entry_milepost": entry,
            "exit_milepost": exit,
        }

    elements = [
        element("nhpn_edge", "A", 1.0, 2.0),
        element("nhpn_edge", "A", 2.0, 3.0),
        element("nhpn_edge", "B", 3.0, 4.0),  # key change starts a new run
        {"kind": "nhs_fill_chord", "site_id": "x"},  # a chord interrupts a run
        element("nhpn_edge", "B", 4.0, 5.0),
        element("nhpn_edge", "B", 5.0, 4.0),  # decreasing does not run
    ]
    runs = continental._increasing_milepost_runs(elements)
    assert [
        (run["lrs_key"], run["first_element_index"], run["element_count"])
        for run in runs
    ] == [("A", 0, 2), ("B", 2, 1), ("B", 4, 1)]
    assert runs[0]["entry_milepost"] == 1.0
    assert runs[0]["exit_milepost"] == 3.0


def test_junction_backtracks_accept_only_the_mirrored_shape() -> None:
    def nhpn(object_id: int, reversed_for_travel: bool) -> dict:
        return {
            "kind": "nhpn_edge",
            "object_id": object_id,
            "part_index": 0,
            "part_range_m": None,
            "reversed_for_travel": reversed_for_travel,
            "length_m": 100.0,
        }

    arriving = {"elements": [nhpn(1, False), nhpn(2, False), nhpn(3, False)]}
    departing = {"elements": [nhpn(3, True), nhpn(2, True), nhpn(4, False)]}
    backtracks = continental._path_junction_backtracks(
        "path", ["a", "b"], {"a": arriving, "b": departing}
    )
    assert backtracks == {
        "a": {"element_count": 2, "backtrack_length_m": 200.0}
    }

    same_direction = {"elements": [nhpn(3, False), nhpn(2, False), nhpn(4, False)]}
    with pytest.raises(ValueError, match="not a\\s+mirrored junction-approach"):
        continental._path_junction_backtracks(
            "path", ["a", "b"], {"a": arriving, "b": same_direction}
        )

    non_consecutive = {"elements": [nhpn(9, False)]}
    with pytest.raises(ValueError, match="non-consecutive segments"):
        continental._path_junction_backtracks(
            "path",
            ["a", "middle", "b"],
            {"a": arriving, "middle": non_consecutive, "b": departing},
        )

    interior_overlap = {"elements": [nhpn(5, False), nhpn(2, True), nhpn(6, False)]}
    with pytest.raises(ValueError, match="not a\\s+mirrored junction-approach"):
        continental._path_junction_backtracks(
            "path", ["a", "b"], {"a": arriving, "b": interior_overlap}
        )


def test_directed_walk_orients_measures_and_prorates_miles() -> None:
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    # Two single-part records digitized in opposite directions, plus one
    # two-part record whose MILES must be prorated between its parts.
    lines = (
        LockedCandidateLine(
            "seg", 1, "0" * 64,
            LineString([(-100.0, 40.0), (-99.99, 40.0)]),
            "K1", 0.0, 10.0, 0.0, 0.6, 0, 0.53, 2,
        ),
        LockedCandidateLine(
            "seg", 2, "0" * 64,
            LineString([(-99.98, 40.0), (-99.99, 40.0)]),
            "K1", 0.0, 10.0, 0.6, 1.1, 0, 0.53, 2,
        ),
        LockedCandidateLine(
            "seg", 3, "0" * 64,
            LineString([(-99.98, 40.0), (-99.97, 40.0)]),
            "K1", 0.0, 10.0, 1.1, 2.0, 0, 1.0, 2,
        ),
        LockedCandidateLine(
            "seg", 3, "0" * 64,
            LineString([(-99.97, 40.0), (-99.96, 40.0)]),
            "K1", 0.0, 10.0, 1.1, 2.0, 1, 1.0, 2,
        ),
    )
    segment = {"id": "seg", "from": "west", "to": "east"}
    metric_lines = tuple(
        (candidate, transform(forward.transform, candidate.geometry))
        for candidate in lines
    )
    from_point = metric_lines[0][1].coords[0]
    to_point = metric_lines[3][1].coords[-1]
    edge_entry = _solve_segment_edge_path(
        segment, metric_lines, from_point, to_point, ENDPOINT_SNAP_TOLERANCE_METERS
    )
    assert edge_entry["connected"] is True

    record = continental._derive_directed_segment(
        segment,
        edge_entry,
        None,
        lines,
        (),
        (),
        {},
        from_point,
        to_point,
        ENDPOINT_SNAP_TOLERANCE_METERS,
        ANCHOR_SNAP_LIMIT_METERS,
        forward,
        inverse,
    )
    elements = record["elements"]
    assert [element["object_id"] for element in elements] == [1, 2, 3, 3]
    # Record 2 is digitized against the travel direction, so its recorded
    # mileposts swap and its trend reads decreasing.
    assert elements[0]["reversed_for_travel"] is False
    assert elements[1]["reversed_for_travel"] is True
    assert elements[1]["entry_milepost"] == 1.1
    assert elements[1]["exit_milepost"] == 0.6
    assert record["milepost_trend"] == {
        "decreasing": 1,
        "increasing": 1,
        "flat": 0,
        "unmeasured": 2,
    }
    # Single-part records keep the source MILES verbatim; the two-part record
    # prorates its MILES by traversed metric length and drops its mileposts.
    assert elements[0]["miles"] == 0.53
    assert elements[2]["entry_milepost"] is None
    assert elements[2]["miles"] == pytest.approx(0.5, abs=0.01)
    assert elements[3]["miles"] == pytest.approx(0.5, abs=0.01)
    # Stationing cascades to the recorded geodesic total.
    assert elements[-1]["cumulative_geodesic_m"] == record["geodesic_length_m"]
    assert record["planimetric_length_m"] == edge_entry["length_meters"]
    assert record["facility_type_counts"] == {"2": 4}


def test_geodesic_lengths_are_ellipsoidal() -> None:
    # One degree of longitude along the equator on GRS80.
    length = continental._geodesic_line_length_m([(0.0, 0.0), (1.0, 0.0)])
    assert length == pytest.approx(111319.49, abs=1.0)
    distance = continental._geodesic_distance_m((0.0, 0.0), (1.0, 0.0))
    assert distance == pytest.approx(length, abs=1e-6)


# --- Corridor elevation lock -------------------------------------------------------

ELEVATION_LOCK_PATH = Path("data/routes/continental/corridor-elevation-lock.v1.json")


def test_elevation_station_offsets() -> None:
    # A partial final interval appends the terminal station...
    offsets = continental._elevation_station_offsets(1050.0, 100.0)
    assert offsets[:2] == [0.0, 100.0]
    assert offsets[-2:] == [1000.0, 1050.0]
    assert len(offsets) == 12
    # ...and an exact multiple does not duplicate it.
    assert continental._elevation_station_offsets(1000.0, 100.0)[-1] == 1000.0
    assert len(continental._elevation_station_offsets(1000.0, 100.0)) == 11
    with pytest.raises(ValueError, match="positive lengths"):
        continental._elevation_station_offsets(0.0, 100.0)


def test_elevation_profile_statistics() -> None:
    offsets = [0.0, 100.0, 200.0, 300.0, 400.0, 450.0]
    elevations = [10.0, 20.0, 15.0, 15.0, 30.0, 30.5]
    stats = continental._elevation_profile_statistics(offsets, elevations, 100.0, 200.0)
    assert stats["min_elevation"] == {"elevation_m": 10.0, "station_m": 0.0}
    assert stats["max_elevation"] == {"elevation_m": 30.5, "station_m": 450.0}
    assert stats["total_climb_m"] == 25.5
    assert stats["total_descent_m"] == 5.0
    # The steepest single interval is the 15 m rise over 200-400 m's last leg.
    assert stats["max_interval_grade"] == {
        "grade_percent": 15.0,
        "from_station_m": 300.0,
    }
    # Sustained windows are whole-interval only: the 400-450 m terminal leg
    # never forms one, and the steepest 200 m window is 200-400 m.
    assert stats["max_sustained_grade"] == {
        "grade_percent": 7.5,
        "from_station_m": 200.0,
        "window_m": 200.0,
    }
    # Extreme ties resolve to the first station.
    flat = continental._elevation_profile_statistics(
        [0.0, 100.0, 200.0], [5.0, 5.0, 5.0], 100.0, 200.0
    )
    assert flat["min_elevation"]["station_m"] == 0.0
    assert flat["max_elevation"]["station_m"] == 0.0
    # A segment shorter than the window records no sustained grade.
    short = continental._elevation_profile_statistics(
        [0.0, 100.0], [5.0, 6.0], 100.0, 1000.0
    )
    assert short["max_sustained_grade"] is None
    with pytest.raises(ValueError, match="strictly increase"):
        continental._elevation_profile_statistics(
            [0.0, 0.0, 100.0], [1.0, 2.0, 3.0], 100.0, 200.0
        )


def test_elevation_station_cell_resolution() -> None:
    locked = frozenset({"n40w106", "n40w105"})
    assert continental._elevation_station_cell(-105.5, 39.5, locked) == "n40w106"
    # A station a reprojection epsilon across the cell edge resolves to a
    # locked neighbour instead of refusing.
    assert (
        continental._elevation_station_cell(-105.0000000001, 39.5, frozenset({"n40w105"}))
        == "n40w105"
    )
    with pytest.raises(ValueError, match="outside the locked corridor cells"):
        continental._elevation_station_cell(-90.5, 39.5, locked)


def test_directed_walk_geometry_sink_orients_travel() -> None:
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    lines = (
        LockedCandidateLine(
            "seg", 1, "0" * 64,
            LineString([(-100.0, 40.0), (-99.99, 40.0)]),
            "K1", 0.0, 10.0, 0.0, 0.6, 0, 0.53, 2,
        ),
        LockedCandidateLine(
            "seg", 2, "0" * 64,
            LineString([(-99.98, 40.0), (-99.99, 40.0)]),
            "K1", 0.0, 10.0, 0.6, 1.1, 0, 0.53, 2,
        ),
    )
    segment = {"id": "seg", "from": "west", "to": "east"}
    metric_lines = tuple(
        (candidate, transform(forward.transform, candidate.geometry))
        for candidate in lines
    )
    from_point = metric_lines[0][1].coords[0]
    to_point = metric_lines[1][1].coords[0]
    edge_entry = _solve_segment_edge_path(
        segment, metric_lines, from_point, to_point, ENDPOINT_SNAP_TOLERANCE_METERS
    )
    geometries: list[LineString] = []
    record = continental._derive_directed_segment(
        segment,
        edge_entry,
        None,
        lines,
        (),
        (),
        {},
        from_point,
        to_point,
        ENDPOINT_SNAP_TOLERANCE_METERS,
        ANCHOR_SNAP_LIMIT_METERS,
        forward,
        inverse,
        geometry_sink=geometries,
    )
    elements = record["elements"]
    assert len(geometries) == len(elements) == 2
    assert elements[1]["reversed_for_travel"] is True
    # Every oriented geometry starts where the previous one ended: the sink
    # yields travel-direction geometry, not source-digitization geometry.
    for previous, current in zip(geometries, geometries[1:], strict=False):
        assert Point(previous.coords[-1]).distance(Point(current.coords[0])) < 1e-6
    # The reversed element's oriented coordinates are its source coordinates
    # backwards.
    source_metric = metric_lines[1][1]
    assert list(geometries[1].coords) == list(source_metric.coords)[::-1]
    # Station coordinates walk the oriented chain monotonically westward here.
    offsets = continental._elevation_station_offsets(
        record["geodesic_length_m"], 500.0
    )
    coordinates = continental._segment_station_coordinates(
        elements, geometries, offsets, inverse
    )
    assert len(coordinates) == len(offsets)
    longitudes = [coordinate[0] for coordinate in coordinates]
    assert longitudes == sorted(longitudes)
    assert coordinates[0][0] == pytest.approx(-100.0, abs=1e-6)
    assert coordinates[-1][0] == pytest.approx(-99.98, abs=1e-6)


def _validate_elevation(path: Path) -> dict:
    return continental.validate_continental_corridor_elevation(
        path,
        DEM_LOCK_PATH,
        DIRECTED_LOCK_PATH,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        NHS_FILL_LOCK_PATH,
        DISPOSITION_PATH,
        OVERLAY_LOCK_PATH,
        CONFLATION_LOCK_PATH,
        CATALOG_PATH,
    )


def test_repository_corridor_elevation_lock_validates() -> None:
    payload = _validate_elevation(ELEVATION_LOCK_PATH)
    assert payload["status"] == continental.CORRIDOR_ELEVATION_STATUS
    assert payload["tile_count"] == 124
    assert payload["segment_count"] == 12
    summary = payload["summary"]
    assert summary["nodata_station_count"] == 0
    assert summary["tile_station_count"] == summary["station_count"]
    # The three product-lock sample hashes stay pinned end to end.
    pinned = [
        tile["cell_id"]
        for tile in payload["tiles"]
        if tile["sha256_pinned_by_product_lock"]
    ]
    assert pinned == ["n34w119", "n39w110", "n42w112"]
    # The canonical NY-to-LA path composes from its locked segments.
    canonical = next(
        path for path in payload["paths"] if path["role"] == "canonical"
    )
    assert canonical["total_geodesic_miles"] == 2791.77
    assert canonical["highest_point"]["elevation_m"] <= summary[
        "highest_point"
    ]["elevation_m"]
    assert canonical["total_climb_m"] > 0


def _tampered_elevation_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(ELEVATION_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["tiles_sha256"] = canonical_sha256(payload["tiles"])
    payload["profile_sha256"] = canonical_sha256(payload["segments"])
    payload["paths_sha256"] = canonical_sha256(payload["paths"])
    target = tmp_path / "corridor-elevation-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_corridor_elevation_lock_rejects_semantic_tampering(tmp_path: Path) -> None:
    def raised_station(payload: dict) -> None:
        payload["segments"][0]["elevations_m"][10] += 5.0

    with pytest.raises(ValueError, match="statistics do not reproduce"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, raised_station))

    def unrounded_station(payload: dict) -> None:
        payload["segments"][0]["elevations_m"][10] += 0.001

    with pytest.raises(ValueError, match="non-finite or unrounded"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, unrounded_station))

    def sample_hash_drift(payload: dict) -> None:
        payload["tiles"][0]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="pinned sample hash"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, sample_hash_drift))

    def byte_drift(payload: dict) -> None:
        payload["tiles"][1]["byte_count"] += 1

    with pytest.raises(ValueError, match="byte count does not match"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, byte_drift))

    def stripped_size_exception(payload: dict) -> None:
        tile = next(
            tile for tile in payload["tiles"] if "declared_size_exception" in tile
        )
        del tile["declared_size_exception"]

    with pytest.raises(ValueError, match="no characterised declaration exception"):
        _validate_elevation(
            _tampered_elevation_lock(tmp_path, stripped_size_exception)
        )

    def unneeded_size_exception(payload: dict) -> None:
        payload["tiles"][1]["declared_size_exception"] = dict(
            continental.ELEVATION_DECLARED_SIZE_EXCEPTIONS["n36w102"]
        )

    with pytest.raises(ValueError, match="exception it does not need"):
        _validate_elevation(
            _tampered_elevation_lock(tmp_path, unneeded_size_exception)
        )

    def dropped_tile(payload: dict) -> None:
        payload["tiles"] = payload["tiles"][1:]
        payload["tile_count"] -= 1

    with pytest.raises(ValueError, match="exactly the locked corridor cells"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, dropped_tile))

    def widened_interval(payload: dict) -> None:
        payload["model"]["station_interval_m"] = 500.0

    with pytest.raises(ValueError, match="model constants drifted"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, widened_interval))

    def smoothed_policy(payload: dict) -> None:
        payload["source_policy"]["profile_smoothing_applied"] = True

    with pytest.raises(ValueError, match="source policy drifted"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, smoothed_policy))

    def summary_drift(payload: dict) -> None:
        payload["summary"]["highest_point"]["elevation_m"] += 10.0

    with pytest.raises(ValueError, match="summary does not reproduce"):
        _validate_elevation(_tampered_elevation_lock(tmp_path, summary_drift))


CONDITIONED_LOCK_PATH = Path(
    "data/routes/continental/conditioned-profile-lock.v1.json"
)
CARRIAGEWAY_LOCK_PATH = Path(
    "data/routes/continental/westbound-carriageway-lock.v1.json"
)


def test_conditioning_seed_windows_detect_triggers_and_flat_runs() -> None:
    offsets = [index * 100.0 for index in range(12)]
    elevations = [
        100.0, 100.0, 130.0, 100.0, 100.0, 50.0, 50.0, 50.0, 50.0, 100.0,
        100.0, 100.0,
    ]
    seeds = continental._conditioning_seed_windows(offsets, elevations)
    kinds = {detection for _, _, detection in seeds}
    assert kinds == {"interval_grade_trigger", "water_flat_run"}
    # The 50 m flat run seeds even though its own grade is zero.
    assert (5, 8, "water_flat_run") in seeds
    # Terminal short legs never seed: a 30 m rise over the terminal leg is
    # quantisation, not an artifact.
    short = continental._conditioning_seed_windows(
        [0.0, 100.0, 130.0], [10.0, 10.0, 40.0]
    )
    assert short == []


def test_conditioning_window_expansion_steps_off_flat_pairs() -> None:
    offsets = [index * 100.0 for index in range(10)]
    elevations = [10.0, 9.0, 0.0, 0.0, 0.0, 0.0, 8.0, 9.0, 9.5, 9.6]
    windows = continental._conditioning_windows(offsets, elevations, "seg")
    assert len(windows) == 1
    start, end, _ = windows[0]
    # The chord is anchored on real terrain on both sides of the water, never
    # on a flat-pair value.
    assert elevations[start] != elevations[start + 1]
    assert elevations[end] != elevations[end - 1]
    assert start <= 1 and end >= 6


def test_conditioning_records_classify_and_replace_with_the_chord() -> None:
    offsets = [index * 100.0 for index in range(9)]
    ridge = [10.0, 10.0, 40.0, 80.0, 120.0, 80.0, 40.0, 10.0, 10.0]
    records, conditioned = continental._condition_segment_profile(
        "seg", offsets, ridge, [], []
    )
    assert len(records) == 1
    record = records[0]
    assert record["artifact_class"] == "terrain_ridge"
    assert record["method"] == "linear_chord"
    assert record["before"]["max_above_chord_m"] > 100.0
    # Interior stations take the rounded chord; boundaries keep raw values.
    interior = record["after"]["replacement_elevations_m"]
    start_index = offsets.index(record["from_station_m"])
    end_index = offsets.index(record["to_station_m"])
    assert conditioned[start_index] == ridge[start_index]
    assert conditioned[end_index] == ridge[end_index]
    assert conditioned[start_index + 1 : end_index] == interior
    assert abs(record["after"]["chord_grade_percent"]) <= (
        continental.CONDITIONING_SUSTAINED_BOUND_PERCENT
    )
    dip = [10.0, 10.0, -40.0, -80.0, -40.0, 10.0, 10.5, 10.7, 10.9]
    dip_records, _ = continental._condition_segment_profile(
        "seg", offsets, dip, [], []
    )
    assert dip_records[0]["artifact_class"] == "bridge_deck_dip"
    # A window overlapping a locked chord span reads as fill-span terrain.
    span = [{"kind": "nhs_fill_chord", "site_id": "x",
             "from_station_m": 200.0, "to_station_m": 400.0}]
    span_records, _ = continental._condition_segment_profile(
        "seg", offsets, dip, span, []
    )
    assert span_records[0]["artifact_class"] == "fill_span_terrain"
    assert span_records[0]["evidence"]["chord_span_overlaps"] == span


def test_conditioning_tunnel_window_must_agree_with_the_authored_bore() -> None:
    offsets = [index * 100.0 for index in range(9)]
    ridge = [10.0, 10.0, 40.0, 80.0, 120.0, 80.0, 40.0, 10.0, 10.0]
    registry = [
        {
            "tunnel_id": "fake",
            "segment_id": "seg",
            "search_station_range_m": [0.0, 900.0],
            "portal_elevation_m": {"east": 500.0, "west": 500.0},
            "bore_length_m": 600.0,
            "provenance": "authored",
            "source_notes": "synthetic",
        }
    ]
    # Portals hundreds of metres off the window's boundary elevations refuse.
    with pytest.raises(ValueError, match="authored tunnel"):
        continental._condition_segment_profile(
            "seg", offsets, ridge, [], registry
        )
    registry[0]["portal_elevation_m"] = {"east": 10.0, "west": 10.0}
    records, _ = continental._condition_segment_profile(
        "seg", offsets, ridge, [], registry
    )
    assert records[0]["artifact_class"] == "tunnel_bore"
    evidence = records[0]["evidence"]["authored_tunnel"]
    assert evidence["tunnel_id"] == "fake"
    assert abs(evidence["entry_portal_delta_m"]) <= (
        continental.CONDITIONING_TUNNEL_PORTAL_TOLERANCE_M
    )


def _validate_conditioned(path: Path) -> dict:
    return continental.validate_continental_conditioned_profile(
        path,
        ELEVATION_LOCK_PATH,
        DEM_LOCK_PATH,
        DIRECTED_LOCK_PATH,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        NHS_FILL_LOCK_PATH,
        DISPOSITION_PATH,
        OVERLAY_LOCK_PATH,
        CONFLATION_LOCK_PATH,
        CATALOG_PATH,
    )


def test_repository_conditioned_profile_lock_validates() -> None:
    payload = _validate_conditioned(CONDITIONED_LOCK_PATH)
    assert payload["status"] == continental.CONDITIONED_PROFILE_STATUS
    summary = payload["summary"]
    assert summary["record_count"] == 154
    assert summary["corrected_station_count"] == 546
    assert {
        cls: entry["record_count"]
        for cls, entry in summary["corrections_by_class"].items()
    } == {
        "bridge_deck_dip": 115,
        "fill_span_terrain": 1,
        "interval_spike": 8,
        "terrain_ridge": 20,
        "tunnel_bore": 1,
        "water_surface": 9,
    }
    # The post-conditioning corridor reads like a real road: the steepest
    # sustained kilometre is under the interstate design bound, and the
    # highest point is the Eisenhower-Johnson bore crown, not the ridge
    # above it.
    assert abs(summary["max_sustained_grade"]["grade_percent"]) <= 7.0
    assert summary["max_sustained_grade"]["segment_id"] == "i70-denver-to-cove-fort"
    assert summary["highest_point"]["elevation_m"] == 3402.08
    assert summary["raw_highest_point"]["elevation_m"] == 3837.26
    assert summary["raw_max_sustained_grade"]["grade_percent"] == -43.979
    for segment in payload["segments"]:
        sustained = segment["statistics"]["max_sustained_grade"]
        assert abs(sustained["grade_percent"]) <= 7.0
    tunnel_records = [
        record
        for segment in payload["segments"]
        for record in segment["conditioning_records"]
        if record["artifact_class"] == "tunnel_bore"
    ]
    assert len(tunnel_records) == 1
    tunnel = tunnel_records[0]
    assert tunnel["from_station_m"] == 86300.0
    assert tunnel["to_station_m"] == 89000.0
    assert abs(
        tunnel["evidence"]["authored_tunnel"]["exit_portal_delta_m"]
    ) <= 60.0
    # The Delaware River fill chord's terrain window carries its span.
    fill_records = [
        record
        for segment in payload["segments"]
        for record in segment["conditioning_records"]
        if record["artifact_class"] == "fill_span_terrain"
    ]
    assert len(fill_records) == 1
    overlap = fill_records[0]["evidence"]["chord_span_overlaps"][0]
    assert overlap["kind"] == "nhs_fill_chord"


def _tampered_conditioned_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(CONDITIONED_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["segments_sha256"] = canonical_sha256(payload["segments"])
    payload["paths_sha256"] = canonical_sha256(payload["paths"])
    target = tmp_path / "conditioned-profile-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_conditioned_profile_lock_rejects_semantic_tampering(
    tmp_path: Path,
) -> None:
    def drifted_replacement(payload: dict) -> None:
        record = payload["segments"][0]["conditioning_records"][0]
        record["after"]["replacement_elevations_m"][0] += 1.0

    with pytest.raises(ValueError, match="records do not reproduce"):
        _validate_conditioned(
            _tampered_conditioned_lock(tmp_path, drifted_replacement)
        )

    def dropped_record(payload: dict) -> None:
        segment = payload["segments"][0]
        segment["conditioning_records"] = segment["conditioning_records"][1:]
        segment["record_count"] -= 1

    with pytest.raises(ValueError, match="records do not reproduce"):
        _validate_conditioned(_tampered_conditioned_lock(tmp_path, dropped_record))

    def widened_trigger(payload: dict) -> None:
        payload["model"]["interval_trigger_grade_percent"] = 50.0

    with pytest.raises(ValueError, match="model constants drifted"):
        _validate_conditioned(_tampered_conditioned_lock(tmp_path, widened_trigger))

    def silent_smooth_claim(payload: dict) -> None:
        payload["source_policy"]["silent_smoothing_applied"] = True

    with pytest.raises(ValueError, match="source policy drifted"):
        _validate_conditioned(
            _tampered_conditioned_lock(tmp_path, silent_smooth_claim)
        )

    def drifted_tunnel(payload: dict) -> None:
        payload["authored_tunnels"][0]["portal_elevation_m"]["west"] = 4000.0

    with pytest.raises(ValueError, match="authored tunnels drifted"):
        _validate_conditioned(_tampered_conditioned_lock(tmp_path, drifted_tunnel))

    def drifted_digest(payload: dict) -> None:
        payload["segments"][0]["conditioned_profile_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="profile digest drifted"):
        _validate_conditioned(_tampered_conditioned_lock(tmp_path, drifted_digest))

    def summary_drift(payload: dict) -> None:
        payload["summary"]["corrected_station_count"] += 1

    with pytest.raises(ValueError, match="summary does not reproduce"):
        _validate_conditioned(_tampered_conditioned_lock(tmp_path, summary_drift))


def test_resample_polyline_walks_stations_linearly() -> None:
    coordinates = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
    samples = continental._resample_polyline(coordinates, 25.0)
    assert samples[0] == (0.0, 0.0)
    assert samples[1] == (25.0, 0.0)
    assert samples[4] == (100.0, 0.0)
    assert samples[-1] == (100.0, 50.0)
    assert len(samples) == 7
    assert continental._vertex_turn_degrees(samples, 4) == pytest.approx(90.0)


def test_excise_reversal_apexes_removes_back_steps_with_records() -> None:
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    # A 60 m out-and-back inside an otherwise straight chain.
    chain = [
        (0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (140.0, 0.001),
        (200.0, 0.002), (300.0, 0.002), (400.0, 0.002),
    ]
    conditioned, records = continental._excise_reversal_apexes(
        "seg", list(chain), [], inverse
    )
    assert not records or all(
        record["reversal_class"] == "joint_back_step" for record in records
    )
    assert records
    for index in range(1, len(conditioned) - 1):
        assert continental._vertex_turn_degrees(conditioned, index) <= (
            continental.CARRIAGEWAY_REVERSAL_THRESHOLD_DEG
        )
    assert records[0]["chain_length_delta_m"] < 0
    # An overlay chord's out-and-back classifies against the overlay line.
    overlay = LineString([(200.0, 0.0), (140.0, 0.001)])
    _, overlay_records = continental._excise_reversal_apexes(
        "seg", list(chain), [overlay], inverse
    )
    assert overlay_records[0]["reversal_class"] == "overlay_out_and_back"
    # A comb of reversals beyond the cap refuses.
    comb: list[tuple[float, float]] = [(0.0, 0.0)]
    for tooth in range(12):
        comb.append((tooth * 10.0 + 10.0, 0.0))
        comb.append((tooth * 10.0 + 4.0, 0.001 * (tooth + 1)))
    with pytest.raises(ValueError, match="removal cap"):
        continental._excise_reversal_apexes("seg", comb, [], inverse)


def test_carriageway_corner_sites_classify_and_refuse_reversals() -> None:
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    # A right-angle corner far from any overlay or backtrack is a route
    # corner.
    corner_chain = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0)]
    sites = continental._carriageway_corner_sites(
        "seg", corner_chain, [], 0.0, 0.0, inverse
    )
    assert len(sites) == 1
    assert sites[0]["corner_class"] == "route_corner"
    assert sites[0]["peak_turn_deg"] > 20.0
    # The same corner inside an overlay lens adjudicates the overlay gate.
    overlay = LineString([(999.0, 0.0), (1001.0, 0.0)])
    overlay_sites = continental._carriageway_corner_sites(
        "seg", corner_chain, [overlay], 0.0, 0.0, inverse
    )
    assert overlay_sites[0]["corner_class"] == "overlay_corner"
    # Inside a junction-backtrack tail span it is a junction approach.
    tail_sites = continental._carriageway_corner_sites(
        "seg", corner_chain, [], 1200.0, 0.0, inverse
    )
    assert tail_sites[0]["corner_class"] == "junction_backtrack_approach"
    # A reversal-class turn surviving to the census refuses.
    reversal_chain = [(0.0, 0.0), (1000.0, 0.0), (0.0, 0.5)]
    with pytest.raises(ValueError, match="reversal-class turn survived"):
        continental._carriageway_corner_sites(
            "seg", reversal_chain, [], 0.0, 0.0, inverse
        )


def test_offset_carriageway_refuses_a_self_intersecting_offset() -> None:
    # The inner side of a hairpin narrower than the offset degenerates.
    hairpin = LineString(
        [(0.0, 0.0), (100.0, 0.0), (100.0, 4.0), (0.0, 4.0)]
    )
    with pytest.raises(ValueError, match="not a single line|degenerate"):
        continental._offset_carriageway("seg", hairpin, "eastbound")
    # A zigzag whose offset splits into pieces refuses on either side.
    zigzag = LineString(
        [(0.0, 0.0), (200.0, 0.0), (200.0, 30.0), (100.0, 30.0),
         (100.0, 15.0), (300.0, 15.0)]
    )
    with pytest.raises(ValueError, match="not a single line"):
        continental._offset_carriageway("seg", zigzag, "westbound")
    straight = LineString([(0.0, 0.0), (500.0, 0.0)])
    westbound = continental._offset_carriageway("seg", straight, "westbound")
    eastbound = continental._offset_carriageway("seg", straight, "eastbound")
    assert westbound[0][1] == -continental.CARRIAGEWAY_OFFSET_M
    assert eastbound[0][1] == continental.CARRIAGEWAY_OFFSET_M


def test_carriageway_backtrack_record_proves_reciprocity() -> None:
    shared = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (300.0, 0.0)]
    arriving = [(-100.0, 300.0), (-100.0, 0.0)] + shared
    departing = list(reversed(shared)) + [(-50.0, -200.0)]
    junction = {
        "anchor_id": "test-anchor",
        "from_segment_id": "a",
        "to_segment_id": "b",
        "backtrack_element_count": 2,
        "backtrack_length_m": 300.0,
    }
    record = continental._carriageway_backtrack_record(
        junction, arriving, departing
    )
    assert record["mirrored_length_m"] == 300.0
    assert record["reciprocity_gap_m"] <= 0.001
    assert record["westbound_separation_m"] >= 19.0
    # A drifted locked length refuses.
    drifted = dict(junction, backtrack_length_m=250.0)
    with pytest.raises(ValueError, match="mirrored backtrack length drifted"):
        continental._carriageway_backtrack_record(drifted, arriving, departing)
    # Chains that do not mirror refuse.
    with pytest.raises(ValueError, match="do not mirror"):
        continental._carriageway_backtrack_record(
            junction, arriving, [(5000.0, 5000.0), (6000.0, 6000.0)]
        )


def _validate_carriageway(path: Path) -> dict:
    return continental.validate_continental_westbound_carriageway(
        path,
        CONDITIONED_LOCK_PATH,
        ELEVATION_LOCK_PATH,
        DEM_LOCK_PATH,
        DIRECTED_LOCK_PATH,
        SELECTION_PATH,
        LOCK_PATH,
        TRANSFER_LOCK_PATH,
        TRANSFER_POLICY_PATH,
        EDGE_PATH_LOCK_PATH,
        NHS_FILL_LOCK_PATH,
        DISPOSITION_PATH,
        OVERLAY_LOCK_PATH,
        CONFLATION_LOCK_PATH,
        CATALOG_PATH,
    )


def test_repository_westbound_carriageway_lock_validates() -> None:
    payload = _validate_carriageway(CARRIAGEWAY_LOCK_PATH)
    assert payload["status"] == continental.WESTBOUND_CARRIAGEWAY_STATUS
    assert payload["westbound_selection"]["carriageway_direction_claimed"] is True
    summary = payload["summary"]
    assert summary["segment_count"] == 12
    assert summary["element_count"] == 12582
    assert summary["gates_failed"] == 0
    assert summary["min_reciprocal_separation_m"] >= 19.0
    assert summary["junction_backtrack_count"] == 2
    # The Quad Cities overlay corner is adjudicated against the overlay
    # lock's recorded 77.2 degree constraint.
    overlay_sites = [
        site
        for segment in payload["segments"]
        for site in segment["corner_sites"]
        if site["corner_class"] == "overlay_corner"
    ]
    assert len(overlay_sites) == 1
    assert abs(overlay_sites[0]["turn_sum_deg"] - 77.2) <= 5.0
    # The two junction backtracks resolve onto the reciprocal pair.
    anchors = {record["anchor_id"] for record in payload["junction_backtracks"]}
    assert anchors == {"ca-barstow-i40-i15", "ut-salt-lake-i80-i15"}
    for record in payload["junction_backtracks"]:
        assert record["reciprocity_gap_m"] <= 0.001
        assert record["westbound_separation_m"] >= 19.0
    # The grade gate adjudicates the conditioned profile.
    assert payload["grade_gate"]["passed"] is True
    assert payload["grade_gate"]["source"] == "conditioned-profile-lock"


def _tampered_carriageway_lock(tmp_path: Path, mutate) -> Path:
    payload = json.loads(CARRIAGEWAY_LOCK_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["segments_sha256"] = canonical_sha256(payload["segments"])
    target = tmp_path / "westbound-carriageway-lock.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_westbound_carriageway_lock_rejects_semantic_tampering(
    tmp_path: Path,
) -> None:
    def unclaimed_direction(payload: dict) -> None:
        payload["westbound_selection"]["carriageway_direction_claimed"] = False

    with pytest.raises(ValueError, match="must claim the carriageway direction"):
        _validate_carriageway(
            _tampered_carriageway_lock(tmp_path, unclaimed_direction)
        )

    def failed_gate(payload: dict) -> None:
        payload["segments"][0]["gates"]["reciprocal_separation"]["passed"] = False

    with pytest.raises(ValueError, match="did not pass"):
        _validate_carriageway(_tampered_carriageway_lock(tmp_path, failed_gate))

    def narrowed_separation(payload: dict) -> None:
        payload["segments"][0]["gates"]["reciprocal_separation"]["measured"] = 5.0

    with pytest.raises(ValueError, match="separation gate drifted"):
        _validate_carriageway(
            _tampered_carriageway_lock(tmp_path, narrowed_separation)
        )

    def unknown_corner_class(payload: dict) -> None:
        for segment in payload["segments"]:
            if segment["corner_sites"]:
                segment["corner_sites"][0]["corner_class"] = "smoothed_away"
                return

    with pytest.raises(ValueError, match="unknown corner class"):
        _validate_carriageway(
            _tampered_carriageway_lock(tmp_path, unknown_corner_class)
        )

    def reversal_grade_corner(payload: dict) -> None:
        for segment in payload["segments"]:
            if segment["corner_sites"]:
                site = segment["corner_sites"][0]
                site["peak_turn_deg"] = 170.0
                segment["gates"]["heading_discipline"]["measured"] = 170.0
                return

    with pytest.raises(ValueError, match="outside the corner class"):
        _validate_carriageway(
            _tampered_carriageway_lock(tmp_path, reversal_grade_corner)
        )

    def drifted_backtrack(payload: dict) -> None:
        payload["junction_backtracks"][0]["reciprocity_gap_m"] = 5.0

    with pytest.raises(ValueError, match="reciprocity gap exceeds"):
        _validate_carriageway(
            _tampered_carriageway_lock(tmp_path, drifted_backtrack)
        )

    def dropped_backtrack(payload: dict) -> None:
        payload["junction_backtracks"] = payload["junction_backtracks"][:1]

    with pytest.raises(ValueError, match="junction backtracks"):
        _validate_carriageway(
            _tampered_carriageway_lock(tmp_path, dropped_backtrack)
        )

    def widened_model(payload: dict) -> None:
        payload["model"]["offset_m"] = 3.0

    with pytest.raises(ValueError, match="model drifted"):
        _validate_carriageway(_tampered_carriageway_lock(tmp_path, widened_model))

    def summary_drift(payload: dict) -> None:
        payload["summary"]["westbound_miles"] += 1.0

    with pytest.raises(ValueError, match="summary does not reproduce"):
        _validate_carriageway(_tampered_carriageway_lock(tmp_path, summary_drift))
