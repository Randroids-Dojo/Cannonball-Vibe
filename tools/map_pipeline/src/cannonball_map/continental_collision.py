from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_right
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import substring

from cannonball_map.continental import _lane_eased_segment_profile

COLLISION_STATUS = "collision_ribbons_locked_package_pending"
COLLISION_SAMPLE_METERS = 25.0
COLLISION_CHUNK_METERS = 2_000.0
COLLISION_GEOMETRY_DECIMALS = 3
COLLISION_ELEVATION_DECIMALS = 2
COLLISION_MIN_CLEARANCE_METERS = 5.03
COLLISION_CLEARANCE_RAMP_METERS = 100.0


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(value: Any) -> str:
    data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stations(length: float, interval: float) -> list[float]:
    values = [round(index * interval, 3) for index in range(int(length // interval) + 1)]
    terminal = round(length, 3)
    if not values or values[-1] != terminal:
        values.append(terminal)
    return values


def _splice(
    line: LineString, start: float, end: float, coordinates: list[list[float]]
) -> LineString:
    head = list(substring(line, 0.0, start).coords)[:-1]
    tail = list(substring(line, end, line.length).coords)[1:]
    merged = head + [tuple(point) for point in coordinates] + tail
    deduped = [merged[0]]
    for point in merged[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return LineString(deduped)


def _refined_line(
    line: LineString, host_kind: str, host_id: str, lane: dict[str, Any]
) -> LineString:
    refinements = sorted(
        (
            item
            for item in lane["corner_refinements"]
            if item["host"] == {"kind": host_kind, "id": host_id}
        ),
        key=lambda item: float(item["window"]["entry_station_m"]),
        reverse=True,
    )
    for refinement in refinements:
        window = refinement["window"]
        line = _splice(
            line,
            float(window["entry_station_m"]),
            float(window["exit_station_m"]),
            refinement["geometry"]["coordinates"],
        )
    return line


def _width_at(sections: list[dict[str, Any]], station: float) -> float:
    section = next(
        (
            item
            for item in sections
            if float(item["start_m"]) - 1e-6 <= station <= float(item["end_m"]) + 1e-6
        ),
        sections[-1],
    )
    lane_width = sum(float(item["width_m"]) for item in section["lanes"])
    return (
        lane_width
        + float(section.get("left_shoulder_m", 0.0))
        + float(section.get("right_shoulder_m", 0.0))
    )


def _elevation_at(values: list[float], terminal: float, station: float) -> float:
    if len(values) == 1 or terminal <= 0:
        return float(values[0])
    scaled = max(0.0, min(len(values) - 1.0, station / terminal * (len(values) - 1)))
    index = min(int(math.floor(scaled)), len(values) - 2)
    fraction = scaled - index
    return float(values[index]) + (float(values[index + 1]) - float(values[index])) * fraction


def _points_at(line: LineString, distances: list[float]) -> list[tuple[float, float]]:
    coordinates = [tuple(point) for point in line.coords]
    cumulative = [0.0]
    for before, after in zip(coordinates, coordinates[1:], strict=False):
        cumulative.append(cumulative[-1] + math.dist(before, after))
    result: list[tuple[float, float]] = []
    for distance in distances:
        clamped = max(0.0, min(cumulative[-1], distance))
        index = min(max(0, bisect_right(cumulative, clamped) - 1), len(coordinates) - 2)
        span = cumulative[index + 1] - cumulative[index]
        fraction = 0.0 if span <= 0 else (clamped - cumulative[index]) / span
        before, after = coordinates[index], coordinates[index + 1]
        result.append(
            (
                before[0] + (after[0] - before[0]) * fraction,
                before[1] + (after[1] - before[1]) * fraction,
            )
        )
    return result


def _clearance_lift(station: float, crossings: list[float]) -> float:
    lift = 0.0
    for crossing in crossings:
        distance = abs(station - crossing)
        if distance <= COLLISION_CLEARANCE_RAMP_METERS:
            lift = max(
                lift,
                COLLISION_MIN_CLEARANCE_METERS
                * 0.5
                * (1.0 + math.cos(math.pi * distance / COLLISION_CLEARANCE_RAMP_METERS)),
            )
    return lift


def _ribbon_samples(
    line: LineString,
    sections: list[dict[str, Any]],
    elevations: list[float],
    elevation_terminal: float,
    crossings: list[float],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    stations = _stations(line.length, COLLISION_SAMPLE_METERS)
    points = _points_at(line, stations)
    before_points = _points_at(line, [max(0.0, station - 1.0) for station in stations])
    after_points = _points_at(line, [min(line.length, station + 1.0) for station in stations])
    for station, point, before, after in zip(
        stations, points, before_points, after_points, strict=True
    ):
        dx, dy = after[0] - before[0], after[1] - before[1]
        magnitude = math.hypot(dx, dy)
        if magnitude <= 0:
            raise ValueError("collision ribbon contains a zero-length tangent")
        nx, ny = -dy / magnitude, dx / magnitude
        half_width = _width_at(sections, station) / 2.0
        elevation = _elevation_at(elevations, elevation_terminal, station) + _clearance_lift(
            station, crossings
        )
        result.append(
            {
                "station_m": round(station, 3),
                "left": [
                    round(point[0] + nx * half_width, COLLISION_GEOMETRY_DECIMALS),
                    round(point[1] + ny * half_width, COLLISION_GEOMETRY_DECIMALS),
                    round(elevation, COLLISION_ELEVATION_DECIMALS),
                ],
                "right": [
                    round(point[0] - nx * half_width, COLLISION_GEOMETRY_DECIMALS),
                    round(point[1] - ny * half_width, COLLISION_GEOMETRY_DECIMALS),
                    round(elevation, COLLISION_ELEVATION_DECIMALS),
                ],
            }
        )
    return result


def _chunks(host_id: str, host_kind: str, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    start = 0
    while start < len(samples) - 1:
        first_station = float(samples[start]["station_m"])
        end = start + 1
        while (
            end + 1 < len(samples)
            and float(samples[end + 1]["station_m"])
            <= first_station + COLLISION_CHUNK_METERS + 1e-6
        ):
            end += 1
        payload = samples[start : end + 1]
        chunk_id = f"{host_id}--collision-{len(chunks):04d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "host_id": host_id,
                "host_kind": host_kind,
                "start_m": payload[0]["station_m"],
                "end_m": payload[-1]["station_m"],
                "sample_count": len(payload),
                "triangle_count": (len(payload) - 1) * 2,
                "geometry_sha256": _sha(payload),
                "entry_boundary": {"left": payload[0]["left"], "right": payload[0]["right"]},
                "exit_boundary": {"left": payload[-1]["left"], "right": payload[-1]["right"]},
            }
        )
        start = end
    return chunks


def _segment_hosts(
    lane: dict[str, Any],
    elevation: dict[str, Any],
    conditioned: dict[str, Any],
    cache_directory: Path,
) -> Iterable[tuple[str, str, LineString, list[dict[str, Any]], list[float], float, list[float]]]:
    conditioned_by_id = {item["segment_id"]: item for item in conditioned["segments"]}
    lane_segments = {item["segment_id"]: item for item in lane["segments"]}
    for record in elevation["segments"]:
        segment_id = record["segment_id"]
        cache = _load(cache_directory / f"{segment_id}.json")
        line = _refined_line(
            LineString(cache["westbound_coordinates"]), "carriageway_chain", segment_id, lane
        )
        section_record = lane_segments[segment_id]
        profile = conditioned_by_id[segment_id]
        eased = _lane_eased_segment_profile(record, profile)
        yield (
            segment_id,
            "segment",
            line,
            section_record["sections"],
            eased,
            float(record["terminal_station_m"]),
            [],
        )


def derive_continental_collision_lock(
    lane_lock_path: Path,
    carriageway_lock_path: Path,
    junction_lock_path: Path,
    connector_lock_path: Path,
    conditioned_lock_path: Path,
    elevation_lock_path: Path,
    carriageway_cache_directory: Path,
    output_path: Path,
) -> dict[str, Any]:
    lane = _load(lane_lock_path)
    junction = _load(junction_lock_path)
    connector = _load(connector_lock_path)
    conditioned = _load(conditioned_lock_path)
    elevation = _load(elevation_lock_path)
    if lane.get("status") != "lane_topology_locked_collision_package_pending":
        raise ValueError("lane topology is not ready for collision generation")

    hosts = list(_segment_hosts(lane, elevation, conditioned, carriageway_cache_directory))
    movement_lanes = {item["movement_id"]: item for item in lane["movements"]}
    separations: dict[str, list[dict[str, Any]]] = {}
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    for item in lane["grade_separations"]:
        separations.setdefault(item["movement_id"], []).append(item)
    for movement in junction["movements"]:
        movement_id = movement["movement_id"]
        line = _refined_line(
            LineString(movement["geometry"]["coordinates"]), "junction_movement", movement_id, lane
        )
        vertical = movement["vertical_context"]["boundary_elevations_m"]
        crossings = [
            line.project(Point(*transformer.transform(*item["coordinate"])))
            for item in separations.get(movement_id, [])
        ]
        hosts.append(
            (
                movement_id,
                "movement",
                line,
                movement_lanes[movement_id]["cross_sections"],
                [float(vertical[0]), float(vertical[1])],
                line.length,
                crossings,
            )
        )

    connector_lanes = {item["connector_id"]: item for item in lane["endpoint_connectors"]}
    conditioned_by_id = {item["segment_id"]: item for item in conditioned["segments"]}
    elevation_by_id = {item["segment_id"]: item for item in elevation["segments"]}
    for record in connector["connectors"]:
        connector_id = record["connector_id"]
        coordinates = [
            transformer.transform(item["longitude"], item["latitude"])
            for item in record["waypoints"]
        ]
        line = _refined_line(LineString(coordinates), "endpoint_connector", connector_id, lane)
        attachment = connector_lanes[connector_id]["attachment"]
        profile = _lane_eased_segment_profile(
            elevation_by_id[attachment["segment_id"]],
            conditioned_by_id[attachment["segment_id"]],
        )
        boundary = float(profile[0] if attachment["end"] == "from" else profile[-1])
        lane_record = connector_lanes[connector_id]
        section = {
            "start_m": 0.0,
            "end_m": round(line.length, 3),
            "lanes": lane_record["lanes"],
            "left_shoulder_m": lane_record["left_shoulder_m"],
            "right_shoulder_m": lane_record["right_shoulder_m"],
        }
        hosts.append(
            (connector_id, "endpoint_connector", line, [section], [boundary], line.length, [])
        )

    host_records: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []
    for host_id, host_kind, line, sections, elevations, terminal, crossings in hosts:
        samples = _ribbon_samples(line, sections, elevations, terminal, crossings)
        chunks = _chunks(host_id, host_kind, samples)
        for previous, current in zip(chunks, chunks[1:], strict=False):
            if previous["exit_boundary"] != current["entry_boundary"]:
                raise ValueError(f"collision chunk seam drifted for '{host_id}'")
        all_chunks.extend(chunks)
        host_records.append(
            {
                "host_id": host_id,
                "host_kind": host_kind,
                "length_m": round(line.length, 3),
                "sample_count": len(samples),
                "chunk_count": len(chunks),
                "triangle_count": sum(item["triangle_count"] for item in chunks),
                "geometry_sha256": _sha(samples),
                "clearance_crossing_count": len(crossings),
            }
        )

    payload = {
        "schema_version": 1,
        "status": COLLISION_STATUS,
        "derived_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coordinate_crs": "EPSG:5070",
        "model": {
            "decision": "ADR-0018",
            "sample_interval_m": COLLISION_SAMPLE_METERS,
            "chunk_length_m": COLLISION_CHUNK_METERS,
            "geometry_decimals": COLLISION_GEOMETRY_DECIMALS,
            "elevation_decimals": COLLISION_ELEVATION_DECIMALS,
            "surface": "two-triangle road ribbon between lane-and-shoulder boundaries",
            "clearance_ramp_m": COLLISION_CLEARANCE_RAMP_METERS,
        },
        "lane_topology_lock_sha256": _file_sha(lane_lock_path),
        "westbound_carriageway_lock_sha256": _file_sha(carriageway_lock_path),
        "junction_geometry_lock_sha256": _file_sha(junction_lock_path),
        "endpoint_connector_lock_sha256": _file_sha(connector_lock_path),
        "conditioned_profile_lock_sha256": _file_sha(conditioned_lock_path),
        "corridor_elevation_lock_sha256": _file_sha(elevation_lock_path),
        "grade_separations": lane["grade_separations"],
        "hosts": sorted(host_records, key=lambda item: (item["host_kind"], item["host_id"])),
        "chunks": sorted(
            all_chunks, key=lambda item: (item["host_kind"], item["host_id"], item["start_m"])
        ),
    }
    payload["hosts_sha256"] = _sha(payload["hosts"])
    payload["chunks_sha256"] = _sha(payload["chunks"])
    payload["summary"] = {
        "host_count": len(host_records),
        "segment_count": sum(item["host_kind"] == "segment" for item in host_records),
        "movement_count": sum(item["host_kind"] == "movement" for item in host_records),
        "endpoint_connector_count": sum(
            item["host_kind"] == "endpoint_connector" for item in host_records
        ),
        "chunk_count": len(all_chunks),
        "triangle_count": sum(item["triangle_count"] for item in all_chunks),
        "open_chunk_seams": 0,
        "grade_separation_count": len(lane["grade_separations"]),
    }
    validate_continental_collision_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_continental_collision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != COLLISION_STATUS or payload.get("schema_version") != 1:
        raise ValueError("collision lock status or schema is invalid")
    if payload.get("hosts_sha256") != _sha(payload.get("hosts")):
        raise ValueError("collision host digest does not reproduce")
    if payload.get("chunks_sha256") != _sha(payload.get("chunks")):
        raise ValueError("collision chunk digest does not reproduce")
    chunks_by_host: dict[str, list[dict[str, Any]]] = {}
    for chunk in payload["chunks"]:
        chunks_by_host.setdefault(chunk["host_id"], []).append(chunk)
        if chunk["sample_count"] < 2 or chunk["triangle_count"] != (chunk["sample_count"] - 1) * 2:
            raise ValueError(f"collision chunk '{chunk['chunk_id']}' has invalid topology")
        if (
            float(chunk["end_m"]) - float(chunk["start_m"])
            > COLLISION_CHUNK_METERS + COLLISION_SAMPLE_METERS
        ):
            raise ValueError(f"collision chunk '{chunk['chunk_id']}' exceeds its length budget")
    for host_id, chunks in chunks_by_host.items():
        ordered = sorted(chunks, key=lambda item: float(item["start_m"]))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if (
                previous["end_m"] != current["start_m"]
                or previous["exit_boundary"] != current["entry_boundary"]
            ):
                raise ValueError(f"collision chunk seam is open for '{host_id}'")
    summary = payload["summary"]
    if summary["host_count"] != len(payload["hosts"]) or summary["chunk_count"] != len(
        payload["chunks"]
    ):
        raise ValueError("collision summary counts do not reproduce")
    if summary["open_chunk_seams"] != 0 or summary["grade_separation_count"] != len(
        payload["grade_separations"]
    ):
        raise ValueError("collision summary gate claims do not reproduce")
    return payload


def validate_continental_collision_lock(
    path: Path,
    lane_lock_path: Path | None = None,
    carriageway_lock_path: Path | None = None,
    junction_lock_path: Path | None = None,
    connector_lock_path: Path | None = None,
    conditioned_lock_path: Path | None = None,
    elevation_lock_path: Path | None = None,
) -> dict[str, Any]:
    payload = validate_continental_collision_payload(_load(path))
    ancestry = {
        "lane_topology_lock_sha256": lane_lock_path,
        "westbound_carriageway_lock_sha256": carriageway_lock_path,
        "junction_geometry_lock_sha256": junction_lock_path,
        "endpoint_connector_lock_sha256": connector_lock_path,
        "conditioned_profile_lock_sha256": conditioned_lock_path,
        "corridor_elevation_lock_sha256": elevation_lock_path,
    }
    for field, source in ancestry.items():
        if source is not None and payload.get(field) != _file_sha(source):
            raise ValueError(f"collision ancestry digest '{field}' does not match")
    return payload
