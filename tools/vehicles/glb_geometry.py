"""Inspect actual GLB accessor bytes without Blender or an importer.

This complements evaluated Blender topology checks: an n-gon can have positive
area while its exported triangulation contains collapsed triangles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


COMPONENTS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path: Path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", raw)
    if magic != b"glTF" or version != 2 or length != len(raw):
        raise ValueError("Invalid GLB header or declared length")
    chunks = {}
    offset = 12
    while offset < length:
        size, kind = struct.unpack_from("<I4s", raw, offset)
        offset += 8
        if offset + size > length or kind in chunks:
            raise ValueError("Invalid or repeated GLB chunk")
        chunks[kind] = raw[offset:offset + size]
        offset += size
    document = json.loads(chunks[b"JSON"])
    if any(buffer.get("uri") for buffer in document.get("buffers", [])):
        raise ValueError("External GLB buffers are not portable")
    return document, chunks.get(b"BIN\x00", b"")


def accessor(document, binary, index):
    entry = document["accessors"][index]
    if "sparse" in entry:
        raise ValueError("Sparse accessors are outside the pinned vehicle export profile")
    view = document["bufferViews"][entry["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise ValueError("Unexpected extra GLB buffer")
    codec = struct.Struct("<" + COMPONENTS[entry["componentType"]] * WIDTHS[entry["type"]])
    stride = view.get("byteStride", codec.size)
    start = view.get("byteOffset", 0) + entry.get("byteOffset", 0)
    end = start + max(0, entry["count"] - 1) * stride + codec.size
    view_end = view.get("byteOffset", 0) + view["byteLength"]
    if end > min(view_end, len(binary)) or stride < codec.size:
        raise ValueError("Accessor exceeds its buffer view")
    return [codec.unpack_from(binary, start + i * stride) for i in range(entry["count"])]


def triangle_area(a, b, c):
    u = tuple(y - x for x, y in zip(a, b))
    v = tuple(y - x for x, y in zip(a, c))
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return math.sqrt(sum(x * x for x in cross)) * 0.5


def inspect(path: Path, area_threshold=1e-12):
    document, binary = read_glb(path)
    defects = []
    triangles = 0
    minimum = math.inf
    for mesh in document.get("meshes", []):
        for pi, primitive in enumerate(mesh.get("primitives", [])):
            if primitive.get("mode", 4) != 4:
                raise ValueError("Vehicle export contains a non-triangle primitive")
            attributes = primitive["attributes"]
            positions = accessor(document, binary, attributes["POSITION"])
            for semantic, index in attributes.items():
                values = accessor(document, binary, index)
                if any(not math.isfinite(v) for item in values for v in item):
                    defects.append({"mesh": mesh.get("name"), "primitive": pi, "error": "nonfinite " + semantic})
                if semantic == "NORMAL" and any(abs(sum(v * v for v in item) - 1) > 0.002 for item in values):
                    defects.append({"mesh": mesh.get("name"), "primitive": pi, "error": "nonunit normal"})
            indices = [v[0] for v in accessor(document, binary, primitive["indices"])] if "indices" in primitive else list(range(len(positions)))
            if len(indices) % 3:
                raise ValueError("Incomplete indexed triangle")
            for ti in range(0, len(indices), 3):
                if any(i >= len(positions) for i in indices[ti:ti + 3]):
                    raise ValueError("GLB index exceeds position accessor")
                area = triangle_area(*(positions[i] for i in indices[ti:ti + 3]))
                triangles += 1
                minimum = min(minimum, area)
                if area <= area_threshold:
                    defects.append({"mesh": mesh.get("name"), "primitive": pi, "triangle": ti // 3, "area_m2": area, "error": "degenerate triangle"})
    return {
        "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": "failed" if defects else "passed", "triangles": triangles,
        "area_threshold_m2": area_threshold, "minimum_triangle_area_m2": minimum,
        "defects": defects,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("glb", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.glb)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", newline="\n")
    print(json.dumps({"status": result["status"], "triangles": result["triangles"], "defects": len(result["defects"])}))
    raise SystemExit(0 if result["status"] == "passed" else 1)
