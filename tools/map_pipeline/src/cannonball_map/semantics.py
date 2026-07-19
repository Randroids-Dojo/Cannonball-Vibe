from __future__ import annotations

import hashlib
import json
import math
import struct
from collections import defaultdict
from typing import Any

MAX_SIMPLIFIED_MAP_BYTES = 16_000_000
MAX_CONTINUATION_DEFLECTION_DEGREES = 1.0

MANEUVER_CONTINUE = 1 << 0
MANEUVER_MERGE = 1 << 1
MANEUVER_SPLIT = 1 << 2
MANEUVER_EXIT = 1 << 3
MANEUVER_ENTRANCE = 1 << 4
MANEUVER_TRANSFER = 1 << 5
ALL_MANEUVERS = (
    MANEUVER_CONTINUE
    | MANEUVER_MERGE
    | MANEUVER_SPLIT
    | MANEUVER_EXIT
    | MANEUVER_ENTRANCE
    | MANEUVER_TRANSFER
)
MOVEMENTS = {"continuation", "merge", "split", "exit", "entrance", "highway_transfer"}
LANE_ROLES = {"general", "auxiliary", "exit_only", "entrance_only", "managed"}
PROVENANCE_KINDS = {"source", "derived", "authored_override"}
ROADWAY_KINDS = {
    "unclassified",
    "divided_carriageway",
    "one_way_ramp",
    "one_way_roadway",
}


