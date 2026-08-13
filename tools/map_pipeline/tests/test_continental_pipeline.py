from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import transform
from typer.testing import CliRunner

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
):
    """Build a locked line already expressed in the metric CRS the solver uses."""
    line = LineString(coordinates)
    candidate = LockedCandidateLine(
        "seg", object_id, "0" * 64, line, lrs, 0.0, 1.0, part_index
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


def test_connectivity_audit_counts_paired_carriageways() -> None:
    # Two records sharing one linear-reference extent are a divided-highway pair.
    metric_lines = (
        _metric_line(1, [(0.0, 0.0), (100.0, 0.0)], "L1"),
        _metric_line(2, [(0.0, 8.0), (100.0, 8.0)], "L1"),
        _metric_line(3, [(0.0, 40.0), (100.0, 40.0)], "L2"),
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 0.0), (100.0, 0.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["paired_carriageway_line_count"] == 2
    # The recorded fraction is rounded to four places.
    assert result["paired_carriageway_fraction"] == pytest.approx(2 / 3, abs=5e-5)


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


def test_lines_without_a_linear_reference_are_not_counted_as_paired() -> None:
    # Three lines with no LRSKEY share the empty identity; counting them together
    # would report them all as carriageway pairs.
    metric_lines = tuple(
        _metric_line(index, [(0.0, index * 40.0), (100.0, index * 40.0)], "")
        for index in range(1, 4)
    )
    result = _solve_segment_edge_path(
        {"id": "seg"}, metric_lines, (0.0, 40.0), (100.0, 40.0),
        ENDPOINT_SNAP_TOLERANCE_METERS,
    )
    assert result["paired_carriageway_line_count"] == 0
    assert result["paired_carriageway_fraction"] == 0.0
    assert result["linearly_unreferenced_line_count"] == 3


def test_audit_finding_is_derived_from_the_recorded_segments() -> None:
    payload = json.loads(EDGE_PATH_LOCK_PATH.read_text(encoding="utf-8"))
    fractions = [entry["paired_carriageway_fraction"] for entry in payload["segments"]]
    connected = sum(1 for entry in payload["segments"] if entry["connected"])
    finding = payload["audit_finding"]
    assert f"{round(min(fractions) * 100)} to {round(max(fractions) * 100)} percent" in finding
    assert f"{len(payload['segments']) - connected} of {len(payload['segments'])}" in finding


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
