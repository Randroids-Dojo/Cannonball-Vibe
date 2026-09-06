from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from shapely.geometry import LineString
from typer.testing import CliRunner

from cannonball_map.cli import app
from cannonball_map.continental_collision import _sha
from cannonball_map.continental_package import (
    authenticated_westbound_line,
    build_continental_package_dict,
    edge_samples,
    lane_sections,
    package_chunks,
)
from cannonball_map.semantics import validate_route_semantics
from cannonball_map.sharding import MAX_CHUNK_BYTES, MAX_ROOT_BYTES, write_sharded_package

REPO_ROOT = Path(__file__).resolve().parents[3]
SEGMENT = "i70-denver-to-cove-fort"
ARTIFACT = "a" * 64
SOURCE = {
    "source_id": "usdot-national-highway-planning-network",
    "publisher": "U.S. Department of Transportation",
    "source_url": "https://example.invalid/nhpn",
    "acquired_on": "2026-07-31",
    "license_status": "public_domain",
    "sha256": ARTIFACT,
    "acquisition_lock_sha256": "b" * 64,
}
SPATIAL = {
    "route_crs": "EPSG:5070",
    "elevation_crs": "EPSG:4269",
    "horizontal_datum": "NAD83",
    "vertical_datum": "NAVD88",
    "elevation_units": "meters",
    "elevation_product_id": "usgs-3dep",
    "elevation_product_title": "NED 1/3 arc-second",
    "elevation_product_resolution": "1/3 arc-second",
    "elevation_artifact_sha256": "c" * 64,
}


