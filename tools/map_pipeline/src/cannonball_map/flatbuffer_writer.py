from __future__ import annotations

from pathlib import Path

import flatbuffers

from Cannonball.Content.ChunkManifestData import ChunkManifestDataT
from Cannonball.Content.ExitData import ExitDataT
from Cannonball.Content.JunctionConnectorData import JunctionConnectorDataT
from Cannonball.Content.LaneSectionData import LaneSectionDataT
from Cannonball.Content.MilepointAnchorData import MilepointAnchorDataT
from Cannonball.Content.RoadsideMarkerData import RoadsideMarkerDataT
from Cannonball.Content.RouteEdgeData import RouteEdgeDataT
from Cannonball.Content.RouteGraphBuffer import RouteGraphBufferT
from Cannonball.Content.RouteIdentityData import RouteIdentityDataT
from Cannonball.Content.RouteLaneData import RouteLaneDataT
from Cannonball.Content.RouteNodeData import RouteNodeDataT
from Cannonball.Content.RouteSample import RouteSampleT
from Cannonball.Content.RouteShoulderData import RouteShoulderDataT
from Cannonball.Content.SemanticProvenanceData import SemanticProvenanceDataT
from Cannonball.Content.SimplifiedMapGeometryData import SimplifiedMapGeometryDataT
from Cannonball.Content.SimplifiedMapPoint import SimplifiedMapPointT
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
            chunkIds=chunk_ids_by_edge.get(edge["edge_id"], []),
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
            laneSectionIds=edge.get("lane_section_ids", []),
            routeIdentityIds=edge.get("route_identity_ids", []),
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
    semantics = package.get("semantics", {}) if package["schema_version"] >= 4 else {}
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
        laneSections=[
            LaneSectionDataT(
                id=section["id"],
                edgeId=section["edge_id"],
                startMeters=section["start_meters"],
                endMeters=section["end_meters"],
                lanes=[
                    RouteLaneDataT(
                        id=lane["id"],
                        index=lane["index"],
                        widthMeters=lane["width_meters"],
                        role=lane["role"],
                        allowedManeuvers=lane["allowed_maneuvers"],
                        provenance=_provenance(lane["provenance"]),
                    )
                    for lane in section["lanes"]
                ],
                leftShoulder=_shoulder(section["left_shoulder"]),
                rightShoulder=_shoulder(section["right_shoulder"]),
                signedDirection=section["signed_direction"],
                provenance=_provenance(section["provenance"]),
            )
            for section in semantics.get("lane_sections", [])
        ],
        junctionConnectors=[
            JunctionConnectorDataT(
                id=connector["id"],
                junctionNodeId=connector["junction_node_id"],
                fromEdgeId=connector["from_edge_id"],
                fromLaneId=connector["from_lane_id"],
                toEdgeId=connector["to_edge_id"],
                toLaneId=connector["to_lane_id"],
                movement=connector["movement"],
                provenance=_provenance(connector["provenance"]),
            )
            for connector in semantics.get("junction_connectors", [])
        ],
        routeIdentities=[
            RouteIdentityDataT(
                id=identity["id"],
                system=identity["system"],
                number=identity["number"],
                shield=identity["shield"],
                signedDirection=identity["signed_direction"],
                localName=identity["local_name"],
                provenance=_provenance(identity["provenance"]),
            )
            for identity in semantics.get("route_identities", [])
        ],
        exits=[
            ExitDataT(
                id=exit_record["id"],
                junctionNodeId=exit_record["junction_node_id"],
                rampEdgeId=exit_record["ramp_edge_id"],
                routeIdentityId=exit_record["route_identity_id"],
                number=exit_record["number"],
                suffix=exit_record["suffix"],
                destinations=exit_record["destinations"],
                services=exit_record["services"],
                provenance=_provenance(exit_record["provenance"]),
            )
            for exit_record in semantics.get("exits", [])
        ],
        milepointAnchors=[
            MilepointAnchorDataT(
                id=anchor["id"],
                routeIdentityId=anchor["route_identity_id"],
                edgeId=anchor["edge_id"],
                distanceMeters=anchor["distance_meters"],
                valueMiles=anchor["value_miles"],
                jurisdiction=anchor["jurisdiction"],
                signedDirection=anchor["signed_direction"],
                provenance=_provenance(anchor["provenance"]),
            )
            for anchor in semantics.get("milepoint_anchors", [])
        ],
        roadsideMarkers=[
            RoadsideMarkerDataT(
                id=marker["id"],
                kind=marker["kind"],
                routeIdentityId=marker["route_identity_id"],
                edgeId=marker["edge_id"],
                distanceMeters=marker["distance_meters"],
                displayText=marker["display_text"],
                provenance=_provenance(marker["provenance"]),
            )
            for marker in semantics.get("roadside_markers", [])
        ],
        simplifiedMapGeometry=[
            SimplifiedMapGeometryDataT(
                edgeId=geometry["edge_id"],
                lod=geometry["lod"],
                points=[
                    SimplifiedMapPointT(
                        xMeters=point["x_meters"],
                        yMeters=point["y_meters"],
                        edgeDistanceMeters=point["edge_distance_meters"],
                    )
                    for point in geometry["points"]
                ],
                contentHash=geometry["content_hash"],
            )
            for geometry in semantics.get("simplified_map_geometry", [])
        ],
    )
    builder = flatbuffers.Builder(1024 * 1024)
    root = graph.Pack(builder)
    builder.Finish(root, file_identifier=b"CBRG")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(builder.Output())


def _provenance(value: dict[str, object]) -> SemanticProvenanceDataT:
    return SemanticProvenanceDataT(
        kind=value["kind"],
        sourceId=value["source_id"],
        sourceRecordId=value["source_record_id"],
        artifactSha256=value["artifact_sha256"],
        derivation=value.get("derivation", ""),
        authoredOverrideId=value.get("authored_override_id", ""),
    )


def _shoulder(value: dict[str, object]) -> RouteShoulderDataT:
    return RouteShoulderDataT(
        widthMeters=value["width_meters"],
        kind=value["kind"],
    )
