from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from Cannonball.Content.RouteChunkBuffer import RouteChunkBuffer
from Cannonball.Content.RouteGraphBuffer import RouteGraphBuffer
from cannonball_map.cli import app
from cannonball_map.elevation import ElevationMetadata, ElevationSampler
from cannonball_map.pipeline import build_route_graph
from cannonball_map.sharding import (
    MAX_CHUNK_BYTES,
    MAX_ROOT_BYTES,
    _continuation_endpoint_tangents,
    write_sharded_package,
)


def _official_package(tmp_path: Path) -> dict[str, object]:
    raster = Path("data/sources/fixtures/usgs-13-n40w106-boulder.tif")
    metadata = ElevationMetadata(
        **json.loads(
            Path("data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json").read_text()
        )
    )
    lock = Path("data/sources/source-lock.json")
    with ElevationSampler(raster, metadata, "EPSG:5070") as sampler:
        return build_route_graph(
            Path("data/sources/fixtures/nhpn-boulder-us36.geojson"),
            Path("data/sources/fixtures/nhpn-boulder-us36.manifest.json"),
            tmp_path / "audit",
            catalog_path=Path("data/sources/catalog.json"),
            elevation_sampler=sampler,
            acquisition_lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
            chunk_meters=100.0,
        )


def test_official_fixture_emits_deterministic_bounded_shards(tmp_path: Path) -> None:
    package = _official_package(tmp_path)
    first = write_sharded_package(package, tmp_path / "first")
    second = write_sharded_package(package, tmp_path / "second")
    first_root = _current_root(tmp_path / "first").read_bytes()
    second_root = _current_root(tmp_path / "second").read_bytes()

    assert first_root == second_root
    assert len(first_root) < MAX_ROOT_BYTES
    root = RouteGraphBuffer.GetRootAs(first_root)
    assert root.SchemaVersion() == 4
    assert root.Edges(0).SamplesLength() == 0
    assert root.LaneSectionsLength() == len(package["semantics"]["lane_sections"])
    assert root.RouteIdentitiesLength() == len(package["semantics"]["route_identities"])
    assert root.MilepointAnchorsLength() == len(package["semantics"]["milepoint_anchors"])
    assert root.RoadsideMarkersLength() == len(package["semantics"]["roadside_markers"])
    assert root.SimplifiedMapGeometryLength() == 3 * root.EdgesLength()
    assert root.SpatialReference().VerticalDatum().decode() == (
        "North American Vertical Datum of 1988"
    )
    assert first["content_version"] == second["content_version"]

    for chunk in first["chunks"]:
        assert Path(chunk["relative_path"]).name == (
            hashlib.sha256(chunk["chunk_id"].encode()).hexdigest() + ".cbck"
        )
        first_bytes = (tmp_path / "first" / chunk["relative_path"]).read_bytes()
        second_bytes = (tmp_path / "second" / chunk["relative_path"]).read_bytes()
        assert first_bytes == second_bytes
        assert len(first_bytes) < MAX_CHUNK_BYTES
        assert chunk["byte_count"] == len(first_bytes)
        assert chunk["content_hash"] == hashlib.sha256(first_bytes).hexdigest()
        payload = RouteChunkBuffer.GetRootAs(first_bytes)
        assert payload.Id().decode() == chunk["chunk_id"]
        assert payload.EdgeId().decode() == chunk["edge_id"]
        assert payload.ContentVersion().decode() == first["content_version"]
        assert payload.SamplesLength() > 0
        assert payload.Samples(0).ElevationMeters() > 0

    for before, after in zip(first["chunks"], first["chunks"][1:], strict=False):
        before_bytes = (tmp_path / "first" / before["relative_path"]).read_bytes()
        after_bytes = (tmp_path / "first" / after["relative_path"]).read_bytes()
        before_payload = RouteChunkBuffer.GetRootAs(before_bytes)
        after_payload = RouteChunkBuffer.GetRootAs(after_bytes)
        before_end = before_payload.Samples(before_payload.SamplesLength() - 1)
        after_start = after_payload.Samples(0)
        assert before_end.DistanceMeters() == after_start.DistanceMeters()
        assert before_end.ProjectedXMeters() == after_start.ProjectedXMeters()
        assert before_end.ProjectedYMeters() == after_start.ProjectedYMeters()
        assert before_end.ElevationMeters() == after_start.ElevationMeters()
        assert before_end.ProjectedTangentX() == after_start.ProjectedTangentX()
        assert before_end.ProjectedTangentY() == after_start.ProjectedTangentY()


