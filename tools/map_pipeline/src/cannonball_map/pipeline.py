from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, MultiLineString
from shapely.ops import substring

from cannonball_map.elevation import ElevationSampler
from cannonball_map.manifest import SourceManifest, validate_source
from cannonball_map.models import PipelineChunk, PipelineEdge, RouteSample
from cannonball_map.semantics import attach_derived_route_semantics

PROJECTED_CRS = "EPSG:5070"
SOURCE_ID_COLUMNS = ("source_feature_id", "source_id", "id", "objectid")
MAXIMUM_CONDITIONED_GRADE = 0.07
ELEVATION_MEDIAN_WINDOW_SAMPLES = 9
ALIGNMENT_TRANSITION_MAX_METERS = 150.0
ALIGNMENT_TRANSITION_EDGE_FRACTION = 0.35
ALIGNMENT_TRANSITION_MIN_METERS = 10.0
ALIGNMENT_MIN_DEFLECTION_DEGREES = 0.25
ALIGNMENT_CURVE_SAMPLES = 33
CORRIDOR_ALIGNMENT_SAMPLE_METERS = 10.0
CORRIDOR_ALIGNMENT_GUIDE_TOLERANCE_METERS = 50.0
CORRIDOR_ALIGNMENT_SIGMA_METERS = 50.0
CORRIDOR_ALIGNMENT_RADIUS_METERS = 150.0
CORRIDOR_ALIGNMENT_MAX_OFFSET_METERS = 35.0


@dataclass(frozen=True)
class _SourceLineRecord:
    source_feature_id: str
    geometry: LineString
    semantic_hints: dict[str, object]


@dataclass(frozen=True)
class _EdgeRecord:
    source_feature_id: str
    geometry: LineString
    edge: PipelineEdge
    semantic_hints: dict[str, object]

    def edge_dict(self) -> dict[str, object]:
        return {
            "source_feature_id": self.source_feature_id,
            **self.semantic_hints,
            **self.edge.to_dict(),
        }


