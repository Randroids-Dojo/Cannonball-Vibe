from __future__ import annotations

import json
import math
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, transform

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
    begin_milepost: float = 0.0
    end_milepost: float = 0.0
    part_index: int = 0


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
    snapshot_by_id = {
        snapshot["segment_id"]: snapshot
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
    }
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
            line_cache[segment_id] = _load_locked_candidate_lines(
                snapshot_by_id[segment_id], cache_root / segment_id
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
    for snapshot in route_lock["nhpn"]["segment_snapshots"]:
        evidence_by_id: dict[int, str] = {}
        for page in snapshot["pages"]:
            offset = page["object_id_offset"]
            for object_id in snapshot["object_ids"][
                offset : offset + page["feature_count"]
            ]:
                evidence_by_id[object_id] = page["canonical_response_sha256"]
        snapshot_evidence[snapshot["segment_id"]] = evidence_by_id
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
                lines.append(
                    LockedCandidateLine(
                        snapshot["segment_id"],
                        object_id,
                        response_hash,
                        LineString(coordinates),
                        str(attributes.get("LRSKEY", "")),
                        float(attributes.get("BEGMP") or 0.0),
                        float(attributes.get("ENDMP") or 0.0),
                        part_index,
                    )
                )
    if seen != set(object_ids):
        raise ValueError(f"Locked NHPN cache does not reconcile for '{snapshot['segment_id']}'.")
    return tuple(lines)


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
    graph = nx.MultiGraph()
    nodes: dict[tuple[int, int], tuple[float, float]] = {}
    edge_endpoints: list[tuple[tuple[int, int], tuple[int, int]]] = []
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
        edge_endpoints.append((start_key, end_key))

    # What shape is this candidate set? An endpoint joining exactly two records is
    # chain interior; one joining a single record is a chain end. A near-linear
    # corridor is dominated by degree 2, and its components separate at chain ends,
    # so the distances between those ends are what explain a connectivity failure.
    endpoint_degree: dict[tuple[int, int], int] = {}
    for start_key, end_key in edge_endpoints:
        endpoint_degree[start_key] = endpoint_degree.get(start_key, 0) + 1
        endpoint_degree[end_key] = endpoint_degree.get(end_key, 0) + 1
    degree_counts: dict[str, int] = {}
    for degree in endpoint_degree.values():
        bucket = str(degree) if degree < 3 else "3+"
        degree_counts[bucket] = degree_counts.get(bucket, 0) + 1
    degree_histogram = dict(sorted(degree_counts.items()))
    end_nodes = sorted(key for key, degree in endpoint_degree.items() if degree == 1)
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

    def nearest_node(point: tuple[float, float]) -> tuple[tuple[int, int], float]:
        best_key, best_distance = None, float("inf")
        for key in sorted(nodes):
            distance = math.dist(point, nodes[key])
            if distance < best_distance:
                best_key, best_distance = key, distance
        assert best_key is not None
        return best_key, best_distance

    from_key, from_distance = nearest_node(from_point)
    to_key, to_distance = nearest_node(to_point)
    diagnostics["from_transfer_node_snap_distance_m"] = round(from_distance, 3)
    diagnostics["to_transfer_node_snap_distance_m"] = round(to_distance, 3)
    diagnostics["anchor_snap_limit_m"] = anchor_limit

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
        edges.append(
            SolvedEdge(
                object_id=int(data["object_id"]),
                part_index=int(data["part_index"]),
                page_response_sha256=str(data["page_response_sha256"]),
                length_meters=float(data["weight"]),
                reversed_for_travel=data["start_key"] != previous,
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
    small_gaps = sorted(
        gap
        for entry in results
        for gap in entry["chain_end_separations_m"]
        if gap <= 1000
    )
    return (
        "Each locked segment is a near-linear chain rather than a network: "
        f"{round(min(interior) * 100)} to {round(max(interior) * 100)} percent of "
        "endpoints join exactly two records. The graph splits where consecutive "
        "records do not share an endpoint within the snapping tolerance, which is "
        f"why {len(results) - connected} of {len(results)} segments have no undirected "
        "path between their locked transfer nodes. The smallest separations between "
        f"chain ends are {small_gaps[:6]} m, so those breaks are endpoint "
        "discontinuities of metres to hundreds of metres rather than missing corridor; "
        "the large separations are the corridor termini, not defects. Where a path was "
        "found it is a shortest undirected traversal and is not a westbound selection, "
        "which this stage does not assert."
    )


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
        lines = _load_locked_candidate_lines(
            snapshot_by_id[segment["id"]], cache_root / segment["id"]
        )
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
        for snapshot in route_lock["nhpn"]["segment_snapshots"]
        for page in snapshot["pages"]
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