def attach_derived_route_semantics(package: dict[str, Any]) -> dict[str, Any]:
    """Attach conservative, explicitly derived route semantics to an audit package."""
    source = package["source"]
    source_id = str(source["source_id"])
    artifact_hash = str(source["sha256"])
    edges = sorted(package["edges"], key=lambda edge: str(edge["edge_id"]))
    nodes = sorted(package["nodes"], key=lambda node: str(node["id"]))

    route_identities_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    lane_sections: list[dict[str, Any]] = []
    route_identity_ids_by_edge: dict[str, list[str]] = {}
    milepoint_anchors: list[dict[str, Any]] = []
    roadside_markers: list[dict[str, Any]] = []
    map_geometry: list[dict[str, Any]] = []

    _attach_carriageway_semantics(edges)

    for edge in edges:
        edge_id = str(edge["edge_id"])
        source_record_id = str(edge["source_feature_id"])
        lane_count = int(edge["lane_count"])
        source_provenance = _provenance(
            "source",
            source_id,
            source_record_id,
            artifact_hash,
        )
        derived_provenance = _provenance(
            "derived",
            source_id,
            source_record_id,
            artifact_hash,
            derivation=(
                f"{lane_count} general-purpose lanes and conservative shoulders are a "
                "deterministic graybox default, not observed lane geometry."
            ),
        )
        route_system = str(edge.get("source_route_system", "unknown"))
        route_number = str(edge.get("source_route_number", "unknown"))
        signed_direction = str(edge.get("source_signed_direction", "unspecified"))
        local_name = str(edge.get("source_local_name", ""))
        identity_key = (route_system, route_number, signed_direction, local_name)
        identity = route_identities_by_key.get(identity_key)
        if identity is None:
            identity_id = _stable_id("route-identity", identity_key)
            identity = {
                "id": identity_id,
                "system": route_system,
                "number": route_number,
                "shield": _shield(route_system),
                "signed_direction": signed_direction,
                "local_name": local_name,
                "provenance": source_provenance,
            }
            route_identities_by_key[identity_key] = identity
        identity_id = str(identity["id"])
        route_identity_ids_by_edge[edge_id] = [identity_id]

        section_id = _stable_id("lane-section", (edge_id, 0.0, edge["length_meters"]))
        lanes = [
            {
                "id": _stable_id("lane", (edge_id, section_id, lane_index)),
                "index": lane_index,
                "width_meters": 3.6,
                "role": "general",
                "allowed_maneuvers": MANEUVER_CONTINUE,
                "provenance": derived_provenance,
            }
            for lane_index in range(lane_count)
        ]
        lane_sections.append(
            {
                "id": section_id,
                "edge_id": edge_id,
                "start_meters": 0.0,
                "end_meters": float(edge["length_meters"]),
                "lanes": lanes,
                "left_shoulder": {"width_meters": 1.5, "kind": "paved"},
                "right_shoulder": {"width_meters": 3.0, "kind": "paved"},
                "signed_direction": signed_direction,
                "provenance": derived_provenance,
            }
        )

        begin_mile = _optional_finite(edge.get("source_begin_mile"))
        end_mile = _optional_finite(edge.get("source_end_mile"))
        for position, value, suffix in (
            (0.0, begin_mile, "start"),
            (float(edge["length_meters"]), end_mile, "end"),
        ):
            if value is None:
                continue
            anchor_id = _stable_id("milepoint", (identity_id, edge_id, position, value, suffix))
            milepoint_anchors.append(
                {
                    "id": anchor_id,
                    "route_identity_id": identity_id,
                    "edge_id": edge_id,
                    "distance_meters": position,
                    "value_miles": value,
                    "jurisdiction": str(edge.get("source_jurisdiction", "unknown")),
                    "signed_direction": signed_direction,
                    "provenance": source_provenance,
                }
            )
            if suffix == "start":
                roadside_markers.append(
                    {
                        "id": _stable_id("roadside-marker", (anchor_id, "mile")),
                        "kind": "mile",
                        "route_identity_id": identity_id,
                        "edge_id": edge_id,
                        "distance_meters": position,
                        "display_text": _format_mile(value),
                        "provenance": source_provenance,
                    }
                )

        map_geometry.extend(_map_lods(edge))

    sections_by_edge = {section["edge_id"]: section for section in lane_sections}
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        incoming[str(edge["to_node_id"])].append(edge)
        outgoing[str(edge["from_node_id"])].append(edge)

    connectors: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node["id"])
        node_incoming = sorted(incoming[node_id], key=lambda edge: str(edge["edge_id"]))
        node_outgoing = sorted(outgoing[node_id], key=lambda edge: str(edge["edge_id"]))
        for from_edge in node_incoming:
            for to_edge in node_outgoing:
                from_section = sections_by_edge[str(from_edge["edge_id"])]
                to_section = sections_by_edge[str(to_edge["edge_id"])]
                from_lane_count = len(from_section["lanes"])
                to_lane_count = len(to_section["lanes"])
                movement = (
                    "merge"
                    if from_lane_count > to_lane_count
                    else "split"
                    if from_lane_count < to_lane_count
                    else _derived_movement(len(node_incoming), len(node_outgoing))
                )
                maneuver = _movement_flag(movement)
                for from_lane_index, to_lane_index in _complete_lane_mapping(
                    from_lane_count, to_lane_count
                ):
                    from_lane = from_section["lanes"][from_lane_index]
                    to_lane = to_section["lanes"][to_lane_index]
                    from_lane["allowed_maneuvers"] |= maneuver
                    provenance = _provenance(
                        "derived",
                        source_id,
                        f"{from_edge['source_feature_id']}->{to_edge['source_feature_id']}",
                        artifact_hash,
                        derivation=(
                            "Complete non-crossing connector mapping derived from snapped "
                            "directed topology and boundary lane counts; not observed lane "
                            "connectivity."
                        ),
                    )
                    connectors.append(
                        {
                            "id": _stable_id(
                                "connector",
                                (
                                    node_id,
                                    from_edge["edge_id"],
                                    from_lane["id"],
                                    to_edge["edge_id"],
                                    to_lane["id"],
                                    movement,
                                ),
                            ),
                            "junction_node_id": node_id,
                            "from_edge_id": from_edge["edge_id"],
                            "from_lane_id": from_lane["id"],
                            "to_edge_id": to_edge["edge_id"],
                            "to_lane_id": to_lane["id"],
                            "movement": movement,
                            "provenance": provenance,
                        }
                    )

    semantics = {
        "lane_sections": sorted(lane_sections, key=_section_sort_key),
        "junction_connectors": sorted(connectors, key=lambda item: item["id"]),
        "route_identities": sorted(route_identities_by_key.values(), key=lambda item: item["id"]),
        "exits": [],
        "milepoint_anchors": sorted(milepoint_anchors, key=lambda item: item["id"]),
        "roadside_markers": sorted(roadside_markers, key=lambda item: item["id"]),
        "simplified_map_geometry": sorted(
            map_geometry, key=lambda item: (item["edge_id"], item["lod"])
        ),
    }
    package["semantics"] = semantics
    for edge in package["edges"]:
        edge_id = str(edge["edge_id"])
        edge["lane_section_ids"] = [
            section["id"] for section in semantics["lane_sections"] if section["edge_id"] == edge_id
        ]
        edge["route_identity_ids"] = route_identity_ids_by_edge[edge_id]
    validate_route_semantics(package)
    return package


