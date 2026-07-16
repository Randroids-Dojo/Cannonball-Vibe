from __future__ import annotations

from pathlib import Path

import flatbuffers

from Cannonball.Content.ChunkManifestData import ChunkManifestDataT
from Cannonball.Content.RouteEdgeData import RouteEdgeDataT
from Cannonball.Content.RouteGraphBuffer import RouteGraphBufferT
from Cannonball.Content.RouteNodeData import RouteNodeDataT
from Cannonball.Content.RouteSample import RouteSampleT
from Cannonball.Content.SourceCoordinate import SourceCoordinateT
from Cannonball.Content.SourceProvenanceData import SourceProvenanceDataT
from Cannonball.Content.SpatialReferenceData import SpatialReferenceDataT


def write_flatbuffer(
    package: dict[str, object],
    output_path: Path,
    *,
    include_samples: bool = True,
) -> None:
    chunks = [
        ChunkManifestDataT(
            id=chunk["chunk_id"],
            edgeId=chunk["edge_id"],
            startMeters=chunk["start_meters"],
            endMeters=chunk["end_meters"],
            contentHash=chunk["content_hash"],
            relativePath=chunk.get("relative_path", f"chunks/{chunk['chunk_id']}.chunk"),
            probableBranchChunkIds=[],
            byteCount=chunk.get("byte_count", 0),
        )
        for chunk in package["chunks"]
    ]
    chunk_ids_by_edge: dict[str, list[str]] = {}
    for chunk in package["chunks"]:
        chunk_ids_by_edge.setdefault(chunk["edge_id"], []).append(chunk["chunk_id"])
    edges = [
        RouteEdgeDataT(
            id=edge["edge_id"],
            fromNodeId=edge["from_node_id"],
            toNodeId=edge["to_node_id"],
            lengthMeters=edge["length_meters"],
            laneCount=edge["lane_count"],
            speedLimitMps=edge["speed_limit_mps"],
            regionId=edge["region_id"],
            generationProfile=edge["generation_profile"],
            chunkIds=chunk_ids_by_edge[edge["edge_id"]],
            samples=[
                RouteSampleT(
                    distanceMeters=sample["distance_meters"],
                    lateralMeters=sample["lateral_meters"],
                    elevationMeters=sample["elevation_meters"],
                    curvature=sample["curvature"],
                    grade=sample["grade"],
                )
                for sample in edge["samples"]
            ]
            if include_samples
            else [],
        )
        for edge in package["edges"]
    ]
    nodes = [
        RouteNodeDataT(
            id=node["id"],
            source=SourceCoordinateT(),
            kind=node["kind"],
            outgoingEdgeIds=node["outgoing_edge_ids"],
        )
        for node in package["nodes"]
    ]
    source = package["source"]
    spatial = package.get("spatial_reference")
    graph = RouteGraphBufferT(
        schemaVersion=package["schema_version"],
        contentVersion=package["content_version"],
        nodes=nodes,
        edges=edges,
        chunks=chunks,
        provenance=SourceProvenanceDataT(
            sourceId=source["source_id"],
            publisher=source["publisher"],
            sourceUrl=source["source_url"],
            artifactSha256=source["sha256"],
            acquisitionLockSha256=source.get("acquisition_lock_sha256", ""),
        ),
        spatialReference=(
            SpatialReferenceDataT(
                routeCrs=spatial["route_crs"],
                elevationCrs=spatial["elevation_crs"],
                horizontalDatum=spatial["horizontal_datum"],
                verticalDatum=spatial["vertical_datum"],
                elevationUnits=spatial["elevation_units"],
                elevationProductId=spatial["elevation_product_id"],
                elevationProductTitle=spatial["elevation_product_title"],
                elevationProductResolution=spatial["elevation_product_resolution"],
                elevationArtifactSha256=spatial["elevation_artifact_sha256"],
            )
            if spatial
            else None
        ),
    )
    builder = flatbuffers.Builder(1024 * 1024)
    root = graph.Pack(builder)
    builder.Finish(root, file_identifier=b"CBRG")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(builder.Output())
