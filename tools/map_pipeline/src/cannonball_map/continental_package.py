"""Build a runtime route package for one locked continental segment.

The sixteen offline P0-021 stages lock everything the runtime needs except the
package itself: the westbound centreline (digest-locked, materialised only in
the ignored carriageway cache), the conditioned and lane-eased elevation
profile, the lane sections, and the 2 km collision chunk grid. This module
turns one segment of that into the same sharded FlatBuffer package the fixture
build emits, through the same writer, so the ADR-0019 ceilings and the runtime
verification apply unchanged.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import LineString

from cannonball_map.continental import _lane_eased_segment_profile
from cannonball_map.continental_collision import (
    _elevation_at,
    _file_sha,
    _load,
    _refined_line,
    _sha,
)
from cannonball_map.pipeline import PROJECTED_CRS, _curvatures, _grades, _sample_distances
from cannonball_map.semantics import (
    MANEUVER_CONTINUE,
    _provenance,
    _stable_id,
    attach_derived_route_semantics,
)
from cannonball_map.sharding import write_sharded_package

PACKAGE_RESAMPLE_METERS = 25.0
PACKAGE_CHUNK_METERS = 2_000.0
PACKAGE_COORDINATE_DECIMALS = 3
PACKAGE_ELEVATION_DECIMALS = 3
MILES_PER_HOUR_TO_METERS_PER_SECOND = 0.44704
PROVENANCE_FILENAME = "continental-package-provenance.json"


def _segment_record(lock: dict[str, Any], segment_id: str, name: str) -> dict[str, Any]:
    segments = lock.get("segments", [])
    if isinstance(segments, dict):
        record = segments.get(segment_id)
    else:
        record = next((item for item in segments if item.get("segment_id") == segment_id), None)
    if record is None:
        raise ValueError(f"{name} has no record for segment '{segment_id}'.")
    return record


def authenticated_westbound_line(
    segment_id: str,
    carriageway_cache_directory: Path,
    carriageway_lock: dict[str, Any],
    lane_lock: dict[str, Any],
) -> LineString:
    """The refined westbound centreline, admitted only when it matches its lock.

    The centreline lives in an ignored cache; the carriageway lock commits its
    digest and vertex count. A cache that does not reproduce them is refused
    with the regeneration path, so a stale or edited cache cannot ship.
    """
    cache_path = carriageway_cache_directory / f"{segment_id}.json"
    if not cache_path.is_file():
        raise ValueError(
            f"carriageway cache '{cache_path}' is missing; regenerate it with "
            "derive-continental-westbound-carriageway."
        )
    cache = _load(cache_path)
    if cache.get("metric_crs", PROJECTED_CRS) != PROJECTED_CRS:
        raise ValueError(f"carriageway cache '{cache_path}' is not in {PROJECTED_CRS}.")
    coordinates = cache.get("westbound_coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError(f"carriageway cache '{cache_path}' has no westbound geometry.")
    locked = _segment_record(carriageway_lock, segment_id, "westbound carriageway lock")[
        "westbound"
    ]
    digest = _sha(coordinates)
    if digest != locked["geometry_sha256"] or len(coordinates) != int(locked["vertex_count"]):
        raise ValueError(
            f"carriageway cache '{cache_path}' does not match the westbound carriageway "
            f"lock (geometry sha256 {digest} vs {locked['geometry_sha256']}, "
            f"{len(coordinates)} vs {locked['vertex_count']} vertices)."
        )
    return _refined_line(LineString(coordinates), "carriageway_chain", segment_id, lane_lock)


def edge_samples(
    line: LineString,
    eased_profile: list[float],
    terminal_station_meters: float,
    resample_meters: float = PACKAGE_RESAMPLE_METERS,
) -> list[dict[str, float]]:
    """Runtime samples on the collision stage's station grid.

    Elevation comes through the same ``_elevation_at`` the collision ribbons
    use, so the drivable surface and the collision mesh agree vertically.
    """
    if line.length <= 0:
        raise ValueError("segment centreline has no length.")
    distances = _sample_distances(line.length, resample_meters)
    points = [line.interpolate(distance) for distance in distances]
    elevations = [
        round(
            _elevation_at(eased_profile, terminal_station_meters, distance),
            PACKAGE_ELEVATION_DECIMALS,
        )
        for distance in distances
    ]
    curvatures = _curvatures(points)
    grades = _grades(distances, elevations)
    samples: list[dict[str, float]] = []
    for index, distance in enumerate(distances):
        samples.append(
            {
                "distance_meters": float(distance),
                "lateral_meters": 0.0,
                "elevation_meters": float(elevations[index]),
                "curvature": float(curvatures[index]),
                "grade": float(grades[index]),
                "projected_x_meters": round(points[index].x, PACKAGE_COORDINATE_DECIMALS),
                "projected_y_meters": round(points[index].y, PACKAGE_COORDINATE_DECIMALS),
            }
        )
    return samples


def package_chunks(edge_id: str, length_meters: float, chunk_meters: float) -> list[dict[str, Any]]:
    """The 2 km grid the collision lock uses, so runtime and collision chunks are co-indexed."""
    if chunk_meters <= 0:
        raise ValueError("chunk_meters must be positive.")
    count = max(1, math.ceil(length_meters / chunk_meters))
    chunks = []
    for index in range(count):
        start = index * chunk_meters
        end = min(length_meters, start + chunk_meters)
        chunks.append(
            {
                "chunk_id": f"{edge_id}-c{index:04d}",
                "edge_id": edge_id,
                "start_meters": float(start),
                "end_meters": float(end),
                "content_hash": "",
            }
        )
    return chunks


def lane_sections(
    segment_id: str,
    edge_id: str,
    length_meters: float,
    lock_sections: list[dict[str, Any]],
    source_id: str,
    artifact_sha256: str,
) -> list[dict[str, Any]]:
    """The lane lock's ordered sections, extended to tile the whole edge.

    The lock's sections cover the traveled span between the head and tail the
    junction movements own. This single-segment package has no movements, so
    the first section starts at 0 and the last ends at the edge length; the
    extension is recorded in each section's provenance.
    """
    if not lock_sections:
        raise ValueError(f"segment '{segment_id}' has no lane sections.")
    ordered = sorted(lock_sections, key=lambda item: float(item["start_m"]))
    result: list[dict[str, Any]] = []
    for index, section in enumerate(ordered):
        start = 0.0 if index == 0 else float(section["start_m"])
        end = length_meters if index == len(ordered) - 1 else float(section["end_m"])
        if end <= start:
            raise ValueError(f"lane section '{section['section_id']}' has an empty span.")
        derivation = (
            "AASHTO Interstate design cross-section from lane-topology-lock.v1 "
            "(ADR-0018 authored default, not observed lane geometry)"
        )
        if start != float(section["start_m"]) or end != float(section["end_m"]):
            derivation += (
                f"; span extended from [{float(section['start_m']):.3f}, "
                f"{float(section['end_m']):.3f}] to [{start:.3f}, {end:.3f}] m to cover the "
                "head and tail that junction movements own in the full chain"
            )
        provenance = _provenance(
            "derived", source_id, segment_id, artifact_sha256, derivation=derivation
        )
        lanes = [
            {
                "id": str(lane["lane_id"]),
                "index": int(lane["index"]),
                "width_meters": float(lane["width_m"]),
                "role": str(lane["role"]),
                "allowed_maneuvers": MANEUVER_CONTINUE,
                "provenance": provenance,
            }
            for lane in sorted(section["lanes"], key=lambda lane: int(lane["index"]))
        ]
        result.append(
            {
                "id": str(section["section_id"]),
                "edge_id": edge_id,
                "start_meters": start,
                "end_meters": end,
                "lanes": lanes,
                "left_shoulder": {
                    "width_meters": float(section.get("left_shoulder_m", 0.0)),
                    "kind": "paved",
                },
                "right_shoulder": {
                    "width_meters": float(section.get("right_shoulder_m", 0.0)),
                    "kind": "paved",
                },
                "signed_direction": "westbound",
                "provenance": provenance,
            }
        )
    return result


def build_continental_package_dict(
    segment_id: str,
    *,
    line: LineString,
    lane_segment: dict[str, Any],
    elevation_segment: dict[str, Any],
    conditioned_segment: dict[str, Any],
    source: dict[str, Any],
    spatial_reference: dict[str, str],
    from_anchor: str,
    to_anchor: str,
    route_system: str = "I",
    route_number: str = "70",
    design_speed_mph: float = 70.0,
    resample_meters: float = PACKAGE_RESAMPLE_METERS,
    chunk_meters: float = PACKAGE_CHUNK_METERS,
) -> dict[str, Any]:
    """Assemble the package the sharded writer takes, from already-loaded lock records."""
    eased = _lane_eased_segment_profile(elevation_segment, conditioned_segment)
    samples = edge_samples(
        line, eased, float(elevation_segment["terminal_station_m"]), resample_meters
    )
    length_meters = samples[-1]["distance_meters"]
    edge_id = f"{segment_id}--westbound"
    from_node = _stable_id("node", (segment_id, "from", from_anchor))
    to_node = _stable_id("node", (segment_id, "to", to_anchor))
    lock_sections = lane_segment["sections"]
    lane_count = len(lock_sections[0]["lanes"])
    if not 0 < lane_count < 256:
        raise ValueError(f"segment '{segment_id}' lane count {lane_count} is out of range.")
    edge = {
        "edge_id": edge_id,
        "from_node_id": from_node,
        "to_node_id": to_node,
        "length_meters": length_meters,
        "lane_count": lane_count,
        "speed_limit_mps": round(design_speed_mph * MILES_PER_HOUR_TO_METERS_PER_SECOND, 4),
        "region_id": f"continental-{segment_id}",
        "generation_profile": "interstate-graybox",
        "samples": samples,
        "source_feature_id": segment_id,
        "source_route_system": route_system,
        "source_route_number": route_number,
        "source_signed_direction": "westbound",
        "source_local_name": "",
        "source_begin_mile": None,
        "source_end_mile": None,
        "source_jurisdiction": "unknown",
        # The eastbound carriageway has no eased profile or lane sections of its
        # own yet; the reciprocal divided pair is a later slice.
        "source_roadway_kind": "one_way_roadway",
        "source_carriageway_group_id": "",
        "source_opposing_feature_id": "",
    }
    package: dict[str, Any] = {
        "schema_version": 5,
        "content_version": f"continental-{segment_id}",
        "source": dict(source),
        "spatial_reference": dict(spatial_reference),
        "nodes": [
            {"id": from_node, "kind": "route", "outgoing_edge_ids": [edge_id]},
            {"id": to_node, "kind": "route", "outgoing_edge_ids": []},
        ],
        "edges": [edge],
        "chunks": package_chunks(edge_id, length_meters, chunk_meters),
    }
    # The derived semantics give the route identity, map LODs and the empty
    # connector, exit and marker lists; the lane sections then come from the
    # lane lock rather than the graybox default the fixture build synthesises.
    attach_derived_route_semantics(package)
    sections = lane_sections(
        segment_id,
        edge_id,
        length_meters,
        lock_sections,
        str(source["source_id"]),
        str(source["sha256"]),
    )
    package["semantics"]["lane_sections"] = sections
    edge["lane_section_ids"] = [section["id"] for section in sections]
    return package


def build_continental_package(
    segment_id: str,
    *,
    collision_lock_path: Path,
    lane_lock_path: Path,
    carriageway_lock_path: Path,
    conditioned_lock_path: Path,
    elevation_lock_path: Path,
    dem_lock_path: Path,
    directed_route_lock_path: Path,
    route_lock_path: Path,
    carriageway_cache_directory: Path,
    output_directory: Path,
    resample_meters: float = PACKAGE_RESAMPLE_METERS,
    chunk_meters: float = PACKAGE_CHUNK_METERS,
) -> dict[str, Any]:
    """Build and publish the package for one segment; returns the provenance record."""
    lane = _load(lane_lock_path)
    carriageway = _load(carriageway_lock_path)
    conditioned = _load(conditioned_lock_path)
    elevation = _load(elevation_lock_path)
    dem = _load(dem_lock_path)
    directed = _load(directed_route_lock_path)
    route_lock = _load(route_lock_path)
    collision = _load(collision_lock_path)

    line = authenticated_westbound_line(segment_id, carriageway_cache_directory, carriageway, lane)
    lane_segment = _segment_record(lane, segment_id, "lane topology lock")
    elevation_segment = _segment_record(elevation, segment_id, "corridor elevation lock")
    conditioned_segment = _segment_record(conditioned, segment_id, "conditioned profile lock")
    directed_segment = _segment_record(directed, segment_id, "directed route lock")
    snapshot = next(
        (
            item
            for item in route_lock["nhpn"]["segment_snapshots"]
            if item.get("segment_id") == segment_id
        ),
        None,
    )
    if snapshot is None:
        raise ValueError(f"continental route lock has no NHPN snapshot for '{segment_id}'.")
    nhpn = route_lock["nhpn"]
    source = {
        "source_id": str(nhpn["source_id"]),
        "publisher": str(nhpn["publisher"]),
        "source_url": str(nhpn["service_url"]),
        "acquired_on": str(route_lock.get("revised_at") or route_lock.get("created_at", "")),
        "license_status": str(nhpn.get("license_status", "public_domain")),
        "sha256": str(snapshot["features_sha256"]),
        "acquisition_lock_sha256": _file_sha(route_lock_path),
    }
    family = dem["product_family"]
    spatial_reference = {
        "route_crs": PROJECTED_CRS,
        "elevation_crs": str(family["raster_crs"]),
        "horizontal_datum": str(family["horizontal_datum"]),
        "vertical_datum": str(family["vertical_datum"]),
        "elevation_units": str(family["elevation_units"]),
        "elevation_product_id": str(elevation["source"]["source_id"]),
        "elevation_product_title": str(family["dataset"]),
        "elevation_product_resolution": str(family["resolution"]),
        "elevation_artifact_sha256": str(elevation["profile_sha256"]),
    }
    defaults = lane.get("model", {}).get("defaults", {}).get("divided_carriageway", {})
    facility = str(directed_segment.get("facility") or "I-70")
    system, _, number = facility.partition("-")
    package = build_continental_package_dict(
        segment_id,
        line=line,
        lane_segment=lane_segment,
        elevation_segment=elevation_segment,
        conditioned_segment=conditioned_segment,
        source=source,
        spatial_reference=spatial_reference,
        from_anchor=str(directed_segment["from_anchor"]),
        to_anchor=str(directed_segment["to_anchor"]),
        route_system=system or "I",
        route_number=number or "unknown",
        design_speed_mph=float(defaults.get("design_speed_mph", 70.0)),
        resample_meters=resample_meters,
        chunk_meters=chunk_meters,
    )
    sharded = write_sharded_package(package, output_directory)

    host = next(
        (item for item in collision.get("hosts", []) if item.get("host_id") == segment_id),
        None,
    )
    root_pointer = _load(output_directory / "current-package.json")
    root_path = output_directory / root_pointer["root_relative_path"]
    chunk_bytes = [int(chunk["byte_count"]) for chunk in sharded["chunks"]]
    provenance = {
        "schema_version": 1,
        "segment_id": segment_id,
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content_version": sharded["content_version"],
        "route_crs": PROJECTED_CRS,
        "length_m": package["edges"][0]["length_meters"],
        "sample_count": len(package["edges"][0]["samples"]),
        "chunk_count": len(sharded["chunks"]),
        "lane_section_count": len(package["semantics"]["lane_sections"]),
        "root_bytes": root_path.stat().st_size,
        "max_chunk_bytes": max(chunk_bytes),
        "total_chunk_bytes": sum(chunk_bytes),
        "collision_host": (
            None
            if host is None
            else {
                "sample_count": host.get("sample_count"),
                "chunk_count": host.get("chunk_count"),
                "length_m": host.get("length_m"),
            }
        ),
        "lock_sha256": {
            "collision_chunk_lock": _file_sha(collision_lock_path),
            "lane_topology_lock": _file_sha(lane_lock_path),
            "westbound_carriageway_lock": _file_sha(carriageway_lock_path),
            "conditioned_profile_lock": _file_sha(conditioned_lock_path),
            "corridor_elevation_lock": _file_sha(elevation_lock_path),
            "dem_product_lock": _file_sha(dem_lock_path),
            "directed_route_lock": _file_sha(directed_route_lock_path),
            "continental_route_lock": _file_sha(route_lock_path),
        },
        "carriageway_cache_geometry_sha256": _segment_record(
            carriageway, segment_id, "westbound carriageway lock"
        )["westbound"]["geometry_sha256"],
    }
    (output_directory / PROVENANCE_FILENAME).write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return provenance
