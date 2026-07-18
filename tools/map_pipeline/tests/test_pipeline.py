import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiLineString

from Cannonball.Content.RouteGraphBuffer import RouteGraphBuffer
from cannonball_map.flatbuffer_writer import write_flatbuffer
from cannonball_map.pipeline import PROJECTED_CRS, build_route_graph

ANCHOR_X = -338_400.0
ANCHOR_Y = 1_894_100.0
SOURCE_ID_FIELD = "source_feature_id"


def _write_source(
    tmp_path: Path,
    name: str,
    records: list[tuple[str, LineString | MultiLineString]],
) -> tuple[Path, Path]:
    source = tmp_path / f"{name}.gpkg"
    frame = gpd.GeoDataFrame(
        {
            SOURCE_ID_FIELD: [source_id for source_id, _ in records],
            "geometry": [geometry for _, geometry in records],
        },
        crs=PROJECTED_CRS,
    )
    frame.to_file(source, layer="route_edges", driver="GPKG", index=False)
    manifest = tmp_path / f"{name}.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_id": "synthetic-public-domain-fixture",
                "publisher": "Test Federal Agency",
                "source_url": "https://example.gov/route",
                "acquired_on": "2026-07-15",
                "license_status": "public_domain",
                "license_evidence_url": "https://example.gov/public-domain",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "derived_from": [],
            }
        ),
        encoding="utf-8",
    )
    return source, manifest


def _read_artifacts(output: Path) -> tuple[dict[str, object], gpd.GeoDataFrame]:
    package = json.loads((output / "route_graph.json").read_text(encoding="utf-8"))
    normalized = gpd.read_file(output / "normalized.gpkg", layer="route_edges")
    return package, normalized


def _assert_edge_source_geometry_pairing(
    package: dict[str, object],
    normalized: gpd.GeoDataFrame,
    expected_by_source: dict[str, LineString],
) -> None:
    assert normalized.crs == PROJECTED_CRS
    assert {"edge_id", SOURCE_ID_FIELD, "geometry"} <= set(normalized.columns)
    assert normalized["edge_id"].is_unique

    json_edges = {edge["edge_id"]: edge for edge in package["edges"]}
    gpkg_rows = normalized.set_index("edge_id", drop=False)
    assert len(json_edges) == len(package["edges"])
    assert list(json_edges) == sorted(json_edges)
    assert set(json_edges) == set(gpkg_rows.index)
    assert {edge[SOURCE_ID_FIELD] for edge in package["edges"]} == set(
        expected_by_source
    )

    for edge_id, edge in json_edges.items():
        row = gpkg_rows.loc[edge_id]
        source_feature_id = edge[SOURCE_ID_FIELD]
        assert row[SOURCE_ID_FIELD] == source_feature_id
        assert row["from_node_id"] == edge["from_node_id"]
        assert row["to_node_id"] == edge["to_node_id"]
        assert row.geometry.equals_exact(
            expected_by_source[source_feature_id],
            tolerance=1e-8,
        )
        assert edge["length_meters"] == pytest.approx(row.geometry.length, abs=1e-8)
        assert edge["samples"][-1]["distance_meters"] == pytest.approx(
            row.geometry.length,
            abs=1e-8,
        )


def test_pipeline_builds_deterministic_connected_chunks(tmp_path: Path) -> None:
    source = tmp_path / "route.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source_feature_id": "segment-west"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-100.0, 40.0], [-99.99, 40.0]],
                        },
                    },
                    {
                        "type": "Feature",
                        "properties": {"source_feature_id": "segment-east"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-99.99, 40.0], [-99.98, 40.0]],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "route.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_id": "synthetic-public-domain-fixture",
                "publisher": "Test Federal Agency",
                "source_url": "https://example.gov/route",
                "acquired_on": "2026-07-14",
                "license_status": "public_domain",
                "license_evidence_url": "https://example.gov/public-domain",
                "sha256": digest,
                "derived_from": [],
            }
        ),
        encoding="utf-8",
    )

    first = build_route_graph(source, manifest, tmp_path / "first", chunk_meters=500)
    second = build_route_graph(source, manifest, tmp_path / "second", chunk_meters=500)

    assert first["content_version"] == second["content_version"]
    assert len(first["edges"]) == 2
    assert len(first["chunks"]) >= 4
    runtime_path = tmp_path / "first" / "route_graph.cbrg"
    write_flatbuffer(first, runtime_path)
    payload = runtime_path.read_bytes()
    assert RouteGraphBuffer.RouteGraphBufferBufferHasIdentifier(payload, 0)
    root = RouteGraphBuffer.GetRootAs(payload)
    assert root.SchemaVersion() == 4
    assert root.EdgesLength() == 2


