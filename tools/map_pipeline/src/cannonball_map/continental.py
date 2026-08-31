from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import networkx as nx
from pyproj import Geod, Transformer
from shapely.geometry import LineString, MultiLineString, Point, box
from shapely.ops import linemerge, nearest_points, substring, transform

from cannonball_map.acquisition import (
    ArcGisTransport,
    NhpnAcquisitionResult,
    UrllibArcGisTransport,
    acquire_nhpn,
)
from cannonball_map.catalog import (
    CatalogSource,
    load_catalog,
    require_catalog_source,
    url_matches_prefix,
)
from cannonball_map.lockfile import canonical_sha256
from cannonball_map.manifest import SHA256_PATTERN, compute_sha256

NHPN_SOURCE_ID = "usdot-national-highway-planning-network"
NHPN_QUERY_SUFFIX = "/query"
TRANSFER_NEXT_STAGE = {
    "id": "exact-westbound-path-solve",
    "requires": [
        "snap route-family candidates to locked transfer anchors",
        "reject disconnected or ambiguous facility graphs",
        "select and checksum exact westbound NHPN object IDs",
    ],
}
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


@dataclass(frozen=True)
class LockedCandidateLine:
    segment_id: str
    object_id: int
    page_response_sha256: str
    geometry: LineString
    lrs_key: str = ""
    # BEGMP and ENDMP: the extent of the LRS section this record belongs to, shared
    # by every consecutive record in that section.
    section_begin_milepost: float = 0.0
    section_end_milepost: float = 0.0
    # BEGIN_POIN and END_POINT: this record's own extent along the section.
    record_begin_milepost: float = 0.0
    record_end_milepost: float = 0.0
    part_index: int = 0
    # MILES: the source's own per-record length assertion, and FACILITY_T: the
    # source's facility-type code. Carried for the directed-selection stage's
    # cross-checks and direction-evidence census; None when the source omits
    # them. Neither is ever a substitute for locked geometry.
    miles: float | None = None
    facility_type: int | None = None


def _reject_non_finite(literal: str) -> float:
    raise ValueError(
        f"Locked JSON contains the non-finite literal '{literal}'. NaN and Infinity "
        "are not JSON, and a non-finite value silently passes every range check "
        "because comparisons against it are false."
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_non_finite)


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


SUPPLEMENTARY_CACHE_DIRECTORY = "supplementary"


def acquire_continental_nhpn_supplements(
    disposition_path: Path,
    selection_path: Path,
    catalog_path: Path,
    lock_path: Path,
    cache_directory: Path,
    output_path: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
) -> dict[str, Any]:
    """Extend the candidate lock with the Q-034 scoped NHPN acquisitions.

    Implements the disposition record's ``nhpn_scoped_acquisition`` sites as a
    supplementary-acquisition extension: the locked segment snapshots are never
    re-acquired or rewritten, each scoped site's named OBJECTIDs are acquired
    with the exact paging/checkpoint/page-hash discipline of the base
    acquisition, and the candidate union is re-reconciled over base plus
    supplements. Refuses a live service whose metadata differs from the locked
    snapshot, so a supplement can never come from a different dataset edition
    than the history it extends, and refuses any OBJECTID the lock already
    carries.
    """
    payload = validate_continental_route_lock(lock_path, catalog_path, selection_path)
    disposition = load_json(disposition_path)
    if disposition.get("schema_version") != 1 or disposition.get("open_question") != "Q-034":
        raise ValueError("Supplementary acquisition requires the Q-034 disposition record.")
    scoped_sites = [
        site
        for site in disposition.get("sites", [])
        if site.get("disposition") == "nhpn_scoped_acquisition"
    ]
    if not scoped_sites:
        raise ValueError("The disposition record names no scoped NHPN acquisitions.")
    nhpn = payload["nhpn"]
    query_url = nhpn["query_url"]
    if service_metadata is None:
        with urllib.request.urlopen(nhpn["service_url"] + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_live_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    if service_metadata_sha256 != nhpn["service"]["canonical_metadata_sha256"]:
        raise ValueError(
            "Live NHPN service metadata has drifted from the candidate lock; a "
            "supplementary acquisition would extend the lock with records from a "
            "different dataset edition than its locked history."
        )
    base_ids = {
        object_id
        for snapshot in nhpn["segment_snapshots"]
        for object_id in snapshot["object_ids"]
    }
    segment_ids = {snapshot["segment_id"] for snapshot in nhpn["segment_snapshots"]}
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    cache_root = (
        cache_directory
        / nhpn["service"]["canonical_metadata_sha256"]
        / SUPPLEMENTARY_CACHE_DIRECTORY
    )
    supplements: list[dict[str, Any]] = []
    acquired_ids: set[int] = set()
    for site in sorted(scoped_sites, key=lambda entry: str(entry.get("site_id", ""))):
        site_id = str(site.get("site_id", ""))
        segment_id = site.get("segment_id")
        if segment_id not in segment_ids or not site_id.startswith(f"{segment_id}--"):
            raise ValueError(
                f"Scoped acquisition site '{site_id}' is not scoped to a locked segment."
            )
        object_ids = site.get("joining_object_ids")
        if (
            not isinstance(object_ids, list)
            or not object_ids
            or object_ids != sorted(set(object_ids))
        ):
            raise ValueError(f"Scoped acquisition site '{site_id}' names no OBJECTIDs.")
        already_locked = sorted(set(object_ids) & (base_ids | acquired_ids))
        if already_locked:
            raise ValueError(
                f"Scoped acquisition site '{site_id}' names already-locked "
                f"OBJECTIDs {already_locked}."
            )
        predicate = "OBJECTID IN (" + ",".join(str(value) for value in object_ids) + ")"
        result = acquire_nhpn(
            transport,
            query_url,
            {"where": predicate},
            cache_root / site_id,
            page_size=page_size,
        )
        if list(result.object_ids) != object_ids:
            raise ValueError(
                f"Scoped acquisition site '{site_id}' did not return exactly the "
                f"named OBJECTIDs: expected {object_ids}, got {list(result.object_ids)}."
            )
        acquired_ids.update(object_ids)
        supplements.append(
            {
                "site_id": site_id,
                "segment_id": segment_id,
                "open_question": "Q-034",
                "disposition": "nhpn_scoped_acquisition",
                "predicate": predicate,
                "acquired_at": timestamp,
                "page_size": page_size,
                "expected_count": result.expected_count,
                "object_ids": object_ids,
                "object_ids_sha256": canonical_sha256(object_ids),
                "features_sha256": canonical_sha256(result.features),
                "pages": _page_records(result, cache_root / site_id, page_size),
                "retries": result.retries,
                "resumed_pages": result.resumed_pages,
            }
        )
    union = sorted(base_ids | acquired_ids)
    payload["revised_at"] = timestamp
    payload["nhpn"]["supplementary_acquisitions"] = supplements
    payload["nhpn"]["candidate_union"] = {
        "expected_count": len(union),
        "object_ids_sha256": canonical_sha256(union),
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
    supplements = nhpn.get("supplementary_acquisitions", [])
    if not isinstance(supplements, list) or any(
        not isinstance(supplement, dict) for supplement in supplements
    ):
        raise ValueError("Continental route lock supplementary acquisitions are invalid.")
    supplement_site_ids: set[str] = set()
    supplement_ids: set[int] = set()
    for supplement in supplements:
        site_id = str(supplement.get("site_id", ""))
        segment_id = supplement.get("segment_id")
        if not site_id or segment_id not in expected_selectors or not site_id.startswith(
            f"{segment_id}--"
        ):
            raise ValueError(
                f"Continental route lock supplement '{site_id}' is not scoped to a "
                "locked segment."
            )
        if site_id in supplement_site_ids:
            raise ValueError(f"Continental route lock repeats supplement '{site_id}'.")
        supplement_site_ids.add(site_id)
        if (
            supplement.get("open_question") != "Q-034"
            or supplement.get("disposition") != "nhpn_scoped_acquisition"
        ):
            raise ValueError(
                f"Continental route lock supplement '{site_id}' records no "
                "disposition ancestry."
            )
        _validate_acquisition_record(supplement, f"supplement '{site_id}'", max_record_count)
        object_ids = supplement["object_ids"]
        expected_predicate = (
            "OBJECTID IN (" + ",".join(str(value) for value in object_ids) + ")"
        )
        if supplement.get("predicate") != expected_predicate:
            raise ValueError(
                f"Continental route lock supplement '{site_id}' predicate drifted."
            )
        already_locked = sorted(set(object_ids) & (union | supplement_ids))
        if already_locked:
            raise ValueError(
                f"Continental route lock supplement '{site_id}' repeats locked "
                f"OBJECTIDs {already_locked}."
            )
        supplement_ids.update(object_ids)
    union.update(supplement_ids)
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


def derive_continental_transfer_lock(
    policy_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    output_path: Path,
    *,
    derived_at: str | None = None,
) -> dict[str, Any]:
    """Derive reproducible transfer anchors from checksum-locked NHPN responses."""
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path,
        catalog_path,
        selection_path,
    )
    policy = load_json(policy_path)
    specs = _validate_transfer_policy(policy, selection)
    cache_root = (
        cache_directory / route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    )
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    line_cache: dict[str, tuple[LockedCandidateLine, ...]] = {}
    metric_line_cache: dict[
        str, tuple[tuple[LockedCandidateLine, LineString], ...]
    ] = {}

    def lines_for(segment_id: str) -> tuple[LockedCandidateLine, ...]:
        if segment_id not in line_cache:
            line_cache[segment_id] = _segment_locked_lines(
                route_lock, segment_id, cache_root
            )
        return line_cache[segment_id]

    def metric_lines_for(
        segment_id: str,
    ) -> tuple[tuple[LockedCandidateLine, LineString], ...]:
        if segment_id not in metric_line_cache:
            metric_line_cache[segment_id] = tuple(
                (candidate, transform(forward.transform, candidate.geometry))
                for candidate in lines_for(segment_id)
            )
        return metric_line_cache[segment_id]

    nodes = [
        _derive_transfer_node(spec, metric_lines_for, forward, inverse) for spec in specs
    ]
    timestamp = derived_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    payload = {
        "schema_version": 1,
        "status": "transfer_nodes_locked_exact_path_pending",
        "decision": selection["decision"],
        "derived_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_policy_sha256": compute_sha256(policy_path),
        "source_policy": {
            "candidate_source": NHPN_SOURCE_ID,
            "nhpn_role": "coarse_topology_only",
            "openstreetmap_ancestry_allowed": False,
            "lane_geometry_claimed": False,
            "continental_downloads_committed": False,
        },
        "transfer_nodes": nodes,
        "transfer_nodes_sha256": canonical_sha256(nodes),
        "next_stage": TRANSFER_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_continental_transfer_lock(
    transfer_lock_path: Path,
    policy_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate a transfer lock without requiring the ignored NHPN response cache."""
    payload = load_json(transfer_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported continental transfer lock schema.")
    if payload.get("status") != "transfer_nodes_locked_exact_path_pending":
        raise ValueError("Continental transfer lock has an unsupported status.")
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path,
        catalog_path,
        selection_path,
    )
    policy = load_json(policy_path)
    specs = _validate_transfer_policy(policy, selection)
    expected_hashes = {
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_policy_sha256": compute_sha256(policy_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Continental transfer lock input hash drifted.")
    if payload.get("decision") != selection.get("decision"):
        raise ValueError("Continental transfer lock decision drifted.")
    raw_derived_at = payload.get("derived_at")
    if not isinstance(raw_derived_at, str):
        raise ValueError("Continental transfer derivation time is invalid.")
    try:
        derived_at = datetime.fromisoformat(raw_derived_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Continental transfer derivation time is invalid.") from error
    if derived_at.tzinfo is None:
        raise ValueError("Continental transfer derivation time has no timezone.")
    if payload.get("coordinate_crs") != "EPSG:4326" or payload.get(
        "metric_crs"
    ) != "EPSG:5070":
        raise ValueError("Continental transfer lock CRS contract drifted.")
    expected_policy = {
        "candidate_source": NHPN_SOURCE_ID,
        "nhpn_role": "coarse_topology_only",
        "openstreetmap_ancestry_allowed": False,
        "lane_geometry_claimed": False,
        "continental_downloads_committed": False,
    }
    if payload.get("source_policy") != expected_policy:
        raise ValueError("Continental transfer lock source policy is incomplete.")
    nodes = payload.get("transfer_nodes", [])
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        raise ValueError("Continental transfer lock nodes are invalid.")
    if len(nodes) != len(specs) or [node.get("id") for node in nodes] != [
        spec["id"] for spec in specs
    ]:
        raise ValueError("Continental transfer lock node order or coverage drifted.")
    snapshot_evidence: dict[str, dict[int, str]] = {}
    for snapshot in (
        *route_lock["nhpn"]["segment_snapshots"],
        *route_lock["nhpn"].get("supplementary_acquisitions", []),
    ):
        evidence_by_id = snapshot_evidence.setdefault(snapshot["segment_id"], {})
        for page in snapshot["pages"]:
            offset = page["object_id_offset"]
            for object_id in snapshot["object_ids"][
                offset : offset + page["feature_count"]
            ]:
                evidence_by_id[object_id] = page["canonical_response_sha256"]
    for node, spec in zip(nodes, specs, strict=True):
        _validate_transfer_node(node, spec, snapshot_evidence)
    if payload.get("next_stage") != TRANSFER_NEXT_STAGE:
        raise ValueError("Continental transfer lock next stage drifted.")
    if payload.get("transfer_nodes_sha256") != canonical_sha256(nodes):
        raise ValueError("Continental transfer node hash drifted.")
    return payload


def _validate_transfer_policy(
    policy: dict[str, Any], selection: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    if policy.get("schema_version") != 1 or policy.get("decision") != selection.get(
        "decision"
    ):
        raise ValueError("Continental transfer policy schema or decision drifted.")
    if policy.get("coordinate_crs") != "EPSG:4326":
        raise ValueError("Continental transfer policy must use EPSG:4326 search hints.")
    specs = policy.get("nodes", [])
    expected_nodes = [
        node["id"] for node in selection.get("nodes", []) if node.get("kind") != "endpoint"
    ]
    if [spec.get("id") for spec in specs] != expected_nodes:
        raise ValueError("Continental transfer policy node order or coverage drifted.")
    segment_by_id = {segment["id"]: segment for segment in selection.get("segments", [])}
    known_sources = {source["id"] for source in selection.get("research_sources", [])}
    for spec in specs:
        method = spec.get("method")
        segment_ids = spec.get("evidence_segment_ids", [])
        expected_count = 1 if method == "snap_to_segment" else 2
        if method not in {"snap_to_segment", "midpoint_between_segments"} or len(
            segment_ids
        ) != expected_count:
            raise ValueError(f"Transfer policy method is invalid for '{spec.get('id')}'.")
        if len(set(segment_ids)) != len(segment_ids):
            raise ValueError(f"Transfer policy repeats evidence for '{spec['id']}'.")
        for segment_id in segment_ids:
            segment = segment_by_id.get(segment_id)
            if segment is None or spec["id"] not in {segment.get("from"), segment.get("to")}:
                raise ValueError(
                    f"Transfer policy segment '{segment_id}' is not incident to '{spec['id']}'."
                )
            if segment.get("geometry_status") != "nhpn_selection_pending":
                raise ValueError(
                    f"Transfer policy segment '{segment_id}' is not NHPN-backed."
                )
        hint = spec.get("search_hint", {})
        longitude = hint.get("longitude")
        latitude = hint.get("latitude")
        if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
            raise ValueError(f"Transfer policy search hint is invalid for '{spec['id']}'.")
        if not (-125 <= longitude <= -66 and 24 <= latitude <= 50):
            raise ValueError(f"Transfer policy search hint is outside CONUS for '{spec['id']}'.")
        search_radius = spec.get("search_radius_m")
        if not isinstance(search_radius, int) or isinstance(search_radius, bool):
            raise ValueError(f"Transfer policy search radius is invalid for '{spec['id']}'.")
        if search_radius < 100:
            raise ValueError(f"Transfer policy search radius is invalid for '{spec['id']}'.")
        max_separation = spec.get("max_facility_separation_m")
        if not isinstance(max_separation, int) or isinstance(max_separation, bool):
            raise ValueError(
                f"Transfer policy facility separation is invalid for '{spec['id']}'."
            )
        if max_separation < 1:
            raise ValueError(
                f"Transfer policy facility separation is invalid for '{spec['id']}'."
            )
        sources = spec.get("research_source_ids", [])
        if (
            not sources
            or any(not isinstance(source, str) for source in sources)
            or not set(sources).issubset(known_sources)
        ):
            raise ValueError(f"Transfer policy sources are missing for '{spec['id']}'.")
    return tuple(specs)


def _load_locked_candidate_lines(
    snapshot: dict[str, Any], checkpoint_directory: Path
) -> tuple[LockedCandidateLine, ...]:
    object_ids = snapshot["object_ids"]
    lines: list[LockedCandidateLine] = []
    seen: set[int] = set()
    for page in snapshot["pages"]:
        checkpoint = checkpoint_directory / f"page-{page['index']:06d}.json"
        if not checkpoint.is_file():
            raise ValueError(f"Locked NHPN checkpoint is missing: {checkpoint}")
        record = load_json(checkpoint)
        response = record.get("response")
        response_hash = canonical_sha256(response)
        if (
            not isinstance(response, dict)
            or record.get("response_sha256") != response_hash
            or page.get("canonical_response_sha256") != response_hash
        ):
            raise ValueError(f"Locked NHPN checkpoint hash drifted: {checkpoint}")
        offset = page["object_id_offset"]
        expected_ids = object_ids[offset : offset + page["feature_count"]]
        features = response.get("features", [])
        returned_ids = [int(feature["attributes"]["OBJECTID"]) for feature in features]
        if returned_ids != expected_ids:
            raise ValueError(f"Locked NHPN checkpoint IDs drifted: {checkpoint}")
        for feature in features:
            object_id = int(feature["attributes"]["OBJECTID"])
            if object_id in seen:
                raise ValueError(f"Locked NHPN checkpoint repeats OBJECTID {object_id}.")
            seen.add(object_id)
            paths = feature.get("geometry", {}).get("paths", [])
            if not paths:
                raise ValueError(f"NHPN OBJECTID {object_id} has no geometry.")
            for part_index, coordinates in enumerate(paths):
                if len(coordinates) < 2:
                    raise ValueError(f"NHPN OBJECTID {object_id} has a degenerate path.")
                attributes = feature["attributes"]
                miles = attributes.get("MILES")
                facility_type = attributes.get("FACILITY_T")
                lines.append(
                    LockedCandidateLine(
                        snapshot["segment_id"],
                        object_id,
                        response_hash,
                        LineString(coordinates),
                        str(attributes.get("LRSKEY", "")),
                        float(attributes.get("BEGMP") or 0.0),
                        float(attributes.get("ENDMP") or 0.0),
                        float(attributes.get("BEGIN_POIN") or 0.0),
                        float(attributes.get("END_POINT") or 0.0),
                        part_index,
                        float(miles) if isinstance(miles, int | float) else None,
                        int(facility_type)
                        if isinstance(facility_type, int | float)
                        and not isinstance(facility_type, bool)
                        else None,
                    )
                )
    if seen != set(object_ids):
        raise ValueError(f"Locked NHPN cache does not reconcile for '{snapshot['segment_id']}'.")
    return tuple(lines)


def _segment_locked_lines(
    route_lock: dict[str, Any], segment_id: str, cache_root: Path
) -> tuple[LockedCandidateLine, ...]:
    """Load one segment's complete locked candidate lines from the response cache.

    The revised lock's candidate set for a segment is its base snapshot plus
    every Q-034 supplementary acquisition scoped to it. Every derivation and
    probe consumes candidates through this helper so none of them can disagree
    about what the lock contains.
    """
    nhpn = route_lock["nhpn"]
    snapshot = next(
        entry for entry in nhpn["segment_snapshots"] if entry["segment_id"] == segment_id
    )
    lines = list(_load_locked_candidate_lines(snapshot, cache_root / segment_id))
    for supplement in nhpn.get("supplementary_acquisitions", []):
        if supplement["segment_id"] != segment_id:
            continue
        lines.extend(
            _load_locked_candidate_lines(
                supplement,
                cache_root / SUPPLEMENTARY_CACHE_DIRECTORY / supplement["site_id"],
            )
        )
    return tuple(lines)


def _locked_object_id_union(route_lock: dict[str, Any]) -> frozenset[int]:
    """Every OBJECTID the revised lock carries: base snapshots plus supplements."""
    nhpn = route_lock["nhpn"]
    return frozenset(
        object_id
        for record in (*nhpn["segment_snapshots"], *nhpn.get("supplementary_acquisitions", []))
        for object_id in record["object_ids"]
    )


def _derive_transfer_node(
    spec: dict[str, Any],
    metric_lines_for: Callable[
        [str], tuple[tuple[LockedCandidateLine, LineString], ...]
    ],
    forward: Transformer,
    inverse: Transformer,
) -> dict[str, Any]:
    hint = Point(spec["search_hint"]["longitude"], spec["search_hint"]["latitude"])
    metric_hint = transform(forward.transform, hint)
    segment_lines: list[list[tuple[LockedCandidateLine, LineString]]] = []
    for segment_id in spec["evidence_segment_ids"]:
        nearby = [
            (candidate, metric_geometry)
            for candidate, metric_geometry in metric_lines_for(segment_id)
            if metric_geometry.distance(metric_hint) <= spec["search_radius_m"]
        ]
        if not nearby:
            raise ValueError(
                f"No NHPN candidates are within the search radius for '{spec['id']}'."
            )
        segment_lines.append(nearby)

    if spec["method"] == "snap_to_segment":
        candidate, geometry = min(
            segment_lines[0],
            key=lambda item: (item[1].distance(metric_hint), item[0].object_id),
        )
        metric_coordinate = nearest_points(metric_hint, geometry)[1]
        separation_m = 0.0
        evidence = [candidate]
    else:
        choices = []
        for left, left_geometry in segment_lines[0]:
            for right, right_geometry in segment_lines[1]:
                left_point, right_point = nearest_points(left_geometry, right_geometry)
                separation = left_point.distance(right_point)
                if separation > spec["max_facility_separation_m"]:
                    continue
                midpoint = LineString([left_point, right_point]).interpolate(0.5, normalized=True)
                choices.append(
                    (
                        midpoint.distance(metric_hint),
                        separation,
                        left.object_id,
                        right.object_id,
                        midpoint,
                        left,
                        right,
                    )
                )
        if not choices:
            raise ValueError(
                f"No NHPN facility pair meets the separation gate for '{spec['id']}'."
            )
        choice = min(choices, key=lambda item: item[:4])
        _, separation_m, _, _, metric_coordinate, left, right = choice
        evidence = [left, right]

    longitude, latitude = inverse.transform(metric_coordinate.x, metric_coordinate.y)
    hint_distance_m = metric_coordinate.distance(metric_hint)
    if hint_distance_m > spec["search_radius_m"]:
        raise ValueError(f"Derived transfer escaped its search radius for '{spec['id']}'.")
    return {
        "id": spec["id"],
        "method": spec["method"],
        "coordinate": {
            "longitude": round(longitude, 12),
            "latitude": round(latitude, 12),
        },
        "hint_distance_m": round(hint_distance_m, 3),
        "facility_separation_m": round(separation_m, 3),
        "evidence": [
            {
                "segment_id": candidate.segment_id,
                "object_id": candidate.object_id,
                "page_response_sha256": candidate.page_response_sha256,
            }
            for candidate in evidence
        ],
        "research_source_ids": spec["research_source_ids"],
    }


def _validate_transfer_node(
    node: dict[str, Any],
    spec: dict[str, Any],
    snapshot_evidence: dict[str, dict[int, str]],
) -> None:
    if node.get("method") != spec["method"]:
        raise ValueError(f"Transfer derivation method drifted for '{spec['id']}'.")
    coordinate = node.get("coordinate", {})
    longitude = coordinate.get("longitude")
    latitude = coordinate.get("latitude")
    if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
        raise ValueError(f"Transfer coordinate is invalid for '{spec['id']}'.")
    if not (-125 <= longitude <= -66 and 24 <= latitude <= 50):
        raise ValueError(f"Transfer coordinate is outside CONUS for '{spec['id']}'.")
    hint_distance = node.get("hint_distance_m")
    separation = node.get("facility_separation_m")
    if not isinstance(hint_distance, (int, float)) or not 0 <= hint_distance <= spec[
        "search_radius_m"
    ]:
        raise ValueError(f"Transfer hint distance is invalid for '{spec['id']}'.")
    if not isinstance(separation, (int, float)) or not 0 <= separation <= spec[
        "max_facility_separation_m"
    ]:
        raise ValueError(f"Transfer facility separation is invalid for '{spec['id']}'.")
    evidence = node.get("evidence", [])
    if [item.get("segment_id") for item in evidence] != spec["evidence_segment_ids"]:
        raise ValueError(f"Transfer evidence coverage drifted for '{spec['id']}'.")
    for item in evidence:
        expected_hash = snapshot_evidence[item["segment_id"]].get(item.get("object_id"))
        if expected_hash is None:
            raise ValueError(f"Transfer OBJECTID drifted for '{spec['id']}'.")
        if item.get("page_response_sha256") != expected_hash:
            raise ValueError(f"Transfer response hash drifted for '{spec['id']}'.")
    if node.get("research_source_ids") != spec["research_source_ids"]:
        raise ValueError(f"Transfer research sources drifted for '{spec['id']}'.")


def _page_records(
    result: NhpnAcquisitionResult, checkpoint_directory: Path, page_size: int
) -> list[dict[str, Any]]:
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
    return pages


def _snapshot_record(
    selector: NhpnCandidateSelector,
    result: NhpnAcquisitionResult,
    checkpoint_directory: Path,
    acquired_at: str,
    page_size: int,
) -> dict[str, Any]:
    pages = _page_records(result, checkpoint_directory, page_size)
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


def _validate_acquisition_record(
    record: dict[str, Any],
    label: str,
    max_record_count: int,
) -> None:
    """Validate the shared acquisition discipline of one paged snapshot record.

    Used by the base segment snapshots, the Q-034 supplementary acquisitions,
    and the NHS fill acquisitions, so no acquisition can land in a lock with a
    weaker paging, hashing, or timestamp contract than the original NHPN one.
    """
    object_ids = record.get("object_ids", [])
    if not object_ids or object_ids != sorted(set(object_ids)):
        raise ValueError(f"Acquired IDs are empty, duplicated, or unsorted for {label}.")
    if any(not isinstance(value, int) or isinstance(value, bool) for value in object_ids):
        raise ValueError(f"Acquired IDs are not integers for {label}.")
    if record.get("expected_count") != len(object_ids):
        raise ValueError(f"Acquired count does not reconcile for {label}.")
    if record.get("object_ids_sha256") != canonical_sha256(object_ids):
        raise ValueError(f"Acquired object ID hash drifted for {label}.")
    try:
        acquired_at = datetime.fromisoformat(record.get("acquired_at", "").replace("Z", "+00:00"))
    except ValueError as error:
        message = f"Acquisition time is invalid for {label}."
        raise ValueError(message) from error
    if acquired_at.tzinfo is None:
        raise ValueError(f"Acquisition time has no timezone for {label}.")
    if not SHA256_PATTERN.fullmatch(record.get("features_sha256", "")):
        raise ValueError(f"Acquired feature hash is invalid for {label}.")
    page_size = int(record.get("page_size", 0))
    if page_size < 1 or page_size > max_record_count:
        raise ValueError(f"Acquired page size is invalid for {label}.")
    pages = record.get("pages", [])
    if not pages:
        raise ValueError(f"Acquired pages are missing for {label}.")
    flattened: list[int] = []
    for index, page in enumerate(pages):
        offset = page.get("object_id_offset")
        count = page.get("feature_count")
        if not isinstance(offset, int) or not isinstance(count, int):
            raise ValueError(f"Acquired page metadata is invalid for {label}.")
        page_ids = object_ids[offset : offset + count]
        if page.get("index") != index or page.get("feature_count") != len(page_ids):
            raise ValueError(f"Acquired page metadata is invalid for {label}.")
        if not page_ids or len(page_ids) > page_size:
            raise ValueError(f"Acquired page size is invalid for {label}.")
        if page.get("object_ids_sha256") != canonical_sha256(page_ids):
            raise ValueError(f"Acquired page ID hash drifted for {label}.")
        if not SHA256_PATTERN.fullmatch(page.get("canonical_response_sha256", "")):
            raise ValueError(f"Acquired page response hash is invalid for {label}.")
        flattened.extend(page_ids)
    if flattened != object_ids:
        raise ValueError(f"Acquired pages do not reconcile for {label}.")


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
    _validate_acquisition_record(
        snapshot, f"segment '{selector.segment_id}'", max_record_count
    )


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


EDGE_PATH_NEXT_STAGE = {
    "id": "authored-connector-and-elevation-lock",
    "requires": [
        "authored connector geometry for the three non-NHPN segments",
        "3DEP product, resolution, and datum lock over the solved corridor",
        "deterministic reconstruction gates over the solved edge path",
    ],
}

# Endpoint snapping tolerance for the connectivity audit, in metres of the
# EPSG:5070 metric CRS.
#
# NHPN is a coarse national topology whose neighbouring records are authored to
# share an endpoint, so a connected pair is expected to coincide to within
# floating-point noise rather than to be merely nearby. The tolerance exists to
# absorb that noise, not to bridge a real gap: anything wider would silently
# invent connectivity the source does not assert, which ADR-0018 forbids. The
# solved artifact records the largest snap distance actually used so the margin
# is auditable rather than assumed.
ENDPOINT_SNAP_TOLERANCE_METERS = 1.0

# The widest snapping tolerance any lock may declare. Without a ceiling the
# validator would only ever compare a lock against its own declared value, so a
# lock derived with a metre-wide-plus tolerance would validate itself and the
# ADR-0018 prohibition on inventing connectivity would be unenforceable.
MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS = 1.0

# How far a locked transfer anchor may sit from the nearest candidate endpoint
# before the segment is treated as unanchored.
#
# Grounded in the transfer lock's own recorded numbers: its anchors were derived
# with hint distances of roughly 2.6 to 4.0 m against sub-metre NHPN endpoints.
# 25 m is generous against that authoring precision while still excluding the
# anchors that sit hundreds of metres away because they were derived against a
# different carriageway.
ANCHOR_SNAP_LIMIT_METERS = 25.0


@dataclass(frozen=True)
class SolvedEdge:
    object_id: int
    part_index: int
    page_response_sha256: str
    length_meters: float
    reversed_for_travel: bool
    # Set when the edge is one sub-edge of a record split at an on-edge transfer
    # anchor: the traversed metre range along the record part's geometry.
    part_range_m: tuple[float, float] | None = None


def _snap_key(x: float, y: float, tolerance: float) -> tuple[int, int]:
    return (int(round(x / tolerance)), int(round(y / tolerance)))


def _neighbour_keys(key: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    x, y = key
    return tuple(
        (x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
    )


def _resolve_endpoint_node(
    coordinate: tuple[float, float],
    nodes: dict[tuple[int, int], tuple[float, float]],
    tolerance: float,
) -> tuple[int, int]:
    """Return the snapped node key for an endpoint, creating one when needed.

    Neighbouring cells are searched before a new node is created so that two
    endpoints astride a grid boundary still resolve to the same node.
    """
    key = _snap_key(coordinate[0], coordinate[1], tolerance)
    best_key: tuple[int, int] | None = None
    best_distance = float("inf")
    for candidate_key in _neighbour_keys(key):
        existing = nodes.get(candidate_key)
        if existing is None:
            continue
        distance = math.dist(coordinate, existing)
        if distance <= tolerance and distance < best_distance:
            best_key, best_distance = candidate_key, distance
    if best_key is not None:
        return best_key
    nodes[key] = coordinate
    return key


def _build_snapped_endpoint_graph(
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    tolerance: float,
) -> tuple[
    nx.MultiGraph,
    dict[tuple[int, int], tuple[float, float]],
    dict[tuple[int, int], list[tuple[LockedCandidateLine, LineString, str]]],
    float,
]:
    """Snap every record endpoint onto shared nodes and build the segment graph.

    Returns the graph, the node coordinates, each node's incident record ends as
    (candidate, metric line, "start" or "end"), and the largest snap distance
    actually used. Shared by the connectivity solve and the break probes so they
    can never disagree about where a segment's graph separates.
    """
    graph = nx.MultiGraph()
    nodes: dict[tuple[int, int], tuple[float, float]] = {}
    incident: dict[tuple[int, int], list[tuple[LockedCandidateLine, LineString, str]]] = {}
    max_snap_distance = 0.0

    # Insert in object-id order so the graph, and therefore any tie between
    # equal-length routes, is identical on every run.
    ordered = sorted(
        metric_lines, key=lambda pair: (pair[0].object_id, pair[0].part_index)
    )
    for candidate, line in ordered:
        coordinates = list(line.coords)
        start, end = coordinates[0], coordinates[-1]
        start_key = _resolve_endpoint_node(start, nodes, tolerance)
        end_key = _resolve_endpoint_node(end, nodes, tolerance)
        max_snap_distance = max(
            max_snap_distance,
            math.dist(start, nodes[start_key]),
            math.dist(end, nodes[end_key]),
        )
        if start_key == end_key:
            # A closed loop cannot advance the path and would add a zero-progress
            # option to the solver.
            continue
        graph.add_edge(
            start_key,
            end_key,
            key=(candidate.object_id, candidate.part_index),
            weight=line.length,
            object_id=candidate.object_id,
            part_index=candidate.part_index,
            page_response_sha256=candidate.page_response_sha256,
            start_key=start_key,
        )
        incident.setdefault(start_key, []).append((candidate, line, "start"))
        incident.setdefault(end_key, []).append((candidate, line, "end"))
    return graph, nodes, incident, max_snap_distance


def _split_edge_at_anchor(
    graph: nx.MultiGraph,
    nodes: dict[tuple[int, int], tuple[float, float]],
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    anchor_point: tuple[float, float],
    tolerance: float,
    anchor_limit: float = ANCHOR_SNAP_LIMIT_METERS,
) -> dict[str, Any] | None:
    """Split one locked record's edge at a transfer anchor that lies on its interior.

    The Q-034c/d resolution (2026-08-31): both remaining anchor mismatches are
    locked ADR-0024 anchors sitting mid-record on the corridor's own locked
    pavement, with no record endpoint inside the anchor snap limit, so neither
    endpoint snapping nor any acquisition can put them on the graph. The graph
    models nodes as record endpoints only; the shipping route model is edge ID
    plus distance-along-edge, so an on-edge anchor is exactly representable by
    splitting the edge at the anchor's projection. This is a fallback used only
    when no endpoint node lies within the anchor snap limit: the solve for every
    endpoint-anchored segment is untouched by construction, the transfer lock
    stays byte-identical, and both tolerances keep their locked values (the
    perpendicular anchor-to-record offset must itself sit inside the unchanged
    anchor snap limit).

    Mutates the graph and node table, replacing the split record's edge with its
    two sub-edges joined at a new node on the anchor's projection, and returns
    the machine-readable split record; returns None when no locked record passes
    within the anchor snap limit or the projection would duplicate an endpoint.
    """
    anchor = Point(anchor_point)
    best: tuple[float, LockedCandidateLine, LineString] | None = None
    for candidate, line in sorted(
        metric_lines, key=lambda pair: (pair[0].object_id, pair[0].part_index)
    ):
        offset = line.distance(anchor)
        if offset > anchor_limit:
            continue
        if best is None or offset < best[0]:
            best = (offset, candidate, line)
    if best is None:
        return None
    offset, candidate, line = best
    distance_along = float(line.project(anchor))
    if distance_along <= tolerance or distance_along >= line.length - tolerance:
        # The anchor projects onto (or within snapping noise of) a record
        # endpoint; the endpoint search already judged that case and found it
        # beyond the anchor limit, so a split would only duplicate a node.
        return None
    edge_key = (candidate.object_id, candidate.part_index)
    located = next(
        (
            (first, second)
            for first, second, key in graph.edges(keys=True)
            if key == edge_key
        ),
        None,
    )
    if located is None:
        # A closed loop never entered the graph, so there is no edge to split.
        return None
    data = graph.get_edge_data(*located, key=edge_key)
    start_key = data["start_key"]
    end_key = located[1] if located[0] == start_key else located[0]
    split_point = line.interpolate(distance_along)
    split_coordinate = (float(split_point.x), float(split_point.y))
    existed_before = set(nodes)
    split_key = _resolve_endpoint_node(split_coordinate, nodes, tolerance)
    if split_key in existed_before:
        # An existing node sits within snapping tolerance of the projection;
        # reuse it rather than authoring a near-duplicate graph node.
        return {
            "side": None,
            "object_id": candidate.object_id,
            "part_index": candidate.part_index,
            "page_response_sha256": candidate.page_response_sha256,
            "anchor_offset_m": round(offset, 3),
            "split_distance_along_part_m": round(distance_along, 3),
            "part_length_m": round(float(line.length), 3),
            "reused_existing_node": True,
            "node_key": split_key,
        }
    graph.remove_edge(*located, key=edge_key)
    graph.add_edge(
        start_key,
        split_key,
        key=(candidate.object_id, candidate.part_index, 0),
        weight=distance_along,
        object_id=candidate.object_id,
        part_index=candidate.part_index,
        page_response_sha256=candidate.page_response_sha256,
        start_key=start_key,
        part_range_m=(0.0, distance_along),
    )
    graph.add_edge(
        split_key,
        end_key,
        key=(candidate.object_id, candidate.part_index, 1),
        weight=float(line.length) - distance_along,
        object_id=candidate.object_id,
        part_index=candidate.part_index,
        page_response_sha256=candidate.page_response_sha256,
        start_key=split_key,
        part_range_m=(distance_along, float(line.length)),
    )
    return {
        "side": None,
        "object_id": candidate.object_id,
        "part_index": candidate.part_index,
        "page_response_sha256": candidate.page_response_sha256,
        "anchor_offset_m": round(offset, 3),
        "split_distance_along_part_m": round(distance_along, 3),
        "part_length_m": round(float(line.length), 3),
        "reused_existing_node": False,
        "node_key": split_key,
    }


def _resolve_anchor_node(
    graph: nx.MultiGraph,
    nodes: dict[tuple[int, int], tuple[float, float]],
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    anchor_point: tuple[float, float],
    side: str,
    tolerance: float,
    anchor_limit: float = ANCHOR_SNAP_LIMIT_METERS,
) -> tuple[tuple[int, int] | None, float, dict[str, Any] | None]:
    """Resolve one transfer anchor onto the snapped graph.

    Endpoint-node acquisition takes precedence; the edge split is strictly a
    fallback for an anchor beyond the snap limit of every endpoint node.
    Returns the node key (None when unresolvable), the anchor's distance to
    that node, and the split record when the fallback authored one.
    """
    best_key: tuple[int, int] | None = None
    best_distance = float("inf")
    for key in sorted(nodes):
        distance = math.dist(anchor_point, nodes[key])
        if distance < best_distance:
            best_key, best_distance = key, distance
    if best_key is not None and best_distance <= anchor_limit:
        return best_key, best_distance, None
    split = _split_edge_at_anchor(
        graph, nodes, metric_lines, anchor_point, tolerance, anchor_limit
    )
    if split is None:
        return best_key, best_distance, None
    split["side"] = side
    node_key = split.pop("node_key")
    distance = math.dist(anchor_point, nodes[node_key])
    split["anchor_to_node_distance_m"] = round(distance, 3)
    return node_key, distance, split


def _solve_segment_edge_path(
    segment: dict[str, Any],
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    from_point: tuple[float, float],
    to_point: tuple[float, float],
    tolerance: float,
    anchor_limit: float = ANCHOR_SNAP_LIMIT_METERS,
) -> dict[str, Any]:
    """Snap endpoints, audit connectivity, and solve one segment's edge path.

    Every quantity the caller might use to judge the result is returned, including
    the failure diagnostics, because a segment that cannot be solved is a finding
    rather than an error to swallow.
    """
    graph, nodes, incident, max_snap_distance = _build_snapped_endpoint_graph(
        metric_lines, tolerance
    )
    end_line = {
        key: [candidate for candidate, _, _ in entries]
        for key, entries in incident.items()
    }

    # What shape is this candidate set? An endpoint joining exactly two records is
    # chain interior; one joining a single record is a chain end. A near-linear
    # corridor is dominated by degree 2, and its components separate at chain ends,
    # so the distances between those ends are what explain a connectivity failure.
    endpoint_degree = {key: len(entries) for key, entries in incident.items()}
    degree_counts: dict[str, int] = {}
    for degree in endpoint_degree.values():
        bucket = str(degree) if degree < 3 else "3+"
        degree_counts[bucket] = degree_counts.get(bucket, 0) + 1
    degree_histogram = dict(sorted(degree_counts.items()))
    end_nodes = sorted(key for key, degree in endpoint_degree.items() if degree == 1)
    # Count distinct record pairs, not endpoint pairs. A record with both ends
    # dangling would otherwise be counted once per endpoint combination.
    contiguous_record_pairs: set[tuple[int, int]] = set()
    for first_index, first in enumerate(end_nodes):
        for second in end_nodes[first_index + 1 :]:
            for left in end_line[first]:
                for right in end_line[second]:
                    if left.object_id == right.object_id:
                        continue
                    if left.lrs_key != right.lrs_key or not left.lrs_key:
                        continue
                    if (
                        abs(left.record_end_milepost - right.record_begin_milepost)
                        < 1e-6
                        or abs(right.record_end_milepost - left.record_begin_milepost)
                        < 1e-6
                    ):
                        contiguous_record_pairs.add(
                            tuple(sorted((left.object_id, right.object_id)))
                        )
    contiguous_pairs = len(contiguous_record_pairs)
    separations = []
    for index, key in enumerate(end_nodes):
        others = [
            math.dist(nodes[key], nodes[other])
            for position, other in enumerate(end_nodes)
            if position != index
        ]
        if others:
            separations.append(round(min(others), 3))

    diagnostics: dict[str, Any] = {
        "segment_id": segment["id"],
        "candidate_line_count": len(metric_lines),
        "endpoint_degree_histogram": degree_histogram,
        "chain_end_count": len(end_nodes),
        "chain_interior_fraction": (
            round(degree_histogram.get("2", 0) / len(endpoint_degree), 4)
            if endpoint_degree
            else 0.0
        ),
        "chain_end_separations_m": sorted(separations),
        "milepost_contiguous_chain_end_pairs": contiguous_pairs,
        "graph_node_count": graph.number_of_nodes(),
        "graph_edge_count": graph.number_of_edges(),
        "connected_component_count": (
            nx.number_connected_components(graph) if graph.number_of_nodes() else 0
        ),
        "maximum_endpoint_snap_distance_m": round(max_snap_distance, 6),
        "endpoint_snap_tolerance_m": tolerance,
    }

    if not graph.number_of_nodes():
        diagnostics.update(
            connected=False,
            direction_validated=False,
            failure="segment produced no graph nodes",
        )
        return diagnostics

    splits: list[dict[str, Any]] = []
    from_key, from_distance, from_split = _resolve_anchor_node(
        graph, nodes, metric_lines, from_point, "from", tolerance, anchor_limit
    )
    if from_split is not None:
        splits.append(from_split)
    to_key, to_distance, to_split = _resolve_anchor_node(
        graph, nodes, metric_lines, to_point, "to", tolerance, anchor_limit
    )
    if to_split is not None:
        splits.append(to_split)
    diagnostics["from_transfer_node_snap_distance_m"] = round(from_distance, 3)
    diagnostics["to_transfer_node_snap_distance_m"] = round(to_distance, 3)
    diagnostics["anchor_snap_limit_m"] = anchor_limit
    if splits:
        # The split sub-edges replaced their records' edges, so the counts the
        # solve actually ran against are the post-split ones.
        diagnostics["anchor_edge_splits"] = splits
        diagnostics["graph_node_count"] = graph.number_of_nodes()
        diagnostics["graph_edge_count"] = graph.number_of_edges()

    # A path between the nearest graph nodes is only a path between the locked
    # anchors if those anchors are actually on this graph. An anchor hundreds of
    # metres away belongs to a different carriageway set, and reporting the walk
    # as connectivity between transfer nodes would overstate what was found.
    if max(from_distance, to_distance) > anchor_limit:
        diagnostics.update(
            connected=False,
            direction_validated=False,
            failure="a locked transfer anchor is farther than the anchor snap limit",
        )
        return diagnostics

    if from_key == to_key:
        diagnostics.update(
            connected=False,
            direction_validated=False,
            failure="both transfer nodes snapped to the same graph node",
        )
        return diagnostics
    if not nx.has_path(graph, from_key, to_key):
        component_of_from = len(nx.node_connected_component(graph, from_key))
        component_of_to = len(nx.node_connected_component(graph, to_key))
        diagnostics.update(
            connected=False,
            direction_validated=False,
            failure="no connected path between the locked transfer nodes",
            from_component_node_count=component_of_from,
            to_component_node_count=component_of_to,
        )
        return diagnostics

    node_path = nx.shortest_path(graph, from_key, to_key, weight="weight")
    edges: list[SolvedEdge] = []
    for previous, current in zip(node_path, node_path[1:], strict=False):
        parallel = graph.get_edge_data(previous, current)
        # Deterministic among parallel edges: shortest first, then object id.
        chosen_key = min(
            parallel,
            key=lambda edge_key: (parallel[edge_key]["weight"], edge_key),
        )
        data = parallel[chosen_key]
        part_range = data.get("part_range_m")
        edges.append(
            SolvedEdge(
                object_id=int(data["object_id"]),
                part_index=int(data["part_index"]),
                page_response_sha256=str(data["page_response_sha256"]),
                length_meters=float(data["weight"]),
                reversed_for_travel=data["start_key"] != previous,
                part_range_m=(
                    None
                    if part_range is None
                    else (float(part_range[0]), float(part_range[1]))
                ),
            )
        )

    total_meters = sum(edge.length_meters for edge in edges)
    diagnostics.update(
        connected=True,
        direction_validated=False,
        edge_count=len(edges),
        length_meters=round(total_meters, 3),
        length_miles=round(total_meters / 1609.344, 3),
        reversed_edge_count=sum(1 for edge in edges if edge.reversed_for_travel),
        object_ids=[edge.object_id for edge in edges],
        edges=[
            {
                "object_id": edge.object_id,
                "part_index": edge.part_index,
                "page_response_sha256": edge.page_response_sha256,
                "length_meters": round(edge.length_meters, 3),
                "reversed_for_travel": edge.reversed_for_travel,
                **(
                    {}
                    if edge.part_range_m is None
                    else {
                        "part_range_m": [
                            round(edge.part_range_m[0], 3),
                            round(edge.part_range_m[1], 3),
                        ]
                    }
                ),
            }
            for edge in edges
        ],
    )
    return diagnostics


def _audit_finding(results: list[dict[str, Any]]) -> str:
    """Describe the audit using the numbers the audit actually produced.

    The prose is generated rather than written so it cannot drift from the
    segments beside it if the locked inputs or the metrics change.
    """
    if not results:
        return "No NHPN-backed segments were audited."
    interior = [entry["chain_interior_fraction"] for entry in results]
    connected = sum(1 for entry in results if entry.get("connected"))
    contiguous = sum(entry["milepost_contiguous_chain_end_pairs"] for entry in results)
    chain_ends = sum(entry["chain_end_count"] for entry in results)
    return (
        "Each locked segment is a near-linear chain rather than a network: "
        f"{round(min(interior) * 100)} to {round(max(interior) * 100)} percent of "
        "endpoints join exactly two records. It is nonetheless broken: there are "
        f"{chain_ends} chain ends across the twelve segments, and "
        f"{len(results) - connected} of {len(results)} segments have no undirected "
        "path between their locked transfer nodes. Only "
        f"{contiguous} chain-end pairs are adjacent in linear referencing, meaning "
        "almost none of the breaks are two records that merely missed each other; the "
        "candidate set does not contain the records that would join them. Spatial "
        "proximity between chain ends is not evidence of adjacency, because unrelated "
        "parts of a route pass close together. Where a path was found it is a shortest "
        "undirected traversal and is not a westbound selection, which this stage does "
        "not assert."
    )


# NHPN publishes record mileposts to three decimals, so 0.001 mi - 1.61 m - is the
# finest distance the source can express. Two records that abut exactly can still
# be recorded a quantum apart, and exact-equality adjacency will always reject
# them.
MILEPOST_QUANTUM_MILES = 0.001
METRES_PER_MILE = 1609.344


def audit_continental_milepost_gaps(
    selection_path: Path,
    route_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
) -> dict[str, Any]:
    """Characterise the milepost gaps inside the locked candidate set.

    The 2026-08-14 contiguity finding tested one record's END_POINT against
    another's BEGIN_POIN on the same LRSKEY and reported that 3 of 67 chain ends
    were contiguous, concluding the candidate set lacked joining records. That
    test is exact, and this audit asks what the gaps it rejects actually measure.

    Gaps are computed as a union of intervals rather than by differencing sorted
    neighbours, because the candidate set contains exact duplicates and
    overlapping records; differencing neighbours reports those as breaks.

    Scope, stated because it is easy to overread: this characterises adjacency
    *within* an LRS key. Mileposts are key-local, so it says nothing about
    continuity where a route crosses from one key to another, which is a
    geometric question. It performs no bridging and changes no lock.
    """
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    snapshot_by_id = {
        snapshot["segment_id"]: snapshot
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }
    cache_root = cache_directory / route_lock["nhpn"]["service"]["canonical_metadata_sha256"]

    segments: list[dict[str, Any]] = []
    all_gaps: list[dict[str, Any]] = []
    for segment in selection["segments"]:
        if segment["id"] not in snapshot_by_id:
            continue
        lines = _segment_locked_lines(route_lock, segment["id"], cache_root)
        by_key: dict[str, list[LockedCandidateLine]] = {}
        for line in lines:
            by_key.setdefault(line.lrs_key, []).append(line)
        contiguous_keys = 0
        for key, group in sorted(by_key.items()):
            spans = _merge_milepost_spans(group)
            if len(spans) == 1:
                contiguous_keys += 1
            for first, second in zip(spans, spans[1:], strict=False):
                gap = second[0] - first[1]
                all_gaps.append(
                    {
                        "segment_id": segment["id"],
                        "lrs_key": key,
                        "from_milepost": first[1],
                        "to_milepost": second[0],
                        "gap_miles": gap,
                        "gap_meters": gap * METRES_PER_MILE,
                        "within_source_quantum": gap <= MILEPOST_QUANTUM_MILES * 1.1,
                    }
                )
        segments.append(
            {
                "segment_id": segment["id"],
                "record_count": len(lines),
                "lrs_key_count": len(by_key),
                "contiguous_key_count": contiguous_keys,
            }
        )

    quantum = [gap for gap in all_gaps if gap["within_source_quantum"]]
    substantial = [gap for gap in all_gaps if gap["gap_miles"] > 1.0]
    return {
        "schema_version": 1,
        "status": "characterisation only; no bridging performed and no lock changed",
        "scope": (
            "adjacency within an LRS key; mileposts are key-local, so this says "
            "nothing about continuity where a route crosses between keys"
        ),
        "source_milepost_quantum_miles": MILEPOST_QUANTUM_MILES,
        "source_milepost_quantum_meters": MILEPOST_QUANTUM_MILES * METRES_PER_MILE,
        "segments": segments,
        "gap_count": len(all_gaps),
        "gaps_within_source_quantum": len(quantum),
        "gaps_over_one_mile": len(substantial),
        "gaps": sorted(all_gaps, key=lambda gap: -gap["gap_miles"]),
    }


def _merge_milepost_spans(
    lines: Sequence[LockedCandidateLine],
) -> list[tuple[float, float]]:
    """Union of record milepost extents, direction-insensitive."""
    ordered = sorted(
        (
            min(line.record_begin_milepost, line.record_end_milepost),
            max(line.record_begin_milepost, line.record_end_milepost),
        )
        for line in lines
    )
    merged: list[list[float]] = []
    for begin, end in ordered:
        if merged and begin <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([begin, end])
    return [(begin, end) for begin, end in merged]


# LRSKEY is a 15-character alphanumeric identifier (underscore included). The
# probe interpolates it into an ArcGIS where clause and a cache directory name,
# so anything outside this alphabet is rejected rather than escaped.
LRS_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")

# A record whose extent merely abuts a gap boundary can be recorded one milepost
# quantum inside it, and internal cracks of the same size are the same
# phenomenon as the 32 quantum-sized gaps the milepost audit counted. The same
# 1.1 factor the audit applies to gap classification is applied to uncovered
# spans here.
GAP_COVERAGE_TOLERANCE_MILES = MILEPOST_QUANTUM_MILES * 1.1

# Spatial break probes inspect a bounded envelope around the two graph points
# whose components would need to meet. The padding is for nearby interchange or
# concurrency features; it is not a snapping tolerance and never changes graph
# connectivity. Any connection still has to satisfy the separately locked 1 m
# endpoint tolerance, with each probe endpoint anchored within the existing 25 m
# limit.
GEOMETRIC_PROBE_PADDING_METERS = 250.0


@dataclass(frozen=True)
class ProbedGapRecord:
    """One NHPN record returned by a whole-key probe, reduced to what the
    exclusion analysis needs."""

    object_id: int
    state_fips: str
    sign_identities: tuple[tuple[str, str], ...]
    low_milepost: float
    high_milepost: float


def _probe_sign_identities(attributes: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The record's signed-route identities across all three NHPN sign slots.

    NHPN pads empty slots with spaces rather than nulls, so values are stripped
    and a slot counts only when both its type and number survive stripping.
    """
    identities: list[tuple[str, str]] = []
    for slot in range(1, 4):
        sign_type = str(attributes.get(f"SIGNT{slot}") or "").strip()
        sign_number = str(attributes.get(f"SIGNN{slot}") or "").strip()
        if sign_type and sign_number:
            identities.append((sign_type, sign_number))
    return tuple(identities)


def _uncovered_spans(
    from_milepost: float,
    to_milepost: float,
    extents: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """The parts of [from, to] no extent covers, as a sorted list of spans."""
    merged: list[list[float]] = []
    for low, high in sorted(extents):
        clipped_low = max(low, from_milepost)
        clipped_high = min(high, to_milepost)
        if clipped_low >= clipped_high:
            continue
        if merged and clipped_low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], clipped_high)
        else:
            merged.append([clipped_low, clipped_high])
    uncovered: list[tuple[float, float]] = []
    cursor = from_milepost
    for low, high in merged:
        if low > cursor:
            uncovered.append((cursor, low))
        cursor = high
    if cursor < to_milepost:
        uncovered.append((cursor, to_milepost))
    return uncovered


def _classify_gap(
    gap: dict[str, Any],
    key_records: Sequence[ProbedGapRecord],
    selector: NhpnCandidateSelector,
    locked_object_ids: frozenset[int],
) -> dict[str, Any]:
    """What fills one locked gap, and why the acquisition predicate missed it.

    Overlap is strict: a record that only touches a gap boundary does not fill
    its interior. Every overlapping record is either already in the candidate
    lock, excluded by the sign filter, excluded by the state filter, excluded by
    both, or an anomaly that matches the predicate yet was not acquired.
    """
    from_milepost = gap["from_milepost"]
    to_milepost = gap["to_milepost"]
    overlapping = [
        record
        for record in key_records
        if record.low_milepost < to_milepost and record.high_milepost > from_milepost
    ]
    required_sign = ("I", selector.route_number)
    declared_fips = set(selector.state_fips)
    in_lock = 0
    excluded_by_sign = 0
    excluded_by_state = 0
    excluded_by_both = 0
    anomalies: list[int] = []
    signed_routes: set[str] = set()
    states: set[str] = set()
    for record in overlapping:
        states.add(record.state_fips)
        signed_routes.update(
            f"{sign_type}-{sign_number}"
            for sign_type, sign_number in record.sign_identities
        )
        if record.object_id in locked_object_ids:
            in_lock += 1
            continue
        sign_matches = required_sign in record.sign_identities
        state_matches = record.state_fips in declared_fips
        if sign_matches and state_matches:
            anomalies.append(record.object_id)
        elif sign_matches:
            excluded_by_state += 1
        elif state_matches:
            excluded_by_sign += 1
        else:
            excluded_by_both += 1
    uncovered = _uncovered_spans(
        from_milepost,
        to_milepost,
        [(record.low_milepost, record.high_milepost) for record in overlapping],
    )
    uncovered_miles = sum(high - low for low, high in uncovered)
    largest_uncovered = max((high - low for low, high in uncovered), default=0.0)
    if not overlapping:
        classification = "no_records"
    elif largest_uncovered <= GAP_COVERAGE_TOLERANCE_MILES:
        classification = "fully_covered"
    else:
        classification = "partially_covered"
    return {
        "segment_id": gap["segment_id"],
        "lrs_key": gap["lrs_key"],
        "from_milepost": from_milepost,
        "to_milepost": to_milepost,
        "gap_miles": gap["gap_miles"],
        "overlapping_record_count": len(overlapping),
        "records_in_candidate_lock": in_lock,
        "records_matching_predicate_unacquired": sorted(anomalies),
        "records_excluded_by_sign_filter": excluded_by_sign,
        "records_excluded_by_state_filter": excluded_by_state,
        "records_excluded_by_both_filters": excluded_by_both,
        "signed_routes_found": sorted(signed_routes),
        "state_fips_found": sorted(states),
        "covered_miles": gap["gap_miles"] - uncovered_miles,
        "uncovered_miles": uncovered_miles,
        "largest_uncovered_miles": largest_uncovered,
        "classification": classification,
    }


def _gap_probe_finding(gaps: list[dict[str, Any]]) -> str:
    """Describe the probe using the numbers it actually produced.

    Generated rather than written so it cannot drift from the gap results
    beside it.
    """
    if not gaps:
        return "No locked gaps exceeded the probe threshold."
    fully = sum(1 for gap in gaps if gap["classification"] == "fully_covered")
    partial = sum(1 for gap in gaps if gap["classification"] == "partially_covered")
    empty = sum(1 for gap in gaps if gap["classification"] == "no_records")
    anomalies = sum(len(gap["records_matching_predicate_unacquired"]) for gap in gaps)
    sign_only = sum(gap["records_excluded_by_sign_filter"] for gap in gaps)
    state_only = sum(gap["records_excluded_by_state_filter"] for gap in gaps)
    both = sum(gap["records_excluded_by_both_filters"] for gap in gaps)
    return (
        f"Of {len(gaps)} locked milepost gaps over the probe threshold, "
        f"{fully} are fully covered by NHPN records on the same LRS key, "
        f"{partial} are partially covered, and {empty} contain no NHPN "
        f"records on their LRS key at all. Among the unacquired overlapping "
        f"records, {sign_only} carry a different signed route within the declared "
        f"states, {state_only} carry the declared route outside the declared "
        f"states, and {both} match neither. {anomalies} records match the "
        "original predicate while absent from the lock. A gap with no records is "
        "not thereby a hole in the road: mileposts are key-local, and the same "
        "corridor may be carried by another LRS key. This is a characterisation "
        "of the acquisition predicate, not a route selection, and no lock is "
        "changed."
    )


def probe_continental_milepost_gaps(
    selection_path: Path,
    route_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    probe_cache_directory: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
    minimum_gap_miles: float = 1.0,
) -> dict[str, Any]:
    """Probe what NHPN carries inside the locked candidate set's large gaps.

    The 2026-08-16 milepost-gap characterisation left its 45 over-a-mile gaps
    unexplained and named the test that would explain them: query NHPN for the
    gap's milepost range without the sign filter. This performs that diagnostic
    acquisition. Each gap's whole LRS key is fetched unfiltered, with the same
    paging, checkpoint, and hash discipline as the candidate acquisition, and
    every record overlapping a gap is classified by which predicate clause
    excluded it.

    This is a characterisation, not a route selection: it changes no lock,
    claims no westbound direction and no authoritative distance, and its
    responses stay in the ignored cache. It refuses to run when the live
    service has drifted from the locked snapshot, because the probe would then
    characterise a different dataset than the one the gaps were measured in.
    """
    audit = audit_continental_milepost_gaps(
        selection_path, route_lock_path, catalog_path, cache_directory
    )
    route_lock = validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    selection = load_json(selection_path)
    selectors = {
        selector.segment_id: selector
        for selector in build_nhpn_candidate_selectors(selection)
    }
    locked_object_ids = _locked_object_id_union(route_lock)
    source = load_catalog(catalog_path)[NHPN_SOURCE_ID]
    service_url = source.raw["service_url"]
    query_url = service_url + NHPN_QUERY_SUFFIX
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_live_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    locked_metadata_sha256 = route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    if service_metadata_sha256 != locked_metadata_sha256:
        raise ValueError(
            "Live NHPN service metadata has drifted from the candidate lock; a probe "
            "against it would characterise a different dataset than the one the "
            "locked gaps were measured in."
        )
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )

    gaps = [gap for gap in audit["gaps"] if gap["gap_miles"] > minimum_gap_miles]
    probe_root = probe_cache_directory / service_metadata_sha256
    key_records: dict[str, tuple[ProbedGapRecord, ...]] = {}
    key_probes: list[dict[str, Any]] = []
    for lrs_key in sorted({gap["lrs_key"] for gap in gaps}):
        if not LRS_KEY_PATTERN.fullmatch(lrs_key):
            raise ValueError(f"Locked gap names an invalid LRS key '{lrs_key}'.")
        predicate = f"LRSKEY='{lrs_key}'"
        result = acquire_nhpn(
            transport,
            query_url,
            {"where": predicate},
            probe_root / lrs_key,
            page_size=page_size,
        )
        records: list[ProbedGapRecord] = []
        unplaced = 0
        for feature in result.features:
            attributes = feature["attributes"]
            begin = attributes.get("BEGIN_POIN")
            end = attributes.get("END_POINT")
            if begin is None or end is None:
                unplaced += 1
                continue
            records.append(
                ProbedGapRecord(
                    int(attributes["OBJECTID"]),
                    str(attributes.get("STFIPS") or "").strip(),
                    _probe_sign_identities(attributes),
                    min(float(begin), float(end)),
                    max(float(begin), float(end)),
                )
            )
        key_records[lrs_key] = tuple(records)
        object_ids = list(result.object_ids)
        key_probes.append(
            {
                "lrs_key": lrs_key,
                "predicate": predicate,
                "expected_count": result.expected_count,
                "object_ids_sha256": canonical_sha256(object_ids),
                "features_sha256": canonical_sha256(list(result.features)),
                "records_without_mileposts": unplaced,
                "retries": result.retries,
                "resumed_pages": result.resumed_pages,
            }
        )

    gap_results = [
        _classify_gap(
            gap,
            key_records[gap["lrs_key"]],
            selectors[gap["segment_id"]],
            locked_object_ids,
        )
        for gap in gaps
    ]
    gap_results.sort(key=lambda gap: (-gap["gap_miles"], gap["segment_id"], gap["lrs_key"]))
    return {
        "schema_version": 1,
        "status": (
            "diagnostic acquisition; characterises the locked gaps' contents and "
            "the acquisition predicate; no lock changed"
        ),
        "acquired_at": timestamp,
        "query_url": query_url,
        "minimum_gap_miles": minimum_gap_miles,
        "source_milepost_quantum_miles": MILEPOST_QUANTUM_MILES,
        "coverage_tolerance_miles": GAP_COVERAGE_TOLERANCE_MILES,
        "service": {
            "canonical_metadata_sha256": service_metadata_sha256,
            "data_last_edit_epoch_ms": service_metadata["editingInfo"]["dataLastEditDate"],
            "matches_candidate_lock": True,
        },
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "source_policy": {
            "candidate_source": NHPN_SOURCE_ID,
            "nhpn_role": "coarse_topology_only",
            "openstreetmap_ancestry_allowed": False,
            "probe_is_selected_route_geometry": False,
            "continental_downloads_committed": False,
        },
        "key_probes": key_probes,
        "gap_count": len(gap_results),
        "gaps_no_records": sum(
            1 for gap in gap_results if gap["classification"] == "no_records"
        ),
        "gaps_fully_covered": sum(
            1 for gap in gap_results if gap["classification"] == "fully_covered"
        ),
        "gaps_partially_covered": sum(
            1 for gap in gap_results if gap["classification"] == "partially_covered"
        ),
        "predicate_anomaly_count": sum(
            len(gap["records_matching_predicate_unacquired"]) for gap in gap_results
        ),
        "finding": _gap_probe_finding(gap_results),
        "gaps": gap_results,
    }


def _derive_segment_geometric_probe_sites(
    segment_id: str,
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    from_point: tuple[float, float],
    to_point: tuple[float, float],
    tolerance: float = ENDPOINT_SNAP_TOLERANCE_METERS,
    anchor_limit: float = ANCHOR_SNAP_LIMIT_METERS,
) -> list[dict[str, Any]]:
    """Derive the smallest deterministic set of local sites that spans components.

    Components are joined conceptually with a minimum spanning tree whose edge
    weights are the nearest chain-end separations. This chooses probe locations;
    it does not join the route graph or assert that proximity means adjacency.
    Distant transfer anchors are separate sites because their mismatch can exist
    even when the candidate graph itself is connected.
    """
    graph, nodes, incident, _ = _build_snapped_endpoint_graph(metric_lines, tolerance)
    end_lines = {
        key: {candidate.object_id for candidate, _, _ in entries}
        for key, entries in incident.items()
    }
    if not graph.number_of_nodes():
        return []

    components = sorted(
        (set(component) for component in nx.connected_components(graph)),
        key=lambda component: min(component),
    )
    component_index = {
        node: index for index, component in enumerate(components) for node in component
    }

    # A near-linear component's degree-1 nodes are its ends. Fall back to all
    # component nodes only for a closed loop so the diagnostic remains defined.
    component_ends: list[list[tuple[int, int]]] = []
    for component in components:
        ends = sorted(node for node in component if graph.degree(node) == 1)
        component_ends.append(ends or sorted(component))

    pair_candidates: list[
        tuple[float, int, int, tuple[int, int], tuple[int, int]]
    ] = []
    for left_index, left_ends in enumerate(component_ends):
        for right_index in range(left_index + 1, len(component_ends)):
            choices = [
                (math.dist(nodes[left], nodes[right]), left, right)
                for left in left_ends
                for right in component_ends[right_index]
            ]
            distance, left, right = min(choices)
            pair_candidates.append((distance, left_index, right_index, left, right))

    parent = list(range(len(components)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> bool:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return False
        parent[max(left_root, right_root)] = min(left_root, right_root)
        return True

    sites: list[dict[str, Any]] = []
    for distance, left_index, right_index, left, right in sorted(pair_candidates):
        if not union(left_index, right_index):
            continue
        sites.append(
            {
                "site_id": (
                    f"{segment_id}--component-{left_index:02d}-{right_index:02d}"
                ),
                "segment_id": segment_id,
                "kind": "component_gap",
                "from_component": left_index,
                "to_component": right_index,
                "from_metric": nodes[left],
                "to_metric": nodes[right],
                "from_adjacent_object_ids": sorted(end_lines.get(left, set())),
                "to_adjacent_object_ids": sorted(end_lines.get(right, set())),
                "separation_m": distance,
            }
        )

    def nearest_node(point: tuple[float, float]) -> tuple[tuple[int, int], float]:
        return min(
            ((node, math.dist(point, coordinate)) for node, coordinate in nodes.items()),
            key=lambda item: (item[1], item[0]),
        )

    for side, point in (("from", from_point), ("to", to_point)):
        node, distance = nearest_node(point)
        if distance <= anchor_limit:
            continue
        sites.append(
            {
                "site_id": f"{segment_id}--anchor-{side}",
                "segment_id": segment_id,
                "kind": "anchor_gap",
                "anchor_side": side,
                "from_component": None,
                "to_component": component_index[node],
                "from_metric": point,
                "to_metric": nodes[node],
                "from_adjacent_object_ids": [],
                "to_adjacent_object_ids": sorted(end_lines.get(node, set())),
                "separation_m": distance,
            }
        )
    return sorted(sites, key=lambda site: site["site_id"])


def _spatial_probe_envelope(
    from_metric: tuple[float, float],
    to_metric: tuple[float, float],
    inverse: Transformer,
    padding_meters: float,
) -> tuple[float, float, float, float]:
    min_x = min(from_metric[0], to_metric[0]) - padding_meters
    max_x = max(from_metric[0], to_metric[0]) + padding_meters
    min_y = min(from_metric[1], to_metric[1]) - padding_meters
    max_y = max(from_metric[1], to_metric[1]) + padding_meters
    corners = [
        inverse.transform(x, y)
        for x in (min_x, max_x)
        for y in (min_y, max_y)
    ]
    longitudes = [coordinate[0] for coordinate in corners]
    latitudes = [coordinate[1] for coordinate in corners]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def _feature_metric_lines(
    features: Sequence[dict[str, Any]], forward: Transformer
) -> tuple[list[tuple[int, int, LineString, dict[str, Any]]], int]:
    lines: list[tuple[int, int, LineString, dict[str, Any]]] = []
    records_without_geometry = 0
    for feature in features:
        attributes = feature["attributes"]
        paths = feature.get("geometry", {}).get("paths", [])
        if not paths:
            records_without_geometry += 1
            continue
        for part_index, coordinates in enumerate(paths):
            if len(coordinates) < 2:
                records_without_geometry += 1
                continue
            line = transform(forward.transform, LineString(coordinates))
            lines.append((int(attributes["OBJECTID"]), part_index, line, attributes))
    return lines, records_without_geometry


def _classify_spatial_probe_connection(
    site: dict[str, Any],
    features: Sequence[dict[str, Any]],
    forward: Transformer,
    segment_object_ids: frozenset[int],
    all_locked_object_ids: frozenset[int],
    tolerance: float = ENDPOINT_SNAP_TOLERANCE_METERS,
    anchor_limit: float = ANCHOR_SNAP_LIMIT_METERS,
) -> dict[str, Any]:
    """Test whether an unfiltered local NHPN graph connects a probe site's ends."""
    lines, records_without_geometry = _feature_metric_lines(features, forward)
    graph = nx.MultiGraph()
    nodes: dict[tuple[int, int], tuple[float, float]] = {}
    attributes_by_id: dict[int, dict[str, Any]] = {}
    for object_id, part_index, line, attributes in sorted(
        lines, key=lambda item: (item[0], item[1])
    ):
        coordinates = list(line.coords)
        start_key = _resolve_endpoint_node(coordinates[0], nodes, tolerance)
        end_key = _resolve_endpoint_node(coordinates[-1], nodes, tolerance)
        if start_key == end_key:
            continue
        graph.add_edge(
            start_key,
            end_key,
            key=(object_id, part_index),
            weight=line.length,
            object_id=object_id,
        )
        attributes_by_id[object_id] = attributes

    result: dict[str, Any] = {
        "source_connection_found": False,
        "records_without_geometry": records_without_geometry,
        "local_graph_node_count": graph.number_of_nodes(),
        "local_graph_edge_count": graph.number_of_edges(),
        "from_probe_snap_distance_m": None,
        "to_probe_snap_distance_m": None,
        "from_probe_snap_limit_m": tolerance,
        "to_probe_snap_limit_m": tolerance,
        "path_object_ids": [],
        "path_records_in_segment_lock": [],
        "path_records_elsewhere_in_candidate_lock": [],
        "path_records_unacquired": [],
        "path_signed_routes": [],
        "path_state_fips": [],
    }
    if not graph.number_of_nodes():
        return result

    def nearest(point: tuple[float, float]) -> tuple[tuple[int, int], float]:
        return min(
            ((node, math.dist(point, coordinate)) for node, coordinate in nodes.items()),
            key=lambda item: (item[1], item[0]),
        )

    from_node, from_distance = nearest(site["from_metric"])
    to_node, to_distance = nearest(site["to_metric"])
    from_limit = (
        anchor_limit
        if site.get("kind") == "anchor_gap" and site.get("anchor_side") == "from"
        else tolerance
    )
    to_limit = (
        anchor_limit
        if site.get("kind") == "anchor_gap" and site.get("anchor_side") == "to"
        else tolerance
    )
    result["from_probe_snap_distance_m"] = round(from_distance, 3)
    result["to_probe_snap_distance_m"] = round(to_distance, 3)
    result["from_probe_snap_limit_m"] = from_limit
    result["to_probe_snap_limit_m"] = to_limit
    if from_distance > from_limit or to_distance > to_limit:
        return result
    if from_node != to_node and not nx.has_path(graph, from_node, to_node):
        return result

    node_path = (
        [from_node]
        if from_node == to_node
        else nx.shortest_path(graph, from_node, to_node, weight="weight")
    )
    path_object_ids: list[int] = []
    for previous, current in zip(node_path, node_path[1:], strict=False):
        parallel = graph.get_edge_data(previous, current)
        chosen_key = min(
            parallel,
            key=lambda edge_key: (parallel[edge_key]["weight"], edge_key),
        )
        path_object_ids.append(int(parallel[chosen_key]["object_id"]))
    unique_ids = sorted(set(path_object_ids))
    signed_routes = {
        f"{sign_type}-{sign_number}"
        for object_id in unique_ids
        for sign_type, sign_number in _probe_sign_identities(attributes_by_id[object_id])
    }
    states = {
        str(attributes_by_id[object_id].get("STFIPS") or "").strip()
        for object_id in unique_ids
    }
    result.update(
        source_connection_found=True,
        path_object_ids=path_object_ids,
        path_records_in_segment_lock=sorted(
            object_id for object_id in unique_ids if object_id in segment_object_ids
        ),
        path_records_elsewhere_in_candidate_lock=sorted(
            object_id
            for object_id in unique_ids
            if object_id in all_locked_object_ids and object_id not in segment_object_ids
        ),
        path_records_unacquired=sorted(
            object_id for object_id in unique_ids if object_id not in all_locked_object_ids
        ),
        path_signed_routes=sorted(signed_routes),
        path_state_fips=sorted(state for state in states if state),
    )
    return result


def _geometric_probe_finding(sites: Sequence[dict[str, Any]]) -> str:
    connected = [site for site in sites if site["source_connection_found"]]
    segment_count = len({site["segment_id"] for site in sites})
    with_unacquired = sum(bool(site["path_records_unacquired"]) for site in connected)
    with_elsewhere = sum(
        bool(site["path_records_elsewhere_in_candidate_lock"]) for site in connected
    )
    return (
        f"The locked graph produced {len(sites)} bounded candidate break sites across "
        f"{segment_count} unconnected segments. Unfiltered local NHPN topology connects "
        f"{len(connected)} sites; {with_unacquired} use records absent from the "
        f"candidate lock and {with_elsewhere} use records locked only for another "
        "segment. These are source-topology findings, not bridge approvals, a "
        "westbound selection, lane geometry, or an authoritative distance; every "
        "site still requires an ADR-0018 disposition."
    )


def probe_continental_geometric_breaks(
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    transfer_policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    probe_cache_directory: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
    padding_meters: float = GEOMETRIC_PROBE_PADDING_METERS,
) -> dict[str, Any]:
    """Probe unfiltered NHPN topology around locked graph break candidates."""
    if not math.isfinite(padding_meters) or padding_meters <= 0:
        raise ValueError("Geometric probe padding must be a positive finite distance.")
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path,
        transfer_policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        transfer_policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    snapshot_by_id = {
        snapshot["segment_id"]: snapshot
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    edge_by_id = {entry["segment_id"]: entry for entry in edge_lock["segments"]}
    all_locked_object_ids = _locked_object_id_union(route_lock)
    cache_root = cache_directory / route_lock["nhpn"]["service"][
        "canonical_metadata_sha256"
    ]
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)

    sites: list[dict[str, Any]] = []
    for segment in selection["segments"]:
        segment_id = segment["id"]
        edge_entry = edge_by_id.get(segment_id)
        if edge_entry is None or edge_entry.get("connected"):
            continue
        lines = _segment_locked_lines(route_lock, segment_id, cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )

        def metric_point(node_id: str) -> tuple[float, float]:
            coordinate = transfer_by_id[node_id]["coordinate"]
            return forward.transform(coordinate["longitude"], coordinate["latitude"])

        from_point = metric_point(segment["from"])
        to_point = metric_point(segment["to"])
        reproduced = _solve_segment_edge_path(
            segment,
            metric_lines,
            from_point,
            to_point,
            edge_lock["endpoint_snap_tolerance_m"],
        )
        if canonical_sha256(reproduced) != canonical_sha256(edge_entry):
            raise ValueError(
                f"Locked cache no longer reproduces edge-path diagnostics for '{segment_id}'."
            )
        sites.extend(
            _derive_segment_geometric_probe_sites(
                segment_id,
                metric_lines,
                from_point,
                to_point,
                edge_lock["endpoint_snap_tolerance_m"],
                edge_lock["anchor_snap_limit_m"],
            )
        )

    source = load_catalog(catalog_path)[NHPN_SOURCE_ID]
    service_url = source.raw["service_url"]
    query_url = service_url + NHPN_QUERY_SUFFIX
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_live_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    locked_metadata_sha256 = route_lock["nhpn"]["service"][
        "canonical_metadata_sha256"
    ]
    if service_metadata_sha256 != locked_metadata_sha256:
        raise ValueError(
            "Live NHPN service metadata has drifted from the candidate lock; a "
            "geometric probe would inspect a different dataset."
        )
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    probe_root = probe_cache_directory / service_metadata_sha256
    for site in sites:
        envelope = _spatial_probe_envelope(
            site["from_metric"], site["to_metric"], inverse, padding_meters
        )
        envelope_text = ",".join(f"{coordinate:.12f}" for coordinate in envelope)
        query = {
            "where": "1=1",
            "geometry": envelope_text,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        }
        result = acquire_nhpn(
            transport,
            query_url,
            query,
            probe_root / site["site_id"],
            page_size=page_size,
        )
        segment_snapshot = snapshot_by_id[site["segment_id"]]
        classification = _classify_spatial_probe_connection(
            site,
            result.features,
            forward,
            frozenset(segment_snapshot["object_ids"]),
            all_locked_object_ids,
            edge_lock["endpoint_snap_tolerance_m"],
            edge_lock["anchor_snap_limit_m"],
        )
        from_longitude, from_latitude = inverse.transform(*site.pop("from_metric"))
        to_longitude, to_latitude = inverse.transform(*site.pop("to_metric"))
        site.update(
            {
                "from_coordinate": {
                    "longitude": round(from_longitude, 12),
                    "latitude": round(from_latitude, 12),
                },
                "to_coordinate": {
                    "longitude": round(to_longitude, 12),
                    "latitude": round(to_latitude, 12),
                },
                "separation_m": round(site["separation_m"], 3),
                "query": query,
                "expected_count": result.expected_count,
                "object_ids_sha256": canonical_sha256(list(result.object_ids)),
                "features_sha256": canonical_sha256(list(result.features)),
                "retries": result.retries,
                "resumed_pages": result.resumed_pages,
                **classification,
            }
        )

    sites.sort(key=lambda site: site["site_id"])
    return {
        "schema_version": 1,
        "status": (
            "diagnostic acquisition; probes unfiltered source topology around locked "
            "break candidates; no lock changed"
        ),
        "acquired_at": timestamp,
        "query_url": query_url,
        "probe_padding_meters": padding_meters,
        "endpoint_snap_tolerance_m": edge_lock["endpoint_snap_tolerance_m"],
        "anchor_snap_limit_m": edge_lock["anchor_snap_limit_m"],
        "service": {
            "canonical_metadata_sha256": service_metadata_sha256,
            "data_last_edit_epoch_ms": service_metadata["editingInfo"]["dataLastEditDate"],
            "matches_candidate_lock": True,
        },
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "source_policy": {
            "candidate_source": NHPN_SOURCE_ID,
            "nhpn_role": "coarse_topology_only",
            "openstreetmap_ancestry_allowed": False,
            "probe_is_selected_route_geometry": False,
            "bridge_approved": False,
            "westbound_selection_validated": False,
            "authoritative_distance_claimed": False,
            "continental_downloads_committed": False,
        },
        "unconnected_segment_count": edge_lock["unconnected_segment_count"],
        "site_count": len(sites),
        "source_connection_count": sum(
            1 for site in sites if site["source_connection_found"]
        ),
        "finding": _geometric_probe_finding(sites),
        "sites": sites,
    }


# --- Per-chain-end census at the unconnected segments' break ends -------------
#
# probe-continental-geometric-breaks answers a path question: does an unfiltered
# local NHPN graph connect the two sides of each bounded break site? The census
# below answers the identity question that remains when it does not: what does
# the source assert at every individual chain end - which features join it,
# under which keys, signs, and states, at what measured offsets and bearings.
# The two probes share the snapped-graph builder and the envelope helper and
# are reconciled in docs/audits/p0-021/2026-08-30-spatial-break-probe.md and
# Q-034.

# Half-width of the spatial query window around each break end, in metres of the
# EPSG:5070 metric CRS. Grounded in the observed data: the largest endpoint
# discontinuity the connectivity audits measured between nearby chain ends is
# 661 m, so the two sides of such a break each see well past their midpoint,
# while the window stays local to the break rather than sampling the corridor.
BREAK_PROBE_BUFFER_METERS = 500.0

# Endpoint-offset ceiling for reporting an unlocked feature as a near join
# rather than an asserted one. Grounded in the transfer lock's own numbers:
# paired NHPN facilities reconcile within 24.401 m, so 30 m sits just above the
# source's observed cross-facility authoring offset. These tiers are reporting
# lenses for the audit, not bridging tolerances; ADR-0018 still forbids joining
# anything, and this probe joins nothing.
BREAK_NEAR_JOIN_TOLERANCE_METERS = 30.0

# A feature whose local bearing is within this many degrees of the break end's
# bearing is reported as aligned with the broken carriageway.
BREAK_ALIGNMENT_TOLERANCE_DEGREES = 20.0

# Chord length for measuring a local bearing: long enough to smooth
# digitisation jitter, short enough to stay local to the break.
BREAK_TANGENT_CHORD_METERS = 25.0

# Feature tiers from strongest to weakest joining evidence. The break end's
# summary classification is the strongest tier any returned feature reaches.
_BREAK_END_SUMMARY_BY_TIER = {
    "asserted_endpoint_join": "asserted_join_present",
    "near_endpoint_join": "near_join_present",
    "aligned_continuation": "aligned_continuation_present",
    "connector_or_crossing": "connectors_or_crossings_only",
    "elsewhere_in_window": "distant_features_only",
    "no_geometry": "distant_features_only",
}
_BREAK_TIER_ORDER = tuple(_BREAK_END_SUMMARY_BY_TIER)


def _chord_bearing(
    line: LineString,
    at_distance: float,
    chord: float = BREAK_TANGENT_CHORD_METERS,
) -> float | None:
    """Bearing of the line over a chord centred on ``at_distance``, in degrees.

    A chord absorbs the vertex-to-vertex jitter a digitised centreline carries.
    Returns None when the line is too degenerate to carry a direction.
    """
    low = max(0.0, at_distance - chord)
    high = min(line.length, at_distance + chord)
    if high <= low:
        return None
    first = line.interpolate(low)
    second = line.interpolate(high)
    if first.x == second.x and first.y == second.y:
        return None
    return math.degrees(math.atan2(second.y - first.y, second.x - first.x))


def _acute_angle_degrees(first: float, second: float) -> float:
    """Smallest angle between two undirected bearings, in [0, 90]."""
    difference = abs(first - second) % 180.0
    return min(difference, 180.0 - difference)


def _break_feature_metrics(
    break_point: Point,
    break_bearing: float | None,
    metric_parts: Sequence[LineString],
) -> dict[str, float | None]:
    """How one probed feature sits relative to a break end, in metric metres.

    ``endpoint_offset_m`` is the nearest feature endpoint, because an endpoint
    near the break is how NHPN would assert a join. ``geometry_distance_m`` is
    the nearest point anywhere on the feature, because a carriageway that
    continues *through* the break area never presents an endpoint there.
    ``alignment_degrees`` compares local bearings at the closest approach.
    """
    if not metric_parts:
        return {
            "endpoint_offset_m": None,
            "geometry_distance_m": None,
            "alignment_degrees": None,
        }
    endpoint_offset = float("inf")
    best_part: LineString | None = None
    best_distance = float("inf")
    for part in metric_parts:
        coordinates = list(part.coords)
        for endpoint in (coordinates[0], coordinates[-1]):
            endpoint_offset = min(
                endpoint_offset, math.dist((break_point.x, break_point.y), endpoint)
            )
        distance = part.distance(break_point)
        if distance < best_distance:
            best_part, best_distance = part, distance
    alignment: float | None = None
    if best_part is not None and break_bearing is not None:
        feature_bearing = _chord_bearing(best_part, best_part.project(break_point))
        if feature_bearing is not None:
            alignment = _acute_angle_degrees(break_bearing, feature_bearing)
    return {
        "endpoint_offset_m": round(endpoint_offset, 3),
        "geometry_distance_m": round(best_distance, 3),
        "alignment_degrees": None if alignment is None else round(alignment, 1),
    }


def _break_feature_tier(
    metrics: dict[str, float | None], snap_tolerance: float
) -> str:
    """Descriptive evidence tier for one probed feature at one break end."""
    endpoint_offset = metrics["endpoint_offset_m"]
    geometry_distance = metrics["geometry_distance_m"]
    alignment = metrics["alignment_degrees"]
    if endpoint_offset is None or geometry_distance is None:
        return "no_geometry"
    if endpoint_offset <= snap_tolerance:
        return "asserted_endpoint_join"
    if endpoint_offset <= BREAK_NEAR_JOIN_TOLERANCE_METERS:
        return "near_endpoint_join"
    if geometry_distance <= BREAK_NEAR_JOIN_TOLERANCE_METERS:
        if alignment is not None and alignment <= BREAK_ALIGNMENT_TOLERANCE_DEGREES:
            return "aligned_continuation"
        return "connector_or_crossing"
    return "elsewhere_in_window"


def _records_milepost_contiguous(
    left: LockedCandidateLine, right: LockedCandidateLine
) -> bool:
    """The 2026-08-14 adjacency rule: one record's END_POINT equals the other's
    BEGIN_POIN on the same LRSKEY."""
    if left.lrs_key != right.lrs_key or not left.lrs_key:
        return False
    return (
        abs(left.record_end_milepost - right.record_begin_milepost) < 1e-6
        or abs(right.record_end_milepost - left.record_begin_milepost) < 1e-6
    )


def _select_break_ends(
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    from_point: tuple[float, float],
    to_point: tuple[float, float],
    tolerance: float,
    inverse: Transformer,
) -> dict[str, Any] | None:
    """Select one unconnected segment's break ends from its snapped graph.

    Shared by the break-end census and the gap-interior sweep, on top of the
    shared graph builder, so no two artifacts can disagree about which chain
    ends are breaks. A break end is a degree-1 chain end that is not, per
    anchor, the chain end of that anchor's component farthest from the opposite
    anchor - that end is where the chain legitimately continues beyond the
    corridor (past the anchor, or past the declared jurisdictions). Returns
    None when the segment produced no graph nodes.
    """
    graph, nodes, incident, _ = _build_snapped_endpoint_graph(metric_lines, tolerance)
    if not graph.number_of_nodes():
        return None

    components = sorted(nx.connected_components(graph), key=lambda c: (-len(c), min(c)))
    component_of = {node: index for index, comp in enumerate(components) for node in comp}
    chain_ends = sorted(key for key, entries in incident.items() if len(entries) == 1)

    def nearest_node(point: tuple[float, float]) -> tuple[tuple[int, int], float]:
        best_key, best_distance = None, float("inf")
        for key in sorted(nodes):
            distance = math.dist(point, nodes[key])
            if distance < best_distance:
                best_key, best_distance = key, distance
        assert best_key is not None
        return best_key, best_distance

    anchor_side_ends: list[dict[str, Any]] = []
    excluded: set[tuple[int, int]] = set()
    anchor_components: dict[str, int] = {}
    anchor_distances: dict[str, float] = {}
    for label, anchor, opposite in (
        ("from", from_point, to_point),
        ("to", to_point, from_point),
    ):
        anchor_node, anchor_distance = nearest_node(anchor)
        component_index = component_of[anchor_node]
        anchor_components[label] = component_index
        anchor_distances[label] = anchor_distance
        component_ends = [key for key in chain_ends if component_of[key] == component_index]
        if not component_ends:
            continue
        end = max(component_ends, key=lambda key: (math.dist(opposite, nodes[key]), key))
        excluded.add(end)
        candidate, _, which = incident[end][0]
        longitude, latitude = inverse.transform(*nodes[end])
        anchor_side_ends.append(
            {
                "anchor": label,
                "component_index": component_index,
                "coordinate": {
                    "longitude": round(longitude, 7),
                    "latitude": round(latitude, 7),
                },
                "record": {
                    "object_id": candidate.object_id,
                    "part_index": candidate.part_index,
                    "geometry_end": which,
                    "lrs_key": candidate.lrs_key,
                },
                "distance_to_anchor_m": round(math.dist(anchor, nodes[end]), 3),
            }
        )

    break_nodes = sorted(
        (key for key in chain_ends if key not in excluded),
        key=lambda key: (
            incident[key][0][0].object_id,
            incident[key][0][0].part_index,
            incident[key][0][2],
        ),
    )
    end_id_by_node: dict[tuple[int, int], str] = {}
    for node in break_nodes:
        candidate, _, which = incident[node][0]
        end_id_by_node[node] = (
            f"end-{candidate.object_id:07d}-{candidate.part_index:02d}-{which}"
        )
    return {
        "graph": graph,
        "nodes": nodes,
        "incident": incident,
        "components": components,
        "component_of": component_of,
        "anchor_side_ends": anchor_side_ends,
        "anchor_components": anchor_components,
        "anchor_distances": anchor_distances,
        "break_nodes": break_nodes,
        "end_id_by_node": end_id_by_node,
        "node_by_end_id": {value: key for key, value in end_id_by_node.items()},
    }


def _nearest_cross_component_pairs(
    break_nodes: Sequence[tuple[int, int]],
    nodes: dict[tuple[int, int], tuple[float, float]],
    component_of: dict[tuple[int, int], int],
    end_id_by_node: dict[tuple[int, int], str],
) -> tuple[dict[str, dict[str, Any] | None], list[dict[str, Any]]]:
    """Pair every break end with the nearest break end in a different component.

    Observed geometry, not asserted adjacency. Returns each end's nearest
    cross-component end and the deduplicated pair list with raw separations,
    shared by the census and the gap-interior sweep so they cannot disagree
    about which interiors exist.
    """
    nearest_by_end: dict[str, dict[str, Any] | None] = {}
    pair_keys: set[tuple[str, str]] = set()
    for node in break_nodes:
        end_id = end_id_by_node[node]
        others = [
            other for other in break_nodes if component_of[other] != component_of[node]
        ]
        if not others:
            nearest_by_end[end_id] = None
            continue
        nearest = min(
            others,
            key=lambda other: (math.dist(nodes[node], nodes[other]), end_id_by_node[other]),
        )
        separation = math.dist(nodes[node], nodes[nearest])
        nearest_by_end[end_id] = {
            "id": end_id_by_node[nearest],
            "separation_m": round(separation, 3),
        }
        pair_keys.add(tuple(sorted((end_id, end_id_by_node[nearest]))))
    node_by_end_id = {value: key for key, value in end_id_by_node.items()}
    pairs = [
        {
            "end_ids": [left_id, right_id],
            "separation_m": math.dist(
                nodes[node_by_end_id[left_id]], nodes[node_by_end_id[right_id]]
            ),
        }
        for left_id, right_id in sorted(pair_keys)
    ]
    return nearest_by_end, pairs


def _probe_segment_break_ends(
    segment_id: str,
    failure: str,
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    from_point: tuple[float, float],
    to_point: tuple[float, float],
    tolerance: float,
    *,
    transport: ArcGisTransport,
    query_url: str,
    probe_root: Path,
    page_size: int,
    locked_segments_by_object_id: dict[int, tuple[str, ...]],
    forward: Transformer,
    inverse: Transformer,
    buffer_meters: float = BREAK_PROBE_BUFFER_METERS,
) -> dict[str, Any]:
    """Census NHPN spatially around one unconnected segment's break ends.

    A break end is a chain end that is not the anchor component's continuation
    beyond the corridor. For each one, everything NHPN carries inside a window
    around the end is fetched with no sign, state, or key filter and reported
    with its keys, signs, and geometric offsets. Nothing is joined and no lock
    is touched: the output is the evidence an ADR-0018-compliant per-break
    decision needs, not the decision.
    """
    selection = _select_break_ends(metric_lines, from_point, to_point, tolerance, inverse)
    result: dict[str, Any] = {"segment_id": segment_id, "failure": failure}
    if selection is None:
        result.update(break_end_count=0, break_ends=[], break_pairs=[],
                      note="segment produced no graph nodes")
        return result

    nodes = selection["nodes"]
    incident = selection["incident"]
    components = selection["components"]
    component_of = selection["component_of"]
    anchor_side_ends = selection["anchor_side_ends"]
    anchor_components = selection["anchor_components"]
    anchor_distances = selection["anchor_distances"]
    break_nodes = selection["break_nodes"]
    end_id_by_node = selection["end_id_by_node"]
    node_by_id = selection["node_by_end_id"]

    break_ends: list[dict[str, Any]] = []
    features_by_end: dict[str, dict[int, dict[str, Any]]] = {}
    for node in break_nodes:
        candidate, line, which = incident[node][0]
        end_id = end_id_by_node[node]
        break_point = Point(nodes[node])
        end_bearing = _chord_bearing(line, 0.0 if which == "start" else line.length)
        envelope = _spatial_probe_envelope(
            nodes[node], nodes[node], inverse, buffer_meters
        )
        query = {
            "where": "1=1",
            "geometry": ",".join(f"{coordinate:.12f}" for coordinate in envelope),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        }
        acquisition = acquire_nhpn(
            transport,
            query_url,
            query,
            probe_root / segment_id / end_id,
            page_size=page_size,
        )

        own_locked_count = 0
        break_record_state = ""
        break_record_signs: list[str] = []
        details: list[dict[str, Any]] = []
        for feature in acquisition.features:
            attributes = feature["attributes"]
            object_id = int(attributes["OBJECTID"])
            locked_under = locked_segments_by_object_id.get(object_id, ())
            if object_id == candidate.object_id:
                break_record_state = str(attributes.get("STFIPS") or "").strip()
                break_record_signs = sorted(
                    f"{sign_type}-{sign_number}"
                    for sign_type, sign_number in _probe_sign_identities(attributes)
                )
            if segment_id in locked_under:
                own_locked_count += 1
                continue
            metric_parts = [
                transform(forward.transform, LineString(coordinates))
                for coordinates in feature.get("geometry", {}).get("paths", [])
                if len(coordinates) >= 2
            ]
            metrics = _break_feature_metrics(break_point, end_bearing, metric_parts)
            details.append(
                {
                    "object_id": object_id,
                    "state_fips": str(attributes.get("STFIPS") or "").strip(),
                    "lrs_key": str(attributes.get("LRSKEY") or "").strip(),
                    "signed_routes": sorted(
                        f"{sign_type}-{sign_number}"
                        for sign_type, sign_number in _probe_sign_identities(attributes)
                    ),
                    "record_begin_milepost": attributes.get("BEGIN_POIN"),
                    "record_end_milepost": attributes.get("END_POINT"),
                    "locked_segment_ids": sorted(locked_under),
                    **metrics,
                    "classification": _break_feature_tier(metrics, tolerance),
                }
            )
        details.sort(
            key=lambda item: (
                item["geometry_distance_m"] if item["geometry_distance_m"] is not None
                else float("inf"),
                item["object_id"],
            )
        )
        tiers_present = {detail["classification"] for detail in details}
        summary = "source_void_beyond_lock"
        for tier in _BREAK_TIER_ORDER:
            if tier in tiers_present:
                summary = _BREAK_END_SUMMARY_BY_TIER[tier]
                break
        longitude, latitude = inverse.transform(*nodes[node])
        features_by_end[end_id] = {detail["object_id"]: detail for detail in details}
        break_ends.append(
            {
                "id": end_id,
                "component_index": component_of[node],
                "component_node_count": len(components[component_of[node]]),
                "coordinate": {
                    "longitude": round(longitude, 7),
                    "latitude": round(latitude, 7),
                },
                "record": {
                    "object_id": candidate.object_id,
                    "part_index": candidate.part_index,
                    "geometry_end": which,
                    "lrs_key": candidate.lrs_key,
                    "record_begin_milepost": candidate.record_begin_milepost,
                    "record_end_milepost": candidate.record_end_milepost,
                    "state_fips": break_record_state,
                    "signed_routes": break_record_signs,
                },
                "envelope_4326": [round(value, 7) for value in envelope],
                "probe": {
                    "expected_count": acquisition.expected_count,
                    "object_ids_sha256": canonical_sha256(list(acquisition.object_ids)),
                    "features_sha256": canonical_sha256(list(acquisition.features)),
                    "retries": acquisition.retries,
                    "resumed_pages": acquisition.resumed_pages,
                },
                "own_locked_feature_count": own_locked_count,
                "classification": summary,
                "classification_counts": {
                    tier: sum(1 for detail in details if detail["classification"] == tier)
                    for tier in _BREAK_TIER_ORDER
                    if tier in tiers_present
                },
                "features": details,
            }
        )

    # Pair every break end with the nearest break end in a different component:
    # observed geometry, not asserted adjacency. Joining evidence for a pair is
    # any probed feature that comes near both of its ends.
    nearest_by_end, raw_pairs = _nearest_cross_component_pairs(
        break_nodes, nodes, component_of, end_id_by_node
    )
    for entry in break_ends:
        entry["nearest_cross_component_end"] = nearest_by_end[entry["id"]]

    break_pairs: list[dict[str, Any]] = []
    for pair in raw_pairs:
        left_id, right_id = pair["end_ids"]
        left_node, right_node = node_by_id[left_id], node_by_id[right_id]
        separation = pair["separation_m"]
        windows_overlap = separation <= 2 * buffer_meters
        spanning: list[int] = []
        if windows_overlap:
            spanning = sorted(
                object_id
                for object_id, detail in features_by_end[left_id].items()
                if object_id in features_by_end[right_id]
                and detail["geometry_distance_m"] is not None
                and detail["geometry_distance_m"] <= BREAK_NEAR_JOIN_TOLERANCE_METERS
                and features_by_end[right_id][object_id]["geometry_distance_m"] is not None
                and features_by_end[right_id][object_id]["geometry_distance_m"]
                <= BREAK_NEAR_JOIN_TOLERANCE_METERS
            )
        break_pairs.append(
            {
                "end_ids": [left_id, right_id],
                "separation_m": round(separation, 3),
                "milepost_contiguous": _records_milepost_contiguous(
                    incident[left_node][0][0], incident[right_node][0][0]
                ),
                "probe_windows_overlap": windows_overlap,
                "spanning_feature_object_ids": spanning,
            }
        )

    result.update(
        connected_component_count=len(components),
        component_node_counts=[len(component) for component in components],
        from_component_index=anchor_components["from"],
        to_component_index=anchor_components["to"],
        from_anchor_node_distance_m=round(anchor_distances["from"], 3),
        to_anchor_node_distance_m=round(anchor_distances["to"], 3),
        anchor_side_ends=anchor_side_ends,
        break_end_count=len(break_ends),
        break_ends=break_ends,
        break_pairs=break_pairs,
    )
    return result


def _break_probe_finding(segments: list[dict[str, Any]]) -> str:
    """Describe the census using the numbers it actually produced.

    Generated rather than written so it cannot drift from the break results
    beside it.
    """
    if not segments:
        return "No unconnected segments were probed."
    ends = [end for segment in segments for end in segment.get("break_ends", [])]
    by_class: dict[str, int] = {}
    for end in ends:
        by_class[end["classification"]] = by_class.get(end["classification"], 0) + 1
    pairs = [pair for segment in segments for pair in segment.get("break_pairs", [])]
    spanned = sum(1 for pair in pairs if pair["spanning_feature_object_ids"])
    contiguous = sum(1 for pair in pairs if pair["milepost_contiguous"])
    return (
        f"Across {len(segments)} unconnected segments, {len(ends)} break ends were "
        "probed spatially with no sign, state, or key filter. "
        f"{by_class.get('asserted_join_present', 0)} break ends have an unlocked "
        "feature whose endpoint coincides with the break end within the snapping "
        f"tolerance, {by_class.get('near_join_present', 0)} have one within the "
        f"{BREAK_NEAR_JOIN_TOLERANCE_METERS:g} m near-join lens, "
        f"{by_class.get('aligned_continuation_present', 0)} have an aligned "
        "carriageway passing through without an endpoint, "
        f"{by_class.get('connectors_or_crossings_only', 0)} see only connectors or "
        f"crossings, {by_class.get('distant_features_only', 0)} see only distant "
        f"features, and {by_class.get('source_void_beyond_lock', 0)} see nothing "
        f"beyond the already-locked records. Of {len(pairs)} cross-component end "
        f"pairs, {contiguous} are milepost-contiguous and {spanned} have at least "
        "one probed feature near both ends. These tiers are reporting lenses, not "
        "bridging decisions: nothing is joined, no direction or distance is "
        "claimed, and no lock is changed."
    )


def probe_continental_break_ends(
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    probe_cache_directory: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
    buffer_meters: float = BREAK_PROBE_BUFFER_METERS,
) -> dict[str, Any]:
    """Census what NHPN asserts at every unconnected-segment break end.

    Complements probe_continental_geometric_breaks, which tests whether an
    unfiltered local source graph supplies a path across each bounded
    component-pair site. This census instead characterises every individual
    chain end: which features physically join it, under which keys, signs, and
    states, at what measured endpoint offsets, geometry distances, and bearing
    alignments — including at sites where no local source path exists, and at
    spur ends the site selection never visits. Both probes feed the Q-034
    per-site disposition.

    It is a characterisation, not a selection or a bridging policy: it changes
    no lock, claims no westbound direction and no authoritative distance, and
    its responses stay in the ignored cache. It refuses to run when the live
    service has drifted from the locked snapshot, because it would then probe a
    different dataset than the one whose breaks it is explaining.
    """
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    route_lock = validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    selection = load_json(selection_path)

    source = load_catalog(catalog_path)[NHPN_SOURCE_ID]
    service_url = source.raw["service_url"]
    query_url = service_url + NHPN_QUERY_SUFFIX
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_live_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    locked_metadata_sha256 = route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    if service_metadata_sha256 != locked_metadata_sha256:
        raise ValueError(
            "Live NHPN service metadata has drifted from the candidate lock; a probe "
            "against it would characterise a different dataset than the one whose "
            "breaks it is explaining."
        )
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )

    locked_segments: dict[int, set[str]] = {}
    for snapshot in route_lock["nhpn"]["segment_snapshots"]:
        for object_id in snapshot["object_ids"]:
            locked_segments.setdefault(object_id, set()).add(snapshot["segment_id"])
    locked_segments_by_object_id = {
        object_id: tuple(sorted(segment_ids))
        for object_id, segment_ids in locked_segments.items()
    }

    segment_by_id = {segment["id"]: segment for segment in selection["segments"]}
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    cache_root = cache_directory / locked_metadata_sha256
    probe_root = probe_cache_directory / service_metadata_sha256
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])

    def metric_point(node_id: str) -> tuple[float, float]:
        coordinate = transfer_by_id[node_id]["coordinate"]
        return forward.transform(coordinate["longitude"], coordinate["latitude"])

    unconnected = sorted(
        (entry for entry in edge_lock["segments"] if not entry.get("connected")),
        key=lambda entry: entry["segment_id"],
    )
    segments: list[dict[str, Any]] = []
    for entry in unconnected:
        segment = segment_by_id[entry["segment_id"]]
        lines = _segment_locked_lines(route_lock, entry["segment_id"], cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )
        segments.append(
            _probe_segment_break_ends(
                entry["segment_id"],
                str(entry.get("failure", "")),
                metric_lines,
                metric_point(segment["from"]),
                metric_point(segment["to"]),
                tolerance,
                transport=transport,
                query_url=query_url,
                probe_root=probe_root,
                page_size=page_size,
                locked_segments_by_object_id=locked_segments_by_object_id,
                forward=forward,
                inverse=inverse,
                buffer_meters=buffer_meters,
            )
        )

    return {
        "schema_version": 1,
        "status": (
            "diagnostic acquisition; characterises what NHPN asserts at the "
            "unconnected segments' break ends; no bridging decided and no "
            "lock changed"
        ),
        "acquired_at": timestamp,
        "query_url": query_url,
        "buffer_meters": buffer_meters,
        "endpoint_snap_tolerance_m": tolerance,
        "near_join_tolerance_m": BREAK_NEAR_JOIN_TOLERANCE_METERS,
        "alignment_tolerance_degrees": BREAK_ALIGNMENT_TOLERANCE_DEGREES,
        "tangent_chord_m": BREAK_TANGENT_CHORD_METERS,
        "service": {
            "canonical_metadata_sha256": service_metadata_sha256,
            "data_last_edit_epoch_ms": service_metadata["editingInfo"]["dataLastEditDate"],
            "matches_candidate_lock": True,
        },
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "source_policy": {
            "candidate_source": NHPN_SOURCE_ID,
            "nhpn_role": "coarse_topology_only",
            "openstreetmap_ancestry_allowed": False,
            "probe_is_selected_route_geometry": False,
            "continental_downloads_committed": False,
            "bridging_decided": False,
        },
        "unconnected_segment_count": len(segments),
        "break_end_count": sum(segment["break_end_count"] for segment in segments),
        "finding": _break_probe_finding(segments),
        "segments": segments,
    }


# --- Interior sweep of the break pairs wider than the census windows ----------
#
# The break-end census characterises 500 m neighbourhoods around each break
# end, so a pair separated by more than two window widths has an interior
# neither probe has seen. The sweep tiles that interior with the same
# unfiltered envelope machinery and classifies what NHPN carries there
# relative to the pair's end-to-end chord. Reporting lenses only: nothing is
# joined, no direction is claimed, and no lock changes.

# A pair whose ends are closer than two census windows has no unseen interior.
INTERIOR_SWEEP_MINIMUM_SEPARATION_METERS = 2.0 * BREAK_PROBE_BUFFER_METERS

# Above this separation a pair does not measure a candidate mainline break: it
# measures the isolation of a fragment embedded in another route's pavement
# (the 27.3 km I-15 and 13.6 km Albuquerque fragment pairings), whose milepost
# interiors the 2026-08-27 whole-key probe already characterised. Such pairs
# are recorded as beyond the sweep limit rather than swept.
INTERIOR_SWEEP_MAXIMUM_SEPARATION_METERS = 5_000.0


def _interior_window_centers(
    from_metric: tuple[float, float],
    to_metric: tuple[float, float],
    buffer_meters: float,
) -> list[tuple[float, float]]:
    """Window centres tiling the interior between two break ends.

    Centres are spaced at most one window half-width apart along the straight
    chord, so consecutive windows overlap and jointly cover the chord end to
    end with margin on every side.
    """
    separation = math.dist(from_metric, to_metric)
    count = max(1, math.ceil(separation / buffer_meters))
    return [
        (
            from_metric[0] + (to_metric[0] - from_metric[0]) * (index + 0.5) / count,
            from_metric[1] + (to_metric[1] - from_metric[1]) * (index + 0.5) / count,
        )
        for index in range(count)
    ]


def _interior_feature_metrics(
    chord: LineString,
    chord_bearing: float | None,
    metric_parts: Sequence[LineString],
) -> dict[str, float | None]:
    """How one probed feature sits relative to a gap's end-to-end chord.

    ``chord_distance_m`` is the feature's nearest approach to the chord;
    ``alignment_degrees`` compares the feature's local bearing at that approach
    against the chord bearing. The chord is a straight reference line between
    the two break ends, not an asserted road alignment.
    """
    if not metric_parts:
        return {"chord_distance_m": None, "alignment_degrees": None}
    best_part: LineString | None = None
    best_distance = float("inf")
    for part in metric_parts:
        distance = part.distance(chord)
        if distance < best_distance:
            best_part, best_distance = part, distance
    alignment: float | None = None
    if best_part is not None and chord_bearing is not None:
        _, on_part = nearest_points(chord, best_part)
        feature_bearing = _chord_bearing(best_part, best_part.project(on_part))
        if feature_bearing is not None:
            alignment = _acute_angle_degrees(chord_bearing, feature_bearing)
    return {
        "chord_distance_m": round(best_distance, 3),
        "alignment_degrees": None if alignment is None else round(alignment, 1),
    }


def _interior_feature_tier(
    metrics: dict[str, float | None],
    axis_lens_meters: float = BREAK_NEAR_JOIN_TOLERANCE_METERS,
) -> str:
    """Descriptive evidence tier for one feature inside a swept gap interior."""
    chord_distance = metrics["chord_distance_m"]
    alignment = metrics["alignment_degrees"]
    if chord_distance is None:
        return "no_geometry"
    aligned = alignment is not None and alignment <= BREAK_ALIGNMENT_TOLERANCE_DEGREES
    if chord_distance <= axis_lens_meters:
        return "aligned_on_axis" if aligned else "crossing_on_axis"
    if aligned:
        return "aligned_off_axis"
    return "elsewhere_in_window"


# Gap summary classifications from strongest to weakest interior evidence.
_INTERIOR_SUMMARY_BY_TIER = {
    "aligned_on_axis": "mainline_candidate_on_axis",
    "aligned_off_axis": "aligned_facilities_off_axis_only",
    "crossing_on_axis": "crossings_only_on_axis",
    "elsewhere_in_window": "distant_features_only",
    "no_geometry": "distant_features_only",
}
_INTERIOR_TIER_ORDER = tuple(_INTERIOR_SUMMARY_BY_TIER)


def _interior_sweep_finding(segments: list[dict[str, Any]]) -> str:
    """Describe the sweep using the numbers it actually produced."""
    if not segments:
        return "No unconnected segments were swept."
    gaps = [gap for segment in segments for gap in segment.get("swept_gaps", [])]
    if not gaps:
        return "No break pair exceeded the sweep threshold; every interior is covered."
    by_class: dict[str, int] = {}
    for gap in gaps:
        by_class[gap["classification"]] = by_class.get(gap["classification"], 0) + 1
    total_km = sum(gap["separation_m"] for gap in gaps) / 1000.0
    return (
        f"{len(gaps)} break-pair interiors wider than the census windows were swept "
        f"({total_km:.1f} km in total) with unfiltered envelopes tiling each pair's "
        f"chord. {by_class.get('mainline_candidate_on_axis', 0)} interiors carry an "
        "unlocked feature aligned with and within the near-join lens of the chord, "
        f"{by_class.get('aligned_facilities_off_axis_only', 0)} carry aligned "
        "facilities only away from the chord, "
        f"{by_class.get('crossings_only_on_axis', 0)} carry only crossings on the "
        f"chord, {by_class.get('distant_features_only', 0)} carry only distant "
        f"features, and {by_class.get('interior_void_beyond_lock', 0)} carry nothing "
        "beyond the already-locked records. The chord is a straight reference line, "
        "not an asserted alignment; these tiers are reporting lenses for the Q-034 "
        "disposition, not bridging decisions, and no lock is changed."
    )


def probe_continental_gap_interiors(
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    probe_cache_directory: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
    buffer_meters: float = BREAK_PROBE_BUFFER_METERS,
    minimum_separation_meters: float = INTERIOR_SWEEP_MINIMUM_SEPARATION_METERS,
    maximum_separation_meters: float = INTERIOR_SWEEP_MAXIMUM_SEPARATION_METERS,
) -> dict[str, Any]:
    """Sweep what NHPN carries inside the break-pair interiors wider than the
    census windows.

    The 2026-08-30 census characterised 500 m neighbourhoods around every break
    end; this closes its named evidence hole - the pair interiors wider than
    two windows - by tiling each such interior with the same unfiltered
    envelope machinery. It is a characterisation, not a selection: it changes
    no lock, claims no direction and no distance, and its responses stay in the
    ignored cache. It refuses a live service that has drifted from the locked
    snapshot.
    """
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    route_lock = validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    selection = load_json(selection_path)

    source = load_catalog(catalog_path)[NHPN_SOURCE_ID]
    service_url = source.raw["service_url"]
    query_url = service_url + NHPN_QUERY_SUFFIX
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_live_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    locked_metadata_sha256 = route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    if service_metadata_sha256 != locked_metadata_sha256:
        raise ValueError(
            "Live NHPN service metadata has drifted from the candidate lock; a sweep "
            "against it would characterise a different dataset than the one whose "
            "gap interiors it is explaining."
        )
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )

    locked_segments: dict[int, set[str]] = {}
    for snapshot in route_lock["nhpn"]["segment_snapshots"]:
        for object_id in snapshot["object_ids"]:
            locked_segments.setdefault(object_id, set()).add(snapshot["segment_id"])

    segment_by_id = {segment["id"]: segment for segment in selection["segments"]}
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    cache_root = cache_directory / locked_metadata_sha256
    probe_root = probe_cache_directory / service_metadata_sha256
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])

    def metric_point(node_id: str) -> tuple[float, float]:
        coordinate = transfer_by_id[node_id]["coordinate"]
        return forward.transform(coordinate["longitude"], coordinate["latitude"])

    unconnected = sorted(
        (entry for entry in edge_lock["segments"] if not entry.get("connected")),
        key=lambda entry: entry["segment_id"],
    )
    segments: list[dict[str, Any]] = []
    for entry in unconnected:
        segment = segment_by_id[entry["segment_id"]]
        lines = _segment_locked_lines(route_lock, entry["segment_id"], cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )
        segments.append(
            _sweep_segment_gap_interiors(
                entry["segment_id"],
                str(entry.get("failure", "")),
                metric_lines,
                metric_point(segment["from"]),
                metric_point(segment["to"]),
                tolerance,
                transport=transport,
                query_url=query_url,
                probe_root=probe_root,
                page_size=page_size,
                locked_segments_by_object_id={
                    object_id: tuple(sorted(ids)) for object_id, ids in locked_segments.items()
                },
                forward=forward,
                inverse=inverse,
                buffer_meters=buffer_meters,
                minimum_separation_meters=minimum_separation_meters,
                maximum_separation_meters=maximum_separation_meters,
            )
        )

    swept = [gap for segment in segments for gap in segment["swept_gaps"]]
    return {
        "schema_version": 1,
        "status": (
            "diagnostic acquisition; characterises what NHPN carries inside the "
            "break-pair interiors wider than the census windows; no bridging "
            "decided and no lock changed"
        ),
        "acquired_at": timestamp,
        "query_url": query_url,
        "buffer_meters": buffer_meters,
        "minimum_separation_meters": minimum_separation_meters,
        "maximum_separation_meters": maximum_separation_meters,
        "endpoint_snap_tolerance_m": tolerance,
        "axis_lens_m": BREAK_NEAR_JOIN_TOLERANCE_METERS,
        "alignment_tolerance_degrees": BREAK_ALIGNMENT_TOLERANCE_DEGREES,
        "service": {
            "canonical_metadata_sha256": service_metadata_sha256,
            "data_last_edit_epoch_ms": service_metadata["editingInfo"]["dataLastEditDate"],
            "matches_candidate_lock": True,
        },
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "source_policy": {
            "candidate_source": NHPN_SOURCE_ID,
            "nhpn_role": "coarse_topology_only",
            "openstreetmap_ancestry_allowed": False,
            "probe_is_selected_route_geometry": False,
            "continental_downloads_committed": False,
            "bridging_decided": False,
        },
        "unconnected_segment_count": len(segments),
        "swept_gap_count": len(swept),
        "swept_meters_total": round(sum(gap["separation_m"] for gap in swept), 3),
        "finding": _interior_sweep_finding(segments),
        "segments": segments,
    }


def _sweep_segment_gap_interiors(
    segment_id: str,
    failure: str,
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    from_point: tuple[float, float],
    to_point: tuple[float, float],
    tolerance: float,
    *,
    transport: ArcGisTransport,
    query_url: str,
    probe_root: Path,
    page_size: int,
    locked_segments_by_object_id: dict[int, tuple[str, ...]],
    forward: Transformer,
    inverse: Transformer,
    buffer_meters: float,
    minimum_separation_meters: float,
    maximum_separation_meters: float,
) -> dict[str, Any]:
    """Sweep one unconnected segment's over-wide break-pair interiors."""
    selection = _select_break_ends(metric_lines, from_point, to_point, tolerance, inverse)
    result: dict[str, Any] = {"segment_id": segment_id, "failure": failure}
    if selection is None:
        result.update(
            break_end_ids=[],
            swept_gaps=[],
            pairs_covered_by_break_end_windows=[],
            pairs_beyond_sweep_limit=[],
            note="segment produced no graph nodes",
        )
        return result
    nodes = selection["nodes"]
    component_of = selection["component_of"]
    break_nodes = selection["break_nodes"]
    end_id_by_node = selection["end_id_by_node"]
    node_by_id = selection["node_by_end_id"]
    _, raw_pairs = _nearest_cross_component_pairs(
        break_nodes, nodes, component_of, end_id_by_node
    )

    covered: list[dict[str, Any]] = []
    beyond: list[dict[str, Any]] = []
    swept: list[dict[str, Any]] = []
    for pair in raw_pairs:
        separation = pair["separation_m"]
        record = {"end_ids": pair["end_ids"], "separation_m": round(separation, 3)}
        if separation <= minimum_separation_meters:
            covered.append(record)
            continue
        if separation > maximum_separation_meters:
            beyond.append(record)
            continue
        left_id, right_id = pair["end_ids"]
        from_metric = nodes[node_by_id[left_id]]
        to_metric = nodes[node_by_id[right_id]]
        chord = LineString([from_metric, to_metric])
        chord_bearing = math.degrees(
            math.atan2(to_metric[1] - from_metric[1], to_metric[0] - from_metric[0])
        )
        gap_id = f"{left_id}--{right_id}"
        windows: list[dict[str, Any]] = []
        own_locked_ids: set[int] = set()
        details_by_id: dict[int, dict[str, Any]] = {}
        for window_index, center in enumerate(
            _interior_window_centers(from_metric, to_metric, buffer_meters)
        ):
            envelope = _spatial_probe_envelope(center, center, inverse, buffer_meters)
            query = {
                "where": "1=1",
                "geometry": ",".join(f"{coordinate:.12f}" for coordinate in envelope),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
            acquisition = acquire_nhpn(
                transport,
                query_url,
                query,
                probe_root / segment_id / gap_id / f"window-{window_index:03d}",
                page_size=page_size,
            )
            center_longitude, center_latitude = inverse.transform(*center)
            windows.append(
                {
                    "index": window_index,
                    "center": {
                        "longitude": round(center_longitude, 7),
                        "latitude": round(center_latitude, 7),
                    },
                    "envelope_4326": [round(value, 7) for value in envelope],
                    "expected_count": acquisition.expected_count,
                    "object_ids_sha256": canonical_sha256(list(acquisition.object_ids)),
                    "features_sha256": canonical_sha256(list(acquisition.features)),
                    "retries": acquisition.retries,
                    "resumed_pages": acquisition.resumed_pages,
                }
            )
            for feature in acquisition.features:
                attributes = feature["attributes"]
                object_id = int(attributes["OBJECTID"])
                locked_under = locked_segments_by_object_id.get(object_id, ())
                if segment_id in locked_under:
                    own_locked_ids.add(object_id)
                    continue
                if object_id in details_by_id:
                    continue
                metric_parts = [
                    transform(forward.transform, LineString(coordinates))
                    for coordinates in feature.get("geometry", {}).get("paths", [])
                    if len(coordinates) >= 2
                ]
                metrics = _interior_feature_metrics(chord, chord_bearing, metric_parts)
                details_by_id[object_id] = {
                    "object_id": object_id,
                    "state_fips": str(attributes.get("STFIPS") or "").strip(),
                    "lrs_key": str(attributes.get("LRSKEY") or "").strip(),
                    "signed_routes": sorted(
                        f"{sign_type}-{sign_number}"
                        for sign_type, sign_number in _probe_sign_identities(attributes)
                    ),
                    "record_begin_milepost": attributes.get("BEGIN_POIN"),
                    "record_end_milepost": attributes.get("END_POINT"),
                    "locked_segment_ids": sorted(locked_under),
                    **metrics,
                    "classification": _interior_feature_tier(metrics),
                }
        details = sorted(
            details_by_id.values(),
            key=lambda item: (
                item["chord_distance_m"]
                if item["chord_distance_m"] is not None
                else float("inf"),
                item["object_id"],
            ),
        )
        tiers_present = {detail["classification"] for detail in details}
        summary = "interior_void_beyond_lock"
        for tier in _INTERIOR_TIER_ORDER:
            if tier in tiers_present:
                summary = _INTERIOR_SUMMARY_BY_TIER[tier]
                break
        from_longitude, from_latitude = inverse.transform(*from_metric)
        to_longitude, to_latitude = inverse.transform(*to_metric)
        swept.append(
            {
                "gap_id": gap_id,
                "end_ids": [left_id, right_id],
                "from_coordinate": {
                    "longitude": round(from_longitude, 7),
                    "latitude": round(from_latitude, 7),
                },
                "to_coordinate": {
                    "longitude": round(to_longitude, 7),
                    "latitude": round(to_latitude, 7),
                },
                "separation_m": round(separation, 3),
                "window_count": len(windows),
                "windows": windows,
                "own_locked_feature_count": len(own_locked_ids),
                "classification": summary,
                "classification_counts": {
                    tier: sum(1 for detail in details if detail["classification"] == tier)
                    for tier in _INTERIOR_TIER_ORDER
                    if tier in tiers_present
                },
                "on_axis_object_ids": sorted(
                    detail["object_id"]
                    for detail in details
                    if detail["classification"] == "aligned_on_axis"
                ),
                "features": details,
            }
        )

    result.update(
        break_end_ids=[end_id_by_node[node] for node in break_nodes],
        anchor_side_ends=selection["anchor_side_ends"],
        swept_gaps=swept,
        pairs_covered_by_break_end_windows=covered,
        pairs_beyond_sweep_limit=beyond,
    )
    return result


# --- NHS probes at the break sites and swept gap interiors (ADR-0026) ---------
#
# ADR-0026 adopts the NTAD National Highway System dataset as the supplementary
# corridor-geometry source where NHPN keys carry no records. These probes
# record what NHS asserts at the bounded break sites and inside the swept gap
# interiors - route identity, measures, and geometric continuity - as evidence
# for the Q-034 per-site disposition. They select nothing and change no lock.

NHS_SOURCE_ID = "usdot-ntad-national-highway-system"
NHS_QUERY_SUFFIX = "/query"
NHS_SERVICE_ITEM_ID = "dce9f09392eb474c8ad8e6a78416279b"

# Reporting lens for whether NHS geometry reaches a break end or spans a site.
# Grounded in the catalog's documented NHPN limitation: NHPN horizontal error
# can reach approximately 80 m, and the site endpoints are NHPN coordinates, so
# a tighter lens would report a false void wherever the two datasets merely
# disagree within their stated error. A lens is not a join: nothing is snapped,
# bridged, or selected at this distance.
NHS_PROXIMITY_LENS_METERS = 80.0


def _validate_nhs_service_metadata(metadata: dict[str, Any]) -> None:
    if metadata.get("id") != 0 or metadata.get("objectIdField") != "OBJECTID":
        raise ValueError("NHS service identity or object ID field changed.")
    if metadata.get("serviceItemId") != NHS_SERVICE_ITEM_ID:
        raise ValueError("NHS service item changed.")
    try:
        max_record_count = int(metadata.get("maxRecordCount", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("NHS service has no usable record limit.") from error
    if max_record_count < 1:
        raise ValueError("NHS service has no usable record limit.")
    editing_info = metadata.get("editingInfo")
    if not isinstance(editing_info, dict) or not isinstance(
        editing_info.get("dataLastEditDate"), int
    ):
        raise ValueError("NHS service no longer reports a data last edit date.")
    copyright_text = str(metadata.get("copyrightText", "")).lower()
    if (
        "work of the united states government" not in copyright_text
        or "unrestricted public use" not in copyright_text
    ):
        raise ValueError("NHS service no longer declares its public-domain status.")


def _require_nhs_query_url(source: CatalogSource) -> tuple[str, str]:
    """The catalog-approved NHS service and query URLs, allowlist-enforced."""
    service_url = str(source.raw.get("service_url", ""))
    query_url = service_url + NHS_QUERY_SUFFIX
    for url in (service_url, query_url):
        if not any(
            url_matches_prefix(url, prefix) for prefix in source.allowed_url_prefixes
        ):
            raise ValueError(f"NHS URL is outside the catalog allowlist: {url}")
    return service_url, query_url


def _nhs_feature_identity(attributes: dict[str, Any]) -> dict[str, Any]:
    """The NHS record fields the disposition needs: route identity and measures."""
    sign_type = str(attributes.get("SIGNT1") or "").strip()
    sign_number = str(attributes.get("SIGNN1") or "").strip()
    return {
        "object_id": int(attributes["OBJECTID"]),
        "state_fips": str(attributes.get("STFIPS") or "").strip(),
        "route_id": str(attributes.get("ROUTEID") or "").strip(),
        "signed_route": f"{sign_type}-{sign_number}" if sign_type and sign_number else "",
        "local_name": str(attributes.get("LNAME") or "").strip(),
        "nhs_component": attributes.get("NHS"),
        "status": attributes.get("STATUS"),
        "facility_type": str(attributes.get("FACILITYT") or "").strip(),
        "begin_point": attributes.get("BEGINPOINT"),
        "end_point": attributes.get("ENDPOINT"),
        "miles": attributes.get("MILES"),
        "year": attributes.get("YEAR"),
        "version": str(attributes.get("VERSION") or "").strip(),
        "update_date": str(attributes.get("UPDATE_DAT") or "").strip(),
    }


def _merge_value_spans(spans: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Union of numeric intervals, direction-insensitive."""
    ordered = sorted((min(low, high), max(low, high)) for low, high in spans)
    merged: list[list[float]] = []
    for low, high in ordered:
        if merged and low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return [(low, high) for low, high in merged]


def _classify_nhs_site(
    from_metric: tuple[float, float],
    to_metric: tuple[float, float],
    features: Sequence[dict[str, Any]],
    forward: Transformer,
    lens_meters: float = NHS_PROXIMITY_LENS_METERS,
) -> dict[str, Any]:
    """What NHS asserts between a site's two ends: identity, measures, geometry.

    ``spans_between_ends`` is a reporting lens - a single record whose geometry
    passes within the lens of both ends - and ``route_groups`` reconstructs each
    state route's measure coverage so the disposition can judge linear-reference
    continuity. Nothing here is a join, a selection, or a direction claim.
    """
    separation = math.dist(from_metric, to_metric)
    from_point = Point(from_metric)
    to_point = Point(to_metric)
    chord = LineString([from_metric, to_metric]) if separation > 0 else None
    chord_bearing = (
        math.degrees(
            math.atan2(to_metric[1] - from_metric[1], to_metric[0] - from_metric[0])
        )
        if separation >= 1.0
        else None
    )
    details: list[dict[str, Any]] = []
    for feature in features:
        identity = _nhs_feature_identity(feature["attributes"])
        metric_parts = [
            transform(forward.transform, LineString(coordinates))
            for coordinates in feature.get("geometry", {}).get("paths", [])
            if len(coordinates) >= 2
        ]
        if not metric_parts:
            details.append(
                {
                    **identity,
                    "distance_to_from_end_m": None,
                    "distance_to_to_end_m": None,
                    "alignment_degrees": None,
                    "spans_between_ends": False,
                }
            )
            continue
        distance_from = min(part.distance(from_point) for part in metric_parts)
        distance_to = min(part.distance(to_point) for part in metric_parts)
        alignment: float | None = None
        if chord is not None and chord_bearing is not None:
            best_part = min(metric_parts, key=lambda part: part.distance(chord))
            _, on_part = nearest_points(chord, best_part)
            feature_bearing = _chord_bearing(best_part, best_part.project(on_part))
            if feature_bearing is not None:
                alignment = _acute_angle_degrees(chord_bearing, feature_bearing)
        details.append(
            {
                **identity,
                "distance_to_from_end_m": round(distance_from, 3),
                "distance_to_to_end_m": round(distance_to, 3),
                "alignment_degrees": None if alignment is None else round(alignment, 1),
                "spans_between_ends": distance_from <= lens_meters
                and distance_to <= lens_meters,
            }
        )
    details.sort(
        key=lambda item: (
            min(
                value
                for value in (
                    item["distance_to_from_end_m"],
                    item["distance_to_to_end_m"],
                    float("inf"),
                )
                if value is not None
            ),
            item["object_id"],
        )
    )

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for detail in details:
        groups.setdefault((detail["state_fips"], detail["route_id"]), []).append(detail)
    route_groups: list[dict[str, Any]] = []
    for (state_fips, route_id), members in sorted(groups.items()):
        measure_spans = _merge_value_spans(
            [
                (float(member["begin_point"]), float(member["end_point"]))
                for member in members
                if member["begin_point"] is not None and member["end_point"] is not None
            ]
        )
        largest_gap = max(
            (
                second[0] - first[1]
                for first, second in zip(measure_spans, measure_spans[1:], strict=False)
            ),
            default=0.0,
        )
        near_from = any(
            member["distance_to_from_end_m"] is not None
            and member["distance_to_from_end_m"] <= lens_meters
            for member in members
        )
        near_to = any(
            member["distance_to_to_end_m"] is not None
            and member["distance_to_to_end_m"] <= lens_meters
            for member in members
        )
        route_groups.append(
            {
                "state_fips": state_fips,
                "route_id": route_id,
                "feature_count": len(members),
                "signed_routes": sorted(
                    {member["signed_route"] for member in members if member["signed_route"]}
                ),
                "near_from_end": near_from,
                "near_to_end": near_to,
                "geometry_near_both_ends": near_from and near_to,
                "measure_spans": [
                    [round(low, 3), round(high, 3)] for low, high in measure_spans
                ],
                "largest_measure_gap_miles": round(largest_gap, 3),
            }
        )
    spanning_ids = sorted(
        detail["object_id"] for detail in details if detail["spans_between_ends"]
    )
    return {
        "proximity_lens_m": lens_meters,
        "feature_count": len(details),
        "features_spanning_between_ends": spanning_ids,
        "nhs_carries_between_ends": bool(spanning_ids)
        or any(group["geometry_near_both_ends"] for group in route_groups),
        "route_groups": route_groups,
        "features": details,
    }


def _nhs_probe_finding(
    sites: Sequence[dict[str, Any]], interior_gaps: Sequence[dict[str, Any]]
) -> str:
    """Describe the NHS probe using the numbers it actually produced."""
    if not sites and not interior_gaps:
        return "No break sites or gap interiors were probed against NHS."
    carrying = sum(1 for site in sites if site["nhs"]["nhs_carries_between_ends"])
    empty = sum(1 for site in sites if site["nhs"]["feature_count"] == 0)
    interior_carrying = sum(
        1 for gap in interior_gaps if gap["nhs"]["nhs_carries_between_ends"]
    )
    return (
        f"NHS was probed at {len(sites)} bounded break sites and across "
        f"{len(interior_gaps)} swept gap interiors. {carrying} sites and "
        f"{interior_carrying} interiors have NHS geometry within the "
        f"{NHS_PROXIMITY_LENS_METERS:g} m lens of both ends, and {empty} sites "
        "returned no NHS features at all. The lens is a reporting device over "
        "two datasets' stated horizontal error, not a snap, join, or selection: "
        "these are ADR-0026 supplementary-source facts for the Q-034 "
        "disposition, no direction or distance is claimed, and no lock is "
        "changed."
    )


def probe_continental_nhs_breaks(
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    probe_cache_directory: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    expected_metadata_sha256: str | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
    padding_meters: float = GEOMETRIC_PROBE_PADDING_METERS,
    buffer_meters: float = BREAK_PROBE_BUFFER_METERS,
    minimum_interior_separation_meters: float = INTERIOR_SWEEP_MINIMUM_SEPARATION_METERS,
    maximum_interior_separation_meters: float = INTERIOR_SWEEP_MAXIMUM_SEPARATION_METERS,
) -> dict[str, Any]:
    """Probe what NHS asserts at every bounded break site and swept interior.

    ADR-0026 adopts NTAD NHS as the supplementary corridor-geometry source;
    this records its evidence at the exact places the NHPN probes found wanting:
    the 14 bounded break sites and the break-pair interiors wider than the
    census windows. Acquisition mirrors the NHPN discipline exactly - paging,
    checkpoints, page hashes, retry limits - against the catalog-approved
    service URL only. It refuses a service whose identity or public-domain
    declaration changed, and, when an expected metadata hash is supplied, one
    that has drifted from it. Responses stay in the ignored cache; nothing is
    selected and no lock changes.
    """
    # Catalog and service gates come first so a refusal cannot depend on the
    # locked response cache being present.
    catalog = load_catalog(catalog_path)
    if NHS_SOURCE_ID not in catalog:
        raise ValueError("NHS is not in the approved source catalog.")
    source = catalog[NHS_SOURCE_ID]
    service_url, query_url = _require_nhs_query_url(source)
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_nhs_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    if (
        expected_metadata_sha256 is not None
        and service_metadata_sha256 != expected_metadata_sha256
    ):
        raise ValueError(
            "Live NHS service metadata has drifted from the expected snapshot; a "
            "probe against it would characterise a different dataset than the one "
            "the disposition evidence names."
        )
    max_record_count = int(service_metadata["maxRecordCount"])
    if page_size > max_record_count:
        raise ValueError(
            f"NHS page size {page_size} exceeds the live service limit of "
            f"{max_record_count}."
        )

    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )

    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    edge_by_id = {entry["segment_id"]: entry for entry in edge_lock["segments"]}
    cache_root = cache_directory / route_lock["nhpn"]["service"][
        "canonical_metadata_sha256"
    ]
    probe_root = probe_cache_directory / service_metadata_sha256
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])

    sites: list[dict[str, Any]] = []
    interior_pairs: list[dict[str, Any]] = []
    for segment in selection["segments"]:
        segment_id = segment["id"]
        edge_entry = edge_by_id.get(segment_id)
        if edge_entry is None or edge_entry.get("connected"):
            continue
        lines = _segment_locked_lines(route_lock, segment_id, cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )

        def metric_point(node_id: str) -> tuple[float, float]:
            coordinate = transfer_by_id[node_id]["coordinate"]
            return forward.transform(coordinate["longitude"], coordinate["latitude"])

        from_point = metric_point(segment["from"])
        to_point = metric_point(segment["to"])
        reproduced = _solve_segment_edge_path(
            segment,
            metric_lines,
            from_point,
            to_point,
            tolerance,
        )
        if canonical_sha256(reproduced) != canonical_sha256(edge_entry):
            raise ValueError(
                f"Locked cache no longer reproduces edge-path diagnostics for "
                f"'{segment_id}'."
            )
        sites.extend(
            _derive_segment_geometric_probe_sites(
                segment_id,
                metric_lines,
                from_point,
                to_point,
                tolerance,
                edge_lock["anchor_snap_limit_m"],
            )
        )
        break_selection = _select_break_ends(
            metric_lines, from_point, to_point, tolerance, inverse
        )
        if break_selection is None:
            continue
        _, raw_pairs = _nearest_cross_component_pairs(
            break_selection["break_nodes"],
            break_selection["nodes"],
            break_selection["component_of"],
            break_selection["end_id_by_node"],
        )
        for pair in raw_pairs:
            if not (
                minimum_interior_separation_meters
                < pair["separation_m"]
                <= maximum_interior_separation_meters
            ):
                continue
            node_by_id = break_selection["node_by_end_id"]
            left_id, right_id = pair["end_ids"]
            interior_pairs.append(
                {
                    "segment_id": segment_id,
                    "gap_id": f"{left_id}--{right_id}",
                    "end_ids": pair["end_ids"],
                    "from_metric": break_selection["nodes"][node_by_id[left_id]],
                    "to_metric": break_selection["nodes"][node_by_id[right_id]],
                    "separation_m": pair["separation_m"],
                }
            )

    site_results: list[dict[str, Any]] = []
    for site in sorted(sites, key=lambda entry: entry["site_id"]):
        envelope = _spatial_probe_envelope(
            site["from_metric"], site["to_metric"], inverse, padding_meters
        )
        query = {
            "where": "1=1",
            "geometry": ",".join(f"{coordinate:.12f}" for coordinate in envelope),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        }
        acquisition = acquire_nhpn(
            transport,
            query_url,
            query,
            probe_root / "sites" / site["site_id"],
            page_size=page_size,
        )
        classification = _classify_nhs_site(
            site["from_metric"], site["to_metric"], acquisition.features, forward
        )
        from_longitude, from_latitude = inverse.transform(*site["from_metric"])
        to_longitude, to_latitude = inverse.transform(*site["to_metric"])
        site_results.append(
            {
                "site_id": site["site_id"],
                "segment_id": site["segment_id"],
                "kind": site["kind"],
                "from_coordinate": {
                    "longitude": round(from_longitude, 12),
                    "latitude": round(from_latitude, 12),
                },
                "to_coordinate": {
                    "longitude": round(to_longitude, 12),
                    "latitude": round(to_latitude, 12),
                },
                "separation_m": round(site["separation_m"], 3),
                "envelope_4326": [round(value, 7) for value in envelope],
                "probe": {
                    "expected_count": acquisition.expected_count,
                    "object_ids_sha256": canonical_sha256(list(acquisition.object_ids)),
                    "features_sha256": canonical_sha256(list(acquisition.features)),
                    "retries": acquisition.retries,
                    "resumed_pages": acquisition.resumed_pages,
                },
                "nhs": classification,
            }
        )

    interior_results: list[dict[str, Any]] = []
    for pair in sorted(interior_pairs, key=lambda entry: (entry["segment_id"], entry["gap_id"])):
        windows: list[dict[str, Any]] = []
        features_by_id: dict[int, dict[str, Any]] = {}
        for window_index, center in enumerate(
            _interior_window_centers(pair["from_metric"], pair["to_metric"], buffer_meters)
        ):
            envelope = _spatial_probe_envelope(center, center, inverse, buffer_meters)
            query = {
                "where": "1=1",
                "geometry": ",".join(f"{coordinate:.12f}" for coordinate in envelope),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
            acquisition = acquire_nhpn(
                transport,
                query_url,
                query,
                probe_root
                / "interiors"
                / pair["segment_id"]
                / pair["gap_id"]
                / f"window-{window_index:03d}",
                page_size=page_size,
            )
            windows.append(
                {
                    "index": window_index,
                    "envelope_4326": [round(value, 7) for value in envelope],
                    "expected_count": acquisition.expected_count,
                    "object_ids_sha256": canonical_sha256(list(acquisition.object_ids)),
                    "features_sha256": canonical_sha256(list(acquisition.features)),
                    "retries": acquisition.retries,
                    "resumed_pages": acquisition.resumed_pages,
                }
            )
            for feature in acquisition.features:
                object_id = int(feature["attributes"]["OBJECTID"])
                features_by_id.setdefault(object_id, feature)
        classification = _classify_nhs_site(
            pair["from_metric"],
            pair["to_metric"],
            [features_by_id[key] for key in sorted(features_by_id)],
            forward,
        )
        interior_results.append(
            {
                "segment_id": pair["segment_id"],
                "gap_id": pair["gap_id"],
                "end_ids": pair["end_ids"],
                "separation_m": round(pair["separation_m"], 3),
                "window_count": len(windows),
                "windows": windows,
                "nhs": classification,
            }
        )

    return {
        "schema_version": 1,
        "status": (
            "diagnostic acquisition; records what the ADR-0026 supplementary NHS "
            "source asserts at the bounded break sites and swept gap interiors; "
            "no bridging decided and no lock changed"
        ),
        "acquired_at": timestamp,
        "query_url": query_url,
        "probe_padding_meters": padding_meters,
        "buffer_meters": buffer_meters,
        "proximity_lens_m": NHS_PROXIMITY_LENS_METERS,
        "endpoint_snap_tolerance_m": tolerance,
        "service": {
            "source_id": NHS_SOURCE_ID,
            "item_id": service_metadata["serviceItemId"],
            "canonical_metadata_sha256": service_metadata_sha256,
            "data_last_edit_epoch_ms": service_metadata["editingInfo"]["dataLastEditDate"],
            "copyright_text": service_metadata.get("copyrightText", ""),
        },
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "source_policy": {
            "supplementary_source": NHS_SOURCE_ID,
            "nhs_role": "supplementary_centerlines_only",
            "nhpn_remains_route_authority": True,
            "openstreetmap_ancestry_allowed": False,
            "probe_is_selected_route_geometry": False,
            "continental_downloads_committed": False,
            "bridging_decided": False,
        },
        "site_count": len(site_results),
        "interior_gap_count": len(interior_results),
        "sites_with_nhs_between_ends": sum(
            1 for site in site_results if site["nhs"]["nhs_carries_between_ends"]
        ),
        "finding": _nhs_probe_finding(site_results, interior_results),
        "sites": site_results,
        "interior_gaps": interior_results,
    }


# --- ADR-0026 NHS fill acquisition lock -----------------------------------------
#
# The disposition record's nhs_fill sites name corridor voids that NHPN cannot
# carry and NHS demonstrably does. The fill lock acquires those NHS records
# under the catalog entry with the exact NHPN acquisition discipline and pins
# them beside the NHPN chain: NHPN stays the route-family authority and the
# topology backbone; NHS supplies centerlines across the named voids only.
# Geometry conflation is later pipeline work (ADR-0026); nothing here selects a
# direction or claims an authoritative distance.

NHS_FILL_LOCK_STATUS = "nhs_fills_locked_conflation_pending"
NHS_FILL_NEXT_STAGE = {
    "id": "nhpn-nhs-conflation-and-reconstruction",
    "requires": [
        "NHPN-to-NHS conflation model over the locked fill spans",
        "3DEP product lock over the chained corridor",
    ],
}
NHS_FILL_SOURCE_POLICY = {
    "supplementary_source": NHS_SOURCE_ID,
    "nhs_role": "supplementary_centerlines_only",
    "nhpn_remains_route_authority": True,
    "openstreetmap_ancestry_allowed": False,
    "lane_geometry_claimed": False,
    "authoritative_distance_claimed": False,
    "continental_downloads_committed": False,
    "conflation_performed": False,
}


def _fill_route_groups(
    classification: dict[str, Any], facility: str
) -> list[dict[str, Any]]:
    """The NHS route groups that actually carry the declared facility across a site.

    A qualifying group has geometry within the lens of both ends, a zero
    state-LRS measure gap, and the segment's declared facility among its signed
    routes. The member records keep the fields ADR-0026 requires a lock to
    record (YEAR, VERSION, UPDATE_DAT) plus their measures.
    """
    groups: list[dict[str, Any]] = []
    for group in classification["route_groups"]:
        if not group["geometry_near_both_ends"]:
            continue
        if group["largest_measure_gap_miles"] != 0.0:
            continue
        if facility not in group["signed_routes"]:
            continue
        members = [
            {
                "object_id": feature["object_id"],
                "signed_route": feature["signed_route"],
                "begin_point": feature["begin_point"],
                "end_point": feature["end_point"],
                "miles": feature["miles"],
                "year": feature["year"],
                "version": feature["version"],
                "update_date": feature["update_date"],
            }
            for feature in classification["features"]
            if feature["state_fips"] == group["state_fips"]
            and feature["route_id"] == group["route_id"]
        ]
        groups.append(
            {
                "state_fips": group["state_fips"],
                "route_id": group["route_id"],
                "signed_routes": group["signed_routes"],
                "feature_count": group["feature_count"],
                "measure_spans": group["measure_spans"],
                "largest_measure_gap_miles": group["largest_measure_gap_miles"],
                "records": members,
            }
        )
    return groups


def _chain_connectivity_with_fills(
    route_lock: dict[str, Any],
    selection: dict[str, Any],
    transfer_lock: dict[str, Any],
    edge_lock: dict[str, Any],
    fill_sites: Sequence[dict[str, Any]],
    disposition_sites: Sequence[dict[str, Any]],
    cache_root: Path,
    forward: Transformer,
    overlay_sites: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Whether each unconnected segment chains end-to-end once fills bridge it.

    Rebuilds each segment's snapped NHPN graph from the revised candidate lock,
    adds one bridge edge per locked NHS fill between the exact break-end
    coordinates the disposition pinned (each must land on an existing graph node
    within the unchanged endpoint tolerance), and tests anchor-to-anchor
    connectivity under the unchanged anchor snap limit, resolving an on-edge
    anchor through the same Q-034c/d edge-split fallback the edge-path solve
    uses. When authored ADR-0018 overlay sites are supplied, each bridges its
    pinned exception boundary the same way a fill does. A chained segment is a
    mixed-ancestry chain, not an NHPN path and not a westbound selection; fill
    and overlay spans contribute their chord length only, so no authoritative
    distance is claimed.
    """
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])
    anchor_limit = float(edge_lock["anchor_snap_limit_m"])
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    segment_by_id = {segment["id"]: segment for segment in selection["segments"]}
    fills_by_segment: dict[str, list[dict[str, Any]]] = {}
    for site in fill_sites:
        fills_by_segment.setdefault(site["segment_id"], []).append(site)
    overlays_by_segment: dict[str, list[dict[str, Any]]] = {}
    overlay_site_ids = set()
    for overlay in overlay_sites:
        overlays_by_segment.setdefault(overlay["segment_id"], []).append(overlay)
        overlay_site_ids.add(overlay["site_id"])
    blockers_by_segment: dict[str, list[dict[str, Any]]] = {}
    for site in disposition_sites:
        # A disposition the lock revision has implemented no longer blocks the
        # chain: scoped acquisitions are in the candidate lock, fills are the
        # bridges themselves, an anchor edge split is applied by the anchor
        # resolution below, and a bounded exception stops blocking once its
        # authored overlay is among the supplied bridges.
        if site.get("disposition") in {
            "nhs_fill",
            "nhpn_scoped_acquisition",
            "anchor_edge_split",
        }:
            continue
        if (
            site.get("disposition") == "bounded_reconstruction_exception"
            and site.get("site_id") in overlay_site_ids
        ):
            continue
        blocker = {
            "site_id": site["site_id"],
            "disposition": site["disposition"],
        }
        if site.get("q034_subitem"):
            blocker["q034_subitem"] = site["q034_subitem"]
        blockers_by_segment.setdefault(site["segment_id"], []).append(blocker)

    results: list[dict[str, Any]] = []
    for entry in sorted(
        (entry for entry in edge_lock["segments"] if not entry.get("connected")),
        key=lambda entry: entry["segment_id"],
    ):
        segment_id = entry["segment_id"]
        segment = segment_by_id[segment_id]
        lines = _segment_locked_lines(route_lock, segment_id, cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )
        graph, nodes, _, _ = _build_snapped_endpoint_graph(metric_lines, tolerance)

        def nearest_node(
            point: tuple[float, float],
            nodes: dict[tuple[int, int], tuple[float, float]] = nodes,
        ) -> tuple[tuple[int, int], float]:
            best_key, best_distance = None, float("inf")
            for key in sorted(nodes):
                distance = math.dist(point, nodes[key])
                if distance < best_distance:
                    best_key, best_distance = key, distance
            assert best_key is not None
            return best_key, best_distance

        def bridge(
            site: dict[str, Any],
            kind: str,
            data_key: str,
            graph: nx.MultiGraph = graph,
            nearest_node: Callable[
                [tuple[float, float]], tuple[tuple[int, int], float]
            ] = nearest_node,
        ) -> None:
            ends = []
            for corner in ("from_coordinate", "to_coordinate"):
                point = forward.transform(
                    site[corner]["longitude"], site[corner]["latitude"]
                )
                node, distance = nearest_node(point)
                if distance > tolerance:
                    raise ValueError(
                        f"{kind} '{site['site_id']}' {corner} does not land on a "
                        f"locked chain end within the {tolerance:g} m tolerance "
                        f"(nearest node is {distance:.3f} m away)."
                    )
                ends.append(node)
            graph.add_edge(
                ends[0],
                ends[1],
                key=(data_key, site["site_id"]),
                weight=float(site["separation_m"]),
                **{f"{data_key}_site_id": site["site_id"]},
            )

        for site in sorted(
            fills_by_segment.get(segment_id, []), key=lambda site: site["site_id"]
        ):
            bridge(site, "NHS fill", "fill")
        for site in sorted(
            overlays_by_segment.get(segment_id, []), key=lambda site: site["site_id"]
        ):
            bridge(site, "Authored overlay", "overlay")

        blockers = [dict(blocker) for blocker in blockers_by_segment.get(segment_id, [])]
        from_point = (
            transfer_by_id[segment["from"]]["coordinate"]["longitude"],
            transfer_by_id[segment["from"]]["coordinate"]["latitude"],
        )
        to_point = (
            transfer_by_id[segment["to"]]["coordinate"]["longitude"],
            transfer_by_id[segment["to"]]["coordinate"]["latitude"],
        )
        splits: list[dict[str, Any]] = []
        from_key, from_distance, from_split = _resolve_anchor_node(
            graph, nodes, metric_lines, forward.transform(*from_point), "from",
            tolerance, anchor_limit,
        )
        if from_split is not None:
            splits.append(from_split)
        to_key, to_distance, to_split = _resolve_anchor_node(
            graph, nodes, metric_lines, forward.transform(*to_point), "to",
            tolerance, anchor_limit,
        )
        if to_split is not None:
            splits.append(to_split)
        for side, distance in (("from", from_distance), ("to", to_distance)):
            if distance > anchor_limit:
                blockers.append(
                    {
                        "kind": "anchor_beyond_snap_limit",
                        "side": side,
                        "distance_m": round(distance, 3),
                    }
                )
        connected = (
            max(from_distance, to_distance) <= anchor_limit
            and from_key != to_key
            and nx.has_path(graph, from_key, to_key)
        )
        result: dict[str, Any] = {
            "segment_id": segment_id,
            "fill_bridge_count": len(fills_by_segment.get(segment_id, [])),
            "overlay_bridge_count": len(overlays_by_segment.get(segment_id, [])),
            "from_anchor_snap_distance_m": round(from_distance, 3),
            "to_anchor_snap_distance_m": round(to_distance, 3),
            "chain_connected_with_fills": connected,
            "remaining_blockers": blockers,
        }
        if splits:
            result["anchor_edge_splits"] = splits
        if connected:
            node_path = nx.shortest_path(graph, from_key, to_key, weight="weight")
            nhpn_meters = 0.0
            fill_meters = 0.0
            overlay_meters = 0.0
            fill_site_ids: list[str] = []
            overlay_ids: list[str] = []
            for previous, current in zip(node_path, node_path[1:], strict=False):
                parallel = graph.get_edge_data(previous, current)
                chosen_key = min(
                    parallel,
                    key=lambda edge_key: (parallel[edge_key]["weight"], str(edge_key)),
                )
                data = parallel[chosen_key]
                if "fill_site_id" in data:
                    fill_meters += data["weight"]
                    fill_site_ids.append(data["fill_site_id"])
                elif "overlay_site_id" in data:
                    overlay_meters += data["weight"]
                    overlay_ids.append(data["overlay_site_id"])
                else:
                    nhpn_meters += data["weight"]
            result.update(
                nhpn_path_meters=round(nhpn_meters, 3),
                fill_chord_meters=round(fill_meters, 3),
                overlay_chord_meters=round(overlay_meters, 3),
                chain_length_meters=round(
                    nhpn_meters + fill_meters + overlay_meters, 3
                ),
                fill_site_ids_on_chain=sorted(fill_site_ids),
                overlay_site_ids_on_chain=sorted(overlay_ids),
            )
        results.append(result)
    return results


def acquire_continental_nhs_fill_lock(
    disposition_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    fill_cache_directory: Path,
    output_path: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    expected_metadata_sha256: str | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
    padding_meters: float = GEOMETRIC_PROBE_PADDING_METERS,
) -> dict[str, Any]:
    """Acquire and lock the NHS records for every nhs_fill disposition site.

    Follows the exact catalog and acquisition discipline of the NHPN lock:
    catalog URL-allowlist enforcement, service identity and public-domain
    validation, optional expected-metadata drift refusal, paging, checkpoints,
    page hashes, and SHA-256 at ingest. Records the NHPN/NHS dual ancestry
    ADR-0026 requires and each record's YEAR, VERSION, and UPDATE_DAT fields.
    Responses stay in the ignored cache; no geometry is conflated, no direction
    is selected, and no authoritative distance is claimed.
    """
    catalog = load_catalog(catalog_path)
    if NHS_SOURCE_ID not in catalog:
        raise ValueError("NHS is not in the approved source catalog.")
    source = catalog[NHS_SOURCE_ID]
    service_url, query_url = _require_nhs_query_url(source)
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_nhs_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    if (
        expected_metadata_sha256 is not None
        and service_metadata_sha256 != expected_metadata_sha256
    ):
        raise ValueError(
            "Live NHS service metadata has drifted from the expected snapshot; an "
            "acquisition against it would lock a different dataset than the one "
            "the disposition evidence names."
        )
    max_record_count = int(service_metadata["maxRecordCount"])
    if page_size > max_record_count:
        raise ValueError(
            f"NHS page size {page_size} exceeds the live service limit of "
            f"{max_record_count}."
        )

    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    disposition = load_json(disposition_path)
    if disposition.get("schema_version") != 1 or disposition.get("open_question") != "Q-034":
        raise ValueError("NHS fill acquisition requires the Q-034 disposition record.")
    disposition_sites = disposition.get("sites", [])
    fill_dispositions = [
        site for site in disposition_sites if site.get("disposition") == "nhs_fill"
    ]
    if not fill_dispositions:
        raise ValueError("The disposition record names no NHS fill sites.")
    # A fill may name a segment the revised candidate lock has since connected
    # (a scoped acquisition can close a segment whose fragment span still has a
    # recorded fill): the fill then records what NHS asserts across the span,
    # while chain connectivity below covers only the still-unconnected segments.
    locked_segment_ids = {entry["segment_id"] for entry in edge_lock["segments"]}
    segment_by_id = {segment["id"]: segment for segment in selection["segments"]}

    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    fill_root = fill_cache_directory / service_metadata_sha256
    cache_root = cache_directory / route_lock["nhpn"]["service"][
        "canonical_metadata_sha256"
    ]

    sites: list[dict[str, Any]] = []
    for site in sorted(fill_dispositions, key=lambda entry: str(entry.get("site_id", ""))):
        site_id = str(site.get("site_id", ""))
        segment_id = site.get("segment_id")
        if segment_id not in locked_segment_ids or not site_id.startswith(f"{segment_id}--"):
            raise ValueError(
                f"NHS fill site '{site_id}' is not scoped to a locked segment."
            )
        facility = segment_by_id[segment_id]["facility_sequence"][0]
        from_metric = forward.transform(
            site["from_coordinate"]["longitude"], site["from_coordinate"]["latitude"]
        )
        to_metric = forward.transform(
            site["to_coordinate"]["longitude"], site["to_coordinate"]["latitude"]
        )
        envelope = _spatial_probe_envelope(from_metric, to_metric, inverse, padding_meters)
        result = acquire_nhpn(
            transport,
            query_url,
            {
                "where": "1=1",
                "geometry": ",".join(f"{coordinate:.12f}" for coordinate in envelope),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
            fill_root / site_id,
            page_size=page_size,
        )
        classification = _classify_nhs_site(
            from_metric, to_metric, result.features, forward
        )
        fill_groups = _fill_route_groups(classification, facility)
        if not classification["nhs_carries_between_ends"] or not fill_groups:
            raise ValueError(
                f"NHS fill site '{site_id}' has no continuous {facility} NHS route "
                "between its ends; the disposition evidence no longer holds."
            )
        sites.append(
            {
                "site_id": site_id,
                "segment_id": segment_id,
                "facility": facility,
                "from_coordinate": site["from_coordinate"],
                "to_coordinate": site["to_coordinate"],
                "separation_m": site["separation_m"],
                "envelope_4326": [round(value, 7) for value in envelope],
                "acquired_at": timestamp,
                "page_size": page_size,
                "expected_count": result.expected_count,
                "object_ids": list(result.object_ids),
                "object_ids_sha256": canonical_sha256(list(result.object_ids)),
                "features_sha256": canonical_sha256(list(result.features)),
                "pages": _page_records(result, fill_root / site_id, page_size),
                "retries": result.retries,
                "resumed_pages": result.resumed_pages,
                "proximity_lens_m": classification["proximity_lens_m"],
                "nhs_carries_between_ends": True,
                "fill_route_groups": fill_groups,
            }
        )

    chain = _chain_connectivity_with_fills(
        route_lock,
        selection,
        transfer_lock,
        edge_lock,
        sites,
        disposition_sites,
        cache_root,
        forward,
    )
    payload = {
        "schema_version": 1,
        "status": NHS_FILL_LOCK_STATUS,
        "decision": selection["decision"],
        "open_question": "Q-034",
        "acquired_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs": {
            "source_id": NHS_SOURCE_ID,
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
        },
        "ancestry": {
            "nhpn_backbone": {
                "source_id": NHPN_SOURCE_ID,
                "role": (
                    "route-family and topology backbone; authority for which "
                    "facilities are on the route"
                ),
                "candidate_lock_sha256": compute_sha256(route_lock_path),
            },
            "nhs_centerlines": {
                "source_id": NHS_SOURCE_ID,
                "role": (
                    "supplementary corridor centerlines and state-LRS milepoints "
                    "across the named NHPN voids only"
                ),
                "decision": "ADR-0026",
            },
        },
        "source_policy": dict(NHS_FILL_SOURCE_POLICY),
        "proximity_lens_m": NHS_PROXIMITY_LENS_METERS,
        "probe_padding_meters": padding_meters,
        "endpoint_snap_tolerance_m": edge_lock["endpoint_snap_tolerance_m"],
        "anchor_snap_limit_m": edge_lock["anchor_snap_limit_m"],
        "westbound_selection_validated": False,
        "site_count": len(sites),
        "sites": sites,
        "sites_sha256": canonical_sha256(sites),
        "chain_connectivity": {
            "note": (
                "Anchor-to-anchor connectivity of each unconnected segment once "
                "every locked NHS fill bridges its pinned break ends. A chained "
                "segment is a mixed-ancestry chain (NHPN backbone plus NHS fill "
                "chords), not an NHPN path, not a westbound selection, and not an "
                "authoritative distance."
            ),
            "chained_segment_count": sum(
                1 for entry in chain if entry["chain_connected_with_fills"]
            ),
            "unchained_segment_count": sum(
                1 for entry in chain if not entry["chain_connected_with_fills"]
            ),
            "segments": chain,
        },
        "chain_connectivity_sha256": canonical_sha256(chain),
        "next_stage": NHS_FILL_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_continental_nhs_fill_lock(
    fill_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the NHS fill lock without requiring the ignored response caches."""
    payload = load_json(fill_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported NHS fill lock schema.")
    if payload.get("status") != NHS_FILL_LOCK_STATUS:
        raise ValueError("NHS fill lock has an unsupported status.")
    if payload.get("open_question") != "Q-034":
        raise ValueError("NHS fill lock does not cite Q-034.")
    if payload.get("westbound_selection_validated") is not False:
        raise ValueError(
            "NHS fill lock claims a validated westbound selection, which this "
            "stage cannot establish."
        )
    selection = load_json(selection_path)
    if payload.get("decision") != selection.get("decision"):
        raise ValueError("NHS fill lock decision does not match the route selection.")
    validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("NHS fill lock input hash drifted.")
    catalog = load_catalog(catalog_path)
    nhs = payload.get("nhs", {})
    source = require_catalog_source(
        catalog,
        source_id=nhs.get("source_id", ""),
        publisher=nhs.get("publisher", ""),
        license_status=nhs.get("license_status", ""),
        source_url=nhs.get("service_url", ""),
        license_evidence_url=nhs.get("license_evidence_url", ""),
    )
    expected_service_url, expected_query_url = _require_nhs_query_url(source)
    if (
        nhs.get("service_url") != expected_service_url
        or nhs.get("query_url") != expected_query_url
    ):
        raise ValueError("NHS fill lock query URL drifted from the catalog allowlist.")
    service = nhs.get("service", {})
    if (
        service.get("item_id") != NHS_SERVICE_ITEM_ID
        or service.get("layer_id") != 0
        or service.get("object_id_field") != "OBJECTID"
    ):
        raise ValueError("NHS fill lock service identity drifted.")
    max_record_count = int(service.get("max_record_count", 0))
    if (
        max_record_count < 1
        or not isinstance(service.get("data_last_edit_epoch_ms"), int)
        or not SHA256_PATTERN.fullmatch(service.get("canonical_metadata_sha256", ""))
    ):
        raise ValueError("NHS fill lock service metadata is incomplete.")
    ancestry = payload.get("ancestry", {})
    backbone = ancestry.get("nhpn_backbone", {})
    centerlines = ancestry.get("nhs_centerlines", {})
    if (
        backbone.get("source_id") != NHPN_SOURCE_ID
        or backbone.get("candidate_lock_sha256") != compute_sha256(route_lock_path)
        or centerlines.get("source_id") != NHS_SOURCE_ID
        or centerlines.get("decision") != "ADR-0026"
    ):
        raise ValueError("NHS fill lock does not record the ADR-0026 dual ancestry.")
    if payload.get("source_policy") != NHS_FILL_SOURCE_POLICY:
        raise ValueError("NHS fill lock source policy is incomplete.")
    if payload.get("endpoint_snap_tolerance_m") != edge_lock["endpoint_snap_tolerance_m"]:
        raise ValueError("NHS fill lock declares a drifted endpoint snap tolerance.")
    if payload.get("anchor_snap_limit_m") != edge_lock["anchor_snap_limit_m"]:
        raise ValueError("NHS fill lock declares a drifted anchor snap limit.")

    unconnected_ids = {
        entry["segment_id"] for entry in edge_lock["segments"] if not entry.get("connected")
    }
    locked_segment_ids = {entry["segment_id"] for entry in edge_lock["segments"]}
    segment_by_id = {segment["id"]: segment for segment in selection["segments"]}
    sites = payload.get("sites")
    if not isinstance(sites, list) or not sites:
        raise ValueError("NHS fill lock records no sites.")
    if payload.get("site_count") != len(sites):
        raise ValueError("NHS fill lock site count does not reconcile.")
    if canonical_sha256(sites) != payload.get("sites_sha256"):
        raise ValueError("NHS fill lock site digest drifted.")
    site_ids: set[str] = set()
    for site in sites:
        site_id = _require_nonempty_string(
            site.get("site_id"), "NHS fill site has no site ID."
        )
        if site_id in site_ids:
            raise ValueError(f"NHS fill lock repeats site '{site_id}'.")
        site_ids.add(site_id)
        segment_id = site.get("segment_id")
        if segment_id not in locked_segment_ids or not site_id.startswith(f"{segment_id}--"):
            raise ValueError(
                f"NHS fill site '{site_id}' is not scoped to a locked segment."
            )
        facility = site.get("facility")
        if facility != segment_by_id[segment_id]["facility_sequence"][0]:
            raise ValueError(f"NHS fill site '{site_id}' facility drifted.")
        for corner in ("from_coordinate", "to_coordinate"):
            _require_conus_coordinate(
                site.get(corner), f"NHS fill site '{site_id}' coordinate is invalid."
            )
        separation = site.get("separation_m")
        if (
            not isinstance(separation, int | float)
            or isinstance(separation, bool)
            or not math.isfinite(separation)
            or separation <= 0
        ):
            raise ValueError(f"NHS fill site '{site_id}' has an invalid separation.")
        _validate_acquisition_record(site, f"NHS fill '{site_id}'", max_record_count)
        if site.get("nhs_carries_between_ends") is not True:
            raise ValueError(
                f"NHS fill site '{site_id}' does not assert NHS carries between ends."
            )
        groups = site.get("fill_route_groups")
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"NHS fill site '{site_id}' records no fill route group.")
        acquired_ids = set(site["object_ids"])
        for group in groups:
            _require_nonempty_string(
                group.get("state_fips"),
                f"NHS fill site '{site_id}' group has no state FIPS.",
            )
            _require_nonempty_string(
                group.get("route_id"),
                f"NHS fill site '{site_id}' group has no route ID.",
            )
            signed_routes = group.get("signed_routes")
            if not isinstance(signed_routes, list) or facility not in signed_routes:
                raise ValueError(
                    f"NHS fill site '{site_id}' group is not signed {facility}."
                )
            if group.get("largest_measure_gap_miles") != 0.0:
                raise ValueError(
                    f"NHS fill site '{site_id}' group has a state-LRS measure gap."
                )
            spans = group.get("measure_spans")
            if not isinstance(spans, list) or not spans or any(
                not isinstance(span, list)
                or len(span) != 2
                or any(
                    not isinstance(value, int | float)
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    for value in span
                )
                for span in spans
            ):
                raise ValueError(
                    f"NHS fill site '{site_id}' group measure spans are invalid."
                )
            records = group.get("records")
            if not isinstance(records, list) or not records:
                raise ValueError(f"NHS fill site '{site_id}' group has no records.")
            for record in records:
                if record.get("object_id") not in acquired_ids:
                    raise ValueError(
                        f"NHS fill site '{site_id}' group cites an unacquired record."
                    )
    chain = payload.get("chain_connectivity", {})
    chain_segments = chain.get("segments")
    if not isinstance(chain_segments, list) or {
        entry.get("segment_id") for entry in chain_segments
    } != unconnected_ids:
        raise ValueError(
            "NHS fill lock chain connectivity does not cover exactly the "
            "unconnected segments."
        )
    if canonical_sha256(chain_segments) != payload.get("chain_connectivity_sha256"):
        raise ValueError("NHS fill lock chain connectivity digest drifted.")
    chained = 0
    for entry in chain_segments:
        connected = entry.get("chain_connected_with_fills")
        if not isinstance(connected, bool):
            raise ValueError("NHS fill lock chain connectivity claim is invalid.")
        if connected:
            chained += 1
            cited = entry.get("fill_site_ids_on_chain", [])
            if any(site_id not in site_ids for site_id in cited):
                raise ValueError(
                    f"Chained segment '{entry.get('segment_id')}' cites an unlocked "
                    "fill site."
                )
        elif not entry.get("remaining_blockers"):
            raise ValueError(
                f"Unchained segment '{entry.get('segment_id')}' records no "
                "remaining blockers."
            )
    if chain.get("chained_segment_count") != chained or chain.get(
        "unchained_segment_count"
    ) != len(chain_segments) - chained:
        raise ValueError("NHS fill lock chain connectivity counts do not reconcile.")
    if payload.get("next_stage") != NHS_FILL_NEXT_STAGE:
        raise ValueError("NHS fill lock next stage drifted.")
    return payload


# --- Q-034 per-site disposition record -----------------------------------------
#
# The disposition artifact is authored, not derived: it records the ADR-0018
# decision the evidence supports at every bounded break site. The validator
# enforces its structure, its pins against the locked inputs, and the bounds
# that keep an exception bounded. It cannot validate the judgment itself; the
# dated audit and Q-034 carry that.

DISPOSITION_STATUS = "dispositions_recorded_lock_revision_pending"
DISPOSITION_STATUS_IMPLEMENTED = "lock_revision_implemented_sub_items_pending"
# Every sub-item is resolved and implemented: scoped acquisitions are candidate
# lock supplements, fills are locked, the on-edge anchors are resolved by the
# recorded edge splits, and the bounded exceptions are authored through the
# ADR-0018 reconstruction gates. No ambiguous site may remain.
DISPOSITION_STATUS_CLOSED = "lock_revision_implemented_topology_closed"
DISPOSITION_CLASSES = (
    "nhpn_scoped_acquisition",
    "nhs_fill",
    "bounded_reconstruction_exception",
    "anchor_edge_split",
    "ambiguous",
)
CENSUS_END_CLASSES = (
    "covered_by_site_disposition",
    "beyond_corridor_continuation",
    "fragment_embedded_in_other_route",
)
Q034_SUBITEM_PATTERN = re.compile(r"^Q-034[a-z]$")
BREAK_END_ID_PATTERN = re.compile(r"^end-\d{7}-\d{2}-(start|end)$")

# The widest gap a bounded reconstruction exception may cover, in metres. The
# exception class exists for authoring discontinuities the source asserts
# adjacency across (the 1.011 m Omaha and 9.190 m Quad Cities micro-gaps), not
# for real corridor voids; the ceiling is the same 30 m near-join lens the
# census grounded in the source's observed cross-facility authoring offset.
MAXIMUM_EXCEPTION_LENGTH_METERS = BREAK_NEAR_JOIN_TOLERANCE_METERS


def _require_nonempty_string(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value


def _require_conus_coordinate(value: Any, message: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(message)
    longitude = value.get("longitude")
    latitude = value.get("latitude")
    if not isinstance(longitude, int | float) or not isinstance(latitude, int | float):
        raise ValueError(message)
    if not (-125 <= longitude <= -66 and 24 <= latitude <= 50):
        raise ValueError(message)


def _validate_disposition_site(
    site: dict[str, Any],
    site_segment_ids: set[str],
    locked_object_ids: frozenset[int],
    *,
    implemented: bool = False,
    supplements_by_site: dict[str, list[int]] | None = None,
    fill_site_ids: frozenset[str] = frozenset(),
    edge_splits_by_segment: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    site_id = _require_nonempty_string(
        site.get("site_id"), "Disposition site has no site ID."
    )
    segment_id = site.get("segment_id")
    if segment_id not in site_segment_ids:
        raise ValueError(f"Disposition site '{site_id}' names a connected segment.")
    if not site_id.startswith(f"{segment_id}--"):
        raise ValueError(f"Disposition site '{site_id}' is not scoped to its segment.")
    if site.get("kind") not in {"component_gap", "anchor_gap"}:
        raise ValueError(f"Disposition site '{site_id}' has an unsupported kind.")
    separation = site.get("separation_m")
    if (
        not isinstance(separation, int | float)
        or isinstance(separation, bool)
        or not math.isfinite(separation)
        or separation < 0
    ):
        raise ValueError(f"Disposition site '{site_id}' has an invalid separation.")
    _require_nonempty_string(
        site.get("evidence_summary"),
        f"Disposition site '{site_id}' records no evidence summary.",
    )
    disposition = site.get("disposition")
    if disposition not in DISPOSITION_CLASSES:
        raise ValueError(f"Disposition site '{site_id}' has an unsupported class.")
    if disposition == "nhpn_scoped_acquisition":
        object_ids = site.get("joining_object_ids")
        if (
            not isinstance(object_ids, list)
            or not object_ids
            or any(not isinstance(value, int) or isinstance(value, bool) for value in object_ids)
            or object_ids != sorted(set(object_ids))
        ):
            raise ValueError(
                f"Disposition site '{site_id}' names no sorted unique joining OBJECTIDs."
            )
        if implemented:
            implemented_ids = (supplements_by_site or {}).get(site_id)
            if implemented_ids != object_ids:
                raise ValueError(
                    f"Disposition site '{site_id}' is not implemented by a matching "
                    "supplementary acquisition in the candidate lock."
                )
        else:
            already_locked = sorted(set(object_ids) & locked_object_ids)
            if already_locked:
                raise ValueError(
                    f"Disposition site '{site_id}' proposes acquiring already-locked "
                    f"OBJECTIDs {already_locked}."
                )
        _require_nonempty_string(
            site.get("direction_review"),
            f"Disposition site '{site_id}' records no direction review.",
        )
        _require_nonempty_string(
            site.get("corridor_fit"),
            f"Disposition site '{site_id}' records no corridor-fit review.",
        )
    elif disposition == "nhs_fill":
        evidence = site.get("nhs_evidence")
        if not isinstance(evidence, dict):
            raise ValueError(f"Disposition site '{site_id}' records no NHS evidence.")
        _require_nonempty_string(
            evidence.get("summary"),
            f"Disposition site '{site_id}' records no NHS evidence summary.",
        )
        if not SHA256_PATTERN.fullmatch(str(evidence.get("probe_artifact_sha256", ""))):
            raise ValueError(
                f"Disposition site '{site_id}' records no NHS probe artifact hash."
            )
        if implemented and site_id not in fill_site_ids:
            raise ValueError(
                f"Disposition site '{site_id}' is not implemented by the NHS fill lock."
            )
    elif disposition == "bounded_reconstruction_exception":
        exception = site.get("exception")
        if not isinstance(exception, dict):
            raise ValueError(f"Disposition site '{site_id}' records no exception.")
        _require_nonempty_string(
            exception.get("kind"),
            f"Disposition site '{site_id}' exception has no kind.",
        )
        _require_nonempty_string(
            exception.get("rationale"),
            f"Disposition site '{site_id}' exception has no rationale.",
        )
        boundary = exception.get("boundary")
        if not isinstance(boundary, dict):
            raise ValueError(f"Disposition site '{site_id}' exception has no boundary.")
        for corner in ("from_coordinate", "to_coordinate"):
            _require_conus_coordinate(
                boundary.get(corner),
                f"Disposition site '{site_id}' exception boundary is invalid.",
            )
        length = boundary.get("length_m")
        if (
            not isinstance(length, int | float)
            or isinstance(length, bool)
            or not math.isfinite(length)
            or length <= 0
        ):
            raise ValueError(
                f"Disposition site '{site_id}' exception has no finite positive length."
            )
        if length > MAXIMUM_EXCEPTION_LENGTH_METERS:
            raise ValueError(
                f"Disposition site '{site_id}' exception exceeds the "
                f"{MAXIMUM_EXCEPTION_LENGTH_METERS:g} m bounded-exception ceiling; a "
                "wider gap is a corridor void, not an authoring discontinuity."
            )
    elif disposition == "anchor_edge_split":
        if site.get("kind") != "anchor_gap":
            raise ValueError(
                f"Disposition site '{site_id}' records an anchor edge split for a "
                "site that is not an anchor gap."
            )
        _require_nonempty_string(
            site.get("mechanism_review"),
            f"Disposition site '{site_id}' records no mechanism review.",
        )
        _require_nonempty_string(
            site.get("resolution"),
            f"Disposition site '{site_id}' records no resolution.",
        )
        subitem = site.get("resolved_q034_subitem", "")
        if not isinstance(subitem, str) or not Q034_SUBITEM_PATTERN.fullmatch(subitem):
            raise ValueError(
                f"Disposition site '{site_id}' resolves no named Q-034 sub-item."
            )
        split = site.get("anchor_split")
        if (
            not isinstance(split, dict)
            or split.get("side") not in {"from", "to"}
            or not isinstance(split.get("object_id"), int)
            or isinstance(split.get("object_id"), bool)
        ):
            raise ValueError(
                f"Disposition site '{site_id}' names no anchor split side and record."
            )
        if implemented:
            recorded = (edge_splits_by_segment or {}).get(site.get("segment_id"), [])
            if not any(
                entry.get("side") == split["side"]
                and entry.get("object_id") == split["object_id"]
                for entry in recorded
            ):
                raise ValueError(
                    f"Disposition site '{site_id}' is not implemented by a matching "
                    "anchor edge split in the edge-path lock."
                )
    else:  # ambiguous
        subitem = site.get("q034_subitem", "")
        if not isinstance(subitem, str) or not Q034_SUBITEM_PATTERN.fullmatch(subitem):
            raise ValueError(
                f"Disposition site '{site_id}' is ambiguous without a Q-034 sub-item."
            )
        _require_nonempty_string(
            site.get("blocking_question"),
            f"Disposition site '{site_id}' records no blocking question.",
        )


def validate_continental_break_dispositions(
    disposition_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
    nhs_fill_lock_path: Path | None = None,
    overlay_lock_path: Path | None = None,
) -> dict[str, Any]:
    """Validate the Q-034 per-site disposition record against the locked inputs.

    In the recorded status the record is a pending decision: no lock may carry
    supplements yet and scoped acquisitions must name unlocked records. In the
    implemented status the lock revision has landed: every scoped acquisition
    must be implemented by a matching candidate-lock supplement, every NHS fill
    by a validated NHS fill lock site, and the record pins the fill lock's hash.
    In the closed status every sub-item is resolved: additionally no ambiguous
    site remains, every anchor gap is implemented by a recorded edge split, and
    every bounded exception is authored in the reconstruction overlay lock,
    which must pin this record's hash. The overlay lock is read raw here - its
    own validator is a separate stage - so the two records pin each other
    without recursion.
    """
    payload = load_json(disposition_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported break-disposition schema.")
    status = payload.get("status")
    if status not in {
        DISPOSITION_STATUS,
        DISPOSITION_STATUS_IMPLEMENTED,
        DISPOSITION_STATUS_CLOSED,
    }:
        raise ValueError("Break-disposition record has an unsupported status.")
    implemented = status in {DISPOSITION_STATUS_IMPLEMENTED, DISPOSITION_STATUS_CLOSED}
    closed = status == DISPOSITION_STATUS_CLOSED
    selection = load_json(selection_path)
    if payload.get("decision") != selection.get("decision"):
        raise ValueError("Break-disposition decision does not match the route selection.")
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    expected_hashes = {
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Break-disposition input hash drifted.")
    raw_authored_at = payload.get("authored_at")
    if not isinstance(raw_authored_at, str):
        raise ValueError("Break-disposition authoring time is invalid.")
    try:
        authored_at = datetime.fromisoformat(raw_authored_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Break-disposition authoring time is invalid.") from error
    if authored_at.tzinfo is None:
        raise ValueError("Break-disposition authoring time has no timezone.")
    if payload.get("open_question") != "Q-034":
        raise ValueError("Break-disposition record does not cite Q-034.")
    authority = payload.get("authority", {})
    decision_records = authority.get("decision_records")
    if (
        not isinstance(decision_records, list)
        or not {"ADR-0018", "ADR-0026"}.issubset(set(decision_records))
    ):
        raise ValueError("Break-disposition record does not cite ADR-0018 and ADR-0026.")
    _require_nonempty_string(
        authority.get("owner_directive"),
        "Break-disposition record does not cite the owner directive.",
    )
    policy = payload.get("source_policy", {})
    if policy != {
        "bridging_performed": False,
        "locks_modified": implemented,
        "openstreetmap_ancestry_allowed": False,
        "tolerance_changed": False,
    }:
        raise ValueError("Break-disposition source policy is incomplete.")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Break-disposition record cites no evidence.")
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Break-disposition evidence entry is invalid.")
        if "path" in item:
            if not Path(str(item["path"])).is_file():
                raise ValueError(
                    f"Break-disposition evidence path is missing: {item['path']}"
                )
        elif not (
            isinstance(item.get("artifact"), str)
            and SHA256_PATTERN.fullmatch(str(item.get("sha256", "")))
        ):
            raise ValueError("Break-disposition evidence entry is invalid.")

    unconnected_ids = {
        entry["segment_id"] for entry in edge_lock["segments"] if not entry.get("connected")
    }
    # A recorded (pending) disposition must not propose acquiring anything the
    # lock already carries, base snapshots and prior supplements alike; an
    # implemented one instead proves its scoped sites are the supplements.
    locked_object_ids = _locked_object_id_union(route_lock)
    supplements = route_lock["nhpn"].get("supplementary_acquisitions", [])
    supplements_by_site = {
        supplement["site_id"]: supplement["object_ids"] for supplement in supplements
    }
    fill_site_ids: frozenset[str] = frozenset()
    if implemented:
        if nhs_fill_lock_path is None:
            raise ValueError(
                "An implemented break-disposition record requires the NHS fill lock."
            )
        fill_lock = validate_continental_nhs_fill_lock(
            nhs_fill_lock_path,
            selection_path,
            route_lock_path,
            transfer_lock_path,
            policy_path,
            edge_path_lock_path,
            catalog_path,
        )
        if payload.get("nhs_fill_lock_sha256") != compute_sha256(nhs_fill_lock_path):
            raise ValueError("Break-disposition NHS fill lock hash drifted.")
        fill_site_ids = frozenset(site["site_id"] for site in fill_lock["sites"])
    edge_splits_by_segment: dict[str, list[dict[str, Any]]] = {
        entry["segment_id"]: entry.get("anchor_edge_splits", [])
        for entry in edge_lock["segments"]
    }
    sites = payload.get("sites")
    if not isinstance(sites, list) or not sites:
        raise ValueError("Break-disposition record contains no sites.")
    site_ids = [site.get("site_id") for site in sites]
    if len(set(site_ids)) != len(site_ids):
        raise ValueError("Break-disposition record repeats a site.")
    # In the recorded status a site may only name a still-unconnected segment.
    # Once the revision is implemented, a scoped acquisition can have connected
    # its segment (downtown Los Angeles did exactly that), so an implemented
    # record's sites may name any locked segment while every segment that is
    # still unconnected must keep its sites.
    site_segment_ids = (
        {entry["segment_id"] for entry in edge_lock["segments"]}
        if implemented
        else unconnected_ids
    )
    for site in sites:
        _validate_disposition_site(
            site,
            site_segment_ids,
            locked_object_ids,
            implemented=implemented,
            supplements_by_site=supplements_by_site,
            fill_site_ids=fill_site_ids,
            edge_splits_by_segment=edge_splits_by_segment,
        )
    if implemented:
        scoped_site_ids = {
            site["site_id"]
            for site in sites
            if site["disposition"] == "nhpn_scoped_acquisition"
        }
        if set(supplements_by_site) != scoped_site_ids:
            raise ValueError(
                "Candidate-lock supplements do not cover exactly the scoped "
                "acquisition sites."
            )
        nhs_fill_disposition_ids = {
            site["site_id"] for site in sites if site["disposition"] == "nhs_fill"
        }
        if fill_site_ids != nhs_fill_disposition_ids:
            raise ValueError(
                "NHS fill lock sites do not cover exactly the nhs_fill dispositions."
            )
    if closed:
        if any(site["disposition"] == "ambiguous" for site in sites):
            raise ValueError(
                "A closed break-disposition record may not carry an ambiguous site."
            )
        if overlay_lock_path is None:
            raise ValueError(
                "A closed break-disposition record requires the reconstruction "
                "overlay lock."
            )
        overlay_lock = load_json(overlay_lock_path)
        if overlay_lock.get("break_disposition_sha256") != compute_sha256(
            disposition_path
        ):
            raise ValueError(
                "The reconstruction overlay lock does not pin this "
                "break-disposition record."
            )
        overlay_site_ids = {
            overlay.get("site_id") for overlay in overlay_lock.get("overlays", [])
        }
        exception_site_ids = {
            site["site_id"]
            for site in sites
            if site["disposition"] == "bounded_reconstruction_exception"
        }
        if overlay_site_ids != exception_site_ids:
            raise ValueError(
                "Reconstruction overlays do not cover exactly the bounded "
                "exception sites."
            )
    covered = {site["segment_id"] for site in sites}
    if implemented:
        if not unconnected_ids <= covered:
            raise ValueError(
                "Break-disposition sites do not cover every unconnected segment."
            )
    elif covered != unconnected_ids:
        raise ValueError(
            "Break-disposition sites do not cover exactly the unconnected segments."
        )
    if payload.get("site_count") != len(sites):
        raise ValueError("Break-disposition site count does not reconcile.")
    expected_counts: dict[str, int] = {}
    for site in sites:
        expected_counts[site["disposition"]] = expected_counts.get(site["disposition"], 0) + 1
    if payload.get("disposition_counts") != expected_counts:
        raise ValueError("Break-disposition class counts do not reconcile.")

    census_ends = payload.get("census_ends", [])
    if not isinstance(census_ends, list):
        raise ValueError("Break-disposition census ends are invalid.")
    end_ids = [end.get("end_id") for end in census_ends if isinstance(end, dict)]
    if len(end_ids) != len(census_ends) or len(set(end_ids)) != len(end_ids):
        raise ValueError("Break-disposition census ends are invalid.")
    for end in census_ends:
        end_id = str(end.get("end_id", ""))
        if not BREAK_END_ID_PATTERN.fullmatch(end_id):
            raise ValueError(f"Break-disposition census end '{end_id}' has an invalid ID.")
        if end.get("segment_id") not in site_segment_ids:
            raise ValueError(
                f"Break-disposition census end '{end_id}' names a connected segment."
            )
        if end.get("classification") not in CENSUS_END_CLASSES:
            raise ValueError(
                f"Break-disposition census end '{end_id}' has an unsupported class."
            )
        _require_nonempty_string(
            end.get("note"), f"Break-disposition census end '{end_id}' has no note."
        )

    implementation = payload.get("implementation", {})
    for key in ("implemented_this_slice", "deferred_to_lock_revision"):
        items = implementation.get(key)
        if (
            not isinstance(items, list)
            or not items
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            raise ValueError(f"Break-disposition implementation '{key}' is invalid.")
    return payload


def derive_continental_edge_path_lock(
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    output_path: Path,
    *,
    derived_at: str | None = None,
    tolerance_meters: float = ENDPOINT_SNAP_TOLERANCE_METERS,
) -> dict[str, Any]:
    """Solve the exact westbound NHPN edge path the candidate lock declares next.

    Consumes only checksum-locked inputs: the candidate lock, the transfer lock,
    and the ignored response cache whose page hashes both locks already pin. No
    network access and no new source acquisition.
    """
    if tolerance_meters <= 0 or tolerance_meters > MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS:
        raise ValueError(
            "Endpoint snap tolerance must be within 0 to "
            f"{MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS} m; a wider tolerance would "
            "invent connectivity the source does not assert."
        )
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    snapshot_by_id = {
        snapshot["segment_id"]: snapshot
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    cache_root = cache_directory / route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)

    results: list[dict[str, Any]] = []
    for segment in selection["segments"]:
        if segment["id"] not in snapshot_by_id:
            continue
        for endpoint in ("from", "to"):
            if segment[endpoint] not in transfer_by_id:
                raise ValueError(
                    f"Segment '{segment['id']}' references unlocked transfer node "
                    f"'{segment[endpoint]}'."
                )
        lines = _segment_locked_lines(route_lock, segment["id"], cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )

        def metric_point(node_id: str) -> tuple[float, float]:
            coordinate = transfer_by_id[node_id]["coordinate"]
            return forward.transform(coordinate["longitude"], coordinate["latitude"])

        results.append(
            _solve_segment_edge_path(
                segment,
                metric_lines,
                metric_point(segment["from"]),
                metric_point(segment["to"]),
                tolerance_meters,
            )
        )

    connected = [entry for entry in results if entry.get("connected")]
    unconnected = [entry for entry in results if not entry.get("connected")]
    timestamp = derived_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    payload = {
        "schema_version": 1,
        "status": "connectivity_audited_westbound_selection_pending",
        "decision": selection["decision"],
        "derived_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "endpoint_snap_tolerance_m": tolerance_meters,
        "anchor_snap_limit_m": ANCHOR_SNAP_LIMIT_METERS,
        "source_policy": {
            "candidate_source": NHPN_SOURCE_ID,
            "nhpn_role": "coarse_topology_only",
            "openstreetmap_ancestry_allowed": False,
            "lane_geometry_claimed": False,
            "authoritative_distance_claimed": False,
            "continental_downloads_committed": False,
        },
        "segment_count": len(results),
        "connected_segment_count": len(connected),
        "unconnected_segment_count": len(unconnected),
        "westbound_selection_validated": False,
        "audit_finding": _audit_finding(results),
        "segments": results,
        "segments_sha256": canonical_sha256(results),
        "next_stage": EDGE_PATH_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_edge_path_lock(
    edge_path_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate an edge-path lock without requiring the ignored response cache."""
    payload = load_json(edge_path_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Continental edge-path lock schema_version must be 1.")
    if payload.get("westbound_selection_validated") is not False:
        raise ValueError(
            "Edge-path lock claims a validated westbound selection, which this stage "
            "cannot establish."
        )
    tolerance = payload.get("endpoint_snap_tolerance_m")
    if (
        not isinstance(tolerance, int | float)
        or isinstance(tolerance, bool)
        or not math.isfinite(tolerance)
    ):
        raise ValueError("Edge-path lock declares no finite numeric snap tolerance.")
    if tolerance <= 0 or tolerance > MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS:
        raise ValueError(
            "Edge-path lock declares a snap tolerance outside the permitted range of "
            f"0 to {MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS} m."
        )
    anchor_limit = payload.get("anchor_snap_limit_m")
    if anchor_limit != ANCHOR_SNAP_LIMIT_METERS:
        raise ValueError("Edge-path lock declares a non-standard anchor snap limit.")
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    if payload.get("route_selection_sha256") != compute_sha256(selection_path):
        raise ValueError("Edge-path lock does not match the recorded route selection.")
    if payload.get("candidate_lock_sha256") != compute_sha256(route_lock_path):
        raise ValueError("Edge-path lock does not match the recorded candidate lock.")
    if payload.get("transfer_lock_sha256") != compute_sha256(transfer_lock_path):
        raise ValueError("Edge-path lock does not match the recorded transfer lock.")
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Edge-path lock records no segments.")
    if canonical_sha256(segments) != payload.get("segments_sha256"):
        raise ValueError("Edge-path lock segment digest drifted.")

    snapshot_ids = {
        snapshot["segment_id"] for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }
    transfer_ids = {node["id"] for node in transfer_lock["transfer_nodes"]}
    selection_by_id = {segment["id"]: segment for segment in selection["segments"]}
    page_hashes = {
        page["canonical_response_sha256"]
        for record in (
            *route_lock["nhpn"]["segment_snapshots"],
            *route_lock["nhpn"].get("supplementary_acquisitions", []),
        )
        for page in record["pages"]
    }
    if {entry["segment_id"] for entry in segments} != snapshot_ids:
        raise ValueError("Edge-path lock does not cover exactly the locked segments.")

    for entry in segments:
        segment = selection_by_id.get(entry["segment_id"])
        if segment is None:
            raise ValueError(
                f"Edge-path lock records segment '{entry['segment_id']}', which the "
                "route selection does not define."
            )
        for endpoint in ("from", "to"):
            if segment[endpoint] not in transfer_ids:
                raise ValueError(
                    f"Segment '{entry['segment_id']}' references an unlocked transfer node."
                )
        if entry.get("direction_validated"):
            raise ValueError(
                f"Segment '{entry['segment_id']}' claims a validated direction that this "
                "stage cannot establish."
            )
        splits = entry.get("anchor_edge_splits", [])
        if not isinstance(splits, list):
            raise ValueError(
                f"Segment '{entry['segment_id']}' anchor edge splits are invalid."
            )
        split_parts: set[tuple[int, int]] = set()
        split_sides: set[str] = set()
        for split in splits:
            if not isinstance(split, dict) or split.get("side") not in {"from", "to"}:
                raise ValueError(
                    f"Segment '{entry['segment_id']}' records an anchor split "
                    "without a valid side."
                )
            side = split["side"]
            if side in split_sides:
                raise ValueError(
                    f"Segment '{entry['segment_id']}' repeats an anchor split side."
                )
            split_sides.add(side)
            if split.get("page_response_sha256") not in page_hashes:
                raise ValueError(
                    f"Segment '{entry['segment_id']}' anchor split cites an "
                    "unlocked page response."
                )
            for field, ceiling in (
                ("anchor_offset_m", ANCHOR_SNAP_LIMIT_METERS),
                ("anchor_to_node_distance_m", ANCHOR_SNAP_LIMIT_METERS),
                ("split_distance_along_part_m", None),
                ("part_length_m", None),
            ):
                value = split.get(field)
                if (
                    not isinstance(value, int | float)
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise ValueError(
                        f"Segment '{entry['segment_id']}' anchor split records no "
                        f"finite {field}."
                    )
                if ceiling is not None and value > ceiling:
                    raise ValueError(
                        f"Segment '{entry['segment_id']}' anchor split exceeds the "
                        "anchor snap limit."
                    )
            if not (
                0.0 < split["split_distance_along_part_m"] < split["part_length_m"]
            ):
                raise ValueError(
                    f"Segment '{entry['segment_id']}' anchor split is not interior "
                    "to its record part."
                )
            recorded = entry.get(f"{side}_transfer_node_snap_distance_m")
            if recorded != split["anchor_to_node_distance_m"]:
                raise ValueError(
                    f"Segment '{entry['segment_id']}' {side} anchor distance does "
                    "not match its recorded split."
                )
            split_parts.add((int(split["object_id"]), int(split.get("part_index", 0))))
        if not entry.get("connected"):
            if not entry.get("failure"):
                raise ValueError(
                    f"Segment '{entry['segment_id']}' is unconnected without a recorded failure."
                )
            continue
        snapped = entry.get("maximum_endpoint_snap_distance_m")
        if (
            not isinstance(snapped, int | float)
            or isinstance(snapped, bool)
            or not math.isfinite(snapped)
        ):
            raise ValueError(
                f"Segment '{entry['segment_id']}' records no finite snap distance."
            )
        if snapped > tolerance:
            raise ValueError(
                f"Segment '{entry['segment_id']}' snapped beyond the declared tolerance."
            )
        for side in ("from", "to"):
            distance = entry.get(f"{side}_transfer_node_snap_distance_m")
            if (
                not isinstance(distance, int | float)
                or isinstance(distance, bool)
                or not math.isfinite(distance)
            ):
                raise ValueError(
                    f"Segment '{entry['segment_id']}' records no finite "
                    f"{side} anchor distance."
                )
            if distance > ANCHOR_SNAP_LIMIT_METERS:
                raise ValueError(
                    f"Segment '{entry['segment_id']}' reports connectivity while its "
                    f"{side} anchor exceeds the anchor snap limit."
                )
        object_ids = entry.get("object_ids") or []
        if len(object_ids) != entry.get("edge_count") or not object_ids:
            raise ValueError(f"Segment '{entry['segment_id']}' edge count disagrees.")
        parts = [
            (edge["object_id"], edge.get("part_index", 0)) for edge in entry.get("edges", [])
        ]
        if len(set(parts)) != len(parts):
            raise ValueError(f"Segment '{entry['segment_id']}' repeats an edge part.")
        edge_records = entry.get("edges")
        if not isinstance(edge_records, list) or len(edge_records) != len(object_ids):
            raise ValueError(f"Segment '{entry['segment_id']}' edge records disagree.")
        for edge in edge_records:
            if edge["page_response_sha256"] not in page_hashes:
                raise ValueError(
                    f"Segment '{entry['segment_id']}' cites an unlocked page response."
                )
    return payload


# --- ADR-0018 reconstruction gates: authored micro-gap overlays -----------------
#
# The ADR-0018 authored-exception contract: deterministic authored overlays for
# rejected or exceptional locations, preserving recursive provenance, stable
# identifiers, validation, and content-addressed output, accepted only when
# every applicable gate passes and rejected with machine-readable diagnostics
# otherwise. This stage authors the Q-034 bounded_reconstruction_exception
# sites - source authoring micro-gaps whose adjacency the source itself asserts
# in linear referencing - as bounded chord overlays between the exact break-end
# coordinates the disposition record pinned. It closes topology only: the gates
# that need generated road geometry or locked elevation are recorded as
# explicitly deferred to the reconstruction-geometry stage, never silently
# skipped or waived.

RECONSTRUCTION_OVERLAY_STATUS = "micro_gap_overlays_authored_conflation_pending"
RECONSTRUCTION_OVERLAY_NEXT_STAGE = {
    "id": "nhpn-nhs-conflation-and-3dep-lock",
    "requires": [
        "NHPN-to-NHS geometry conflation over the locked fill spans",
        "3DEP product, resolution, and datum lock over the chained corridor",
        "westbound directed edge selection over the closed topology",
    ],
}
RECONSTRUCTION_OVERLAY_SOURCE_POLICY = {
    "authored_overlay": True,
    "source_asserts_adjacency": True,
    "openstreetmap_ancestry_allowed": False,
    "lane_geometry_claimed": False,
    "authoritative_distance_claimed": False,
    "continental_downloads_committed": False,
    "tolerance_changed": False,
}
# The ADR-0018 gates a topological chord cannot exercise: they need generated
# lane and surface geometry or locked 3DEP elevation, neither of which exists at
# this stage. Deferred explicitly so nothing is waived in silence.
RECONSTRUCTION_OVERLAY_DEFERRED_GATES = (
    "curvature",
    "curvature_rate",
    "grade",
    "vertical_curvature",
    "sightline",
    "clearance",
    "collision",
    "lane_connection",
    "drivability",
)
RECONSTRUCTION_OVERLAY_DEFERRED_REASON = (
    "These gates measure generated road geometry and elevation. The overlay "
    "authored here is a bounded topological closure of a source authoring "
    "micro-gap, not drivable surface geometry; the deferred gates run when the "
    "reconstruction-geometry stage generates the actual road over the closed "
    "topology with locked 3DEP elevation."
)
RECONSTRUCTION_OVERLAY_HEADING_REASON = (
    "At micro-gap scale a chord's own bearing measures authoring noise, and an "
    "authoring gap may sit exactly on an interchange corner of the route's own "
    "LRS - the Quad Cities gap does, with 77.2 degrees between its adjoining "
    "end tangents at the I-80/I-74 corner - so heading is not adjudicated "
    "against a straight-through assumption here. Heading and curvature are "
    "properties of the generated road, judged by the reconstruction-geometry "
    "stage's gates; the measured end-tangent deviation is recorded as that "
    "stage's authoring constraint for this connection."
)
# The recomputed chord may differ from the pinned length only by coordinate
# rounding noise: the disposition pins coordinates to ~1e-7 degrees, which is
# centimetres, so anything beyond 5 mm means the boundary drifted.
OVERLAY_LENGTH_AGREEMENT_METERS = 0.005


def _overlay_gate(measured: Any, threshold: Any, passed: bool) -> dict[str, Any]:
    return {"measured": measured, "threshold": threshold, "passed": passed}


def _author_overlay_for_site(
    site: dict[str, Any],
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    tolerance: float,
    forward: Transformer,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Author one bounded micro-gap overlay through the applicable ADR-0018 gates.

    Raises with machine-readable diagnostics when any applicable gate fails;
    ADR-0018 forbids accepting a candidate past a failed gate.
    """
    site_id = site["site_id"]
    exception = site["exception"]
    boundary = exception["boundary"]
    _, nodes, incident, _ = _build_snapped_endpoint_graph(metric_lines, tolerance)

    ends: dict[str, dict[str, Any]] = {}
    for end_name in ("from", "to"):
        coordinate = boundary[f"{end_name}_coordinate"]
        point = forward.transform(coordinate["longitude"], coordinate["latitude"])
        best_key, best_distance = None, float("inf")
        for key in sorted(nodes):
            distance = math.dist(point, nodes[key])
            if distance < best_distance:
                best_key, best_distance = key, distance
        if best_key is None or best_distance > tolerance:
            raise ValueError(
                json.dumps(
                    {
                        "gate": "endpoint_position",
                        "overlay_site": site_id,
                        "end": end_name,
                        "measured_m": round(best_distance, 3),
                        "threshold_m": tolerance,
                        "finding": (
                            "The pinned boundary coordinate does not land on a "
                            "locked chain-end node within the endpoint tolerance."
                        ),
                    },
                    sort_keys=True,
                )
            )
        ends[end_name] = {
            "metric_point": point,
            "node_key": best_key,
            "node_distance_m": best_distance,
            "incident": incident.get(best_key, []),
        }

    # The source-adjacency gate: the exception class exists for gaps whose
    # adjacency the source itself asserts in linear referencing, so the two
    # boundary nodes must present record ends that are milepost-contiguous on a
    # shared LRS key. Anything else is a corridor void, not an authoring gap.
    adjacency_pair: tuple[Any, Any] | None = None
    for left, left_line, left_end in ends["from"]["incident"]:
        for right, right_line, right_end in ends["to"]["incident"]:
            if left.object_id == right.object_id:
                continue
            if _records_milepost_contiguous(left, right):
                adjacency_pair = (
                    (left, left_line, left_end),
                    (right, right_line, right_end),
                )
                break
        if adjacency_pair is not None:
            break
    if adjacency_pair is None:
        raise ValueError(
            json.dumps(
                {
                    "gate": "source_adjacency",
                    "overlay_site": site_id,
                    "finding": (
                        "No record ends at the boundary nodes are "
                        "milepost-contiguous on a shared LRS key; the source does "
                        "not assert adjacency across this gap."
                    ),
                },
                sort_keys=True,
            )
        )

    # Heading across the gap is measured, not adjudicated: an authoring gap may
    # sit exactly on an interchange corner of the route's own LRS, so the
    # adjoining end tangents (the census's jitter-absorbing 25 m chords) are
    # recorded as the reconstruction-geometry stage's authoring constraint. A
    # record too degenerate to carry a bearing still refuses authoring - the
    # constraint must be measurable.
    bearings: list[float] = []
    for candidate, line, end_name in adjacency_pair:
        at_distance = 0.0 if end_name == "start" else float(line.length)
        bearing = _chord_bearing(line, at_distance)
        if bearing is None:
            raise ValueError(
                json.dumps(
                    {
                        "gate": "heading_continuity",
                        "overlay_site": site_id,
                        "object_id": candidate.object_id,
                        "finding": "An adjoining record is too degenerate to carry a bearing.",
                    },
                    sort_keys=True,
                )
            )
        bearings.append(bearing)
    heading_deviation = _acute_angle_degrees(bearings[0], bearings[1])

    chord_length = math.dist(ends["from"]["metric_point"], ends["to"]["metric_point"])
    pinned_length = float(boundary["length_m"])
    if chord_length > MAXIMUM_EXCEPTION_LENGTH_METERS or abs(
        chord_length - pinned_length
    ) > OVERLAY_LENGTH_AGREEMENT_METERS:
        raise ValueError(
            json.dumps(
                {
                    "gate": "length_bound",
                    "overlay_site": site_id,
                    "measured_m": round(chord_length, 3),
                    "pinned_m": pinned_length,
                    "ceiling_m": MAXIMUM_EXCEPTION_LENGTH_METERS,
                    "finding": (
                        "The recomputed chord disagrees with the pinned exception "
                        "boundary or exceeds the bounded-exception ceiling."
                    ),
                },
                sort_keys=True,
            )
        )
    if chord_length <= 0.0:
        raise ValueError(
            json.dumps(
                {
                    "gate": "self_intersection",
                    "overlay_site": site_id,
                    "finding": "The boundary coordinates coincide; there is no gap to close.",
                },
                sort_keys=True,
            )
        )

    coordinates = [
        [
            boundary["from_coordinate"]["longitude"],
            boundary["from_coordinate"]["latitude"],
        ],
        [
            boundary["to_coordinate"]["longitude"],
            boundary["to_coordinate"]["latitude"],
        ],
    ]
    adjoining_records = []
    for end_name in ("from", "to"):
        for candidate, line, record_end in sorted(
            ends[end_name]["incident"],
            key=lambda entry: (entry[0].object_id, entry[0].part_index),
        ):
            endpoint = (
                line.coords[0] if record_end == "start" else line.coords[-1]
            )
            adjoining_records.append(
                {
                    "end": end_name,
                    "object_id": candidate.object_id,
                    "part_index": candidate.part_index,
                    "joined_at": record_end,
                    "lrs_key": candidate.lrs_key,
                    "record_begin_milepost": candidate.record_begin_milepost,
                    "record_end_milepost": candidate.record_end_milepost,
                    "page_response_sha256": candidate.page_response_sha256,
                    "endpoint_distance_m": round(
                        math.dist(ends[end_name]["metric_point"], endpoint), 3
                    ),
                }
            )
    left = adjacency_pair[0][0]
    right = adjacency_pair[1][0]
    return {
        "overlay_id": f"{site_id}--authored-overlay",
        "site_id": site_id,
        "segment_id": site["segment_id"],
        "kind": exception["kind"],
        "rationale": exception["rationale"],
        "boundary": boundary,
        "geometry": {
            "type": "chord",
            "coordinate_crs": "EPSG:4326",
            "coordinates": coordinates,
            "length_m": round(chord_length, 3),
            "geometry_sha256": canonical_sha256(coordinates),
        },
        "gates": {
            "endpoint_position": _overlay_gate(
                {
                    "from_node_distance_m": round(ends["from"]["node_distance_m"], 3),
                    "to_node_distance_m": round(ends["to"]["node_distance_m"], 3),
                },
                {"maximum_m": tolerance},
                True,
            ),
            "length_bound": _overlay_gate(
                {"chord_length_m": round(chord_length, 3), "pinned_m": pinned_length},
                {
                    "ceiling_m": MAXIMUM_EXCEPTION_LENGTH_METERS,
                    "pinned_agreement_m": OVERLAY_LENGTH_AGREEMENT_METERS,
                },
                True,
            ),
            "source_adjacency": _overlay_gate(
                {
                    "lrs_key": left.lrs_key,
                    "object_ids": sorted((left.object_id, right.object_id)),
                    "mileposts": [
                        [left.record_begin_milepost, left.record_end_milepost],
                        [right.record_begin_milepost, right.record_end_milepost],
                    ],
                },
                {"rule": "END_POINT equals BEGIN_POIN on a shared LRSKEY"},
                True,
            ),
            "heading_continuity": {
                "measured": {
                    "end_tangent_deviation_degrees": round(heading_deviation, 1),
                    "end_tangent_chord_m": BREAK_TANGENT_CHORD_METERS,
                },
                "deferred_to": "reconstruction-geometry-stage",
                "reason": RECONSTRUCTION_OVERLAY_HEADING_REASON,
            },
            "self_intersection": _overlay_gate(
                {"vertex_count": 2, "distinct_endpoints": True},
                {"rule": "a two-vertex chord with distinct endpoints cannot self-intersect"},
                True,
            ),
            "deferred": {
                "gates": list(RECONSTRUCTION_OVERLAY_DEFERRED_GATES),
                "deferred_to": "reconstruction-geometry-stage",
                "reason": RECONSTRUCTION_OVERLAY_DEFERRED_REASON,
            },
        },
        "adjoining_records": adjoining_records,
        "evidence": evidence,
    }


def author_continental_reconstruction_overlays(
    disposition_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    nhs_fill_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    output_path: Path,
    *,
    authored_at: str | None = None,
) -> dict[str, Any]:
    """Author the Q-034 bounded-exception overlays through the ADR-0018 gates.

    Consumes only checksum-locked inputs and the locked response cache; no
    network access and no new source acquisition. Writes the overlay lock only
    when every applicable gate passes at every exception site, and records the
    chain connectivity of the closed topology: NHPN backbone plus locked NHS
    fill chords plus these authored overlay chords, with the Q-034c/d on-edge
    anchors resolved by the edge-split fallback.
    """
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    fill_lock = validate_continental_nhs_fill_lock(
        nhs_fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    disposition = load_json(disposition_path)
    if disposition.get("schema_version") != 1 or disposition.get("open_question") != "Q-034":
        raise ValueError("Overlay authoring requires the Q-034 disposition record.")
    exception_sites = [
        site
        for site in disposition.get("sites", [])
        if site.get("disposition") == "bounded_reconstruction_exception"
    ]
    if not exception_sites:
        raise ValueError("The disposition record names no bounded exceptions to author.")

    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    cache_root = cache_directory / route_lock["nhpn"]["service"][
        "canonical_metadata_sha256"
    ]
    evidence = [dict(item) for item in disposition.get("evidence", [])]
    evidence.append({"path": str(disposition_path)})

    overlays: list[dict[str, Any]] = []
    for site in sorted(exception_sites, key=lambda entry: str(entry.get("site_id", ""))):
        lines = _segment_locked_lines(route_lock, site["segment_id"], cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )
        overlays.append(
            _author_overlay_for_site(site, metric_lines, tolerance, forward, evidence)
        )

    overlay_bridges = [
        {
            "site_id": overlay["site_id"],
            "segment_id": overlay["segment_id"],
            "from_coordinate": overlay["boundary"]["from_coordinate"],
            "to_coordinate": overlay["boundary"]["to_coordinate"],
            "separation_m": overlay["geometry"]["length_m"],
        }
        for overlay in overlays
    ]
    chain = _chain_connectivity_with_fills(
        route_lock,
        selection,
        transfer_lock,
        edge_lock,
        fill_lock["sites"],
        disposition.get("sites", []),
        cache_root,
        forward,
        overlay_sites=overlay_bridges,
    )
    connected_entries = [
        entry for entry in edge_lock["segments"] if entry.get("connected")
    ]
    chained_entries = [
        entry for entry in chain if entry["chain_connected_with_fills"]
    ]
    corridor_meters = sum(
        float(entry["length_meters"]) for entry in connected_entries
    ) + sum(float(entry["chain_length_meters"]) for entry in chained_entries)
    timestamp = authored_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    payload = {
        "schema_version": 1,
        "status": RECONSTRUCTION_OVERLAY_STATUS,
        "decision": "ADR-0018",
        "route_decision": selection["decision"],
        "open_question": "Q-034",
        "authored_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(nhs_fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "endpoint_snap_tolerance_m": edge_lock["endpoint_snap_tolerance_m"],
        "anchor_snap_limit_m": edge_lock["anchor_snap_limit_m"],
        "maximum_exception_length_m": MAXIMUM_EXCEPTION_LENGTH_METERS,
        "source_policy": dict(RECONSTRUCTION_OVERLAY_SOURCE_POLICY),
        "westbound_selection_validated": False,
        "overlay_count": len(overlays),
        "overlays": overlays,
        "overlays_sha256": canonical_sha256(overlays),
        "chain_connectivity": {
            "note": (
                "Anchor-to-anchor connectivity of each unconnected segment over "
                "the closed topology: NHPN backbone, locked NHS fill chords, "
                "authored ADR-0018 overlay chords, and the Q-034c/d on-edge "
                "anchors resolved by the edge-split fallback. A chained segment "
                "is a mixed-ancestry chain, not an NHPN path, not a westbound "
                "selection, and not an authoritative distance."
            ),
            "chained_segment_count": len(chained_entries),
            "unchained_segment_count": len(chain) - len(chained_entries),
            "segments": chain,
        },
        "chain_connectivity_sha256": canonical_sha256(chain),
        "corridor": {
            "segment_count": len(edge_lock["segments"]),
            "nhpn_connected_segment_count": len(connected_entries),
            "chained_segment_count": len(chained_entries),
            "segments_chaining_anchor_to_anchor": (
                len(connected_entries) + len(chained_entries)
            ),
            "continuously_chained_corridor_miles": round(
                corridor_meters / METRES_PER_MILE, 1
            ),
            "note": (
                "Chain lengths are shortest undirected mixed-ancestry chains; "
                "fill and overlay spans contribute chord length only. Not an "
                "authoritative distance and not a westbound selection."
            ),
        },
        "next_stage": RECONSTRUCTION_OVERLAY_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_reconstruction_overlays(
    overlay_lock_path: Path,
    disposition_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    nhs_fill_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the authored overlay lock without the ignored response cache.

    Everything recomputable without the cache is recomputed: the pins, the
    boundary equality against the disposition record, the chord geometry and its
    length, the gate records against their own thresholds, the digests, and the
    chain-connectivity reconciliation. The disposition record is read raw here -
    its own validator cross-checks this artifact, so each side pins the other
    without recursion.
    """
    payload = load_json(overlay_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported reconstruction overlay lock schema.")
    if payload.get("status") != RECONSTRUCTION_OVERLAY_STATUS:
        raise ValueError("Reconstruction overlay lock has an unsupported status.")
    if payload.get("decision") != "ADR-0018":
        raise ValueError("Reconstruction overlay lock does not cite ADR-0018.")
    if payload.get("open_question") != "Q-034":
        raise ValueError("Reconstruction overlay lock does not cite Q-034.")
    if payload.get("westbound_selection_validated") is not False:
        raise ValueError(
            "Reconstruction overlay lock claims a validated westbound selection, "
            "which this stage cannot establish."
        )
    selection = load_json(selection_path)
    if payload.get("route_decision") != selection.get("decision"):
        raise ValueError(
            "Reconstruction overlay lock route decision does not match the "
            "route selection."
        )
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    validate_continental_nhs_fill_lock(
        nhs_fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(nhs_fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Reconstruction overlay lock input hash drifted.")
    if payload.get("source_policy") != RECONSTRUCTION_OVERLAY_SOURCE_POLICY:
        raise ValueError("Reconstruction overlay lock source policy is incomplete.")
    if payload.get("endpoint_snap_tolerance_m") != edge_lock["endpoint_snap_tolerance_m"]:
        raise ValueError(
            "Reconstruction overlay lock declares a drifted endpoint snap tolerance."
        )
    if payload.get("anchor_snap_limit_m") != edge_lock["anchor_snap_limit_m"]:
        raise ValueError(
            "Reconstruction overlay lock declares a drifted anchor snap limit."
        )
    if payload.get("maximum_exception_length_m") != MAXIMUM_EXCEPTION_LENGTH_METERS:
        raise ValueError(
            "Reconstruction overlay lock declares a non-standard exception ceiling."
        )
    if payload.get("next_stage") != RECONSTRUCTION_OVERLAY_NEXT_STAGE:
        raise ValueError("Reconstruction overlay lock next stage drifted.")

    disposition = load_json(disposition_path)
    exception_by_site = {
        site["site_id"]: site
        for site in disposition.get("sites", [])
        if site.get("disposition") == "bounded_reconstruction_exception"
    }
    overlays = payload.get("overlays")
    if not isinstance(overlays, list) or not overlays:
        raise ValueError("Reconstruction overlay lock records no overlays.")
    if payload.get("overlay_count") != len(overlays):
        raise ValueError("Reconstruction overlay lock overlay count does not reconcile.")
    if canonical_sha256(overlays) != payload.get("overlays_sha256"):
        raise ValueError("Reconstruction overlay lock overlay digest drifted.")
    if {overlay.get("site_id") for overlay in overlays} != set(exception_by_site):
        raise ValueError(
            "Reconstruction overlays do not cover exactly the disposition's "
            "bounded exceptions."
        )
    tolerance = float(payload["endpoint_snap_tolerance_m"])
    page_hashes = {
        page["canonical_response_sha256"]
        for record in (
            *route_lock["nhpn"]["segment_snapshots"],
            *route_lock["nhpn"].get("supplementary_acquisitions", []),
        )
        for page in record["pages"]
    }
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    for overlay in overlays:
        site_id = overlay["site_id"]
        site = exception_by_site[site_id]
        exception = site["exception"]
        if overlay.get("overlay_id") != f"{site_id}--authored-overlay":
            raise ValueError(f"Overlay for '{site_id}' has an unstable identifier.")
        if overlay.get("segment_id") != site["segment_id"]:
            raise ValueError(f"Overlay for '{site_id}' names the wrong segment.")
        if overlay.get("boundary") != exception["boundary"]:
            raise ValueError(
                f"Overlay for '{site_id}' does not match the pinned exception boundary."
            )
        if overlay.get("kind") != exception["kind"] or overlay.get(
            "rationale"
        ) != exception["rationale"]:
            raise ValueError(
                f"Overlay for '{site_id}' drifted from the recorded exception."
            )
        geometry = overlay.get("geometry", {})
        boundary = exception["boundary"]
        expected_coordinates = [
            [
                boundary["from_coordinate"]["longitude"],
                boundary["from_coordinate"]["latitude"],
            ],
            [
                boundary["to_coordinate"]["longitude"],
                boundary["to_coordinate"]["latitude"],
            ],
        ]
        if (
            geometry.get("type") != "chord"
            or geometry.get("coordinate_crs") != "EPSG:4326"
            or geometry.get("coordinates") != expected_coordinates
            or geometry.get("geometry_sha256") != canonical_sha256(expected_coordinates)
        ):
            raise ValueError(f"Overlay for '{site_id}' geometry drifted.")
        length = geometry.get("length_m")
        if (
            not isinstance(length, int | float)
            or isinstance(length, bool)
            or not math.isfinite(length)
            or length <= 0
            or length > MAXIMUM_EXCEPTION_LENGTH_METERS
        ):
            raise ValueError(
                f"Overlay for '{site_id}' length violates the bounded-exception "
                "ceiling."
            )
        chord = math.dist(
            forward.transform(
                boundary["from_coordinate"]["longitude"],
                boundary["from_coordinate"]["latitude"],
            ),
            forward.transform(
                boundary["to_coordinate"]["longitude"],
                boundary["to_coordinate"]["latitude"],
            ),
        )
        if round(chord, 3) != length or abs(
            chord - float(boundary["length_m"])
        ) > OVERLAY_LENGTH_AGREEMENT_METERS:
            raise ValueError(
                f"Overlay for '{site_id}' length does not reproduce from its "
                "pinned coordinates."
            )
        gates = overlay.get("gates")
        if not isinstance(gates, dict):
            raise ValueError(f"Overlay for '{site_id}' records no gates.")
        for gate_name in (
            "endpoint_position",
            "length_bound",
            "source_adjacency",
            "self_intersection",
        ):
            gate = gates.get(gate_name)
            if not isinstance(gate, dict) or gate.get("passed") is not True:
                raise ValueError(
                    f"Overlay for '{site_id}' gate '{gate_name}' did not pass."
                )
        position = gates["endpoint_position"]["measured"]
        for field in ("from_node_distance_m", "to_node_distance_m"):
            value = position.get(field)
            if (
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value > tolerance
            ):
                raise ValueError(
                    f"Overlay for '{site_id}' endpoint distance exceeds the "
                    "endpoint tolerance."
                )
        heading = gates.get("heading_continuity")
        if not isinstance(heading, dict) or heading.get(
            "deferred_to"
        ) != "reconstruction-geometry-stage" or not str(
            heading.get("reason", "")
        ).strip():
            raise ValueError(
                f"Overlay for '{site_id}' does not defer heading to the "
                "geometry stage explicitly."
            )
        deviation = (heading.get("measured") or {}).get(
            "end_tangent_deviation_degrees"
        )
        if (
            not isinstance(deviation, int | float)
            or isinstance(deviation, bool)
            or not math.isfinite(deviation)
        ):
            raise ValueError(
                f"Overlay for '{site_id}' records no measured end-tangent "
                "deviation for the geometry stage."
            )
        deferred = gates.get("deferred", {})
        if deferred.get("gates") != list(RECONSTRUCTION_OVERLAY_DEFERRED_GATES) or not str(
            deferred.get("reason", "")
        ).strip():
            raise ValueError(
                f"Overlay for '{site_id}' does not record the deferred gates "
                "explicitly."
            )
        adjoining = overlay.get("adjoining_records")
        if not isinstance(adjoining, list) or not adjoining:
            raise ValueError(f"Overlay for '{site_id}' records no adjoining records.")
        if {record.get("end") for record in adjoining} != {"from", "to"}:
            raise ValueError(
                f"Overlay for '{site_id}' does not record both adjoining ends."
            )
        for record in adjoining:
            if record.get("page_response_sha256") not in page_hashes:
                raise ValueError(
                    f"Overlay for '{site_id}' cites an unlocked page response."
                )
            distance = record.get("endpoint_distance_m")
            if (
                not isinstance(distance, int | float)
                or isinstance(distance, bool)
                or not math.isfinite(distance)
                or distance > tolerance
            ):
                raise ValueError(
                    f"Overlay for '{site_id}' adjoining record is not at the "
                    "boundary."
                )
        evidence = overlay.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"Overlay for '{site_id}' cites no evidence.")
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError(f"Overlay for '{site_id}' evidence entry is invalid.")
            if "path" in item:
                if not Path(str(item["path"])).is_file():
                    raise ValueError(
                        f"Overlay for '{site_id}' evidence path is missing: "
                        f"{item['path']}"
                    )
            elif not (
                isinstance(item.get("artifact"), str)
                and SHA256_PATTERN.fullmatch(str(item.get("sha256", "")))
            ):
                raise ValueError(f"Overlay for '{site_id}' evidence entry is invalid.")

    unconnected_ids = {
        entry["segment_id"] for entry in edge_lock["segments"] if not entry.get("connected")
    }
    chain = payload.get("chain_connectivity", {})
    chain_segments = chain.get("segments")
    if not isinstance(chain_segments, list) or {
        entry.get("segment_id") for entry in chain_segments
    } != unconnected_ids:
        raise ValueError(
            "Reconstruction overlay chain connectivity does not cover exactly "
            "the unconnected segments."
        )
    if canonical_sha256(chain_segments) != payload.get("chain_connectivity_sha256"):
        raise ValueError("Reconstruction overlay chain connectivity digest drifted.")
    overlay_site_ids = {overlay["site_id"] for overlay in overlays}
    chained = 0
    cited_overlays: set[str] = set()
    for entry in chain_segments:
        connected = entry.get("chain_connected_with_fills")
        if not isinstance(connected, bool):
            raise ValueError("Reconstruction overlay chain claim is invalid.")
        if connected:
            chained += 1
            for site_id in entry.get("overlay_site_ids_on_chain", []):
                if site_id not in overlay_site_ids:
                    raise ValueError(
                        f"Chained segment '{entry.get('segment_id')}' cites an "
                        "unauthored overlay."
                    )
                cited_overlays.add(site_id)
        elif not entry.get("remaining_blockers"):
            raise ValueError(
                f"Unchained segment '{entry.get('segment_id')}' records no "
                "remaining blockers."
            )
    if chain.get("chained_segment_count") != chained or chain.get(
        "unchained_segment_count"
    ) != len(chain_segments) - chained:
        raise ValueError(
            "Reconstruction overlay chain connectivity counts do not reconcile."
        )
    corridor = payload.get("corridor", {})
    connected_entries = [
        entry for entry in edge_lock["segments"] if entry.get("connected")
    ]
    corridor_meters = sum(
        float(entry["length_meters"]) for entry in connected_entries
    ) + sum(
        float(entry["chain_length_meters"])
        for entry in chain_segments
        if entry["chain_connected_with_fills"]
    )
    expected_corridor = {
        "segment_count": len(edge_lock["segments"]),
        "nhpn_connected_segment_count": len(connected_entries),
        "chained_segment_count": chained,
        "segments_chaining_anchor_to_anchor": len(connected_entries) + chained,
        "continuously_chained_corridor_miles": round(
            corridor_meters / METRES_PER_MILE, 1
        ),
        "note": corridor.get("note"),
    }
    if corridor != expected_corridor or not str(corridor.get("note", "")).strip():
        raise ValueError("Reconstruction overlay corridor summary does not reconcile.")
    return payload


# --- ADR-0026 NHPN-NHS conflation model ------------------------------------------
#
# The fill lock records what NHS asserts across the named NHPN voids; nothing in
# it is conflated. This stage builds the deterministic correspondence between the
# two datasets over exactly the locked fill spans: seam correspondence at each
# span end (NHS state-LRS measures against the NHPN record and milepost space the
# chain ends carry), and geometric agreement bounds along the span. ADR-0026
# requires the model to be reusable when HPMS is adopted later: HPMS extracts the
# same ARNOLD substrate, so every correspondence here is keyed on the ARNOLD LRS
# identity (STFIPS, ROUTEID, measure) and nothing is keyed on NHS-only fields.
# Nothing here selects a direction, claims an authoritative distance, or bridges
# anything the locks do not already bridge.

NHS_CONFLATION_LOCK_STATUS = "nhpn_nhs_conflation_locked_reconstruction_pending"
NHS_CONFLATION_NEXT_STAGE = {
    "id": "westbound-selection-and-reconstruction",
    "requires": [
        "westbound directed edge selection over the closed topology",
        "reconstruction geometry through the full ADR-0018 gate battery",
    ],
}

# Seam agreement bound between a pinned NHPN break-end coordinate and the NHS
# centerline it corresponds to. Grounded exactly like the probe lens: the seam
# coordinate is an NHPN record endpoint and the catalog documents NHPN
# horizontal error up to approximately 80 m, so a tighter bound would refuse a
# correspondence wherever the two datasets merely disagree within their stated
# error. A seam is a recorded correspondence, not a snap or a join.
CONFLATION_SEAM_OFFSET_BOUND_METERS = NHS_PROXIMITY_LENS_METERS

# Along-span sampling interval. 50 m resolves the shortest locked fill span
# (the 320 m Rifle void) into multiple interior stations while keeping the
# longest (the 27.3 km i15 span) to a few hundred deterministic stations.
CONFLATION_STATION_SPACING_METERS = 50.0

# How far a participating record's planimetric geometry length may disagree
# with the source's own length assertion for that record (the MILES field), as
# a fraction of MILES. The 2026-08-31 characterisation proved the state-LRS
# measure axis (BEGINPOINT/ENDPOINT) is calibrated, not metric: per-record
# measure extents diverge from planimetric length by up to 43% (and 14.6% over
# the whole i78 span) while the source's MILES field agrees with its geometry
# within about 1% on every locked fill record. The length bound therefore
# belongs between geometry and MILES - it trips when the conflated geometry is
# not the geometry the source measured - and the measure axis is recorded as a
# parametrisation only, never as a length.
CONFLATION_GEOMETRY_MILES_AGREEMENT_RATIO = 0.02

# Geometric coincidence tolerance for measure-adjacency evidence: two NHS
# records of one state route whose measures abut are digitized end-on, so
# their shared boundary vertex is expected to coincide to authoring noise.
# This tolerance orients record geometry against the measure axis; it never
# bridges a gap and it is far inside the 80 m cross-dataset lens.
CONFLATION_ADJACENCY_GAP_METERS = 5.0

# Measure margin for the orientation-evidence acquisition around each locked
# fill span. The margin exists only so that every span-carrying record has a
# measure-adjacent neighbour on record (a single-record span has no intra-span
# adjacency); margin records supply orientation evidence and are not fill
# geometry, not candidates, and not additions to any lock.
CONFLATION_MEASURE_MARGIN_MILES = 0.25

CONFLATION_SOURCE_POLICY = {
    "supplementary_source": NHS_SOURCE_ID,
    "nhs_role": "supplementary_centerlines_only",
    "nhpn_remains_route_authority": True,
    "openstreetmap_ancestry_allowed": False,
    "lane_geometry_claimed": False,
    "authoritative_distance_claimed": False,
    "continental_downloads_committed": False,
    "conflation_performed": True,
    "margin_records_are_orientation_evidence_only": True,
}


def _load_locked_nhs_site_features(
    site: dict[str, Any], checkpoint_directory: Path
) -> dict[int, dict[str, Any]]:
    """Load one fill site's locked NHS features from its response cache.

    Applies the same drift discipline as the NHPN loader: every checkpoint must
    reproduce the page hash the fill lock pinned, and the returned features must
    reconcile exactly with the locked OBJECTID snapshot.
    """
    object_ids = site["object_ids"]
    features: dict[int, dict[str, Any]] = {}
    for page in site["pages"]:
        checkpoint = checkpoint_directory / f"page-{page['index']:06d}.json"
        if not checkpoint.is_file():
            raise ValueError(f"Locked NHS checkpoint is missing: {checkpoint}")
        record = load_json(checkpoint)
        response = record.get("response")
        response_hash = canonical_sha256(response)
        if (
            not isinstance(response, dict)
            or record.get("response_sha256") != response_hash
            or page.get("canonical_response_sha256") != response_hash
        ):
            raise ValueError(f"Locked NHS checkpoint hash drifted: {checkpoint}")
        offset = page["object_id_offset"]
        expected_ids = object_ids[offset : offset + page["feature_count"]]
        page_features = response.get("features", [])
        returned_ids = [int(feature["attributes"]["OBJECTID"]) for feature in page_features]
        if returned_ids != expected_ids:
            raise ValueError(f"Locked NHS checkpoint IDs drifted: {checkpoint}")
        for feature in page_features:
            features[int(feature["attributes"]["OBJECTID"])] = feature
    if sorted(features) != sorted(object_ids):
        raise ValueError(
            f"Locked NHS cache does not reconcile for '{site['site_id']}'."
        )
    return features


def _conflation_margin_predicate(
    state_fips: str,
    route_id: str,
    measure_low: float,
    measure_high: float,
    margin_miles: float = CONFLATION_MEASURE_MARGIN_MILES,
) -> str:
    """The exact attribute predicate of one orientation-evidence acquisition."""
    escaped = route_id.replace("'", "''")
    low = measure_low - margin_miles
    high = measure_high + margin_miles
    return (
        f"STFIPS = '{state_fips}' AND ROUTEID = '{escaped}' "
        f"AND ENDPOINT > {low:.6f} AND BEGINPOINT < {high:.6f}"
    )


def _merged_feature_line(feature: dict[str, Any]) -> LineString:
    """One NHS record's geometry as a single continuous line, or a refusal."""
    parts = [
        LineString(coordinates)
        for coordinates in feature.get("geometry", {}).get("paths", [])
        if len(coordinates) >= 2
    ]
    if not parts:
        raise ValueError(
            f"NHS record {feature['attributes'].get('OBJECTID')} has no geometry."
        )
    if len(parts) == 1:
        return parts[0]
    merged = linemerge(MultiLineString(parts))
    if not isinstance(merged, LineString):
        raise ValueError(
            f"NHS record {feature['attributes'].get('OBJECTID')} does not merge "
            "into one continuous line; its measures cannot be interpolated."
        )
    return merged


def _measure_adjacency_votes(
    target: dict[str, Any],
    neighbours: Sequence[dict[str, Any]],
    gap_tolerance_m: float,
    *,
    measure_quantum: float = 1e-6,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Orient one record's geometry against its measure axis by adjacency.

    A record whose measures abut a neighbour's is digitized end-on with it, so
    the geometric end that coincides with that neighbour is the shared measure
    boundary. Each matched boundary is one vote for ``forward`` (geometry
    coordinate order runs from BEGINPOINT to ENDPOINT) or ``reversed``.
    Conflicting votes are a refusal, not a preference: they would mean the
    source's own geometry contradicts its measure space at this site.
    """
    target_coords = list(target["line"].coords)
    target_start, target_end = target_coords[0], target_coords[-1]
    votes: set[str] = set()
    evidence: list[dict[str, Any]] = []
    for neighbour in sorted(neighbours, key=lambda entry: entry["object_id"]):
        if neighbour["object_id"] == target["object_id"]:
            continue
        boundaries: list[tuple[str, float]] = []
        if abs(target["end"] - neighbour["begin"]) <= measure_quantum:
            boundaries.append(("high", target["end"]))
        if abs(neighbour["end"] - target["begin"]) <= measure_quantum:
            boundaries.append(("low", target["begin"]))
        if not boundaries:
            continue
        neighbour_coords = list(neighbour["line"].coords)
        neighbour_ends = (neighbour_coords[0], neighbour_coords[-1])
        start_gap = min(math.dist(target_start, end) for end in neighbour_ends)
        end_gap = min(math.dist(target_end, end) for end in neighbour_ends)
        for boundary_kind, boundary_measure in boundaries:
            record: dict[str, Any] = {
                "neighbour_object_id": neighbour["object_id"],
                "boundary": boundary_kind,
                "boundary_measure": round(boundary_measure, 6),
                "start_gap_m": round(start_gap, 3),
                "end_gap_m": round(end_gap, 3),
            }
            if min(start_gap, end_gap) > gap_tolerance_m:
                record["unmatched"] = True
                evidence.append(record)
                continue
            # The boundary end is the strictly closer one. A record can be as
            # short as one source measure quantum (about 1.6 m), so both of its
            # ends may sit inside the coincidence tolerance of a neighbour; the
            # shared boundary vertex is still the exact one, so the vote is
            # ambiguous only when the two gaps are indistinguishable.
            if abs(start_gap - end_gap) <= 1e-3:
                record["ambiguous"] = True
                evidence.append(record)
                continue
            boundary_at_end = end_gap < start_gap
            if boundary_kind == "high":
                vote = "forward" if boundary_at_end else "reversed"
            else:
                vote = "forward" if not boundary_at_end else "reversed"
            record.update(
                vote=vote,
                endpoint_gap_m=round(end_gap if boundary_at_end else start_gap, 3),
            )
            votes.add(vote)
            evidence.append(record)
    if len(votes) > 1:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "conflicting measure-orientation evidence",
                    "object_id": target["object_id"],
                    "evidence": evidence,
                },
                sort_keys=True,
            )
        )
    return (votes.pop() if votes else None), evidence


def _measure_at_distance(record: dict[str, Any], distance_along_m: float) -> float:
    """The state-LRS measure at a distance along one oriented record geometry."""
    length = float(record["line"].length)
    extent = record["end"] - record["begin"]
    fraction = 0.0 if length <= 0 else min(max(distance_along_m / length, 0.0), 1.0)
    if record["orientation"] == "forward":
        return record["begin"] + extent * fraction
    return record["end"] - extent * fraction


def _assemble_conflation_span(
    records: Sequence[dict[str, Any]],
    measure_low: float,
    measure_high: float,
) -> dict[str, Any]:
    """The NHS span geometry between two seam measures, in measure order.

    Records are clipped to the seam interval through their own linear
    measure-to-distance map, oriented ascending, and concatenated. Overlapping
    records (the source publishes duplicates) are resolved deterministically:
    the cursor only moves forward, and the first record in (begin, end,
    object_id) order supplies each measure range.
    """
    pieces: list[dict[str, Any]] = []
    coordinates: list[tuple[float, float]] = []
    cursor = measure_low
    max_joint_gap = 0.0
    for record in sorted(
        records, key=lambda entry: (entry["begin"], entry["end"], entry["object_id"])
    ):
        if record["end"] <= cursor + 1e-9 or record["begin"] >= measure_high - 1e-9:
            continue
        piece_low = max(record["begin"], cursor)
        piece_high = min(record["end"], measure_high)
        if piece_high - piece_low <= 1e-9:
            continue
        length = float(record["line"].length)
        extent = record["end"] - record["begin"]
        if record["orientation"] == "forward":
            start = (piece_low - record["begin"]) / extent * length
            stop = (piece_high - record["begin"]) / extent * length
            geometry = substring(record["line"], start, stop)
            piece_coords = list(geometry.coords)
        else:
            start = (record["end"] - piece_high) / extent * length
            stop = (record["end"] - piece_low) / extent * length
            geometry = substring(record["line"], start, stop)
            piece_coords = list(geometry.coords)[::-1]
        if coordinates:
            joint_gap = math.dist(coordinates[-1], piece_coords[0])
            max_joint_gap = max(max_joint_gap, joint_gap)
            if joint_gap <= 1e-9:
                piece_coords = piece_coords[1:]
        coordinates.extend(piece_coords)
        pieces.append(
            {
                "object_id": record["object_id"],
                "measure_range": [round(piece_low, 6), round(piece_high, 6)],
                "length_m": round(float(geometry.length), 3),
            }
        )
        cursor = piece_high
    if cursor < measure_high - 1e-9 or len(coordinates) < 2:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "NHS records do not cover the seam measure interval",
                    "covered_to": round(cursor, 6),
                    "measure_high": round(measure_high, 6),
                },
                sort_keys=True,
            )
        )
    return {
        "line": LineString(coordinates),
        "pieces": pieces,
        "max_joint_gap_m": round(max_joint_gap, 3),
    }


def _span_nhpn_agreement(
    span_line: LineString,
    metric_lines: Sequence[tuple[LockedCandidateLine, LineString]],
    spacing_m: float,
    lens_m: float,
) -> dict[str, Any]:
    """Where along the span the locked NHPN candidate set agrees, and where it is void.

    Stations beyond the lens are the NHPN void the fill exists for; they are
    characterised as contiguous runs, never absorbed. Stations within the lens
    measure the two datasets' lateral agreement over shared pavement.
    """
    length = float(span_line.length)
    stations = [index * spacing_m for index in range(int(length // spacing_m) + 1)]
    if not stations or length - stations[-1] > 1e-6:
        stations.append(length)
    minx, miny, maxx, maxy = span_line.bounds
    window = (minx - 2 * lens_m, miny - 2 * lens_m, maxx + 2 * lens_m, maxy + 2 * lens_m)
    nearby = [
        geometry
        for _, geometry in metric_lines
        if geometry.bounds[0] <= window[2]
        and geometry.bounds[2] >= window[0]
        and geometry.bounds[1] <= window[3]
        and geometry.bounds[3] >= window[1]
    ]
    offsets: list[tuple[float, float]] = []
    for station in stations:
        point = span_line.interpolate(station)
        distance = min(
            (geometry.distance(point) for geometry in nearby), default=float("inf")
        )
        offsets.append((station, distance))
    within = [(station, value) for station, value in offsets if value <= lens_m]
    beyond = [(station, value) for station, value in offsets if value > lens_m]
    void_runs: list[dict[str, Any]] = []
    run_start: float | None = None
    previous_station = 0.0
    for station, value in offsets:
        if value > lens_m:
            if run_start is None:
                run_start = station
            previous_station = station
        elif run_start is not None:
            void_runs.append(
                {
                    "start_m": round(run_start, 3),
                    "end_m": round(previous_station, 3),
                }
            )
            run_start = None
    if run_start is not None:
        void_runs.append(
            {"start_m": round(run_start, 3), "end_m": round(previous_station, 3)}
        )
    return {
        "station_spacing_m": spacing_m,
        "station_count": len(offsets),
        "stations_within_nhpn_lens": len(within),
        "stations_beyond_nhpn_lens": len(beyond),
        "nhpn_void_runs": void_runs,
        "nhpn_agreement": {
            "max_offset_m": round(max((value for _, value in within), default=0.0), 3),
            "mean_offset_m": round(
                sum(value for _, value in within) / len(within) if within else 0.0, 3
            ),
        },
    }


def _nhpn_seam_correspondence(
    seam_metric: tuple[float, float],
    metric_lines: Sequence[tuple[LockedCandidateLine, LineString]],
    tolerance_m: float,
) -> dict[str, Any]:
    """The NHPN record whose chain end carries a seam, with its milepost space.

    The seam coordinate is a pinned break end, so it must coincide with at
    least one locked record endpoint within the unchanged endpoint tolerance.
    The record's milepost at the seam end is resolved by the same
    measure-adjacency evidence the NHS side uses, against the record's own LRS
    key; when the key carries no adjacent record the interval is recorded and
    the seam milepost stays null rather than guessed.
    """
    matches: list[dict[str, Any]] = []
    for candidate, geometry in metric_lines:
        coordinates = list(geometry.coords)
        for end_name, coordinate in (("start", coordinates[0]), ("end", coordinates[-1])):
            distance = math.dist(seam_metric, coordinate)
            if distance <= tolerance_m:
                matches.append(
                    {
                        "object_id": candidate.object_id,
                        "part_index": candidate.part_index,
                        "lrs_key": candidate.lrs_key,
                        "geometry_end": end_name,
                        "endpoint_distance_m": round(distance, 3),
                        "record_milepost_interval": [
                            candidate.record_begin_milepost,
                            candidate.record_end_milepost,
                        ],
                        "page_response_sha256": candidate.page_response_sha256,
                    }
                )
    if not matches:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "seam does not land on a locked NHPN record endpoint",
                    "tolerance_m": tolerance_m,
                },
                sort_keys=True,
            )
        )
    matches.sort(
        key=lambda entry: (
            entry["endpoint_distance_m"],
            entry["object_id"],
            entry["part_index"],
        )
    )
    primary = matches[0]
    target_line = next(
        geometry
        for candidate, geometry in metric_lines
        if candidate.object_id == primary["object_id"]
        and candidate.part_index == primary["part_index"]
    )
    target_candidate = next(
        candidate
        for candidate, _ in metric_lines
        if candidate.object_id == primary["object_id"]
        and candidate.part_index == primary["part_index"]
    )
    neighbours = [
        {
            "object_id": candidate.object_id,
            "begin": candidate.record_begin_milepost,
            "end": candidate.record_end_milepost,
            "line": geometry,
        }
        for candidate, geometry in metric_lines
        if candidate.lrs_key == target_candidate.lrs_key
        and candidate.lrs_key
        and candidate.object_id != target_candidate.object_id
    ]
    orientation, evidence = _measure_adjacency_votes(
        {
            "object_id": target_candidate.object_id,
            "begin": target_candidate.record_begin_milepost,
            "end": target_candidate.record_end_milepost,
            "line": target_line,
        },
        neighbours,
        tolerance_m,
        measure_quantum=MILEPOST_QUANTUM_MILES / 2,
    )
    milepost_at_seam: float | None = None
    if orientation is not None:
        at_geometry_end = primary["geometry_end"] == "end"
        forward = orientation == "forward"
        milepost_at_seam = (
            target_candidate.record_end_milepost
            if at_geometry_end == forward
            else target_candidate.record_begin_milepost
        )
    return {
        "matches": matches,
        "correspondence": {
            **primary,
            "orientation": orientation,
            "orientation_evidence": evidence,
            "milepost_at_seam": milepost_at_seam,
        },
    }


def derive_continental_nhs_conflation(
    fill_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    fill_cache_directory: Path,
    conflation_cache_directory: Path,
    output_path: Path,
    *,
    transport: ArcGisTransport | None = None,
    service_metadata: dict[str, Any] | None = None,
    acquired_at: str | None = None,
    page_size: int = 2_000,
) -> dict[str, Any]:
    """Derive the NHPN-NHS conflation lock over the five locked fill spans.

    Consumes the checksum-locked inputs and their response caches. The only
    network access is the orientation-evidence margin acquisition around each
    span, made with the full NHPN acquisition discipline against the exact NHS
    service the fill lock names: a live service whose metadata hash has drifted
    from the fill lock's is refused outright, because its measures would not be
    the ones the fill lock records. Every bound failure is a machine-readable
    refusal, never an absorbed offset.
    """
    catalog = load_catalog(catalog_path)
    if NHS_SOURCE_ID not in catalog:
        raise ValueError("NHS is not in the approved source catalog.")
    source = catalog[NHS_SOURCE_ID]
    service_url, query_url = _require_nhs_query_url(source)
    fill_lock = validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    if service_metadata is None:
        with urllib.request.urlopen(service_url + "?f=pjson", timeout=120) as response:
            service_metadata = json.loads(response.read())
    _validate_nhs_service_metadata(service_metadata)
    service_metadata_sha256 = canonical_sha256(service_metadata)
    if service_metadata_sha256 != fill_lock["nhs"]["service"]["canonical_metadata_sha256"]:
        raise ValueError(
            "Live NHS service metadata has drifted from the fill lock; a "
            "conflation against it would correspond measures the fill lock does "
            "not record."
        )
    max_record_count = int(service_metadata["maxRecordCount"])
    if page_size > max_record_count:
        raise ValueError(
            f"NHS page size {page_size} exceeds the live service limit of "
            f"{max_record_count}."
        )
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    if transport is None:
        transport = UrllibArcGisTransport(timeout_seconds=120)
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    cache_root = cache_directory / route_lock["nhpn"]["service"][
        "canonical_metadata_sha256"
    ]
    fill_root = fill_cache_directory / service_metadata_sha256
    conflation_root = conflation_cache_directory / service_metadata_sha256
    tolerance = float(fill_lock["endpoint_snap_tolerance_m"])

    sites: list[dict[str, Any]] = []
    for site in sorted(fill_lock["sites"], key=lambda entry: entry["site_id"]):
        site_id = site["site_id"]
        groups = site["fill_route_groups"]
        if len(groups) != 1:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "conflation expects exactly one qualifying route "
                        "group per fill site",
                        "site_id": site_id,
                        "group_count": len(groups),
                    },
                    sort_keys=True,
                )
            )
        group = groups[0]
        locked_features = _load_locked_nhs_site_features(site, fill_root / site_id)
        segment_lines = _segment_locked_lines(route_lock, site["segment_id"], cache_root)
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in segment_lines
        )

        measure_low = min(span[0] for span in group["measure_spans"])
        measure_high = max(span[1] for span in group["measure_spans"])
        predicate = _conflation_margin_predicate(
            group["state_fips"], group["route_id"], measure_low, measure_high
        )
        # The hosted NHS service intermittently answers a valid attribute query
        # with HTTP 400 and succeeds on the identical retry (observed three
        # times on 2026-08-31, each request verified valid out of band). A 400
        # is not in the shared transport's retryable set because it normally
        # means a bad predicate, so the bounded retry lives here: the predicate
        # is machine-built from locked inputs, and a genuine parameter error
        # still fails after the last attempt.
        margin: NhpnAcquisitionResult | None = None
        for attempt in range(3):
            try:
                margin = acquire_nhpn(
                    transport,
                    query_url,
                    {"where": predicate},
                    conflation_root / site_id,
                    page_size=page_size,
                )
                break
            except ValueError as error:
                if "'code': 400" not in str(error) or attempt == 2:
                    raise
        assert margin is not None
        margin_features = {
            int(feature["attributes"]["OBJECTID"]): feature
            for feature in margin.features
        }
        group_ids = sorted(record["object_id"] for record in group["records"])
        missing = [
            object_id for object_id in group_ids if object_id not in margin_features
        ]
        if missing:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "margin acquisition no longer returns the locked "
                        "fill records",
                        "site_id": site_id,
                        "missing_object_ids": missing,
                    },
                    sort_keys=True,
                )
            )
        drifted = [
            object_id
            for object_id in group_ids
            if canonical_sha256(margin_features[object_id])
            != canonical_sha256(locked_features[object_id])
        ]
        if drifted:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "live NHS features drifted from the locked fill "
                        "cache",
                        "site_id": site_id,
                        "drifted_object_ids": drifted,
                    },
                    sort_keys=True,
                )
            )

        records: dict[int, dict[str, Any]] = {}
        for object_id in sorted(margin_features):
            attributes = margin_features[object_id]["attributes"]
            begin = float(attributes.get("BEGINPOINT") or 0.0)
            end = float(attributes.get("ENDPOINT") or 0.0)
            if end < begin:
                raise ValueError(
                    json.dumps(
                        {
                            "refusal": "NHS record measures run backwards",
                            "site_id": site_id,
                            "object_id": object_id,
                        },
                        sort_keys=True,
                    )
                )
            records[object_id] = {
                "object_id": object_id,
                "begin": begin,
                "end": end,
                "line": transform(
                    forward.transform, _merged_feature_line(margin_features[object_id])
                ),
            }

        orientation_entries: list[dict[str, Any]] = []
        for object_id in group_ids:
            record = records[object_id]
            orientation, evidence = _measure_adjacency_votes(
                record,
                [records[key] for key in sorted(records)],
                CONFLATION_ADJACENCY_GAP_METERS,
            )
            if orientation is None:
                raise ValueError(
                    json.dumps(
                        {
                            "refusal": "no measure-orientation evidence for a span "
                            "record",
                            "site_id": site_id,
                            "object_id": object_id,
                        },
                        sort_keys=True,
                    )
                )
            record["orientation"] = orientation
            orientation_entries.append(
                {
                    "object_id": object_id,
                    "orientation": orientation,
                    "evidence": evidence,
                }
            )

        seams: list[dict[str, Any]] = []
        seam_measures: list[float] = []
        for side, corner in (("from", "from_coordinate"), ("to", "to_coordinate")):
            seam_metric = forward.transform(
                site[corner]["longitude"], site[corner]["latitude"]
            )
            seam_point = Point(seam_metric)
            offset, seam_record = min(
                (
                    (records[object_id]["line"].distance(seam_point), records[object_id])
                    for object_id in group_ids
                ),
                key=lambda entry: (round(entry[0], 9), entry[1]["object_id"]),
            )
            if offset > CONFLATION_SEAM_OFFSET_BOUND_METERS:
                raise ValueError(
                    json.dumps(
                        {
                            "refusal": "seam offset exceeds the conflation bound",
                            "site_id": site_id,
                            "side": side,
                            "measured_offset_m": round(offset, 3),
                            "bound_m": CONFLATION_SEAM_OFFSET_BOUND_METERS,
                        },
                        sort_keys=True,
                    )
                )
            distance_along = float(seam_record["line"].project(seam_point))
            measure = _measure_at_distance(seam_record, distance_along)
            seam_measures.append(measure)
            nhpn = _nhpn_seam_correspondence(seam_metric, metric_lines, tolerance)
            seams.append(
                {
                    "side": side,
                    "coordinate": site[corner],
                    "nhs": {
                        "object_id": seam_record["object_id"],
                        "seam_offset_m": round(offset, 3),
                        "measure_at_seam": round(measure, 6),
                        "measure_interval": [
                            round(seam_record["begin"], 6),
                            round(seam_record["end"], 6),
                        ],
                        "orientation": seam_record["orientation"],
                    },
                    "nhpn": nhpn,
                    "within_bound": True,
                }
            )

        span_low, span_high = sorted(seam_measures)
        span = _assemble_conflation_span(
            [records[object_id] for object_id in group_ids], span_low, span_high
        )
        if span["max_joint_gap_m"] > CONFLATION_ADJACENCY_GAP_METERS:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "span pieces do not join within the adjacency "
                        "tolerance",
                        "site_id": site_id,
                        "max_joint_gap_m": span["max_joint_gap_m"],
                        "bound_m": CONFLATION_ADJACENCY_GAP_METERS,
                    },
                    sort_keys=True,
                )
            )
        span_line = span["line"]
        # Rounded before the ratio so the offline validator reproduces it.
        geometry_length = round(float(span_line.length), 3)
        measure_length = round((span_high - span_low) * METRES_PER_MILE, 3)
        distortion = (
            abs(geometry_length - measure_length) / measure_length
            if measure_length > 0
            else float("inf")
        )
        miles_by_id = {
            record["object_id"]: float(record["miles"]) for record in group["records"]
        }
        records_checked: list[dict[str, Any]] = []
        for object_id in sorted({piece["object_id"] for piece in span["pieces"]}):
            # Computed from the recorded (rounded) length so the offline
            # validator reproduces the ratio exactly.
            record_geometry_m = round(float(records[object_id]["line"].length), 3)
            record_miles_m = miles_by_id[object_id] * METRES_PER_MILE
            record_ratio = (
                abs(record_geometry_m - record_miles_m) / record_miles_m
                if record_miles_m > 0
                else float("inf")
            )
            if record_ratio > CONFLATION_GEOMETRY_MILES_AGREEMENT_RATIO:
                raise ValueError(
                    json.dumps(
                        {
                            "refusal": "record geometry disagrees with the source's "
                            "own MILES length",
                            "site_id": site_id,
                            "object_id": object_id,
                            "measured_ratio": round(record_ratio, 6),
                            "bound": CONFLATION_GEOMETRY_MILES_AGREEMENT_RATIO,
                        },
                        sort_keys=True,
                    )
                )
            records_checked.append(
                {
                    "object_id": object_id,
                    "miles": miles_by_id[object_id],
                    "geometry_length_m": record_geometry_m,
                    "geometry_miles_ratio": round(record_ratio, 6),
                }
            )
        agreement = _span_nhpn_agreement(
            span_line,
            metric_lines,
            CONFLATION_STATION_SPACING_METERS,
            NHS_PROXIMITY_LENS_METERS,
        )
        sites.append(
            {
                "site_id": site_id,
                "segment_id": site["segment_id"],
                "facility": site["facility"],
                "group": {
                    "state_fips": group["state_fips"],
                    "route_id": group["route_id"],
                    "signed_routes": group["signed_routes"],
                },
                "margin_acquisition": {
                    "predicate": predicate,
                    "acquired_at": timestamp,
                    "page_size": page_size,
                    "expected_count": margin.expected_count,
                    "object_ids": list(margin.object_ids),
                    "object_ids_sha256": canonical_sha256(list(margin.object_ids)),
                    "features_sha256": canonical_sha256(list(margin.features)),
                    "pages": _page_records(margin, conflation_root / site_id, page_size),
                    "retries": margin.retries,
                    "resumed_pages": margin.resumed_pages,
                    "locked_records_reproduced": True,
                },
                "orientation": orientation_entries,
                "seams": seams,
                "span": {
                    "measure_low": round(span_low, 6),
                    "measure_high": round(span_high, 6),
                    "measure_delta_miles": round(span_high - span_low, 6),
                    "measure_length_m": round(measure_length, 3),
                    "geometry_length_m": round(geometry_length, 3),
                    "measure_axis_distortion_ratio": round(distortion, 6),
                    "records_checked": records_checked,
                    "max_record_geometry_miles_ratio": round(
                        max(
                            record["geometry_miles_ratio"] for record in records_checked
                        ),
                        6,
                    ),
                    "max_piece_joint_gap_m": span["max_joint_gap_m"],
                    "pieces": span["pieces"],
                    "geometry_sha256": canonical_sha256(
                        [
                            [round(x, 3), round(y, 3)]
                            for x, y in span_line.coords
                        ]
                    ),
                    **agreement,
                },
            }
        )

    seam_offsets = [
        seam["nhs"]["seam_offset_m"] for entry in sites for seam in entry["seams"]
    ]
    payload = {
        "schema_version": 1,
        "status": NHS_CONFLATION_LOCK_STATUS,
        "decision": "ADR-0026",
        "route_decision": selection["decision"],
        "acquired_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "nhs": fill_lock["nhs"],
        "ancestry": fill_lock["ancestry"],
        "source_policy": dict(CONFLATION_SOURCE_POLICY),
        "model": {
            "seam_offset_bound_m": CONFLATION_SEAM_OFFSET_BOUND_METERS,
            "station_spacing_m": CONFLATION_STATION_SPACING_METERS,
            "geometry_miles_agreement_bound": CONFLATION_GEOMETRY_MILES_AGREEMENT_RATIO,
            "adjacency_gap_m": CONFLATION_ADJACENCY_GAP_METERS,
            "measure_margin_miles": CONFLATION_MEASURE_MARGIN_MILES,
            "nhpn_proximity_lens_m": NHS_PROXIMITY_LENS_METERS,
            "measure_space": "state-LRS route measures (STFIPS, ROUTEID, measure)",
            "measure_axis_note": (
                "The state-LRS measure axis is calibrated, not metric: per-record "
                "measure extents diverge from planimetric length by up to 43% on "
                "the locked fill records while the source's own MILES field "
                "agrees with its geometry within about 1%. Measures parametrise "
                "the span and key the correspondence; they are never a length, "
                "and the length bound is between geometry and MILES."
            ),
            "hpms_reuse": {
                "decision": "ADR-0026",
                "keyed_on": ["state_fips", "route_id", "measure"],
                "note": (
                    "HPMS extracts the same ARNOLD substrate, so every seam "
                    "correspondence and span parametrisation here is keyed on the "
                    "ARNOLD LRS identity and reusable unchanged if HPMS is adopted."
                ),
            },
        },
        "endpoint_snap_tolerance_m": tolerance,
        "westbound_selection_validated": False,
        "site_count": len(sites),
        "sites": sites,
        "sites_sha256": canonical_sha256(sites),
        "summary": {
            "seam_count": len(seam_offsets),
            "seams_within_bound": len(seam_offsets),
            "max_seam_offset_m": max(seam_offsets) if seam_offsets else 0.0,
            "max_record_geometry_miles_ratio": max(
                entry["span"]["max_record_geometry_miles_ratio"] for entry in sites
            ),
            "max_measure_axis_distortion_ratio": max(
                entry["span"]["measure_axis_distortion_ratio"] for entry in sites
            ),
            "total_span_meters": round(
                sum(entry["span"]["geometry_length_m"] for entry in sites), 3
            ),
            "sites_with_nhpn_void": sum(
                1 for entry in sites if entry["span"]["nhpn_void_runs"]
            ),
        },
        "next_stage": NHS_CONFLATION_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_nhs_conflation(
    conflation_path: Path,
    fill_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the conflation lock without the ignored response caches."""
    payload = load_json(conflation_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported NHS conflation lock schema.")
    if payload.get("status") != NHS_CONFLATION_LOCK_STATUS:
        raise ValueError("NHS conflation lock has an unsupported status.")
    if payload.get("decision") != "ADR-0026":
        raise ValueError("NHS conflation lock does not cite ADR-0026.")
    if payload.get("westbound_selection_validated") is not False:
        raise ValueError(
            "NHS conflation lock claims a validated westbound selection, which "
            "this stage cannot establish."
        )
    fill_lock = validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    selection = load_json(selection_path)
    if payload.get("route_decision") != selection.get("decision"):
        raise ValueError("NHS conflation lock decision does not match the selection.")
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("NHS conflation lock input hash drifted.")
    if payload.get("nhs") != fill_lock["nhs"]:
        raise ValueError("NHS conflation lock service identity drifted from the fill lock.")
    if payload.get("ancestry") != fill_lock["ancestry"]:
        raise ValueError("NHS conflation lock does not carry the ADR-0026 dual ancestry.")
    if payload.get("source_policy") != CONFLATION_SOURCE_POLICY:
        raise ValueError("NHS conflation lock source policy is incomplete.")
    if payload.get("endpoint_snap_tolerance_m") != fill_lock["endpoint_snap_tolerance_m"]:
        raise ValueError("NHS conflation lock declares a drifted endpoint tolerance.")
    model = payload.get("model", {})
    expected_model_constants = {
        "seam_offset_bound_m": CONFLATION_SEAM_OFFSET_BOUND_METERS,
        "station_spacing_m": CONFLATION_STATION_SPACING_METERS,
        "geometry_miles_agreement_bound": CONFLATION_GEOMETRY_MILES_AGREEMENT_RATIO,
        "adjacency_gap_m": CONFLATION_ADJACENCY_GAP_METERS,
        "measure_margin_miles": CONFLATION_MEASURE_MARGIN_MILES,
        "nhpn_proximity_lens_m": NHS_PROXIMITY_LENS_METERS,
    }
    if any(model.get(key) != value for key, value in expected_model_constants.items()):
        raise ValueError("NHS conflation model constants drifted.")
    if not str(model.get("measure_axis_note", "")).strip():
        raise ValueError(
            "NHS conflation model does not record the calibrated measure-axis "
            "characterisation."
        )
    hpms = model.get("hpms_reuse", {})
    if hpms.get("decision") != "ADR-0026" or hpms.get("keyed_on") != [
        "state_fips",
        "route_id",
        "measure",
    ]:
        raise ValueError("NHS conflation lock does not record the ADR-0026 HPMS reuse key.")

    fill_sites_by_id = {site["site_id"]: site for site in fill_lock["sites"]}
    max_record_count = int(fill_lock["nhs"]["service"]["max_record_count"])
    nhpn_page_hashes = _locked_page_hashes_by_object_id(
        validate_continental_route_lock(route_lock_path, catalog_path, selection_path)
    )
    sites = payload.get("sites")
    if not isinstance(sites, list) or {entry.get("site_id") for entry in sites} != set(
        fill_sites_by_id
    ):
        raise ValueError(
            "NHS conflation lock does not cover exactly the locked fill sites."
        )
    if payload.get("site_count") != len(sites):
        raise ValueError("NHS conflation lock site count does not reconcile.")
    if canonical_sha256(sites) != payload.get("sites_sha256"):
        raise ValueError("NHS conflation lock site digest drifted.")

    seam_offsets: list[float] = []
    ratios: list[float] = []
    distortions: list[float] = []
    span_total = 0.0
    void_sites = 0
    for entry in sites:
        site_id = entry["site_id"]
        fill_site = fill_sites_by_id[site_id]
        group = fill_site["fill_route_groups"][0]
        if entry.get("segment_id") != fill_site["segment_id"] or entry.get(
            "facility"
        ) != fill_site["facility"]:
            raise ValueError(f"Conflation site '{site_id}' identity drifted.")
        recorded_group = entry.get("group", {})
        if (
            recorded_group.get("state_fips") != group["state_fips"]
            or recorded_group.get("route_id") != group["route_id"]
            or recorded_group.get("signed_routes") != group["signed_routes"]
        ):
            raise ValueError(f"Conflation site '{site_id}' route group drifted.")
        group_ids = {record["object_id"] for record in group["records"]}
        margin = entry.get("margin_acquisition", {})
        measure_low = min(span[0] for span in group["measure_spans"])
        measure_high = max(span[1] for span in group["measure_spans"])
        expected_predicate = _conflation_margin_predicate(
            group["state_fips"], group["route_id"], measure_low, measure_high
        )
        if margin.get("predicate") != expected_predicate:
            raise ValueError(f"Conflation site '{site_id}' margin predicate drifted.")
        if margin.get("locked_records_reproduced") is not True:
            raise ValueError(
                f"Conflation site '{site_id}' does not assert locked-record "
                "reproduction."
            )
        _validate_acquisition_record(
            margin, f"conflation margin '{site_id}'", max_record_count
        )
        margin_ids = set(margin["object_ids"])
        if not group_ids <= margin_ids:
            raise ValueError(
                f"Conflation site '{site_id}' margin does not cover the locked "
                "fill records."
            )
        orientation_by_id: dict[int, str] = {}
        for record in entry.get("orientation", []):
            object_id = record.get("object_id")
            orientation = record.get("orientation")
            if object_id not in group_ids or orientation not in {"forward", "reversed"}:
                raise ValueError(
                    f"Conflation site '{site_id}' orientation entry is invalid."
                )
            votes = [
                item
                for item in record.get("evidence", [])
                if item.get("vote") in {"forward", "reversed"}
            ]
            if not votes or any(
                item.get("endpoint_gap_m", float("inf")) > CONFLATION_ADJACENCY_GAP_METERS
                or item.get("vote") != orientation
                for item in votes
            ):
                raise ValueError(
                    f"Conflation site '{site_id}' orientation evidence does not "
                    "support its claim."
                )
            orientation_by_id[object_id] = orientation
        seams = entry.get("seams", [])
        if [seam.get("side") for seam in seams] != ["from", "to"]:
            raise ValueError(f"Conflation site '{site_id}' does not record both seams.")
        seam_measures: list[float] = []
        for seam, corner in zip(seams, ("from_coordinate", "to_coordinate"), strict=True):
            if seam.get("coordinate") != fill_site[corner]:
                raise ValueError(
                    f"Conflation site '{site_id}' seam coordinate drifted from the "
                    "fill lock."
                )
            nhs = seam.get("nhs", {})
            offset = nhs.get("seam_offset_m")
            if (
                not isinstance(offset, int | float)
                or isinstance(offset, bool)
                or not math.isfinite(offset)
                or offset < 0
                or offset > CONFLATION_SEAM_OFFSET_BOUND_METERS
                or seam.get("within_bound") is not True
            ):
                raise ValueError(
                    f"Conflation site '{site_id}' seam offset violates the bound."
                )
            if nhs.get("object_id") not in group_ids:
                raise ValueError(
                    f"Conflation site '{site_id}' seam cites an unlocked NHS record."
                )
            if orientation_by_id.get(nhs.get("object_id")) != nhs.get("orientation"):
                raise ValueError(
                    f"Conflation site '{site_id}' seam orientation is unsupported."
                )
            measure = nhs.get("measure_at_seam")
            if (
                not isinstance(measure, int | float)
                or isinstance(measure, bool)
                or not math.isfinite(measure)
                or not (
                    measure_low - MILEPOST_QUANTUM_MILES
                    <= measure
                    <= measure_high + MILEPOST_QUANTUM_MILES
                )
            ):
                raise ValueError(
                    f"Conflation site '{site_id}' seam measure is outside the "
                    "locked span."
                )
            seam_measures.append(float(measure))
            seam_offsets.append(float(offset))
            nhpn = seam.get("nhpn", {})
            matches = nhpn.get("matches")
            correspondence = nhpn.get("correspondence", {})
            if not isinstance(matches, list) or not matches:
                raise ValueError(
                    f"Conflation site '{site_id}' seam has no NHPN endpoint match."
                )
            for match in matches:
                expected_hash = nhpn_page_hashes.get(match.get("object_id"))
                if expected_hash is None or match.get(
                    "page_response_sha256"
                ) not in expected_hash:
                    raise ValueError(
                        f"Conflation site '{site_id}' cites an unlocked NHPN record."
                    )
                distance = match.get("endpoint_distance_m")
                if (
                    not isinstance(distance, int | float)
                    or isinstance(distance, bool)
                    or not 0
                    <= distance
                    <= fill_lock["endpoint_snap_tolerance_m"]
                ):
                    raise ValueError(
                        f"Conflation site '{site_id}' NHPN endpoint match exceeds "
                        "the endpoint tolerance."
                    )
            if correspondence.get("object_id") != matches[0].get("object_id"):
                raise ValueError(
                    f"Conflation site '{site_id}' NHPN correspondence is not the "
                    "nearest endpoint match."
                )
            milepost = correspondence.get("milepost_at_seam")
            if milepost is not None:
                interval = sorted(correspondence.get("record_milepost_interval", []))
                if len(interval) != 2 or not (
                    interval[0] <= milepost <= interval[1]
                ):
                    raise ValueError(
                        f"Conflation site '{site_id}' seam milepost is outside its "
                        "record interval."
                    )
                if correspondence.get("orientation") not in {"forward", "reversed"}:
                    raise ValueError(
                        f"Conflation site '{site_id}' claims a seam milepost "
                        "without orientation evidence."
                    )
        span = entry.get("span", {})
        expected_low, expected_high = sorted(seam_measures)
        if (
            span.get("measure_low") != round(expected_low, 6)
            or span.get("measure_high") != round(expected_high, 6)
        ):
            raise ValueError(
                f"Conflation site '{site_id}' span does not run seam to seam."
            )
        miles_by_id = {
            record["object_id"]: record["miles"] for record in group["records"]
        }
        records_checked = span.get("records_checked")
        if not isinstance(records_checked, list) or not records_checked:
            raise ValueError(
                f"Conflation site '{site_id}' span records no geometry-MILES "
                "checks."
            )
        checked_ids = set()
        for check in records_checked:
            object_id = check.get("object_id")
            if object_id not in group_ids or check.get("miles") != miles_by_id.get(
                object_id
            ):
                raise ValueError(
                    f"Conflation site '{site_id}' geometry-MILES check cites an "
                    "unlocked record."
                )
            miles_m = float(check["miles"]) * METRES_PER_MILE
            geometry_m = check.get("geometry_length_m")
            check_ratio = check.get("geometry_miles_ratio")
            if (
                not isinstance(geometry_m, int | float)
                or isinstance(geometry_m, bool)
                or not math.isfinite(geometry_m)
                or geometry_m <= 0
                or not isinstance(check_ratio, int | float)
                or isinstance(check_ratio, bool)
                or round(abs(geometry_m - miles_m) / miles_m, 6) != check_ratio
                or check_ratio > CONFLATION_GEOMETRY_MILES_AGREEMENT_RATIO
            ):
                raise ValueError(
                    f"Conflation site '{site_id}' violates the geometry-MILES "
                    "agreement bound."
                )
            checked_ids.add(object_id)
        if span.get("max_record_geometry_miles_ratio") != max(
            check["geometry_miles_ratio"] for check in records_checked
        ):
            raise ValueError(
                f"Conflation site '{site_id}' geometry-MILES maximum does not "
                "reconcile."
            )
        distortion = span.get("measure_axis_distortion_ratio")
        measure_length = span.get("measure_length_m")
        geometry_length = span.get("geometry_length_m")
        if (
            not isinstance(distortion, int | float)
            or isinstance(distortion, bool)
            or not math.isfinite(distortion)
            or not isinstance(measure_length, int | float)
            or not isinstance(geometry_length, int | float)
            or measure_length <= 0
            or round(abs(geometry_length - measure_length) / measure_length, 6)
            != distortion
        ):
            raise ValueError(
                f"Conflation site '{site_id}' measure-axis characterisation does "
                "not reconcile."
            )
        joint_gap = span.get("max_piece_joint_gap_m")
        if (
            not isinstance(joint_gap, int | float)
            or isinstance(joint_gap, bool)
            or not 0 <= joint_gap <= CONFLATION_ADJACENCY_GAP_METERS
        ):
            raise ValueError(
                f"Conflation site '{site_id}' span pieces violate the adjacency "
                "bound."
            )
        pieces = span.get("pieces")
        if not isinstance(pieces, list) or not pieces:
            raise ValueError(f"Conflation site '{site_id}' span has no pieces.")
        cursor = span["measure_low"]
        for piece in pieces:
            if piece.get("object_id") not in group_ids:
                raise ValueError(
                    f"Conflation site '{site_id}' span cites an unlocked record."
                )
            piece_range = piece.get("measure_range", [])
            if (
                len(piece_range) != 2
                or piece_range[0] < cursor - 1e-6
                or piece_range[1] <= piece_range[0]
            ):
                raise ValueError(
                    f"Conflation site '{site_id}' span pieces are not contiguous "
                    "ascending."
                )
            if orientation_by_id.get(piece["object_id"]) is None:
                raise ValueError(
                    f"Conflation site '{site_id}' span piece has no orientation."
                )
            cursor = piece_range[1]
        if abs(cursor - span["measure_high"]) > 1e-5:
            raise ValueError(
                f"Conflation site '{site_id}' span pieces do not reach the far seam."
            )
        if {piece["object_id"] for piece in pieces} != checked_ids:
            raise ValueError(
                f"Conflation site '{site_id}' geometry-MILES checks do not cover "
                "exactly the span records."
            )
        if not SHA256_PATTERN.fullmatch(str(span.get("geometry_sha256", ""))):
            raise ValueError(f"Conflation site '{site_id}' span digest is invalid.")
        if span.get("station_count") != span.get("stations_within_nhpn_lens", 0) + span.get(
            "stations_beyond_nhpn_lens", 0
        ):
            raise ValueError(
                f"Conflation site '{site_id}' station counts do not reconcile."
            )
        ratios.append(float(span["max_record_geometry_miles_ratio"]))
        distortions.append(float(distortion))
        span_total += float(span.get("geometry_length_m", 0.0))
        if span.get("nhpn_void_runs"):
            void_sites += 1
    summary = payload.get("summary", {})
    expected_summary = {
        "seam_count": len(seam_offsets),
        "seams_within_bound": len(seam_offsets),
        "max_seam_offset_m": max(seam_offsets) if seam_offsets else 0.0,
        "max_record_geometry_miles_ratio": max(ratios) if ratios else 0.0,
        "max_measure_axis_distortion_ratio": max(distortions) if distortions else 0.0,
        "total_span_meters": round(span_total, 3),
        "sites_with_nhpn_void": void_sites,
    }
    if summary != expected_summary:
        raise ValueError("NHS conflation lock summary does not reconcile.")
    if payload.get("next_stage") != NHS_CONFLATION_NEXT_STAGE:
        raise ValueError("NHS conflation lock next stage drifted.")
    return payload


def _locked_page_hashes_by_object_id(
    route_lock: dict[str, Any],
) -> dict[int, set[str]]:
    """Every locked OBJECTID's admissible page-response hashes, base and supplements."""
    hashes: dict[int, set[str]] = {}
    nhpn = route_lock["nhpn"]
    for record in (*nhpn["segment_snapshots"], *nhpn.get("supplementary_acquisitions", [])):
        object_ids = record["object_ids"]
        for page in record["pages"]:
            offset = page["object_id_offset"]
            page_hash = page["canonical_response_sha256"]
            for object_id in object_ids[offset : offset + page["feature_count"]]:
                hashes.setdefault(object_id, set()).add(page_hash)
    return hashes


# --- ADR-0007 3DEP product lock over the closed corridor --------------------------
#
# The geodata law is exact: 3DEP supplies elevation only after product,
# resolution, date, horizontal datum, and vertical datum are locked. This stage
# locks the catalog's declared 1/3 arc-second baseline product per ADR-0007 for
# every 1x1 degree cell the closed corridor traverses: exact dated product URLs
# from the catalog's discovery API, publication dates, and per-tile FGDC datum
# evidence fetched from inside the catalog's allowed prefixes, with a
# deterministic sample of full tiles verified end to end (checksum plus raster
# inspection). The lock is the deliverable; the corridor-wide raster download is
# a later acquisition against these exact URLs and checksummed expectations.

DEM_SOURCE_ID = "usgs-3dep"
DEM_PRODUCT_LOCK_STATUS = "3dep_products_locked_elevation_acquisition_pending"
DEM_PRODUCT_NEXT_STAGE = {
    "id": "westbound-selection-and-reconstruction",
    "requires": [
        "westbound directed edge selection over the closed topology",
        "corridor elevation acquisition against the locked product URLs",
    ],
}

# Discovery inset: the bbox sent per cell is the cell shrunk by this margin so
# that only products staged for that cell intersect it (tile bounding boxes
# overhang their nominal cell by roughly 0.002 degrees, far inside the inset).
DEM_CELL_INSET_DEGREES = 0.1

# A locked product must cover its whole nominal cell within this margin.
DEM_COVER_EPSILON_DEGREES = 0.01

DEM_EXPECTED_RESOLUTION = "1/3 arc-second"
DEM_EXPECTED_RASTER_EPSG = 4269
DEM_EXPECTED_HORIZONTAL_DATUM = "North American Datum of 1983"
DEM_EXPECTED_VERTICAL_DATUM = "North American Vertical Datum of 1988"
DEM_EXPECTED_ELEVATION_UNITS = "meters"
DEM_EXPECTED_NODATA = -999999.0
DEM_PIXEL_DEGREES = 1.0 / 10_800.0
# The staged products encode the cell size with about nine significant digits
# (observed 9.25925927753796e-05 against the exact 1/10800), so the agreement
# tolerance is one part per million - far tighter than the 3x gap to the next
# product family, far looser than the source's own encoding noise.
DEM_PIXEL_RELATIVE_TOLERANCE = 1e-6
DEM_DISCOVERY_MAX = 100
DEM_SAMPLE_POLICY = (
    "deterministic sample: the first, middle, and last cell of the sorted "
    "corridor cell list, downloaded in full, checksummed, and raster-inspected"
)
DEM_CELL_ID_PATTERN = re.compile(r"^n(\d{2})w(\d{3})$")
DEM_SELECTION_POLICY = (
    "among discovered GeoTIFF products of the catalog dataset whose bounding "
    "box covers the cell and whose download URL is inside the catalog "
    "allowlist, select the latest publication date; ties resolve to the "
    "lexically first sourceId"
)

DEM_PRODUCT_SOURCE_POLICY = {
    "elevation_source": DEM_SOURCE_ID,
    "baseline_decision": "ADR-0007",
    "one_meter_upgrade": "remains gated per ADR-0007 and is not locked here",
    "opportunistic_lookup_allowed": False,
    "silent_resolution_fallback_allowed": False,
    "continental_downloads_committed": False,
    "authoritative_distance_claimed": False,
}


@dataclass(frozen=True)
class DemFetchResult:
    status: int
    content_type: str
    etag: str
    last_modified: str
    sha256: str
    byte_count: int
    body: bytes | None


class DemTransport(Protocol):
    def fetch(self, url: str, destination: Path | None = None) -> DemFetchResult: ...


class UrllibDemTransport:
    """HTTPS GET transport for the 3DEP discovery API, metadata, and tiles.

    The TNM discovery API intermittently answers 5xx; transient statuses and
    network failures are retried with bounded backoff, mirroring the ArcGIS
    transport's retryable set. A non-transient status raises immediately.
    """

    RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(self, timeout_seconds: float = 300.0, attempts: int = 5) -> None:
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts

    def fetch(self, url: str, destination: Path | None = None) -> DemFetchResult:
        for attempt in range(self.attempts):
            try:
                return self._fetch_once(url, destination)
            except urllib.error.HTTPError as error:
                if error.code not in self.RETRYABLE_STATUSES:
                    raise ValueError(
                        f"3DEP request failed with status {error.code}: {url}"
                    ) from error
                if attempt + 1 == self.attempts:
                    raise ValueError(
                        f"3DEP request kept failing with status {error.code} after "
                        f"{self.attempts} attempts: {url}"
                    ) from error
                time.sleep(min(0.5 * (2**attempt), 8.0))
            except OSError as error:
                if attempt + 1 == self.attempts:
                    raise ValueError(
                        f"3DEP request kept failing after {self.attempts} "
                        f"attempts: {url}"
                    ) from error
                time.sleep(min(0.5 * (2**attempt), 8.0))
        raise AssertionError("retry loop did not return")

    def _fetch_once(self, url: str, destination: Path | None) -> DemFetchResult:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            headers = response.headers
            hasher = hashlib.sha256()
            byte_count = 0
            body: bytes | None
            if destination is None:
                body = response.read()
                hasher.update(body)
                byte_count = len(body)
            else:
                body = None
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                with temporary.open("wb") as sink:
                    while True:
                        chunk = response.read(1 << 20)
                        if not chunk:
                            break
                        hasher.update(chunk)
                        byte_count += len(chunk)
                        sink.write(chunk)
                temporary.replace(destination)
            return DemFetchResult(
                status=response.status,
                content_type=headers.get("Content-Type", ""),
                etag=headers.get("ETag", ""),
                last_modified=headers.get("Last-Modified", ""),
                sha256=hasher.hexdigest(),
                byte_count=byte_count,
                body=body,
            )


def _dem_cell_id(cell: tuple[int, int]) -> str:
    """The USGS staged-product cell name for one 1x1 degree CONUS cell."""
    west, south = cell
    if not (-125 <= west <= -66 and 24 <= south <= 49):
        raise ValueError(f"Corridor cell is outside CONUS: {cell}")
    return f"n{south + 1:02d}w{-west:03d}"


def _dem_cell_bounds(cell_id: str) -> tuple[int, int, int, int]:
    match = DEM_CELL_ID_PATTERN.fullmatch(cell_id)
    if match is None:
        raise ValueError(f"Invalid 3DEP cell id: {cell_id}")
    north = int(match.group(1))
    west = -int(match.group(2))
    return west, north - 1, west + 1, north


def _cells_intersecting_line(line: LineString, cells: set[tuple[int, int]]) -> None:
    minx, miny, maxx, maxy = line.bounds
    for west in range(math.floor(minx), math.floor(maxx) + 1):
        for south in range(math.floor(miny), math.floor(maxy) + 1):
            if (west, south) in cells:
                continue
            if box(west, south, west + 1, south + 1).intersects(line):
                cells.add((west, south))


def _chained_segment_path_edges(
    segment: dict[str, Any],
    metric_lines: tuple[tuple[LockedCandidateLine, LineString], ...],
    from_point: tuple[float, float],
    to_point: tuple[float, float],
    tolerance: float,
    anchor_limit: float,
    fill_sites: Sequence[dict[str, Any]],
    overlay_sites: Sequence[dict[str, Any]],
    forward: Transformer,
) -> dict[str, Any]:
    """The NHPN edges one chained segment's mixed-ancestry chain traverses.

    Rebuilds the same snapped graph, fill and overlay bridges, and anchor
    resolution the chain-connectivity model uses, and returns the traversed
    NHPN (object_id, part_index) pairs plus the chord totals so the caller can
    prove the walk reproduces the locked chain exactly.
    """
    graph, nodes, _, _ = _build_snapped_endpoint_graph(metric_lines, tolerance)

    def nearest_node(point: tuple[float, float]) -> tuple[tuple[int, int], float]:
        best_key, best_distance = None, float("inf")
        for key in sorted(nodes):
            distance = math.dist(point, nodes[key])
            if distance < best_distance:
                best_key, best_distance = key, distance
        assert best_key is not None
        return best_key, best_distance

    def bridge(site: dict[str, Any], data_key: str) -> None:
        ends = []
        for corner in ("from_coordinate", "to_coordinate"):
            point = forward.transform(
                site[corner]["longitude"], site[corner]["latitude"]
            )
            node, distance = nearest_node(point)
            if distance > tolerance:
                raise ValueError(
                    f"Bridge '{site['site_id']}' {corner} does not land on a locked "
                    f"chain end within the {tolerance:g} m tolerance."
                )
            ends.append(node)
        graph.add_edge(
            ends[0],
            ends[1],
            key=(data_key, site["site_id"]),
            weight=float(site["separation_m"]),
            **{f"{data_key}_site_id": site["site_id"]},
        )

    for site in sorted(fill_sites, key=lambda entry: entry["site_id"]):
        bridge(site, "fill")
    for site in sorted(overlay_sites, key=lambda entry: entry["site_id"]):
        bridge(site, "overlay")

    from_key, from_distance, _ = _resolve_anchor_node(
        graph, nodes, metric_lines, from_point, "from", tolerance, anchor_limit
    )
    to_key, to_distance, _ = _resolve_anchor_node(
        graph, nodes, metric_lines, to_point, "to", tolerance, anchor_limit
    )
    if max(from_distance, to_distance) > anchor_limit or from_key == to_key:
        raise ValueError(
            f"Chained segment '{segment['id']}' anchors did not resolve onto the "
            "bridged graph."
        )
    if not nx.has_path(graph, from_key, to_key):
        raise ValueError(
            f"Chained segment '{segment['id']}' has no path on the bridged graph."
        )
    node_path = nx.shortest_path(graph, from_key, to_key, weight="weight")
    nhpn_edges: list[tuple[int, int]] = []
    nhpn_meters = 0.0
    fill_meters = 0.0
    overlay_meters = 0.0
    fill_ids: list[str] = []
    overlay_ids: list[str] = []
    for previous, current in zip(node_path, node_path[1:], strict=False):
        parallel = graph.get_edge_data(previous, current)
        chosen_key = min(
            parallel,
            key=lambda edge_key: (parallel[edge_key]["weight"], str(edge_key)),
        )
        data = parallel[chosen_key]
        if "fill_site_id" in data:
            fill_meters += data["weight"]
            fill_ids.append(data["fill_site_id"])
        elif "overlay_site_id" in data:
            overlay_meters += data["weight"]
            overlay_ids.append(data["overlay_site_id"])
        else:
            nhpn_meters += data["weight"]
            nhpn_edges.append((int(data["object_id"]), int(data["part_index"])))
    return {
        "nhpn_edges": nhpn_edges,
        "nhpn_path_meters": round(nhpn_meters, 3),
        "fill_chord_meters": round(fill_meters, 3),
        "overlay_chord_meters": round(overlay_meters, 3),
        "chain_length_meters": round(nhpn_meters + fill_meters + overlay_meters, 3),
        "fill_site_ids_on_chain": sorted(fill_ids),
        "overlay_site_ids_on_chain": sorted(overlay_ids),
    }


def _dem_discovery_request(
    dataset: str, product_format: str, extent: str, cell: tuple[int, int]
) -> dict[str, Any]:
    west, south = cell
    bbox = (
        f"{west + DEM_CELL_INSET_DEGREES},{south + DEM_CELL_INSET_DEGREES},"
        f"{west + 1 - DEM_CELL_INSET_DEGREES},{south + 1 - DEM_CELL_INSET_DEGREES}"
    )
    return {
        "datasets": dataset,
        "prodFormats": product_format,
        "prodExtents": extent,
        "bbox": bbox,
        "outputFormat": "JSON",
        "max": DEM_DISCOVERY_MAX,
        "offset": 0,
    }


def _select_dem_product(
    items: Sequence[dict[str, Any]],
    cell: tuple[int, int],
    extent: str,
    allowed_prefixes: Sequence[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The deterministic product selection for one cell, with its candidates."""
    west, south = cell
    candidates: list[dict[str, Any]] = []
    for item in items:
        if item.get("format") != "GeoTIFF" or item.get("extent") != extent:
            continue
        bounding_box = item.get("boundingBox") or {}
        try:
            covers = (
                float(bounding_box["minX"]) <= west + DEM_COVER_EPSILON_DEGREES
                and float(bounding_box["maxX"]) >= west + 1 - DEM_COVER_EPSILON_DEGREES
                and float(bounding_box["minY"]) <= south + DEM_COVER_EPSILON_DEGREES
                and float(bounding_box["maxY"]) >= south + 1 - DEM_COVER_EPSILON_DEGREES
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not covers:
            continue
        download_url = str(item.get("downloadURL") or "")
        if not any(
            url_matches_prefix(download_url, prefix) for prefix in allowed_prefixes
        ):
            continue
        publication_date = str(item.get("publicationDate") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication_date):
            continue
        candidates.append(
            {
                "source_id": str(item.get("sourceId") or ""),
                "title": str(item.get("title") or ""),
                "publication_date": publication_date,
                "download_url": download_url,
                "size_bytes": int(item.get("sizeInBytes") or 0),
                "bounding_box": [
                    round(float(bounding_box["minX"]), 8),
                    round(float(bounding_box["minY"]), 8),
                    round(float(bounding_box["maxX"]), 8),
                    round(float(bounding_box["maxY"]), 8),
                ],
            }
        )
    if not candidates:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "discovery returned no covering catalog product",
                    "cell_id": _dem_cell_id(cell),
                },
                sort_keys=True,
            )
        )
    latest = max(candidate["publication_date"] for candidate in candidates)
    selected = min(
        (candidate for candidate in candidates if candidate["publication_date"] == latest),
        key=lambda candidate: candidate["source_id"],
    )
    summary = sorted(
        (
            {
                "source_id": candidate["source_id"],
                "publication_date": candidate["publication_date"],
            }
            for candidate in candidates
        ),
        key=lambda candidate: (candidate["publication_date"], candidate["source_id"]),
    )
    return selected, summary


def _parse_dem_fgdc_metadata(body_text: str) -> dict[str, Any]:
    """The datum and resolution assertions of one tile's FGDC metadata."""

    def field(tag: str) -> str:
        match = re.search(rf"<{tag}>([^<]*)</{tag}>", body_text)
        return match.group(1).strip() if match else ""

    horizontal = field("horizdn")
    vertical = field("altdatum")
    units = field("altunits")
    if not horizontal or not vertical or not units:
        raise ValueError("FGDC metadata does not state the product datums.")
    resolutions = {}
    for tag, key in (
        ("latres", "latitude_resolution_deg"),
        ("longres", "longitude_resolution_deg"),
    ):
        raw = field(tag)
        if raw:
            value = abs(float(raw))
            if abs(value - DEM_PIXEL_DEGREES) / DEM_PIXEL_DEGREES > DEM_PIXEL_RELATIVE_TOLERANCE:
                raise ValueError(
                    f"FGDC {tag} {value!r} is not the 1/3 arc-second cell size."
                )
            resolutions[key] = value
    return {
        "horizontal_datum": horizontal,
        "vertical_datum": vertical,
        "elevation_units": units,
        "metadata_publication_date": field("pubdate"),
        **resolutions,
    }


def _inspect_dem_raster(path: Path, cell_id: str) -> dict[str, Any]:
    """Raster-level verification of one downloaded sample tile."""
    import rasterio

    west, south, east, north = _dem_cell_bounds(cell_id)
    with rasterio.open(path) as raster:
        epsg = raster.crs.to_epsg() if raster.crs else None
        if epsg != DEM_EXPECTED_RASTER_EPSG:
            raise ValueError(
                f"Sample tile '{cell_id}' CRS is EPSG:{epsg}, not the locked "
                f"EPSG:{DEM_EXPECTED_RASTER_EPSG}."
            )
        pixel_x = abs(raster.transform.a)
        pixel_y = abs(raster.transform.e)
        for pixel in (pixel_x, pixel_y):
            if abs(pixel - DEM_PIXEL_DEGREES) / DEM_PIXEL_DEGREES > DEM_PIXEL_RELATIVE_TOLERANCE:
                raise ValueError(
                    f"Sample tile '{cell_id}' pixel size {pixel!r} is not 1/3 "
                    "arc-second."
                )
        if raster.count != 1 or raster.dtypes[0] != "float32":
            raise ValueError(f"Sample tile '{cell_id}' is not a single float32 band.")
        if raster.nodata != DEM_EXPECTED_NODATA:
            raise ValueError(
                f"Sample tile '{cell_id}' nodata {raster.nodata!r} is not the "
                "locked value."
            )
        bounds = raster.bounds
        if not (
            bounds.left <= west + 1e-6
            and bounds.bottom <= south + 1e-6
            and bounds.right >= east - 1e-6
            and bounds.top >= north - 1e-6
        ):
            raise ValueError(f"Sample tile '{cell_id}' does not cover its cell.")
        return {
            "crs": f"EPSG:{epsg}",
            "pixel_degrees": [round(pixel_x, 12), round(pixel_y, 12)],
            "band_count": raster.count,
            "dtype": raster.dtypes[0],
            "nodata": raster.nodata,
            "width": raster.width,
            "height": raster.height,
            "bounds": [
                round(bounds.left, 7),
                round(bounds.bottom, 7),
                round(bounds.right, 7),
                round(bounds.top, 7),
            ],
        }


def _corridor_dem_cells(
    selection: dict[str, Any],
    route_lock: dict[str, Any],
    transfer_lock: dict[str, Any],
    edge_lock: dict[str, Any],
    fill_lock: dict[str, Any],
    overlay_lock: dict[str, Any],
    cache_root: Path,
    fill_root: Path,
    forward: Transformer,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Every 1x1 degree cell the closed corridor's chained geometry traverses.

    The corridor is exactly what the locks chain: the solved NHPN edge paths of
    the connected segments (re-proved against the cache before use), the
    recomputed mixed-ancestry chains of the unconnected segments (proved equal
    to the locked chain-connectivity entries), the locked NHS fill span
    geometry, and the authored overlay chords.
    """
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    edge_by_id = {entry["segment_id"]: entry for entry in edge_lock["segments"]}
    chain_by_id = {
        entry["segment_id"]: entry
        for entry in overlay_lock["chain_connectivity"]["segments"]
    }
    fills_by_segment: dict[str, list[dict[str, Any]]] = {}
    for site in fill_lock["sites"]:
        fills_by_segment.setdefault(site["segment_id"], []).append(site)
    overlays_by_segment: dict[str, list[dict[str, Any]]] = {}
    for overlay in overlay_lock["overlays"]:
        overlays_by_segment.setdefault(overlay["segment_id"], []).append(
            {
                "site_id": overlay["site_id"],
                "from_coordinate": overlay["boundary"]["from_coordinate"],
                "to_coordinate": overlay["boundary"]["to_coordinate"],
                "separation_m": overlay["boundary"]["length_m"],
            }
        )
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])
    anchor_limit = float(edge_lock["anchor_snap_limit_m"])

    cells: set[tuple[int, int]] = set()
    coverage: list[dict[str, Any]] = []
    for segment in selection["segments"]:
        segment_id = segment["id"]
        entry = edge_by_id.get(segment_id)
        if entry is None:
            continue
        lines = _segment_locked_lines(route_lock, segment_id, cache_root)
        line_by_key = {
            (candidate.object_id, candidate.part_index): candidate.geometry
            for candidate in lines
        }
        metric_lines = tuple(
            (candidate, transform(forward.transform, candidate.geometry))
            for candidate in lines
        )
        from_point = forward.transform(
            transfer_by_id[segment["from"]]["coordinate"]["longitude"],
            transfer_by_id[segment["from"]]["coordinate"]["latitude"],
        )
        to_point = forward.transform(
            transfer_by_id[segment["to"]]["coordinate"]["longitude"],
            transfer_by_id[segment["to"]]["coordinate"]["latitude"],
        )
        if entry.get("connected"):
            reproduced = _solve_segment_edge_path(
                segment, metric_lines, from_point, to_point, tolerance
            )
            if canonical_sha256(reproduced) != canonical_sha256(entry):
                raise ValueError(
                    f"Locked cache no longer reproduces the solved edge path for "
                    f"'{segment_id}'."
                )
            path_edges = [
                (edge["object_id"], edge["part_index"]) for edge in entry["edges"]
            ]
            cross_check = {
                "segment_id": segment_id,
                "kind": "solved_edge_path",
                "recorded_length_m": entry["length_meters"],
                "recomputed_length_m": reproduced["length_meters"],
            }
        else:
            walk = _chained_segment_path_edges(
                segment,
                metric_lines,
                from_point,
                to_point,
                tolerance,
                anchor_limit,
                fills_by_segment.get(segment_id, []),
                overlays_by_segment.get(segment_id, []),
                forward,
            )
            recorded = chain_by_id[segment_id]
            for key in (
                "chain_length_meters",
                "nhpn_path_meters",
                "fill_chord_meters",
                "overlay_chord_meters",
                "fill_site_ids_on_chain",
                "overlay_site_ids_on_chain",
            ):
                if walk[key] != recorded.get(key, 0.0 if key.endswith("meters") else []):
                    raise ValueError(
                        f"Recomputed chain for '{segment_id}' does not reproduce the "
                        f"locked chain connectivity ({key})."
                    )
            path_edges = walk["nhpn_edges"]
            cross_check = {
                "segment_id": segment_id,
                "kind": "mixed_ancestry_chain",
                "recorded_length_m": recorded["chain_length_meters"],
                "recomputed_length_m": walk["chain_length_meters"],
            }
        segment_cells: set[tuple[int, int]] = set()
        for key in path_edges:
            _cells_intersecting_line(line_by_key[key], segment_cells)
        cells.update(segment_cells)
        cross_check["cell_count"] = len(segment_cells)
        coverage.append(cross_check)

    fill_cells: set[tuple[int, int]] = set()
    for site in sorted(fill_lock["sites"], key=lambda entry: entry["site_id"]):
        features = _load_locked_nhs_site_features(site, fill_root / site["site_id"])
        for group in site["fill_route_groups"]:
            for record in group["records"]:
                _cells_intersecting_line(
                    _merged_feature_line(features[record["object_id"]]), fill_cells
                )
    cells.update(fill_cells)
    coverage.append({"kind": "nhs_fill_spans", "cell_count": len(fill_cells)})
    overlay_cells: set[tuple[int, int]] = set()
    for overlay in overlay_lock["overlays"]:
        _cells_intersecting_line(
            LineString(overlay["geometry"]["coordinates"]), overlay_cells
        )
    cells.update(overlay_cells)
    coverage.append({"kind": "authored_overlay_chords", "cell_count": len(overlay_cells)})
    return sorted(_dem_cell_id(cell) for cell in cells), coverage


def _dem_checkpoint_reuse(
    checkpoint: Path, request_sha256: str
) -> dict[str, Any] | None:
    if not checkpoint.is_file():
        return None
    record = json.loads(checkpoint.read_text(encoding="utf-8"))
    if record.get("request_sha256") != request_sha256:
        return None
    return record


def _write_dem_checkpoint(checkpoint: Path, record: dict[str, Any]) -> None:
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    temporary = checkpoint.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(checkpoint)


def lock_continental_3dep_products(
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    overlay_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    fill_cache_directory: Path,
    dem_cache_directory: Path,
    output_path: Path,
    *,
    transport: DemTransport | None = None,
    acquired_at: str | None = None,
) -> dict[str, Any]:
    """Lock the exact 3DEP product set over the closed continental corridor.

    Per cell: one discovery request inside the catalog's discovery endpoint, a
    deterministic latest-publication selection among covering catalog products,
    and the tile's own FGDC metadata (fetched from inside the catalog's allowed
    prefixes) as the datum evidence. A deterministic three-tile sample is
    downloaded in full, checksummed, and raster-inspected. All responses stay in
    the ignored cache; the lock records URLs, dates, datums, and checksums.
    """
    catalog = load_catalog(catalog_path)
    if DEM_SOURCE_ID not in catalog:
        raise ValueError("3DEP is not in the approved source catalog.")
    source = catalog[DEM_SOURCE_ID]
    discovery_endpoint = str(source.raw.get("discovery_url", ""))
    if not discovery_endpoint.startswith("https://"):
        raise ValueError("The catalog names no 3DEP discovery endpoint.")
    catalog_products = source.raw.get("products", [])
    family = next(
        (
            product
            for product in catalog_products
            if product.get("resolution") == DEM_EXPECTED_RESOLUTION
        ),
        None,
    )
    if family is None:
        raise ValueError(
            "The catalog declares no 1/3 arc-second 3DEP product; ADR-0007 locks "
            "that baseline."
        )
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    fill_lock = validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    overlay_lock = load_json(overlay_lock_path)
    if overlay_lock.get("edge_path_lock_sha256") != compute_sha256(
        edge_path_lock_path
    ) or overlay_lock.get("nhs_fill_lock_sha256") != compute_sha256(fill_lock_path):
        raise ValueError(
            "Reconstruction overlay lock does not pin the same edge-path and "
            "fill locks."
        )
    if transport is None:
        transport = UrllibDemTransport()
    timestamp = acquired_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    cache_root = cache_directory / route_lock["nhpn"]["service"][
        "canonical_metadata_sha256"
    ]
    fill_root = fill_cache_directory / fill_lock["nhs"]["service"][
        "canonical_metadata_sha256"
    ]
    cells, coverage = _corridor_dem_cells(
        selection,
        route_lock,
        transfer_lock,
        edge_lock,
        fill_lock,
        overlay_lock,
        cache_root,
        fill_root,
        forward,
    )

    discovery_root = dem_cache_directory / "discovery"
    metadata_root = dem_cache_directory / "metadata"
    tiles_root = dem_cache_directory / "tiles"
    products: list[dict[str, Any]] = []
    resumed_discoveries = 0
    resumed_metadata = 0
    for cell_id in cells:
        west, south, _, _ = _dem_cell_bounds(cell_id)
        request = _dem_discovery_request(
            family["dataset"], family["format"], family["extent"], (west, south)
        )
        request_sha256 = canonical_sha256(
            {"endpoint": discovery_endpoint, "request": request}
        )
        checkpoint = discovery_root / f"{cell_id}.json"
        record = _dem_checkpoint_reuse(checkpoint, request_sha256)
        if record is None:
            url = discovery_endpoint + "?" + urllib.parse.urlencode(request)
            fetched = transport.fetch(url)
            if fetched.status != 200 or fetched.body is None:
                raise ValueError(
                    f"3DEP discovery failed for cell '{cell_id}' with status "
                    f"{fetched.status}."
                )
            response = json.loads(fetched.body)
            record = {
                "request_sha256": request_sha256,
                "response_sha256": canonical_sha256(response),
                "response": response,
            }
            _write_dem_checkpoint(checkpoint, record)
        else:
            resumed_discoveries += 1
        response = record["response"]
        total = int(response.get("total", 0))
        items = response.get("items", [])
        if total > DEM_DISCOVERY_MAX or total != len(items):
            raise ValueError(
                f"3DEP discovery for cell '{cell_id}' returned an unpaged total of "
                f"{total}; the lock expects one complete page."
            )
        selected, candidates = _select_dem_product(
            items, (west, south), family["extent"], source.allowed_url_prefixes
        )
        if not selected["download_url"].endswith(".tif"):
            raise ValueError(
                f"3DEP product for cell '{cell_id}' is not a staged GeoTIFF URL."
            )
        metadata_url = selected["download_url"][:-4] + ".xml"
        if not any(
            url_matches_prefix(metadata_url, prefix)
            for prefix in source.allowed_url_prefixes
        ):
            raise ValueError(
                f"3DEP metadata URL for cell '{cell_id}' is outside the catalog "
                "allowlist."
            )
        metadata_checkpoint = metadata_root / f"{cell_id}.json"
        metadata_record = _dem_checkpoint_reuse(
            metadata_checkpoint, canonical_sha256({"url": metadata_url})
        )
        if metadata_record is None:
            fetched = transport.fetch(metadata_url)
            if fetched.status != 200 or fetched.body is None:
                raise ValueError(
                    f"3DEP metadata fetch failed for cell '{cell_id}' with status "
                    f"{fetched.status}."
                )
            metadata_record = {
                "request_sha256": canonical_sha256({"url": metadata_url}),
                "url": metadata_url,
                "sha256": fetched.sha256,
                "byte_count": fetched.byte_count,
                "response": {
                    "status": fetched.status,
                    "content_type": fetched.content_type,
                    "etag": fetched.etag,
                    "last_modified": fetched.last_modified,
                },
                "body_text": fetched.body.decode("utf-8", errors="replace"),
            }
            _write_dem_checkpoint(metadata_checkpoint, metadata_record)
        else:
            resumed_metadata += 1
        parsed = _parse_dem_fgdc_metadata(metadata_record["body_text"])
        if (
            parsed["horizontal_datum"] != DEM_EXPECTED_HORIZONTAL_DATUM
            or parsed["vertical_datum"] != DEM_EXPECTED_VERTICAL_DATUM
            or parsed["elevation_units"] != DEM_EXPECTED_ELEVATION_UNITS
        ):
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "3DEP tile metadata does not state the locked "
                        "datums",
                        "cell_id": cell_id,
                        "measured": parsed,
                    },
                    sort_keys=True,
                )
            )
        products.append(
            {
                "cell_id": cell_id,
                "product": selected,
                "discovery": {
                    "request": request,
                    "request_sha256": request_sha256,
                    "response_sha256": record["response_sha256"],
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                },
                "metadata": {
                    "url": metadata_url,
                    "sha256": metadata_record["sha256"],
                    "byte_count": metadata_record["byte_count"],
                    **parsed,
                },
            }
        )

    product_by_cell = {product["cell_id"]: product for product in products}
    sample_indices = sorted({0, len(cells) // 2, len(cells) - 1})
    samples: list[dict[str, Any]] = []
    resumed_tiles = 0
    for index in sample_indices:
        cell_id = cells[index]
        product = product_by_cell[cell_id]["product"]
        filename = product["download_url"].rsplit("/", 1)[-1]
        destination = tiles_root / filename
        tile_checkpoint = tiles_root / f"{filename}.json"
        tile_request_sha256 = canonical_sha256({"url": product["download_url"]})
        record = _dem_checkpoint_reuse(tile_checkpoint, tile_request_sha256)
        if (
            record is not None
            and destination.is_file()
            and compute_sha256(destination) == record["sha256"]
        ):
            resumed_tiles += 1
        else:
            fetched = transport.fetch(product["download_url"], destination)
            if fetched.status != 200:
                raise ValueError(
                    f"3DEP tile download failed for cell '{cell_id}' with status "
                    f"{fetched.status}."
                )
            record = {
                "request_sha256": tile_request_sha256,
                "url": product["download_url"],
                "sha256": fetched.sha256,
                "byte_count": fetched.byte_count,
                "response": {
                    "status": fetched.status,
                    "content_type": fetched.content_type,
                    "etag": fetched.etag,
                    "last_modified": fetched.last_modified,
                },
            }
            _write_dem_checkpoint(tile_checkpoint, record)
        if record["byte_count"] != product["size_bytes"]:
            raise ValueError(
                f"3DEP tile for cell '{cell_id}' downloaded {record['byte_count']} "
                f"bytes where discovery declared {product['size_bytes']}."
            )
        samples.append(
            {
                "cell_id": cell_id,
                "url": product["download_url"],
                "sha256": record["sha256"],
                "byte_count": record["byte_count"],
                "response": record["response"],
                "acquired_at": timestamp,
                "raster": _inspect_dem_raster(destination, cell_id),
            }
        )

    payload = {
        "schema_version": 1,
        "status": DEM_PRODUCT_LOCK_STATUS,
        "decision": "ADR-0007",
        "route_decision": selection["decision"],
        "acquired_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "source": {
            "source_id": DEM_SOURCE_ID,
            "publisher": source.publisher,
            "license_status": source.license_status,
            "license_evidence_url": source.license_evidence_url,
            "discovery_endpoint": discovery_endpoint,
        },
        "product_family": {
            "dataset": family["dataset"],
            "format": family["format"],
            "extent": family["extent"],
            "resolution": DEM_EXPECTED_RESOLUTION,
            "raster_crs": f"EPSG:{DEM_EXPECTED_RASTER_EPSG}",
            "horizontal_datum": DEM_EXPECTED_HORIZONTAL_DATUM,
            "vertical_datum": DEM_EXPECTED_VERTICAL_DATUM,
            "elevation_units": DEM_EXPECTED_ELEVATION_UNITS,
        },
        "selection_policy": DEM_SELECTION_POLICY,
        "source_policy": dict(DEM_PRODUCT_SOURCE_POLICY),
        "corridor": {
            "cell_count": len(cells),
            "cells": cells,
            "cells_sha256": canonical_sha256(cells),
            "coverage": coverage,
            "note": (
                "Cells are every 1x1 degree cell intersected by the closed "
                "corridor's chained geometry: the solved NHPN edge paths, the "
                "recomputed mixed-ancestry chains (proved equal to the locked "
                "chain connectivity), the locked NHS fill spans, and the "
                "authored overlay chords."
            ),
        },
        "discovery_resumed_cells": resumed_discoveries,
        "metadata_resumed_cells": resumed_metadata,
        "product_count": len(products),
        "products": products,
        "products_sha256": canonical_sha256(products),
        "sample_verification": {
            "policy": DEM_SAMPLE_POLICY,
            "sample_count": len(samples),
            "resumed_tiles": resumed_tiles,
            "samples": samples,
        },
        "westbound_selection_validated": False,
        "next_stage": DEM_PRODUCT_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_3dep_products(
    dem_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    overlay_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the 3DEP product lock without caches, downloads, or discovery."""
    payload = load_json(dem_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported 3DEP product lock schema.")
    if payload.get("status") != DEM_PRODUCT_LOCK_STATUS:
        raise ValueError("3DEP product lock has an unsupported status.")
    if payload.get("decision") != "ADR-0007":
        raise ValueError("3DEP product lock does not cite ADR-0007.")
    if payload.get("westbound_selection_validated") is not False:
        raise ValueError(
            "3DEP product lock claims a validated westbound selection, which "
            "this stage cannot establish."
        )
    selection = load_json(selection_path)
    if payload.get("route_decision") != selection.get("decision"):
        raise ValueError("3DEP product lock decision does not match the selection.")
    validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("3DEP product lock input hash drifted.")
    catalog = load_catalog(catalog_path)
    recorded_source = payload.get("source", {})
    if recorded_source.get("source_id") != DEM_SOURCE_ID or DEM_SOURCE_ID not in catalog:
        raise ValueError("3DEP product lock does not cite the catalog 3DEP source.")
    source = catalog[DEM_SOURCE_ID]
    if (
        recorded_source.get("publisher") != source.publisher
        or recorded_source.get("license_status") != source.license_status
        or recorded_source.get("license_evidence_url") != source.license_evidence_url
    ):
        raise ValueError("3DEP product lock source identity drifted from the catalog.")
    if recorded_source.get("discovery_endpoint") != source.raw.get("discovery_url"):
        raise ValueError(
            "3DEP product lock discovery endpoint drifted from the catalog."
        )
    family = payload.get("product_family", {})
    matches_catalog = any(
        product.get("dataset") == family.get("dataset")
        and product.get("format") == family.get("format")
        and product.get("extent") == family.get("extent")
        and product.get("resolution") == family.get("resolution")
        for product in source.raw.get("products", [])
    )
    if not matches_catalog:
        raise ValueError("3DEP product family does not match an explicit catalog product.")
    expected_family_facts = {
        "resolution": DEM_EXPECTED_RESOLUTION,
        "raster_crs": f"EPSG:{DEM_EXPECTED_RASTER_EPSG}",
        "horizontal_datum": DEM_EXPECTED_HORIZONTAL_DATUM,
        "vertical_datum": DEM_EXPECTED_VERTICAL_DATUM,
        "elevation_units": DEM_EXPECTED_ELEVATION_UNITS,
    }
    if any(family.get(key) != value for key, value in expected_family_facts.items()):
        raise ValueError("3DEP product lock family facts drifted.")
    if payload.get("selection_policy") != DEM_SELECTION_POLICY:
        raise ValueError("3DEP product lock selection policy drifted.")
    if payload.get("source_policy") != DEM_PRODUCT_SOURCE_POLICY:
        raise ValueError("3DEP product lock source policy is incomplete.")

    corridor = payload.get("corridor", {})
    cells = corridor.get("cells")
    if (
        not isinstance(cells, list)
        or not cells
        or cells != sorted(set(cells))
        or corridor.get("cell_count") != len(cells)
        or canonical_sha256(cells) != corridor.get("cells_sha256")
    ):
        raise ValueError("3DEP product lock corridor cells do not reconcile.")
    products = payload.get("products")
    if not isinstance(products, list) or [
        product.get("cell_id") for product in products
    ] != cells:
        raise ValueError(
            "3DEP product lock does not lock exactly one product per corridor cell."
        )
    if payload.get("product_count") != len(products) or canonical_sha256(
        products
    ) != payload.get("products_sha256"):
        raise ValueError("3DEP product lock product digest drifted.")
    for entry in products:
        cell_id = entry["cell_id"]
        west, south, east, north = _dem_cell_bounds(cell_id)
        product = entry.get("product", {})
        download_url = str(product.get("download_url", ""))
        if not any(
            url_matches_prefix(download_url, prefix)
            for prefix in source.allowed_url_prefixes
        ):
            raise ValueError(
                f"3DEP product for cell '{cell_id}' is outside the catalog allowlist."
            )
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(product.get("publication_date", ""))):
            raise ValueError(
                f"3DEP product for cell '{cell_id}' has no publication date."
            )
        for field in ("source_id", "title"):
            if not str(product.get(field, "")).strip():
                raise ValueError(
                    f"3DEP product for cell '{cell_id}' is missing '{field}'."
                )
        if int(product.get("size_bytes", 0)) <= 0:
            raise ValueError(f"3DEP product for cell '{cell_id}' has no size.")
        bounding_box = product.get("bounding_box", [])
        if len(bounding_box) != 4 or not (
            bounding_box[0] <= west + DEM_COVER_EPSILON_DEGREES
            and bounding_box[1] <= south + DEM_COVER_EPSILON_DEGREES
            and bounding_box[2] >= east - DEM_COVER_EPSILON_DEGREES
            and bounding_box[3] >= north - DEM_COVER_EPSILON_DEGREES
        ):
            raise ValueError(
                f"3DEP product for cell '{cell_id}' does not cover its cell."
            )
        discovery = entry.get("discovery", {})
        expected_request = _dem_discovery_request(
            family["dataset"], family["format"], family["extent"], (west, south)
        )
        if discovery.get("request") != expected_request:
            raise ValueError(
                f"3DEP discovery request for cell '{cell_id}' drifted."
            )
        if int(discovery.get("candidate_count", 0)) < 1 or not SHA256_PATTERN.fullmatch(
            str(discovery.get("response_sha256", ""))
        ):
            raise ValueError(
                f"3DEP discovery contract for cell '{cell_id}' is incomplete."
            )
        candidates = discovery.get("candidates", [])
        if len(candidates) != discovery.get("candidate_count") or not any(
            candidate.get("source_id") == product.get("source_id")
            and candidate.get("publication_date") == product.get("publication_date")
            for candidate in candidates
        ):
            raise ValueError(
                f"3DEP selection for cell '{cell_id}' is not among its candidates."
            )
        latest = max(candidate["publication_date"] for candidate in candidates)
        tied = sorted(
            candidate["source_id"]
            for candidate in candidates
            if candidate["publication_date"] == latest
        )
        if product.get("publication_date") != latest or product.get("source_id") != tied[0]:
            raise ValueError(
                f"3DEP selection for cell '{cell_id}' violates the selection policy."
            )
        metadata = entry.get("metadata", {})
        if metadata.get("url") != download_url[:-4] + ".xml" or not any(
            url_matches_prefix(str(metadata.get("url", "")), prefix)
            for prefix in source.allowed_url_prefixes
        ):
            raise ValueError(
                f"3DEP metadata URL for cell '{cell_id}' is outside the allowlist."
            )
        if not SHA256_PATTERN.fullmatch(str(metadata.get("sha256", ""))) or int(
            metadata.get("byte_count", 0)
        ) <= 0:
            raise ValueError(
                f"3DEP metadata evidence for cell '{cell_id}' is incomplete."
            )
        if (
            metadata.get("horizontal_datum") != DEM_EXPECTED_HORIZONTAL_DATUM
            or metadata.get("vertical_datum") != DEM_EXPECTED_VERTICAL_DATUM
            or metadata.get("elevation_units") != DEM_EXPECTED_ELEVATION_UNITS
        ):
            raise ValueError(
                f"3DEP metadata for cell '{cell_id}' does not state the locked "
                "datums."
            )

    sample_block = payload.get("sample_verification", {})
    if sample_block.get("policy") != DEM_SAMPLE_POLICY:
        raise ValueError("3DEP sample policy drifted.")
    samples = sample_block.get("samples", [])
    expected_cells = [cells[index] for index in sorted({0, len(cells) // 2, len(cells) - 1})]
    if [sample.get("cell_id") for sample in samples] != expected_cells or sample_block.get(
        "sample_count"
    ) != len(samples):
        raise ValueError("3DEP sample selection is not the deterministic sample.")
    product_by_cell = {product["cell_id"]: product for product in products}
    for sample in samples:
        product = product_by_cell[sample["cell_id"]]["product"]
        if sample.get("url") != product["download_url"]:
            raise ValueError(
                f"3DEP sample for cell '{sample['cell_id']}' is not the locked URL."
            )
        if not SHA256_PATTERN.fullmatch(str(sample.get("sha256", ""))):
            raise ValueError(
                f"3DEP sample for cell '{sample['cell_id']}' has an invalid checksum."
            )
        if sample.get("byte_count") != product["size_bytes"]:
            raise ValueError(
                f"3DEP sample for cell '{sample['cell_id']}' byte count does not "
                "match discovery."
            )
        response = sample.get("response", {})
        if response.get("status") != 200 or not response.get("content_type"):
            raise ValueError(
                f"3DEP sample for cell '{sample['cell_id']}' has incomplete "
                "response metadata."
            )
        raster = sample.get("raster", {})
        west, south, east, north = _dem_cell_bounds(sample["cell_id"])
        pixels = raster.get("pixel_degrees", [])
        if (
            raster.get("crs") != f"EPSG:{DEM_EXPECTED_RASTER_EPSG}"
            or raster.get("band_count") != 1
            or raster.get("dtype") != "float32"
            or raster.get("nodata") != DEM_EXPECTED_NODATA
            or len(pixels) != 2
            or any(
                abs(pixel - DEM_PIXEL_DEGREES) / DEM_PIXEL_DEGREES
                > DEM_PIXEL_RELATIVE_TOLERANCE
                for pixel in pixels
            )
        ):
            raise ValueError(
                f"3DEP sample raster for cell '{sample['cell_id']}' does not match "
                "the locked product facts."
            )
        bounds = raster.get("bounds", [])
        if len(bounds) != 4 or not (
            bounds[0] <= west + 1e-6
            and bounds[1] <= south + 1e-6
            and bounds[2] >= east - 1e-6
            and bounds[3] >= north - 1e-6
        ):
            raise ValueError(
                f"3DEP sample raster for cell '{sample['cell_id']}' does not cover "
                "its cell."
            )
    if payload.get("next_stage") != DEM_PRODUCT_NEXT_STAGE:
        raise ValueError("3DEP product lock next stage drifted.")
    return payload


# --- Westbound directed route lock over the closed corridor -----------------------

DIRECTED_ROUTE_STATUS = "westbound_directed_route_locked_reconstruction_pending"
DIRECTED_ROUTE_NEXT_STAGE = {
    "id": "reconstruction-geometry",
    "requires": [
        "reciprocal directed westbound carriageway reconstruction under ADR-0014",
        "full ADR-0018 gate battery, including the gates deferred at the two "
        "overlay sites and the recorded Quad Cities 77.2 degree corner constraint",
        "corridor elevation acquisition against the locked 3DEP product URLs",
        "authored endpoint connector geometry for the three non-NHPN segments",
    ],
}

# Every directed element is measured two ways: the EPSG:5070 planimetric length
# the chain and edge-path locks already recorded (their exact figures are
# reproduced, not approximated), and a geodesic length on the GRS80 ellipsoid
# over the record's locked EPSG:4326 coordinates. EPSG:5070 is an equal-area
# projection, not an equidistant one; its scale error inside the corridor's
# latitude band (33.8 to 41.3 degrees N, spanning the 29.5/45.5 standard
# parallels) stays under one percent, so a wider disagreement between the two
# measurements of the same locked coordinates is a defect, not projection
# distortion. The measured corridor-wide divergence at lock time is recorded in
# the artifact beside the bound.
GEODESIC_PLANIMETRIC_AGREEMENT_RATIO = 0.01

# Recorded element lengths are millimetre-rounded, so any comparison between two
# recorded values may carry up to two half-quantum rounding steps.
GEODESIC_ROUNDING_ALLOWANCE_M = 0.002

# The NHPN MILES aggregation is a cross-check against the source's own length
# assertion, not a distance authority. Unlike the NHS/ARNOLD MILES field, which
# the conflation lock proved agrees with its geometry within about 0.9 percent,
# the NHPN MILES field (VERSION-stamped 2014.05 on the corridor records)
# disagrees with the same records' locked geometry by a characterised margin:
# at derivation the per-segment aggregate divergence envelope measured 0.4 to
# 4.4 percent, with a per-record median MILES/geodesic ratio near 0.96. The
# bound trips a material drift beyond that characterised envelope without
# absorbing the envelope itself.
NHPN_MILES_AGGREGATE_BOUND = 0.06

# Two consecutive segments resolve their shared ADR-0024 anchor on two
# independently snapped graphs, each within the unchanged 25 m anchor snap
# limit, so their terminal nodes may sit up to twice that limit apart. The gap
# is a bounded anchor-model discontinuity, recorded and excluded from
# stationing; junction geometry is reconstruction-stage output.
JUNCTION_CONTINUITY_LIMIT_M = 2.0 * ANCHOR_SNAP_LIMIT_METERS

_DIRECTED_GEOD = Geod(ellps="GRS80")


def _geodesic_line_length_m(coordinates: Sequence[tuple[float, float]]) -> float:
    """GRS80 geodesic length of an EPSG:4326 coordinate sequence, in metres."""
    return float(
        _DIRECTED_GEOD.line_length(
            [point[0] for point in coordinates], [point[1] for point in coordinates]
        )
    )


def _geodesic_distance_m(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    """GRS80 geodesic distance between two EPSG:4326 lon/lat points, in metres."""
    _, _, distance = _DIRECTED_GEOD.inv(first[0], first[1], second[0], second[1])
    return float(distance)


def _milepost_trend(entry: float | None, exit: float | None) -> str:
    if entry is None or exit is None:
        return "unmeasured"
    if exit < entry:
        return "decreasing"
    if exit > entry:
        return "increasing"
    return "flat"


def _rounding_envelope_m(count: int, quantum: float = 0.001) -> float:
    """The largest disagreement pure rounding can produce between a recorded sum
    and the sum of its recorded, individually rounded parts."""
    return 0.5 * quantum * (count + 1) + 1e-6


def _increasing_milepost_runs(elements: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Contiguous same-key runs of increasing milepost trend along a traversal.

    Direction evidence, not adjudication: within one LRS key a consistent
    milepost trend corroborates the traversal orientation, and a run against
    the dominant trend is a key-local calibration-direction fact worth reading,
    not an error.
    """
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, element in enumerate(elements):
        if element["kind"] not in ("nhpn_edge", "nhpn_split_edge"):
            current = None
            continue
        trend = _milepost_trend(element["entry_milepost"], element["exit_milepost"])
        if trend != "increasing":
            current = None
            continue
        if (
            current is not None
            and current["lrs_key"] == element["lrs_key"]
            and current["first_element_index"] + current["element_count"] == index
        ):
            current["element_count"] += 1
            current["exit_milepost"] = element["exit_milepost"]
        else:
            current = {
                "lrs_key": element["lrs_key"],
                "first_element_index": index,
                "element_count": 1,
                "entry_milepost": element["entry_milepost"],
                "exit_milepost": element["exit_milepost"],
            }
            runs.append(current)
    return runs


def _directed_bridge_sites(
    graph: nx.MultiGraph,
    nodes: dict[tuple[int, int], tuple[float, float]],
    sites: Sequence[dict[str, Any]],
    data_key: str,
    tolerance: float,
    forward: Transformer,
) -> dict[str, tuple[tuple[int, int], tuple[int, int]]]:
    """Bridge fill or overlay sites exactly as the chain-connectivity model does.

    Same edge keys, weights, and attributes, so the shortest traversal cannot
    disagree with the locked chain; additionally returns each site's
    (from-node, to-node) keys so the traversal can record which pinned boundary
    end it entered.
    """
    ends_by_site: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}

    def nearest_node(point: tuple[float, float]) -> tuple[tuple[int, int], float]:
        best_key, best_distance = None, float("inf")
        for key in sorted(nodes):
            distance = math.dist(point, nodes[key])
            if distance < best_distance:
                best_key, best_distance = key, distance
        assert best_key is not None
        return best_key, best_distance

    for site in sorted(sites, key=lambda entry: entry["site_id"]):
        ends = []
        for corner in ("from_coordinate", "to_coordinate"):
            point = forward.transform(
                site[corner]["longitude"], site[corner]["latitude"]
            )
            node, distance = nearest_node(point)
            if distance > tolerance:
                raise ValueError(
                    f"Bridge '{site['site_id']}' {corner} does not land on a locked "
                    f"chain end within the {tolerance:g} m tolerance."
                )
            ends.append(node)
        graph.add_edge(
            ends[0],
            ends[1],
            key=(data_key, site["site_id"]),
            weight=float(site["separation_m"]),
            **{f"{data_key}_site_id": site["site_id"]},
        )
        ends_by_site[site["site_id"]] = (ends[0], ends[1])
    return ends_by_site


def _derive_directed_segment(
    segment: dict[str, Any],
    edge_entry: dict[str, Any],
    chain_entry: dict[str, Any] | None,
    lines: tuple[LockedCandidateLine, ...],
    fill_sites: Sequence[dict[str, Any]],
    overlay_sites: Sequence[dict[str, Any]],
    conflation_site_by_id: dict[str, dict[str, Any]],
    from_point: tuple[float, float],
    to_point: tuple[float, float],
    tolerance: float,
    anchor_limit: float,
    forward: Transformer,
    inverse: Transformer,
    geometry_sink: list[LineString] | None = None,
) -> dict[str, Any]:
    """Walk one segment's locked traversal from its from-anchor to its to-anchor.

    Rebuilds the identical snapped graph, bridges, and anchor resolution the
    edge-path and chain-connectivity locks used, then refuses to emit anything
    that does not reproduce those locks exactly: the directed sequence is the
    locked topology traversed in the ADR-0024 westbound anchor order, never a
    new selection.
    """
    segment_id = segment["id"]
    connected = bool(edge_entry.get("connected"))

    candidate_by_key: dict[tuple[int, int], LockedCandidateLine] = {}
    metric_by_key: dict[tuple[int, int], LineString] = {}
    part_counts: dict[int, int] = {}
    record_metric_total: dict[int, float] = {}
    metric_pairs: list[tuple[LockedCandidateLine, LineString]] = []
    for candidate in lines:
        metric = transform(forward.transform, candidate.geometry)
        metric_pairs.append((candidate, metric))
        key = (candidate.object_id, candidate.part_index)
        if key in candidate_by_key:
            raise ValueError(
                f"Segment '{segment_id}' locked candidates repeat part {key}."
            )
        candidate_by_key[key] = candidate
        metric_by_key[key] = metric
        part_counts[candidate.object_id] = part_counts.get(candidate.object_id, 0) + 1
        record_metric_total[candidate.object_id] = (
            record_metric_total.get(candidate.object_id, 0.0) + float(metric.length)
        )
    metric_lines = tuple(metric_pairs)

    graph, nodes, _, _ = _build_snapped_endpoint_graph(metric_lines, tolerance)
    bridge_ends: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}
    if not connected:
        bridge_ends.update(
            _directed_bridge_sites(graph, nodes, fill_sites, "fill", tolerance, forward)
        )
        bridge_ends.update(
            _directed_bridge_sites(
                graph, nodes, overlay_sites, "overlay", tolerance, forward
            )
        )

    splits: list[dict[str, Any]] = []
    from_key, from_distance, from_split = _resolve_anchor_node(
        graph, nodes, metric_lines, from_point, "from", tolerance, anchor_limit
    )
    if from_split is not None:
        splits.append(from_split)
    to_key, to_distance, to_split = _resolve_anchor_node(
        graph, nodes, metric_lines, to_point, "to", tolerance, anchor_limit
    )
    if to_split is not None:
        splits.append(to_split)
    if max(from_distance, to_distance) > anchor_limit or from_key == to_key:
        raise ValueError(
            f"Segment '{segment_id}' anchors did not resolve onto the locked graph."
        )
    if not nx.has_path(graph, from_key, to_key):
        raise ValueError(
            f"Segment '{segment_id}' has no anchor-to-anchor path on the locked "
            "closed topology."
        )
    node_path = nx.shortest_path(graph, from_key, to_key, weight="weight")

    fill_by_id = {site["site_id"]: site for site in fill_sites}
    overlay_by_id = {site["site_id"]: site for site in overlay_sites}
    elements: list[dict[str, Any]] = []
    ancestry_counts = {
        "nhpn_edge": 0,
        "nhpn_split_edge": 0,
        "nhs_fill_chord": 0,
        "authored_overlay_chord": 0,
    }
    planimetric_sums = {"nhpn": 0.0, "fill": 0.0, "overlay": 0.0}
    geodesic_total = 0.0
    nhpn_geodesic_total = 0.0
    miles_total = 0.0
    miles_unavailable = 0
    facility_counts: dict[str, int] = {}
    trend_counts = {"decreasing": 0, "increasing": 0, "flat": 0, "unmeasured": 0}
    thin = {"flat_milepost": [], "unmeasured_milepost": [], "authored_overlay": []}
    fill_ids: list[str] = []
    overlay_ids: list[str] = []
    reversed_count = 0

    for previous, current in zip(node_path, node_path[1:], strict=False):
        parallel = graph.get_edge_data(previous, current)
        if connected:
            chosen = min(
                parallel, key=lambda edge_key: (parallel[edge_key]["weight"], edge_key)
            )
        else:
            chosen = min(
                parallel,
                key=lambda edge_key: (parallel[edge_key]["weight"], str(edge_key)),
            )
        data = parallel[chosen]
        index = len(elements)
        if "fill_site_id" in data:
            site_id = data["fill_site_id"]
            site = fill_by_id[site_id]
            conflation_site = conflation_site_by_id.get(site_id)
            if conflation_site is None:
                raise ValueError(
                    f"Traversed fill '{site_id}' has no conflation lock span."
                )
            reversed_for_travel = bridge_ends[site_id][0] != previous
            chord = [
                (
                    site["from_coordinate"]["longitude"],
                    site["from_coordinate"]["latitude"],
                ),
                (
                    site["to_coordinate"]["longitude"],
                    site["to_coordinate"]["latitude"],
                ),
            ]
            geodesic = _geodesic_line_length_m(chord)
            travel_geometry = LineString(
                [forward.transform(*chord[0]), forward.transform(*chord[1])]
            )
            measure_by_side = {
                seam["side"]: seam["nhs"]["measure_at_seam"]
                for seam in conflation_site["seams"]
            }
            if set(measure_by_side) != {"from", "to"}:
                raise ValueError(
                    f"Conflation span '{site_id}' does not record both seam sides."
                )
            entry_side = "to" if reversed_for_travel else "from"
            exit_side = "from" if reversed_for_travel else "to"
            span = conflation_site["span"]
            length = float(site["separation_m"])
            element = {
                "kind": "nhs_fill_chord",
                "site_id": site_id,
                "reversed_for_travel": reversed_for_travel,
                "length_m": round(length, 3),
                "geodesic_length_m": round(geodesic, 3),
                "nhs_route": {
                    "state_fips": conflation_site["group"]["state_fips"],
                    "route_id": conflation_site["group"]["route_id"],
                },
                "entry_measure": measure_by_side[entry_side],
                "exit_measure": measure_by_side[exit_side],
                "measure_trend": _milepost_trend(
                    measure_by_side[entry_side], measure_by_side[exit_side]
                ),
                "conflated_span": {
                    "geometry_sha256": span["geometry_sha256"],
                    "geometry_length_m": span["geometry_length_m"],
                    "span_minus_chord_m": round(
                        span["geometry_length_m"] - round(length, 3), 3
                    ),
                },
            }
            ancestry_counts["nhs_fill_chord"] += 1
            planimetric_sums["fill"] += length
            fill_ids.append(site_id)
        elif "overlay_site_id" in data:
            site_id = data["overlay_site_id"]
            site = overlay_by_id[site_id]
            reversed_for_travel = bridge_ends[site_id][0] != previous
            geodesic = _geodesic_line_length_m(site["geometry"]["coordinates"])
            travel_geometry = LineString(
                [forward.transform(x, y) for x, y in site["geometry"]["coordinates"]]
            )
            length = float(site["separation_m"])
            element = {
                "kind": "authored_overlay_chord",
                "site_id": site_id,
                "overlay_id": site["overlay_id"],
                "reversed_for_travel": reversed_for_travel,
                "length_m": round(length, 3),
                "geodesic_length_m": round(geodesic, 3),
            }
            ancestry_counts["authored_overlay_chord"] += 1
            planimetric_sums["overlay"] += length
            overlay_ids.append(site_id)
            thin["authored_overlay"].append(index)
        else:
            object_id = int(data["object_id"])
            part_index = int(data["part_index"])
            candidate = candidate_by_key[(object_id, part_index)]
            metric = metric_by_key[(object_id, part_index)]
            part_range = data.get("part_range_m")
            reversed_for_travel = data["start_key"] != previous
            length = float(data["weight"])
            if part_range is None:
                travel_geometry = metric
                geodesic = _geodesic_line_length_m(list(candidate.geometry.coords))
            else:
                clipped = substring(metric, float(part_range[0]), float(part_range[1]))
                travel_geometry = clipped
                geodesic = _geodesic_line_length_m(
                    [inverse.transform(x, y) for x, y in clipped.coords]
                )
            single_part = part_counts[object_id] == 1
            whole_part = part_range is None
            if whole_part and single_part:
                entry_milepost = (
                    candidate.record_end_milepost
                    if reversed_for_travel
                    else candidate.record_begin_milepost
                )
                exit_milepost = (
                    candidate.record_begin_milepost
                    if reversed_for_travel
                    else candidate.record_end_milepost
                )
            else:
                # A record's mileposts describe the whole record; a split
                # sub-edge or one part of a multi-part record has no source
                # measure of its own, and interpolating one would manufacture
                # precision the measure axis does not carry.
                entry_milepost = None
                exit_milepost = None
            if candidate.miles is None:
                prorated_miles = None
                miles_unavailable += 1
            elif whole_part and single_part:
                prorated_miles = float(candidate.miles)
            else:
                prorated_miles = (
                    float(candidate.miles) * length / record_metric_total[object_id]
                )
            element = {
                "kind": "nhpn_edge" if whole_part else "nhpn_split_edge",
                "object_id": object_id,
                "part_index": part_index,
                "lrs_key": candidate.lrs_key,
                "reversed_for_travel": reversed_for_travel,
                "length_m": round(length, 3),
                "geodesic_length_m": round(geodesic, 3),
                "entry_milepost": entry_milepost,
                "exit_milepost": exit_milepost,
                "miles": None if prorated_miles is None else round(prorated_miles, 6),
                "facility_type": candidate.facility_type,
            }
            if not whole_part:
                element["part_range_m"] = [
                    round(float(part_range[0]), 3),
                    round(float(part_range[1]), 3),
                ]
            kind_key = "nhpn_edge" if whole_part else "nhpn_split_edge"
            ancestry_counts[kind_key] += 1
            planimetric_sums["nhpn"] += length
            nhpn_geodesic_total += geodesic
            if prorated_miles is not None:
                miles_total += prorated_miles
            facility_key = (
                "null" if candidate.facility_type is None else str(candidate.facility_type)
            )
            facility_counts[facility_key] = facility_counts.get(facility_key, 0) + 1
            trend = _milepost_trend(entry_milepost, exit_milepost)
            trend_counts[trend] += 1
            if trend == "flat":
                thin["flat_milepost"].append(index)
            elif trend == "unmeasured":
                thin["unmeasured_milepost"].append(index)
        deviation = abs(element["geodesic_length_m"] - element["length_m"])
        allowance = (
            GEODESIC_PLANIMETRIC_AGREEMENT_RATIO * element["length_m"]
            + GEODESIC_ROUNDING_ALLOWANCE_M
        )
        if deviation > allowance:
            raise ValueError(
                f"Segment '{segment_id}' element {index} geodesic length departs "
                f"from its planimetric length by {deviation:.3f} m against the "
                f"{allowance:.3f} m agreement bound."
            )
        geodesic_total += geodesic
        element["cumulative_geodesic_m"] = round(geodesic_total, 3)
        if element["reversed_for_travel"]:
            reversed_count += 1
        if geometry_sink is not None:
            geometry_sink.append(
                LineString(list(travel_geometry.coords)[::-1])
                if element["reversed_for_travel"]
                else travel_geometry
            )
        elements.append(element)

    # Refuse anything that does not reproduce the locked artifacts exactly.
    planimetric_total = round(sum(planimetric_sums.values()), 3)
    if connected:
        recorded_edges = edge_entry["edges"]
        walked = [
            element
            for element in elements
            if element["kind"] in ("nhpn_edge", "nhpn_split_edge")
        ]
        if len(recorded_edges) != len(walked) or len(walked) != len(elements):
            raise ValueError(
                f"Segment '{segment_id}' directed walk does not reproduce the "
                "locked edge path."
            )
        for recorded, element in zip(recorded_edges, walked, strict=True):
            recorded_range = recorded.get("part_range_m")
            if (
                recorded["object_id"] != element["object_id"]
                or recorded["part_index"] != element["part_index"]
                or recorded["reversed_for_travel"] != element["reversed_for_travel"]
                or recorded["length_meters"] != element["length_m"]
                or recorded_range != element.get("part_range_m")
            ):
                raise ValueError(
                    f"Segment '{segment_id}' directed walk disagrees with the "
                    "locked edge path."
                )
        if planimetric_total != edge_entry["length_meters"]:
            raise ValueError(
                f"Segment '{segment_id}' directed length does not reproduce the "
                "locked edge-path length."
            )
        locked_reference = {
            "artifact": "edge-path-lock.v1",
            "length_m": edge_entry["length_meters"],
        }
    else:
        assert chain_entry is not None
        checks = (
            ("chain_length_meters", planimetric_total),
            ("nhpn_path_meters", round(planimetric_sums["nhpn"], 3)),
            ("fill_chord_meters", round(planimetric_sums["fill"], 3)),
            ("overlay_chord_meters", round(planimetric_sums["overlay"], 3)),
        )
        for key, value in checks:
            if chain_entry.get(key) != value:
                raise ValueError(
                    f"Segment '{segment_id}' directed walk does not reproduce the "
                    f"locked chain connectivity ({key})."
                )
        if sorted(fill_ids) != chain_entry.get("fill_site_ids_on_chain", []):
            raise ValueError(
                f"Segment '{segment_id}' traversed fills disagree with the locked "
                "chain."
            )
        if sorted(overlay_ids) != chain_entry.get("overlay_site_ids_on_chain", []):
            raise ValueError(
                f"Segment '{segment_id}' traversed overlays disagree with the "
                "locked chain."
            )
        recorded_splits = chain_entry.get("anchor_edge_splits", [])
        if canonical_sha256(splits) != canonical_sha256(recorded_splits):
            raise ValueError(
                f"Segment '{segment_id}' anchor resolution does not reproduce the "
                "locked anchor edge splits."
            )
        locked_reference = {
            "artifact": "reconstruction-overlay-lock.v1#chain_connectivity",
            "length_m": chain_entry["chain_length_meters"],
        }

    increasing_runs = _increasing_milepost_runs(elements)

    geodesic_total_rounded = round(geodesic_total, 3)
    nhpn_geodesic_rounded = round(nhpn_geodesic_total, 3)
    miles_total_rounded = round(miles_total, 6)
    miles_divergence = round(
        (miles_total_rounded * METRES_PER_MILE - nhpn_geodesic_rounded)
        / nhpn_geodesic_rounded,
        6,
    )
    if abs(miles_divergence) > NHPN_MILES_AGGREGATE_BOUND:
        raise ValueError(
            f"Segment '{segment_id}' NHPN MILES aggregation diverges from its "
            f"geodesic length by {miles_divergence:+.4%}, beyond the "
            f"{NHPN_MILES_AGGREGATE_BOUND:.0%} bound."
        )
    from_node = inverse.transform(*nodes[from_key])
    to_node = inverse.transform(*nodes[to_key])

    if connected and canonical_sha256(splits) != canonical_sha256(
        edge_entry.get("anchor_edge_splits", [])
    ):
        raise ValueError(
            f"Segment '{segment_id}' anchor resolution does not reproduce the "
            "locked anchor edge splits."
        )

    record: dict[str, Any] = {
        "segment_id": segment_id,
        "from_anchor": segment["from"],
        "to_anchor": segment["to"],
        "solve": "nhpn_connected" if connected else "mixed_ancestry_chain",
        "from_anchor_snap_distance_m": round(from_distance, 3),
        "to_anchor_snap_distance_m": round(to_distance, 3),
        "from_node": {
            "longitude": round(from_node[0], 9),
            "latitude": round(from_node[1], 9),
        },
        "to_node": {
            "longitude": round(to_node[0], 9),
            "latitude": round(to_node[1], 9),
        },
        "element_count": len(elements),
        "ancestry_counts": ancestry_counts,
        "reversed_for_travel_count": reversed_count,
        "planimetric_length_m": planimetric_total,
        "nhpn_planimetric_length_m": round(planimetric_sums["nhpn"], 3),
        "fill_chord_planimetric_length_m": round(planimetric_sums["fill"], 3),
        "overlay_chord_planimetric_length_m": round(planimetric_sums["overlay"], 3),
        "locked_reference": locked_reference,
        "geodesic_length_m": geodesic_total_rounded,
        "geodesic_planimetric_divergence_ratio": round(
            (geodesic_total_rounded - planimetric_total) / planimetric_total, 6
        ),
        "nhpn_geodesic_length_m": nhpn_geodesic_rounded,
        "nhpn_miles_sum": miles_total_rounded,
        "nhpn_miles_divergence_ratio": miles_divergence,
        "miles_unavailable_element_count": miles_unavailable,
        "facility_type_counts": dict(sorted(facility_counts.items())),
        "milepost_trend": trend_counts,
        "increasing_milepost_runs": increasing_runs,
        "thin_direction_elements": thin,
        "elements": elements,
    }
    if splits:
        record["anchor_edge_splits"] = splits
    return record


def _directed_junction_gaps(
    locked_ids: Sequence[str], record_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Continuity gaps between consecutive segments' recorded terminal nodes."""
    junctions: list[dict[str, Any]] = []
    for from_id, to_id in zip(locked_ids, locked_ids[1:], strict=False):
        exit_node = record_by_id[from_id]["to_node"]
        entry_node = record_by_id[to_id]["from_node"]
        gap = round(
            _geodesic_distance_m(
                (exit_node["longitude"], exit_node["latitude"]),
                (entry_node["longitude"], entry_node["latitude"]),
            ),
            3,
        )
        junctions.append(
            {
                "anchor_id": record_by_id[from_id]["to_anchor"],
                "from_segment_id": from_id,
                "to_segment_id": to_id,
                "continuity_gap_m": gap,
            }
        )
    return junctions


def _directed_path_records(
    selection: dict[str, Any],
    record_by_id: dict[str, dict[str, Any]],
    snapshot_ids: set[str],
) -> list[dict[str, Any]]:
    """One directed path record per ADR-0024 path, over the locked segments only."""
    selection_by_id = {segment["id"]: segment for segment in selection["segments"]}
    paths: list[dict[str, Any]] = []
    for path in selection["paths"]:
        locked_ids = [sid for sid in path["segment_ids"] if sid in snapshot_ids]
        excluded = [
            {
                "segment_id": sid,
                "geometry_status": selection_by_id[sid]["geometry_status"],
            }
            for sid in path["segment_ids"]
            if sid not in snapshot_ids
        ]
        if not locked_ids:
            raise ValueError(f"Path '{path['id']}' has no locked segments.")
        anchor_sequence = [selection_by_id[locked_ids[0]]["from"]]
        for previous_id, current_id in zip(locked_ids, locked_ids[1:], strict=False):
            if selection_by_id[previous_id]["to"] != selection_by_id[current_id]["from"]:
                raise ValueError(
                    f"Path '{path['id']}' locked segments do not chain: "
                    f"'{previous_id}' does not hand off to '{current_id}'."
                )
        anchor_sequence.extend(selection_by_id[sid]["to"] for sid in locked_ids)
        junctions = _directed_junction_gaps(locked_ids, record_by_id)
        backtracks = _path_junction_backtracks(path["id"], locked_ids, record_by_id)
        for junction in junctions:
            if junction["continuity_gap_m"] > JUNCTION_CONTINUITY_LIMIT_M:
                raise ValueError(
                    f"Path '{path['id']}' junction at '{junction['anchor_id']}' has a "
                    f"{junction['continuity_gap_m']:.3f} m continuity gap beyond the "
                    f"{JUNCTION_CONTINUITY_LIMIT_M:g} m limit."
                )
            backtrack = backtracks.get(
                junction["from_segment_id"],
                {"element_count": 0, "backtrack_length_m": 0.0},
            )
            junction["backtrack_element_count"] = backtrack["element_count"]
            junction["backtrack_length_m"] = backtrack["backtrack_length_m"]
        total_planimetric = round(
            sum(record_by_id[sid]["planimetric_length_m"] for sid in locked_ids), 3
        )
        total_geodesic = round(
            sum(record_by_id[sid]["geodesic_length_m"] for sid in locked_ids), 3
        )
        paths.append(
            {
                "path_id": path["id"],
                "role": path["role"],
                "anchor_sequence": anchor_sequence,
                "locked_segment_ids": locked_ids,
                "excluded_connector_segments": excluded,
                "junctions": junctions,
                "total_planimetric_m": total_planimetric,
                "total_geodesic_m": total_geodesic,
                "total_geodesic_miles": round(total_geodesic / METRES_PER_MILE, 3),
            }
        )
    return paths


def _directed_portal_exclusions(
    selection: dict[str, Any],
    transfer_lock: dict[str, Any],
    canonical_path: dict[str, Any],
) -> list[dict[str, Any]]:
    """The canonical path's pending endpoint connectors, with portal context.

    The straight-line portal-to-anchor distances are context only - never route
    geometry and never added to any distance figure.
    """
    selection_by_id = {segment["id"]: segment for segment in selection["segments"]}
    portal_coordinates = {
        endpoint["node_id"]: endpoint["coordinate"]
        for endpoint in selection["endpoints"].values()
    }
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    exclusions: list[dict[str, Any]] = []
    for excluded in canonical_path["excluded_connector_segments"]:
        segment = selection_by_id[excluded["segment_id"]]
        portal_ids = [
            node_id
            for node_id in (segment["from"], segment["to"])
            if node_id in portal_coordinates
        ]
        anchor_ids = [
            node_id
            for node_id in (segment["from"], segment["to"])
            if node_id in transfer_by_id
        ]
        if len(portal_ids) != 1 or len(anchor_ids) != 1:
            raise ValueError(
                f"Connector segment '{segment['id']}' does not join exactly one "
                "portal to exactly one locked anchor."
            )
        portal = portal_coordinates[portal_ids[0]]
        anchor = transfer_by_id[anchor_ids[0]]["coordinate"]
        exclusions.append(
            {
                "segment_id": segment["id"],
                "geometry_status": segment["geometry_status"],
                "portal_node_id": portal_ids[0],
                "anchor_id": anchor_ids[0],
                "portal_to_anchor_straight_line_m": round(
                    _geodesic_distance_m(
                        (portal["longitude"], portal["latitude"]),
                        (anchor["longitude"], anchor["latitude"]),
                    ),
                    1,
                ),
            }
        )
    return exclusions


def _directed_element_identity(element: dict[str, Any]) -> tuple[Any, ...]:
    if element["kind"] in ("nhpn_edge", "nhpn_split_edge"):
        return (
            element["object_id"],
            element["part_index"],
            tuple(element.get("part_range_m") or ()),
        )
    return (element["kind"], element["site_id"])


def _path_junction_backtracks(
    path_id: str,
    locked_ids: Sequence[str],
    record_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Measure, and bound, element overlap between a path's composed segments.

    Two consecutive segments may share elements in exactly one shape: a
    mirrored junction-approach backtrack, where the locked ADR-0024 anchor sits
    on pavement off the through junction, so the arriving traversal's final
    elements are the departing traversal's first elements travelled in the
    opposite orientation (observed at Barstow, where the anchor is the I-40
    terminus, and at Salt Lake City on the I-80/I-15 concurrency). That is a
    measured fact of the locked anchor model, recorded per junction; any other
    repetition - non-consecutive segments, non-contiguous overlap, or a repeat
    travelled in the same direction - is a defective composition and is
    refused. Junction and transfer geometry remain reconstruction-stage output.
    """
    identities = {
        segment_id: [
            _directed_element_identity(element)
            for element in record_by_id[segment_id]["elements"]
        ]
        for segment_id in locked_ids
    }
    backtracks: dict[str, dict[str, Any]] = {}
    for position, earlier_id in enumerate(locked_ids):
        for later_id in locked_ids[position + 1 :]:
            earlier = identities[earlier_id]
            later = identities[later_id]
            shared = set(earlier) & set(later)
            if not shared:
                continue
            if later_id != locked_ids[position + 1]:
                raise ValueError(
                    f"Path '{path_id}' repeats directed elements between "
                    f"non-consecutive segments '{earlier_id}' and '{later_id}'."
                )
            earlier_positions = sorted(earlier.index(identity) for identity in shared)
            later_positions = sorted(later.index(identity) for identity in shared)
            contiguous = (
                earlier_positions
                == list(range(earlier_positions[0], earlier_positions[-1] + 1))
                and later_positions
                == list(range(later_positions[0], later_positions[-1] + 1))
                and earlier_positions[-1] == len(earlier) - 1
                and later_positions[0] == 0
            )
            mirrored = [earlier[index] for index in earlier_positions] == [
                later[index] for index in reversed(later_positions)
            ]
            earlier_elements = record_by_id[earlier_id]["elements"]
            later_elements = record_by_id[later_id]["elements"]
            opposite = all(
                earlier_elements[earlier.index(identity)]["reversed_for_travel"]
                != later_elements[later.index(identity)]["reversed_for_travel"]
                for identity in shared
            )
            if not (contiguous and mirrored and opposite):
                raise ValueError(
                    f"Path '{path_id}' repeats directed elements between "
                    f"'{earlier_id}' and '{later_id}' in a shape that is not a "
                    "mirrored junction-approach backtrack."
                )
            backtracks[earlier_id] = {
                "element_count": len(shared),
                "backtrack_length_m": round(
                    sum(
                        earlier_elements[index]["length_m"]
                        for index in earlier_positions
                    ),
                    3,
                ),
            }
    return backtracks


def _directed_corridor_and_summary(
    selection: dict[str, Any],
    transfer_lock: dict[str, Any],
    fill_lock: dict[str, Any],
    overlay_lock: dict[str, Any],
    segments: Sequence[dict[str, Any]],
    paths: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The corridor and summary sections, recomputed identically by derivation
    and validation so the two can never disagree about an aggregate."""
    canonical = next(path for path in paths if path["role"] == "canonical")

    corridor_planimetric = round(
        sum(record["planimetric_length_m"] for record in segments), 3
    )
    corridor_planimetric_miles = round(corridor_planimetric / METRES_PER_MILE, 1)
    locked_corridor_miles = overlay_lock["corridor"][
        "continuously_chained_corridor_miles"
    ]
    if corridor_planimetric_miles != locked_corridor_miles:
        raise ValueError(
            "Directed corridor length does not reproduce the locked chained "
            f"corridor ({corridor_planimetric_miles} vs {locked_corridor_miles} mi)."
        )
    corridor_geodesic = round(
        sum(record["geodesic_length_m"] for record in segments), 3
    )
    corridor_nhpn_geodesic = round(
        sum(record["nhpn_geodesic_length_m"] for record in segments), 3
    )
    corridor_miles_sum = round(
        sum(record["nhpn_miles_sum"] for record in segments), 6
    )
    corridor_miles_divergence = round(
        (corridor_miles_sum * METRES_PER_MILE - corridor_nhpn_geodesic)
        / corridor_nhpn_geodesic,
        6,
    )
    if abs(corridor_miles_divergence) > NHPN_MILES_AGGREGATE_BOUND:
        raise ValueError(
            "Corridor NHPN MILES aggregation diverges beyond the "
            f"{NHPN_MILES_AGGREGATE_BOUND:.0%} bound."
        )

    traversed_fills: list[dict[str, Any]] = []
    traversed_fill_ids: set[str] = set()
    for record in segments:
        for element in record["elements"]:
            if element["kind"] != "nhs_fill_chord":
                continue
            traversed_fill_ids.add(element["site_id"])
            traversed_fills.append(
                {
                    "site_id": element["site_id"],
                    "segment_id": record["segment_id"],
                    "chord_m": element["length_m"],
                    "conflated_span_m": element["conflated_span"]["geometry_length_m"],
                    "delta_m": element["conflated_span"]["span_minus_chord_m"],
                }
            )
    traversed_fills.sort(key=lambda entry: entry["site_id"])
    untraversed_fills = [
        {
            "site_id": site["site_id"],
            "segment_id": site["segment_id"],
            "reason": (
                "The locked chain traversal does not cross this site's bridge: "
                "locked NHPN carries the traversal across its span (see the "
                "conflation lock's per-station agreement for the span)."
            ),
        }
        for site in sorted(fill_lock["sites"], key=lambda entry: entry["site_id"])
        if site["site_id"] not in traversed_fill_ids
    ]
    fill_delta_total = round(sum(entry["delta_m"] for entry in traversed_fills), 3)
    junction_gaps = [
        junction["continuity_gap_m"]
        for path in paths
        for junction in path["junctions"]
    ]
    backtracks_by_anchor: dict[str, dict[str, Any]] = {}
    for path in paths:
        for junction in path["junctions"]:
            if junction["backtrack_element_count"] == 0:
                continue
            entry = {
                "anchor_id": junction["anchor_id"],
                "element_count": junction["backtrack_element_count"],
                "backtrack_length_m": junction["backtrack_length_m"],
            }
            existing = backtracks_by_anchor.get(junction["anchor_id"])
            if existing is not None and existing != entry:
                raise ValueError(
                    f"Junction backtrack at '{junction['anchor_id']}' disagrees "
                    "between paths."
                )
            backtracks_by_anchor[junction["anchor_id"]] = entry
    junction_backtracks = [
        backtracks_by_anchor[anchor_id]
        for anchor_id in sorted(backtracks_by_anchor)
    ]
    canonical_backtrack_doubled = round(
        2.0
        * sum(
            junction["backtrack_length_m"] for junction in canonical["junctions"]
        ),
        3,
    )

    corridor = {
        "planimetric_length_m": corridor_planimetric,
        "planimetric_length_miles": corridor_planimetric_miles,
        "chained_corridor_miles_reference": locked_corridor_miles,
        "geodesic_length_m": corridor_geodesic,
        "geodesic_length_miles": round(corridor_geodesic / METRES_PER_MILE, 3),
        "geodesic_planimetric_divergence_ratio": round(
            (corridor_geodesic - corridor_planimetric) / corridor_planimetric, 6
        ),
        "authoritative_distance": {
            "claimed": True,
            "scope": "westbound_corridor_anchor_to_anchor",
            "path_id": canonical["path_id"],
            "from_anchor": canonical["anchor_sequence"][0],
            "to_anchor": canonical["anchor_sequence"][-1],
            "geodesic_length_m": canonical["total_geodesic_m"],
            "geodesic_length_miles": canonical["total_geodesic_miles"],
            "planimetric_length_m": canonical["total_planimetric_m"],
            "basis": (
                "GRS80 geodesic over the locked source centerline coordinates "
                "of the canonical westbound traversal, with traversed NHS fill "
                "and authored overlay chords at their pinned boundaries."
            ),
            "excluded_endpoint_connectors": _directed_portal_exclusions(
                selection, transfer_lock, canonical
            ),
            "adr_0024_note": (
                "ADR-0024's portal-to-portal run length remains unpublished "
                "until the authored endpoint connectors are checksum-locked; "
                "this figure is the locked highway corridor anchor-to-anchor."
            ),
            "fill_chord_refinement_note": (
                "Reconstruction replaces each traversed fill chord with its "
                "conflated NHS span; the recorded per-site deltas total "
                f"{fill_delta_total} m."
            ),
            "junction_backtrack_note": (
                "The composed figure includes "
                f"{canonical_backtrack_doubled} m of doubled junction-approach "
                "travel at anchors whose locked coordinate sits off the through "
                "junction (recorded per junction); transfer geometry is "
                "reconstruction-stage output."
            ),
        },
        "fill_spans": {
            "traversed": traversed_fills,
            "traversed_delta_total_m": fill_delta_total,
            "locked_but_not_on_directed_chain": untraversed_fills,
        },
        "junction_continuity": {
            "limit_m": JUNCTION_CONTINUITY_LIMIT_M,
            "max_gap_m": max(junction_gaps) if junction_gaps else 0.0,
            "backtracks": junction_backtracks,
        },
    }

    summary = {
        "element_count": sum(record["element_count"] for record in segments),
        "ancestry_counts": {
            kind: sum(record["ancestry_counts"][kind] for record in segments)
            for kind in (
                "nhpn_edge",
                "nhpn_split_edge",
                "nhs_fill_chord",
                "authored_overlay_chord",
            )
        },
        "reversed_for_travel_count": sum(
            record["reversed_for_travel_count"] for record in segments
        ),
        "milepost_trend": {
            trend: sum(record["milepost_trend"][trend] for record in segments)
            for trend in ("decreasing", "increasing", "flat", "unmeasured")
        },
        "facility_type_counts": {},
        "max_geodesic_planimetric_divergence_ratio": max(
            abs(record["geodesic_planimetric_divergence_ratio"])
            for record in segments
        ),
        "thin_direction_element_count": sum(
            len(indices)
            for record in segments
            for indices in record["thin_direction_elements"].values()
        ),
        "miles_cross_check": {
            "nhpn_miles_sum": corridor_miles_sum,
            "nhpn_geodesic_length_m": corridor_nhpn_geodesic,
            "nhpn_miles_divergence_ratio": corridor_miles_divergence,
            "finding": (
                "NHPN's MILES field is a coarse length assertion: the corridor "
                "aggregation runs short of the same records' geodesic geometry "
                "by the recorded ratio, where the NHS/ARNOLD MILES field agreed "
                "within about 0.9 percent on the fill records. Distance authority "
                "is the locked geometry; MILES is recorded as the source's own "
                "cross-check."
            ),
        },
    }
    facility_totals: dict[str, int] = {}
    for record in segments:
        for code, count in record["facility_type_counts"].items():
            facility_totals[code] = facility_totals.get(code, 0) + count
    summary["facility_type_counts"] = dict(sorted(facility_totals.items()))
    return corridor, summary


def derive_continental_directed_route_lock(
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    output_path: Path,
    *,
    derived_at: str | None = None,
) -> dict[str, Any]:
    """Derive the westbound directed edge sequence over the closed corridor.

    Consumes only checksum-locked inputs plus the locked NHPN response cache -
    no network access and no new acquisition. Every segment is traversed from
    its ADR-0024 from-anchor to its to-anchor on exactly the graph the edge-path
    and chain-connectivity locks solved, and the derivation refuses to write a
    lock whose traversal does not reproduce those artifacts to the millimetre.
    Direction is the traversal orientation over NHPN's single centerline
    topology; the reciprocal directed westbound carriageway remains
    reconstruction-stage output under ADR-0014 and is expressly not claimed.
    """
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    fill_lock = validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    validate_continental_break_dispositions(
        disposition_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
        nhs_fill_lock_path=fill_lock_path,
        overlay_lock_path=overlay_lock_path,
    )
    overlay_lock = validate_continental_reconstruction_overlays(
        overlay_lock_path,
        disposition_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        catalog_path,
    )
    conflation_lock = validate_continental_nhs_conflation(
        conflation_lock_path,
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )

    cache_root = (
        cache_directory / route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    )
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])
    anchor_limit = float(edge_lock["anchor_snap_limit_m"])
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    edge_by_id = {entry["segment_id"]: entry for entry in edge_lock["segments"]}
    chain_by_id = {
        entry["segment_id"]: entry
        for entry in overlay_lock["chain_connectivity"]["segments"]
    }
    conflation_site_by_id = {
        site["site_id"]: site for site in conflation_lock["sites"]
    }
    fills_by_segment: dict[str, list[dict[str, Any]]] = {}
    for site in fill_lock["sites"]:
        fills_by_segment.setdefault(site["segment_id"], []).append(site)
    overlays_by_segment: dict[str, list[dict[str, Any]]] = {}
    for overlay in overlay_lock["overlays"]:
        overlays_by_segment.setdefault(overlay["segment_id"], []).append(
            {
                "site_id": overlay["site_id"],
                "overlay_id": overlay["overlay_id"],
                "from_coordinate": overlay["boundary"]["from_coordinate"],
                "to_coordinate": overlay["boundary"]["to_coordinate"],
                "separation_m": overlay["boundary"]["length_m"],
                "geometry": overlay["geometry"],
            }
        )
    snapshot_ids = {
        snapshot["segment_id"]
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }

    segments: list[dict[str, Any]] = []
    for segment in selection["segments"]:
        if segment["id"] not in snapshot_ids:
            continue
        lines = _segment_locked_lines(route_lock, segment["id"], cache_root)
        edge_entry = edge_by_id[segment["id"]]
        segments.append(
            _derive_directed_segment(
                segment,
                edge_entry,
                chain_by_id.get(segment["id"]),
                lines,
                fills_by_segment.get(segment["id"], []),
                overlays_by_segment.get(segment["id"], []),
                conflation_site_by_id,
                forward.transform(
                    transfer_by_id[segment["from"]]["coordinate"]["longitude"],
                    transfer_by_id[segment["from"]]["coordinate"]["latitude"],
                ),
                forward.transform(
                    transfer_by_id[segment["to"]]["coordinate"]["longitude"],
                    transfer_by_id[segment["to"]]["coordinate"]["latitude"],
                ),
                tolerance,
                anchor_limit,
                forward,
                inverse,
            )
        )
    record_by_id = {record["segment_id"]: record for record in segments}
    paths = _directed_path_records(selection, record_by_id, snapshot_ids)
    corridor, summary = _directed_corridor_and_summary(
        selection, transfer_lock, fill_lock, overlay_lock, segments, paths
    )
    timestamp = derived_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")

    payload = {
        "schema_version": 1,
        "status": DIRECTED_ROUTE_STATUS,
        "route_decision": "ADR-0024",
        "carriageway_decision": "ADR-0014",
        "reconstruction_decision": "ADR-0018",
        "derived_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "endpoint_snap_tolerance_m": tolerance,
        "anchor_snap_limit_m": anchor_limit,
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "catalog_sha256": compute_sha256(catalog_path),
        "model": {
            "geodesic": {
                "ellipsoid": "GRS80",
                "method": (
                    "pyproj Geod.line_length over each record's locked EPSG:4326 "
                    "coordinates; split sub-edges over the EPSG:5070 substring "
                    "reprojected to EPSG:4326; chords between their pinned "
                    "boundary coordinates"
                ),
            },
            "geodesic_planimetric_agreement_ratio": (
                GEODESIC_PLANIMETRIC_AGREEMENT_RATIO
            ),
            "geodesic_rounding_allowance_m": GEODESIC_ROUNDING_ALLOWANCE_M,
            "nhpn_miles_aggregate_bound": NHPN_MILES_AGGREGATE_BOUND,
            "junction_continuity_limit_m": JUNCTION_CONTINUITY_LIMIT_M,
            "stationing_note": (
                "cumulative_geodesic_m is the millimetre-rounded running geodesic "
                "sum from the segment's from-anchor node; junction gaps are "
                "recorded separately and never added to stationing."
            ),
            "measure_note": (
                "Mileposts and state-LRS measures parametrise and key; they are "
                "never a length (2026-08-31 conflation finding: the measure axis "
                "is calibrated, not metric)."
            ),
        },
        "source_policy": {
            "candidate_source": NHPN_SOURCE_ID,
            "fill_source": NHS_SOURCE_ID,
            "authored_overlays": True,
            "nhpn_role": "coarse_topology_only",
            "lane_geometry_claimed": False,
            "carriageway_direction_claimed": False,
            "openstreetmap_ancestry_allowed": False,
            "continental_downloads_committed": False,
            "authoritative_corridor_distance_claimed": True,
        },
        "westbound_selection": {
            "validated": True,
            "level": "source_centerline_traversal",
            "carriageway_direction_claimed": False,
            "definition": (
                "Each segment is traversed from its ADR-0024 from-anchor to its "
                "to-anchor in the route selection's Atlantic-to-Pacific order; "
                "every element records its orientation relative to the locked "
                "source geometry."
            ),
            "carriageway_note": (
                "NHPN models these facilities as a single centerline (facility-"
                "type census recorded per segment); the reciprocal directed "
                "westbound carriageway is reconstruction-stage output under "
                "ADR-0014 and is not claimed here."
            ),
            "direction_evidence": {
                "primary": (
                    "anchor-to-anchor chain continuity over the locked closed "
                    "topology"
                ),
                "corroborating": [
                    "NHPN record milepost trend within shared LRS keys",
                    "NHS state-LRS measures at traversed fill seams",
                    "NHPN facility-type census",
                ],
            },
        },
        "segment_count": len(segments),
        "segments": segments,
        "segments_sha256": canonical_sha256(segments),
        "paths": paths,
        "paths_sha256": canonical_sha256(paths),
        "corridor": corridor,
        "summary": summary,
        "next_stage": DIRECTED_ROUTE_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _require_finite_number(value: Any, message: str, minimum: float | None = None) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(message)
    if minimum is not None and value < minimum:
        raise ValueError(message)
    return float(value)


def _validate_directed_segment_record(
    record: dict[str, Any],
    segment: dict[str, Any],
    edge_entry: dict[str, Any],
    chain_entry: dict[str, Any] | None,
    transfer_by_id: dict[str, dict[str, Any]],
    page_hashes_by_id: dict[int, set[str]],
    fill_site_by_id: dict[str, dict[str, Any]],
    overlay_by_site_id: dict[str, dict[str, Any]],
    conflation_site_by_id: dict[str, dict[str, Any]],
) -> None:
    """Recompute one directed segment record from its locked inputs and refuse
    any recorded quantity the elements beside it do not reproduce."""
    segment_id = record["segment_id"]
    connected = edge_entry.get("connected") is True
    if record.get("from_anchor") != segment["from"] or record.get("to_anchor") != segment["to"]:
        raise ValueError(f"Segment '{segment_id}' anchors drifted from the selection.")
    expected_solve = "nhpn_connected" if connected else "mixed_ancestry_chain"
    if record.get("solve") != expected_solve:
        raise ValueError(f"Segment '{segment_id}' records the wrong solve kind.")
    if connected:
        locked_from = edge_entry["from_transfer_node_snap_distance_m"]
        locked_to = edge_entry["to_transfer_node_snap_distance_m"]
        locked_splits = edge_entry.get("anchor_edge_splits", [])
    else:
        if chain_entry is None:
            raise ValueError(f"Segment '{segment_id}' has no locked chain entry.")
        locked_from = chain_entry["from_anchor_snap_distance_m"]
        locked_to = chain_entry["to_anchor_snap_distance_m"]
        locked_splits = chain_entry.get("anchor_edge_splits", [])
    if (
        record.get("from_anchor_snap_distance_m") != locked_from
        or record.get("to_anchor_snap_distance_m") != locked_to
    ):
        raise ValueError(
            f"Segment '{segment_id}' anchor snap distances drifted from the locks."
        )
    if canonical_sha256(record.get("anchor_edge_splits", [])) != canonical_sha256(
        locked_splits
    ):
        raise ValueError(
            f"Segment '{segment_id}' anchor edge splits drifted from the locks."
        )
    for side in ("from", "to"):
        node = record.get(f"{side}_node")
        if not isinstance(node, dict):
            raise ValueError(f"Segment '{segment_id}' records no {side} node.")
        longitude = _require_finite_number(
            node.get("longitude"), f"Segment '{segment_id}' {side} node is invalid."
        )
        latitude = _require_finite_number(
            node.get("latitude"), f"Segment '{segment_id}' {side} node is invalid."
        )
        anchor = transfer_by_id[segment[side]]["coordinate"]
        distance = _geodesic_distance_m(
            (longitude, latitude), (anchor["longitude"], anchor["latitude"])
        )
        allowed = (
            ANCHOR_SNAP_LIMIT_METERS * (1.0 + GEODESIC_PLANIMETRIC_AGREEMENT_RATIO)
            + GEODESIC_ROUNDING_ALLOWANCE_M
        )
        if distance > allowed:
            raise ValueError(
                f"Segment '{segment_id}' {side} node sits {distance:.3f} m from its "
                "locked anchor, beyond the anchor snap limit."
            )

    elements = record.get("elements")
    if not isinstance(elements, list) or not elements:
        raise ValueError(f"Segment '{segment_id}' records no directed elements.")
    ancestry = {
        "nhpn_edge": 0,
        "nhpn_split_edge": 0,
        "nhs_fill_chord": 0,
        "authored_overlay_chord": 0,
    }
    trend_counts = {"decreasing": 0, "increasing": 0, "flat": 0, "unmeasured": 0}
    facility_counts: dict[str, int] = {}
    thin = {"flat_milepost": [], "unmeasured_milepost": [], "authored_overlay": []}
    length_sums = {"nhpn": 0.0, "fill": 0.0, "overlay": 0.0}
    geodesic_sum = 0.0
    nhpn_geodesic_sum = 0.0
    miles_sum = 0.0
    miles_unavailable = 0
    reversed_count = 0
    previous_cumulative = 0.0
    seen: set[tuple[Any, ...]] = set()
    fill_ids: list[str] = []
    overlay_ids: list[str] = []

    for index, element in enumerate(elements):
        kind = element.get("kind")
        if kind not in ancestry:
            raise ValueError(
                f"Segment '{segment_id}' element {index} has unknown kind '{kind}'."
            )
        length = _require_finite_number(
            element.get("length_m"),
            f"Segment '{segment_id}' element {index} has no finite length.",
            minimum=0.0,
        )
        geodesic = _require_finite_number(
            element.get("geodesic_length_m"),
            f"Segment '{segment_id}' element {index} has no finite geodesic length.",
            minimum=0.0,
        )
        if abs(geodesic - length) > (
            GEODESIC_PLANIMETRIC_AGREEMENT_RATIO * length
            + GEODESIC_ROUNDING_ALLOWANCE_M
        ):
            raise ValueError(
                f"Segment '{segment_id}' element {index} breaks the geodesic-"
                "planimetric agreement bound."
            )
        cumulative = _require_finite_number(
            element.get("cumulative_geodesic_m"),
            f"Segment '{segment_id}' element {index} has no finite stationing.",
            minimum=0.0,
        )
        if abs(cumulative - previous_cumulative - geodesic) > 0.002:
            raise ValueError(
                f"Segment '{segment_id}' element {index} breaks the cumulative "
                "stationing cascade."
            )
        previous_cumulative = cumulative
        if not isinstance(element.get("reversed_for_travel"), bool):
            raise ValueError(
                f"Segment '{segment_id}' element {index} records no travel "
                "orientation."
            )
        if element["reversed_for_travel"]:
            reversed_count += 1
        ancestry[kind] += 1
        geodesic_sum += geodesic

        if kind in ("nhpn_edge", "nhpn_split_edge"):
            object_id = element.get("object_id")
            if not isinstance(object_id, int) or object_id not in page_hashes_by_id:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} cites an unlocked "
                    "NHPN record."
                )
            part_index = element.get("part_index")
            if not isinstance(part_index, int) or part_index < 0:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} has an invalid part."
                )
            if not isinstance(element.get("lrs_key"), str):
                raise ValueError(
                    f"Segment '{segment_id}' element {index} records no LRS key."
                )
            part_range = element.get("part_range_m")
            if kind == "nhpn_split_edge":
                if (
                    not isinstance(part_range, list)
                    or len(part_range) != 2
                    or not 0.0 <= part_range[0] < part_range[1]
                ):
                    raise ValueError(
                        f"Segment '{segment_id}' element {index} split range is "
                        "invalid."
                    )
            elif part_range is not None:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} is not a split but "
                    "records a part range."
                )
            entry_milepost = element.get("entry_milepost")
            exit_milepost = element.get("exit_milepost")
            if (entry_milepost is None) != (exit_milepost is None):
                raise ValueError(
                    f"Segment '{segment_id}' element {index} records a one-sided "
                    "milepost."
                )
            if kind == "nhpn_split_edge" and entry_milepost is not None:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} interpolates a "
                    "milepost onto a split sub-edge."
                )
            if entry_milepost is not None:
                _require_finite_number(
                    entry_milepost,
                    f"Segment '{segment_id}' element {index} milepost is invalid.",
                )
                _require_finite_number(
                    exit_milepost,
                    f"Segment '{segment_id}' element {index} milepost is invalid.",
                )
            miles = element.get("miles")
            if miles is None:
                miles_unavailable += 1
            else:
                miles_sum += _require_finite_number(
                    miles,
                    f"Segment '{segment_id}' element {index} MILES is invalid.",
                    minimum=0.0,
                )
            facility_type = element.get("facility_type")
            if facility_type is not None and (
                not isinstance(facility_type, int) or isinstance(facility_type, bool)
            ):
                raise ValueError(
                    f"Segment '{segment_id}' element {index} facility type is "
                    "invalid."
                )
            facility_key = "null" if facility_type is None else str(facility_type)
            facility_counts[facility_key] = facility_counts.get(facility_key, 0) + 1
            trend = _milepost_trend(entry_milepost, exit_milepost)
            trend_counts[trend] += 1
            if trend == "flat":
                thin["flat_milepost"].append(index)
            elif trend == "unmeasured":
                thin["unmeasured_milepost"].append(index)
            length_sums["nhpn"] += length
            nhpn_geodesic_sum += geodesic
            identity = (
                object_id,
                part_index,
                tuple(part_range) if part_range else (),
            )
        elif kind == "nhs_fill_chord":
            if connected:
                raise ValueError(
                    f"Segment '{segment_id}' is NHPN-connected but traverses a "
                    "fill chord."
                )
            site_id = element.get("site_id")
            site = fill_site_by_id.get(site_id)
            if site is None or site["segment_id"] != segment_id:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} cites an unlocked "
                    "fill site."
                )
            if element["length_m"] != round(float(site["separation_m"]), 3):
                raise ValueError(
                    f"Segment '{segment_id}' element {index} chord length drifted "
                    "from the fill lock."
                )
            chord = round(
                _geodesic_line_length_m(
                    [
                        (
                            site["from_coordinate"]["longitude"],
                            site["from_coordinate"]["latitude"],
                        ),
                        (
                            site["to_coordinate"]["longitude"],
                            site["to_coordinate"]["latitude"],
                        ),
                    ]
                ),
                3,
            )
            if element["geodesic_length_m"] != chord:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} geodesic chord does "
                    "not reproduce from the pinned boundary."
                )
            conflation_site = conflation_site_by_id.get(site_id)
            if conflation_site is None:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} has no conflation "
                    "span."
                )
            measure_by_side = {
                seam["side"]: seam["nhs"]["measure_at_seam"]
                for seam in conflation_site["seams"]
            }
            entry_side = "to" if element["reversed_for_travel"] else "from"
            exit_side = "from" if element["reversed_for_travel"] else "to"
            if (
                element.get("entry_measure") != measure_by_side.get(entry_side)
                or element.get("exit_measure") != measure_by_side.get(exit_side)
                or element.get("measure_trend")
                != _milepost_trend(
                    measure_by_side.get(entry_side), measure_by_side.get(exit_side)
                )
            ):
                raise ValueError(
                    f"Segment '{segment_id}' element {index} seam measures drifted "
                    "from the conflation lock."
                )
            if element.get("nhs_route") != {
                "state_fips": conflation_site["group"]["state_fips"],
                "route_id": conflation_site["group"]["route_id"],
            }:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} NHS route identity "
                    "drifted."
                )
            span = conflation_site["span"]
            recorded_span = element.get("conflated_span")
            if recorded_span != {
                "geometry_sha256": span["geometry_sha256"],
                "geometry_length_m": span["geometry_length_m"],
                "span_minus_chord_m": round(
                    span["geometry_length_m"] - element["length_m"], 3
                ),
            }:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} conflated span "
                    "citation drifted."
                )
            length_sums["fill"] += length
            fill_ids.append(site_id)
            identity = (kind, site_id)
        else:
            if connected:
                raise ValueError(
                    f"Segment '{segment_id}' is NHPN-connected but traverses an "
                    "overlay chord."
                )
            site_id = element.get("site_id")
            overlay = overlay_by_site_id.get(site_id)
            if overlay is None or overlay["segment_id"] != segment_id:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} cites an unauthored "
                    "overlay."
                )
            if element.get("overlay_id") != overlay["overlay_id"]:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} overlay identity "
                    "drifted."
                )
            if element["length_m"] != round(float(overlay["boundary"]["length_m"]), 3):
                raise ValueError(
                    f"Segment '{segment_id}' element {index} overlay chord length "
                    "drifted."
                )
            recomputed = round(
                _geodesic_line_length_m(overlay["geometry"]["coordinates"]), 3
            )
            if element["geodesic_length_m"] != recomputed:
                raise ValueError(
                    f"Segment '{segment_id}' element {index} overlay geodesic "
                    "length does not reproduce from the authored geometry."
                )
            length_sums["overlay"] += length
            overlay_ids.append(site_id)
            thin["authored_overlay"].append(index)
            identity = (kind, site_id)
        if identity in seen:
            raise ValueError(
                f"Segment '{segment_id}' repeats directed element {identity}."
            )
        seen.add(identity)

    if record.get("element_count") != len(elements):
        raise ValueError(f"Segment '{segment_id}' element count disagrees.")
    if record.get("ancestry_counts") != ancestry:
        raise ValueError(f"Segment '{segment_id}' ancestry counts disagree.")
    if record.get("reversed_for_travel_count") != reversed_count:
        raise ValueError(f"Segment '{segment_id}' orientation census disagrees.")
    if record.get("facility_type_counts") != dict(sorted(facility_counts.items())):
        raise ValueError(f"Segment '{segment_id}' facility-type census disagrees.")
    if record.get("milepost_trend") != trend_counts:
        raise ValueError(f"Segment '{segment_id}' milepost trend census disagrees.")
    if record.get("thin_direction_elements") != thin:
        raise ValueError(f"Segment '{segment_id}' thin-evidence census disagrees.")
    if record.get("increasing_milepost_runs") != _increasing_milepost_runs(elements):
        raise ValueError(f"Segment '{segment_id}' milepost trend runs disagree.")
    if record.get("miles_unavailable_element_count") != miles_unavailable:
        raise ValueError(f"Segment '{segment_id}' MILES availability disagrees.")

    for field, sum_key in (
        ("nhpn_planimetric_length_m", "nhpn"),
        ("fill_chord_planimetric_length_m", "fill"),
        ("overlay_chord_planimetric_length_m", "overlay"),
    ):
        recorded = _require_finite_number(
            record.get(field), f"Segment '{segment_id}' records no finite {field}.",
            minimum=0.0,
        )
        count = (
            ancestry["nhpn_edge"] + ancestry["nhpn_split_edge"]
            if sum_key == "nhpn"
            else ancestry["nhs_fill_chord"]
            if sum_key == "fill"
            else ancestry["authored_overlay_chord"]
        )
        if abs(length_sums[sum_key] - recorded) > _rounding_envelope_m(count):
            raise ValueError(
                f"Segment '{segment_id}' {field} disagrees with its elements."
            )
    planimetric = _require_finite_number(
        record.get("planimetric_length_m"),
        f"Segment '{segment_id}' records no finite planimetric length.",
        minimum=0.0,
    )
    if (
        abs(
            record["nhpn_planimetric_length_m"]
            + record["fill_chord_planimetric_length_m"]
            + record["overlay_chord_planimetric_length_m"]
            - planimetric
        )
        > _rounding_envelope_m(3)
    ):
        raise ValueError(
            f"Segment '{segment_id}' planimetric length disagrees with its "
            "ancestry decomposition."
        )

    if connected:
        recorded_edges = edge_entry["edges"]
        if record["locked_reference"] != {
            "artifact": "edge-path-lock.v1",
            "length_m": edge_entry["length_meters"],
        }:
            raise ValueError(f"Segment '{segment_id}' locked reference drifted.")
        if planimetric != edge_entry["length_meters"]:
            raise ValueError(
                f"Segment '{segment_id}' planimetric length does not reproduce "
                "the locked edge-path length."
            )
        if len(recorded_edges) != len(elements):
            raise ValueError(
                f"Segment '{segment_id}' does not cover the locked edge path."
            )
        for locked_edge, element in zip(recorded_edges, elements, strict=True):
            if (
                locked_edge["object_id"] != element.get("object_id")
                or locked_edge["part_index"] != element.get("part_index")
                or locked_edge["reversed_for_travel"]
                != element.get("reversed_for_travel")
                or locked_edge["length_meters"] != element.get("length_m")
                or locked_edge.get("part_range_m") != element.get("part_range_m")
            ):
                raise ValueError(
                    f"Segment '{segment_id}' directed sequence disagrees with the "
                    "locked edge path."
                )
    else:
        assert chain_entry is not None
        if record["locked_reference"] != {
            "artifact": "reconstruction-overlay-lock.v1#chain_connectivity",
            "length_m": chain_entry["chain_length_meters"],
        }:
            raise ValueError(f"Segment '{segment_id}' locked reference drifted.")
        for field, key in (
            ("planimetric_length_m", "chain_length_meters"),
            ("nhpn_planimetric_length_m", "nhpn_path_meters"),
            ("fill_chord_planimetric_length_m", "fill_chord_meters"),
            ("overlay_chord_planimetric_length_m", "overlay_chord_meters"),
        ):
            if record[field] != chain_entry.get(key):
                raise ValueError(
                    f"Segment '{segment_id}' {field} does not reproduce the "
                    "locked chain connectivity."
                )
        if sorted(fill_ids) != chain_entry.get("fill_site_ids_on_chain", []):
            raise ValueError(
                f"Segment '{segment_id}' traversed fills disagree with the locked "
                "chain."
            )
        if sorted(overlay_ids) != chain_entry.get("overlay_site_ids_on_chain", []):
            raise ValueError(
                f"Segment '{segment_id}' traversed overlays disagree with the "
                "locked chain."
            )

    geodesic_total = _require_finite_number(
        record.get("geodesic_length_m"),
        f"Segment '{segment_id}' records no finite geodesic length.",
        minimum=0.0,
    )
    if elements[-1]["cumulative_geodesic_m"] != geodesic_total:
        raise ValueError(
            f"Segment '{segment_id}' stationing does not end at its geodesic "
            "length."
        )
    if abs(geodesic_sum - geodesic_total) > _rounding_envelope_m(len(elements)):
        raise ValueError(
            f"Segment '{segment_id}' geodesic length disagrees with its elements."
        )
    nhpn_geodesic = _require_finite_number(
        record.get("nhpn_geodesic_length_m"),
        f"Segment '{segment_id}' records no finite NHPN geodesic length.",
        minimum=0.0,
    )
    nhpn_count = ancestry["nhpn_edge"] + ancestry["nhpn_split_edge"]
    if abs(nhpn_geodesic_sum - nhpn_geodesic) > _rounding_envelope_m(nhpn_count):
        raise ValueError(
            f"Segment '{segment_id}' NHPN geodesic length disagrees with its "
            "elements."
        )
    if abs(geodesic_total - planimetric) > (
        GEODESIC_PLANIMETRIC_AGREEMENT_RATIO * planimetric
        + GEODESIC_ROUNDING_ALLOWANCE_M
    ):
        raise ValueError(
            f"Segment '{segment_id}' breaks the geodesic-planimetric agreement "
            "bound."
        )
    if record.get("geodesic_planimetric_divergence_ratio") != round(
        (geodesic_total - planimetric) / planimetric, 6
    ):
        raise ValueError(
            f"Segment '{segment_id}' divergence ratio does not reproduce."
        )
    miles_recorded = _require_finite_number(
        record.get("nhpn_miles_sum"),
        f"Segment '{segment_id}' records no finite MILES aggregation.",
        minimum=0.0,
    )
    if abs(miles_sum - miles_recorded) > _rounding_envelope_m(nhpn_count, 1e-6):
        raise ValueError(
            f"Segment '{segment_id}' MILES aggregation disagrees with its "
            "elements."
        )
    expected_divergence = round(
        (miles_recorded * METRES_PER_MILE - nhpn_geodesic) / nhpn_geodesic, 6
    )
    if record.get("nhpn_miles_divergence_ratio") != expected_divergence:
        raise ValueError(
            f"Segment '{segment_id}' MILES divergence ratio does not reproduce."
        )
    if abs(expected_divergence) > NHPN_MILES_AGGREGATE_BOUND:
        raise ValueError(
            f"Segment '{segment_id}' MILES aggregation diverges beyond the "
            f"{NHPN_MILES_AGGREGATE_BOUND:.0%} bound."
        )


def validate_continental_directed_route_lock(
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the directed route lock without the ignored response cache.

    Everything recomputable without the cache is recomputed: the pins, every
    per-element citation against the locks that own it, the stationing cascade,
    the censuses, the exact reproduction of the edge-path and chain-connectivity
    figures, and the paths, corridor, and summary sections through the same
    helpers the derivation used. The NHPN element geometry itself lives in the
    cache; its lengths are held to the locked artifacts and the recorded
    agreement bounds instead.
    """
    payload = load_json(directed_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Directed route lock schema_version must be 1.")
    if payload.get("status") != DIRECTED_ROUTE_STATUS:
        raise ValueError("Directed route lock has an unsupported status.")
    for field, expected in (
        ("route_decision", "ADR-0024"),
        ("carriageway_decision", "ADR-0014"),
        ("reconstruction_decision", "ADR-0018"),
        ("coordinate_crs", "EPSG:4326"),
        ("metric_crs", "EPSG:5070"),
    ):
        if payload.get(field) != expected:
            raise ValueError(f"Directed route lock {field} drifted.")
    tolerance = payload.get("endpoint_snap_tolerance_m")
    if (
        not isinstance(tolerance, int | float)
        or isinstance(tolerance, bool)
        or not 0 < tolerance <= MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS
    ):
        raise ValueError(
            "Directed route lock declares a snap tolerance outside the permitted "
            f"range of 0 to {MAXIMUM_ENDPOINT_SNAP_TOLERANCE_METERS} m."
        )
    if payload.get("anchor_snap_limit_m") != ANCHOR_SNAP_LIMIT_METERS:
        raise ValueError("Directed route lock declares a non-standard anchor limit.")
    model = payload.get("model")
    if not isinstance(model, dict):
        raise ValueError("Directed route lock records no model.")
    for field, expected in (
        ("geodesic_planimetric_agreement_ratio", GEODESIC_PLANIMETRIC_AGREEMENT_RATIO),
        ("geodesic_rounding_allowance_m", GEODESIC_ROUNDING_ALLOWANCE_M),
        ("nhpn_miles_aggregate_bound", NHPN_MILES_AGGREGATE_BOUND),
        ("junction_continuity_limit_m", JUNCTION_CONTINUITY_LIMIT_M),
    ):
        if model.get(field) != expected:
            raise ValueError(f"Directed route lock widens or drifts the {field} bound.")
    if not isinstance(model.get("geodesic"), dict) or model["geodesic"].get(
        "ellipsoid"
    ) != "GRS80":
        raise ValueError("Directed route lock geodesic model drifted.")
    source_policy = payload.get("source_policy")
    if not isinstance(source_policy, dict):
        raise ValueError("Directed route lock records no source policy.")
    for field, expected in (
        ("carriageway_direction_claimed", False),
        ("lane_geometry_claimed", False),
        ("openstreetmap_ancestry_allowed", False),
        ("continental_downloads_committed", False),
        ("authoritative_corridor_distance_claimed", True),
    ):
        if source_policy.get(field) is not expected:
            raise ValueError(f"Directed route lock source policy {field} drifted.")
    westbound = payload.get("westbound_selection")
    if (
        not isinstance(westbound, dict)
        or westbound.get("validated") is not True
        or westbound.get("level") != "source_centerline_traversal"
        or westbound.get("carriageway_direction_claimed") is not False
    ):
        raise ValueError(
            "Directed route lock westbound-selection claim drifted: this stage "
            "validates the source-centerline traversal and expressly not a "
            "carriageway direction."
        )

    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    fill_lock = validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    validate_continental_break_dispositions(
        disposition_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
        nhs_fill_lock_path=fill_lock_path,
        overlay_lock_path=overlay_lock_path,
    )
    overlay_lock = validate_continental_reconstruction_overlays(
        overlay_lock_path,
        disposition_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        catalog_path,
    )
    conflation_lock = validate_continental_nhs_conflation(
        conflation_lock_path,
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    for field, path in (
        ("route_selection_sha256", selection_path),
        ("candidate_lock_sha256", route_lock_path),
        ("transfer_lock_sha256", transfer_lock_path),
        ("edge_path_lock_sha256", edge_path_lock_path),
        ("nhs_fill_lock_sha256", fill_lock_path),
        ("break_disposition_sha256", disposition_path),
        ("reconstruction_overlay_lock_sha256", overlay_lock_path),
        ("nhs_conflation_lock_sha256", conflation_lock_path),
        ("catalog_sha256", catalog_path),
    ):
        if payload.get(field) != compute_sha256(path):
            raise ValueError(f"Directed route lock {field} does not match its input.")

    snapshot_ids = {
        snapshot["segment_id"]
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }
    ordered_ids = [
        segment["id"] for segment in selection["segments"] if segment["id"] in snapshot_ids
    ]
    segments = payload.get("segments")
    if not isinstance(segments, list) or [
        record.get("segment_id") for record in segments
    ] != ordered_ids:
        raise ValueError(
            "Directed route lock does not cover exactly the locked segments in "
            "selection order."
        )
    if payload.get("segment_count") != len(segments):
        raise ValueError("Directed route lock segment count disagrees.")
    if payload.get("segments_sha256") != canonical_sha256(segments):
        raise ValueError("Directed route lock segment digest drifted.")

    selection_by_id = {segment["id"]: segment for segment in selection["segments"]}
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    edge_by_id = {entry["segment_id"]: entry for entry in edge_lock["segments"]}
    chain_by_id = {
        entry["segment_id"]: entry
        for entry in overlay_lock["chain_connectivity"]["segments"]
    }
    page_hashes_by_id = _locked_page_hashes_by_object_id(route_lock)
    fill_site_by_id = {site["site_id"]: site for site in fill_lock["sites"]}
    overlay_by_site_id = {
        overlay["site_id"]: overlay for overlay in overlay_lock["overlays"]
    }
    conflation_site_by_id = {
        site["site_id"]: site for site in conflation_lock["sites"]
    }
    for record in segments:
        _validate_directed_segment_record(
            record,
            selection_by_id[record["segment_id"]],
            edge_by_id[record["segment_id"]],
            chain_by_id.get(record["segment_id"]),
            transfer_by_id,
            page_hashes_by_id,
            fill_site_by_id,
            overlay_by_site_id,
            conflation_site_by_id,
        )

    record_by_id = {record["segment_id"]: record for record in segments}
    expected_paths = _directed_path_records(selection, record_by_id, snapshot_ids)
    if payload.get("paths") != expected_paths:
        raise ValueError(
            "Directed route lock paths do not reproduce from the locked segments."
        )
    if payload.get("paths_sha256") != canonical_sha256(expected_paths):
        raise ValueError("Directed route lock path digest drifted.")
    expected_corridor, expected_summary = _directed_corridor_and_summary(
        selection, transfer_lock, fill_lock, overlay_lock, segments, expected_paths
    )
    if payload.get("corridor") != expected_corridor:
        raise ValueError(
            "Directed route lock corridor section does not reproduce from the "
            "locked segments."
        )
    if payload.get("summary") != expected_summary:
        raise ValueError(
            "Directed route lock summary does not reproduce from the locked "
            "segments."
        )
    if payload.get("next_stage") != DIRECTED_ROUTE_NEXT_STAGE:
        raise ValueError("Directed route lock next stage drifted.")
    return payload


# --- ADR-0007 corridor elevation acquisition over the directed route --------------
#
# The 3DEP product lock is the contract: exact dated immutable staged-product
# URLs, discovery byte counts, per-tile datum evidence, and three sample tiles
# already verified end to end. This stage executes that contract - every locked
# tile is downloaded, verified against its declaration (byte count, first
# recorded or pinned SHA-256, full raster inspection), and sampled along the
# locked westbound directed route - and locks the corridor's first elevation
# profile. Rasters stay in the ignored cache (optionally released after
# verification); the committed artifact carries the hashes, the stations, and
# the statistics.

CORRIDOR_ELEVATION_STATUS = "corridor_elevation_acquired_reconstruction_pending"

# One station every 100 m of directed geodesic stationing (plus the terminal
# station) resolves grade features an order of magnitude wider than the
# raster's ~10 m cells without committing a megabyte-scale artifact per
# segment. Sustained grade is the mean grade over a 1 km window - the scale of
# a real mountain-grade sign, not a single raster cell.
ELEVATION_STATION_INTERVAL_M = 100.0
ELEVATION_SUSTAINED_WINDOW_M = 1000.0
ELEVATION_VALUE_DECIMALS = 2
# A station may sit a reprojection epsilon outside its floored cell when an
# element crosses a cell edge between vertices; the staged tiles overhang their
# nominal cell by ~0.002 degrees, so a neighbouring locked cell within this
# margin samples identically.
ELEVATION_CELL_EDGE_EPSILON_DEG = 1e-6

ELEVATION_SAMPLER_MODEL = {
    "interpolation": "bilinear between raster cell centres",
    "station_crs": "EPSG:4326",
    "raster_crs": "EPSG:4269",
    "nodata_policy": "refuse",
}

# Characterised source-side declaration defects, refused unless pinned here
# exactly. A HEAD census of all 124 locked product URLs on 2026-08-31 found
# exactly six catalog declarations disagreeing with the immutable dated S3
# objects, every one of which was last modified 2022-12-03 - years before the
# product lock's discovery snapshot - so the defect is TNM's catalog size
# index, not object drift: two sub-megabyte nonsense declarations (n36w102,
# n36w103: a ~361 KB / ~338 KB claim for ~350 MB tiles) and four
# percent-scale staleness errors (n36w104 -0.14%, n38w080 +11.8%, n42w086
# +0.13%, n42w087 +0.18%, declared relative to actual). Live re-discovery
# still asserts the defective values (items lastUpdated 2026-06-08), and the
# S3 objects' own Content-Lengths match the downloads byte for byte. All six
# rasters verify fully - CRS, exact 1/3 arc-second pixels, single float32
# band, locked nodata, full cell coverage - so each pin holds its tile to
# the measured size AND its SHA-256, strictly tighter than the defective
# declaration it stands in for. The other 118 tiles stay under byte
# equality, and an unpinned mismatch anywhere is still a refusal.
ELEVATION_DECLARED_SIZE_EXCEPTIONS = {
    "n36w102": {
        "declared_size_bytes": 361416,
        "measured_byte_count": 370105790,
        "sha256": "0b4c8518558a35408b875e4d14112188cbcef73b6db294911b9c1b7cc0b79a2c",
        "reason": (
            "TNM catalog sizeInBytes misdeclares the immutable staged object; "
            "the S3 object's own Content-Length matches the measured bytes"
        ),
    },
    "n36w103": {
        "declared_size_bytes": 338581,
        "measured_byte_count": 346722950,
        "sha256": "cba6c24be98497a574f044ab46cee5c2da5573b235024bbe96d311b1ece57ec3",
        "reason": (
            "TNM catalog sizeInBytes misdeclares the immutable staged object; "
            "the S3 object's own Content-Length matches the measured bytes"
        ),
    },
    "n36w104": {
        "declared_size_bytes": 363746466,
        "measured_byte_count": 364271986,
        "sha256": "ffa3e9d85ec7a8cf1a0bbb73a5bc39ad75273de9b727796fad55f06b9563f0ee",
        "reason": (
            "TNM catalog sizeInBytes misdeclares the immutable staged object; "
            "the S3 object's own Content-Length matches the measured bytes"
        ),
    },
    "n38w080": {
        "declared_size_bytes": 543397409,
        "measured_byte_count": 486226211,
        "sha256": "cae7570266a794b58c33f8aac96d9edffc2f48e4e6a15c4fe4dae931e113cc3f",
        "reason": (
            "TNM catalog sizeInBytes misdeclares the immutable staged object; "
            "the S3 object's own Content-Length matches the measured bytes"
        ),
    },
    "n42w086": {
        "declared_size_bytes": 430468098,
        "measured_byte_count": 429895986,
        "sha256": "f2e8fb009073aeefafd7d181053473b2397d63c4a46f8d839d3a264b3cf7bc97",
        "reason": (
            "TNM catalog sizeInBytes misdeclares the immutable staged object; "
            "the S3 object's own Content-Length matches the measured bytes"
        ),
    },
    "n42w087": {
        "declared_size_bytes": 400229668,
        "measured_byte_count": 399510396,
        "sha256": "cec8c921bfc9ddd2c39a27359bb30386ea787bbf2f292423716dea6a4ffd7434",
        "reason": (
            "TNM catalog sizeInBytes misdeclares the immutable staged object; "
            "the S3 object's own Content-Length matches the measured bytes"
        ),
    },
}

CORRIDOR_ELEVATION_SOURCE_POLICY = {
    "elevation_source": DEM_SOURCE_ID,
    "baseline_decision": "ADR-0007",
    "one_meter_upgrade": "remains gated per ADR-0007 and is not locked here",
    "opportunistic_lookup_allowed": False,
    "silent_resolution_fallback_allowed": False,
    "continental_downloads_committed": False,
    "profile_smoothing_applied": False,
    "authoritative_distance_claimed": False,
}

CORRIDOR_ELEVATION_NEXT_STAGE = {
    "id": "reconstruction-geometry",
    "requires": [
        "reciprocal directed westbound carriageway reconstruction under ADR-0014",
        "full ADR-0018 gate battery, including the gates deferred at the two "
        "overlay sites and the recorded Quad Cities 77.2 degree corner constraint",
        "ADR-0017 vertical profile conditioning and grade policy at package build",
        "authored endpoint connector geometry for the three non-NHPN segments",
    ],
}


def _elevation_station_offsets(
    total_geodesic_m: float, interval_m: float
) -> list[float]:
    """Station offsets over one directed segment's geodesic stationing.

    Every whole interval from the from-anchor node, plus the terminal station
    at the segment's locked (millimetre-rounded) geodesic length when it does
    not fall on the grid.
    """
    if total_geodesic_m <= 0 or interval_m <= 0:
        raise ValueError("Station offsets need positive lengths.")
    count = int(math.floor(total_geodesic_m / interval_m))
    offsets = [round(index * interval_m, 3) for index in range(count + 1)]
    terminal = round(total_geodesic_m, 3)
    if offsets[-1] < terminal:
        offsets.append(terminal)
    return offsets


def _segment_station_coordinates(
    elements: Sequence[dict[str, Any]],
    geometries: Sequence[LineString],
    offsets: Sequence[float],
    inverse: Transformer,
) -> list[tuple[float, float]]:
    """EPSG:4326 coordinates of one segment's stations on its directed walk.

    A station's containing element is found on the locked cumulative geodesic
    stationing; its position interpolates planimetrically within that element
    at the station's geodesic fraction. The two axes agree within the recorded
    one percent bound, so the longitudinal placement error within a single
    element is bounded by that ratio times the element length.
    """
    if len(elements) != len(geometries):
        raise ValueError("Element and geometry sequences must align.")
    coordinates: list[tuple[float, float]] = []
    index = 0
    for offset in offsets:
        while (
            index < len(elements) - 1
            and offset > elements[index]["cumulative_geodesic_m"]
        ):
            index += 1
        cumulative_end = elements[index]["cumulative_geodesic_m"]
        length = float(elements[index]["geodesic_length_m"])
        local = offset - (cumulative_end - length)
        fraction = 0.0 if length <= 0 else min(max(local / length, 0.0), 1.0)
        geometry = geometries[index]
        point = geometry.interpolate(fraction * geometry.length)
        coordinates.append(inverse.transform(point.x, point.y))
    return coordinates


def _elevation_station_cell(
    longitude: float, latitude: float, locked_cells: frozenset[str]
) -> str:
    """The locked corridor cell whose tile samples one station."""
    candidates: list[str] = []
    for west in {math.floor(longitude), math.floor(longitude - ELEVATION_CELL_EDGE_EPSILON_DEG),
                 math.floor(longitude + ELEVATION_CELL_EDGE_EPSILON_DEG)}:
        for south in {math.floor(latitude), math.floor(latitude - ELEVATION_CELL_EDGE_EPSILON_DEG),
                      math.floor(latitude + ELEVATION_CELL_EDGE_EPSILON_DEG)}:
            try:
                cell_id = _dem_cell_id((west, south))
            except ValueError:
                continue
            if cell_id in locked_cells:
                candidates.append(cell_id)
    primary = f"n{math.floor(latitude) + 1:02d}w{-math.floor(longitude):03d}"
    if primary in candidates:
        return primary
    if candidates:
        return sorted(set(candidates))[0]
    raise ValueError(
        json.dumps(
            {
                "refusal": "station falls outside the locked corridor cells",
                "longitude": round(longitude, 9),
                "latitude": round(latitude, 9),
            },
            sort_keys=True,
        )
    )


def _elevation_profile_statistics(
    offsets: Sequence[float],
    elevations: Sequence[float],
    interval_m: float,
    window_m: float,
) -> dict[str, Any]:
    """Deterministic profile statistics over one segment's committed stations.

    Operates entirely on the millimetre-rounded station offsets and the
    centimetre-rounded committed elevations, so the cache-independent validator
    recomputes bit-identical figures. Extremes and steepest grades resolve ties
    to the first (lowest-station) occurrence.
    """
    if len(offsets) != len(elevations) or len(offsets) < 2:
        raise ValueError("Profile statistics need at least two matched stations.")
    min_index = 0
    max_index = 0
    climb = 0.0
    descent = 0.0
    steepest: tuple[float, float, float] | None = None
    for index in range(len(elevations)):
        if elevations[index] < elevations[min_index]:
            min_index = index
        if elevations[index] > elevations[max_index]:
            max_index = index
        if index == 0:
            continue
        run = offsets[index] - offsets[index - 1]
        if run <= 0:
            raise ValueError("Station offsets must strictly increase.")
        delta = elevations[index] - elevations[index - 1]
        if delta >= 0:
            climb += delta
        else:
            descent -= delta
        # The terminal leg can be arbitrarily short (a millimetre-rounded
        # segment length modulo the interval), where centimetre-rounded
        # elevations would quantise into a meaningless grade; grades are
        # therefore measured over whole-interval legs only.
        if abs(run - interval_m) > 1e-6:
            continue
        grade = delta / run
        if steepest is None or abs(grade) > steepest[0]:
            steepest = (abs(grade), offsets[index - 1], grade)
    window_steps = int(round(window_m / interval_m))
    sustained: tuple[float, float, float] | None = None
    for start in range(len(elevations) - window_steps):
        run = offsets[start + window_steps] - offsets[start]
        if abs(run - window_m) > 1e-6:
            continue
        grade = (elevations[start + window_steps] - elevations[start]) / run
        if sustained is None or abs(grade) > sustained[0]:
            sustained = (abs(grade), offsets[start], grade)
    return {
        "min_elevation": {
            "elevation_m": elevations[min_index],
            "station_m": offsets[min_index],
        },
        "max_elevation": {
            "elevation_m": elevations[max_index],
            "station_m": offsets[max_index],
        },
        "total_climb_m": round(climb, 2),
        "total_descent_m": round(descent, 2),
        "max_interval_grade": (
            None
            if steepest is None
            else {
                "grade_percent": round(steepest[2] * 100.0, 3),
                "from_station_m": steepest[1],
            }
        ),
        "max_sustained_grade": (
            None
            if sustained is None
            else {
                "grade_percent": round(sustained[2] * 100.0, 3),
                "from_station_m": sustained[1],
                "window_m": window_m,
            }
        ),
    }


def _elevation_path_records(
    directed_paths: Sequence[dict[str, Any]],
    segments_payload: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-ADR-0024-path elevation composition from the per-segment statistics.

    Stationing is per segment and junction gaps are excluded from it, so no
    grade window spans a junction; the composition of per-segment statistics is
    therefore exact, not an approximation.
    """
    segment_by_id = {segment["segment_id"]: segment for segment in segments_payload}
    records: list[dict[str, Any]] = []
    for path in directed_paths:
        highest: dict[str, Any] | None = None
        lowest: dict[str, Any] | None = None
        sustained: dict[str, Any] | None = None
        interval_extreme: dict[str, Any] | None = None
        climb = 0.0
        descent = 0.0
        station_count = 0
        for segment_id in path["locked_segment_ids"]:
            segment = segment_by_id[segment_id]
            statistics = segment["statistics"]
            top = statistics["max_elevation"]
            if highest is None or top["elevation_m"] > highest["elevation_m"]:
                highest = {"segment_id": segment_id, **top}
            bottom = statistics["min_elevation"]
            if lowest is None or bottom["elevation_m"] < lowest["elevation_m"]:
                lowest = {"segment_id": segment_id, **bottom}
            candidate = statistics["max_sustained_grade"]
            if candidate is not None and (
                sustained is None
                or abs(candidate["grade_percent"]) > abs(sustained["grade_percent"])
            ):
                sustained = {"segment_id": segment_id, **candidate}
            interval_candidate = statistics["max_interval_grade"]
            if interval_candidate is not None and (
                interval_extreme is None
                or abs(interval_candidate["grade_percent"])
                > abs(interval_extreme["grade_percent"])
            ):
                interval_extreme = {"segment_id": segment_id, **interval_candidate}
            climb += statistics["total_climb_m"]
            descent += statistics["total_descent_m"]
            station_count += segment["station_count"]
        records.append(
            {
                "path_id": path["path_id"],
                "role": path["role"],
                "locked_segment_ids": list(path["locked_segment_ids"]),
                "total_geodesic_m": path["total_geodesic_m"],
                "total_geodesic_miles": path["total_geodesic_miles"],
                "station_count": station_count,
                "highest_point": highest,
                "lowest_point": lowest,
                "total_climb_m": round(climb, 2),
                "total_descent_m": round(descent, 2),
                "max_sustained_grade": sustained,
                "max_interval_grade": interval_extreme,
            }
        )
    return records


def _elevation_summary(
    segments_payload: Sequence[dict[str, Any]],
    tiles: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Corridor-wide elevation summary across all locked segments."""
    highest: dict[str, Any] | None = None
    lowest: dict[str, Any] | None = None
    sustained: dict[str, Any] | None = None
    station_count = 0
    for segment in segments_payload:
        statistics = segment["statistics"]
        top = statistics["max_elevation"]
        if highest is None or top["elevation_m"] > highest["elevation_m"]:
            highest = {"segment_id": segment["segment_id"], **top}
        bottom = statistics["min_elevation"]
        if lowest is None or bottom["elevation_m"] < lowest["elevation_m"]:
            lowest = {"segment_id": segment["segment_id"], **bottom}
        candidate = statistics["max_sustained_grade"]
        if candidate is not None and (
            sustained is None
            or abs(candidate["grade_percent"]) > abs(sustained["grade_percent"])
        ):
            sustained = {"segment_id": segment["segment_id"], **candidate}
        station_count += segment["station_count"]
    return {
        "segment_count": len(segments_payload),
        "station_count": station_count,
        "tile_count": len(tiles),
        "total_tile_bytes": sum(tile["byte_count"] for tile in tiles),
        "tile_station_count": sum(tile["station_count"] for tile in tiles),
        "highest_point": highest,
        "lowest_point": lowest,
        "max_sustained_grade": sustained,
        "nodata_station_count": 0,
    }


def _check_elevation_raster_facts(raster: dict[str, Any], cell_id: str) -> None:
    """The raster facts every verified tile must state (sample-tile precedent)."""
    west, south, east, north = _dem_cell_bounds(cell_id)
    pixels = raster.get("pixel_degrees", [])
    if (
        raster.get("crs") != f"EPSG:{DEM_EXPECTED_RASTER_EPSG}"
        or raster.get("band_count") != 1
        or raster.get("dtype") != "float32"
        or raster.get("nodata") != DEM_EXPECTED_NODATA
        or len(pixels) != 2
        or any(
            abs(pixel - DEM_PIXEL_DEGREES) / DEM_PIXEL_DEGREES
            > DEM_PIXEL_RELATIVE_TOLERANCE
            for pixel in pixels
        )
    ):
        raise ValueError(
            f"Verified tile for cell '{cell_id}' does not match the locked "
            "product facts."
        )
    bounds = raster.get("bounds", [])
    if len(bounds) != 4 or not (
        bounds[0] <= west + 1e-6
        and bounds[1] <= south + 1e-6
        and bounds[2] >= east - 1e-6
        and bounds[3] >= north - 1e-6
    ):
        raise ValueError(
            f"Verified tile for cell '{cell_id}' does not cover its cell."
        )


def acquire_continental_corridor_elevation(
    dem_lock_path: Path,
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    dem_cache_directory: Path,
    output_path: Path,
    *,
    transport: DemTransport | None = None,
    acquired_at: str | None = None,
    release_tiles: bool = False,
) -> dict[str, Any]:
    """Acquire and verify every locked 3DEP tile and lock the corridor profile.

    Verification per tile: the download URL must be the locked product URL
    inside the catalog allowlist, the byte count must equal the discovery
    declaration, the SHA-256 must equal the product lock's pinned hash where it
    pins one (the three sample tiles) and is recorded as the first-acquisition
    pin otherwise, and the raster must state the locked CRS, cell size, band
    layout, nodata, and cell coverage. Tiles are checkpointed and resumable;
    with ``release_tiles`` each raster is deleted after verification and
    station extraction, so the cache retains hashes and elevations rather than
    51.68 GB of rasters. The directed walk is re-derived and refused unless it
    reproduces the committed directed route lock exactly.
    """
    dem_lock = validate_continental_3dep_products(
        dem_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        overlay_lock_path,
        catalog_path,
    )
    directed_lock = validate_continental_directed_route_lock(
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    catalog = load_catalog(catalog_path)
    source = catalog[DEM_SOURCE_ID]
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    fill_lock = validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    overlay_lock = validate_continental_reconstruction_overlays(
        overlay_lock_path,
        disposition_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        catalog_path,
    )
    conflation_lock = validate_continental_nhs_conflation(
        conflation_lock_path,
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    if transport is None:
        transport = UrllibDemTransport()
    timestamp = acquired_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    cache_root = (
        cache_directory / route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    )
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])
    anchor_limit = float(edge_lock["anchor_snap_limit_m"])
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    edge_by_id = {entry["segment_id"]: entry for entry in edge_lock["segments"]}
    chain_by_id = {
        entry["segment_id"]: entry
        for entry in overlay_lock["chain_connectivity"]["segments"]
    }
    conflation_site_by_id = {
        site["site_id"]: site for site in conflation_lock["sites"]
    }
    fills_by_segment: dict[str, list[dict[str, Any]]] = {}
    for site in fill_lock["sites"]:
        fills_by_segment.setdefault(site["segment_id"], []).append(site)
    overlays_by_segment: dict[str, list[dict[str, Any]]] = {}
    for overlay in overlay_lock["overlays"]:
        overlays_by_segment.setdefault(overlay["segment_id"], []).append(
            {
                "site_id": overlay["site_id"],
                "overlay_id": overlay["overlay_id"],
                "from_coordinate": overlay["boundary"]["from_coordinate"],
                "to_coordinate": overlay["boundary"]["to_coordinate"],
                "separation_m": overlay["boundary"]["length_m"],
                "geometry": overlay["geometry"],
            }
        )
    snapshot_ids = {
        snapshot["segment_id"]
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }
    locked_record_by_id = {
        record["segment_id"]: record for record in directed_lock["segments"]
    }
    locked_cells = frozenset(dem_lock["corridor"]["cells"])

    segment_profiles: list[dict[str, Any]] = []
    stations_by_cell: dict[str, list[tuple[int, int]]] = {}
    for segment in selection["segments"]:
        if segment["id"] not in snapshot_ids:
            continue
        lines = _segment_locked_lines(route_lock, segment["id"], cache_root)
        geometries: list[LineString] = []
        record = _derive_directed_segment(
            segment,
            edge_by_id[segment["id"]],
            chain_by_id.get(segment["id"]),
            lines,
            fills_by_segment.get(segment["id"], []),
            overlays_by_segment.get(segment["id"], []),
            conflation_site_by_id,
            forward.transform(
                transfer_by_id[segment["from"]]["coordinate"]["longitude"],
                transfer_by_id[segment["from"]]["coordinate"]["latitude"],
            ),
            forward.transform(
                transfer_by_id[segment["to"]]["coordinate"]["longitude"],
                transfer_by_id[segment["to"]]["coordinate"]["latitude"],
            ),
            tolerance,
            anchor_limit,
            forward,
            inverse,
            geometry_sink=geometries,
        )
        locked_record = locked_record_by_id[segment["id"]]
        if canonical_sha256(record) != canonical_sha256(locked_record):
            raise ValueError(
                f"Directed walk for '{segment['id']}' does not reproduce the "
                "committed directed route lock; refusing to sample elevation "
                "for a different route."
            )
        offsets = _elevation_station_offsets(
            record["geodesic_length_m"], ELEVATION_STATION_INTERVAL_M
        )
        coordinates = _segment_station_coordinates(
            record["elements"], geometries, offsets, inverse
        )
        segment_index = len(segment_profiles)
        for station_index, (longitude, latitude) in enumerate(coordinates):
            cell_id = _elevation_station_cell(longitude, latitude, locked_cells)
            stations_by_cell.setdefault(cell_id, []).append(
                (segment_index, station_index)
            )
        segment_profiles.append(
            {
                "segment_id": segment["id"],
                "geodesic_length_m": record["geodesic_length_m"],
                "offsets": offsets,
                "coordinates": coordinates,
                "elevations": [None] * len(offsets),
            }
        )

    tiles_root = dem_cache_directory / "tiles"
    elevation_root = dem_cache_directory / "elevation"
    sample_sha_by_cell = {
        sample["cell_id"]: sample["sha256"]
        for sample in dem_lock["sample_verification"]["samples"]
    }
    product_by_cell = {product["cell_id"]: product for product in dem_lock["products"]}
    tiles: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    resumed_tiles = 0
    reused_extractions = 0
    downloaded_bytes = 0
    for cell_id in dem_lock["corridor"]["cells"]:
        product = product_by_cell[cell_id]["product"]
        url = product["download_url"]
        if not any(
            url_matches_prefix(url, prefix) for prefix in source.allowed_url_prefixes
        ):
            raise ValueError(
                f"Locked product URL for cell '{cell_id}' is outside the catalog "
                "allowlist."
            )
        filename = url.rsplit("/", 1)[-1]
        destination = tiles_root / filename
        checkpoint_path = tiles_root / f"{filename}.json"
        request_sha256 = canonical_sha256({"url": url})
        record = _dem_checkpoint_reuse(checkpoint_path, request_sha256)
        cell_stations = sorted(stations_by_cell.get(cell_id, []))
        station_points = [
            [
                round(segment_profiles[segment_index]["coordinates"][station_index][0], 9),
                round(segment_profiles[segment_index]["coordinates"][station_index][1], 9),
            ]
            for segment_index, station_index in cell_stations
        ]

        extraction_scope = {
            "cell_id": cell_id,
            "url": url,
            "stations": station_points,
            "sampler": ELEVATION_SAMPLER_MODEL,
        }
        extraction_path = elevation_root / f"{cell_id}.json"
        tile_on_disk = destination.is_file()
        if (
            record is not None
            and tile_on_disk
            and compute_sha256(destination) == record["sha256"]
        ):
            resumed_tiles += 1
        elif (
            record is not None
            and not tile_on_disk
            and isinstance(record.get("raster"), dict)
            and _dem_checkpoint_reuse(
                extraction_path,
                canonical_sha256(
                    {**extraction_scope, "tile_sha256": record["sha256"]}
                ),
            )
            is not None
        ):
            # The tile was verified, sampled, and released; the checkpoint
            # carries its hash, raster facts, and extraction evidence.
            resumed_tiles += 1
        else:
            fetched = transport.fetch(url, destination)
            if fetched.status != 200:
                raise ValueError(
                    f"3DEP tile download failed for cell '{cell_id}' with status "
                    f"{fetched.status}."
                )
            record = {
                "request_sha256": request_sha256,
                "url": url,
                "sha256": fetched.sha256,
                "byte_count": fetched.byte_count,
                "response": {
                    "status": fetched.status,
                    "content_type": fetched.content_type,
                    "etag": fetched.etag,
                    "last_modified": fetched.last_modified,
                },
                "acquired_at": timestamp,
            }
            downloaded_bytes += fetched.byte_count
            tile_on_disk = True
        if "acquired_at" not in record:
            # A checkpoint written by the product-lock sample stage predates
            # this field; pin the first acquisition timestamp this stage saw.
            record["acquired_at"] = timestamp
        size_exception = None
        if record["byte_count"] != product["size_bytes"]:
            size_exception = ELEVATION_DECLARED_SIZE_EXCEPTIONS.get(cell_id)
            if (
                size_exception is None
                or product["size_bytes"] != size_exception["declared_size_bytes"]
                or record["byte_count"] != size_exception["measured_byte_count"]
                or record["sha256"] != size_exception["sha256"]
            ):
                raise ValueError(
                    f"3DEP tile for cell '{cell_id}' carries "
                    f"{record['byte_count']} bytes where discovery declared "
                    f"{product['size_bytes']}, and no characterised declaration "
                    "exception pins this exact artifact."
                )
        locked_sample_sha256 = sample_sha_by_cell.get(cell_id)
        if (
            locked_sample_sha256 is not None
            and record["sha256"] != locked_sample_sha256
        ):
            raise ValueError(
                f"3DEP tile for cell '{cell_id}' hash {record['sha256']} does not "
                "match the product lock's pinned sample hash."
            )
        if tile_on_disk:
            record["raster"] = _inspect_dem_raster(destination, cell_id)
        raster = record["raster"]
        _check_elevation_raster_facts(raster, cell_id)
        _write_dem_checkpoint(checkpoint_path, record)

        extraction_request = canonical_sha256(
            {**extraction_scope, "tile_sha256": record["sha256"]}
        )
        extraction = _dem_checkpoint_reuse(extraction_path, extraction_request)
        if extraction is None:
            # Imported here like rasterio in _inspect_dem_raster: raster tooling
            # loads only when a tile actually needs sampling.
            from cannonball_map.elevation import ElevationMetadata, ElevationSampler

            metadata = ElevationMetadata(
                product_id=product["source_id"],
                product_title=product["title"],
                product_resolution=DEM_EXPECTED_RESOLUTION,
                raster_crs=f"EPSG:{DEM_EXPECTED_RASTER_EPSG}",
                horizontal_datum=DEM_EXPECTED_HORIZONTAL_DATUM,
                vertical_datum=DEM_EXPECTED_VERTICAL_DATUM,
                elevation_units=DEM_EXPECTED_ELEVATION_UNITS,
                artifact_sha256=record["sha256"],
            )
            values: list[float | None] = []
            with ElevationSampler(destination, metadata, "EPSG:4326") as sampler:
                for point in station_points:
                    try:
                        values.append(
                            round(
                                sampler.sample(point[0], point[1]),
                                ELEVATION_VALUE_DECIMALS,
                            )
                        )
                    except ValueError as error:
                        values.append(None)
                        anomalies.append(
                            {
                                "cell_id": cell_id,
                                "longitude": point[0],
                                "latitude": point[1],
                                "error": str(error),
                            }
                        )
            extraction = {
                "request_sha256": extraction_request,
                "cell_id": cell_id,
                "tile_sha256": record["sha256"],
                "station_count": len(values),
                "elevations_m": values,
            }
            _write_dem_checkpoint(extraction_path, extraction)
        else:
            reused_extractions += 1
        for (segment_index, station_index), value in zip(
            cell_stations, extraction["elevations_m"], strict=True
        ):
            segment_profiles[segment_index]["elevations"][station_index] = value
        if release_tiles and destination.is_file():
            destination.unlink()
        tile_record = {
            "cell_id": cell_id,
            "url": url,
            "publication_date": product["publication_date"],
            "sha256": record["sha256"],
            "byte_count": record["byte_count"],
            "acquired_at": record["acquired_at"],
            "response": record["response"],
            "raster": raster,
            "station_count": len(cell_stations),
            "sha256_pinned_by_product_lock": locked_sample_sha256 is not None,
        }
        if size_exception is not None:
            tile_record["declared_size_exception"] = dict(size_exception)
        tiles.append(tile_record)

    if anomalies:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "elevation stations intersect nodata or fall "
                    "outside their raster",
                    "anomaly_count": len(anomalies),
                    "first_anomalies": anomalies[:20],
                },
                sort_keys=True,
            )
        )

    segments_payload: list[dict[str, Any]] = []
    for profile in segment_profiles:
        elevations = profile["elevations"]
        if any(value is None for value in elevations):
            raise AssertionError("Unextracted station survived the tile loop.")
        statistics = _elevation_profile_statistics(
            profile["offsets"],
            elevations,
            ELEVATION_STATION_INTERVAL_M,
            ELEVATION_SUSTAINED_WINDOW_M,
        )
        segments_payload.append(
            {
                "segment_id": profile["segment_id"],
                "geodesic_length_m": profile["geodesic_length_m"],
                "station_interval_m": ELEVATION_STATION_INTERVAL_M,
                "station_count": len(elevations),
                "terminal_station_m": profile["offsets"][-1],
                "elevations_m": elevations,
                "statistics": statistics,
            }
        )
    paths_payload = _elevation_path_records(directed_lock["paths"], segments_payload)
    summary = _elevation_summary(segments_payload, tiles)

    payload = {
        "schema_version": 1,
        "status": CORRIDOR_ELEVATION_STATUS,
        "decision": "ADR-0007",
        "route_decision": selection["decision"],
        "carriageway_decision": "ADR-0014",
        "acquired_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "dem_product_lock_sha256": compute_sha256(dem_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
        "source": dict(dem_lock["source"]),
        "product_family": dict(dem_lock["product_family"]),
        "model": {
            "station_interval_m": ELEVATION_STATION_INTERVAL_M,
            "sustained_grade_window_m": ELEVATION_SUSTAINED_WINDOW_M,
            "elevation_decimals": ELEVATION_VALUE_DECIMALS,
            "sampler": dict(ELEVATION_SAMPLER_MODEL),
            "stationing_note": (
                "Stations lie on each directed segment's geodesic stationing - "
                "every interval from the from-anchor node plus the terminal "
                "station; positions interpolate planimetrically within the "
                "containing element at the station's geodesic fraction, and "
                "junction gaps carry no stations."
            ),
            "smoothing_note": (
                "No smoothing or conditioning is applied: this is the raw "
                "1/3 arc-second baseline profile at the stated stations. "
                "ADR-0017 grade smoothing remains a package-build policy, and "
                "single-interval grade extremes can reflect structures the "
                "surface model captured rather than road surface (2026-08-16 "
                "survey-departure decomposition)."
            ),
            "grade_note": (
                "Grades are station-to-station differences of the committed "
                "elevations over the geodesic station axis, measured on "
                "whole-interval legs and windows only: the terminal leg can be "
                "arbitrarily short, where centimetre-rounded elevations "
                "quantise into meaningless grades."
            ),
        },
        "source_policy": dict(CORRIDOR_ELEVATION_SOURCE_POLICY),
        "tile_retention": (
            "released_after_verification" if release_tiles else "cached"
        ),
        "resumed_tile_count": resumed_tiles,
        "reused_extraction_count": reused_extractions,
        "downloaded_byte_count": downloaded_bytes,
        "tile_count": len(tiles),
        "tiles": tiles,
        "tiles_sha256": canonical_sha256(tiles),
        "segment_count": len(segments_payload),
        "segments": segments_payload,
        "profile_sha256": canonical_sha256(segments_payload),
        "paths": paths_payload,
        "paths_sha256": canonical_sha256(paths_payload),
        "summary": summary,
        "next_stage": CORRIDOR_ELEVATION_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_corridor_elevation(
    elevation_lock_path: Path,
    dem_lock_path: Path,
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the corridor elevation lock without caches, rasters, or network.

    Everything recomputable from committed artifacts is recomputed: every tile
    against the product lock's declarations (URL, byte count, pinned sample
    hashes, raster facts), every station count against the directed lock's
    stationing, every statistic from the committed elevations through the same
    helpers the acquisition used, and the path and summary compositions. The
    model constants are held to the module's values so a widened interval or
    window cannot validate itself.
    """
    payload = load_json(elevation_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Corridor elevation lock schema_version must be 1.")
    if payload.get("status") != CORRIDOR_ELEVATION_STATUS:
        raise ValueError("Corridor elevation lock has an unsupported status.")
    if payload.get("decision") != "ADR-0007":
        raise ValueError("Corridor elevation lock does not cite ADR-0007.")
    dem_lock = validate_continental_3dep_products(
        dem_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        overlay_lock_path,
        catalog_path,
    )
    directed_lock = validate_continental_directed_route_lock(
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    selection = load_json(selection_path)
    if payload.get("route_decision") != selection.get("decision"):
        raise ValueError(
            "Corridor elevation lock decision does not match the selection."
        )
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "dem_product_lock_sha256": compute_sha256(dem_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Corridor elevation lock input hash drifted.")
    if payload.get("source") != dem_lock["source"]:
        raise ValueError("Corridor elevation lock source drifted from the product lock.")
    if payload.get("product_family") != dem_lock["product_family"]:
        raise ValueError(
            "Corridor elevation lock product family drifted from the product lock."
        )
    model = payload.get("model", {})
    if (
        model.get("station_interval_m") != ELEVATION_STATION_INTERVAL_M
        or model.get("sustained_grade_window_m") != ELEVATION_SUSTAINED_WINDOW_M
        or model.get("elevation_decimals") != ELEVATION_VALUE_DECIMALS
        or model.get("sampler") != ELEVATION_SAMPLER_MODEL
    ):
        raise ValueError("Corridor elevation lock model constants drifted.")
    if payload.get("source_policy") != CORRIDOR_ELEVATION_SOURCE_POLICY:
        raise ValueError("Corridor elevation lock source policy drifted.")
    if payload.get("tile_retention") not in ("cached", "released_after_verification"):
        raise ValueError("Corridor elevation lock tile retention is unstated.")

    tiles = payload.get("tiles", [])
    cells = dem_lock["corridor"]["cells"]
    if payload.get("tile_count") != len(tiles) or [
        tile.get("cell_id") for tile in tiles
    ] != cells:
        raise ValueError(
            "Corridor elevation lock does not verify exactly the locked corridor "
            "cells in order."
        )
    sample_sha_by_cell = {
        sample["cell_id"]: sample["sha256"]
        for sample in dem_lock["sample_verification"]["samples"]
    }
    product_by_cell = {product["cell_id"]: product for product in dem_lock["products"]}
    for tile in tiles:
        cell_id = tile["cell_id"]
        product = product_by_cell[cell_id]["product"]
        if tile.get("url") != product["download_url"]:
            raise ValueError(
                f"Verified tile for cell '{cell_id}' is not the locked URL."
            )
        if tile.get("publication_date") != product["publication_date"]:
            raise ValueError(
                f"Verified tile for cell '{cell_id}' publication date drifted."
            )
        size_exception = ELEVATION_DECLARED_SIZE_EXCEPTIONS.get(cell_id)
        if tile.get("byte_count") != product["size_bytes"]:
            if (
                size_exception is None
                or tile.get("declared_size_exception") != size_exception
                or product["size_bytes"] != size_exception["declared_size_bytes"]
                or tile.get("byte_count") != size_exception["measured_byte_count"]
                or tile.get("sha256") != size_exception["sha256"]
            ):
                raise ValueError(
                    f"Verified tile for cell '{cell_id}' byte count does not "
                    "match discovery and no characterised declaration exception "
                    "pins it."
                )
        elif tile.get("declared_size_exception") is not None:
            raise ValueError(
                f"Verified tile for cell '{cell_id}' claims a declaration "
                "exception it does not need."
            )
        if not SHA256_PATTERN.fullmatch(str(tile.get("sha256", ""))):
            raise ValueError(
                f"Verified tile for cell '{cell_id}' has an invalid checksum."
            )
        pinned = sample_sha_by_cell.get(cell_id)
        if tile.get("sha256_pinned_by_product_lock") != (pinned is not None):
            raise ValueError(
                f"Verified tile for cell '{cell_id}' misstates its sample pin."
            )
        if pinned is not None and tile["sha256"] != pinned:
            raise ValueError(
                f"Verified tile for cell '{cell_id}' does not match the product "
                "lock's pinned sample hash."
            )
        response = tile.get("response", {})
        if response.get("status") != 200 or not response.get("content_type"):
            raise ValueError(
                f"Verified tile for cell '{cell_id}' has incomplete response "
                "metadata."
            )
        if not tile.get("acquired_at"):
            raise ValueError(
                f"Verified tile for cell '{cell_id}' has no acquisition timestamp."
            )
        _check_elevation_raster_facts(tile.get("raster", {}), cell_id)
        if not isinstance(tile.get("station_count"), int) or tile["station_count"] < 0:
            raise ValueError(
                f"Verified tile for cell '{cell_id}' has an invalid station count."
            )
    if payload.get("tiles_sha256") != canonical_sha256(tiles):
        raise ValueError("Corridor elevation lock tile digest drifted.")

    segments = payload.get("segments", [])
    directed_segments = directed_lock["segments"]
    if payload.get("segment_count") != len(segments) or [
        segment.get("segment_id") for segment in segments
    ] != [record["segment_id"] for record in directed_segments]:
        raise ValueError(
            "Corridor elevation lock does not cover exactly the directed "
            "segments in order."
        )
    total_stations = 0
    for segment, record in zip(segments, directed_segments, strict=True):
        segment_id = segment["segment_id"]
        if segment.get("geodesic_length_m") != record["geodesic_length_m"]:
            raise ValueError(
                f"Elevation segment '{segment_id}' geodesic length drifted from "
                "the directed lock."
            )
        if segment.get("station_interval_m") != ELEVATION_STATION_INTERVAL_M:
            raise ValueError(
                f"Elevation segment '{segment_id}' station interval drifted."
            )
        offsets = _elevation_station_offsets(
            record["geodesic_length_m"], ELEVATION_STATION_INTERVAL_M
        )
        elevations = segment.get("elevations_m", [])
        if (
            segment.get("station_count") != len(offsets)
            or len(elevations) != len(offsets)
            or segment.get("terminal_station_m") != offsets[-1]
        ):
            raise ValueError(
                f"Elevation segment '{segment_id}' stationing does not reproduce "
                "the directed lock's geodesic length under the locked interval."
            )
        for value in elevations:
            if (
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or value != value
                or round(float(value), ELEVATION_VALUE_DECIMALS) != value
            ):
                raise ValueError(
                    f"Elevation segment '{segment_id}' carries a non-finite or "
                    "unrounded elevation."
                )
        expected_statistics = _elevation_profile_statistics(
            offsets,
            elevations,
            ELEVATION_STATION_INTERVAL_M,
            ELEVATION_SUSTAINED_WINDOW_M,
        )
        if segment.get("statistics") != expected_statistics:
            raise ValueError(
                f"Elevation segment '{segment_id}' statistics do not reproduce "
                "from its committed stations."
            )
        total_stations += len(offsets)
    if payload.get("profile_sha256") != canonical_sha256(segments):
        raise ValueError("Corridor elevation lock profile digest drifted.")
    if sum(tile["station_count"] for tile in tiles) != total_stations:
        raise ValueError(
            "Corridor elevation lock tile station counts do not cover every "
            "station exactly once."
        )

    expected_paths = _elevation_path_records(directed_lock["paths"], segments)
    if payload.get("paths") != expected_paths:
        raise ValueError(
            "Corridor elevation lock paths do not reproduce from the committed "
            "segments."
        )
    if payload.get("paths_sha256") != canonical_sha256(expected_paths):
        raise ValueError("Corridor elevation lock path digest drifted.")
    expected_summary = _elevation_summary(segments, tiles)
    if payload.get("summary") != expected_summary:
        raise ValueError(
            "Corridor elevation lock summary does not reproduce from the "
            "committed sections."
        )
    if payload.get("next_stage") != CORRIDOR_ELEVATION_NEXT_STAGE:
        raise ValueError("Corridor elevation lock next stage drifted.")
    return payload


CONDITIONED_PROFILE_STATUS = "vertical_profile_conditioned_carriageway_pending"

# ADR-0017 vertical conditioning bounds, grounded in the 2026-08-31 corridor
# elevation audit's characterised artifact classes and in interstate design
# practice. Sustained design grades on the US interstate system top out near
# six percent, with mountainous-terrain exceptions to about seven (AASHTO
# maximum grades; the corridor's steepest signed real grades - I-70's western
# approaches - are posted at six to seven percent). Seven percent over the
# locked 1 km sustained window is therefore the physical plausibility bound:
# anything a conditioning chord cannot bring under it is a refusal, never a
# silent smooth. The single-interval trigger is looser: real pavement cannot
# exceed the sustained design envelope by much over a whole 100 m leg
# (vertical curves round the grade breaks), but bilinear 1/3 arc-second
# samples on legitimate steep road carry per-leg sampling noise of a couple
# percent; twelve percent - the design envelope plus double that noise - marks
# only unambiguous artifacts. Measured on the committed profile, every 100 m
# interval beyond twelve percent belongs to a characterised artifact class,
# and conditioning exactly those windows brings every 1 km sustained window on
# all twelve segments under the seven percent bound. Between seven and twelve
# percent per interval is recorded measurement noise for the package-build
# grade policy, not this stage's artifact correction.
CONDITIONING_INTERVAL_TRIGGER_PERCENT = 12.0
CONDITIONING_SUSTAINED_BOUND_PERCENT = 7.0
# Bilinear samples of a hydro-flattened water surface repeat the identical
# centimetre value station after station; real pavement on a 10 m surface
# model never does (the corridor-wide census finds no run of four identical
# values anywhere except the characterised water crossings). Four stations
# (>= 300 m of exactly zero grade) therefore seed a water-surface window even
# when the approach grades stay under the interval trigger (the Newark tidal
# viaducts descend at ~8.5 percent per leg).
CONDITIONING_FLAT_RUN_MIN_STATIONS = 4
# Neighbouring detections within one sustained window merge into a single
# artifact window rather than fragmenting one structure into many records.
CONDITIONING_JOIN_DISTANCE_M = 1000.0
CONDITIONING_METHOD = "linear_chord"
# Window shape classification: interior departure from the boundary chord
# must clear both an absolute floor and dominance over the opposite side
# before a window reads as a ridge or a dip rather than a mixed spike.
CONDITIONING_SHAPE_MIN_M = 5.0
CONDITIONING_SHAPE_DOMINANCE_RATIO = 2.0
# A bore-consistent tunnel chord must look like a real tunnel: interstate
# bores hold gentle sustained grades (the Eisenhower-Johnson bore runs about
# 1.6 percent), and the conditioned window must sit at bore scale with its
# boundary stations near the authored portal elevations (the 100 m station
# grid and the surface-vs-portal difference bound the agreement).
CONDITIONING_TUNNEL_GRADE_BOUND_PERCENT = 3.0
CONDITIONING_TUNNEL_PORTAL_TOLERANCE_M = 60.0
CONDITIONING_TUNNEL_LENGTH_RATIO_RANGE = (0.5, 2.0)
# Chord-overlap evidence: a conditioning window whose stations lie within
# two station intervals of a locked fill or overlay chord span samples the
# terrain the chord bridges, and the record cites the span.
CONDITIONING_CHORD_EVIDENCE_MARGIN_M = 200.0

CONDITIONING_ARTIFACT_CLASSES = (
    "tunnel_bore",
    "water_surface",
    "fill_span_terrain",
    "terrain_ridge",
    "bridge_deck_dip",
    "interval_spike",
)

# ADR-0017 authored route context: deterministic authored overlay values with
# recursive provenance and reviewer-visible source notes. The registry names
# the corridor's one characterised bore whose overburden the surface model
# samples. Authored, not observed; the conditioning window itself is detected
# from the committed profile and only classified against this registry.
AUTHORED_TUNNEL_REGISTRY = (
    {
        "tunnel_id": "eisenhower-johnson-memorial-tunnel",
        "segment_id": "i70-denver-to-cove-fort",
        "search_station_range_m": [84000.0, 94000.0],
        "portal_elevation_m": {"east": 3356.8, "west": 3401.0},
        "bore_length_m": 2720.0,
        "provenance": "authored",
        "source_notes": (
            "Colorado DOT Eisenhower-Johnson Memorial Tunnel public facility "
            "facts: east portal 11,013 ft (3,356.8 m), west portal 11,158 ft "
            "(3,401.0 m) - the highest point on the Interstate system - and a "
            "bore of about 1.69 mi (2,720 m). The 2026-08-31 corridor "
            "elevation audit characterised the surface model's 3,837.26 m "
            "ridge above this bore as the corridor's largest artifact."
        ),
        "evidence": "docs/audits/p0-021/2026-08-31-corridor-elevation.md",
    },
)

CONDITIONED_PROFILE_SOURCE_POLICY = {
    "elevation_source": DEM_SOURCE_ID,
    "baseline_decision": "ADR-0007",
    "conditioning_decision": "ADR-0017",
    "artifact_conditioning_applied": True,
    "silent_smoothing_applied": False,
    "package_build_grade_policy": (
        "ADR-0017 grade smoothing over sub-artifact raster noise remains a "
        "package-build policy; this stage removes only the characterised "
        "artifact classes as bounded, evidence-linked records"
    ),
    "continental_downloads_committed": False,
    "authoritative_distance_claimed": False,
}

CONDITIONED_PROFILE_NEXT_STAGE = {
    "id": "westbound-carriageway",
    "requires": [
        "reciprocal directed westbound carriageway model under ADR-0014 over "
        "the locked directed sequence",
        "ADR-0018 geometry gates, including the deferred overlay-site gates "
        "and the recorded Quad Cities 77.2 degree corner constraint",
    ],
}


def _directed_chord_spans(directed_segment: dict[str, Any]) -> list[dict[str, Any]]:
    """Station spans of a directed segment's fill and overlay chord elements.

    Spans lie on the same geodesic station axis the elevation profile uses,
    so a conditioning window's overlap with a chord span is exact evidence
    that the window samples terrain a locked chord bridges.
    """
    spans: list[dict[str, Any]] = []
    for element in directed_segment["elements"]:
        if element["kind"] not in ("nhs_fill_chord", "authored_overlay_chord"):
            continue
        end = float(element["cumulative_geodesic_m"])
        spans.append(
            {
                "kind": element["kind"],
                "site_id": element.get("site_id"),
                "from_station_m": round(end - float(element["geodesic_length_m"]), 3),
                "to_station_m": round(end, 3),
            }
        )
    return spans


def _conditioning_seed_windows(
    offsets: Sequence[float], elevations: Sequence[float]
) -> list[tuple[int, int, str]]:
    """Detection seeds: interval-grade excursions and water flat runs."""
    seeds: list[tuple[int, int, str]] = []
    count = len(elevations)
    for index in range(count - 1):
        run = offsets[index + 1] - offsets[index]
        # Terminal short legs quantise centimetre elevations into meaningless
        # grades and are excluded exactly as the raw profile statistics do.
        if abs(run - ELEVATION_STATION_INTERVAL_M) > 1e-6:
            continue
        grade = abs(elevations[index + 1] - elevations[index]) / run * 100.0
        if grade > CONDITIONING_INTERVAL_TRIGGER_PERCENT:
            seeds.append((index, index + 1, "interval_grade_trigger"))
    run_length = 1
    for index in range(1, count + 1):
        if index < count and elevations[index] == elevations[index - 1]:
            run_length += 1
            continue
        if run_length >= CONDITIONING_FLAT_RUN_MIN_STATIONS:
            seeds.append((index - run_length, index - 1, "water_flat_run"))
        run_length = 1
    seeds.sort(key=lambda seed: (seed[0], seed[1]))
    return seeds


def _expand_conditioning_window(
    offsets: Sequence[float],
    elevations: Sequence[float],
    start: int,
    end: int,
    segment_id: str,
) -> tuple[int, int]:
    """Grow a window until its boundary chord is physically plausible.

    A boundary may not touch a flat pair (a chord anchored on a hydro-flat
    water value would replace water with water), so flat runs adjacent to a
    boundary are absorbed whole and stepped past; then the window grows one
    station at a time on the side that most improves the chord grade until
    the chord sits under the sustained bound. Ties grow the upstream side,
    deterministically.
    """
    count = len(elevations)
    while True:
        while start > 0 and (
            elevations[start - 1] == elevations[start]
            or elevations[start] == elevations[start + 1]
        ):
            start -= 1
        while end < count - 1 and (
            elevations[end + 1] == elevations[end]
            or elevations[end] == elevations[end - 1]
        ):
            end += 1
        run = offsets[end] - offsets[start]
        chord = (elevations[end] - elevations[start]) / run * 100.0
        if abs(chord) <= CONDITIONING_SUSTAINED_BOUND_PERCENT:
            return start, end
        if start > 0 and end < count - 1:
            upstream = (
                (elevations[end] - elevations[start - 1])
                / (offsets[end] - offsets[start - 1])
                * 100.0
            )
            downstream = (
                (elevations[end + 1] - elevations[start])
                / (offsets[end + 1] - offsets[start])
                * 100.0
            )
            if abs(upstream) <= abs(downstream):
                start -= 1
            else:
                end += 1
        elif start > 0:
            start -= 1
        elif end < count - 1:
            end += 1
        else:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "conditioning window cannot reach a "
                        "plausible boundary chord",
                        "segment_id": segment_id,
                        "chord_grade_percent": round(chord, 3),
                        "bound_percent": CONDITIONING_SUSTAINED_BOUND_PERCENT,
                    },
                    sort_keys=True,
                )
            )


def _conditioning_windows(
    offsets: Sequence[float], elevations: Sequence[float], segment_id: str
) -> list[tuple[int, int, list[str]]]:
    """Final artifact windows: seeds merged, expanded, and re-merged."""
    seeds = _conditioning_seed_windows(offsets, elevations)
    join_steps = int(round(CONDITIONING_JOIN_DISTANCE_M / ELEVATION_STATION_INTERVAL_M))
    merged: list[list[Any]] = []
    for start, end, detection in seeds:
        if merged and start - merged[-1][1] <= join_steps:
            merged[-1][1] = max(merged[-1][1], end)
            if detection not in merged[-1][2]:
                merged[-1][2].append(detection)
        else:
            merged.append([start, end, [detection]])
    windows: list[list[Any]] = []
    for start, end, detections in merged:
        start, end = _expand_conditioning_window(
            offsets, elevations, start, end, segment_id
        )
        if windows and start <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], end)
            for detection in detections:
                if detection not in windows[-1][2]:
                    windows[-1][2].append(detection)
        else:
            windows.append([start, end, detections])
    for window in windows:
        window[0], window[1] = _expand_conditioning_window(
            offsets, elevations, window[0], window[1], segment_id
        )
    return [(window[0], window[1], window[2]) for window in windows]


def _conditioning_record(
    segment_id: str,
    record_index: int,
    offsets: Sequence[float],
    elevations: Sequence[float],
    start: int,
    end: int,
    detections: list[str],
    chord_spans: Sequence[dict[str, Any]],
    tunnel_registry: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """One bounded, evidence-linked conditioning record with its replacement."""
    run = offsets[end] - offsets[start]
    chord_grade = (elevations[end] - elevations[start]) / run * 100.0
    above = 0.0
    below = 0.0
    flat_best = 1
    flat_current = 1
    max_interval_grade = 0.0
    for index in range(start, end + 1):
        chord_value = elevations[start] + (
            elevations[end] - elevations[start]
        ) * (offsets[index] - offsets[start]) / run
        above = max(above, elevations[index] - chord_value)
        below = max(below, chord_value - elevations[index])
        if index > start:
            if elevations[index] == elevations[index - 1]:
                flat_current += 1
                flat_best = max(flat_best, flat_current)
            else:
                flat_current = 1
            leg = offsets[index] - offsets[index - 1]
            if abs(leg - ELEVATION_STATION_INTERVAL_M) <= 1e-6:
                max_interval_grade = max(
                    max_interval_grade,
                    abs(elevations[index] - elevations[index - 1]) / leg * 100.0,
                )
    overlaps = [
        span
        for span in chord_spans
        if span["from_station_m"] - CONDITIONING_CHORD_EVIDENCE_MARGIN_M
        <= offsets[end]
        and offsets[start]
        <= span["to_station_m"] + CONDITIONING_CHORD_EVIDENCE_MARGIN_M
    ]
    tunnel = None
    for entry in tunnel_registry:
        if entry["segment_id"] != segment_id:
            continue
        search_from, search_to = entry["search_station_range_m"]
        if offsets[start] <= search_to and search_from <= offsets[end]:
            tunnel = entry
            break
    if flat_best >= CONDITIONING_FLAT_RUN_MIN_STATIONS:
        artifact_class = "water_surface"
    elif tunnel is not None and above >= below:
        artifact_class = "tunnel_bore"
    elif overlaps:
        artifact_class = "fill_span_terrain"
    elif (
        above > CONDITIONING_SHAPE_DOMINANCE_RATIO * below
        and above > CONDITIONING_SHAPE_MIN_M
    ):
        artifact_class = "terrain_ridge"
    elif (
        below > CONDITIONING_SHAPE_DOMINANCE_RATIO * above
        and below > CONDITIONING_SHAPE_MIN_M
    ):
        artifact_class = "bridge_deck_dip"
    else:
        artifact_class = "interval_spike"
    evidence: dict[str, Any] = {
        "detections": list(detections),
        "characterisation": "docs/audits/p0-021/2026-08-31-corridor-elevation.md",
    }
    if overlaps:
        evidence["chord_span_overlaps"] = overlaps
    if artifact_class == "tunnel_bore":
        portal_east = tunnel["portal_elevation_m"]["east"]
        portal_west = tunnel["portal_elevation_m"]["west"]
        # Westbound travel enters at the east portal and exits at the west.
        entry_delta = round(elevations[start] - portal_east, 2)
        exit_delta = round(elevations[end] - portal_west, 2)
        length_ratio = run / tunnel["bore_length_m"]
        low, high = CONDITIONING_TUNNEL_LENGTH_RATIO_RANGE
        if (
            abs(chord_grade) > CONDITIONING_TUNNEL_GRADE_BOUND_PERCENT
            or abs(entry_delta) > CONDITIONING_TUNNEL_PORTAL_TOLERANCE_M
            or abs(exit_delta) > CONDITIONING_TUNNEL_PORTAL_TOLERANCE_M
            or not low <= length_ratio <= high
        ):
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "conditioning window does not agree with "
                        "its authored tunnel",
                        "segment_id": segment_id,
                        "tunnel_id": tunnel["tunnel_id"],
                        "chord_grade_percent": round(chord_grade, 3),
                        "entry_portal_delta_m": entry_delta,
                        "exit_portal_delta_m": exit_delta,
                        "window_to_bore_ratio": round(length_ratio, 3),
                    },
                    sort_keys=True,
                )
            )
        evidence["authored_tunnel"] = {
            "tunnel_id": tunnel["tunnel_id"],
            "entry_portal_delta_m": entry_delta,
            "exit_portal_delta_m": exit_delta,
            "window_to_bore_length_ratio": round(length_ratio, 3),
            "source_notes": tunnel["source_notes"],
            "provenance": tunnel["provenance"],
        }
    replacement = [
        round(
            elevations[start]
            + (elevations[end] - elevations[start])
            * (offsets[index] - offsets[start])
            / run,
            ELEVATION_VALUE_DECIMALS,
        )
        for index in range(start + 1, end)
    ]
    return {
        "record_id": f"{segment_id}--conditioning-{record_index:03d}",
        "artifact_class": artifact_class,
        "method": CONDITIONING_METHOD,
        "from_station_m": offsets[start],
        "to_station_m": offsets[end],
        "interior_station_count": end - start - 1,
        "before": {
            "max_interval_grade_percent": round(max_interval_grade, 3),
            "max_above_chord_m": round(above, 2),
            "max_below_chord_m": round(below, 2),
            "longest_flat_run_stations": flat_best,
            "raw_sha256": canonical_sha256(list(elevations[start : end + 1])),
        },
        "after": {
            "chord_grade_percent": round(chord_grade, 3),
            "replacement_elevations_m": replacement,
        },
        "evidence": evidence,
    }


def _condition_segment_profile(
    segment_id: str,
    offsets: Sequence[float],
    elevations: Sequence[float],
    chord_spans: Sequence[dict[str, Any]],
    tunnel_registry: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[float]]:
    """All conditioning records for one segment plus its conditioned profile."""
    windows = _conditioning_windows(offsets, elevations, segment_id)
    records: list[dict[str, Any]] = []
    conditioned = list(elevations)
    for index, (start, end, detections) in enumerate(windows):
        record = _conditioning_record(
            segment_id,
            index,
            offsets,
            elevations,
            start,
            end,
            detections,
            chord_spans,
            tunnel_registry,
        )
        records.append(record)
        conditioned[start + 1 : end] = record["after"]["replacement_elevations_m"]
    return records, conditioned


def _conditioned_summary(
    segments_payload: Sequence[dict[str, Any]],
    raw_summary: dict[str, Any],
) -> dict[str, Any]:
    """Corridor-wide conditioning summary: corrections by class plus the
    post-conditioning extremes, next to the raw baseline they replace."""
    by_class: dict[str, dict[str, Any]] = {}
    record_count = 0
    corrected_stations = 0
    corrected_length = 0.0
    for segment in segments_payload:
        for record in segment["conditioning_records"]:
            entry = by_class.setdefault(
                record["artifact_class"],
                {
                    "record_count": 0,
                    "corrected_station_count": 0,
                    "corrected_length_m": 0.0,
                },
            )
            entry["record_count"] += 1
            entry["corrected_station_count"] += record["interior_station_count"]
            entry["corrected_length_m"] += (
                record["to_station_m"] - record["from_station_m"]
            )
            record_count += 1
            corrected_stations += record["interior_station_count"]
            corrected_length += record["to_station_m"] - record["from_station_m"]
    for entry in by_class.values():
        entry["corrected_length_m"] = round(entry["corrected_length_m"], 3)
    highest: dict[str, Any] | None = None
    lowest: dict[str, Any] | None = None
    sustained: dict[str, Any] | None = None
    interval: dict[str, Any] | None = None
    station_count = 0
    for segment in segments_payload:
        statistics = segment["statistics"]
        top = statistics["max_elevation"]
        if highest is None or top["elevation_m"] > highest["elevation_m"]:
            highest = {"segment_id": segment["segment_id"], **top}
        bottom = statistics["min_elevation"]
        if lowest is None or bottom["elevation_m"] < lowest["elevation_m"]:
            lowest = {"segment_id": segment["segment_id"], **bottom}
        candidate = statistics["max_sustained_grade"]
        if candidate is not None and (
            sustained is None
            or abs(candidate["grade_percent"]) > abs(sustained["grade_percent"])
        ):
            sustained = {"segment_id": segment["segment_id"], **candidate}
        leg = statistics["max_interval_grade"]
        if leg is not None and (
            interval is None
            or abs(leg["grade_percent"]) > abs(interval["grade_percent"])
        ):
            interval = {"segment_id": segment["segment_id"], **leg}
        station_count += segment["station_count"]
    return {
        "segment_count": len(segments_payload),
        "station_count": station_count,
        "record_count": record_count,
        "corrected_station_count": corrected_stations,
        "corrected_length_m": round(corrected_length, 3),
        "corrections_by_class": by_class,
        "highest_point": highest,
        "lowest_point": lowest,
        "max_sustained_grade": sustained,
        "max_interval_grade": interval,
        "raw_max_sustained_grade": dict(raw_summary["max_sustained_grade"]),
        "raw_highest_point": dict(raw_summary["highest_point"]),
    }


def derive_continental_conditioned_profile(
    elevation_lock_path: Path,
    dem_lock_path: Path,
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
    output_path: Path,
    *,
    derived_at: str | None = None,
) -> dict[str, Any]:
    """Derive the ADR-0017 conditioned elevation profile from committed locks.

    A pure function of the committed corridor elevation lock and the directed
    route lock - no caches, rasters, or network. Every correction is a
    bounded, evidence-linked conditioning record (interval, artifact class,
    method, before/after, replacement values); nothing outside a record's
    interior changes, and the stage refuses outright when a window cannot be
    conditioned under the physical sustained-grade bound.
    """
    elevation_lock = validate_continental_corridor_elevation(
        elevation_lock_path,
        dem_lock_path,
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    directed_lock = load_json(directed_lock_path)
    timestamp = derived_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    directed_by_id = {
        record["segment_id"]: record for record in directed_lock["segments"]
    }
    segments_payload: list[dict[str, Any]] = []
    for segment in elevation_lock["segments"]:
        segment_id = segment["segment_id"]
        offsets = _elevation_station_offsets(
            segment["geodesic_length_m"], ELEVATION_STATION_INTERVAL_M
        )
        elevations = segment["elevations_m"]
        chord_spans = _directed_chord_spans(directed_by_id[segment_id])
        records, conditioned = _condition_segment_profile(
            segment_id, offsets, elevations, chord_spans, AUTHORED_TUNNEL_REGISTRY
        )
        statistics = _elevation_profile_statistics(
            offsets,
            conditioned,
            ELEVATION_STATION_INTERVAL_M,
            ELEVATION_SUSTAINED_WINDOW_M,
        )
        sustained = statistics["max_sustained_grade"]
        if sustained is not None and (
            abs(sustained["grade_percent"]) > CONDITIONING_SUSTAINED_BOUND_PERCENT
        ):
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "conditioned profile still exceeds the "
                        "physical sustained-grade bound",
                        "segment_id": segment_id,
                        "max_sustained_grade": sustained,
                        "bound_percent": CONDITIONING_SUSTAINED_BOUND_PERCENT,
                    },
                    sort_keys=True,
                )
            )
        segments_payload.append(
            {
                "segment_id": segment_id,
                "geodesic_length_m": segment["geodesic_length_m"],
                "station_interval_m": ELEVATION_STATION_INTERVAL_M,
                "station_count": len(offsets),
                "terminal_station_m": offsets[-1],
                "record_count": len(records),
                "corrected_station_count": sum(
                    record["interior_station_count"] for record in records
                ),
                "conditioning_records": records,
                "conditioned_profile_sha256": canonical_sha256(conditioned),
                "statistics": statistics,
            }
        )
    used_tunnels = {
        record["evidence"]["authored_tunnel"]["tunnel_id"]
        for segment in segments_payload
        for record in segment["conditioning_records"]
        if record["artifact_class"] == "tunnel_bore"
    }
    for entry in AUTHORED_TUNNEL_REGISTRY:
        if entry["tunnel_id"] not in used_tunnels:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "authored tunnel matched no conditioning "
                        "window",
                        "tunnel_id": entry["tunnel_id"],
                    },
                    sort_keys=True,
                )
            )
    paths_payload = _elevation_path_records(directed_lock["paths"], segments_payload)
    summary = _conditioned_summary(segments_payload, elevation_lock["summary"])
    payload = {
        "schema_version": 1,
        "status": CONDITIONED_PROFILE_STATUS,
        "decision": "ADR-0017",
        "route_decision": elevation_lock["route_decision"],
        "carriageway_decision": "ADR-0014",
        "derived_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "dem_product_lock_sha256": compute_sha256(dem_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
        "corridor_elevation_lock_sha256": compute_sha256(elevation_lock_path),
        "model": {
            "interval_trigger_grade_percent": CONDITIONING_INTERVAL_TRIGGER_PERCENT,
            "sustained_bound_percent": CONDITIONING_SUSTAINED_BOUND_PERCENT,
            "flat_run_min_stations": CONDITIONING_FLAT_RUN_MIN_STATIONS,
            "join_distance_m": CONDITIONING_JOIN_DISTANCE_M,
            "method": CONDITIONING_METHOD,
            "station_interval_m": ELEVATION_STATION_INTERVAL_M,
            "sustained_grade_window_m": ELEVATION_SUSTAINED_WINDOW_M,
            "elevation_decimals": ELEVATION_VALUE_DECIMALS,
            "bound_justification": (
                "Sustained design grades on the US interstate system reach "
                "six percent, with mountainous exceptions near seven; seven "
                "percent over the locked 1 km window is the physical "
                "plausibility bound. The 100 m interval trigger of twelve "
                "percent is that envelope plus double the per-leg sampling "
                "noise of bilinear 1/3 arc-second samples on legitimate "
                "steep pavement, so only unambiguous artifacts condition; "
                "intervals between the bounds remain recorded raster noise "
                "for the package-build grade policy."
            ),
            "conditioning_note": (
                "Corrections replace only each record's interior stations "
                "with the boundary chord, rounded to the locked precision; "
                "boundary stations keep their committed raw values, every "
                "record carries before/after evidence, and the conditioned "
                "profile reproduces deterministically from the raw lock "
                "plus the records."
            ),
        },
        "authored_tunnels": [dict(entry) for entry in AUTHORED_TUNNEL_REGISTRY],
        "source_policy": dict(CONDITIONED_PROFILE_SOURCE_POLICY),
        "segment_count": len(segments_payload),
        "segments": segments_payload,
        "segments_sha256": canonical_sha256(segments_payload),
        "paths": paths_payload,
        "paths_sha256": canonical_sha256(paths_payload),
        "summary": summary,
        "next_stage": CONDITIONED_PROFILE_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_conditioned_profile(
    conditioned_lock_path: Path,
    elevation_lock_path: Path,
    dem_lock_path: Path,
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the conditioned profile lock without caches or network.

    The whole conditioning derivation is recomputed from the committed raw
    elevations under the module's locked model constants - windows, classes,
    replacement values, statistics, paths, and summary must all reproduce
    exactly, so a drifted record, a widened bound, or a silent smooth cannot
    validate itself.
    """
    payload = load_json(conditioned_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Conditioned profile lock schema_version must be 1.")
    if payload.get("status") != CONDITIONED_PROFILE_STATUS:
        raise ValueError("Conditioned profile lock has an unsupported status.")
    if payload.get("decision") != "ADR-0017":
        raise ValueError("Conditioned profile lock does not cite ADR-0017.")
    elevation_lock = validate_continental_corridor_elevation(
        elevation_lock_path,
        dem_lock_path,
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    directed_lock = load_json(directed_lock_path)
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "dem_product_lock_sha256": compute_sha256(dem_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
        "corridor_elevation_lock_sha256": compute_sha256(elevation_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Conditioned profile lock input hash drifted.")
    model = payload.get("model", {})
    if (
        model.get("interval_trigger_grade_percent")
        != CONDITIONING_INTERVAL_TRIGGER_PERCENT
        or model.get("sustained_bound_percent") != CONDITIONING_SUSTAINED_BOUND_PERCENT
        or model.get("flat_run_min_stations") != CONDITIONING_FLAT_RUN_MIN_STATIONS
        or model.get("join_distance_m") != CONDITIONING_JOIN_DISTANCE_M
        or model.get("method") != CONDITIONING_METHOD
        or model.get("station_interval_m") != ELEVATION_STATION_INTERVAL_M
        or model.get("sustained_grade_window_m") != ELEVATION_SUSTAINED_WINDOW_M
        or model.get("elevation_decimals") != ELEVATION_VALUE_DECIMALS
    ):
        raise ValueError("Conditioned profile lock model constants drifted.")
    if payload.get("authored_tunnels") != [
        dict(entry) for entry in AUTHORED_TUNNEL_REGISTRY
    ]:
        raise ValueError("Conditioned profile lock authored tunnels drifted.")
    if payload.get("source_policy") != CONDITIONED_PROFILE_SOURCE_POLICY:
        raise ValueError("Conditioned profile lock source policy drifted.")
    segments = payload.get("segments", [])
    if payload.get("segment_count") != len(segments) or [
        segment.get("segment_id") for segment in segments
    ] != [segment["segment_id"] for segment in elevation_lock["segments"]]:
        raise ValueError(
            "Conditioned profile lock does not cover exactly the locked "
            "segments in order."
        )
    directed_by_id = {
        record["segment_id"]: record for record in directed_lock["segments"]
    }
    raw_by_id = {
        segment["segment_id"]: segment for segment in elevation_lock["segments"]
    }
    for segment in segments:
        segment_id = segment["segment_id"]
        raw_segment = raw_by_id[segment_id]
        offsets = _elevation_station_offsets(
            raw_segment["geodesic_length_m"], ELEVATION_STATION_INTERVAL_M
        )
        if (
            segment.get("geodesic_length_m") != raw_segment["geodesic_length_m"]
            or segment.get("station_interval_m") != ELEVATION_STATION_INTERVAL_M
            or segment.get("station_count") != len(offsets)
            or segment.get("terminal_station_m") != offsets[-1]
        ):
            raise ValueError(
                f"Conditioned segment '{segment_id}' stationing drifted from "
                "the raw profile."
            )
        chord_spans = _directed_chord_spans(directed_by_id[segment_id])
        expected_records, conditioned = _condition_segment_profile(
            segment_id,
            offsets,
            raw_segment["elevations_m"],
            chord_spans,
            AUTHORED_TUNNEL_REGISTRY,
        )
        if segment.get("conditioning_records") != expected_records:
            raise ValueError(
                f"Conditioned segment '{segment_id}' records do not reproduce "
                "from the committed raw profile under the locked model."
            )
        if segment.get("record_count") != len(expected_records) or segment.get(
            "corrected_station_count"
        ) != sum(record["interior_station_count"] for record in expected_records):
            raise ValueError(
                f"Conditioned segment '{segment_id}' record accounting drifted."
            )
        if segment.get("conditioned_profile_sha256") != canonical_sha256(conditioned):
            raise ValueError(
                f"Conditioned segment '{segment_id}' profile digest drifted."
            )
        expected_statistics = _elevation_profile_statistics(
            offsets,
            conditioned,
            ELEVATION_STATION_INTERVAL_M,
            ELEVATION_SUSTAINED_WINDOW_M,
        )
        if segment.get("statistics") != expected_statistics:
            raise ValueError(
                f"Conditioned segment '{segment_id}' statistics do not "
                "reproduce from the conditioned profile."
            )
        sustained = expected_statistics["max_sustained_grade"]
        if sustained is not None and (
            abs(sustained["grade_percent"]) > CONDITIONING_SUSTAINED_BOUND_PERCENT
        ):
            raise ValueError(
                f"Conditioned segment '{segment_id}' still exceeds the "
                "physical sustained-grade bound."
            )
    if payload.get("segments_sha256") != canonical_sha256(segments):
        raise ValueError("Conditioned profile lock segment digest drifted.")
    expected_paths = _elevation_path_records(directed_lock["paths"], segments)
    if payload.get("paths") != expected_paths:
        raise ValueError(
            "Conditioned profile lock paths do not reproduce from the "
            "committed segments."
        )
    if payload.get("paths_sha256") != canonical_sha256(expected_paths):
        raise ValueError("Conditioned profile lock path digest drifted.")
    expected_summary = _conditioned_summary(segments, elevation_lock["summary"])
    if payload.get("summary") != expected_summary:
        raise ValueError(
            "Conditioned profile lock summary does not reproduce from the "
            "committed segments."
        )
    if payload.get("next_stage") != CONDITIONED_PROFILE_NEXT_STAGE:
        raise ValueError("Conditioned profile lock next stage drifted.")
    return payload


WESTBOUND_CARRIAGEWAY_STATUS = "portal_corridor_locked_transfer_geometry_pending"

# The v1 lock (the first carriageway cut, with the three traversed NHS fill
# chords still riding their pinned boundary chords and no endpoint
# connectors) is superseded by the schema-2 revision, never rewritten: its
# recorded digest and status stay here as append-only history.
SUPERSEDED_WESTBOUND_CARRIAGEWAY_V1 = {
    "artifact": "westbound-carriageway-lock.v1.json",
    "schema_version": 1,
    "sha256": "4607550702f6042412f99c45e12008a7a5c299c817deb62bb70cf29cde570c5b",
    "status": "westbound_carriageway_locked_junction_geometry_pending",
    "superseded_reason": (
        "The junction-and-span-geometry stage replaced the three traversed "
        "NHS fill chords with their seam-registered conflated spans, "
        "integrated the two authored ADR-0024 endpoint connectors, and "
        "published the portal-to-portal run length; the v1 gate results "
        "over chord-class fill geometry are history, not current claims."
    ),
}

# ADR-0014 reciprocal carriageway model parameters. The offset is an authored
# uniform model parameter under ADR-0017's observed/derived/authored
# discipline - NHPN asserts a single facility centerline and no median
# geometry, so the 20 m carriageway-centreline separation (two 12 ft lanes
# per carriageway around a 40 ft-class depressed median gives 64 ft = 19.5 m;
# common rural interstate medians span 36-60 ft) is recorded as authored and
# never claimed as observed cross-section. Per-site cross-sections are later
# lane-topology refinement.
CARRIAGEWAY_OFFSET_M = 10.0
CARRIAGEWAY_QUAD_SEGS = 8
CARRIAGEWAY_JOIN_STYLE = "round"
CARRIAGEWAY_GEOMETRY_DECIMALS = 3
# Consecutive directed elements share snapped nodes within the locked 1 m
# endpoint tolerance; a joint gap beyond it is a chain break, not a bridge.
CARRIAGEWAY_JOINT_GAP_LIMIT_M = 1.0
# Heading discipline at the census lens the break-end census established:
# turn angles are measured on 25 m tangents, corner-class turns (> 20
# degrees) are recorded exception sites, and reversal-class turns (> 150
# degrees) are physically impossible pavement - the corridor's real corners
# top out at 143.7 degrees (the Barstow junction approach) while the
# characterised joint back-steps measure 173.8-180.0 degrees, so 150 cleanly
# separates road from artifact.
CARRIAGEWAY_TANGENT_LENS_M = 25.0
CARRIAGEWAY_CORNER_THRESHOLD_DEG = 20.0
CARRIAGEWAY_REVERSAL_THRESHOLD_DEG = 150.0
CARRIAGEWAY_CORNER_CLUSTER_STEPS = 10
CARRIAGEWAY_MAX_REVERSAL_REMOVALS = 8
# A removed reversal apex within this distance of an authored overlay chord
# is the chord's own out-and-back (the Omaha 1.011 m start-to-start chord);
# anything else is an NHPN joint back-step.
CARRIAGEWAY_OVERLAY_PROXIMITY_M = 2.0
# Corner sites within this distance of an authored overlay chord adjudicate
# that overlay's deferred heading gate against its recorded corner constraint.
CARRIAGEWAY_OVERLAY_CORNER_LENS_M = 100.0
CARRIAGEWAY_OVERLAY_CORNER_TOLERANCE_DEG = 5.0
# The reciprocal pair must hold the dual-carriageway envelope apart
# everywhere: five percent under the nominal 2 x offset separation absorbs
# join-arc trimming at recorded corners without ever letting the pair touch.
CARRIAGEWAY_MIN_SEPARATION_M = 19.0
# An offset curve's length differs from its centerline by join geometry:
# outer round joins add up to offset x turn of arc per corner and inner
# joins trim up to 2 x offset x tan(turn/2). On the corner-densest segment
# (the Virgin River Gorge curves plus the Barstow junction-approach corner)
# the measured divergence is 0.107 percent; 0.2 percent accommodates
# corner-class join geometry while tripping genuine geometry loss (a
# dropped loop or a collapsed corner run).
CARRIAGEWAY_LENGTH_AGREEMENT_RATIO = 0.002
# Backtrack reciprocity: the mirrored coordinate run must reproduce the
# directed lock's recorded backtrack length to the rounding quantum, and the
# departing westbound carriageway must equal the arriving eastbound
# carriageway over that run - GEOS offsets of identical reversed lines agree
# exactly, so the tolerance is a numerical epsilon, not a fudge.
CARRIAGEWAY_BACKTRACK_LENGTH_TOLERANCE_M = 0.005
CARRIAGEWAY_BACKTRACK_MIRROR_TOLERANCE_M = 0.001
CARRIAGEWAY_BACKTRACK_MATCH_EPSILON_M = 1e-6

CARRIAGEWAY_CORNER_CLASSES = (
    "overlay_corner",
    "conflated_span_corner",
    "junction_backtrack_approach",
    "route_corner",
)
CARRIAGEWAY_REVERSAL_CLASSES = ("overlay_out_and_back", "joint_back_step")

# Conflated-span replacement: each traversed fill chord is replaced by its
# conflation-lock span, reassembled from the locked NHS fill cache and
# refused unless it reproduces the locked geometry digest, then registered
# onto the pinned chord endpoints by a correction interpolated linearly in
# arc length. The endpoint corrections are exactly the conflation lock's
# recorded seam offsets (the two datasets' characterised lateral
# disagreement inside the catalog's ~80 m NHPN error class); the measured
# correction must agree with the recorded offset to the measure-quantum
# rounding envelope.
CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M = 0.02
# Corner sites within this lens of a replaced span record the span's
# cross-dataset seam heading and its real NHS road curvature as their own
# recorded class.
CARRIAGEWAY_SPAN_CORNER_LENS_M = 100.0

CARRIAGEWAY_MODEL = {
    "decision": "ADR-0014",
    "offset_m": CARRIAGEWAY_OFFSET_M,
    "offset_provenance": "authored",
    "offset_justification": (
        "NHPN models the facility as a single centerline with no median "
        "geometry; the 20 m carriageway-centreline separation matches a "
        "typical rural divided interstate cross-section (two 12 ft lanes "
        "per carriageway around a 40 ft-class depressed median = 64 ft = "
        "19.5 m; common medians span 36-60 ft). Authored uniform model "
        "parameter per ADR-0017 - never claimed as observed cross-section; "
        "per-site cross-sections are later lane-topology refinement."
    ),
    "metric_crs": "EPSG:5070",
    "join_style": CARRIAGEWAY_JOIN_STYLE,
    "quad_segs": CARRIAGEWAY_QUAD_SEGS,
    "geometry_decimals": CARRIAGEWAY_GEOMETRY_DECIMALS,
    "tangent_lens_m": CARRIAGEWAY_TANGENT_LENS_M,
    "corner_threshold_deg": CARRIAGEWAY_CORNER_THRESHOLD_DEG,
    "reversal_threshold_deg": CARRIAGEWAY_REVERSAL_THRESHOLD_DEG,
    "side_rule": (
        "The westbound carriageway offsets to the right of westbound travel; "
        "the source centerline is the median axis on the left of each "
        "directed carriageway, carrying ADR-0014 marking semantics (yellow "
        "continuous left/median edge, white broken same-direction dividers, "
        "white continuous right edge)."
    ),
    "pairing_rule": (
        "Per directed element index k of segment s, the westbound edge "
        "'<s>:<k>:westbound' pairs the opposing edge '<s>:<k>:eastbound' in "
        "carriageway group '<s>:<k>' with roadway_kind divided_carriageway - "
        "a deterministic reciprocal rule over the locked element sequence "
        "rather than 12,582 explicit rows. The eastbound carriageway is the "
        "opposite offset of the same locked centerline with travel reversed, "
        "so the pair is reciprocal by construction and no opposing geometry "
        "is synthesized from unrelated nearby lines."
    ),
    "span_replacement": {
        "decision": "ADR-0026",
        "method": "seam_registration_linear_in_arc_length",
        "seam_tolerance_m": CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M,
        "span_corner_lens_m": CARRIAGEWAY_SPAN_CORNER_LENS_M,
        "justification": (
            "Each traversed NHS fill chord is replaced by its conflation-"
            "lock span, reassembled from the locked NHS fill cache and "
            "refused unless it reproduces the locked geometry digest, then "
            "registered onto the pinned chord endpoints by a correction "
            "interpolated linearly in arc length. The endpoint corrections "
            "equal the conflation lock's recorded seam offsets - the two "
            "datasets' characterised lateral disagreement inside the "
            "catalog's ~80 m NHPN error class - so the chain joints stay "
            "exact and no seam jog is invented. Vertical context is the "
            "ADR-0017 conditioned profile over the chord's directed-walk "
            "station interval, re-parametrised by the span's arc length; no "
            "observed span elevation is claimed."
        ),
    },
}

CARRIAGEWAY_DEFERRED_GATES = {
    "deferred_to": "lane-topology-and-package-build-stage",
    "gates": [
        "curvature_design_radius",
        "curvature_rate",
        "vertical_curvature",
        "sightline",
        "clearance",
        "collision",
        "lane_connection",
        "drivability",
    ],
    "reason": (
        "NHPN centerline vertices carry catalog-documented ~80 m class "
        "horizontal error; design-radius adjudication on 25 m tangents would "
        "measure digitization noise, not road design. This stage adjudicates "
        "corner-class heading discipline (every turn beyond 20 degrees at "
        "the 25 m lens is a recorded exception site, reversal-class turns "
        "are refused), topology (self-intersection, monotonicity, "
        "reciprocal separation), and the grade gate against the conditioned "
        "profile; the finer gates run when lane splines and collision "
        "ribbons are generated over this carriageway model."
    ),
}

CARRIAGEWAY_SOURCE_POLICY = {
    "carriageway_decision": "ADR-0014",
    "reconstruction_decision": "ADR-0018",
    "context_decision": "ADR-0017",
    "control_line_decision": "ADR-0013",
    "opposing_geometry_synthesized_from_proximity": False,
    "fill_chords_replaced_by_conflated_spans": True,
    "junction_transfer_geometry_generated": False,
    "endpoint_connectors_generated": True,
    "continental_downloads_committed": False,
    "authoritative_distance_claimed": True,
    "authoritative_distance_scope": (
        "ADR-0024 portal-to-portal westbound run length over the locked "
        "corridor (traversed fill chords replaced by their seam-registered "
        "conflated NHS spans) plus the two authored endpoint connectors; "
        "the connector contribution carries declared authored-waypoint "
        "precision, recorded in the run-length record."
    ),
}

WESTBOUND_CARRIAGEWAY_NEXT_STAGE = {
    "id": "transfer-and-lane-geometry",
    "requires": [
        "transfer geometry at the seven cross-segment junctions and the two "
        "junction-backtrack turn-arounds",
        "lane topology, ramps, and collision over the carriageway model "
        "with the deferred ADR-0018 gates, then the GeoPackage/FlatBuffer "
        "package build under ADR-0019 budgets",
        "the southern path's Holland Tunnel connector (nyc-start-to-i78) "
        "before its portal-to-portal figure can publish",
        "runtime integration and the double-build/traversal evidence",
    ],
}


def _carriageway_gate(measured: Any, threshold: Any, passed: bool) -> dict[str, Any]:
    return {"measured": measured, "threshold": threshold, "passed": bool(passed)}


def _polyline_length(coordinates: Sequence[tuple[float, float]]) -> float:
    return sum(
        math.dist(coordinates[index - 1], coordinates[index])
        for index in range(1, len(coordinates))
    )


def _vertex_turn_degrees(
    coordinates: Sequence[tuple[float, float]], index: int
) -> float:
    """Unsigned direction change at one interior vertex."""
    ax = coordinates[index][0] - coordinates[index - 1][0]
    ay = coordinates[index][1] - coordinates[index - 1][1]
    bx = coordinates[index + 1][0] - coordinates[index][0]
    by = coordinates[index + 1][1] - coordinates[index][1]
    da = math.hypot(ax, ay)
    db = math.hypot(bx, by)
    if da < 1e-9 or db < 1e-9:
        return 0.0
    dot = max(-1.0, min(1.0, (ax * bx + ay * by) / (da * db)))
    return math.degrees(math.acos(dot))


def _dedupe_polyline(
    coordinates: Sequence[tuple[float, float]], epsilon: float = 1e-9
) -> list[tuple[float, float]]:
    deduped = [tuple(coordinates[0])]
    for point in coordinates[1:]:
        if math.dist(deduped[-1], point) > epsilon:
            deduped.append(tuple(point))
    return deduped


def _resample_polyline(
    coordinates: Sequence[tuple[float, float]], spacing: float
) -> list[tuple[float, float]]:
    """Points every ``spacing`` metres along the polyline plus its terminus.

    A single linear walk over the vertices - deterministic and linear-time
    where per-point interpolation against a 70,000-vertex line would not be.
    """
    samples = [tuple(coordinates[0])]
    target = spacing
    travelled = 0.0
    for index in range(1, len(coordinates)):
        previous = coordinates[index - 1]
        current = coordinates[index]
        leg = math.dist(previous, current)
        while leg > 0 and target <= travelled + leg + 1e-12:
            fraction = (target - travelled) / leg
            samples.append(
                (
                    previous[0] + (current[0] - previous[0]) * fraction,
                    previous[1] + (current[1] - previous[1]) * fraction,
                )
            )
            target += spacing
        travelled += leg
    terminus = tuple(coordinates[-1])
    if math.dist(samples[-1], terminus) > 1e-9:
        samples.append(terminus)
    return samples


def _build_segment_chain(
    segment_id: str, geometries: Sequence[LineString]
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    """One continuous metric-CRS chain over a segment's directed elements.

    Consecutive element geometries share snapped nodes exactly or within the
    locked endpoint tolerance; exact joints deduplicate and tolerance joints
    bridge with a recorded step. Anything beyond the tolerance refuses.
    """
    coordinates: list[tuple[float, float]] = []
    max_joint_gap = 0.0
    bridged = 0
    for geometry in geometries:
        points = [tuple(point) for point in geometry.coords]
        if coordinates:
            gap = math.dist(coordinates[-1], points[0])
            if gap > CARRIAGEWAY_JOINT_GAP_LIMIT_M:
                raise ValueError(
                    json.dumps(
                        {
                            "refusal": "directed element joint exceeds the "
                            "locked endpoint tolerance",
                            "segment_id": segment_id,
                            "joint_gap_m": round(gap, 6),
                            "limit_m": CARRIAGEWAY_JOINT_GAP_LIMIT_M,
                        },
                        sort_keys=True,
                    )
                )
            max_joint_gap = max(max_joint_gap, gap)
            if gap <= 1e-6:
                points = points[1:]
            else:
                bridged += 1
        coordinates.extend(points)
    return _dedupe_polyline(coordinates), {
        "max_joint_gap_m": round(max_joint_gap, 6),
        "bridged_joint_count": bridged,
    }


def _excise_reversal_apexes(
    segment_id: str,
    coordinates: list[tuple[float, float]],
    overlay_lines: Sequence[LineString],
    inverse: Transformer,
) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    """Remove reversal-class apex vertices with a bounded record for each.

    A vertex whose tangents reverse beyond the threshold is doubled travel
    the source digitized (a record-joint overlap back-step, or an authored
    overlay chord's lateral out-and-back), never pavement; the apex is
    removed, the chain re-deduplicated, and the excision recorded with
    before/after lengths. The loop is greedy on the worst turn and refuses
    beyond the removal cap.
    """
    records: list[dict[str, Any]] = []
    while True:
        worst: tuple[int, float] | None = None
        for index in range(1, len(coordinates) - 1):
            angle = _vertex_turn_degrees(coordinates, index)
            if angle > CARRIAGEWAY_REVERSAL_THRESHOLD_DEG and (
                worst is None or angle > worst[1]
            ):
                worst = (index, angle)
        if worst is None:
            break
        if len(records) >= CARRIAGEWAY_MAX_REVERSAL_REMOVALS:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "reversal excision exceeded the removal cap",
                        "segment_id": segment_id,
                        "cap": CARRIAGEWAY_MAX_REVERSAL_REMOVALS,
                    },
                    sort_keys=True,
                )
            )
        index, angle = worst
        apex = coordinates[index]
        station = round(_polyline_length(coordinates[: index + 1]), 3)
        apex_point = Point(apex)
        reversal_class = "joint_back_step"
        for overlay_line in overlay_lines:
            if apex_point.distance(overlay_line) <= CARRIAGEWAY_OVERLAY_PROXIMITY_M:
                reversal_class = "overlay_out_and_back"
                break
        length_before = _polyline_length(coordinates)
        del coordinates[index]
        coordinates = _dedupe_polyline(coordinates)
        longitude, latitude = inverse.transform(apex[0], apex[1])
        records.append(
            {
                "reversal_class": reversal_class,
                "chain_station_m": station,
                "turn_deg": round(angle, 2),
                "coordinate": [round(longitude, 7), round(latitude, 7)],
                "chain_length_delta_m": round(
                    _polyline_length(coordinates) - length_before, 3
                ),
            }
        )
    return coordinates, records


def _carriageway_corner_sites(
    segment_id: str,
    coordinates: Sequence[tuple[float, float]],
    overlay_lines: Sequence[LineString],
    tail_backtrack_m: float,
    head_backtrack_m: float,
    inverse: Transformer,
    span_lines: Sequence[LineString] = (),
) -> list[dict[str, Any]]:
    """Corner-class heading exceptions at the 25 m tangent lens.

    Every turn beyond the corner threshold joins a cluster; each cluster is
    recorded with its peak and summed turn and classified: an overlay corner
    (adjudicating that overlay's deferred heading gate), a conflated-span
    corner (the replaced span's cross-dataset seam heading or its real NHS
    road curvature), a junction-backtrack approach (transfer geometry is
    deferred stage output), or a route corner the designated route itself
    turns through. Reversal-class turns at the lens refuse - the chain was
    conditioned below them.
    """
    samples = _resample_polyline(coordinates, CARRIAGEWAY_TANGENT_LENS_M)
    chain_length = _polyline_length(coordinates)
    flagged: list[tuple[float, int]] = []
    for index in range(1, len(samples) - 1):
        angle = _vertex_turn_degrees(samples, index)
        if angle > CARRIAGEWAY_REVERSAL_THRESHOLD_DEG:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "reversal-class turn survived conditioning",
                        "segment_id": segment_id,
                        "turn_deg": round(angle, 2),
                        "station_m": round(index * CARRIAGEWAY_TANGENT_LENS_M, 1),
                    },
                    sort_keys=True,
                )
            )
        if angle > CARRIAGEWAY_CORNER_THRESHOLD_DEG:
            flagged.append((angle, index))
    clusters: list[list[tuple[float, int]]] = []
    for angle, index in flagged:
        if (
            clusters
            and index - clusters[-1][-1][1] <= CARRIAGEWAY_CORNER_CLUSTER_STEPS
        ):
            clusters[-1].append((angle, index))
        else:
            clusters.append([(angle, index)])
    sites: list[dict[str, Any]] = []
    for cluster_index, cluster in enumerate(clusters):
        peak_angle, peak_sample = max(cluster)
        station = round(peak_sample * CARRIAGEWAY_TANGENT_LENS_M, 1)
        peak_point = Point(samples[peak_sample])
        corner_class = "route_corner"
        overlay_distance = None
        span_distance = None
        for overlay_line in overlay_lines:
            distance = peak_point.distance(overlay_line)
            if distance <= CARRIAGEWAY_OVERLAY_CORNER_LENS_M:
                corner_class = "overlay_corner"
                overlay_distance = round(distance, 3)
                break
        if corner_class == "route_corner":
            for span_line in span_lines:
                distance = peak_point.distance(span_line)
                if distance <= CARRIAGEWAY_SPAN_CORNER_LENS_M:
                    corner_class = "conflated_span_corner"
                    span_distance = round(distance, 3)
                    break
        if corner_class == "route_corner":
            margin = CARRIAGEWAY_TANGENT_LENS_M * CARRIAGEWAY_CORNER_CLUSTER_STEPS
            in_tail = tail_backtrack_m > 0 and station >= chain_length - (
                tail_backtrack_m + margin
            )
            in_head = head_backtrack_m > 0 and station <= head_backtrack_m + margin
            if in_tail or in_head:
                corner_class = "junction_backtrack_approach"
        longitude, latitude = inverse.transform(*samples[peak_sample])
        site = {
            "corner_id": f"{segment_id}--corner-{cluster_index:03d}",
            "corner_class": corner_class,
            "from_station_m": round(cluster[0][1] * CARRIAGEWAY_TANGENT_LENS_M, 1),
            "to_station_m": round(cluster[-1][1] * CARRIAGEWAY_TANGENT_LENS_M, 1),
            "peak_turn_deg": round(peak_angle, 2),
            "turn_sum_deg": round(sum(angle for angle, _ in cluster), 2),
            "sample_count": len(cluster),
            "coordinate": [round(longitude, 7), round(latitude, 7)],
        }
        if overlay_distance is not None:
            site["overlay_distance_m"] = overlay_distance
        if span_distance is not None:
            site["span_distance_m"] = span_distance
        sites.append(site)
    return sites


def _offset_carriageway(
    segment_id: str, chain: LineString, side: str
) -> list[tuple[float, float]]:
    """One directed carriageway as a millimetre-rounded offset polyline."""
    distance = (
        -CARRIAGEWAY_OFFSET_M if side == "westbound" else CARRIAGEWAY_OFFSET_M
    )
    offset = chain.offset_curve(
        distance,
        quad_segs=CARRIAGEWAY_QUAD_SEGS,
        join_style=CARRIAGEWAY_JOIN_STYLE,
    )
    if offset.geom_type != "LineString" or offset.is_empty:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "carriageway offset is not a single line",
                    "segment_id": segment_id,
                    "side": side,
                    "geometry_type": offset.geom_type,
                },
                sort_keys=True,
            )
        )
    if not offset.is_simple:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "carriageway offset self-intersects",
                    "segment_id": segment_id,
                    "side": side,
                },
                sort_keys=True,
            )
        )
    rounded = [
        (
            round(x, CARRIAGEWAY_GEOMETRY_DECIMALS),
            round(y, CARRIAGEWAY_GEOMETRY_DECIMALS),
        )
        for x, y in offset.coords
    ]
    deduped = _dedupe_polyline(rounded) if rounded else []
    if len(deduped) < 2:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "carriageway offset is degenerate",
                    "segment_id": segment_id,
                    "side": side,
                },
                sort_keys=True,
            )
        )
    return deduped


def _directed_backtrack_junctions(
    directed_lock: dict[str, Any],
) -> list[dict[str, Any]]:
    """Unique junction-backtrack records across the locked paths."""
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in directed_lock["paths"]:
        for junction in path["junctions"]:
            if junction["backtrack_element_count"] <= 0:
                continue
            key = (
                junction["anchor_id"],
                junction["from_segment_id"],
                junction["to_segment_id"],
            )
            seen.setdefault(key, junction)
    return [seen[key] for key in sorted(seen)]


def _carriageway_backtrack_record(
    junction: dict[str, Any],
    arriving_chain: Sequence[tuple[float, float]],
    departing_chain: Sequence[tuple[float, float]],
) -> dict[str, Any]:
    """Prove the doubled junction-approach travel rides the reciprocal pair.

    The departing chain must open with the arriving chain's closing
    coordinates exactly mirrored; over that run the departing westbound
    carriageway must equal the arriving eastbound carriageway (the ADR-0014
    reciprocal edge), and the two directions' westbound carriageways must
    hold the full reciprocal separation. The turn-around at the anchor
    remains deferred transfer geometry, recorded, never bridged silently.
    """
    limit = min(len(arriving_chain), len(departing_chain))
    mirrored = 0
    while (
        mirrored < limit
        and math.dist(arriving_chain[-1 - mirrored], departing_chain[mirrored])
        <= CARRIAGEWAY_BACKTRACK_MATCH_EPSILON_M
    ):
        mirrored += 1
    if mirrored < 2:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "junction backtrack chains do not mirror",
                    "anchor_id": junction["anchor_id"],
                },
                sort_keys=True,
            )
        )
    shared = departing_chain[:mirrored]
    shared_length = _polyline_length(shared)
    if (
        abs(shared_length - junction["backtrack_length_m"])
        > CARRIAGEWAY_BACKTRACK_LENGTH_TOLERANCE_M
    ):
        raise ValueError(
            json.dumps(
                {
                    "refusal": "mirrored backtrack length drifted from the "
                    "directed lock",
                    "anchor_id": junction["anchor_id"],
                    "measured_m": round(shared_length, 3),
                    "locked_m": junction["backtrack_length_m"],
                },
                sort_keys=True,
            )
        )
    arriving_line = LineString(arriving_chain[-mirrored:])
    departing_line = LineString(shared)
    departing_westbound = departing_line.offset_curve(
        -CARRIAGEWAY_OFFSET_M,
        quad_segs=CARRIAGEWAY_QUAD_SEGS,
        join_style=CARRIAGEWAY_JOIN_STYLE,
    )
    arriving_eastbound = arriving_line.offset_curve(
        CARRIAGEWAY_OFFSET_M,
        quad_segs=CARRIAGEWAY_QUAD_SEGS,
        join_style=CARRIAGEWAY_JOIN_STYLE,
    )
    arriving_westbound = arriving_line.offset_curve(
        -CARRIAGEWAY_OFFSET_M,
        quad_segs=CARRIAGEWAY_QUAD_SEGS,
        join_style=CARRIAGEWAY_JOIN_STYLE,
    )
    mirror_gap = departing_westbound.hausdorff_distance(arriving_eastbound)
    separation = departing_westbound.distance(arriving_westbound)
    if mirror_gap > CARRIAGEWAY_BACKTRACK_MIRROR_TOLERANCE_M:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "backtrack reciprocity failed: the departing "
                    "westbound carriageway is not the arriving eastbound "
                    "carriageway",
                    "anchor_id": junction["anchor_id"],
                    "mirror_gap_m": round(mirror_gap, 6),
                },
                sort_keys=True,
            )
        )
    if separation < CARRIAGEWAY_MIN_SEPARATION_M:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "backtrack carriageways violate the "
                    "reciprocal separation",
                    "anchor_id": junction["anchor_id"],
                    "separation_m": round(separation, 3),
                },
                sort_keys=True,
            )
        )
    return {
        "anchor_id": junction["anchor_id"],
        "from_segment_id": junction["from_segment_id"],
        "to_segment_id": junction["to_segment_id"],
        "backtrack_element_count": junction["backtrack_element_count"],
        "mirrored_vertex_count": mirrored,
        "mirrored_length_m": round(shared_length, 3),
        "locked_backtrack_length_m": junction["backtrack_length_m"],
        "reciprocity_gap_m": round(mirror_gap, 6),
        "westbound_separation_m": round(separation, 3),
        "resolution": (
            "The doubled junction-approach travel rides the reciprocal "
            "carriageway pair: the departing westbound carriageway over the "
            "mirrored elements is exactly the arriving eastbound "
            "carriageway, so the directed route occupies each physical "
            "roadway once per direction. The anchor turn-around is deferred "
            "transfer geometry."
        ),
    }


def _conditioned_segment_elevations(
    elevation_segment: dict[str, Any], conditioned_segment: dict[str, Any]
) -> list[float]:
    """One segment's conditioned station elevations from the committed locks.

    The committed raw profile with every conditioning record's replacement
    values applied over its interior stations - exactly the substitution the
    conditioned-profile derivation recorded (boundary stations keep their raw
    values).
    """
    values = [float(value) for value in elevation_segment["elevations_m"]]
    interval = float(elevation_segment["station_interval_m"])
    for record in conditioned_segment["conditioning_records"]:
        from_index = int(round(record["from_station_m"] / interval))
        to_index = int(round(record["to_station_m"] / interval))
        replacements = record["after"]["replacement_elevations_m"]
        if to_index - from_index - 1 != len(replacements):
            raise ValueError(
                f"Conditioning record '{record['record_id']}' interior span "
                "does not match its replacement values."
            )
        values[from_index + 1 : to_index] = [float(value) for value in replacements]
    return values


def _profile_elevation_at(
    values: Sequence[float],
    interval: float,
    terminal_station: float,
    station: float,
) -> float:
    """Linear interpolation of the station profile at one exact station."""
    clamped = min(max(station, 0.0), terminal_station)
    last_regular = len(values) - 2
    index = int(clamped // interval)
    if index >= last_regular:
        low_station = last_regular * interval
        high_station = terminal_station
        low_value = values[-2]
        high_value = values[-1]
    else:
        low_station = index * interval
        high_station = low_station + interval
        low_value = values[index]
        high_value = values[index + 1]
    if high_station <= low_station:
        return high_value
    fraction = (clamped - low_station) / (high_station - low_station)
    return low_value + (high_value - low_value) * fraction


def _span_vertical_context(
    elevation_segment: dict[str, Any],
    conditioned_segment: dict[str, Any],
    interval_from_m: float,
    interval_to_m: float,
    registered_geodesic_m: float,
) -> dict[str, Any]:
    """ADR-0017 vertical context for one replaced span.

    The conditioned profile over the chord's directed-walk station interval,
    re-parametrised by the registered span's arc length: a derived deck
    chord, never observed span elevation. The overlapping conditioning
    records are cited as the interval's characterised artifact evidence.
    """
    values = _conditioned_segment_elevations(elevation_segment, conditioned_segment)
    interval = float(elevation_segment["station_interval_m"])
    terminal = float(elevation_segment["terminal_station_m"])
    entry_elevation = _profile_elevation_at(values, interval, terminal, interval_from_m)
    exit_elevation = _profile_elevation_at(values, interval, terminal, interval_to_m)
    delta = exit_elevation - entry_elevation
    chord_length = interval_to_m - interval_from_m
    overlapping = [
        {
            "record_id": record["record_id"],
            "artifact_class": record["artifact_class"],
        }
        for record in conditioned_segment["conditioning_records"]
        if record["to_station_m"] >= interval_from_m
        and record["from_station_m"] <= interval_to_m
    ]
    span_grade = (
        delta / registered_geodesic_m * 100.0 if registered_geodesic_m > 0 else 0.0
    )
    return {
        "source": "conditioned-profile-lock over corridor-elevation-lock",
        "method": (
            "ADR-0017 deck-chord re-parametrisation: the conditioned "
            "profile's boundary elevations over the chord's directed-walk "
            "station interval map linearly onto the span's arc length; no "
            "observed span elevation is claimed."
        ),
        "chord_station_interval_m": [
            round(interval_from_m, 3),
            round(interval_to_m, 3),
        ],
        "boundary_elevations_m": [
            round(entry_elevation, 2),
            round(exit_elevation, 2),
        ],
        "conditioning_records": overlapping,
        "chord_grade_percent": round(
            delta / chord_length * 100.0 if chord_length > 0 else 0.0, 3
        ),
        "span_grade_percent": round(span_grade, 3),
    }


def _registered_conflation_span(
    site: dict[str, Any],
    conflation_site: dict[str, Any],
    fill_root: Path,
    forward: Transformer,
) -> tuple[LineString, dict[str, Any]]:
    """One traversed fill span, reassembled, verified, and seam-registered.

    Reassembles the conflation lock's oriented span geometry from the locked
    NHS fill cache (refusing unless it reproduces the locked geometry
    digest), orients it chord-from to chord-to, and registers it onto the
    pinned chord endpoints with a correction interpolated linearly in arc
    length whose endpoint magnitudes must reproduce the conflation lock's
    recorded seam offsets.
    """
    site_id = site["site_id"]
    features = _load_locked_nhs_site_features(site, fill_root / site_id)
    orientation_by_id = {
        entry["object_id"]: entry["orientation"]
        for entry in conflation_site["orientation"]
    }
    groups = site["fill_route_groups"]
    if len(groups) != 1:
        raise ValueError(
            f"Fill site '{site_id}' does not carry exactly one qualifying "
            "route group."
        )
    group_ids = sorted(record["object_id"] for record in groups[0]["records"])
    records = []
    record_by_id: dict[int, dict[str, Any]] = {}
    for object_id in group_ids:
        attributes = features[object_id]["attributes"]
        record = {
            "object_id": object_id,
            "begin": float(attributes.get("BEGINPOINT") or 0.0),
            "end": float(attributes.get("ENDPOINT") or 0.0),
            "orientation": orientation_by_id[object_id],
            "line": transform(
                forward.transform, _merged_feature_line(features[object_id])
            ),
        }
        records.append(record)
        record_by_id[object_id] = record
    span_block = conflation_site["span"]
    # The conflation derive clipped at full-precision seam measures and
    # recorded them rounded; recompute each seam measure through the exact
    # projection the conflation used and refuse if the rounded value no
    # longer reproduces the lock.
    seam_measures: list[float] = []
    for seam in conflation_site["seams"]:
        seam_record = record_by_id[seam["nhs"]["object_id"]]
        seam_point = Point(
            forward.transform(
                seam["coordinate"]["longitude"], seam["coordinate"]["latitude"]
            )
        )
        distance_along = float(seam_record["line"].project(seam_point))
        measure = _measure_at_distance(seam_record, distance_along)
        if round(measure, 6) != seam["nhs"]["measure_at_seam"]:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "recomputed seam measure does not "
                        "reproduce the conflation lock",
                        "site_id": site_id,
                        "side": seam["side"],
                        "recomputed": round(measure, 6),
                        "locked": seam["nhs"]["measure_at_seam"],
                    },
                    sort_keys=True,
                )
            )
        seam_measures.append(measure)
    span_low, span_high = sorted(seam_measures)
    span = _assemble_conflation_span(records, span_low, span_high)
    span_line = span["line"]
    digest = canonical_sha256(
        [[round(x, 3), round(y, 3)] for x, y in span_line.coords]
    )
    if digest != span_block["geometry_sha256"]:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "reassembled span does not reproduce the "
                    "conflation lock's geometry digest",
                    "site_id": site_id,
                    "reassembled_sha256": digest,
                    "locked_sha256": span_block["geometry_sha256"],
                },
                sort_keys=True,
            )
        )
    measure_by_side = {
        seam["side"]: seam["nhs"]["measure_at_seam"]
        for seam in conflation_site["seams"]
    }
    offsets_by_side = {
        seam["side"]: seam["nhs"]["seam_offset_m"]
        for seam in conflation_site["seams"]
    }
    coordinates = list(span_line.coords)
    if measure_by_side["from"] > measure_by_side["to"]:
        coordinates = coordinates[::-1]
    chord_from = forward.transform(
        site["from_coordinate"]["longitude"], site["from_coordinate"]["latitude"]
    )
    chord_to = forward.transform(
        site["to_coordinate"]["longitude"], site["to_coordinate"]["latitude"]
    )
    from_offset = math.dist(chord_from, coordinates[0])
    to_offset = math.dist(chord_to, coordinates[-1])
    agreement = max(
        abs(from_offset - offsets_by_side["from"]),
        abs(to_offset - offsets_by_side["to"]),
    )
    if agreement > CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "seam registration disagrees with the "
                    "conflation lock's recorded seam offsets",
                    "site_id": site_id,
                    "measured_from_m": round(from_offset, 3),
                    "measured_to_m": round(to_offset, 3),
                    "recorded_from_m": offsets_by_side["from"],
                    "recorded_to_m": offsets_by_side["to"],
                    "tolerance_m": CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M,
                },
                sort_keys=True,
            )
        )
    delta_from = (chord_from[0] - coordinates[0][0], chord_from[1] - coordinates[0][1])
    delta_to = (chord_to[0] - coordinates[-1][0], chord_to[1] - coordinates[-1][1])
    total_length = _polyline_length(coordinates)
    registered: list[tuple[float, float]] = []
    travelled = 0.0
    for index, vertex in enumerate(coordinates):
        if index > 0:
            travelled += math.dist(coordinates[index - 1], vertex)
        fraction = travelled / total_length if total_length > 0 else 0.0
        registered.append(
            (
                vertex[0] + delta_from[0] * (1.0 - fraction) + delta_to[0] * fraction,
                vertex[1] + delta_from[1] * (1.0 - fraction) + delta_to[1] * fraction,
            )
        )
    registered[0] = chord_from
    registered[-1] = chord_to
    registered_line = LineString(registered)
    if not registered_line.is_simple:
        raise ValueError(
            json.dumps(
                {
                    "refusal": "registered span self-intersects",
                    "site_id": site_id,
                },
                sort_keys=True,
            )
        )
    facts = {
        "span": {
            "geometry_sha256": span_block["geometry_sha256"],
            "geometry_length_m": span_block["geometry_length_m"],
            "piece_count": len(span["pieces"]),
            "reassembled_digest_verified": True,
        },
        "seam_registration": {
            "method": "linear_in_arc_length",
            "from_offset_m": round(from_offset, 3),
            "to_offset_m": round(to_offset, 3),
            "recorded_seam_offsets_m": {
                "from": offsets_by_side["from"],
                "to": offsets_by_side["to"],
            },
            "offset_agreement_delta_m": round(agreement, 3),
        },
    }
    return registered_line, facts


def _run_length_records(
    directed_lock: dict[str, Any],
    connector_payload: dict[str, Any],
    span_replacements: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """The ADR-0024 portal-to-portal run-length record per locked path.

    A path publishes when every one of its excluded endpoint connectors is
    authored and gated; otherwise it stays recorded pending with the reason.
    The corridor figure is the directed lock's anchor-to-anchor total with
    each traversed fill chord's contribution replaced by its registered
    span's measured lengths.
    """
    connectors_by_id = {
        connector["connector_id"]: connector
        for connector in connector_payload["connectors"]
    }
    replacements_by_segment: dict[str, list[dict[str, Any]]] = {}
    for replacement in span_replacements:
        replacements_by_segment.setdefault(replacement["segment_id"], []).append(
            replacement
        )
    paths: list[dict[str, Any]] = []
    canonical: dict[str, Any] | None = None
    for path in directed_lock["paths"]:
        segment_ids = list(path["locked_segment_ids"])
        refinement_geodesic = 0.0
        refinement_planimetric = 0.0
        path_replacements: list[str] = []
        for segment_id in segment_ids:
            for replacement in replacements_by_segment.get(segment_id, []):
                refinement_geodesic += (
                    replacement["registered"]["geodesic_m"]
                    - replacement["chord"]["geodesic_m"]
                )
                refinement_planimetric += (
                    replacement["registered"]["planimetric_m"]
                    - replacement["chord"]["planimetric_m"]
                )
                path_replacements.append(replacement["site_id"])
        excluded = [
            entry["segment_id"] for entry in path["excluded_connector_segments"]
        ]
        missing = [
            segment_id
            for segment_id in excluded
            if segment_id not in connectors_by_id
        ]
        record: dict[str, Any] = {
            "path_id": path["path_id"],
            "role": path["role"],
            "corridor_anchor_to_anchor_geodesic_m": path["total_geodesic_m"],
            "corridor_anchor_to_anchor_planimetric_m": path["total_planimetric_m"],
            "span_refinement_geodesic_m": round(refinement_geodesic, 3),
            "span_refinement_planimetric_m": round(refinement_planimetric, 3),
            "replaced_span_site_ids": sorted(path_replacements),
            "connector_segment_ids": excluded,
        }
        if missing:
            record["published"] = False
            record["reason"] = (
                "Endpoint connector(s) "
                + ", ".join(sorted(missing))
                + " are not yet authored; the portal-to-portal figure for "
                "this path stays unpublished."
            )
        else:
            connector_geodesic = sum(
                connectors_by_id[segment_id]["lengths"]["geodesic_m"]
                for segment_id in excluded
            )
            connector_planimetric = sum(
                connectors_by_id[segment_id]["lengths"]["planimetric_m"]
                for segment_id in excluded
            )
            geodesic_total = round(
                path["total_geodesic_m"] + refinement_geodesic + connector_geodesic,
                3,
            )
            planimetric_total = round(
                path["total_planimetric_m"]
                + refinement_planimetric
                + connector_planimetric,
                3,
            )
            record["published"] = True
            record["connector_geodesic_m"] = {
                segment_id: connectors_by_id[segment_id]["lengths"]["geodesic_m"]
                for segment_id in excluded
            }
            record["portal_to_portal_geodesic_m"] = geodesic_total
            record["portal_to_portal_miles"] = round(
                geodesic_total / METRES_PER_MILE, 2
            )
            record["portal_to_portal_planimetric_m"] = planimetric_total
        paths.append(record)
        if path["role"] == "canonical":
            canonical = record
    if canonical is None or not canonical.get("published"):
        raise ValueError(
            "The canonical path's portal-to-portal run length did not "
            "publish; the ADR-0024 figure is the point of this stage."
        )
    authoritative = directed_lock["corridor"]["authoritative_distance"]
    return {
        "decision": "ADR-0024",
        "scope": "portal_to_portal_westbound",
        "from_portal": "nyc-east-31st-public-road-portal",
        "to_portal": "redondo-portofino-way-public-road-portal",
        "basis": (
            "GRS80 geodesic over the locked corridor anchor-to-anchor "
            "traversal with each traversed NHS fill chord's contribution "
            "replaced by its seam-registered conflated span, plus the two "
            "authored ADR-0018 endpoint connectors joining the locked "
            "portals to the corridor ends."
        ),
        "canonical_portal_to_portal_miles": canonical["portal_to_portal_miles"],
        "canonical_portal_to_portal_geodesic_m": canonical[
            "portal_to_portal_geodesic_m"
        ],
        "anchor_to_anchor_reference": {
            "geodesic_m": authoritative["geodesic_length_m"],
            "miles": authoritative["geodesic_length_miles"],
            "relationship": (
                "portal-to-portal = the anchor-to-anchor corridor figure "
                "plus the recorded span refinement plus the two authored "
                "connectors; every component is recorded per path."
            ),
        },
        "precision": {
            "corridor": "locked source-centerline fidelity",
            "connectors": (
                "authored-waypoint fidelity per the endpoint connector "
                "lock's declared class; the connector contribution is "
                "recorded per connector and refines when connector source "
                "geometry is acquired"
            ),
        },
        "junction_backtrack_note": authoritative["junction_backtrack_note"],
        "paths": paths,
    }


def _carriageway_summary(
    segments_payload: Sequence[dict[str, Any]],
    backtracks: Sequence[dict[str, Any]],
    span_replacements: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    corner_by_class: dict[str, int] = {}
    reversal_by_class: dict[str, int] = {}
    gates_passed = 0
    westbound_length = 0.0
    eastbound_length = 0.0
    chain_length = 0.0
    element_count = 0
    min_separation: float | None = None
    for segment in segments_payload:
        element_count += segment["element_count"]
        westbound_length += segment["westbound"]["length_m"]
        eastbound_length += segment["eastbound"]["length_m"]
        chain_length += segment["chain"]["length_m"]
        for site in segment["corner_sites"]:
            corner_by_class[site["corner_class"]] = (
                corner_by_class.get(site["corner_class"], 0) + 1
            )
        for record in segment["planimetric_conditioning"]:
            reversal_by_class[record["reversal_class"]] = (
                reversal_by_class.get(record["reversal_class"], 0) + 1
            )
        for gate in segment["gates"].values():
            if gate["passed"]:
                gates_passed += 1
        separation = segment["gates"]["reciprocal_separation"]["measured"]
        if min_separation is None or separation < min_separation:
            min_separation = separation
    replaced_span_length = 0.0
    for replacement in span_replacements:
        replaced_span_length += replacement["registered"]["planimetric_m"]
        for gate in replacement["gates"].values():
            if gate["passed"]:
                gates_passed += 1
    return {
        "segment_count": len(segments_payload),
        "element_count": element_count,
        "chain_length_m": round(chain_length, 3),
        "westbound_length_m": round(westbound_length, 3),
        "westbound_miles": round(westbound_length / 1609.344, 3),
        "eastbound_length_m": round(eastbound_length, 3),
        "corner_site_count": sum(corner_by_class.values()),
        "corner_sites_by_class": dict(sorted(corner_by_class.items())),
        "planimetric_conditioning_count": sum(reversal_by_class.values()),
        "planimetric_conditioning_by_class": dict(sorted(reversal_by_class.items())),
        "min_reciprocal_separation_m": min_separation,
        "junction_backtrack_count": len(backtracks),
        "span_replacement_count": len(span_replacements),
        "replaced_span_length_m": round(replaced_span_length, 3),
        "gates_passed": gates_passed,
        "gates_failed": 0,
    }


def derive_continental_westbound_carriageway(
    conditioned_lock_path: Path,
    elevation_lock_path: Path,
    dem_lock_path: Path,
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    connector_lock_path: Path,
    catalog_path: Path,
    cache_directory: Path,
    fill_cache_directory: Path,
    carriageway_cache_directory: Path,
    output_path: Path,
    *,
    derived_at: str | None = None,
) -> dict[str, Any]:
    """Derive the reciprocal directed westbound carriageway model (ADR-0014).

    The directed walk is re-derived through the locked machinery and refused
    unless it reproduces the committed directed route lock; each segment's
    element chain is conditioned of reversal-class digitization artifacts
    (every excision recorded), censused for corner-class heading exceptions,
    and offset into the reciprocal westbound/eastbound pair through the
    ADR-0018 gates. The schema-2 revision replaces each traversed NHS fill
    chord with its seam-registered conflated span (verified against the
    conflation lock's geometry digest, conditioned vertically per ADR-0017),
    integrates the authored endpoint connector lock, and publishes the
    ADR-0024 portal-to-portal run length. Bulk geometry stays in the ignored
    cache; the lock carries the derivation, measurements, gate results, and
    digests.
    """
    conditioned_lock = validate_continental_conditioned_profile(
        conditioned_lock_path,
        elevation_lock_path,
        dem_lock_path,
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    directed_lock = load_json(directed_lock_path)
    selection = load_json(selection_path)
    route_lock = validate_continental_route_lock(
        route_lock_path, catalog_path, selection_path
    )
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    edge_lock = validate_continental_edge_path_lock(
        edge_path_lock_path,
        transfer_lock_path,
        policy_path,
        selection_path,
        route_lock_path,
        catalog_path,
    )
    fill_lock = validate_continental_nhs_fill_lock(
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    overlay_lock = validate_continental_reconstruction_overlays(
        overlay_lock_path,
        disposition_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        catalog_path,
    )
    conflation_lock = validate_continental_nhs_conflation(
        conflation_lock_path,
        fill_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        catalog_path,
    )
    connector_payload = validate_continental_endpoint_connectors(
        connector_lock_path,
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    elevation_lock = load_json(elevation_lock_path)
    elevation_by_id = {
        segment["segment_id"]: segment for segment in elevation_lock["segments"]
    }
    conditioned_by_id = {
        segment["segment_id"]: segment for segment in conditioned_lock["segments"]
    }
    timestamp = derived_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    cache_root = (
        cache_directory / route_lock["nhpn"]["service"]["canonical_metadata_sha256"]
    )
    fill_root = (
        fill_cache_directory
        / fill_lock["nhs"]["service"]["canonical_metadata_sha256"]
    )
    tolerance = float(edge_lock["endpoint_snap_tolerance_m"])
    anchor_limit = float(edge_lock["anchor_snap_limit_m"])
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    edge_by_id = {entry["segment_id"]: entry for entry in edge_lock["segments"]}
    chain_by_id = {
        entry["segment_id"]: entry
        for entry in overlay_lock["chain_connectivity"]["segments"]
    }
    conflation_site_by_id = {
        site["site_id"]: site for site in conflation_lock["sites"]
    }
    fills_by_segment: dict[str, list[dict[str, Any]]] = {}
    for site in fill_lock["sites"]:
        fills_by_segment.setdefault(site["segment_id"], []).append(site)
    overlays_by_segment: dict[str, list[dict[str, Any]]] = {}
    overlay_lines_by_segment: dict[str, list[LineString]] = {}
    for overlay in overlay_lock["overlays"]:
        overlays_by_segment.setdefault(overlay["segment_id"], []).append(
            {
                "site_id": overlay["site_id"],
                "overlay_id": overlay["overlay_id"],
                "from_coordinate": overlay["boundary"]["from_coordinate"],
                "to_coordinate": overlay["boundary"]["to_coordinate"],
                "separation_m": overlay["boundary"]["length_m"],
                "geometry": overlay["geometry"],
            }
        )
        overlay_lines_by_segment.setdefault(overlay["segment_id"], []).append(
            LineString(
                [
                    forward.transform(point[0], point[1])
                    for point in overlay["geometry"]["coordinates"]
                ]
            )
        )
    locked_record_by_id = {
        record["segment_id"]: record for record in directed_lock["segments"]
    }
    backtrack_junctions = _directed_backtrack_junctions(directed_lock)
    tail_backtrack = {
        junction["from_segment_id"]: float(junction["backtrack_length_m"])
        for junction in backtrack_junctions
    }
    head_backtrack = {
        junction["to_segment_id"]: float(junction["backtrack_length_m"])
        for junction in backtrack_junctions
    }

    segments_payload: list[dict[str, Any]] = []
    span_replacements: list[dict[str, Any]] = []
    chains_by_segment: dict[str, list[tuple[float, float]]] = {}
    carriageway_cache_directory.mkdir(parents=True, exist_ok=True)
    for segment in selection["segments"]:
        segment_id = segment["id"]
        if segment_id not in locked_record_by_id:
            continue
        lines = _segment_locked_lines(route_lock, segment_id, cache_root)
        geometries: list[LineString] = []
        record = _derive_directed_segment(
            segment,
            edge_by_id[segment_id],
            chain_by_id.get(segment_id),
            lines,
            fills_by_segment.get(segment_id, []),
            overlays_by_segment.get(segment_id, []),
            conflation_site_by_id,
            forward.transform(
                transfer_by_id[segment["from"]]["coordinate"]["longitude"],
                transfer_by_id[segment["from"]]["coordinate"]["latitude"],
            ),
            forward.transform(
                transfer_by_id[segment["to"]]["coordinate"]["longitude"],
                transfer_by_id[segment["to"]]["coordinate"]["latitude"],
            ),
            tolerance,
            anchor_limit,
            forward,
            inverse,
            geometry_sink=geometries,
        )
        locked_record = locked_record_by_id[segment_id]
        if canonical_sha256(record) != canonical_sha256(locked_record):
            raise ValueError(
                f"Directed walk for '{segment_id}' does not reproduce the "
                "committed directed route lock; refusing to build a "
                "carriageway for a different route."
            )
        # Conflated-span replacement: every traversed fill chord's geometry
        # is swapped for its seam-registered conflation span before the
        # chain is built, so the carriageway rides source-asserted road
        # geometry across the NHPN voids instead of chord-class fills.
        fill_site_by_id = {
            site["site_id"]: site for site in fills_by_segment.get(segment_id, [])
        }
        segment_span_lines: list[LineString] = []
        for element_index, element in enumerate(record["elements"]):
            if element["kind"] != "nhs_fill_chord":
                continue
            site = fill_site_by_id[element["site_id"]]
            conflation_site = conflation_site_by_id[element["site_id"]]
            registered_line, span_facts = _registered_conflation_span(
                site, conflation_site, fill_root, forward
            )
            registered_coordinates = list(registered_line.coords)
            registered_planimetric = round(
                _polyline_length(registered_coordinates), 3
            )
            registered_geodesic = round(
                _geodesic_line_length_m(
                    [inverse.transform(x, y) for x, y in registered_coordinates]
                ),
                3,
            )
            interval_to = element["cumulative_geodesic_m"]
            interval_from = interval_to - element["geodesic_length_m"]
            vertical = _span_vertical_context(
                elevation_by_id[segment_id],
                conditioned_by_id[segment_id],
                interval_from,
                interval_to,
                registered_geodesic,
            )
            length_change_bound = round(
                span_facts["seam_registration"]["from_offset_m"]
                + span_facts["seam_registration"]["to_offset_m"]
                + 0.01,
                3,
            )
            gates = {
                "span_digest_agreement": _carriageway_gate(
                    span_facts["span"]["geometry_sha256"],
                    "reassembled span reproduces the conflation lock digest",
                    True,
                ),
                "seam_registration": _carriageway_gate(
                    span_facts["seam_registration"]["offset_agreement_delta_m"],
                    CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M,
                    True,
                ),
                "registration_length_change": _carriageway_gate(
                    round(
                        abs(
                            registered_planimetric
                            - span_facts["span"]["geometry_length_m"]
                        ),
                        3,
                    ),
                    length_change_bound,
                    abs(
                        registered_planimetric
                        - span_facts["span"]["geometry_length_m"]
                    )
                    <= length_change_bound,
                ),
                "span_grade": _carriageway_gate(
                    vertical["span_grade_percent"],
                    CONDITIONING_SUSTAINED_BOUND_PERCENT,
                    abs(vertical["span_grade_percent"])
                    <= CONDITIONING_SUSTAINED_BOUND_PERCENT,
                ),
            }
            failed_span_gates = {
                name for name, gate in gates.items() if not gate["passed"]
            }
            if failed_span_gates:
                raise ValueError(
                    json.dumps(
                        {
                            "refusal": "span replacement gates failed",
                            "site_id": element["site_id"],
                            "failed_gates": sorted(failed_span_gates),
                            "gates": gates,
                        },
                        sort_keys=True,
                    )
                )
            geometries[element_index] = (
                LineString(registered_coordinates[::-1])
                if element["reversed_for_travel"]
                else registered_line
            )
            segment_span_lines.append(registered_line)
            span_replacements.append(
                {
                    "site_id": element["site_id"],
                    "segment_id": segment_id,
                    "element_index": element_index,
                    "nhs_route": dict(element["nhs_route"]),
                    "reversed_for_travel": element["reversed_for_travel"],
                    "chord": {
                        "planimetric_m": element["length_m"],
                        "geodesic_m": element["geodesic_length_m"],
                    },
                    **span_facts,
                    "registered": {
                        "planimetric_m": registered_planimetric,
                        "geodesic_m": registered_geodesic,
                        "vertex_count": len(registered_coordinates),
                    },
                    "deltas": {
                        "registered_minus_chord_m": round(
                            registered_planimetric - element["length_m"], 3
                        ),
                        "span_minus_chord_m": round(
                            span_facts["span"]["geometry_length_m"]
                            - element["length_m"],
                            3,
                        ),
                    },
                    "vertical_context": vertical,
                    "gates": gates,
                }
            )
        overlay_lines = overlay_lines_by_segment.get(segment_id, [])
        coordinates, joint_facts = _build_segment_chain(segment_id, geometries)
        raw_length = _polyline_length(coordinates)
        coordinates, excisions = _excise_reversal_apexes(
            segment_id, coordinates, overlay_lines, inverse
        )
        chain_length = _polyline_length(coordinates)
        corner_sites = _carriageway_corner_sites(
            segment_id,
            coordinates,
            overlay_lines,
            tail_backtrack.get(segment_id, 0.0),
            head_backtrack.get(segment_id, 0.0),
            inverse,
            span_lines=segment_span_lines,
        )
        chain_line = LineString(coordinates)
        westbound = _offset_carriageway(segment_id, chain_line, "westbound")
        eastbound = _offset_carriageway(segment_id, chain_line, "eastbound")
        westbound_length = _polyline_length(westbound)
        eastbound_length = _polyline_length(eastbound)
        separation = LineString(westbound).distance(LineString(eastbound))
        length_ratio = max(
            abs(westbound_length - chain_length),
            abs(eastbound_length - chain_length),
        ) / chain_length
        gates = {
            "chain_continuity": _carriageway_gate(
                joint_facts["max_joint_gap_m"],
                CARRIAGEWAY_JOINT_GAP_LIMIT_M,
                joint_facts["max_joint_gap_m"] <= CARRIAGEWAY_JOINT_GAP_LIMIT_M,
            ),
            "reversal_excision": _carriageway_gate(
                len(excisions),
                CARRIAGEWAY_MAX_REVERSAL_REMOVALS,
                len(excisions) <= CARRIAGEWAY_MAX_REVERSAL_REMOVALS,
            ),
            "heading_discipline": _carriageway_gate(
                max(
                    (site["peak_turn_deg"] for site in corner_sites),
                    default=0.0,
                ),
                CARRIAGEWAY_REVERSAL_THRESHOLD_DEG,
                True,
            ),
            "self_intersection": _carriageway_gate(
                {"westbound_simple": True, "eastbound_simple": True},
                "both offsets single simple LineStrings",
                True,
            ),
            "station_monotonicity": _carriageway_gate(
                {
                    "westbound_vertex_count": len(westbound),
                    "eastbound_vertex_count": len(eastbound),
                },
                "strictly increasing station at every vertex",
                True,
            ),
            "reciprocal_separation": _carriageway_gate(
                round(separation, 3),
                CARRIAGEWAY_MIN_SEPARATION_M,
                separation >= CARRIAGEWAY_MIN_SEPARATION_M,
            ),
            "length_agreement": _carriageway_gate(
                round(length_ratio, 9),
                CARRIAGEWAY_LENGTH_AGREEMENT_RATIO,
                length_ratio <= CARRIAGEWAY_LENGTH_AGREEMENT_RATIO,
            ),
        }
        failed = {name for name, gate in gates.items() if not gate["passed"]}
        if failed:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "carriageway gates failed",
                        "segment_id": segment_id,
                        "failed_gates": sorted(failed),
                        "gates": gates,
                    },
                    sort_keys=True,
                )
            )
        cache_payload = {
            "schema_version": 1,
            "segment_id": segment_id,
            "metric_crs": "EPSG:5070",
            "offset_m": CARRIAGEWAY_OFFSET_M,
            "chain_coordinates": [
                [
                    round(x, CARRIAGEWAY_GEOMETRY_DECIMALS),
                    round(y, CARRIAGEWAY_GEOMETRY_DECIMALS),
                ]
                for x, y in coordinates
            ],
            "westbound_coordinates": [[x, y] for x, y in westbound],
            "eastbound_coordinates": [[x, y] for x, y in eastbound],
        }
        cache_path = carriageway_cache_directory / f"{segment_id}.json"
        cache_path.write_text(
            json.dumps(cache_payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        segments_payload.append(
            {
                "segment_id": segment_id,
                "element_count": locked_record["element_count"],
                "chain": {
                    "vertex_count": len(coordinates),
                    "length_m": round(chain_length, 3),
                    "raw_length_m": round(raw_length, 3),
                    "max_joint_gap_m": joint_facts["max_joint_gap_m"],
                    "bridged_joint_count": joint_facts["bridged_joint_count"],
                },
                "planimetric_conditioning": excisions,
                "corner_sites": corner_sites,
                "westbound": {
                    "length_m": round(westbound_length, 3),
                    "vertex_count": len(westbound),
                    "geometry_sha256": canonical_sha256(
                        cache_payload["westbound_coordinates"]
                    ),
                },
                "eastbound": {
                    "length_m": round(eastbound_length, 3),
                    "vertex_count": len(eastbound),
                    "geometry_sha256": canonical_sha256(
                        cache_payload["eastbound_coordinates"]
                    ),
                },
                "gates": gates,
            }
        )
        chains_by_segment[segment_id] = coordinates

    backtracks_payload = [
        _carriageway_backtrack_record(
            junction,
            chains_by_segment[junction["from_segment_id"]],
            chains_by_segment[junction["to_segment_id"]],
        )
        for junction in backtrack_junctions
    ]
    overlay_corner_constraints = {
        overlay["overlay_id"]: overlay["gates"]["heading_continuity"]["measured"][
            "end_tangent_deviation_degrees"
        ]
        for overlay in overlay_lock["overlays"]
    }
    summary = _carriageway_summary(
        segments_payload, backtracks_payload, span_replacements
    )
    run_length = _run_length_records(
        directed_lock, connector_payload, span_replacements
    )
    grade_gate = _carriageway_gate(
        conditioned_lock["summary"]["max_sustained_grade"],
        CONDITIONING_SUSTAINED_BOUND_PERCENT,
        abs(conditioned_lock["summary"]["max_sustained_grade"]["grade_percent"])
        <= CONDITIONING_SUSTAINED_BOUND_PERCENT,
    )
    payload = {
        "schema_version": 2,
        "supersedes": dict(SUPERSEDED_WESTBOUND_CARRIAGEWAY_V1),
        "status": WESTBOUND_CARRIAGEWAY_STATUS,
        "decision": "ADR-0014",
        "reconstruction_decision": "ADR-0018",
        "route_decision": selection["decision"],
        "derived_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "endpoint_connector_lock_sha256": compute_sha256(connector_lock_path),
        "dem_product_lock_sha256": compute_sha256(dem_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
        "corridor_elevation_lock_sha256": compute_sha256(elevation_lock_path),
        "conditioned_profile_lock_sha256": compute_sha256(conditioned_lock_path),
        "model": dict(CARRIAGEWAY_MODEL),
        "source_policy": dict(CARRIAGEWAY_SOURCE_POLICY),
        "westbound_selection": {
            "carriageway_direction_claimed": True,
            "basis": (
                "The directed route lock fixes anchor-to-anchor travel; this "
                "ADR-0014 reconstruction stage constructs the reciprocal "
                "offset pair over that locked sequence and claims the "
                "westbound carriageway as the travel roadway. NHPN itself "
                "still asserts no per-carriageway direction (the directed "
                "lock's facility census stands)."
            ),
        },
        "deferred_gates": dict(CARRIAGEWAY_DEFERRED_GATES),
        "grade_gate": {
            **grade_gate,
            "source": "conditioned-profile-lock",
        },
        "overlay_corner_constraints": overlay_corner_constraints,
        "segment_count": len(segments_payload),
        "segments": segments_payload,
        "segments_sha256": canonical_sha256(segments_payload),
        "span_replacements": span_replacements,
        "span_replacements_sha256": canonical_sha256(span_replacements),
        "junction_backtracks": backtracks_payload,
        "run_length": run_length,
        "summary": summary,
        "next_stage": WESTBOUND_CARRIAGEWAY_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_westbound_carriageway(
    carriageway_lock_path: Path,
    conditioned_lock_path: Path,
    elevation_lock_path: Path,
    dem_lock_path: Path,
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    connector_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the westbound carriageway lock without caches or network.

    Cache-independent: every recorded measurement is held to the module's
    locked thresholds, every gate must pass, the corner census must include
    the overlay-corner adjudication of the Quad Cities constraint and no
    reversal-class turn, the junction backtracks must match the directed
    lock's records with reciprocity proven, the span replacements must cite
    exactly the directed lock's traversed fill chords with the conflation
    lock's digests and seam offsets and a vertical context recomputed from
    the committed profile locks, the run length must reproduce from the
    directed, span, and connector records, and the summary must reproduce
    from the committed segments.
    """
    payload = load_json(carriageway_lock_path)
    if payload.get("schema_version") != 2:
        raise ValueError("Westbound carriageway lock schema_version must be 2.")
    if payload.get("supersedes") != SUPERSEDED_WESTBOUND_CARRIAGEWAY_V1:
        raise ValueError(
            "Westbound carriageway lock must record the superseded v1 lock "
            "verbatim."
        )
    if payload.get("status") != WESTBOUND_CARRIAGEWAY_STATUS:
        raise ValueError("Westbound carriageway lock has an unsupported status.")
    if payload.get("decision") != "ADR-0014":
        raise ValueError("Westbound carriageway lock does not cite ADR-0014.")
    if payload.get("reconstruction_decision") != "ADR-0018":
        raise ValueError("Westbound carriageway lock does not cite ADR-0018.")
    conditioned_lock = validate_continental_conditioned_profile(
        conditioned_lock_path,
        elevation_lock_path,
        dem_lock_path,
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    directed_lock = load_json(directed_lock_path)
    overlay_lock = load_json(overlay_lock_path)
    conflation_lock = load_json(conflation_lock_path)
    elevation_lock = load_json(elevation_lock_path)
    connector_payload = validate_continental_endpoint_connectors(
        connector_lock_path,
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "endpoint_connector_lock_sha256": compute_sha256(connector_lock_path),
        "dem_product_lock_sha256": compute_sha256(dem_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
        "corridor_elevation_lock_sha256": compute_sha256(elevation_lock_path),
        "conditioned_profile_lock_sha256": compute_sha256(conditioned_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Westbound carriageway lock input hash drifted.")
    if payload.get("model") != CARRIAGEWAY_MODEL:
        raise ValueError("Westbound carriageway lock model drifted.")
    if payload.get("source_policy") != CARRIAGEWAY_SOURCE_POLICY:
        raise ValueError("Westbound carriageway lock source policy drifted.")
    if payload.get("deferred_gates") != CARRIAGEWAY_DEFERRED_GATES:
        raise ValueError("Westbound carriageway lock deferred gates drifted.")
    claim = payload.get("westbound_selection", {})
    if claim.get("carriageway_direction_claimed") is not True or not claim.get(
        "basis"
    ):
        raise ValueError(
            "Westbound carriageway lock must claim the carriageway direction "
            "with its basis."
        )
    directed_claim = directed_lock["westbound_selection"][
        "carriageway_direction_claimed"
    ]
    if directed_claim is not False:
        raise ValueError(
            "The directed route lock may not claim carriageway direction; "
            "that claim belongs to this reconstruction stage."
        )
    grade_gate = payload.get("grade_gate", {})
    sustained = conditioned_lock["summary"]["max_sustained_grade"]
    if (
        grade_gate.get("measured") != sustained
        or grade_gate.get("threshold") != CONDITIONING_SUSTAINED_BOUND_PERCENT
        or grade_gate.get("passed")
        is not (abs(sustained["grade_percent"]) <= CONDITIONING_SUSTAINED_BOUND_PERCENT)
        or grade_gate.get("source") != "conditioned-profile-lock"
        or not grade_gate.get("passed")
    ):
        raise ValueError(
            "Westbound carriageway grade gate does not adjudicate the "
            "conditioned profile."
        )
    expected_constraints = {
        overlay["overlay_id"]: overlay["gates"]["heading_continuity"]["measured"][
            "end_tangent_deviation_degrees"
        ]
        for overlay in overlay_lock["overlays"]
    }
    if payload.get("overlay_corner_constraints") != expected_constraints:
        raise ValueError(
            "Westbound carriageway lock overlay corner constraints drifted."
        )
    segments = payload.get("segments", [])
    directed_by_id = {
        record["segment_id"]: record for record in directed_lock["segments"]
    }
    if payload.get("segment_count") != len(segments) or [
        segment.get("segment_id") for segment in segments
    ] != [record["segment_id"] for record in directed_lock["segments"]]:
        raise ValueError(
            "Westbound carriageway lock does not cover exactly the directed "
            "segments in order."
        )
    overlay_segments = {
        overlay["segment_id"] for overlay in overlay_lock["overlays"]
    }
    span_replacements = payload.get("span_replacements", [])
    replaced_segments = {
        replacement.get("segment_id") for replacement in span_replacements
    }
    corner_corners = 0
    for segment in segments:
        segment_id = segment["segment_id"]
        if segment.get("element_count") != directed_by_id[segment_id][
            "element_count"
        ]:
            raise ValueError(
                f"Carriageway segment '{segment_id}' element count drifted "
                "from the directed lock."
            )
        chain = segment.get("chain", {})
        if (
            not isinstance(chain.get("vertex_count"), int)
            or chain["vertex_count"] < 2
            or not isinstance(chain.get("length_m"), int | float)
            or chain["length_m"] <= 0
        ):
            raise ValueError(
                f"Carriageway segment '{segment_id}' chain facts are invalid."
            )
        gates = segment.get("gates", {})
        expected_gate_names = {
            "chain_continuity",
            "reversal_excision",
            "heading_discipline",
            "self_intersection",
            "station_monotonicity",
            "reciprocal_separation",
            "length_agreement",
        }
        if set(gates) != expected_gate_names:
            raise ValueError(
                f"Carriageway segment '{segment_id}' gate battery is incomplete."
            )
        for name, gate in gates.items():
            if gate.get("passed") is not True:
                raise ValueError(
                    f"Carriageway segment '{segment_id}' gate '{name}' did "
                    "not pass."
                )
        if (
            gates["chain_continuity"]["threshold"] != CARRIAGEWAY_JOINT_GAP_LIMIT_M
            or gates["chain_continuity"]["measured"]
            > CARRIAGEWAY_JOINT_GAP_LIMIT_M
            or gates["chain_continuity"]["measured"] != chain.get("max_joint_gap_m")
        ):
            raise ValueError(
                f"Carriageway segment '{segment_id}' chain continuity gate "
                "drifted."
            )
        excisions = segment.get("planimetric_conditioning", [])
        if (
            gates["reversal_excision"]["threshold"]
            != CARRIAGEWAY_MAX_REVERSAL_REMOVALS
            or gates["reversal_excision"]["measured"] != len(excisions)
            or len(excisions) > CARRIAGEWAY_MAX_REVERSAL_REMOVALS
        ):
            raise ValueError(
                f"Carriageway segment '{segment_id}' reversal excision gate "
                "drifted."
            )
        for excision in excisions:
            if excision.get("reversal_class") not in CARRIAGEWAY_REVERSAL_CLASSES:
                raise ValueError(
                    f"Carriageway segment '{segment_id}' carries an unknown "
                    "reversal class."
                )
            if (
                not isinstance(excision.get("turn_deg"), int | float)
                or excision["turn_deg"] <= CARRIAGEWAY_REVERSAL_THRESHOLD_DEG
            ):
                raise ValueError(
                    f"Carriageway segment '{segment_id}' excised a "
                    "non-reversal turn."
                )
        corner_sites = segment.get("corner_sites", [])
        if gates["heading_discipline"]["measured"] != max(
            (site["peak_turn_deg"] for site in corner_sites), default=0.0
        ) or gates["heading_discipline"]["threshold"] != (
            CARRIAGEWAY_REVERSAL_THRESHOLD_DEG
        ):
            raise ValueError(
                f"Carriageway segment '{segment_id}' heading gate drifted."
            )
        for site in corner_sites:
            if site.get("corner_class") not in CARRIAGEWAY_CORNER_CLASSES:
                raise ValueError(
                    f"Carriageway segment '{segment_id}' carries an unknown "
                    "corner class."
                )
            if (
                not isinstance(site.get("peak_turn_deg"), int | float)
                or site["peak_turn_deg"] <= CARRIAGEWAY_CORNER_THRESHOLD_DEG
                or site["peak_turn_deg"] > CARRIAGEWAY_REVERSAL_THRESHOLD_DEG
            ):
                raise ValueError(
                    f"Carriageway segment '{segment_id}' corner site "
                    "measurement is outside the corner class."
                )
            if site["corner_class"] == "conflated_span_corner" and (
                segment_id not in replaced_segments
            ):
                raise ValueError(
                    f"Carriageway segment '{segment_id}' claims a "
                    "conflated-span corner without a span replacement."
                )
            if site["corner_class"] == "overlay_corner":
                corner_corners += 1
                if segment_id not in overlay_segments:
                    raise ValueError(
                        f"Carriageway segment '{segment_id}' claims an "
                        "overlay corner without an overlay."
                    )
                deviations = [
                    expected_constraints[overlay["overlay_id"]]
                    for overlay in overlay_lock["overlays"]
                    if overlay["segment_id"] == segment_id
                ]
                if not any(
                    abs(site["turn_sum_deg"] - deviation)
                    <= CARRIAGEWAY_OVERLAY_CORNER_TOLERANCE_DEG
                    for deviation in deviations
                ):
                    raise ValueError(
                        f"Carriageway segment '{segment_id}' overlay corner "
                        "does not honor the overlay lock's recorded corner "
                        "constraint."
                    )
        if (
            gates["reciprocal_separation"]["threshold"]
            != CARRIAGEWAY_MIN_SEPARATION_M
            or gates["reciprocal_separation"]["measured"]
            < CARRIAGEWAY_MIN_SEPARATION_M
        ):
            raise ValueError(
                f"Carriageway segment '{segment_id}' separation gate drifted."
            )
        if (
            gates["length_agreement"]["threshold"]
            != CARRIAGEWAY_LENGTH_AGREEMENT_RATIO
            or gates["length_agreement"]["measured"]
            > CARRIAGEWAY_LENGTH_AGREEMENT_RATIO
        ):
            raise ValueError(
                f"Carriageway segment '{segment_id}' length agreement gate "
                "drifted."
            )
        for side in ("westbound", "eastbound"):
            facts = segment.get(side, {})
            if (
                not isinstance(facts.get("length_m"), int | float)
                or facts["length_m"] <= 0
                or not isinstance(facts.get("vertex_count"), int)
                or facts["vertex_count"] < 2
                or not SHA256_PATTERN.fullmatch(str(facts.get("geometry_sha256", "")))
            ):
                raise ValueError(
                    f"Carriageway segment '{segment_id}' {side} record is "
                    "invalid."
                )
            if (
                abs(facts["length_m"] - chain["length_m"]) / chain["length_m"]
                > CARRIAGEWAY_LENGTH_AGREEMENT_RATIO
            ):
                raise ValueError(
                    f"Carriageway segment '{segment_id}' {side} length "
                    "disagrees with its chain."
                )
    quad_cities_overlay = "i80-new-jersey-to-big-springs--component-01-02--authored-overlay"
    if quad_cities_overlay in expected_constraints and corner_corners < 1:
        raise ValueError(
            "The Quad Cities overlay corner constraint has no adjudicating "
            "corner site."
        )
    if payload.get("segments_sha256") != canonical_sha256(segments):
        raise ValueError("Westbound carriageway lock segment digest drifted.")
    backtracks = payload.get("junction_backtracks", [])
    expected_junctions = _directed_backtrack_junctions(directed_lock)
    if len(backtracks) != len(expected_junctions):
        raise ValueError(
            "Westbound carriageway lock does not cover exactly the directed "
            "lock's junction backtracks."
        )
    for backtrack, junction in zip(backtracks, expected_junctions, strict=True):
        if (
            backtrack.get("anchor_id") != junction["anchor_id"]
            or backtrack.get("from_segment_id") != junction["from_segment_id"]
            or backtrack.get("to_segment_id") != junction["to_segment_id"]
            or backtrack.get("backtrack_element_count")
            != junction["backtrack_element_count"]
            or backtrack.get("locked_backtrack_length_m")
            != junction["backtrack_length_m"]
        ):
            raise ValueError(
                "Westbound carriageway backtrack record drifted from the "
                "directed lock."
            )
        if (
            abs(
                backtrack.get("mirrored_length_m", 0.0)
                - junction["backtrack_length_m"]
            )
            > CARRIAGEWAY_BACKTRACK_LENGTH_TOLERANCE_M
        ):
            raise ValueError(
                "Westbound carriageway backtrack mirrored length drifted."
            )
        if (
            backtrack.get("reciprocity_gap_m", 1.0)
            > CARRIAGEWAY_BACKTRACK_MIRROR_TOLERANCE_M
        ):
            raise ValueError(
                "Westbound carriageway backtrack reciprocity gap exceeds the "
                "tolerance."
            )
        if (
            backtrack.get("westbound_separation_m", 0.0)
            < CARRIAGEWAY_MIN_SEPARATION_M
        ):
            raise ValueError(
                "Westbound carriageway backtrack separation violates the "
                "reciprocal bound."
            )
    # Span replacements: exactly the directed lock's traversed fill chords,
    # carrying the conflation lock's digests and seam offsets, with a
    # vertical context recomputed from the committed profile locks.
    directed_fill_elements: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for record in directed_lock["segments"]:
        for index, element in enumerate(record["elements"]):
            if element["kind"] == "nhs_fill_chord":
                directed_fill_elements[
                    (record["segment_id"], element["site_id"])
                ] = (index, element)
    recorded_keys = {
        (replacement.get("segment_id"), replacement.get("site_id"))
        for replacement in span_replacements
    }
    if recorded_keys != set(directed_fill_elements) or len(span_replacements) != len(
        directed_fill_elements
    ):
        raise ValueError(
            "Westbound carriageway span replacements do not cover exactly "
            "the directed lock's traversed fill chords."
        )
    conflation_by_site = {
        site["site_id"]: site for site in conflation_lock["sites"]
    }
    elevation_by_id = {
        segment["segment_id"]: segment for segment in elevation_lock["segments"]
    }
    conditioned_by_id = {
        segment["segment_id"]: segment
        for segment in conditioned_lock["segments"]
    }
    for replacement in span_replacements:
        key = (replacement["segment_id"], replacement["site_id"])
        element_index, element = directed_fill_elements[key]
        if (
            replacement.get("element_index") != element_index
            or replacement.get("reversed_for_travel")
            != element["reversed_for_travel"]
            or replacement.get("nhs_route") != element["nhs_route"]
        ):
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' drifted from "
                "the directed lock's fill element."
            )
        chord = replacement.get("chord", {})
        if (
            chord.get("planimetric_m") != element["length_m"]
            or chord.get("geodesic_m") != element["geodesic_length_m"]
        ):
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' chord lengths "
                "drifted from the directed lock."
            )
        conflation_site = conflation_by_site[replacement["site_id"]]
        span_block = conflation_site["span"]
        span = replacement.get("span", {})
        if (
            span.get("geometry_sha256") != span_block["geometry_sha256"]
            or span.get("geometry_length_m") != span_block["geometry_length_m"]
            or span.get("reassembled_digest_verified") is not True
            or span.get("piece_count") != len(span_block["pieces"])
        ):
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' span facts "
                "drifted from the conflation lock."
            )
        offsets_by_side = {
            seam["side"]: seam["nhs"]["seam_offset_m"]
            for seam in conflation_site["seams"]
        }
        registration = replacement.get("seam_registration", {})
        if (
            registration.get("method") != "linear_in_arc_length"
            or registration.get("recorded_seam_offsets_m")
            != {"from": offsets_by_side["from"], "to": offsets_by_side["to"]}
            or not isinstance(registration.get("from_offset_m"), int | float)
            or not isinstance(registration.get("to_offset_m"), int | float)
            or abs(registration["from_offset_m"] - offsets_by_side["from"])
            > CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M
            or abs(registration["to_offset_m"] - offsets_by_side["to"])
            > CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M
            or registration.get("offset_agreement_delta_m", 1.0)
            > CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M
        ):
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' seam "
                "registration disagrees with the conflation lock's recorded "
                "seam offsets."
            )
        registered = replacement.get("registered", {})
        if (
            not isinstance(registered.get("planimetric_m"), int | float)
            or not isinstance(registered.get("geodesic_m"), int | float)
            or not isinstance(registered.get("vertex_count"), int)
            or registered["planimetric_m"] <= 0
            or registered["vertex_count"] < 2
        ):
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' registered "
                "facts are invalid."
            )
        length_change_bound = round(
            registration["from_offset_m"] + registration["to_offset_m"] + 0.01, 3
        )
        length_change = round(
            abs(registered.get("planimetric_m", 0.0) - span_block["geometry_length_m"]),
            3,
        )
        if length_change > length_change_bound:
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' registered "
                "length departs from the span beyond the seam-correction "
                "envelope."
            )
        geodesic_allowance = (
            GEODESIC_PLANIMETRIC_AGREEMENT_RATIO * registered.get("planimetric_m", 0.0)
            + GEODESIC_ROUNDING_ALLOWANCE_M
        )
        if (
            abs(registered.get("geodesic_m", 0.0) - registered.get("planimetric_m", 0.0))
            > geodesic_allowance
        ):
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' registered "
                "geodesic length departs from its planimetric length."
            )
        interval_to = element["cumulative_geodesic_m"]
        interval_from = interval_to - element["geodesic_length_m"]
        expected_vertical = _span_vertical_context(
            elevation_by_id[replacement["segment_id"]],
            conditioned_by_id[replacement["segment_id"]],
            interval_from,
            interval_to,
            registered.get("geodesic_m", 0.0),
        )
        if replacement.get("vertical_context") != expected_vertical:
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' vertical "
                "context does not reproduce from the committed profile locks."
            )
        if abs(expected_vertical["span_grade_percent"]) > (
            CONDITIONING_SUSTAINED_BOUND_PERCENT
        ):
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' grade exceeds "
                "the sustained bound."
            )
        expected_gates = {
            "span_digest_agreement": _carriageway_gate(
                span_block["geometry_sha256"],
                "reassembled span reproduces the conflation lock digest",
                True,
            ),
            "seam_registration": _carriageway_gate(
                registration["offset_agreement_delta_m"],
                CARRIAGEWAY_SPAN_SEAM_TOLERANCE_M,
                True,
            ),
            "registration_length_change": _carriageway_gate(
                length_change,
                length_change_bound,
                True,
            ),
            "span_grade": _carriageway_gate(
                expected_vertical["span_grade_percent"],
                CONDITIONING_SUSTAINED_BOUND_PERCENT,
                True,
            ),
        }
        if replacement.get("gates") != expected_gates:
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' gates do not "
                "reproduce from the recorded measurements."
            )
        deltas = replacement.get("deltas", {})
        if deltas != {
            "registered_minus_chord_m": round(
                registered["planimetric_m"] - element["length_m"], 3
            ),
            "span_minus_chord_m": round(
                span_block["geometry_length_m"] - element["length_m"], 3
            ),
        }:
            raise ValueError(
                f"Span replacement '{replacement['site_id']}' deltas do not "
                "reproduce."
            )
    if payload.get("span_replacements_sha256") != canonical_sha256(
        span_replacements
    ):
        raise ValueError(
            "Westbound carriageway span replacement digest drifted."
        )
    if payload.get("run_length") != _run_length_records(
        directed_lock, connector_payload, span_replacements
    ):
        raise ValueError(
            "Westbound carriageway run length does not reproduce from the "
            "directed, span, and connector records."
        )
    if payload.get("summary") != _carriageway_summary(
        segments, backtracks, span_replacements
    ):
        raise ValueError(
            "Westbound carriageway lock summary does not reproduce from the "
            "committed segments."
        )
    if payload.get("next_stage") != WESTBOUND_CARRIAGEWAY_NEXT_STAGE:
        raise ValueError("Westbound carriageway lock next stage drifted.")
    return payload


# --- ADR-0024 authored endpoint connectors ---------------------------------

ENDPOINT_CONNECTOR_STATUS = "endpoint_connectors_authored_run_length_publishable"

# The connector census reuses the carriageway heading discipline: turns are
# measured on 25 m tangents, corner-class turns are recorded exception sites,
# and reversal-class turns refuse. Urban connector corners (street-grid right
# angles, the Portofino marina corner) are expected recorded sites, never
# hidden.
CONNECTOR_CORNER_CLASS = "connector_corner"
# The recomputed portal-to-anchor straight line must reproduce the directed
# lock's recorded context to its rounding quantum.
CONNECTOR_STRAIGHT_LINE_AGREEMENT_M = 0.1
# Every authored leg must be resolvable at the census lens.
CONNECTOR_MIN_LEG_M = 2.0 * CARRIAGEWAY_TANGENT_LENS_M

ENDPOINT_CONNECTOR_FIDELITY = {
    "class": "authored_waypoint",
    "waypoint_position_class_m": 250.0,
    "statement": (
        "Interior waypoints are project-authored route context at declared "
        "waypoint fidelity (ADR-0017 authored class): each waypoint names the "
        "public facility ADR-0024 prescribes and is placed from public "
        "geographic knowledge of that facility, never claimed as observed "
        "centerline, lane geometry, or survey-class position. The connector "
        "length therefore carries authored-waypoint precision; the locked "
        "corridor figure it joins remains source-centerline fidelity. "
        "Acquiring locked source geometry for these facilities is recorded "
        "future refinement, not assumed."
    ),
}

ENDPOINT_CONNECTOR_MODEL = {
    "decision": "ADR-0018",
    "context_decision": "ADR-0017",
    "carriageway_decision": "ADR-0014",
    "metric_crs": "EPSG:5070",
    "tangent_lens_m": CARRIAGEWAY_TANGENT_LENS_M,
    "corner_threshold_deg": CARRIAGEWAY_CORNER_THRESHOLD_DEG,
    "reversal_threshold_deg": CARRIAGEWAY_REVERSAL_THRESHOLD_DEG,
    "min_leg_m": CONNECTOR_MIN_LEG_M,
    "straight_line_agreement_m": CONNECTOR_STRAIGHT_LINE_AGREEMENT_M,
    "fidelity": ENDPOINT_CONNECTOR_FIDELITY,
    "endpoint_rule": (
        "Each connector joins exactly two locked coordinates: the "
        "route-selection public-road portal (census address match) and the "
        "directed route lock's corridor-end node at the ADR-0024 anchor. "
        "Both are carried verbatim; every metre between them is authored and "
        "recorded with its facility justification."
    ),
    "roadway_kind_rule": (
        "Connectors are ADR-0014 'unclassified' roadway records: the "
        "sequence spans divided highways (NJ 495, NJ 3, US 46, CA 107) and "
        "undivided public streets (Manhattan crosstown, Torrance Boulevard "
        "approaches, Portofino Way), so no reciprocal divided-carriageway "
        "pair is claimed and no opposing edge is synthesized. Lane-level "
        "modelling of the endpoint service bubbles is later stage output."
    ),
}

ENDPOINT_CONNECTOR_SOURCE_POLICY = {
    "reconstruction_decision": "ADR-0018",
    "context_decision": "ADR-0017",
    "route_decision": "ADR-0024",
    "authored_geometry_claimed_as_source": False,
    "lane_geometry_claimed": False,
    "vertical_context_claimed": False,
    "private_property_required": False,
    "continental_downloads_committed": False,
}

ENDPOINT_CONNECTOR_DEFERRED_GATES = {
    "deferred_to": "lane-topology-and-package-build-stage",
    "gates": [
        "grade",
        "vertical_curvature",
        "curvature_design_radius",
        "curvature_rate",
        "sightline",
        "clearance",
        "collision",
        "lane_connection",
        "drivability",
        "reciprocal_separation",
    ],
    "reason": (
        "No locked elevation or lane source covers the connector facilities: "
        "the corridor elevation lock stations only the locked directed walk, "
        "and ADR-0017 keeps unknown values unknown rather than authored into "
        "false precision. The connectors are ADR-0014 'unclassified' roadway "
        "records - the undivided portions cannot claim the divided-"
        "carriageway reciprocal pair, so the separation gate has no pair to "
        "measure. Vertical and lane-level gates run when the endpoint "
        "service bubbles are built at the package-build stage."
    ),
}

ENDPOINT_CONNECTOR_NEXT_STAGE = {
    "id": "portal-run-length-publication",
    "requires": [
        "the westbound carriageway lock revision pins this artifact and "
        "publishes ADR-0024's portal-to-portal run length from the locked "
        "corridor plus these connectors",
        "the southern path's Holland Tunnel connector (nyc-start-to-i78) "
        "remains unauthored; its portal-to-portal figure stays unpublished "
        "until it is",
        "endpoint service-bubble lane topology, elevation, and collision at "
        "the package-build stage",
    ],
}

# Interior waypoints are authored travel-ordered route context between the two
# locked endpoint coordinates. Each carries the ADR-0024 facility its arriving
# leg travels and a reviewer-visible justification note (ADR-0017/ADR-0018
# authored-overlay discipline). The envelope ratio bounds the authored length
# against the directed lock's recorded portal-to-anchor straight line.
AUTHORED_ENDPOINT_CONNECTORS = (
    {
        "segment_id": "nyc-start-to-i80",
        "role": "atlantic_start",
        "travel": "portal_to_corridor",
        "corridor_end": {"segment_id": "i80-new-jersey-to-big-springs", "end": "from"},
        "length_envelope_ratio": 1.25,
        "length_envelope_justification": (
            "The Lincoln Tunnel / NJ 495 / NJ 3 / US 46 corridor runs "
            "broadly parallel to the portal-to-anchor straight line across "
            "the Hudson and the Meadowlands; a metropolitan arterial "
            "connector on these facilities cannot legitimately exceed a "
            "quarter more than the straight line, and the authored polyline "
            "measures near 1.10."
        ),
        "waypoints": (
            {
                "longitude": -73.984167,
                "latitude": 40.746667,
                "facility": "project-authored Manhattan connector",
                "note": (
                    "Midtown crosstown from the E 31st Street portal toward "
                    "the Lincoln Tunnel approach."
                ),
            },
            {
                "longitude": -73.9925,
                "latitude": 40.7515,
                "facility": "project-authored Manhattan connector",
                "note": (
                    "Herald Square area crosstown context (W 34th Street "
                    "corridor)."
                ),
            },
            {
                "longitude": -73.9967,
                "latitude": 40.757,
                "facility": "project-authored Manhattan connector",
                "note": "Dyer Avenue approach to the Lincoln Tunnel New York portal.",
            },
            {
                "longitude": -74.01,
                "latitude": 40.7625,
                "facility": "Lincoln Tunnel",
                "note": (
                    "Mid-river tunnel alignment under the Hudson (authored "
                    "context; the bore is not surface geometry)."
                ),
            },
            {
                "longitude": -74.0205,
                "latitude": 40.7655,
                "facility": "Lincoln Tunnel",
                "note": "Weehawken portal and helix.",
            },
            {
                "longitude": -74.033,
                "latitude": 40.769,
                "facility": "NJ 495",
                "note": "NJ 495 westbound through Union City.",
            },
            {
                "longitude": -74.063,
                "latitude": 40.777,
                "facility": "NJ 495",
                "note": (
                    "NJ 495 / NJ 3 continuation at the eastern Meadowlands "
                    "interchange complex."
                ),
            },
            {
                "longitude": -74.093,
                "latitude": 40.79,
                "facility": "NJ 3",
                "note": "NJ 3 across the Hackensack Meadowlands.",
            },
            {
                "longitude": -74.128,
                "latitude": 40.809,
                "facility": "NJ 3",
                "note": "NJ 3 through Rutherford; Passaic River approach.",
            },
            {
                "longitude": -74.156,
                "latitude": 40.8215,
                "facility": "NJ 3",
                "note": "NJ 3 through Clifton.",
            },
            {
                "longitude": -74.183,
                "latitude": 40.852,
                "facility": "NJ 3",
                "note": "NJ 3 western terminus at the US 46 merge in Clifton.",
            },
            {
                "longitude": -74.223,
                "latitude": 40.87,
                "facility": "US 46",
                "note": "US 46 through Little Falls.",
            },
            {
                "longitude": -74.258,
                "latitude": 40.888,
                "facility": "US 46",
                "note": "US 46 at the Willowbrook interchange complex in Wayne.",
            },
            {
                "longitude": -74.31,
                "latitude": 40.881,
                "facility": "US 46",
                "note": "US 46 through Fairfield.",
            },
            {
                "longitude": -74.345,
                "latitude": 40.872,
                "facility": "US 46",
                "note": "US 46 through Pine Brook.",
            },
            {
                "longitude": -74.395,
                "latitude": 40.868,
                "facility": "US 46",
                "note": "US 46 through Parsippany-Troy Hills.",
            },
        ),
        "final_leg_facility": "US 46",
        "final_leg_note": (
            "US 46 at the locked I-80 corridor anchor (the directed lock's "
            "from-node of i80-new-jersey-to-big-springs)."
        ),
    },
    {
        "segment_id": "redondo-access-to-finish",
        "role": "pacific_finish",
        "travel": "corridor_to_portal",
        "corridor_end": {"segment_id": "i405-west-la-to-ca107", "end": "to"},
        "length_envelope_ratio": 1.8,
        "length_envelope_justification": (
            "The locked street sequence is a right-angle dogleg - south on "
            "CA 107 / Hawthorne Boulevard, then west to the Redondo Beach "
            "waterfront - so the taxicab geometry of the named streets "
            "legitimately exceeds the diagonal straight line (the dogleg "
            "alone measures near 1.57); 1.8 bounds the grid detour without "
            "absorbing an unjustified route."
        ),
        "waypoints": (
            {
                "longitude": -118.3524,
                "latitude": 33.8785,
                "facility": "CA 107 / Hawthorne Boulevard",
                "note": (
                    "Hawthorne Boulevard immediately south of the I-405 "
                    "interchange."
                ),
            },
            {
                "longitude": -118.3525,
                "latitude": 33.8595,
                "facility": "CA 107 / Hawthorne Boulevard",
                "note": "Hawthorne Boulevard at the 190th Street corridor.",
            },
            {
                "longitude": -118.3526,
                "latitude": 33.8358,
                "facility": "CA 107 / Hawthorne Boulevard",
                "note": (
                    "Hawthorne Boulevard at Torrance Boulevard - the CA 107 "
                    "terminus corner."
                ),
            },
            {
                "longitude": -118.37,
                "latitude": 33.8358,
                "facility": "Torrance Boulevard",
                "note": "Torrance Boulevard westbound through central Torrance.",
            },
            {
                "longitude": -118.3875,
                "latitude": 33.8363,
                "facility": "Torrance Boulevard",
                "note": "Torrance Boulevard at Catalina Avenue in Redondo Beach.",
            },
            {
                "longitude": -118.3895,
                "latitude": 33.8428,
                "facility": "Catalina Avenue",
                "note": "Catalina Avenue north to Beryl Street.",
            },
            {
                "longitude": -118.3928,
                "latitude": 33.844,
                "facility": "Beryl Street",
                "note": "Beryl Street west to Harbor Drive.",
            },
            {
                "longitude": -118.3947,
                "latitude": 33.846,
                "facility": "Harbor Drive",
                "note": "Harbor Drive north to the Portofino Way corner.",
            },
        ),
        "final_leg_facility": "Portofino Way",
        "final_leg_note": (
            "Portofino Way public-road portal adjacent to the historical "
            "260 Portofino Way reference address; no private hotel or "
            "marina property is required or implied."
        ),
    },
)


def _connector_corner_sites(
    connector_id: str,
    coordinates: Sequence[tuple[float, float]],
    inverse: Transformer,
) -> list[dict[str, Any]]:
    """Corner-class heading exceptions along one authored connector.

    The carriageway census discipline at the 25 m lens: every turn beyond the
    corner threshold joins a recorded cluster, and a reversal-class turn is a
    refusal - an authored connector may not double back on itself.
    """
    samples = _resample_polyline(coordinates, CARRIAGEWAY_TANGENT_LENS_M)
    flagged: list[tuple[float, int]] = []
    for index in range(1, len(samples) - 1):
        angle = _vertex_turn_degrees(samples, index)
        if angle > CARRIAGEWAY_REVERSAL_THRESHOLD_DEG:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "authored connector carries a "
                        "reversal-class turn",
                        "connector_id": connector_id,
                        "turn_deg": round(angle, 2),
                        "station_m": round(index * CARRIAGEWAY_TANGENT_LENS_M, 1),
                    },
                    sort_keys=True,
                )
            )
        if angle > CARRIAGEWAY_CORNER_THRESHOLD_DEG:
            flagged.append((angle, index))
    clusters: list[list[tuple[float, int]]] = []
    for angle, index in flagged:
        if clusters and index - clusters[-1][-1][1] <= CARRIAGEWAY_CORNER_CLUSTER_STEPS:
            clusters[-1].append((angle, index))
        else:
            clusters.append([(angle, index)])
    sites: list[dict[str, Any]] = []
    for cluster_index, cluster in enumerate(clusters):
        peak_angle, peak_sample = max(cluster)
        longitude, latitude = inverse.transform(*samples[peak_sample])
        sites.append(
            {
                "corner_id": f"{connector_id}--corner-{cluster_index:03d}",
                "corner_class": CONNECTOR_CORNER_CLASS,
                "from_station_m": round(
                    cluster[0][1] * CARRIAGEWAY_TANGENT_LENS_M, 1
                ),
                "to_station_m": round(cluster[-1][1] * CARRIAGEWAY_TANGENT_LENS_M, 1),
                "peak_turn_deg": round(peak_angle, 2),
                "turn_sum_deg": round(sum(angle for angle, _ in cluster), 2),
                "sample_count": len(cluster),
                "coordinate": [round(longitude, 7), round(latitude, 7)],
            }
        )
    return sites


def _endpoint_connector_records(
    selection: dict[str, Any],
    transfer_lock: dict[str, Any],
    directed_lock: dict[str, Any],
) -> list[dict[str, Any]]:
    """The two authored ADR-0024 endpoint connectors, gated and recorded."""
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    inverse = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    selection_by_id = {segment["id"]: segment for segment in selection["segments"]}
    endpoints_by_node = {
        endpoint["node_id"]: endpoint for endpoint in selection["endpoints"].values()
    }
    transfer_by_id = {node["id"]: node for node in transfer_lock["transfer_nodes"]}
    directed_by_id = {
        record["segment_id"]: record for record in directed_lock["segments"]
    }
    straight_line_by_segment = {
        entry["segment_id"]: entry
        for entry in directed_lock["corridor"]["authoritative_distance"][
            "excluded_endpoint_connectors"
        ]
    }

    connectors: list[dict[str, Any]] = []
    for authored in AUTHORED_ENDPOINT_CONNECTORS:
        connector_id = authored["segment_id"]
        segment = selection_by_id[connector_id]
        portal_ids = [
            node_id
            for node_id in (segment["from"], segment["to"])
            if node_id in endpoints_by_node
        ]
        anchor_ids = [
            node_id
            for node_id in (segment["from"], segment["to"])
            if node_id in transfer_by_id
        ]
        if len(portal_ids) != 1 or len(anchor_ids) != 1:
            raise ValueError(
                f"Connector '{connector_id}' does not join exactly one portal "
                "to exactly one locked anchor."
            )
        portal = endpoints_by_node[portal_ids[0]]
        anchor = transfer_by_id[anchor_ids[0]]
        corridor_record = directed_by_id[authored["corridor_end"]["segment_id"]]
        end_key = f"{authored['corridor_end']['end']}_node"
        corridor_node = corridor_record[end_key]
        corridor_anchor_id = corridor_record[
            f"{authored['corridor_end']['end']}_anchor"
        ]
        if corridor_anchor_id != anchor_ids[0]:
            raise ValueError(
                f"Connector '{connector_id}' corridor end does not sit at its "
                "ADR-0024 anchor."
            )

        portal_point = (
            portal["coordinate"]["longitude"],
            portal["coordinate"]["latitude"],
        )
        corridor_point = (corridor_node["longitude"], corridor_node["latitude"])
        interior = [
            (waypoint["longitude"], waypoint["latitude"])
            for waypoint in authored["waypoints"]
        ]
        if authored["travel"] == "portal_to_corridor":
            coordinates = [portal_point, *interior, corridor_point]
        else:
            coordinates = [corridor_point, *interior, portal_point]

        # The recomputed straight line must reproduce the directed lock's
        # recorded portal-to-anchor context.
        straight_line = round(
            _geodesic_distance_m(
                portal_point,
                (anchor["coordinate"]["longitude"], anchor["coordinate"]["latitude"]),
            ),
            1,
        )
        recorded_straight = straight_line_by_segment[connector_id][
            "portal_to_anchor_straight_line_m"
        ]
        if abs(straight_line - recorded_straight) > CONNECTOR_STRAIGHT_LINE_AGREEMENT_M:
            raise ValueError(
                f"Connector '{connector_id}' straight-line context "
                f"({straight_line} m) does not reproduce the directed lock's "
                f"recorded {recorded_straight} m."
            )

        metric = [forward.transform(*point) for point in coordinates]
        legs: list[dict[str, Any]] = []
        facilities: list[str] = []
        geodesic_total = 0.0
        planimetric_total = 0.0
        for index in range(1, len(coordinates)):
            arriving_authored = (
                authored["waypoints"][index - 1]
                if index - 1 < len(authored["waypoints"])
                else None
            )
            facility = (
                arriving_authored["facility"]
                if arriving_authored is not None
                else authored["final_leg_facility"]
            )
            note = (
                arriving_authored["note"]
                if arriving_authored is not None
                else authored["final_leg_note"]
            )
            geodesic = _geodesic_line_length_m(
                [coordinates[index - 1], coordinates[index]]
            )
            planimetric = math.dist(metric[index - 1], metric[index])
            if planimetric < CONNECTOR_MIN_LEG_M:
                raise ValueError(
                    f"Connector '{connector_id}' leg {index} is shorter than "
                    f"the {CONNECTOR_MIN_LEG_M} m census floor."
                )
            legs.append(
                {
                    "leg_index": index - 1,
                    "facility": facility,
                    "note": note,
                    "provenance": "authored",
                    "geodesic_m": round(geodesic, 3),
                    "planimetric_m": round(planimetric, 3),
                }
            )
            facilities.append(facility)
            geodesic_total += geodesic
            planimetric_total += planimetric

        # The travel-ordered facility sequence must be exactly the ADR-0024
        # selection's facility sequence, with no facility invented or dropped.
        deduped: list[str] = []
        for facility in facilities:
            if not deduped or deduped[-1] != facility:
                deduped.append(facility)
        # Both authored connectors list their ADR-0024 facility sequence in
        # travel order (the selection writes each connector portal-outward
        # for the start and corridor-outward for the finish).
        travel_sequence = list(segment["facility_sequence"])
        if deduped != travel_sequence:
            raise ValueError(
                f"Connector '{connector_id}' authored facility sequence "
                f"{deduped} does not reproduce the ADR-0024 sequence "
                f"{travel_sequence}."
            )

        line = LineString(metric)
        if not line.is_simple:
            raise ValueError(
                f"Connector '{connector_id}' authored polyline "
                "self-intersects."
            )
        corner_sites = _connector_corner_sites(connector_id, metric, inverse)
        geodesic_total = round(geodesic_total, 3)
        planimetric_total = round(planimetric_total, 3)
        detour_ratio = round(geodesic_total / recorded_straight, 6)
        agreement_allowance = (
            GEODESIC_PLANIMETRIC_AGREEMENT_RATIO * planimetric_total
            + GEODESIC_ROUNDING_ALLOWANCE_M * len(legs)
        )
        gates = {
            "endpoint_continuity": _carriageway_gate(
                {
                    "portal_gap_m": 0.0,
                    "corridor_end_gap_m": 0.0,
                },
                "locked portal and corridor-end coordinates carried verbatim",
                True,
            ),
            "heading_discipline": _carriageway_gate(
                max((site["peak_turn_deg"] for site in corner_sites), default=0.0),
                CARRIAGEWAY_REVERSAL_THRESHOLD_DEG,
                True,
            ),
            "self_intersection": _carriageway_gate(
                {"simple": True},
                "authored polyline is a single simple LineString",
                True,
            ),
            "station_monotonicity": _carriageway_gate(
                {"vertex_count": len(coordinates)},
                "strictly increasing station at every vertex",
                True,
            ),
            "length_envelope": _carriageway_gate(
                detour_ratio,
                authored["length_envelope_ratio"],
                1.0 <= detour_ratio <= authored["length_envelope_ratio"],
            ),
            "geodesic_planimetric_agreement": _carriageway_gate(
                round(abs(geodesic_total - planimetric_total), 3),
                round(agreement_allowance, 3),
                abs(geodesic_total - planimetric_total) <= agreement_allowance,
            ),
        }
        failed = {name for name, gate in gates.items() if not gate["passed"]}
        if failed:
            raise ValueError(
                json.dumps(
                    {
                        "refusal": "endpoint connector gates failed",
                        "connector_id": connector_id,
                        "failed_gates": sorted(failed),
                        "gates": gates,
                    },
                    sort_keys=True,
                )
            )

        waypoints_payload: list[dict[str, Any]] = []
        for index, point in enumerate(coordinates):
            if index == 0:
                provenance = (
                    "locked_portal"
                    if authored["travel"] == "portal_to_corridor"
                    else "locked_corridor_end"
                )
            elif index == len(coordinates) - 1:
                provenance = (
                    "locked_corridor_end"
                    if authored["travel"] == "portal_to_corridor"
                    else "locked_portal"
                )
            else:
                provenance = "authored"
            entry: dict[str, Any] = {
                "index": index,
                "longitude": point[0],
                "latitude": point[1],
                "provenance": provenance,
            }
            if provenance == "authored":
                authored_waypoint = authored["waypoints"][index - 1]
                entry["facility"] = authored_waypoint["facility"]
                entry["note"] = authored_waypoint["note"]
            waypoints_payload.append(entry)

        connectors.append(
            {
                "connector_id": connector_id,
                "role": authored["role"],
                "decision": "ADR-0018",
                "travel": authored["travel"],
                "roadway_kind": "unclassified",
                "portal": {
                    "node_id": portal["node_id"],
                    "label": portal["label"],
                    "reference_address": portal["reference_address"],
                    "coordinate": {
                        "longitude": portal["coordinate"]["longitude"],
                        "latitude": portal["coordinate"]["latitude"],
                        "precision": portal["coordinate"]["precision"],
                    },
                    "playable_policy": portal["playable_policy"],
                },
                "corridor_end": {
                    "anchor_id": anchor_ids[0],
                    "segment_id": authored["corridor_end"]["segment_id"],
                    "end": authored["corridor_end"]["end"],
                    "coordinate": dict(corridor_node),
                    "provenance": "directed-route-lock",
                },
                "straight_line_context_m": straight_line,
                "length_envelope": {
                    "ratio_bound": authored["length_envelope_ratio"],
                    "justification": authored["length_envelope_justification"],
                },
                "waypoints": waypoints_payload,
                "legs": legs,
                "lengths": {
                    "geodesic_m": geodesic_total,
                    "geodesic_miles": round(geodesic_total / METRES_PER_MILE, 3),
                    "planimetric_m": planimetric_total,
                    "detour_ratio": detour_ratio,
                },
                "authored_breakdown": {
                    "locked_endpoint_count": 2,
                    "authored_waypoint_count": len(authored["waypoints"]),
                    "authored_geodesic_m": geodesic_total,
                    "sourced_geodesic_m": 0.0,
                    "statement": (
                        "The two endpoint coordinates are locked artifacts "
                        "(route-selection portal; directed-route-lock "
                        "corridor-end node). No locked or probed source "
                        "geometry exists for the connector facilities - the "
                        "NHPN candidate lock is scoped to the twelve "
                        "corridor segments - so every metre between the "
                        "locked endpoints is authored, each leg justified by "
                        "its ADR-0024 facility."
                    ),
                },
                "corner_sites": corner_sites,
                "gates": gates,
            }
        )
    return connectors


def author_continental_endpoint_connectors(
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
    output_path: Path,
    *,
    authored_at: str | None = None,
) -> dict[str, Any]:
    """Author the two ADR-0024 endpoint connectors as bounded ADR-0018 records.

    A pure function of the committed locks and the authored registry - no
    cache, no network. Each connector joins the locked public-road portal to
    the directed lock's corridor-end node over the ADR-0024 facility
    sequence, with every authored metre recorded and gated.
    """
    directed_lock = validate_continental_directed_route_lock(
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    selection = load_json(selection_path)
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    timestamp = authored_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    connectors = _endpoint_connector_records(selection, transfer_lock, directed_lock)
    payload = {
        "schema_version": 1,
        "status": ENDPOINT_CONNECTOR_STATUS,
        "decision": "ADR-0018",
        "route_decision": selection["decision"],
        "context_decision": "ADR-0017",
        "carriageway_decision": "ADR-0014",
        "authored_at": timestamp,
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
        "model": dict(ENDPOINT_CONNECTOR_MODEL),
        "source_policy": dict(ENDPOINT_CONNECTOR_SOURCE_POLICY),
        "deferred_gates": dict(ENDPOINT_CONNECTOR_DEFERRED_GATES),
        "connector_count": len(connectors),
        "connectors": connectors,
        "connectors_sha256": canonical_sha256(connectors),
        "unauthored_connectors": [
            {
                "segment_id": "nyc-start-to-i78",
                "reason": (
                    "The southern path's Holland Tunnel connector remains "
                    "unauthored; ADR-0024's canonical run uses the Lincoln "
                    "Tunnel start, and the southern portal-to-portal figure "
                    "stays unpublished until this connector is authored and "
                    "gated."
                ),
            }
        ],
        "summary": {
            "connector_count": len(connectors),
            "gates_passed": sum(
                1
                for connector in connectors
                for gate in connector["gates"].values()
                if gate["passed"]
            ),
            "gates_failed": 0,
            "corner_site_count": sum(
                len(connector["corner_sites"]) for connector in connectors
            ),
            "authored_geodesic_m": round(
                sum(connector["lengths"]["geodesic_m"] for connector in connectors),
                3,
            ),
            "authored_waypoint_count": sum(
                connector["authored_breakdown"]["authored_waypoint_count"]
                for connector in connectors
            ),
        },
        "next_stage": ENDPOINT_CONNECTOR_NEXT_STAGE,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def validate_continental_endpoint_connectors(
    connector_lock_path: Path,
    directed_lock_path: Path,
    selection_path: Path,
    route_lock_path: Path,
    transfer_lock_path: Path,
    policy_path: Path,
    edge_path_lock_path: Path,
    fill_lock_path: Path,
    disposition_path: Path,
    overlay_lock_path: Path,
    conflation_lock_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Validate the endpoint connector lock by full re-derivation.

    The authoring is a pure function of committed locks and the authored
    registry, so the validator recomputes the entire artifact and requires
    exact reproduction modulo the authoring timestamp - a drifted waypoint,
    dropped leg, widened envelope, or hand-edited gate cannot validate.
    """
    payload = load_json(connector_lock_path)
    if payload.get("schema_version") != 1:
        raise ValueError("Endpoint connector lock schema_version must be 1.")
    directed_lock = validate_continental_directed_route_lock(
        directed_lock_path,
        selection_path,
        route_lock_path,
        transfer_lock_path,
        policy_path,
        edge_path_lock_path,
        fill_lock_path,
        disposition_path,
        overlay_lock_path,
        conflation_lock_path,
        catalog_path,
    )
    selection = load_json(selection_path)
    transfer_lock = validate_continental_transfer_lock(
        transfer_lock_path, policy_path, selection_path, route_lock_path, catalog_path
    )
    expected_hashes = {
        "catalog_sha256": compute_sha256(catalog_path),
        "route_selection_sha256": compute_sha256(selection_path),
        "candidate_lock_sha256": compute_sha256(route_lock_path),
        "transfer_lock_sha256": compute_sha256(transfer_lock_path),
        "edge_path_lock_sha256": compute_sha256(edge_path_lock_path),
        "nhs_fill_lock_sha256": compute_sha256(fill_lock_path),
        "break_disposition_sha256": compute_sha256(disposition_path),
        "reconstruction_overlay_lock_sha256": compute_sha256(overlay_lock_path),
        "nhs_conflation_lock_sha256": compute_sha256(conflation_lock_path),
        "directed_route_lock_sha256": compute_sha256(directed_lock_path),
    }
    if any(payload.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Endpoint connector lock input hash drifted.")
    expected_connectors = _endpoint_connector_records(
        selection, transfer_lock, directed_lock
    )
    expected = {
        "schema_version": 1,
        "status": ENDPOINT_CONNECTOR_STATUS,
        "decision": "ADR-0018",
        "route_decision": selection["decision"],
        "context_decision": "ADR-0017",
        "carriageway_decision": "ADR-0014",
        "authored_at": payload.get("authored_at"),
        "coordinate_crs": "EPSG:4326",
        "metric_crs": "EPSG:5070",
        **expected_hashes,
        "model": dict(ENDPOINT_CONNECTOR_MODEL),
        "source_policy": dict(ENDPOINT_CONNECTOR_SOURCE_POLICY),
        "deferred_gates": dict(ENDPOINT_CONNECTOR_DEFERRED_GATES),
        "connector_count": len(expected_connectors),
        "connectors": expected_connectors,
        "connectors_sha256": canonical_sha256(expected_connectors),
        "unauthored_connectors": payload.get("unauthored_connectors"),
        "summary": payload.get("summary"),
        "next_stage": ENDPOINT_CONNECTOR_NEXT_STAGE,
    }
    if payload.get("connectors_sha256") != expected["connectors_sha256"] or (
        payload.get("connectors") != expected_connectors
    ):
        raise ValueError(
            "Endpoint connector lock does not reproduce from the committed "
            "inputs and the authored registry."
        )
    if not isinstance(payload.get("authored_at"), str) or not payload["authored_at"]:
        raise ValueError("Endpoint connector lock authoring timestamp is missing.")
    unauthored = payload.get("unauthored_connectors")
    if (
        not isinstance(unauthored, list)
        or len(unauthored) != 1
        or unauthored[0].get("segment_id") != "nyc-start-to-i78"
        or not unauthored[0].get("reason")
    ):
        raise ValueError(
            "Endpoint connector lock must record the unauthored Holland "
            "Tunnel connector with its reason."
        )
    expected_summary = {
        "connector_count": len(expected_connectors),
        "gates_passed": sum(
            1
            for connector in expected_connectors
            for gate in connector["gates"].values()
            if gate["passed"]
        ),
        "gates_failed": 0,
        "corner_site_count": sum(
            len(connector["corner_sites"]) for connector in expected_connectors
        ),
        "authored_geodesic_m": round(
            sum(
                connector["lengths"]["geodesic_m"]
                for connector in expected_connectors
            ),
            3,
        ),
        "authored_waypoint_count": sum(
            connector["authored_breakdown"]["authored_waypoint_count"]
            for connector in expected_connectors
        ),
    }
    if payload.get("summary") != expected_summary:
        raise ValueError(
            "Endpoint connector lock summary does not reproduce from the "
            "committed connectors."
        )
    comparable = {key: value for key, value in payload.items()}
    if comparable != expected:
        raise ValueError(
            "Endpoint connector lock does not reproduce the authored "
            "derivation exactly."
        )
    return payload
