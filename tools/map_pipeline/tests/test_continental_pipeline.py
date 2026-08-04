from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cannonball_map.continental import (
    acquire_continental_nhpn_candidates,
    build_nhpn_candidate_selectors,
    validate_continental_route_lock,
)
from cannonball_map.lockfile import canonical_sha256

SELECTION_PATH = Path("data/routes/continental/route-selection.v1.json")
CATALOG_PATH = Path("data/sources/catalog.json")
LOCK_PATH = Path("data/sources/continental-route-lock.json")


def _selection() -> dict:
    return json.loads(SELECTION_PATH.read_text(encoding="utf-8"))


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
    metadata = {
        "id": 0,
        "serviceItemId": "4179a784a8d547ac869b14505c168430",
        "objectIdField": "OBJECTID",
        "maxRecordCount": 2_000,
        "editingInfo": {"dataLastEditDate": 1},
        "copyrightText": "U.S. government work available for unrestricted public use.",
    }

    class Transport:
        def post(self, _url: str, form: dict[str, str]) -> dict:
            if form.get("returnCountOnly") == "true":
                return {"count": 1}
            if form.get("returnIdsOnly") == "true":
                return {"objectIdFieldName": "OBJECTID", "objectIds": [1]}
            return {"features": [{"attributes": {"OBJECTID": 1}}]}

    cache = tmp_path / "cache"
    output = tmp_path / "lock.json"
    payload = acquire_continental_nhpn_candidates(
        SELECTION_PATH,
        CATALOG_PATH,
        output,
        cache,
        transport=Transport(),
        service_metadata=metadata,
        acquired_at="2026-08-04T01:58:01Z",
    )
    metadata_hash = canonical_sha256(metadata)

    assert payload["nhpn"]["service"]["canonical_metadata_sha256"] == metadata_hash
    assert (cache / metadata_hash / "i80-new-jersey-to-big-springs" / "page-000000.json").is_file()
    assert not (cache / "i80-new-jersey-to-big-springs").exists()
    validate_continental_route_lock(output, CATALOG_PATH, SELECTION_PATH)


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
