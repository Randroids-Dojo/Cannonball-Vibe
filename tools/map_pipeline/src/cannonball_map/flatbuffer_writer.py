from __future__ import annotations

from pathlib import Path

import flatbuffers

from Cannonball.Content.ChunkManifestData import ChunkManifestDataT
from Cannonball.Content.RouteEdgeData import RouteEdgeDataT
from Cannonball.Content.RouteGraphBuffer import RouteGraphBufferT
from Cannonball.Content.RouteNodeData import RouteNodeDataT
from Cannonball.Content.RouteSample import RouteSampleT
from Cannonball.Content.SourceCoordinate import SourceCoordinateT


def write_flatbuffer(package: dict[str, object], output_path: Path) -> None:
    chunks = [
        ChunkManifestDataT(
            id=chunk["chunk_id"],
            edgeId=chunk["edge_id"],
            startMeters=chunk["start_meters"],
            endMeters=chunk["end_meters"],
            contentHash=chunk["content_hash"],
            relativePath=f"chunks/{chunk['chunk_id']}.chunk",
            probableBranchChunkIds=[],
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
            ],
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
    graph = RouteGraphBufferT(
        schemaVersion=package["schema_version"],
        contentVersion=package["content_version"],
        nodes=nodes,
        edges=edges,
        chunks=chunks,
    )
    builder = flatbuffers.Builder(1024 * 1024)
    root = graph.Pack(builder)
    builder.Finish(root, file_identifier=b"CBRG")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(builder.Output())