def build_route_graph(
    source_path: Path,
    manifest_path: Path,
    output_directory: Path,
    *,
    resample_meters: float = 25.0,
    chunk_meters: float = 2_000.0,
    snap_tolerance_meters: float = 10.0,
    catalog_path: Path | None = None,
    elevation_sampler: ElevationSampler | None = None,
    acquisition_lock_sha256: str = "",
) -> dict[str, object]:
    manifest = SourceManifest.load(manifest_path)
    validate_source(manifest, source_path, catalog_path)
    frame = gpd.read_file(source_path)
    if frame.crs is None:
        raise ValueError("Source geometry must declare a coordinate reference system.")
    frame = frame.to_crs(PROJECTED_CRS)

    source_id_column = _source_id_column(frame)
    source_records: list[_SourceLineRecord] = []
    for _, row in frame.iterrows():
        geometry = row.geometry
        line_parts = _line_parts(geometry)
        if not line_parts:
            continue
        source_feature_id = _source_feature_id(row, source_id_column)
        for line in line_parts:
            if line.length <= 0:
                continue
            snapped_geometry = _snap_line_endpoints(line, snap_tolerance_meters)
            if snapped_geometry.length <= 0:
                raise ValueError("Endpoint snapping collapsed a source line to zero length.")
            source_records.append(
                _SourceLineRecord(
                    source_feature_id,
                    snapped_geometry,
                    _semantic_hints(row),
                )
            )
    if not source_records:
        raise ValueError("Source contains no line geometry.")

    source_records = _reconstruct_continuation_alignments(source_records)
    records = [
        _EdgeRecord(
            record.source_feature_id,
            record.geometry,
            _build_edge(
                record.geometry,
                manifest.source_id,
                record.source_feature_id,
                resample_meters,
                snap_tolerance_meters,
                elevation_sampler,
            ),
            record.semantic_hints,
        )
        for record in source_records
    ]

    records.sort(key=lambda record: record.edge.edge_id)
    if elevation_sampler is not None and len(records) > 1:
        records = _condition_linear_corridor_elevations(records)
    edges = [record.edge for record in records]
    _validate_topology(edges)
    _validate_endpoint_geometry(records)
    chunks = _partition(edges, chunk_meters)
    content_version = _content_version(
        manifest,
        records,
        chunks,
        elevation_sampler,
        acquisition_lock_sha256,
    )
    package = {
        "schema_version": 5,
        "content_version": content_version,
        "source": {
            "source_id": manifest.source_id,
            "publisher": manifest.publisher,
            "source_url": manifest.source_url,
            "acquired_on": manifest.acquired_on,
            "license_status": manifest.license_status,
            "sha256": manifest.sha256,
            "acquisition_lock_sha256": acquisition_lock_sha256,
        },
        "spatial_reference": _spatial_reference(elevation_sampler),
        "nodes": _nodes(edges),
        "edges": [record.edge_dict() for record in records],
        "chunks": [chunk.to_dict() for chunk in chunks],
    }
    attach_derived_route_semantics(package)

    output_directory.mkdir(parents=True, exist_ok=True)
    package_path = output_directory / "route_graph.json"
    package_path.write_text(
        json.dumps(package, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    normalized = gpd.GeoDataFrame(
        [
            {
                "edge_id": record.edge.edge_id,
                "source_feature_id": record.source_feature_id,
                "from_node_id": record.edge.from_node_id,
                "to_node_id": record.edge.to_node_id,
                "geometry": record.geometry,
            }
            for record in records
        ],
        crs=PROJECTED_CRS,
    )
    normalized_path = output_directory / "normalized.gpkg"
    normalized.to_file(normalized_path, layer="route_edges", driver="GPKG")
    _write_semantic_audit_tables(normalized_path, package["semantics"])
    _normalize_geopackage(normalized_path)
    return package


def _write_semantic_audit_tables(path: Path, semantics: dict[str, Any]) -> None:
    table_names = {
        "lane_sections": "route_lane_sections",
        "junction_connectors": "route_junction_connectors",
        "route_identities": "route_identities",
        "exits": "route_exits",
        "milepoint_anchors": "route_milepoint_anchors",
        "roadside_markers": "route_roadside_markers",
        "simplified_map_geometry": "route_simplified_map_geometry",
    }
    with sqlite3.connect(path) as connection:
        for key, table_name in table_names.items():
            connection.execute(
                f"CREATE TABLE {table_name} "
                "(record_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
            )
            records = semantics[key]
            normalized = []
            for record in records:
                record_id = str(record.get("id") or f"{record['edge_id']}:lod-{record['lod']}")
                payload = json.dumps(record, separators=(",", ":"), sort_keys=True)
                normalized.append((record_id, payload))
            connection.executemany(
                f"INSERT INTO {table_name} (record_id, payload_json) VALUES (?, ?)",
                sorted(normalized),
            )
        connection.commit()


def _normalize_geopackage(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE gpkg_contents SET last_change = ?",
            ("1970-01-01T00:00:00.000Z",),
        )
        connection.commit()
        connection.execute("VACUUM")
    # SQLite increments both header counters when GDAL reuses a process-level
    # connection. They do not describe route content, but otherwise make two
    # semantically identical GeoPackages differ at bytes 24-27 and 92-95.
    with path.open("r+b") as geopackage:
        fixed_counter = (1).to_bytes(4, "big")
        geopackage.seek(24)
        geopackage.write(fixed_counter)
        geopackage.seek(92)
        geopackage.write(fixed_counter)


def _build_edge(
    line: LineString,
    dataset_source_id: str,
    source_feature_id: str,
    resample_meters: float,
    snap_tolerance_meters: float,
    elevation_sampler: ElevationSampler | None,
) -> PipelineEdge:
    start = _snap(line.coords[0], snap_tolerance_meters)
    end = _snap(line.coords[-1], snap_tolerance_meters)
    from_node_id = _stable_id("node", start)
    to_node_id = _stable_id("node", end)
    canonical = (
        dataset_source_id,
        source_feature_id,
        tuple(round(value, 3) for coordinate in line.coords for value in coordinate),
        from_node_id,
        to_node_id,
    )
    edge_id = _stable_id("edge", canonical)
    distances = _sample_distances(line.length, resample_meters)
    points = [line.interpolate(distance) for distance in distances]
    curvatures = _curvatures(points)
    elevations = [
        elevation_sampler.sample(point.x, point.y)
        if elevation_sampler is not None
        else (point.z if point.has_z else 0.0)
        for point in points
    ]
    grades = _grades(distances, elevations)
    samples = [
        RouteSample(
            distance,
            0.0,
            elevations[index],
            curvatures[index],
            grades[index],
            points[index].x,
            points[index].y,
        )
        for index, distance in enumerate(distances)
    ]
    return PipelineEdge(
        edge_id=edge_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        length_meters=line.length,
        lane_count=2,
        speed_limit_mps=31.2928,
        region_id="unassigned",
        generation_profile="interstate-graybox",
        samples=tuple(samples),
    )


def _nodes(edges: list[PipelineEdge]) -> list[dict[str, object]]:
    outgoing: dict[str, list[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.from_node_id, []).append(edge.edge_id)
        outgoing.setdefault(edge.to_node_id, [])
    return [
        {
            "id": node_id,
            "kind": "junction" if len(edge_ids) > 1 else "route",
            "outgoing_edge_ids": sorted(edge_ids),
        }
        for node_id, edge_ids in sorted(outgoing.items())
    ]


def _partition(edges: list[PipelineEdge], chunk_meters: float) -> list[PipelineChunk]:
    chunks: list[PipelineChunk] = []
    for edge in edges:
        count = max(1, math.ceil(edge.length_meters / chunk_meters))
        for index in range(count):
            start = index * chunk_meters
            end = min(edge.length_meters, start + chunk_meters)
            key = f"{edge.edge_id}:{start:.3f}:{end:.3f}".encode()
            chunks.append(
                PipelineChunk(
                    chunk_id=f"{edge.edge_id}-c{index:04d}",
                    edge_id=edge.edge_id,
                    start_meters=start,
                    end_meters=end,
                    content_hash=hashlib.sha256(key).hexdigest(),
                )
            )
    return chunks


def _validate_topology(edges: list[PipelineEdge]) -> None:
    graph = nx.MultiDiGraph()
    for edge in edges:
        graph.add_edge(edge.from_node_id, edge.to_node_id, key=edge.edge_id)
    if graph.number_of_edges() != len(edges):
        raise ValueError("Duplicate route edge ID collapsed during topology validation.")
    if not nx.is_weakly_connected(graph):
        raise ValueError("Selected route data is disconnected after endpoint snapping.")


def _validate_endpoint_geometry(records: list[_EdgeRecord]) -> None:
    coordinates_by_node: dict[str, tuple[float, ...]] = {}
    for record in records:
        endpoints = (
            (record.edge.from_node_id, record.geometry.coords[0]),
            (record.edge.to_node_id, record.geometry.coords[-1]),
        )
        for node_id, coordinate in endpoints:
            point = tuple(coordinate)
            existing = coordinates_by_node.setdefault(node_id, point)
            if existing != point:
                raise ValueError(
                    f"Node '{node_id}' has emitted geometry endpoints that do not meet."
                )


def _sample_distances(length: float, spacing: float) -> list[float]:
    if spacing <= 0:
        raise ValueError("resample_meters must be positive.")
    result = [index * spacing for index in range(int(length // spacing) + 1)]
    if not math.isclose(result[-1], length):
        result.append(length)
    return result


def _snap(coordinate: tuple[float, ...], tolerance: float) -> tuple[float, float]:
    if tolerance <= 0:
        raise ValueError("snap_tolerance_meters must be positive.")
    return (
        round(coordinate[0] / tolerance) * tolerance,
        round(coordinate[1] / tolerance) * tolerance,
    )


def _snap_line_endpoints(line: LineString, tolerance: float) -> LineString:
    coordinates = list(line.coords)
    start = _snap(coordinates[0], tolerance)
    end = _snap(coordinates[-1], tolerance)
    while len(coordinates) > 2 and math.dist(coordinates[1][:2], start) <= tolerance:
        del coordinates[1]
    while len(coordinates) > 2 and math.dist(coordinates[-2][:2], end) <= tolerance:
        del coordinates[-2]
    coordinates[0] = (*start, *coordinates[0][2:])
    coordinates[-1] = (*end, *coordinates[-1][2:])
    return LineString(coordinates)


def _reconstruct_continuation_alignments(
    records: list[_SourceLineRecord],
) -> list[_SourceLineRecord]:
    """Replace angle points with a sampled, curvature-conditioned alignment."""
    corridor = _reconstruct_linear_corridor_alignment(records)
    if corridor is not None:
        return corridor

    incoming_by_node: dict[tuple[float, float], list[int]] = {}
    outgoing_by_node: dict[tuple[float, float], list[int]] = {}
    for index, record in enumerate(records):
        start = tuple(record.geometry.coords[0][:2])
        end = tuple(record.geometry.coords[-1][:2])
        outgoing_by_node.setdefault(start, []).append(index)
        incoming_by_node.setdefault(end, []).append(index)

    start_replacements: dict[int, tuple[float, list[tuple[float, float]]]] = {}
    end_replacements: dict[int, tuple[float, list[tuple[float, float]]]] = {}
    for node in sorted(incoming_by_node.keys() & outgoing_by_node.keys()):
        incoming_indices = incoming_by_node[node]
        outgoing_indices = outgoing_by_node[node]
        if len(incoming_indices) != 1 or len(outgoing_indices) != 1:
            continue
        incoming_index = incoming_indices[0]
        outgoing_index = outgoing_indices[0]
        if incoming_index == outgoing_index:
            continue
        incoming = records[incoming_index].geometry
        outgoing = records[outgoing_index].geometry
        transition_meters = min(
            ALIGNMENT_TRANSITION_MAX_METERS,
            incoming.length * ALIGNMENT_TRANSITION_EDGE_FRACTION,
            outgoing.length * ALIGNMENT_TRANSITION_EDGE_FRACTION,
        )
        if transition_meters < ALIGNMENT_TRANSITION_MIN_METERS:
            continue

        incoming_cut_distance = incoming.length - transition_meters
        outgoing_cut_distance = transition_meters
        incoming_cut = incoming.interpolate(incoming_cut_distance)
        outgoing_cut = outgoing.interpolate(outgoing_cut_distance)
        tangent_sample_meters = min(5.0, transition_meters / 2)
        incoming_before = incoming.interpolate(
            max(0.0, incoming_cut_distance - tangent_sample_meters)
        )
        outgoing_after = outgoing.interpolate(
            min(outgoing.length, outgoing_cut_distance + tangent_sample_meters)
        )
        incoming_tangent = _unit_direction(incoming_before, incoming_cut)
        outgoing_tangent = _unit_direction(outgoing_cut, outgoing_after)
        deflection = math.degrees(
            math.acos(
                max(
                    -1.0,
                    min(
                        1.0,
                        incoming_tangent[0] * outgoing_tangent[0]
                        + incoming_tangent[1] * outgoing_tangent[1],
                    ),
                )
            )
        )
        if deflection < ALIGNMENT_MIN_DEFLECTION_DEGREES:
            continue

        curve = _quintic_transition_curve(
            (incoming_cut.x, incoming_cut.y),
            incoming_tangent,
            (outgoing_cut.x, outgoing_cut.y),
            outgoing_tangent,
        )
        if not LineString(curve).is_simple:
            raise ValueError(
                f"Continuation at {node} cannot be reconstructed without a self-intersection."
            )
        midpoint = ALIGNMENT_CURVE_SAMPLES // 2
        end_replacements[incoming_index] = (
            incoming_cut_distance,
            curve[: midpoint + 1],
        )
        start_replacements[outgoing_index] = (
            outgoing_cut_distance,
            curve[midpoint:],
        )

    rebuilt: list[_SourceLineRecord] = []
    for index, record in enumerate(records):
        if index not in start_replacements and index not in end_replacements:
            rebuilt.append(record)
            continue
        line = record.geometry
        start_distance, start_curve = start_replacements.get(
            index,
            (0.0, [tuple(line.coords[0][:2])]),
        )
        end_distance, end_curve = end_replacements.get(
            index,
            (line.length, [tuple(line.coords[-1][:2])]),
        )
        if start_distance >= end_distance:
            raise ValueError(
                f"Source feature '{record.source_feature_id}' is too short for its "
                "continuation transitions."
            )
        middle = substring(line, start_distance, end_distance)
        if not isinstance(middle, LineString):
            raise ValueError("Continuation reconstruction produced no middle alignment.")
        coordinates = list(start_curve)
        _extend_distinct(coordinates, [tuple(point[:2]) for point in middle.coords])
        _extend_distinct(coordinates, end_curve)
        rebuilt.append(replace(record, geometry=LineString(coordinates)))
    return rebuilt


def _reconstruct_linear_corridor_alignment(
    records: list[_SourceLineRecord],
) -> list[_SourceLineRecord] | None:
    ordered_indices = _ordered_linear_source_indices(records)
    if ordered_indices is None or len(ordered_indices) < 2:
        return None
    if any(
        len(coordinate) > 2
        for record in records
        for coordinate in record.geometry.coords
    ):
        return None

    ordered = [records[index] for index in ordered_indices]
    boundary_deflections = []
    for incoming, outgoing in zip(ordered, ordered[1:], strict=False):
        incoming_tangent = _unit_direction(
            incoming.geometry.interpolate(max(0.0, incoming.geometry.length - 5.0)),
            incoming.geometry.interpolate(incoming.geometry.length),
        )
        outgoing_tangent = _unit_direction(
            outgoing.geometry.interpolate(0.0),
            outgoing.geometry.interpolate(min(5.0, outgoing.geometry.length)),
        )
        dot = max(
            -1.0,
            min(
                1.0,
                incoming_tangent[0] * outgoing_tangent[0]
                + incoming_tangent[1] * outgoing_tangent[1],
            ),
        )
        boundary_deflections.append(math.degrees(math.acos(dot)))
    if max(boundary_deflections, default=0.0) < ALIGNMENT_MIN_DEFLECTION_DEGREES:
        return list(records)

    coordinates: list[tuple[float, float]] = []
    boundary_distances = [0.0]
    for record in ordered:
        _extend_distinct(
            coordinates,
            [tuple(coordinate[:2]) for coordinate in record.geometry.coords],
        )
        boundary_distances.append(boundary_distances[-1] + record.geometry.length)
    raw_alignment = LineString(coordinates)
    total_distance = boundary_distances[-1]
    if total_distance < CORRIDOR_ALIGNMENT_RADIUS_METERS * 2:
        return None
    design_guide = raw_alignment.simplify(
        CORRIDOR_ALIGNMENT_GUIDE_TOLERANCE_METERS,
        preserve_topology=False,
    )
    if not isinstance(design_guide, LineString) or len(design_guide.coords) < 2:
        raise ValueError("Corridor design guide collapsed during alignment simplification.")
    design_distance_ratio = design_guide.length / total_distance
    sample_distances = sorted(
        {
            *_sample_distances(total_distance, CORRIDOR_ALIGNMENT_SAMPLE_METERS),
            *boundary_distances,
        }
    )
    start_tangent = _unit_direction(
        design_guide.interpolate(0.0),
        design_guide.interpolate(
            min(CORRIDOR_ALIGNMENT_SAMPLE_METERS * design_distance_ratio, design_guide.length)
        ),
    )
    end_tangent = _unit_direction(
        design_guide.interpolate(
            max(0.0, design_guide.length - CORRIDOR_ALIGNMENT_SAMPLE_METERS * design_distance_ratio)
        ),
        design_guide.interpolate(design_guide.length),
    )

    def extended_point(distance: float) -> tuple[float, float]:
        if distance < 0.0:
            start = design_guide.coords[0]
            return (
                start[0] + start_tangent[0] * distance,
                start[1] + start_tangent[1] * distance,
            )
        if distance > total_distance:
            end = design_guide.coords[-1]
            extension = distance - total_distance
            return (
                end[0] + end_tangent[0] * extension,
                end[1] + end_tangent[1] * extension,
            )
        point = design_guide.interpolate(distance * design_distance_ratio)
        return point.x, point.y

    stencil_count = round(
        CORRIDOR_ALIGNMENT_RADIUS_METERS / CORRIDOR_ALIGNMENT_SAMPLE_METERS
    )
    stencil = [
        (
            offset * CORRIDOR_ALIGNMENT_SAMPLE_METERS,
            math.exp(
                -0.5
                * (
                    offset
                    * CORRIDOR_ALIGNMENT_SAMPLE_METERS
                    / CORRIDOR_ALIGNMENT_SIGMA_METERS
                )
                ** 2
            ),
        )
        for offset in range(-stencil_count, stencil_count + 1)
    ]
    weight_sum = sum(weight for _, weight in stencil)
    smoothed_points: list[tuple[float, float]] = []
    for distance in sample_distances:
        raw_point = extended_point(distance)
        smoothed = (
            sum(extended_point(distance + offset)[0] * weight for offset, weight in stencil)
            / weight_sum,
            sum(extended_point(distance + offset)[1] * weight for offset, weight in stencil)
            / weight_sum,
        )
        displacement = math.dist(raw_point, smoothed)
        if displacement > CORRIDOR_ALIGNMENT_MAX_OFFSET_METERS:
            ratio = CORRIDOR_ALIGNMENT_MAX_OFFSET_METERS / displacement
            smoothed = (
                raw_point[0] + (smoothed[0] - raw_point[0]) * ratio,
                raw_point[1] + (smoothed[1] - raw_point[1]) * ratio,
            )
        if math.isclose(distance, 0.0) or math.isclose(distance, total_distance):
            smoothed = raw_point
        smoothed_points.append(smoothed)

    smoothed_alignment = LineString(smoothed_points)
    if not smoothed_alignment.is_simple:
        raise ValueError("Corridor alignment reconstruction produced a self-intersection.")

    rebuilt_by_index: dict[int, _SourceLineRecord] = {}
    for order, record_index in enumerate(ordered_indices):
        start_distance = boundary_distances[order]
        end_distance = boundary_distances[order + 1]
        edge_points = [
            point
            for distance, point in zip(sample_distances, smoothed_points, strict=True)
            if start_distance <= distance <= end_distance
        ]
        if len(edge_points) < 2:
            raise ValueError("Corridor reconstruction emitted an empty source edge.")
        rebuilt_by_index[record_index] = replace(
            records[record_index],
            geometry=LineString(edge_points),
        )
    return [rebuilt_by_index[index] for index in range(len(records))]


def _ordered_linear_source_indices(
    records: list[_SourceLineRecord],
) -> list[int] | None:
    by_from: dict[tuple[float, float], list[int]] = {}
    destinations = {tuple(record.geometry.coords[-1][:2]) for record in records}
    for index, record in enumerate(records):
        start = tuple(record.geometry.coords[0][:2])
        by_from.setdefault(start, []).append(index)
    starts = [
        index
        for index, record in enumerate(records)
        if tuple(record.geometry.coords[0][:2]) not in destinations
    ]
    if len(starts) != 1:
        return None
    remaining = set(range(len(records)))
    ordered: list[int] = []
    current = starts[0]
    while True:
        ordered.append(current)
        remaining.remove(current)
        if not remaining:
            return ordered
        node = tuple(records[current].geometry.coords[-1][:2])
        candidates = [index for index in by_from.get(node, []) if index in remaining]
        if len(candidates) != 1:
            return None
        current = candidates[0]


def _unit_direction(before: Any, after: Any) -> tuple[float, float]:
    delta_x = after.x - before.x
    delta_y = after.y - before.y
    magnitude = math.hypot(delta_x, delta_y)
    if magnitude <= 1e-9:
        raise ValueError("Continuation alignment has a zero-length tangent sample.")
    return delta_x / magnitude, delta_y / magnitude


def _quintic_transition_curve(
    start: tuple[float, float],
    start_tangent: tuple[float, float],
    end: tuple[float, float],
    end_tangent: tuple[float, float],
) -> list[tuple[float, float]]:
    chord = math.dist(start, end)
    if chord <= 1e-9:
        raise ValueError("Continuation transition endpoints are coincident.")
    start_velocity = start_tangent[0] * chord, start_tangent[1] * chord
    end_velocity = end_tangent[0] * chord, end_tangent[1] * chord
    result: list[tuple[float, float]] = []
    for index in range(ALIGNMENT_CURVE_SAMPLES):
        t = index / (ALIGNMENT_CURVE_SAMPLES - 1)
        t2 = t * t
        t3 = t2 * t
        t4 = t3 * t
        t5 = t4 * t
        h00 = 1 - 10 * t3 + 15 * t4 - 6 * t5
        h10 = t - 6 * t3 + 8 * t4 - 3 * t5
        h01 = 10 * t3 - 15 * t4 + 6 * t5
        h11 = -4 * t3 + 7 * t4 - 3 * t5
        result.append(
            (
                h00 * start[0] + h10 * start_velocity[0] + h01 * end[0] + h11 * end_velocity[0],
                h00 * start[1] + h10 * start_velocity[1] + h01 * end[1] + h11 * end_velocity[1],
            )
        )
    return result


def _extend_distinct(
    destination: list[tuple[float, float]],
    coordinates: list[tuple[float, float]],
) -> None:
    for coordinate in coordinates:
        if not destination or math.dist(destination[-1], coordinate) > 1e-8:
            destination.append(coordinate)


def _line_parts(geometry: object) -> tuple[LineString, ...]:
    if isinstance(geometry, LineString):
        return (geometry,)
    if isinstance(geometry, MultiLineString):
        return tuple(geometry.geoms)
    return ()


def _source_id_column(frame: gpd.GeoDataFrame) -> Any | None:
    columns = {str(column).casefold(): column for column in frame.columns}
    return next((columns[name] for name in SOURCE_ID_COLUMNS if name in columns), None)


def _source_feature_id(row: Any, column: Any | None) -> str:
    if column is None:
        raise ValueError(
            "Source features require a stable source_feature_id, source_id, id, or OBJECTID column."
        )
    value = str(row[column]).strip()
    if not value or value.casefold() in {"<na>", "nan", "none"}:
        raise ValueError(f"Source feature has no value for identifier column '{column}'.")
    return value


def _semantic_hints(row: Any) -> dict[str, object]:
    sign_type = _clean_source_value(row, "SIGNT1")
    route_system = {
        "I": "I",
        "U": "US",
        "S": "CO",
    }.get(sign_type, "unknown")
    route_number = _clean_source_value(row, "SIGNN1") or _clean_source_value(row, "ROUTE_ID")
    return {
        "source_route_system": route_system,
        "source_route_number": route_number or "unknown",
        "source_signed_direction": _clean_source_value(row, "SIGNQ1") or "unspecified",
        "source_local_name": _clean_source_value(row, "LNAME"),
        "source_begin_mile": _optional_source_number(row, "BEGMP"),
        "source_end_mile": _optional_source_number(row, "ENDMP"),
        "source_jurisdiction": _clean_source_value(row, "STFIPS") or "unknown",
        "source_roadway_kind": _clean_source_value(row, "ROADWAY_KIND") or "unclassified",
        "source_carriageway_group_id": _clean_source_value(row, "CARRIAGEWAY_ID"),
        "source_opposing_feature_id": _clean_source_value(row, "OPPOSING_ID"),
    }


def _clean_source_value(row: Any, field: str) -> str:
    try:
        value = str(row[field]).strip()
    except (KeyError, TypeError):
        return ""
    return "" if value.casefold() in {"<na>", "nan", "none"} else value


def _optional_source_number(row: Any, field: str) -> float | None:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _stable_id(prefix: str, value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:20]}"


def _content_version(
    manifest: SourceManifest,
    records: list[_EdgeRecord],
    chunks: list[PipelineChunk],
    elevation_sampler: ElevationSampler | None,
    acquisition_lock_sha256: str,
) -> str:
    payload = {
        "source_sha256": manifest.sha256,
        "edges": [record.edge_dict() for record in records],
        "chunks": [chunk.to_dict() for chunk in chunks],
        "spatial_reference": _spatial_reference(elevation_sampler),
        "acquisition_lock_sha256": acquisition_lock_sha256,
    }
    digest = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    schema_version = 2 if elevation_sampler else 1
    return f"route-v{schema_version}-{digest[:16]}"


def _angle_delta(first: float, second: float) -> float:
    return (second - first + math.pi) % (2 * math.pi) - math.pi


def _curvatures(points: list[Any]) -> list[float]:
    if len(points) < 3:
        return [0.0] * len(points)
    result: list[float] = []
    for index in range(len(points)):
        center = min(max(index, 1), len(points) - 2)
        before = points[center - 1]
        point = points[center]
        after = points[center + 1]
        incoming_heading = math.atan2(point.y - before.y, point.x - before.x)
        outgoing_heading = math.atan2(after.y - point.y, after.x - point.x)
        average_segment_length = max(
            1e-9,
            (point.distance(before) + point.distance(after)) / 2,
        )
        result.append(
            _angle_delta(incoming_heading, outgoing_heading) / average_segment_length
        )
    return result


def _grades(distances: list[float], elevations: list[float]) -> list[float]:
    if len(distances) == 1:
        return [0.0]
    result: list[float] = []
    for index in range(len(distances)):
        before = max(0, index - 1)
        after = min(len(distances) - 1, index + 1)
        run = distances[after] - distances[before]
        result.append(0.0 if run == 0 else (elevations[after] - elevations[before]) / run)
    return result


def _condition_linear_corridor_elevations(
    records: list[_EdgeRecord],
) -> list[_EdgeRecord]:
    """Remove local surface-model spikes on a single directed highway corridor.

    NHPN centerlines can pass beside structures represented in the 3DEP surface
    model. A corridor-wide median followed by a deterministic Lipschitz projection
    preserves broad elevation change while preventing impossible road grades and
    keeping shared edge endpoints identical. Branched graphs remain raw only when
    they already satisfy the ceiling; otherwise they fail until their route-choice
    elevation contract is defined.
    """
    ordered = _ordered_linear_records(records)
    if ordered is None:
        maximum_raw_grade = max(
            abs(sample.grade) for record in records for sample in record.edge.samples
        )
        if maximum_raw_grade > MAXIMUM_CONDITIONED_GRADE:
            raise ValueError(
                "Branched elevation graph exceeds the grade ceiling and needs "
                "branch-aware conditioning."
            )
        return records

    global_distances: list[float] = []
    raw_elevations: list[float] = []
    sample_indices: dict[str, list[int]] = {}
    offset = 0.0
    for edge_index, record in enumerate(ordered):
        indices: list[int] = []
        for sample_index, sample in enumerate(record.edge.samples):
            if edge_index > 0 and sample_index == 0:
                indices.append(len(global_distances) - 1)
                continue
            indices.append(len(global_distances))
            global_distances.append(offset + sample.distance_meters)
            raw_elevations.append(sample.elevation_meters)
        sample_indices[record.edge.edge_id] = indices
        offset += record.edge.length_meters

    radius = ELEVATION_MEDIAN_WINDOW_SAMPLES // 2
    conditioned: list[float] = []
    for index in range(len(raw_elevations)):
        window = sorted(raw_elevations[max(0, index - radius) : index + radius + 1])
        conditioned.append(window[len(window) // 2])
    _project_maximum_grade(global_distances, conditioned, MAXIMUM_CONDITIONED_GRADE)

    rebuilt_by_id: dict[str, _EdgeRecord] = {}
    for record in ordered:
        indices = sample_indices[record.edge.edge_id]
        elevations = [conditioned[index] for index in indices]
        distances = [sample.distance_meters for sample in record.edge.samples]
        grades = _grades(distances, elevations)
        samples = tuple(
            replace(sample, elevation_meters=elevations[index], grade=grades[index])
            for index, sample in enumerate(record.edge.samples)
        )
        rebuilt_by_id[record.edge.edge_id] = replace(
            record,
            edge=replace(record.edge, samples=samples),
        )
    return [rebuilt_by_id[record.edge.edge_id] for record in records]


def _ordered_linear_records(records: list[_EdgeRecord]) -> list[_EdgeRecord] | None:
    by_from: dict[str, list[_EdgeRecord]] = {}
    destination_nodes = {record.edge.to_node_id for record in records}
    for record in records:
        by_from.setdefault(record.edge.from_node_id, []).append(record)
    starts = [record for record in records if record.edge.from_node_id not in destination_nodes]
    if len(starts) != 1:
        return None
    remaining = {record.edge.edge_id: record for record in records}
    ordered: list[_EdgeRecord] = []
    current = starts[0]
    while True:
        ordered.append(current)
        remaining.pop(current.edge.edge_id)
        if not remaining:
            return ordered
        next_records = [
            record
            for record in by_from.get(current.edge.to_node_id, [])
            if record.edge.edge_id in remaining
        ]
        if len(next_records) != 1:
            return None
        current = next_records[0]


def _project_maximum_grade(
    distances: list[float],
    elevations: list[float],
    maximum_grade: float,
) -> None:
    if len(distances) != len(elevations) or len(distances) < 2:
        raise ValueError("Grade conditioning needs aligned corridor samples.")
    for _ in range(len(elevations) * 2):
        changed = False
        for index in range(1, len(elevations)):
            limit = maximum_grade * (distances[index] - distances[index - 1])
            bounded = min(
                elevations[index - 1] + limit,
                max(elevations[index - 1] - limit, elevations[index]),
            )
            if abs(bounded - elevations[index]) > 1e-12:
                elevations[index] = bounded
                changed = True
        for index in range(len(elevations) - 2, -1, -1):
            limit = maximum_grade * (distances[index + 1] - distances[index])
            bounded = min(
                elevations[index + 1] + limit,
                max(elevations[index + 1] - limit, elevations[index]),
            )
            if abs(bounded - elevations[index]) > 1e-12:
                elevations[index] = bounded
                changed = True
        if not changed:
            break
    else:
        raise ValueError("Grade conditioning did not converge.")

    if any(
        abs(elevations[index] - elevations[index - 1])
        > maximum_grade * (distances[index] - distances[index - 1]) + 1e-9
        for index in range(1, len(elevations))
    ):
        raise ValueError("Grade conditioning exceeded its configured grade ceiling.")


def _spatial_reference(sampler: ElevationSampler | None) -> dict[str, str] | None:
    if sampler is None:
        return None
    metadata = sampler.metadata
    return {
        "route_crs": PROJECTED_CRS,
        "elevation_crs": metadata.raster_crs,
        "horizontal_datum": metadata.horizontal_datum,
        "vertical_datum": metadata.vertical_datum,
        "elevation_units": metadata.elevation_units,
        "elevation_product_id": metadata.product_id,
        "elevation_product_title": metadata.product_title,
        "elevation_product_resolution": metadata.product_resolution,
        "elevation_artifact_sha256": metadata.artifact_sha256,
    }