def _attach_carriageway_semantics(edges: list[dict[str, Any]]) -> None:
    source_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source_edges[str(edge["source_feature_id"])].append(edge)

    for edge in edges:
        kind = str(edge.get("source_roadway_kind", "unclassified")).strip().casefold()
        if kind not in ROADWAY_KINDS:
            raise ValueError(
                f"Edge '{edge['edge_id']}' has unknown roadway kind '{kind}'."
            )
        group_id = str(edge.get("source_carriageway_group_id", "")).strip()
        opposing_source_id = str(edge.get("source_opposing_feature_id", "")).strip()
        opposing_edge_id = ""
        if kind == "divided_carriageway":
            if not group_id or not opposing_source_id:
                raise ValueError(
                    f"Divided carriageway edge '{edge['edge_id']}' needs a carriageway "
                    "group and opposing source feature."
                )
            candidates = source_edges.get(opposing_source_id, [])
            if len(candidates) != 1:
                raise ValueError(
                    f"Divided carriageway edge '{edge['edge_id']}' opposing source feature "
                    f"'{opposing_source_id}' is not unique."
                )
            opposing_edge_id = str(candidates[0]["edge_id"])
        elif group_id or opposing_source_id:
            raise ValueError(
                f"Non-divided edge '{edge['edge_id']}' cannot declare carriageway pairing."
            )
        edge["roadway_kind"] = kind
        edge["carriageway_group_id"] = group_id
        edge["opposing_edge_id"] = opposing_edge_id


