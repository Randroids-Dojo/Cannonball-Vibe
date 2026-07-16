from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, MultiLineString

from cannonball_map.elevation import ElevationSampler
from cannonball_map.manifest import SourceManifest, validate_source
from cannonball_map.models import PipelineChunk, PipelineEdge, RouteSample

PROJECTED_CRS = "EPSG:5070"
SOURCE_ID_COLUMNS = ("source_feature_id", "source_id", "id", "objectid")


@dataclass(frozen=True)
class _EdgeRecord:
    source_feature_id: str
    geometry: LineString
    edge: PipelineEdge

    def edge_dict(self) -> dict[str, object]:
        return {"source_feature_id": self.source_feature_id, **self.edge.to_dict()}


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
    records: list[_EdgeRecord] = []
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
            edge = _build_edge(
                snapped_geometry,
                manifest.source_id,
                source_feature_id,
                resample_meters,
                snap_tolerance_meters,
                elevation_sampler,
            )
            records.append(_EdgeRecord(source_feature_id, snapped_geometry, edge))
    if not records:
        raise ValueError("Source contains no line geometry.")

    records.sort(key=lambda record: record.edge.edge_id)
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
        "schema_version": 2 if elevation_sampler else 1,
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
    _normalize_geopackage(normalized_path)
    return package


def _normalize_geopackage(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE gpkg_contents SET last_change = ?",
            ("1970-01-01T00:00:00.000Z",),
        )
        connection.commit()
        connection.execute("VACUUM")


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
    curvatures: list[float] = []
    elevations = [
        elevation_sampler.sample(point.x, point.y)
        if elevation_sampler is not None
        else (point.z if point.has_z else 0.0)
        for point in points
    ]
    previous_heading: float | None = None
    for index in range(len(points)):
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        heading = math.atan2(after.y - before.y, after.x - before.x)
        curvature = 0.0 if previous_heading is None else _angle_delta(previous_heading, heading)
        previous_heading = heading
        curvatures.append(curvature)
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
    coordinates[0] = (*start, *coordinates[0][2:])
    coordinates[-1] = (*end, *coordinates[-1][2:])
    return LineString(coordinates)


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
            "Source features require a stable source_feature_id, source_id, id, "
            "or OBJECTID column."
        )
    value = str(row[column]).strip()
    if not value or value.casefold() in {"<na>", "nan", "none"}:
        raise ValueError(f"Source feature has no value for identifier column '{column}'.")
    return value


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
