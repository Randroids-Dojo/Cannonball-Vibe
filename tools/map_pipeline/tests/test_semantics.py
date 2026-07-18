from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from Cannonball.Content.RouteGraphBuffer import RouteGraphBuffer
from cannonball_map.flatbuffer_writer import write_flatbuffer
from cannonball_map.pipeline import build_route_graph
from cannonball_map.semantics import (
    MANEUVER_CONTINUE,
    MANEUVER_ENTRANCE,
    MANEUVER_EXIT,
    MANEUVER_MERGE,
    MANEUVER_SPLIT,
    MANEUVER_TRANSFER,
    attach_derived_route_semantics,
    validate_route_semantics,
)

ARTIFACT_HASH = hashlib.sha256(b"semantic-fixture").hexdigest()
CONTRACT = json.loads(
    Path("data/routes/fixtures/semantics/representative-contract.json").read_text()
)
MOVEMENTS = {
    "continuation": MANEUVER_CONTINUE,
    "merge": MANEUVER_MERGE,
    "split": MANEUVER_SPLIT,
    "exit": MANEUVER_EXIT,
    "entrance": MANEUVER_ENTRANCE,
    "highway_transfer": MANEUVER_TRANSFER,
}


def _edge(edge_id: str, start: str, end: str, x_offset: float, lane_count: int) -> dict:
    return {
        "source_feature_id": edge_id,
        "source_route_system": "I",
        "source_route_number": "70",
        "source_signed_direction": "east",
        "source_local_name": "Veterans Memorial Highway",
        "source_begin_mile": x_offset / 100.0,
        "source_end_mile": (x_offset + 100.0) / 100.0,
        "source_jurisdiction": "08",
        "edge_id": edge_id,
        "from_node_id": start,
        "to_node_id": end,
        "length_meters": 100.0,
        "lane_count": lane_count,
        "speed_limit_mps": 31.2928,
        "region_id": "fixture",
        "generation_profile": "graybox",
        "samples": [
            {
                "distance_meters": 0.0,
                "lateral_meters": 0.0,
                "elevation_meters": 1_500.0,
                "curvature": 0.0,
                "grade": 0.0,
                "projected_x_meters": x_offset,
                "projected_y_meters": 0.0,
            },
            {
                "distance_meters": 100.0,
                "lateral_meters": 0.0,
                "elevation_meters": 1_500.0,
                "curvature": 0.0,
                "grade": 0.0,
                "projected_x_meters": x_offset + 100.0,
                "projected_y_meters": 0.0,
            },
        ],
    }


def _junction_package() -> dict:
    package = {
        "schema_version": 4,
        "content_version": "route-v4-semantic-fixture",
        "source": {
            "source_id": "synthetic-public-domain-fixture",
            "publisher": "Test Federal Agency",
            "source_url": "https://example.gov/route",
            "sha256": ARTIFACT_HASH,
        },
        "nodes": [
            {"id": "west", "kind": "route", "outgoing_edge_ids": ["incoming"]},
            {
                "id": "junction",
                "kind": "junction",
                "outgoing_edge_ids": ["mainline", "ramp"],
            },
            {"id": "east", "kind": "route", "outgoing_edge_ids": []},
            {"id": "ramp-end", "kind": "route", "outgoing_edge_ids": []},
        ],
        "edges": [
            _edge("incoming", "west", "junction", 0.0, 2),
            _edge("mainline", "junction", "east", 100.0, 2),
            _edge("ramp", "junction", "ramp-end", 100.0, 1),
        ],
        "chunks": [],
    }
    attach_derived_route_semantics(package)
    identity_id = package["edges"][0]["route_identity_ids"][0]
    source_provenance = {
        "kind": "source",
        "source_id": package["source"]["source_id"],
        "source_record_id": "exit-205",
        "artifact_sha256": ARTIFACT_HASH,
        "derivation": "",
        "authored_override_id": "",
    }
    package["semantics"]["exits"] = [
        {
            "id": "exit-205",
            "junction_node_id": "junction",
            "ramp_edge_id": "ramp",
            "route_identity_id": identity_id,
            "number": "205",
            "suffix": "",
            "destinations": ["Silverthorne", "Dillon"],
            "services": ["fuel", "food"],
            "provenance": source_provenance,
        }
    ]
    validate_route_semantics(package)
    return package


def _mainline_connectors(package: dict) -> list[dict]:
    return [
        connector
        for connector in package["semantics"]["junction_connectors"]
        if connector["to_edge_id"] == "mainline"
    ]


def test_representative_contract_locks_its_inputs() -> None:
    assert CONTRACT["schema_version"] == 4
    assert set(CONTRACT["connector_movements"]) == set(MOVEMENTS)
    for relative_path, expected_hash in CONTRACT["locked_inputs"].items():
        assert hashlib.sha256(Path(relative_path).read_bytes()).hexdigest() == expected_hash