def test_continuation_endpoints_share_the_angle_bisector_tangent() -> None:
    edges = {
        "incoming": {
            "samples": [
                {"distance_meters": 0.0, "projected_x_meters": 0.0, "projected_y_meters": 0.0},
                {"distance_meters": 100.0, "projected_x_meters": 100.0, "projected_y_meters": 0.0},
            ]
        },
        "outgoing": {
            "samples": [
                {"distance_meters": 0.0, "projected_x_meters": 100.0, "projected_y_meters": 0.0},
                {"distance_meters": 100.0, "projected_x_meters": 200.0, "projected_y_meters": 20.0},
            ]
        },
    }
    semantics = {
        "junction_connectors": [
            {
                "from_edge_id": "incoming",
                "to_edge_id": "outgoing",
                "movement": "merge",
            },
            {
                "from_edge_id": "incoming",
                "to_edge_id": "outgoing",
                "movement": "continuation",
            },
        ]
    }

    tangents = _continuation_endpoint_tangents(edges, semantics)

    assert tangents[("incoming", "end")] == pytest.approx(
        tangents[("outgoing", "start")]
    )
    assert tangents[("incoming", "end")][0] < 1.0
    assert tangents[("incoming", "end")][1] > 0.0


def test_runtime_build_requires_elevation_contract(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "build",
            "--source",
            "data/sources/fixtures/nhpn-boulder-us36.geojson",
            "--manifest",
            "data/sources/fixtures/nhpn-boulder-us36.manifest.json",
            "--output",
            str(tmp_path / "rejected"),
        ],
    )

    assert result.exit_code == 2
    assert "runtime schema 4 requires elevation" in result.output


