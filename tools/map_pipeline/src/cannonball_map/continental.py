from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cannonball_map.acquisition import (
    ArcGisTransport,
    NhpnAcquisitionResult,
    UrllibArcGisTransport,
    acquire_nhpn,
)
from cannonball_map.catalog import load_catalog, require_catalog_source
from cannonball_map.lockfile import canonical_sha256
from cannonball_map.manifest import SHA256_PATTERN, compute_sha256

NHPN_SOURCE_ID = "usdot-national-highway-planning-network"
NHPN_QUERY_SUFFIX = "/query"
INTERSTATE_PATTERN = re.compile(r"I-(\d{1,3})")
STATE_FIPS = {
    "AL": "01",
    "AK": "02",
    "AZ": "04",
    "AR": "05",
    "CA": "06",
    "CO": "08",
    "CT": "09",
    "DE": "10",
    "DC": "11",
    "FL": "12",
    "GA": "13",
    "HI": "15",
    "ID": "16",
    "IL": "17",
    "IN": "18",
    "IA": "19",
    "KS": "20",
    "KY": "21",
    "LA": "22",
    "ME": "23",
    "MD": "24",
    "MA": "25",
    "MI": "26",
    "MN": "27",
    "MS": "28",
    "MO": "29",
    "MT": "30",
    "NE": "31",
    "NV": "32",
    "NH": "33",
    "NJ": "34",
    "NM": "35",
    "NY": "36",
    "NC": "37",
    "ND": "38",
    "OH": "39",
    "OK": "40",
    "OR": "41",
    "PA": "42",
    "RI": "44",
    "SC": "45",
    "SD": "46",
    "TN": "47",
    "TX": "48",
    "UT": "49",
    "VT": "50",
    "VA": "51",
    "WA": "53",
    "WV": "54",
    "WI": "55",
    "WY": "56",
}


@dataclass(frozen=True)
class NhpnCandidateSelector:
    segment_id: str
    facility: str
    route_number: str
    jurisdictions: tuple[str, ...]
    state_fips: tuple[str, ...]
    predicate: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_nhpn_candidate_selectors(selection: dict[str, Any]) -> tuple[NhpnCandidateSelector, ...]:
    selectors: list[NhpnCandidateSelector] = []
    for segment in selection.get("segments", []):
        if segment.get("geometry_status") != "nhpn_selection_pending":
            continue
        facilities = segment.get("facility_sequence", [])
        if len(facilities) != 1:
            raise ValueError(
                f"NHPN segment '{segment.get('id')}' must declare exactly one facility."
            )
        facility = facilities[0]
        match = INTERSTATE_PATTERN.fullmatch(facility)
        if match is None:
            raise ValueError(f"NHPN segment '{segment.get('id')}' is not an Interstate facility.")
        jurisdictions = tuple(segment.get("jurisdictions", []))
        try:
            state_fips = tuple(STATE_FIPS[state] for state in jurisdictions)
        except KeyError as error:
            raise ValueError(f"Unknown state jurisdiction '{error.args[0]}'.") from error
        route_number = match.group(1)
        quoted_fips = ",".join(f"'{value}'" for value in state_fips)
        sign_slots = " OR ".join(
            f"(SIGNT{slot}='I' AND SIGNN{slot}='{route_number}')"
            for slot in range(1, 4)
        )
        predicate = f"STFIPS IN ({quoted_fips}) AND ({sign_slots})"
        selectors.append(
            NhpnCandidateSelector(
                segment["id"],
                facility,
                route_number,
                jurisdictions,
                state_fips,
                predicate,
            )
        )
    if not selectors:
        raise ValueError("Route selection contains no NHPN-backed segments.")
    return tuple(selectors)