def validate_route_semantics(package: dict[str, Any]) -> None:
    semantics = package.get("semantics")
    if not isinstance(semantics, dict):
        raise ValueError("Route package is missing versioned semantics.")
    source = package.get("source")
    if not isinstance(source, dict):
        raise ValueError("Route package is missing source provenance.")
    source_id = _required_string(source, "source_id", "Route package source")
    artifact_sha256 = _required_string(source, "sha256", "Route package source")
    if len(artifact_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in artifact_sha256
    ):
        raise ValueError("Route package source has an invalid artifact hash.")
    source_description = " ".join(
        str(source.get(field, "")) for field in ("source_id", "publisher", "source_url")
    ).casefold()
    if "openstreetmap" in source_description or source_id.casefold() == "osm":
        raise ValueError("OpenStreetMap-derived data is prohibited by the project source policy.")
    edges = {str(edge["edge_id"]): edge for edge in package["edges"]}
    nodes = {str(node["id"]): node for node in package["nodes"]}
    if len(edges) != len(package["edges"]) or len(nodes) != len(package["nodes"]):
        raise ValueError("Route semantics cannot validate duplicate node or edge IDs.")
    _validate_carriageway_semantics(edges)

    identities = _unique_by_id(semantics.get("route_identities", []), "route identity")
    sections = _unique_by_id(semantics.get("lane_sections", []), "lane section")
    sections_by_edge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section in sections.values():
        edge_id = _required_string(section, "edge_id", "Lane section")
        if edge_id not in edges:
            raise ValueError(f"Lane section '{section['id']}' references unknown edge '{edge_id}'.")
        start = _finite(section, "start_meters", f"Lane section '{section['id']}'")
        end = _finite(section, "end_meters", f"Lane section '{section['id']}'")
        if start < 0 or end <= start or end > float(edges[edge_id]["length_meters"]):
            raise ValueError(f"Lane section '{section['id']}' has an invalid distance range.")
        _required_string(section, "signed_direction", f"Lane section '{section['id']}'")
        _validate_provenance(
            section.get("provenance"),
            f"Lane section '{section['id']}'",
            source_id,
            artifact_sha256,
        )
        _validate_shoulder(section.get("left_shoulder"), f"Lane section '{section['id']}' left")
        _validate_shoulder(section.get("right_shoulder"), f"Lane section '{section['id']}' right")
        lanes = section.get("lanes")
        if not isinstance(lanes, list) or not lanes:
            raise ValueError(f"Lane section '{section['id']}' has no lanes.")
        lane_ids: set[str] = set()
        lane_indexes: set[int] = set()
        for lane in lanes:
            lane_id = _required_string(lane, "id", f"Lane section '{section['id']}' lane")
            lane_index = lane.get("index")
            if not isinstance(lane_index, int) or lane_index < 0:
                raise ValueError(f"Lane '{lane_id}' has an invalid index.")
            if lane_id in lane_ids or lane_index in lane_indexes:
                raise ValueError(f"Lane section '{section['id']}' repeats a lane ID or index.")
            width = _finite(lane, "width_meters", f"Lane '{lane_id}'")
            if width <= 0:
                raise ValueError(f"Lane '{lane_id}' must have a positive width.")
            if lane.get("role") not in LANE_ROLES:
                raise ValueError(f"Lane '{lane_id}' has unknown role '{lane.get('role')}'.")
            maneuvers = lane.get("allowed_maneuvers")
            if not isinstance(maneuvers, int) or maneuvers <= 0 or maneuvers & ~ALL_MANEUVERS:
                raise ValueError(f"Lane '{lane_id}' has invalid allowed maneuvers.")
            _validate_provenance(
                lane.get("provenance"), f"Lane '{lane_id}'", source_id, artifact_sha256
            )
            lane_ids.add(lane_id)
            lane_indexes.add(lane_index)
        if lane_indexes != set(range(len(lanes))):
            raise ValueError(
                f"Lane section '{section['id']}' indexes must be contiguous from zero."
            )
        sections_by_edge[edge_id].append(section)

    for edge_id, edge in edges.items():
        edge_sections = sorted(sections_by_edge[edge_id], key=_section_sort_key)
        if not edge_sections:
            raise ValueError(f"Edge '{edge_id}' has no lane sections.")
        expected_start = 0.0
        for section in edge_sections:
            if not math.isclose(float(section["start_meters"]), expected_start, abs_tol=1e-9):
                raise ValueError(f"Edge '{edge_id}' lane sections have a gap or overlap.")
            expected_start = float(section["end_meters"])
        if not math.isclose(expected_start, float(edge["length_meters"]), abs_tol=1e-9):
            raise ValueError(f"Edge '{edge_id}' lane sections do not cover the complete edge.")
        expected_ids = [section["id"] for section in edge_sections]
        if edge.get("lane_section_ids") != expected_ids:
            raise ValueError(f"Edge '{edge_id}' lane-section references are not canonical.")
        if len({str(section["signed_direction"]) for section in edge_sections}) != 1:
            raise ValueError(
                f"Edge '{edge_id}' changes signed direction between lane sections."
            )
        route_ids = edge.get("route_identity_ids")
        if not isinstance(route_ids, list) or not route_ids:
            raise ValueError(f"Edge '{edge_id}' has no route identity.")
        for route_id in route_ids:
            if route_id not in identities:
                raise ValueError(
                    f"Edge '{edge_id}' references unknown route identity '{route_id}'."
                )

    connectors = _unique_by_id(semantics.get("junction_connectors", []), "connector")
    connector_targets: set[tuple[str, str, str, str]] = set()
    connectors_by_pair: dict[tuple[str, str], list[tuple[int, int, str]]] = defaultdict(list)
    incoming_coverage: set[tuple[str, str]] = set()
    outgoing_coverage: set[tuple[str, str]] = set()
    for connector in connectors.values():
        connector_id = connector["id"]
        node_id = _required_string(connector, "junction_node_id", f"Connector '{connector_id}'")
        from_edge_id = _required_string(connector, "from_edge_id", f"Connector '{connector_id}'")
        to_edge_id = _required_string(connector, "to_edge_id", f"Connector '{connector_id}'")
        from_lane_id = _required_string(connector, "from_lane_id", f"Connector '{connector_id}'")
        to_lane_id = _required_string(connector, "to_lane_id", f"Connector '{connector_id}'")
        movement = connector.get("movement")
        if node_id not in nodes or from_edge_id not in edges or to_edge_id not in edges:
            raise ValueError(f"Connector '{connector_id}' references an unknown node or edge.")
        if (
            edges[from_edge_id]["to_node_id"] != node_id
            or edges[to_edge_id]["from_node_id"] != node_id
        ):
            raise ValueError(f"Connector '{connector_id}' does not meet at its declared junction.")
        if movement not in MOVEMENTS:
            raise ValueError(f"Connector '{connector_id}' has unknown movement '{movement}'.")
        final_from_section = max(
            sections_by_edge[from_edge_id], key=lambda item: item["end_meters"]
        )
        first_to_section = min(sections_by_edge[to_edge_id], key=lambda item: item["start_meters"])
        from_lane = next(
            (lane for lane in final_from_section["lanes"] if lane["id"] == from_lane_id),
            None,
        )
        to_lane = next(
            (lane for lane in first_to_section["lanes"] if lane["id"] == to_lane_id),
            None,
        )
        if from_lane is None or to_lane is None:
            raise ValueError(f"Connector '{connector_id}' references an orphan lane.")
        target_key = (from_edge_id, from_lane_id, to_edge_id, to_lane_id)
        if target_key in connector_targets:
            raise ValueError(f"Connector '{connector_id}' repeats a lane mapping.")
        movement_flag = _movement_flag(str(movement))
        if not int(from_lane["allowed_maneuvers"]) & movement_flag:
            raise ValueError(
                f"Connector '{connector_id}' movement is not allowed by lane '{from_lane_id}'."
            )
        connector_targets.add(target_key)
        connectors_by_pair[(from_edge_id, to_edge_id)].append(
            (int(from_lane["index"]), int(to_lane["index"]), str(movement))
        )
        incoming_coverage.add((from_edge_id, from_lane_id))
        outgoing_coverage.add((to_edge_id, to_lane_id))
        _validate_provenance(
            connector.get("provenance"),
            f"Connector '{connector_id}'",
            source_id,
            artifact_sha256,
        )
    for pair, lane_pairs in connectors_by_pair.items():
        ordered = sorted(lane_pairs)
        if any(after[1] < before[1] for before, after in zip(ordered, ordered[1:], strict=False)):
            raise ValueError(f"Connectors between '{pair[0]}' and '{pair[1]}' cross lanes.")
        successors: dict[int, list[tuple[int, str]]] = defaultdict(list)
        predecessors: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for from_index, to_index, connector_movement in lane_pairs:
            successors[from_index].append((to_index, connector_movement))
            predecessors[to_index].append((from_index, connector_movement))
        if any(
            len({target for target, _ in mappings}) > 1
            and {item_movement for _, item_movement in mappings} != {"split"}
            for mappings in successors.values()
        ):
            raise ValueError(
                f"Connectors between '{pair[0]}' and '{pair[1]}' create an ambiguous "
                "lane successor."
            )
        if any(
            len({source_index for source_index, _ in mappings}) > 1
            and {item_movement for _, item_movement in mappings} != {"merge"}
            for mappings in predecessors.values()
        ):
            raise ValueError(
                f"Connectors between '{pair[0]}' and '{pair[1]}' create an ambiguous "
                "lane predecessor."
            )
        if "continuation" in {movement for _, _, movement in lane_pairs}:
            deflection = _continuation_deflection_degrees(edges[pair[0]], edges[pair[1]])
            if deflection > MAX_CONTINUATION_DEFLECTION_DEGREES:
                raise ValueError(
                    f"Continuation from '{pair[0]}' to '{pair[1]}' has a "
                    f"{deflection:.3f}-degree endpoint tangent discontinuity; maximum is "
                    f"{MAX_CONTINUATION_DEFLECTION_DEGREES:.3f} degrees."
                )

    incoming_edges_by_node: dict[str, list[str]] = defaultdict(list)
    outgoing_edges_by_node: dict[str, list[str]] = defaultdict(list)
    for edge_id, edge in edges.items():
        incoming_edges_by_node[str(edge["to_node_id"])].append(edge_id)
        outgoing_edges_by_node[str(edge["from_node_id"])].append(edge_id)
    for node_id in set(incoming_edges_by_node) & set(outgoing_edges_by_node):
        for edge_id in incoming_edges_by_node[node_id]:
            final_section = max(sections_by_edge[edge_id], key=lambda item: item["end_meters"])
            for lane in final_section["lanes"]:
                if (edge_id, lane["id"]) not in incoming_coverage:
                    raise ValueError(
                        f"Junction '{node_id}' leaves incoming lane '{lane['id']}' orphaned."
                    )
        for edge_id in outgoing_edges_by_node[node_id]:
            first_section = min(sections_by_edge[edge_id], key=lambda item: item["start_meters"])
            for lane in first_section["lanes"]:
                if (edge_id, lane["id"]) not in outgoing_coverage:
                    raise ValueError(
                        f"Junction '{node_id}' leaves outgoing lane '{lane['id']}' orphaned."
                    )

    for identity in identities.values():
        for field in ("system", "number", "shield", "signed_direction"):
            _required_string(identity, field, f"Route identity '{identity['id']}'")
        _validate_provenance(
            identity.get("provenance"),
            f"Route identity '{identity['id']}'",
            source_id,
            artifact_sha256,
        )

    _validate_context_records(semantics, edges, nodes, identities, source_id, artifact_sha256)
    map_bytes = 0
    map_keys: set[tuple[str, int]] = set()
    map_records = semantics.get("simplified_map_geometry", [])
    if not isinstance(map_records, list):
        raise ValueError("Route semantics simplified map geometry collection must be a list.")
    for geometry in map_records:
        edge_id = _required_string(geometry, "edge_id", "Simplified map geometry")
        lod = geometry.get("lod")
        if edge_id not in edges or not isinstance(lod, int) or lod < 0:
            raise ValueError("Simplified map geometry has an invalid edge or LOD.")
        if (edge_id, lod) in map_keys:
            raise ValueError(f"Simplified map geometry repeats edge '{edge_id}' LOD {lod}.")
        map_keys.add((edge_id, lod))
        points = geometry.get("points")
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError(f"Simplified map geometry '{edge_id}' LOD {lod} needs two points.")
        previous_distance: float | None = None
        for point in points:
            for field in ("x_meters", "y_meters", "edge_distance_meters"):
                _finite(point, field, f"Simplified map geometry '{edge_id}' LOD {lod}")
            distance = float(point["edge_distance_meters"])
            if previous_distance is not None and distance <= previous_distance:
                raise ValueError(
                    f"Simplified map geometry '{edge_id}' LOD {lod} distances are not increasing."
                )
            previous_distance = distance
        starts_at_zero = math.isclose(float(points[0]["edge_distance_meters"]), 0.0, abs_tol=1e-9)
        ends_at_edge_length = math.isclose(
            float(points[-1]["edge_distance_meters"]),
            float(edges[edge_id]["length_meters"]),
            abs_tol=1e-9,
        )
        if not starts_at_zero or not ends_at_edge_length:
            raise ValueError(
                f"Simplified map geometry '{edge_id}' LOD {lod} has invalid endpoints."
            )
        payload = map_geometry_payload(edge_id, lod, points)
        map_bytes += len(payload)
        if hashlib.sha256(payload).hexdigest() != geometry.get("content_hash"):
            raise ValueError(f"Simplified map geometry '{edge_id}' LOD {lod} hash is invalid.")
    expected_map_keys = {(edge_id, lod) for edge_id in edges for lod in range(3)}
    if map_keys != expected_map_keys:
        raise ValueError("Simplified map geometry must contain LODs 0, 1, and 2 for every edge.")
    if map_bytes >= MAX_SIMPLIFIED_MAP_BYTES:
        raise ValueError("Simplified map geometry exceeds the 16 MB package budget.")


