from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import flatbuffers

from Cannonball.Content.ChunkRouteSample import ChunkRouteSampleT
from Cannonball.Content.RouteChunkBuffer import RouteChunkBufferT
from cannonball_map.flatbuffer_writer import write_flatbuffer
from cannonball_map.semantics import validate_route_semantics

MAX_ROOT_BYTES = 64_000_000
MAX_CHUNK_BYTES = 16_000_000
_SAMPLE_FIELDS = (
    "distance_meters",
    "lateral_meters",
    "elevation_meters",
    "curvature",
    "grade",
    "projected_x_meters",
    "projected_y_meters",
)
_SAFE_CHUNK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def write_sharded_package(
    package: dict[str, Any],
    output_directory: Path,
    *,
    audit_artifacts: dict[str, Path] | None = None,
) -> dict[str, Any]:
    sharded = deepcopy(package)
    validate_route_semantics(sharded)
    semantic_chunks = _semantic_chunks(sharded)
    semantic_chunks.sort(key=_chunk_sort_key)
    sharded["chunks"].sort(key=_chunk_sort_key)
    version_payload = {
        "source_content_version": package["content_version"],
        "chunks": semantic_chunks,
        "semantics": sharded["semantics"],
    }
    digest = hashlib.sha256(
        json.dumps(version_payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    content_version = f"route-v4-{digest[:16]}"
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}-staging-",
            dir=output_directory.parent,
        )
    )
    try:
        chunk_directory = staging / "chunks" / content_version
        chunk_directory.mkdir(parents=True)
        hashes: dict[str, str] = {}
        byte_counts: dict[str, int] = {}
        for chunk in semantic_chunks:
            data = _chunk_bytes(chunk, content_version)
            if len(data) >= MAX_CHUNK_BYTES:
                raise ValueError(f"Runtime chunk '{chunk['chunk_id']}' exceeds 16 MB.")
            path = chunk_directory / _chunk_filename(chunk["chunk_id"])
            path.write_bytes(data)
            hashes[chunk["chunk_id"]] = hashlib.sha256(data).hexdigest()
            byte_counts[chunk["chunk_id"]] = len(data)

        sharded["schema_version"] = 4
        sharded["content_version"] = content_version
        for chunk in sharded["chunks"]:
            chunk["content_hash"] = hashes[chunk["chunk_id"]]
            chunk["byte_count"] = byte_counts[chunk["chunk_id"]]
            chunk["relative_path"] = (
                f"chunks/{content_version}/{_chunk_filename(chunk['chunk_id'])}"
            )
        if audit_artifacts:
            audit_directory = staging / "audit" / content_version
            audit_directory.mkdir(parents=True)
            sharded["audit_artifacts"] = []
            for name, source in sorted(audit_artifacts.items()):
                if Path(name).name != name or not source.is_file():
                    raise ValueError(f"Audit artifact '{name}' is invalid or missing.")
                data = source.read_bytes()
                artifact_hash = hashlib.sha256(data).hexdigest()
                artifact_name = f"{artifact_hash}-{name}"
                destination = audit_directory / artifact_name
                destination.write_bytes(data)
                sharded["audit_artifacts"].append(
                    {
                        "relative_path": f"audit/{content_version}/{artifact_name}",
                        "byte_count": len(data),
                        "sha256": artifact_hash,
                    }
                )

        staged_root = staging / "route_graph.cbrg"
        write_flatbuffer(sharded, staged_root, include_samples=False)
        if staged_root.stat().st_size >= MAX_ROOT_BYTES:
            raise ValueError("Runtime route root exceeds 64 MB.")
        staged_json = staging / "route_graph.json"
        staged_json.write_bytes(
            (json.dumps(sharded, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
        _publish(staging, output_directory, content_version)
        return sharded
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _publish(staging: Path, output_directory: Path, content_version: str) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    final_chunks_parent = output_directory / "chunks"
    final_chunks_parent.mkdir(exist_ok=True)
    staged_chunks = staging / "chunks" / content_version
    final_chunks = final_chunks_parent / content_version
    if final_chunks.exists():
        if not _directories_match(staged_chunks, final_chunks):
            raise ValueError(
                f"Published content version '{content_version}' has different chunk bytes."
            )
    else:
        staged_chunks.replace(final_chunks)

    staged_audit = staging / "audit" / content_version
    if staged_audit.exists():
        final_audit_parent = output_directory / "audit"
        final_audit_parent.mkdir(exist_ok=True)
        final_audit = final_audit_parent / content_version
        final_audit.mkdir(exist_ok=True)
        for staged_artifact in staged_audit.iterdir():
            final_artifact = final_audit / staged_artifact.name
            if final_artifact.exists():
                if staged_artifact.read_bytes() != final_artifact.read_bytes():
                    raise ValueError(
                        f"Published audit artifact '{staged_artifact.name}' has different bytes."
                    )
            else:
                staged_artifact.replace(final_artifact)

    staged_root = staging / "route_graph.cbrg"
    staged_json = staging / "route_graph.json"
    revision = hashlib.sha256(staged_root.read_bytes() + staged_json.read_bytes()).hexdigest()
    final_root = output_directory / f"route_graph-{revision}.cbrg"
    final_json = output_directory / f"route_graph-{revision}.json"
    _publish_immutable_file(staged_root, final_root)
    _publish_immutable_file(staged_json, final_json)

    # The tiny pointer is the sole package commit point. Roots, metadata, chunks,
    # and audits are immutable, so concurrent publishers can only choose which
    # complete revision becomes current; they cannot expose a mixed package.
    pointer = {
        "schema_version": 1,
        "content_version": content_version,
        "root_relative_path": final_root.name,
        "metadata_relative_path": final_json.name,
    }
    staged_pointer = staging / "current-package.json"
    staged_pointer.write_bytes(
        (json.dumps(pointer, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    os.replace(staged_pointer, output_directory / "current-package.json")


def _publish_immutable_file(source: Path, destination: Path) -> None:
    if destination.exists():
        if source.read_bytes() != destination.read_bytes():
            raise ValueError(f"Published artifact '{destination.name}' has different bytes.")
        return
    os.replace(source, destination)


def _directories_match(first: Path, second: Path) -> bool:
    first_files = sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second) for path in second.rglob("*") if path.is_file())
    if first_files != second_files:
        return False
    return all((first / path).read_bytes() == (second / path).read_bytes() for path in first_files)


def _chunk_filename(chunk_id: str) -> str:
    return f"{hashlib.sha256(chunk_id.encode('utf-8')).hexdigest()}.cbck"


def _chunk_sort_key(chunk: dict[str, Any]) -> tuple[str, float, float, str]:
    return (
        str(chunk["edge_id"]),
        float(chunk["start_meters"]),
        float(chunk["end_meters"]),
        str(chunk["chunk_id"]),
    )


def _semantic_chunks(package: dict[str, Any]) -> list[dict[str, Any]]:
    edges: dict[str, dict[str, Any]] = {}
    for edge in package["edges"]:
        edge_id = edge["edge_id"]
        if not isinstance(edge_id, str) or not edge_id:
            raise ValueError("Route package contains an invalid edge ID.")
        normalized_edge = dict(edge)
        normalized_edge["samples"] = _validated_edge_samples(edge_id, edge)
        edges[edge_id] = normalized_edge
    if len(edges) != len(package["edges"]):
        raise ValueError("Route package contains duplicate edge IDs.")
    chunk_ids = [chunk["chunk_id"] for chunk in package["chunks"]]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Route package contains duplicate chunk IDs.")
    result: list[dict[str, Any]] = []
    chunks_by_edge: dict[str, list[dict[str, Any]]] = {edge_id: [] for edge_id in edges}
    for chunk in package["chunks"]:
        chunk_id = chunk["chunk_id"]
        if not isinstance(chunk_id, str) or not _SAFE_CHUNK_ID.fullmatch(chunk_id):
            raise ValueError(f"Chunk ID '{chunk_id}' is not safe for publication.")
        if chunk["edge_id"] not in edges:
            raise ValueError(f"Chunk '{chunk_id}' references an unknown edge.")
        edge = edges[chunk["edge_id"]]
        samples = edge["samples"]
        start = _finite_number(chunk, "start_meters", f"Chunk '{chunk_id}'")
        end = _finite_number(chunk, "end_meters", f"Chunk '{chunk_id}'")
        if start >= end:
            raise ValueError(f"Chunk '{chunk_id}' must have a positive distance range.")
        if start < samples[0]["distance_meters"] or end > samples[-1]["distance_meters"]:
            raise ValueError(f"Chunk '{chunk_id}' extends outside its edge sample range.")
        normalized_chunk = {
            "chunk_id": chunk_id,
            "edge_id": chunk["edge_id"],
            "start_meters": start,
            "end_meters": end,
        }
        chunks_by_edge[chunk["edge_id"]].append(normalized_chunk)
        internal = [
            sample
            for sample in samples
            if start < sample["distance_meters"] < end
        ]
        chunk_samples = [
            _interpolate_sample(samples, start),
            *internal,
            _interpolate_sample(samples, end),
        ]
        runtime_samples = []
        for sample in chunk_samples:
            tangent_x, tangent_y = _projected_tangent(samples, sample["distance_meters"])
            runtime_samples.append(
                {
                    **{field: float(sample[field]) for field in _SAMPLE_FIELDS},
                    "projected_tangent_x": tangent_x,
                    "projected_tangent_y": tangent_y,
                }
            )
        result.append(
            {
                **normalized_chunk,
                "samples": runtime_samples,
            }
        )
    _validate_chunk_ranges(edges, chunks_by_edge)
    return result


def _validated_edge_samples(
    edge_id: str,
    edge: dict[str, Any],
) -> list[dict[str, float]]:
    samples = edge["samples"]
    if len(samples) < 2:
        raise ValueError(f"Edge '{edge_id}' requires at least two route samples.")
    length = _finite_number(edge, "length_meters", f"Edge '{edge_id}'")
    if length <= 0:
        raise ValueError(f"Edge '{edge_id}' must have a positive length.")
    normalized: list[dict[str, float]] = []
    previous_distance: float | None = None
    for index, sample in enumerate(samples):
        normalized_sample = {
            field: _finite_number(sample, field, f"Edge '{edge_id}' sample {index}")
            for field in _SAMPLE_FIELDS
        }
        distance = normalized_sample["distance_meters"]
        if previous_distance is not None and distance <= previous_distance:
            raise ValueError(f"Edge '{edge_id}' sample distances must be strictly increasing.")
        previous_distance = distance
        normalized.append(normalized_sample)
    if not math.isclose(normalized[0]["distance_meters"], 0.0, abs_tol=1e-9):
        raise ValueError(f"Edge '{edge_id}' samples must start at zero meters.")
    if not math.isclose(normalized[-1]["distance_meters"], length, abs_tol=1e-9):
        raise ValueError(f"Edge '{edge_id}' samples must end at the declared edge length.")
    return normalized


def _validate_chunk_ranges(
    edges: dict[str, dict[str, Any]],
    chunks_by_edge: dict[str, list[dict[str, Any]]],
) -> None:
    for edge_id, edge in edges.items():
        chunks = sorted(chunks_by_edge[edge_id], key=lambda chunk: chunk["start_meters"])
        if not chunks:
            raise ValueError(f"Edge '{edge_id}' has no runtime chunks.")
        expected_start = edge["samples"][0]["distance_meters"]
        for chunk in chunks:
            if not math.isclose(chunk["start_meters"], expected_start, abs_tol=1e-9):
                raise ValueError(f"Edge '{edge_id}' chunks must be contiguous and non-overlapping.")
            expected_start = chunk["end_meters"]
        if not math.isclose(
            expected_start,
            edge["samples"][-1]["distance_meters"],
            abs_tol=1e-9,
        ):
            raise ValueError(f"Edge '{edge_id}' chunks must cover its complete sample range.")


def _finite_number(values: dict[str, Any], field: str, context: str) -> float:
    try:
        value = float(values[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{context} has an invalid '{field}'.") from error
    if not math.isfinite(value):
        raise ValueError(f"{context} has a non-finite '{field}'.")
    return value


def _projected_tangent(
    samples: list[dict[str, float]],
    distance: float,
) -> tuple[float, float]:
    after_index = next(
        index
        for index, sample in enumerate(samples)
        if sample["distance_meters"] >= distance
    )
    if math.isclose(samples[after_index]["distance_meters"], distance, abs_tol=1e-9):
        before_index = max(0, after_index - 1)
        following_index = min(len(samples) - 1, after_index + 1)
    else:
        before_index = after_index - 1
        following_index = after_index
    delta_x = (
        samples[following_index]["projected_x_meters"]
        - samples[before_index]["projected_x_meters"]
    )
    delta_y = (
        samples[following_index]["projected_y_meters"]
        - samples[before_index]["projected_y_meters"]
    )
    magnitude = math.hypot(delta_x, delta_y)
    if magnitude <= 1e-9:
        raise ValueError(f"Route samples have no projected tangent at {distance} meters.")
    return delta_x / magnitude, delta_y / magnitude


def _interpolate_sample(samples: list[dict[str, Any]], distance: float) -> dict[str, Any]:
    if distance <= samples[0]["distance_meters"]:
        return dict(samples[0])
    if distance >= samples[-1]["distance_meters"]:
        return dict(samples[-1])
    for before, after in zip(samples, samples[1:], strict=False):
        if before["distance_meters"] <= distance <= after["distance_meters"]:
            span = after["distance_meters"] - before["distance_meters"]
            factor = 0.0 if span == 0 else (distance - before["distance_meters"]) / span
            return {
                key: distance
                if key == "distance_meters"
                else before[key] + (after[key] - before[key]) * factor
                for key in before
            }
    raise ValueError(f"Cannot interpolate route sample at {distance} meters.")


def _chunk_bytes(chunk: dict[str, Any], content_version: str) -> bytes:
    payload = RouteChunkBufferT(
        schemaVersion=1,
        contentVersion=content_version,
        id=chunk["chunk_id"],
        edgeId=chunk["edge_id"],
        startMeters=chunk["start_meters"],
        endMeters=chunk["end_meters"],
        samples=[ChunkRouteSampleT(**_camel_sample(sample)) for sample in chunk["samples"]],
    )
    builder = flatbuffers.Builder(64 * 1024)
    root = payload.Pack(builder)
    builder.Finish(root, file_identifier=b"CBCK")
    return bytes(builder.Output())


def _camel_sample(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "distanceMeters": sample["distance_meters"],
        "lateralMeters": sample["lateral_meters"],
        "elevationMeters": sample["elevation_meters"],
        "curvature": sample["curvature"],
        "grade": sample["grade"],
        "projectedXMeters": sample["projected_x_meters"],
        "projectedYMeters": sample["projected_y_meters"],
        "projectedTangentX": sample["projected_tangent_x"],
        "projectedTangentY": sample["projected_tangent_y"],
    }