def test_two_clean_official_cli_builds_are_byte_deterministic(tmp_path: Path) -> None:
    outputs = [tmp_path / "first-cli", tmp_path / "second-cli"]
    for output in outputs:
        result = CliRunner().invoke(
            app,
            [
                "build",
                "--source",
                "data/sources/fixtures/nhpn-boulder-us36.geojson",
                "--manifest",
                "data/sources/fixtures/nhpn-boulder-us36.manifest.json",
                "--elevation",
                "data/sources/fixtures/usgs-13-n40w106-boulder.tif",
                "--elevation-metadata",
                "data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json",
                "--acquisition-lock",
                "data/sources/source-lock.json",
                "--chunk-meters",
                "100",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, result.output

    first_metadata = _current_metadata(outputs[0])
    second_metadata = _current_metadata(outputs[1])
    assert _current_root(outputs[0]).read_bytes() == _current_root(outputs[1]).read_bytes()
    assert first_metadata.read_bytes() == second_metadata.read_bytes()
    assert b"\r" not in first_metadata.read_bytes()
    assert b"\r" not in (outputs[0] / "current-package.json").read_bytes()
    first_package = json.loads(first_metadata.read_text(encoding="utf-8"))
    second_package = json.loads(second_metadata.read_text(encoding="utf-8"))
    assert first_package["audit_artifacts"] == second_package["audit_artifacts"]
    first_audit = outputs[0] / first_package["audit_artifacts"][0]["relative_path"]
    second_audit = outputs[1] / second_package["audit_artifacts"][0]["relative_path"]
    first_audit_bytes = first_audit.read_bytes()
    assert first_audit_bytes == second_audit.read_bytes()
    assert first_audit_bytes[24:28] == first_audit_bytes[92:96] == (1).to_bytes(4, "big")


def test_deterministic_rebuild_reuses_identical_versioned_chunks(tmp_path: Path) -> None:
    package = _official_package(tmp_path)
    output = tmp_path / "published"
    first = write_sharded_package(package, output)
    before = _published_files(output)

    second = write_sharded_package(package, output)

    assert second == first
    assert _published_files(output) == before
    assert not list(tmp_path.glob(".published-staging-*"))


def test_shuffled_chunks_publish_in_canonical_edge_order(tmp_path: Path) -> None:
    package = deepcopy(_official_package(tmp_path))
    package["chunks"].reverse()

    published = write_sharded_package(package, tmp_path / "published")
    root = RouteGraphBuffer.GetRootAs(_current_root(tmp_path / "published").read_bytes())
    expected = [chunk["chunk_id"] for chunk in published["chunks"]]
    actual = [
        root.Edges(0).ChunkIds(index).decode()
        for index in range(root.Edges(0).ChunkIdsLength())
    ]

    assert actual == expected
    assert [chunk["start_meters"] for chunk in published["chunks"]] == sorted(
        chunk["start_meters"] for chunk in published["chunks"]
    )


def test_package_root_is_the_last_published_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _official_package(tmp_path)
    destinations: list[str] = []
    real_replace = __import__("os").replace

    def recording_replace(source: Path, destination: Path) -> None:
        destinations.append(Path(destination).name)
        real_replace(source, destination)

    monkeypatch.setattr("cannonball_map.sharding.os.replace", recording_replace)

    write_sharded_package(package, tmp_path / "published")

    assert destinations[-1] == "current-package.json"


def test_chunk_budget_fails_before_publishing_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _official_package(tmp_path)
    monkeypatch.setattr("cannonball_map.sharding.MAX_CHUNK_BYTES", 1)

    with pytest.raises(ValueError, match="exceeds 16 MB"):
        write_sharded_package(package, tmp_path / "rejected")

    assert not (tmp_path / "rejected/current-package.json").exists()
    assert not list(tmp_path.glob(".rejected-staging-*"))


def test_failed_rebuild_preserves_published_package_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _official_package(tmp_path)
    output = tmp_path / "published"
    write_sharded_package(package, output)
    before = _published_files(output)
    monkeypatch.setattr("cannonball_map.sharding.MAX_ROOT_BYTES", 1)

    with pytest.raises(ValueError, match="exceeds 64 MB"):
        write_sharded_package(package, output)

    assert _published_files(output) == before
    assert not list(tmp_path.glob(".published-staging-*"))


def test_audit_artifact_is_content_addressed_and_failure_does_not_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _official_package(tmp_path)
    audit = tmp_path / "normalized.gpkg"
    audit.write_bytes(b"inspectable-audit")
    published = write_sharded_package(
        package,
        tmp_path / "published",
        audit_artifacts={"normalized.gpkg": audit},
    )
    artifact = published["audit_artifacts"][0]
    assert (tmp_path / "published" / artifact["relative_path"]).read_bytes() == audit.read_bytes()
    assert artifact["sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()

    rejected = tmp_path / "rejected"
    monkeypatch.setattr("cannonball_map.sharding.MAX_ROOT_BYTES", 1)
    with pytest.raises(ValueError, match="exceeds 64 MB"):
        write_sharded_package(
            package,
            rejected,
            audit_artifacts={"normalized.gpkg": audit},
        )
    assert not (rejected / "current-package.json").exists()
    assert not (rejected / "audit").exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("distance_meters", float("nan"), "non-finite 'distance_meters'"),
        ("projected_x_meters", float("inf"), "non-finite 'projected_x_meters'"),
        ("grade", float("-inf"), "non-finite 'grade'"),
    ],
)
def test_non_finite_samples_are_rejected_before_publication(
    tmp_path: Path,
    field: str,
    value: float,
    message: str,
) -> None:
    package = deepcopy(_official_package(tmp_path))
    package["edges"][0]["samples"][1][field] = value
    output = tmp_path / "rejected"

    with pytest.raises(ValueError, match=message):
        write_sharded_package(package, output)

    assert not (output / "current-package.json").exists()
    assert not list(tmp_path.glob(".rejected-staging-*"))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda package: package["chunks"][0].update(start_meters=10.0, end_meters=5.0),
            "positive distance range",
        ),
        (
            lambda package: package["chunks"][0].update(start_meters=-1.0),
            "outside its edge sample range",
        ),
        (
            lambda package: package["chunks"][-1].update(
                end_meters=package["chunks"][-1]["end_meters"] - 1
            ),
            "cover its complete sample range",
        ),
    ],
)
def test_invalid_chunk_ranges_are_rejected(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    package = deepcopy(_official_package(tmp_path))
    mutate(package)

    with pytest.raises(ValueError, match=message):
        write_sharded_package(package, tmp_path / "rejected")


def test_unsafe_chunk_id_is_rejected(tmp_path: Path) -> None:
    package = deepcopy(_official_package(tmp_path))
    package["chunks"][0]["chunk_id"] = "../escape"

    with pytest.raises(ValueError, match="not safe for publication"):
        write_sharded_package(package, tmp_path / "rejected")


def test_case_distinct_chunk_ids_have_portable_distinct_filenames(tmp_path: Path) -> None:
    assert hashlib.sha256(b"Chunk").hexdigest() != hashlib.sha256(b"chunk").hexdigest()
    assert not {"CON.cbck", "NUL.cbck"} & {
        hashlib.sha256(value.encode()).hexdigest() + ".cbck"
        for value in ("CON", "NUL", "Chunk", "chunk")
    }


def _published_files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _current_root(directory: Path) -> Path:
    pointer = json.loads((directory / "current-package.json").read_text(encoding="utf-8"))
    return directory / pointer["root_relative_path"]


def _current_metadata(directory: Path) -> Path:
    pointer = json.loads((directory / "current-package.json").read_text(encoding="utf-8"))
    return directory / pointer["metadata_relative_path"]