def acquire_continental_nhpn_candidates(
    selection_path: Path,
    catalog_path: Path,
    output_path: Path,
    cache_directory: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
) -> dict[str, Any]:
    selection = load_json(selection_path)
    catalog = load_catalog(catalog_path)
    source = catalog[NHPN_SOURCE_ID]
    service_url = source.raw["service_url"]
    query_url = service_url + NHPN_QUERY_SUFFIX
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_live_service_metadata(service_metadata)
    max_record_count = int(service_metadata["maxRecordCount"])
    if page_size > max_record_count:
        raise ValueError(
            f"NHPN page size {page_size} exceeds the live service limit "
            f"of {max_record_count}."
        )
    service_metadata_sha256 = canonical_sha256(service_metadata)
    snapshot_cache_directory = cache_directory / service_metadata_sha256
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    snapshots: list[dict[str, Any]] = []
    all_object_ids: set[int] = set()
    for selector in build_nhpn_candidate_selectors(selection):
        segment_cache = snapshot_cache_directory / selector.segment_id
        result = acquire_nhpn(
            transport,
            query_url,
            {"where": selector.predicate},
            segment_cache,
            page_size=page_size,
        )
        snapshots.append(
            _snapshot_record(selector, result, segment_cache, timestamp, page_size)
        )
        all_object_ids.update(result.object_ids)
    union = sorted(all_object_ids)
    payload = {
        "schema_version": 1,
        "status": "nhpn_candidates_locked_3dep_pending",
        "created_at": timestamp,
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection": {
            "path": selection_path.as_posix(),
            "sha256": compute_sha256(selection_path),
            "decision": selection.get("decision"),
        },
        "source_policy": {
            "openstreetmap_ancestry_allowed": False,
            "continental_downloads_committed": False,
            "candidate_snapshot_is_selected_route_geometry": False,
        },
        "nhpn": {
            "source_id": NHPN_SOURCE_ID,
            "publisher": source.publisher,
            "license_status": source.license_status,
            "license_evidence_url": source.license_evidence_url,
            "service_url": service_url,
            "query_url": query_url,
            "service": {
                "item_id": service_metadata["serviceItemId"],
                "layer_id": service_metadata["id"],
                "object_id_field": service_metadata["objectIdField"],
                "max_record_count": service_metadata["maxRecordCount"],
                "data_last_edit_epoch_ms": service_metadata["editingInfo"][
                    "dataLastEditDate"
                ],
                "canonical_metadata_sha256": service_metadata_sha256,
            },
            "selection_policy": (
                "Acquire signed Interstate route-family candidates in every declared "
                "jurisdiction and preserve all three NHPN sign slots. A later connected-path "
                "solve selects exact westbound edges between ADR-0024 transfer nodes."
            ),
            "segment_snapshots": snapshots,
            "candidate_union": {
                "expected_count": len(union),
                "object_ids_sha256": canonical_sha256(union),
            },
        },
        "elevation": {
            "source_id": "usgs-3dep",
            "required_resolution": "1/3 arc-second",
            "status": "pending_exact_nhpn_path_geometry",
            "reason": (
                "3DEP product discovery requires the exact connected NHPN edge set and "
                "authored connector bounds; candidate route-family supersets are too broad."
            ),
        },
        "next_stage": {
            "id": "exact-westbound-path-solve",
            "requires": [
                "transfer-node coordinate lock",
                "NHPN endpoint snapping and connectivity audit",
                "westbound directed-edge selection",
            ],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_continental_route_lock(
    lock_path: Path,
    catalog_path: Path,
    selection_path: Path,
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    payload = load_json(lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported continental route lock schema.")
    status = payload.get("status")
    if status != "nhpn_candidates_locked_3dep_pending":
        raise ValueError("Continental route lock has an unsupported status.")
    if require_complete:
        raise ValueError("Continental route lock is not complete.")
    if payload.get("catalog_sha256") != compute_sha256(catalog_path):
        raise ValueError("Source catalog hash drifted from the continental route lock.")
    route_selection = payload.get("route_selection", {})
    if route_selection.get("sha256") != compute_sha256(selection_path):
        raise ValueError("Route selection hash drifted from the continental route lock.")
    selection = load_json(selection_path)
    if route_selection.get("decision") != selection.get("decision"):
        raise ValueError("Continental route lock decision does not match route selection.")
    policy = payload.get("source_policy", {})
    if policy != {
        "candidate_snapshot_is_selected_route_geometry": False,
        "continental_downloads_committed": False,
        "openstreetmap_ancestry_allowed": False,
    }:
        raise ValueError("Continental route lock source policy is incomplete.")
    catalog = load_catalog(catalog_path)
    nhpn = payload.get("nhpn", {})
    source = require_catalog_source(
        catalog,
        source_id=nhpn.get("source_id", ""),
        publisher=nhpn.get("publisher", ""),
        license_status=nhpn.get("license_status", ""),
        source_url=nhpn.get("service_url", ""),
        license_evidence_url=nhpn.get("license_evidence_url", ""),
    )
    if nhpn.get("query_url") != source.raw["service_url"] + NHPN_QUERY_SUFFIX:
        raise ValueError("Continental route lock NHPN query URL drifted.")
    service = nhpn.get("service", {})
    if (
        service.get("item_id") != "4179a784a8d547ac869b14505c168430"
        or service.get("layer_id") != 0
        or service.get("object_id_field") != "OBJECTID"
    ):
        raise ValueError("Continental route lock has an unsupported object ID field.")
    max_record_count = int(service.get("max_record_count", 0))
    if max_record_count < 1 or not SHA256_PATTERN.fullmatch(
        service.get("canonical_metadata_sha256", "")
    ):
        raise ValueError("Continental route lock service metadata is incomplete.")
    expected_selectors = {
        selector.segment_id: selector for selector in build_nhpn_candidate_selectors(selection)
    }
    snapshots = nhpn.get("segment_snapshots", [])
    if len(snapshots) != len(expected_selectors) or {
        snapshot.get("segment_id") for snapshot in snapshots
    } != set(expected_selectors):
        raise ValueError("Continental route lock does not cover every NHPN segment exactly once.")
    union: set[int] = set()
    for snapshot in snapshots:
        selector = expected_selectors[snapshot["segment_id"]]
        _validate_snapshot(snapshot, selector, max_record_count)
        union.update(snapshot["object_ids"])
    candidate_union = nhpn.get("candidate_union", {})
    object_ids = sorted(union)
    if candidate_union.get("expected_count") != len(object_ids):
        raise ValueError("Continental route lock candidate union count does not reconcile.")
    if candidate_union.get("object_ids_sha256") != canonical_sha256(object_ids):
        raise ValueError("Continental route lock candidate union hash drifted.")
    elevation = payload.get("elevation", {})
    if elevation.get("source_id") != "usgs-3dep" or elevation.get("status") != (
        "pending_exact_nhpn_path_geometry"
    ):
        raise ValueError("Partial continental route lock must identify the pending 3DEP stage.")
    return payload


def _snapshot_record(
    selector: NhpnCandidateSelector,
    result: NhpnAcquisitionResult,
    checkpoint_directory: Path,
    acquired_at: str,
    page_size: int,
) -> dict[str, Any]:
    pages = []
    for page_index, start in enumerate(range(0, len(result.object_ids), page_size)):
        page_ids = list(result.object_ids[start : start + page_size])
        checkpoint = checkpoint_directory / f"page-{page_index:06d}.json"
        record = load_json(checkpoint)
        pages.append(
            {
                "index": page_index,
                "object_id_offset": start,
                "feature_count": len(page_ids),
                "object_ids_sha256": canonical_sha256(page_ids),
                "canonical_response_sha256": record["response_sha256"],
            }
        )
    object_ids = list(result.object_ids)
    return {
        "segment_id": selector.segment_id,
        "facility": selector.facility,
        "jurisdictions": list(selector.jurisdictions),
        "state_fips": list(selector.state_fips),
        "predicate": selector.predicate,
        "acquired_at": acquired_at,
        "page_size": page_size,
        "expected_count": result.expected_count,
        "object_ids": object_ids,
        "object_ids_sha256": canonical_sha256(object_ids),
        "features_sha256": canonical_sha256(result.features),
        "pages": pages,
        "retries": result.retries,
        "resumed_pages": result.resumed_pages,
    }


def _validate_snapshot(
    snapshot: dict[str, Any],
    selector: NhpnCandidateSelector,
    max_record_count: int,
) -> None:
    expected_identity = {
        "facility": selector.facility,
        "jurisdictions": list(selector.jurisdictions),
        "state_fips": list(selector.state_fips),
        "predicate": selector.predicate,
    }
    if any(snapshot.get(key) != value for key, value in expected_identity.items()):
        raise ValueError(f"NHPN selector drifted for segment '{selector.segment_id}'.")
    object_ids = snapshot.get("object_ids", [])
    if not object_ids or object_ids != sorted(set(object_ids)):
        raise ValueError(
            f"NHPN IDs are empty, duplicated, or unsorted for '{selector.segment_id}'."
        )
    if snapshot.get("expected_count") != len(object_ids):
        raise ValueError(f"NHPN count does not reconcile for '{selector.segment_id}'.")
    if snapshot.get("object_ids_sha256") != canonical_sha256(object_ids):
        raise ValueError(f"NHPN object ID hash drifted for '{selector.segment_id}'.")
    try:
        acquired_at = datetime.fromisoformat(snapshot.get("acquired_at", "").replace("Z", "+00:00"))
    except ValueError as error:
        message = f"NHPN acquisition time is invalid for '{selector.segment_id}'."
        raise ValueError(message) from error
    if acquired_at.tzinfo is None:
        raise ValueError(f"NHPN acquisition time has no timezone for '{selector.segment_id}'.")
    if not SHA256_PATTERN.fullmatch(snapshot.get("features_sha256", "")):
        raise ValueError(f"NHPN feature hash is invalid for '{selector.segment_id}'.")
    page_size = int(snapshot.get("page_size", 0))
    if page_size < 1 or page_size > max_record_count:
        raise ValueError(f"NHPN page size is invalid for '{selector.segment_id}'.")
    pages = snapshot.get("pages", [])
    if not pages:
        raise ValueError(f"NHPN pages are missing for '{selector.segment_id}'.")
    flattened: list[int] = []
    for index, page in enumerate(pages):
        offset = page.get("object_id_offset")
        count = page.get("feature_count")
        if not isinstance(offset, int) or not isinstance(count, int):
            raise ValueError(f"NHPN page metadata is invalid for '{selector.segment_id}'.")
        page_ids = object_ids[offset : offset + count]
        if page.get("index") != index or page.get("feature_count") != len(page_ids):
            raise ValueError(f"NHPN page metadata is invalid for '{selector.segment_id}'.")
        if not page_ids or len(page_ids) > page_size:
            raise ValueError(f"NHPN page size is invalid for '{selector.segment_id}'.")
        if page.get("object_ids_sha256") != canonical_sha256(page_ids):
            raise ValueError(f"NHPN page ID hash drifted for '{selector.segment_id}'.")
        if not SHA256_PATTERN.fullmatch(page.get("canonical_response_sha256", "")):
            raise ValueError(f"NHPN page response hash is invalid for '{selector.segment_id}'.")
        flattened.extend(page_ids)
    if flattened != object_ids:
        raise ValueError(f"NHPN pages do not reconcile for '{selector.segment_id}'.")


def _validate_live_service_metadata(metadata: dict[str, Any]) -> None:
    if metadata.get("id") != 0 or metadata.get("objectIdField") != "OBJECTID":
        raise ValueError("NHPN service identity or object ID field changed.")
    if metadata.get("serviceItemId") != "4179a784a8d547ac869b14505c168430":
        raise ValueError("NHPN service item changed.")
    try:
        max_record_count = int(metadata.get("maxRecordCount", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("NHPN service has no usable record limit.") from error
    if max_record_count < 1:
        raise ValueError("NHPN service has no usable record limit.")
    editing_info = metadata.get("editingInfo")
    if not isinstance(editing_info, dict) or not isinstance(
        editing_info.get("dataLastEditDate"), int
    ):
        raise ValueError("NHPN service no longer reports a data last edit date.")
    copyright_text = str(metadata.get("copyrightText", "")).lower()
    if "unrestricted public use" not in copyright_text:
        raise ValueError("NHPN service no longer declares unrestricted public use.")
