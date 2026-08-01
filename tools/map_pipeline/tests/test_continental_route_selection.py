from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SELECTION_PATH = REPO_ROOT / "data/routes/continental/route-selection.v1.json"


def _selection() -> dict:
    return json.loads(SELECTION_PATH.read_text(encoding="utf-8"))


def _ordered_jurisdictions(segments: list[dict], segment_ids: list[str]) -> list[str]:
    segment_by_id = {segment["id"]: segment for segment in segments}
    ordered: list[str] = []
    for segment_id in segment_ids:
        for jurisdiction in segment_by_id[segment_id]["jurisdictions"]:
            if (not ordered or ordered[-1] != jurisdiction) and jurisdiction not in ordered:
                ordered.append(jurisdiction)
    return ordered


def test_continental_selection_locks_one_canonical_and_two_major_alternatives() -> None:
    selection = _selection()

    assert selection["schema_version"] == 1
    assert selection["decision"] == "ADR-0024"
    assert selection["status"] == "selected_not_acquired"
    assert selection["direction"] == "westbound"
    assert selection["distance"]["meters"] is None

    roles = [path["role"] for path in selection["paths"]]
    assert roles.count("canonical") == 1
    assert roles.count("major_alternative") == 2
    assert {path["id"] for path in selection["paths"]} == {
        "central-rockies",
        "northern-plains",
        "southern-i40",
    }


def test_every_selected_path_is_contiguous_and_crosses_both_portals() -> None:
    selection = _selection()
    nodes = {node["id"] for node in selection["nodes"]}
    segments = selection["segments"]
    segment_by_id = {segment["id"]: segment for segment in segments}

    assert len(nodes) == len(selection["nodes"])
    assert len(segment_by_id) == len(segments)
    assert all(segment["from"] in nodes and segment["to"] in nodes for segment in segments)

    atlantic = selection["endpoints"]["atlantic"]["node_id"]
    pacific = selection["endpoints"]["pacific"]["node_id"]
    for path in selection["paths"]:
        assert len(path["segment_ids"]) == len(set(path["segment_ids"]))
        selected = [segment_by_id[segment_id] for segment_id in path["segment_ids"]]
        assert selected[0]["from"] == atlantic
        assert selected[-1]["to"] == pacific
        assert all(
            left["to"] == right["from"]
            for left, right in zip(selected, selected[1:], strict=False)
        )
        assert path["jurisdictions"] == _ordered_jurisdictions(segments, path["segment_ids"])


def test_selection_preserves_provenance_and_avoids_false_geometry_precision() -> None:
    selection = _selection()
    sources = selection["research_sources"]

    assert len({source["id"] for source in sources}) == len(sources)
    assert all(source["url"].startswith("https://") for source in sources)
    assert all(source["accessed_on"] == "2026-07-31" for source in sources)
    assert selection["source_policy"]["openstreetmap_ancestry_allowed"] is False
    assert selection["source_policy"]["continental_downloads_committed"] is False
    assert selection["source_policy"]["research_references_are_shipping_inputs"] is False
    assert all(
        segment["geometry_status"]
        in {
            "nhpn_selection_pending",
            "authored_connector_pending_source_lock_and_validation",
        }
        for segment in selection["segments"]
    )

    for endpoint in selection["endpoints"].values():
        coordinate = endpoint["coordinate"]
        assert coordinate["crs"] == "EPSG:4326"
        assert coordinate["precision"] == "census_address_match_not_lane_geometry"
        assert -125.0 <= coordinate["longitude"] <= -66.0
        assert 24.0 <= coordinate["latitude"] <= 50.0
