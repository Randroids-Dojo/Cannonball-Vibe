"""Read a frozen .blend and retain evaluated geometry/actual driven poses only.

No render, scene save, shipping export or production module import occurs.
The JSON is QA evidence in Blender source coordinates, not a runtime asset.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector


def matrix(value):
    return [list(row) for row in value]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--opening-steps", type=int, default=10)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    assert 10 <= args.opening_steps <= 1000
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "evaluated-meshes.json.gz").exists():
        raise RuntimeError("Retain earlier evaluated geometry unchanged.")
    assert bpy.app.version == (5, 1, 2)
    assert bpy.app.build_hash.decode() == "ec6e62d40fa9"
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()), load_ui=False, use_scripts=True)
    source = Path(bpy.data.filepath)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    started = datetime.now(timezone.utc).isoformat()
    begin = time.perf_counter()
    controls = bpy.data.objects["RigControls"]
    numeric = {key: float(controls[key]) for key in controls.keys()
               if isinstance(controls[key], (float, int))}

    def pose(values):
        for key in numeric:
            controls[key] = numeric[key] if key.startswith("source_sim_") else 0.0
        for key, value in values.items():
            if key not in numeric:
                raise RuntimeError("Missing source control: " + key)
            controls[key] = value
        controls.update_tag(refresh={"OBJECT"})
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.update()
        return bpy.context.evaluated_depsgraph_get()

    graph = pose({})
    objects = [obj for obj in bpy.data.objects if obj.type in ("MESH", "FONT")
               and (obj.name.startswith(("LOD0_", "LOD1_", "LOD2_", "Collision")) or obj.get("source_preview_only") is True)]
    meshes = {}
    inventory = []
    for obj in objects:
        evaluated = obj.evaluated_get(graph)
        data = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        data.calc_loop_triangles()
        world = evaluated.matrix_world
        vertices = [list(world @ vertex.co) for vertex in data.vertices]
        indices = [list(tri.vertices) for tri in data.loop_triangles]
        ancestors = []
        parent = obj.parent
        while parent is not None:
            ancestors.append(parent.name)
            parent = parent.parent
        verts = [Vector(p) for p in vertices]
        signed_volume = sum(verts[a].dot(verts[b].cross(verts[c])) for a, b, c in indices) / 6
        areas = [((verts[b] - verts[a]).cross(verts[c] - verts[a])).length / 2 for a, b, c in indices]
        edge_counts = {}
        for polygon in data.polygons:
            for a, b in polygon.edge_keys:
                edge = tuple(sorted((a, b)))
                edge_counts[edge] = edge_counts.get(edge, 0) + 1
        triangle_keys = Counter(tuple(sorted(triangle)) for triangle in indices)
        triangle_edges = Counter(tuple(sorted((triangle[i], triangle[(i + 1) % 3])))
                                 for triangle in indices for i in range(3))
        row = {"name": obj.name, "ancestors": ancestors, "rest_world_matrix": matrix(world),
               "vertices": vertices, "triangles": indices,
               "properties": {key: obj[key] for key in obj.keys() if isinstance(obj[key], (str, float, int, bool))},
               "material_names": [slot.material.name if slot.material else None for slot in obj.material_slots]}
        if obj.name.startswith("LOD0_") or obj.get("source_preview_only") is True:
            meshes[obj.name] = row
        inventory.append({"name": obj.name, "source_preview_only": obj.get("source_preview_only") is True,
                          "vertices": len(vertices), "triangles": len(indices), "material_names": row["material_names"],
                          "signed_volume_m3": signed_volume, "absolute_volume_l": abs(signed_volume) * 1000,
                          "minimum_triangle_area_m2": min(areas, default=None),
                          "degenerate_loop_triangles": sum(area <= 1e-12 for area in areas),
                          "nonmanifold_edges": sum(count != 2 for count in edge_counts.values()),
                          "duplicate_loop_triangles": sum(count - 1 for count in triangle_keys.values()),
                          "triangulated_nonmanifold_edges": sum(count != 2 for count in triangle_edges.values()),
                          "bounds_source_m": [[min((p[i] for p in vertices), default=None) for i in range(3)],
                                              [max((p[i] for p in vertices), default=None) for i in range(3)]]})
        evaluated.to_mesh_clear()
    print("QA_EVALUATED_GEOMETRY " + str(len(meshes)), flush=True)
    semantics = [obj for obj in bpy.data.objects if obj.type == "EMPTY" and obj.name != "RigControls"]
    poses = []
    requests = [("rest", {})]
    openings = [key for key in numeric if key.endswith("_open")]
    requests.append(("openings_rest", {key: 0 for key in openings}))
    for key in openings:
        for i in range(1, args.opening_steps + 1):
            requests.append((key + "_" + str(i), {key: i / args.opening_steps}))
    requests.append(("all_open", {key: 1 for key in openings}))
    for value in (-1, -.5, -.02, .02, .5, 1):
        requests.append(("steering_" + str(value), {"steering": value}))
    for suspension in (-.075, .085):
        for steering in (-1, 0, 1):
            requests.append((f"suspension_{suspension}_steer_{steering}", {"suspension": suspension, "steering": steering}))
    for key in ("accelerator", "brake", "wiper_sweep"):
        for i in range(1, 11):
            requests.append((key + "_" + str(i), {key: i / 10}))
    for label, values in requests:
        graph = pose(values)
        pivots = {obj.name: matrix(obj.evaluated_get(graph).matrix_world) for obj in semantics}
        poses.append({"name": label, "controls": values, "semantic_world_matrices": pivots})
    graph = pose({})
    spec = json.loads(bpy.context.scene["specification"])
    payload = {"task_id": "P1-018", "start_utc": started,
               "end_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.perf_counter() - begin,
               "source_path": str(source), "source_sha256": before, "blender_version": bpy.app.version_string,
               "blender_build": bpy.app.build_hash.decode(), "scene_stage": bpy.context.scene.get("production_stage"),
               "surface_preview_only": bpy.context.scene.get("surface_preview_only"),
               "opening_sample_steps": args.opening_steps,
               "source_controls_before_probe": numeric, "embedded_specification": spec,
               "meshes": meshes, "poses": poses,
               "scope": "Actual evaluated LOD0 mesh and native driver pose extraction. Poses are samples and do not themselves certify continuous clearance.",
               "human_approval_reference": None}
    encoded = json.dumps(payload, separators=(",", ":")).encode()
    with (out / "evaluated-meshes.json.gz").open("wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0) as compressed:
            compressed.write(encoded)
    summary = {key: value for key, value in payload.items() if key not in ("meshes", "poses", "embedded_specification")}
    shipping = [row for row in inventory if not row["source_preview_only"]]
    lod_triangles = {str(lod): sum(row["triangles"] for row in shipping if row["name"].startswith(f"LOD{lod}_")) for lod in range(3)}
    summary.update({"mesh_inventory": inventory, "pose_count": len(poses), "triangle_count": sum(r["triangles"] for r in inventory),
                    "shipping_triangle_count": lod_triangles["0"],
                    "shipping_triangle_total": sum(r["triangles"] for r in shipping),
                    "shipping_lod_triangles": lod_triangles,
                    "shipping_collision_triangles": sum(row["triangles"] for row in shipping if row["name"].startswith("Collision")),
                    "shipping_materials": sorted({name for row in shipping for name in row["material_names"] if name}),
                    "shipping_degenerate_loop_triangles": sum(r["degenerate_loop_triangles"] for r in shipping),
                    "shipping_nonmanifold_edges": sum(r["nonmanifold_edges"] for r in shipping),
                    "shipping_duplicate_loop_triangles": sum(r["duplicate_loop_triangles"] for r in shipping),
                    "shipping_triangulated_nonmanifold_edges": sum(r["triangulated_nonmanifold_edges"] for r in shipping),
                    "excluded_from_shipping_by_exact_flag": [row for row in inventory if row["source_preview_only"]],
                    "degenerate_loop_triangles": sum(r["degenerate_loop_triangles"] for r in inventory),
                    "nonmanifold_edges": sum(r["nonmanifold_edges"] for r in inventory),
                    "geometry_payload_sha256": hashlib.sha256((out / "evaluated-meshes.json.gz").read_bytes()).hexdigest(),
                    "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    (out / "evaluated-inventory.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before, "Frozen source changed during probe."
    print("QA_SOURCE_READ_ONLY_OK " + json.dumps({"meshes": len(meshes), "poses": len(poses), "source_sha256": before}), flush=True)


if __name__ == "__main__":
    main()