def _synthetic_inputs(length: float = 4_050.0) -> dict:
    line = LineString([(0.0, 0.0), (length, 0.0)])
    stations = int(length // 100) + 1
    elevations = [1_600.0 + index * 0.5 for index in range(stations)] + [1_600.0 + stations * 0.5]
    elevation_segment = {
        "segment_id": "fixture",
        "elevations_m": elevations,
        "station_interval_m": 100.0,
        "terminal_station_m": length,
        "station_count": len(elevations),
    }
    conditioned_segment = {"segment_id": "fixture", "conditioning_records": []}
    lane_segment = {
        "segment_id": "fixture",
        "sections": [
            {
                "section_id": "fixture--westbound--section-000",
                "start_m": 251.572,
                "end_m": 3_000.0,
                "lanes": [
                    {
                        "index": 0,
                        "lane_id": "fixture--lane-000",
                        "role": "general",
                        "width_m": 3.6576,
                    },
                    {
                        "index": 1,
                        "lane_id": "fixture--lane-001",
                        "role": "general",
                        "width_m": 3.6576,
                    },
                ],
                "left_shoulder_m": 1.2192,
                "right_shoulder_m": 3.048,
            },
            {
                "section_id": "fixture--westbound--section-001",
                "start_m": 3_000.0,
                "end_m": 3_800.0,
                "lanes": [
                    {
                        "index": 0,
                        "lane_id": "fixture--lane-000",
                        "role": "general",
                        "width_m": 3.6576,
                    },
                    {
                        "index": 1,
                        "lane_id": "fixture--lane-001",
                        "role": "general",
                        "width_m": 3.6576,
                    },
                ],
                "left_shoulder_m": 1.2192,
                "right_shoulder_m": 3.048,
            },
        ],
    }
    return {
        "line": line,
        "lane_segment": lane_segment,
        "elevation_segment": elevation_segment,
        "conditioned_segment": conditioned_segment,
        "source": SOURCE,
        "spatial_reference": SPATIAL,
        "from_anchor": "a",
        "to_anchor": "b",
    }


def _build_synthetic() -> dict:
    return build_continental_package_dict("fixture", **_synthetic_inputs())


def test_lane_sections_tile_the_whole_edge_and_keep_lane_ids() -> None:
    inputs = _synthetic_inputs()
    sections = lane_sections(
        "fixture",
        "fixture--westbound",
        4_050.0,
        inputs["lane_segment"]["sections"],
        SOURCE["source_id"],
        ARTIFACT,
    )
    assert sections[0]["start_meters"] == 0.0
    assert sections[-1]["end_meters"] == 4_050.0
    assert sections[0]["end_meters"] == 3_000.0
    assert [lane["id"] for lane in sections[0]["lanes"]] == [
        "fixture--lane-000",
        "fixture--lane-001",
    ]
    assert "span extended" in sections[0]["provenance"]["derivation"]
    assert "span extended" in sections[-1]["provenance"]["derivation"]


def test_samples_and_chunks_follow_the_collision_station_grid() -> None:
    inputs = _synthetic_inputs()
    samples = edge_samples(inputs["line"], [1_600.0, 1_610.0], 4_050.0)
    assert len(samples) == 163
    assert samples[0]["distance_meters"] == 0.0
    assert samples[-1]["distance_meters"] == 4_050.0
    assert samples[0]["elevation_meters"] == pytest.approx(1_600.0)
    assert samples[-1]["elevation_meters"] == pytest.approx(1_610.0)
    chunks = package_chunks("edge", 4_050.0, 2_000.0)
    assert [(chunk["start_meters"], chunk["end_meters"]) for chunk in chunks] == [
        (0.0, 2_000.0),
        (2_000.0, 4_000.0),
        (4_000.0, 4_050.0),
    ]


def test_synthetic_package_passes_route_semantics_and_uses_lock_widths() -> None:
    package = _build_synthetic()
    validate_route_semantics(package)
    edge = package["edges"][0]
    assert edge["roadway_kind"] == "one_way_roadway"
    assert edge["lane_count"] == 2
    assert edge["speed_limit_mps"] == pytest.approx(31.2928)
    assert len(package["semantics"]["lane_sections"]) == 2
    assert package["semantics"]["lane_sections"][0]["lanes"][0]["width_meters"] == 3.6576
    assert package["semantics"]["route_identities"][0]["number"] == "70"
    assert package["semantics"]["junction_connectors"] == []
    assert package["semantics"]["simplified_map_geometry"]


def test_two_synthetic_builds_are_byte_identical(tmp_path: Path) -> None:
    first = write_sharded_package(_build_synthetic(), tmp_path / "first")
    second = write_sharded_package(_build_synthetic(), tmp_path / "second")
    assert first["content_version"] == second["content_version"]
    for directory in (tmp_path / "first", tmp_path / "second"):
        pointer = json.loads((directory / "current-package.json").read_text())
        assert pointer["content_version"] == first["content_version"]
    first_files = sorted(
        path.relative_to(tmp_path / "first")
        for path in (tmp_path / "first").rglob("*")
        if path.is_file()
    )
    second_files = sorted(
        path.relative_to(tmp_path / "second")
        for path in (tmp_path / "second").rglob("*")
        if path.is_file()
    )
    assert first_files == second_files
    for relative in first_files:
        left = hashlib.sha256((tmp_path / "first" / relative).read_bytes()).hexdigest()
        right = hashlib.sha256((tmp_path / "second" / relative).read_bytes()).hexdigest()
        assert left == right, relative


def test_cache_that_does_not_match_the_carriageway_lock_is_refused(tmp_path: Path) -> None:
    coordinates = [[0.0, 0.0], [1_000.0, 0.0], [2_000.0, 10.0]]
    (tmp_path / "fixture.json").write_text(
        json.dumps({"metric_crs": "EPSG:5070", "westbound_coordinates": coordinates})
    )
    carriageway_lock = {
        "segments": [
            {
                "segment_id": "fixture",
                "westbound": {"geometry_sha256": _sha(coordinates), "vertex_count": 3},
            }
        ]
    }
    lane_lock = {"corner_refinements": []}
    line = authenticated_westbound_line("fixture", tmp_path, carriageway_lock, lane_lock)
    assert line.length == pytest.approx(2_000.05, abs=0.01)

    tampered = deepcopy(carriageway_lock)
    tampered["segments"][0]["westbound"]["geometry_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="does not match the westbound carriageway lock"):
        authenticated_westbound_line("fixture", tmp_path, tampered, lane_lock)
    with pytest.raises(ValueError, match="is missing"):
        authenticated_westbound_line("absent", tmp_path, carriageway_lock, lane_lock)


def test_cli_reports_a_clean_failure_without_the_cache(tmp_path: Path) -> None:
    (tmp_path / "cache").mkdir()
    result = CliRunner().invoke(
        app,
        [
            "build-continental-package",
            "--segment",
            SEGMENT,
            "--output",
            str(tmp_path / "package"),
            "--carriageway-cache",
            str(tmp_path / "cache"),
            "--collision-lock",
            str(REPO_ROOT / "data/routes/continental/collision-chunk-lock.v1.json"),
            "--lane-lock",
            str(REPO_ROOT / "data/routes/continental/lane-topology-lock.v1.json"),
            "--carriageway-lock",
            str(REPO_ROOT / "data/routes/continental/westbound-carriageway-lock.v1.json"),
            "--conditioned-lock",
            str(REPO_ROOT / "data/routes/continental/conditioned-profile-lock.v1.json"),
            "--elevation-lock",
            str(REPO_ROOT / "data/routes/continental/corridor-elevation-lock.v1.json"),
            "--dem-lock",
            str(REPO_ROOT / "data/routes/continental/3dep-product-lock.v1.json"),
            "--directed-route-lock",
            str(REPO_ROOT / "data/routes/continental/directed-route-lock.v1.json"),
            "--route-lock",
            str(REPO_ROOT / "data/sources/continental-route-lock.json"),
        ],
    )
    assert result.exit_code == 1
    assert "continental-package-failed:" in result.output
    assert "derive-continental-westbound-carriageway" in result.output


@pytest.mark.skipif(
    not (REPO_ROOT / ".tools/continental/carriageway" / f"{SEGMENT}.json").is_file(),
    reason="the digest-locked carriageway cache is an ignored artifact; absent on a clean checkout",
)
def test_repository_segment_builds_inside_the_adr_0019_ceilings(tmp_path: Path) -> None:
    from cannonball_map.continental_package import build_continental_package

    locks = REPO_ROOT / "data/routes/continental"
    provenance = build_continental_package(
        SEGMENT,
        collision_lock_path=locks / "collision-chunk-lock.v1.json",
        lane_lock_path=locks / "lane-topology-lock.v1.json",
        carriageway_lock_path=locks / "westbound-carriageway-lock.v1.json",
        conditioned_lock_path=locks / "conditioned-profile-lock.v1.json",
        elevation_lock_path=locks / "corridor-elevation-lock.v1.json",
        dem_lock_path=locks / "3dep-product-lock.v1.json",
        directed_route_lock_path=locks / "directed-route-lock.v1.json",
        route_lock_path=REPO_ROOT / "data/sources/continental-route-lock.json",
        carriageway_cache_directory=REPO_ROOT / ".tools/continental/carriageway",
        output_directory=tmp_path / "package",
    )
    collision = json.loads((locks / "collision-chunk-lock.v1.json").read_text(encoding="utf-8"))
    host = next(item for item in collision["hosts"] if item["host_id"] == SEGMENT)
    assert provenance["sample_count"] == host["sample_count"]
    assert provenance["chunk_count"] == host["chunk_count"]
    assert provenance["length_m"] == pytest.approx(host["length_m"], abs=0.01)
    assert provenance["root_bytes"] < MAX_ROOT_BYTES
    assert provenance["max_chunk_bytes"] < MAX_CHUNK_BYTES
    assert (tmp_path / "package" / "current-package.json").is_file()