def test_reversed_feature_order_preserves_semantic_edge_records(tmp_path: Path) -> None:
    records = [
        (
            "source-west",
            LineString(
                [
                    (ANCHOR_X, ANCHOR_Y),
                    (ANCHOR_X + 50.0, ANCHOR_Y + 20.0),
                    (ANCHOR_X + 100.0, ANCHOR_Y),
                ]
            ),
        ),
        (
            "source-east",
            LineString(
                [
                    (ANCHOR_X + 100.0, ANCHOR_Y),
                    (ANCHOR_X + 150.0, ANCHOR_Y - 30.0),
                    (ANCHOR_X + 200.0, ANCHOR_Y),
                ]
            ),
        ),
    ]
    expected = dict(records)
    forward_source, forward_manifest = _write_source(tmp_path, "forward", records)
    reverse_source, reverse_manifest = _write_source(
        tmp_path,
        "reverse",
        list(reversed(records)),
    )
    forward_output = tmp_path / "forward-output"
    reverse_output = tmp_path / "reverse-output"

    build_route_graph(forward_source, forward_manifest, forward_output)
    build_route_graph(reverse_source, reverse_manifest, reverse_output)
    forward, forward_gpkg = _read_artifacts(forward_output)
    reverse, reverse_gpkg = _read_artifacts(reverse_output)

    _assert_edge_source_geometry_pairing(forward, forward_gpkg, expected)
    _assert_edge_source_geometry_pairing(reverse, reverse_gpkg, expected)
    assert forward["nodes"] == reverse["nodes"]
    assert forward["edges"] == reverse["edges"]
    assert forward["chunks"] == reverse["chunks"]
    forward_rows = sorted(
        zip(
            forward_gpkg["edge_id"],
            forward_gpkg[SOURCE_ID_FIELD],
            forward_gpkg.geometry.to_wkb(hex=True),
            strict=True,
        )
    )
    reverse_rows = sorted(
        zip(
            reverse_gpkg["edge_id"],
            reverse_gpkg[SOURCE_ID_FIELD],
            reverse_gpkg.geometry.to_wkb(hex=True),
            strict=True,
        )
    )
    assert forward_rows == reverse_rows


def test_parallel_directed_edges_are_preserved(tmp_path: Path) -> None:
    records = [
        (
            "parallel-north",
            LineString(
                [
                    (ANCHOR_X, ANCHOR_Y),
                    (ANCHOR_X + 50.0, ANCHOR_Y + 30.0),
                    (ANCHOR_X + 100.0, ANCHOR_Y),
                ]
            ),
        ),
        (
            "parallel-south",
            LineString(
                [
                    (ANCHOR_X, ANCHOR_Y),
                    (ANCHOR_X + 50.0, ANCHOR_Y - 30.0),
                    (ANCHOR_X + 100.0, ANCHOR_Y),
                ]
            ),
        ),
    ]
    source, manifest = _write_source(tmp_path, "parallel", records)
    output = tmp_path / "parallel-output"

    build_route_graph(source, manifest, output)
    package, normalized = _read_artifacts(output)
    _assert_edge_source_geometry_pairing(package, normalized, dict(records))

    edges = package["edges"]
    assert len(edges) == 2
    assert len({edge["edge_id"] for edge in edges}) == 2
    assert {edge[SOURCE_ID_FIELD] for edge in edges} == {
        "parallel-north",
        "parallel-south",
    }
    assert len({(edge["from_node_id"], edge["to_node_id"]) for edge in edges}) == 1


def test_stacked_3d_parallel_edges_have_distinct_ids(tmp_path: Path) -> None:
    paths = MultiLineString(
        [
            LineString(
                [
                    (ANCHOR_X, ANCHOR_Y, 100.0),
                    (ANCHOR_X + 50.0, ANCHOR_Y, 110.0),
                    (ANCHOR_X + 100.0, ANCHOR_Y, 100.0),
                ]
            ),
            LineString(
                [
                    (ANCHOR_X, ANCHOR_Y, 100.0),
                    (ANCHOR_X + 50.0, ANCHOR_Y, 90.0),
                    (ANCHOR_X + 100.0, ANCHOR_Y, 100.0),
                ]
            ),
        ]
    )
    source, manifest = _write_source(
        tmp_path,
        "stacked-parallel",
        [("stacked-source", paths)],
    )

    package = build_route_graph(
        source,
        manifest,
        tmp_path / "stacked-parallel-output",
    )
    edges = package["edges"]

    assert len(edges) == 2
    assert len({edge["edge_id"] for edge in edges}) == 2
    assert len({(edge["from_node_id"], edge["to_node_id"]) for edge in edges}) == 1