def _validate_carriageway_semantics(edges: dict[str, dict[str, Any]]) -> None:
    for edge_id, edge in edges.items():
        kind = str(edge.get("roadway_kind", ""))
        group_id = str(edge.get("carriageway_group_id", ""))
        opposing_edge_id = str(edge.get("opposing_edge_id", ""))
        if kind not in ROADWAY_KINDS:
            raise ValueError(f"Edge '{edge_id}' has unknown roadway kind '{kind}'.")
        if kind != "divided_carriageway":
            if group_id or opposing_edge_id:
                raise ValueError(
                    f"Non-divided edge '{edge_id}' cannot declare carriageway pairing."
                )
            continue
        opposing = edges.get(opposing_edge_id)
        if (
            not group_id
            or opposing is None
            or opposing_edge_id == edge_id
            or opposing.get("roadway_kind") != "divided_carriageway"
            or opposing.get("opposing_edge_id") != edge_id
            or opposing.get("carriageway_group_id") != group_id
        ):
            raise ValueError(
                f"Divided carriageway edge '{edge_id}' does not have a reciprocal pair."
            )
        if not _opposing_signed_directions(
            str(edge.get("source_signed_direction", "")),
            str(opposing.get("source_signed_direction", "")),
        ):
            raise ValueError(
                f"Divided carriageway edge '{edge_id}' does not declare the opposite "
                "signed direction from its pair."
            )


