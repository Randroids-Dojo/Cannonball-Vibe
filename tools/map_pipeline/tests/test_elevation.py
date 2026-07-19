from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from Cannonball.Content.RouteGraphBuffer import RouteGraphBuffer
from cannonball_map.elevation import ElevationMetadata, ElevationSampler
from cannonball_map.flatbuffer_writer import write_flatbuffer
from cannonball_map.pipeline import build_route_graph


def test_official_fixture_preserves_elevation_grade_datums_and_provenance(
    tmp_path: Path,
) -> None:
    source = Path("data/sources/fixtures/nhpn-boulder-us36.geojson")
    manifest = Path("data/sources/fixtures/nhpn-boulder-us36.manifest.json")
    raster = Path("data/sources/fixtures/usgs-13-n40w106-boulder.tif")
    metadata = ElevationMetadata(
        product_id="620de4b0d34e6c7e83ba9fde",
        product_title="USGS 1/3 Arc Second n40w106 20220216",
        product_resolution="1/3 arc-second",
        raster_crs="EPSG:4269",
        horizontal_datum="North American Datum of 1983",
        vertical_datum="North American Vertical Datum of 1988",
        elevation_units="meters",
        artifact_sha256=hashlib.sha256(raster.read_bytes()).hexdigest(),
    )
    lock_digest = hashlib.sha256(Path("data/sources/source-lock.json").read_bytes()).hexdigest()
    with ElevationSampler(raster, metadata, "EPSG:5070") as sampler:
        package = build_route_graph(
            source,
            manifest,
            tmp_path / "output",
            catalog_path=Path("data/sources/catalog.json"),
            elevation_sampler=sampler,
            acquisition_lock_sha256=lock_digest,
        )

    assert package["schema_version"] == 5
    assert package["spatial_reference"]["route_crs"] == "EPSG:5070"
    assert package["spatial_reference"]["vertical_datum"] == (
        "North American Vertical Datum of 1988"
    )
    samples = package["edges"][0]["samples"]
    assert all(sample["elevation_meters"] > 0 for sample in samples)
    assert any(abs(sample["grade"]) > 1e-6 for sample in samples)

    output = tmp_path / "route_graph.cbrg"
    write_flatbuffer(package, output)
    root = RouteGraphBuffer.GetRootAs(output.read_bytes())
    assert root.SchemaVersion() == 5
    assert root.SpatialReference().VerticalDatum().decode() == (
        "North American Vertical Datum of 1988"
    )
    assert root.Provenance().AcquisitionLockSha256().decode() == lock_digest


def test_sampler_fails_on_crs_disagreement() -> None:
    raster = Path("data/sources/fixtures/usgs-13-n40w106-boulder.tif")
    metadata = ElevationMetadata(
        "id",
        "title",
        "resolution",
        "EPSG:4326",
        "datum",
        "vertical",
        "meters",
        hashlib.sha256(raster.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="CRS mismatch"):
        ElevationSampler(raster, metadata, "EPSG:5070")


def test_sampler_fails_on_hash_drift() -> None:
    metadata = ElevationMetadata(
        "id", "title", "resolution", "EPSG:4269", "datum", "vertical", "meters", "0" * 64
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ElevationSampler(
            Path("data/sources/fixtures/usgs-13-n40w106-boulder.tif"),
            metadata,
            "EPSG:5070",
        )


def test_representative_corridor_conditions_surface_spikes_and_shared_seams(
    tmp_path: Path,
) -> None:
    source = Path("data/sources/fixtures/nhpn-boulder-westminster-us36.geojson")
    manifest = Path("data/sources/fixtures/nhpn-boulder-westminster-us36.manifest.json")
    raster = Path("data/sources/fixtures/usgs-13-n40w106-boulder-westminster.tif")
    metadata = ElevationMetadata(
        product_id="620de4b0d34e6c7e83ba9fde",
        product_title="USGS 1/3 Arc Second n40w106 20220216",
        product_resolution="1/3 arc-second",
        raster_crs="EPSG:4269",
        horizontal_datum="North American Datum of 1983",
        vertical_datum="North American Vertical Datum of 1988",
        elevation_units="meters",
        artifact_sha256=hashlib.sha256(raster.read_bytes()).hexdigest(),
    )
    lock_digest = hashlib.sha256(
        Path("data/sources/representative-corridor-lock.json").read_bytes()
    ).hexdigest()
    with ElevationSampler(raster, metadata, "EPSG:5070") as sampler:
        package = build_route_graph(
            source,
            manifest,
            tmp_path / "representative",
            catalog_path=Path("data/sources/catalog.json"),
            elevation_sampler=sampler,
            acquisition_lock_sha256=lock_digest,
        )

    edges = package["edges"]
    assert max(abs(sample["grade"]) for edge in edges for sample in edge["samples"]) <= 0.0700001
    by_from = {edge["from_node_id"]: edge for edge in edges}
    for edge in edges:
        continuation = by_from.get(edge["to_node_id"])
        if continuation is not None:
            assert (
                edge["samples"][-1]["elevation_meters"]
                == (continuation["samples"][0]["elevation_meters"])
            )
