from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, MultiLineString

from cannonball_map.manifest import SourceManifest, validate_source
from cannonball_map.models import PipelineChunk, PipelineEdge, RouteSample

PROJECTED_CRS = "EPSG:5070"


def build_route_graph(
    source_path: Path,
    manifest_path: Path,
    output_directory: Path,
    *,
    resample_meters: float = 25.0,
    chunk_meters: float = 2_000.0,
    snap_tolerance_meters: float = 10.0,
) -> dict[str, object]:
    manifest = SourceManifest.load(manifest_path)
    validate_source(manifest, source_path)
    frame = gpd.read_file(source_path)
    if frame.crs is None:
        raise ValueError("Source geometry must declare a coordinate reference system.")
    frame = frame.to_crs(PROJECTED_CRS)

    lines: list[LineString] = []
    for geometry in frame.geometry:
        if isinstance(geometry, LineString):
            lines.append(geometry)
        elif isinstance(geometry, MultiLineString):
            lines.extend(geometry.geoms)
    if not lines:
        raise ValueError("Source contains no line geometry.")

    edges = [
        _build_edge(line, resample_meters, snap_tolerance_meters)
        for line in lines
        if line.length > 0
    ]
    edges.sort(key=lambda edge: edge.edge_id)
    _validate_topology(edges)
    chunks = _partition(edges, chunk_meters)
    content_version = _content_version(manifest, edges, chunks)
    package = {
        "schema_version": 1,
        "content_version": content_version,
        "source": {
            "source_id": manifest.source_id,
            "publisher": manifest.publisher,
            "source_url": manifest.source_url,
            "acquired_on": manifest.acquired_on,
            "license_status": manifest.license_status,
            "sha256": manifest.sha256,
        },
        "nodes": _nodes(edges),
        "edges": [edge.to_dict() for edge in edges],
        "chunks": [chunk.to_dict() for chunk in chunks],
    }

    output_directory.mkdir(parents=True, exist_ok=True)
    package_path = output_directory / "route_graph.json"
    package_path.write_text(
        json.dumps(package, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    normalized = gpd.GeoDataFrame(
        {"edge_id": [edge.edge_id for edge in edges], "geometry": lines},
        crs=PROJECTED_CRS,
    )
    normalized.to_file(output_directory / "normalized.gpkg", layer="route_edges", driver="GPKG")
    return package


def _build_edge(
    line: LineString,
    resample_meters: float,
    snap_tolerance_meters: float,
) -> PipelineEdge:
    start = _snap(line.coords[0], snap_tolerance_meters)
    end = _snap(line.coords[-1], snap_tolerance_meters)
    from_node_id = _stable_id("node", start)
    to_node_id = _stable_id("node", end)
    canonical = (
        tuple(round(value, 3) for coordinate in line.coords for value in coordinate[:2]),
        from_node_id,
        to_node_id,
    )
    edge_id = _stable_id("edge", canonical)
    distances = _sample_distances(line.length, resample_meters)
    points = [line.interpolate(distance) for distance in distances]
    samples: list[RouteSample] = []
    previous_heading: float | None = None
    for index, (distance, point) in enumerate(zip(distances, points, strict=True)):
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        heading = math.atan2(after.y - before.y, after.x - before.x)
        curvature = 0.0 if previous_heading is None else _angle_delta(previous_heading, heading)
        previous_heading = heading
        elevation = point.z if point.has_z else 0.0
        samples.append(RouteSample(distance, 0.0, elevation, curvature, 0.0))
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
    graph = nx.DiGraph()
    graph.add_edges_from((edge.from_node_id, edge.to_node_id) for edge in edges)
    if graph.number_of_edges() != len(edges):
        raise ValueError("Duplicate route edge collapsed during topology validation.")
    if not nx.is_weakly_connected(graph):
        raise ValueError("Selected route data is disconnected after endpoint snapping.")


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


def _stable_id(prefix: str, value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:20]}"


def _content_version(
    manifest: SourceManifest,
    edges: list[PipelineEdge],
    chunks: list[PipelineChunk],
) -> str:
    payload = {
        "source_sha256": manifest.sha256,
        "edges": [edge.to_dict() for edge in edges],
        "chunks": [chunk.to_dict() for chunk in chunks],
    }
    digest = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return f"route-v1-{digest[:16]}"


def _angle_delta(first: float, second: float) -> float:
    return (second - first + math.pi) % (2 * math.pi) - math.pi