def _opposing_signed_directions(first: str, second: str) -> bool:
    aliases = {
        "eastbound": "east",
        "westbound": "west",
        "northbound": "north",
        "southbound": "south",
    }
    first = aliases.get(first.strip().casefold(), first.strip().casefold())
    second = aliases.get(second.strip().casefold(), second.strip().casefold())
    return (first, second) in {
        ("east", "west"),
        ("west", "east"),
        ("north", "south"),
        ("south", "north"),
    }


def map_geometry_payload(edge_id: str, lod: int, points: list[dict[str, Any]]) -> bytes:
    edge_bytes = edge_id.encode("utf-8")
    payload = bytearray(struct.pack("<I", len(edge_bytes)))
    payload.extend(edge_bytes)
    payload.extend(struct.pack("<II", lod, len(points)))
    for point in points:
        payload.extend(
            struct.pack(
                "<ddd",
                float(point["x_meters"]),
                float(point["y_meters"]),
                float(point["edge_distance_meters"]),
            )
        )
    return bytes(payload)


def _map_lods(edge: dict[str, Any]) -> list[dict[str, Any]]:
    samples = edge["samples"]
    indices_by_lod = {
        0: list(range(len(samples))),
        1: sorted({*range(0, len(samples), 4), len(samples) - 1}),
        2: [0, len(samples) - 1],
    }
    result = []
    for lod, indices in indices_by_lod.items():
        points = [
            {
                "x_meters": float(samples[index]["projected_x_meters"]),
                "y_meters": float(samples[index]["projected_y_meters"]),
                "edge_distance_meters": float(samples[index]["distance_meters"]),
            }
            for index in indices
        ]
        payload = map_geometry_payload(str(edge["edge_id"]), lod, points)
        result.append(
            {
                "edge_id": edge["edge_id"],
                "lod": lod,
                "points": points,
                "content_hash": hashlib.sha256(payload).hexdigest(),
            }
        )
    return result