def test_snapped_topology_emits_physically_continuous_geometry(tmp_path: Path) -> None:
    records = [
        (
            "seam-west",
            LineString(
                [
                    (ANCHOR_X, ANCHOR_Y),
                    (ANCHOR_X + 98.0, ANCHOR_Y + 2.0),
                ]
            ),
        ),
        (
            "seam-east",
            LineString(
                [
                    (ANCHOR_X + 102.0, ANCHOR_Y - 2.0),
                    (ANCHOR_X + 200.0, ANCHOR_Y),
                ]
            ),
        ),
    ]
    expected = {
        "seam-west": LineString(
            [(ANCHOR_X, ANCHOR_Y), (ANCHOR_X + 100.0, ANCHOR_Y)]
        ),
        "seam-east": LineString(
            [(ANCHOR_X + 100.0, ANCHOR_Y), (ANCHOR_X + 200.0, ANCHOR_Y)]
        ),
    }
    source, manifest = _write_source(tmp_path, "seam", records)
    output = tmp_path / "seam-output"

    build_route_graph(
        source,
        manifest,
        output,
        snap_tolerance_meters=10.0,
    )
    package, normalized = _read_artifacts(output)
    _assert_edge_source_geometry_pairing(package, normalized, expected)

    edges_by_source = {edge[SOURCE_ID_FIELD]: edge for edge in package["edges"]}
    geometry_by_source = {
        row[SOURCE_ID_FIELD]: row.geometry for _, row in normalized.iterrows()
    }
    assert (
        edges_by_source["seam-west"]["to_node_id"]
        == edges_by_source["seam-east"]["from_node_id"]
    )
    assert geometry_by_source["seam-west"].coords[-1] == pytest.approx(
        geometry_by_source["seam-east"].coords[0],
        abs=1e-8,
    )
    assert geometry_by_source["seam-west"].coords[-1] == pytest.approx(
        (ANCHOR_X + 100.0, ANCHOR_Y),
        abs=1e-8,
    )


def test_vertical_endpoint_seam_fails_closed(tmp_path: Path) -> None:
    records = [
        (
            "seam-low",
            LineString(
                [
                    (ANCHOR_X, ANCHOR_Y, 100.0),
                    (ANCHOR_X + 100.0, ANCHOR_Y, 100.0),
                ]
            ),
        ),
        (
            "seam-high",
            LineString(
                [
                    (ANCHOR_X + 100.0, ANCHOR_Y, 105.0),
                    (ANCHOR_X + 200.0, ANCHOR_Y, 105.0),
                ]
            ),
        ),
    ]
    source, manifest = _write_source(tmp_path, "vertical-seam", records)

    with pytest.raises(ValueError, match="endpoints that do not meet"):
        build_route_graph(source, manifest, tmp_path / "vertical-seam-output")


def test_multiline_parts_retain_parent_source_feature_id(tmp_path: Path) -> None:
    parts = [
        LineString([(ANCHOR_X, ANCHOR_Y), (ANCHOR_X + 100.0, ANCHOR_Y)]),
        LineString(
            [(ANCHOR_X + 100.0, ANCHOR_Y), (ANCHOR_X + 200.0, ANCHOR_Y)]
        ),
    ]
    source, manifest = _write_source(
        tmp_path,
        "multiline",
        [("multi-source", MultiLineString(parts))],
    )
    output = tmp_path / "multiline-output"

    build_route_graph(source, manifest, output)
    package, normalized = _read_artifacts(output)

    assert len(package["edges"]) == 2
    assert {edge[SOURCE_ID_FIELD] for edge in package["edges"]} == {"multi-source"}
    assert set(normalized[SOURCE_ID_FIELD]) == {"multi-source"}
    assert set(normalized.geometry.to_wkb(hex=True)) == {
        part.wkb_hex for part in parts
    }


def test_exact_duplicate_edge_ids_fail_closed(tmp_path: Path) -> None:
    duplicate = LineString(
        [(ANCHOR_X, ANCHOR_Y), (ANCHOR_X + 100.0, ANCHOR_Y)]
    )
    source, manifest = _write_source(
        tmp_path,
        "duplicate",
        [("duplicate-source", duplicate), ("duplicate-source", duplicate)],
    )

    with pytest.raises(ValueError, match="Duplicate route edge ID"):
        build_route_graph(source, manifest, tmp_path / "duplicate-output")