def test_semantics_survive_flatbuffer_boundary_with_map_lods(tmp_path: Path) -> None:
    package = _junction_package()
    output = tmp_path / "route.cbrg"
    write_flatbuffer(package, output, include_samples=False)
    root = RouteGraphBuffer.GetRootAs(output.read_bytes())

    assert root.SchemaVersion() == 4
    assert root.LaneSectionsLength() == 3
    assert root.JunctionConnectorsLength() == 3
    assert root.RouteIdentitiesLength() == 1
    assert root.ExitsLength() == 1
    assert root.MilepointAnchorsLength() == 6
    assert root.RoadsideMarkersLength() == 3
    assert root.SimplifiedMapGeometryLength() == 9
    assert root.Exits(0).DestinationsLength() == 2
    assert root.Exits(0).ServicesLength() == 2
    assert {
        root.SimplifiedMapGeometry(index).Lod()
        for index in range(root.SimplifiedMapGeometryLength())
    } == {0, 1, 2}


@pytest.mark.parametrize(
    "movement",
    CONTRACT["connector_movements"],
)
def test_all_declared_connector_movements_validate(movement: str) -> None:
    package = _junction_package()
    for connector in package["semantics"]["junction_connectors"]:
        connector["movement"] = movement
        from_lane_id = connector["from_lane_id"]
        for section in package["semantics"]["lane_sections"]:
            for lane in section["lanes"]:
                if lane["id"] == from_lane_id:
                    lane["allowed_maneuvers"] |= MOVEMENTS[movement]

    validate_route_semantics(package)


def test_variable_lane_sections_preserve_stable_lane_identity() -> None:
    package = _junction_package()
    edge = next(edge for edge in package["edges"] if edge["edge_id"] == "mainline")
    section = next(
        section
        for section in package["semantics"]["lane_sections"]
        if section["edge_id"] == "mainline"
    )
    first = deepcopy(section)
    first["id"] = "mainline-before-drop"
    first["end_meters"] = 50.0
    second = deepcopy(section)
    second["id"] = "mainline-after-drop"
    second["start_meters"] = 50.0
    second["lanes"] = [deepcopy(section["lanes"][1])]
    second["lanes"][0]["index"] = 0
    package["semantics"]["lane_sections"].remove(section)
    package["semantics"]["lane_sections"].extend([first, second])
    edge["lane_section_ids"] = [first["id"], second["id"]]

    validate_route_semantics(package)

    assert first["lanes"][1]["id"] == second["lanes"][0]["id"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("gap", "gap or overlap"),
        ("orphan", "orphaned"),
        ("crossing", "cross lanes"),
        ("ambiguous", "ambiguous lane successor"),
        ("disallowed", "not allowed by lane"),
        ("map-hash", "hash is invalid"),
    ],
)
def test_malformed_semantics_fail_actionably(mutation: str, message: str) -> None:
    package = deepcopy(_junction_package())
    if mutation == "gap":
        package["semantics"]["lane_sections"][0]["start_meters"] = 1.0
    elif mutation == "orphan":
        connector = _mainline_connectors(package)[-1]
        package["semantics"]["junction_connectors"].remove(connector)
    elif mutation == "crossing":
        connectors = _mainline_connectors(package)
        connectors[0]["to_lane_id"], connectors[1]["to_lane_id"] = (
            connectors[1]["to_lane_id"],
            connectors[0]["to_lane_id"],
        )
    elif mutation == "ambiguous":
        duplicate = deepcopy(package["semantics"]["junction_connectors"][0])
        duplicate["id"] = "duplicate-successor"
        duplicate["movement"] = "highway_transfer"
        from_lane_id = duplicate["from_lane_id"]
        for section in package["semantics"]["lane_sections"]:
            for lane in section["lanes"]:
                if lane["id"] == from_lane_id:
                    lane["allowed_maneuvers"] |= MANEUVER_TRANSFER
        package["semantics"]["junction_connectors"].append(duplicate)
    elif mutation == "disallowed":
        connector = package["semantics"]["junction_connectors"][0]
        connector["movement"] = "highway_transfer"
    else:
        package["semantics"]["simplified_map_geometry"][0]["content_hash"] = "0" * 64

    with pytest.raises(ValueError, match=message):
        validate_route_semantics(package)


def test_authored_override_requires_stable_ancestry() -> None:
    package = _junction_package()
    provenance = package["semantics"]["lane_sections"][0]["provenance"]
    provenance["kind"] = "authored_override"
    provenance["authored_override_id"] = ""

    with pytest.raises(ValueError, match="missing its override ID"):
        validate_route_semantics(package)

    provenance["authored_override_id"] = "manual-lanes-i70-205-v1"
    validate_route_semantics(package)


def test_geopackage_contains_equivalent_semantic_audit_tables(tmp_path: Path) -> None:
    output = tmp_path / "audit"
    package = build_route_graph(
        Path("data/sources/fixtures/nhpn-boulder-us36.geojson"),
        Path("data/sources/fixtures/nhpn-boulder-us36.manifest.json"),
        output,
        catalog_path=Path("data/sources/catalog.json"),
    )
    table_keys = {
        "route_lane_sections": "lane_sections",
        "route_junction_connectors": "junction_connectors",
        "route_identities": "route_identities",
        "route_exits": "exits",
        "route_milepoint_anchors": "milepoint_anchors",
        "route_roadside_markers": "roadside_markers",
        "route_simplified_map_geometry": "simplified_map_geometry",
    }

    with sqlite3.connect(output / "normalized.gpkg") as connection:
        for table, key in table_keys.items():
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == len(package["semantics"][key])