def _validate_context_records(
    semantics: dict[str, Any],
    edges: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    identities: dict[str, dict[str, Any]],
    source_id: str,
    artifact_sha256: str,
) -> None:
    for label, key in (
        ("exit", "exits"),
        ("milepoint anchor", "milepoint_anchors"),
        ("roadside marker", "roadside_markers"),
    ):
        records = _unique_by_id(semantics.get(key, []), label)
        for record in records.values():
            identity_id = _required_string(
                record,
                "route_identity_id",
                f"{label.title()} '{record['id']}'",
            )
            if identity_id not in identities:
                raise ValueError(
                    f"{label.title()} '{record['id']}' references unknown route identity."
                )
            _validate_provenance(
                record.get("provenance"),
                f"{label.title()} '{record['id']}'",
                source_id,
                artifact_sha256,
            )
            if label == "exit":
                node_id = _required_string(record, "junction_node_id", f"Exit '{record['id']}'")
                ramp_edge_id = _required_string(record, "ramp_edge_id", f"Exit '{record['id']}'")
                if node_id not in nodes or ramp_edge_id not in edges:
                    raise ValueError(
                        f"Exit '{record['id']}' references an unknown node or ramp edge."
                    )
                if edges[ramp_edge_id]["from_node_id"] != node_id:
                    raise ValueError(f"Exit '{record['id']}' ramp does not start at its junction.")
                number = record.get("number", "")
                suffix = record.get("suffix", "")
                if not isinstance(number, str) or not isinstance(suffix, str):
                    raise ValueError(f"Exit '{record['id']}' number and suffix must be strings.")
                destinations = _string_list(record, "destinations", f"Exit '{record['id']}'")
                _string_list(record, "services", f"Exit '{record['id']}'")
                if not number and not destinations:
                    raise ValueError(f"Exit '{record['id']}' needs a number or destination.")
            else:
                edge_id = _required_string(record, "edge_id", f"{label.title()} '{record['id']}'")
                if edge_id not in edges:
                    raise ValueError(f"{label.title()} '{record['id']}' references unknown edge.")
                if identity_id not in edges[edge_id]["route_identity_ids"]:
                    raise ValueError(
                        f"{label.title()} '{record['id']}' route identity does not belong to "
                        f"edge '{edge_id}'."
                    )
                distance = _finite(record, "distance_meters", f"{label.title()} '{record['id']}'")
                if distance < 0 or distance > float(edges[edge_id]["length_meters"]):
                    raise ValueError(f"{label.title()} '{record['id']}' is outside its edge.")
                if label == "milepoint anchor":
                    _finite(record, "value_miles", f"Milepoint anchor '{record['id']}'")
                else:
                    _required_string(record, "kind", f"Roadside marker '{record['id']}'")
                    _required_string(record, "display_text", f"Roadside marker '{record['id']}'")


def _unique_by_id(records: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError(f"Route semantics {label} collection must be a list.")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"Route semantics {label} record must be an object.")
        record_id = _required_string(record, "id", label.title())
        if record_id in result:
            raise ValueError(f"Route semantics repeats {label} ID '{record_id}'.")
        result[record_id] = record
    return result


def _validate_provenance(
    value: Any,
    context: str,
    expected_source_id: str,
    expected_artifact_sha256: str,
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{context} is missing provenance.")
    kind = value.get("kind")
    if kind not in PROVENANCE_KINDS:
        raise ValueError(f"{context} has unknown provenance kind '{kind}'.")
    source_id = _required_string(value, "source_id", f"{context} provenance")
    _required_string(value, "source_record_id", f"{context} provenance")
    digest = _required_string(value, "artifact_sha256", f"{context} provenance")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{context} has invalid provenance artifact hash.")
    if source_id != expected_source_id or digest != expected_artifact_sha256:
        raise ValueError(f"{context} provenance is outside the package's locked source ancestry.")
    if kind == "derived" and not value.get("derivation"):
        raise ValueError(f"{context} derived provenance is missing its recipe.")
    if kind == "authored_override" and not value.get("authored_override_id"):
        raise ValueError(f"{context} authored provenance is missing its override ID.")


def _validate_shoulder(value: Any, context: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{context} shoulder is missing.")
    if _finite(value, "width_meters", context) < 0:
        raise ValueError(f"{context} shoulder width cannot be negative.")
    _required_string(value, "kind", context)


def _string_list(values: dict[str, Any], field: str, context: str) -> list[str]:
    result = values.get(field, [])
    if not isinstance(result, list) or any(
        not isinstance(value, str) or not value.strip() for value in result
    ):
        raise ValueError(f"{context} has an invalid '{field}' list.")
    return result


def _provenance(
    kind: str,
    source_id: str,
    source_record_id: str,
    artifact_sha256: str,
    *,
    derivation: str = "",
    authored_override_id: str = "",
) -> dict[str, str]:
    return {
        "kind": kind,
        "source_id": source_id,
        "source_record_id": source_record_id,
        "artifact_sha256": artifact_sha256,
        "derivation": derivation,
        "authored_override_id": authored_override_id,
    }


def _continuation_deflection_degrees(
    from_edge: dict[str, Any],
    to_edge: dict[str, Any],
) -> float:
    from_samples = from_edge.get("samples")
    to_samples = to_edge.get("samples")
    if (
        not isinstance(from_samples, list)
        or len(from_samples) < 2
        or not isinstance(to_samples, list)
        or len(to_samples) < 2
    ):
        raise ValueError("Continuation geometry requires at least two samples per edge.")

    def direction(before: dict[str, Any], after: dict[str, Any]) -> tuple[float, float]:
        delta_x = _finite(after, "projected_x_meters", "Continuation sample") - _finite(
            before, "projected_x_meters", "Continuation sample"
        )
        delta_y = _finite(after, "projected_y_meters", "Continuation sample") - _finite(
            before, "projected_y_meters", "Continuation sample"
        )
        magnitude = math.hypot(delta_x, delta_y)
        if magnitude <= 1e-9:
            raise ValueError("Continuation geometry has a zero-length endpoint segment.")
        return delta_x / magnitude, delta_y / magnitude

    incoming = direction(from_samples[-2], from_samples[-1])
    outgoing = direction(to_samples[0], to_samples[1])
    dot = max(-1.0, min(1.0, incoming[0] * outgoing[0] + incoming[1] * outgoing[1]))
    return math.degrees(math.acos(dot))


def _derived_movement(incoming_count: int, outgoing_count: int) -> str:
    if outgoing_count > 1:
        return "split"
    if incoming_count > 1:
        return "merge"
    return "continuation"


def _complete_lane_mapping(from_count: int, to_count: int) -> list[tuple[int, int]]:
    if from_count <= 0 or to_count <= 0:
        raise ValueError("Lane connector boundaries must contain at least one lane.")
    if from_count == to_count:
        return [(index, index) for index in range(from_count)]
    if from_count > to_count:
        return [
            (index, min(to_count - 1, index * to_count // from_count))
            for index in range(from_count)
        ]
    return [
        (min(from_count - 1, index * from_count // to_count), index) for index in range(to_count)
    ]


def _movement_flag(movement: str) -> int:
    return {
        "continuation": MANEUVER_CONTINUE,
        "merge": MANEUVER_MERGE,
        "split": MANEUVER_SPLIT,
        "exit": MANEUVER_EXIT,
        "entrance": MANEUVER_ENTRANCE,
        "highway_transfer": MANEUVER_TRANSFER,
    }[movement]


def _section_sort_key(section: dict[str, Any]) -> tuple[str, float, float, str]:
    return (
        str(section["edge_id"]),
        float(section["start_meters"]),
        float(section["end_meters"]),
        str(section["id"]),
    )


def _shield(system: str) -> str:
    return {"US": "us", "I": "interstate", "CO": "state"}.get(system, "generic")


def _format_mile(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}".rstrip("0").rstrip(".")


def _optional_finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite(values: dict[str, Any], field: str, context: str) -> float:
    try:
        value = float(values[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{context} has invalid '{field}'.") from error
    if not math.isfinite(value):
        raise ValueError(f"{context} has non-finite '{field}'.")
    return value


def _required_string(values: dict[str, Any], field: str, context: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} is missing '{field}'.")
    return value


def _stable_id(prefix: str, value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:20]}"
