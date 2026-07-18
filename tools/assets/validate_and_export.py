"""Lint, export, inventory, and render one Cannonball Blender asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector


REQUIRED_NODES = {
    "AssetRoot",
    "Visual_LOD0",
    "Visual_LOD1",
    "CollisionProxy",
    "Anchor_Origin",
}
EXPECTED_VERSION = (5, 1, 2)


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--contact-sheet", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def assert_identity(value: bpy.types.Object) -> None:
    epsilon = 1e-6
    if any(abs(component) > epsilon for component in value.location):
        raise ValueError(f"{value.name} has unapplied location {tuple(value.location)}")
    if any(abs(component) > epsilon for component in value.rotation_euler):
        raise ValueError(f"{value.name} has unapplied rotation {tuple(value.rotation_euler)}")
    if any(abs(component - 1.0) > epsilon for component in value.scale):
        raise ValueError(f"{value.name} has unapplied scale {tuple(value.scale)}")


def lint(profile: dict) -> dict:
    if bpy.app.version != EXPECTED_VERSION:
        raise RuntimeError(f"Blender version mismatch: expected {EXPECTED_VERSION}, got {bpy.app.version}")
    if bpy.context.scene.unit_settings.system != "METRIC" or not math.isclose(
        bpy.context.scene.unit_settings.scale_length, 1.0
    ):
        raise ValueError("Scene units must be metric at one meter per unit")
    asset = bpy.data.collections.get("Asset")
    if asset is None:
        raise ValueError("Missing Asset collection")
    names = {item.name for item in asset.objects}
    missing = REQUIRED_NODES - names
    if missing:
        raise ValueError(f"Missing semantic nodes: {sorted(missing)}")
    if bpy.data.libraries:
        raise ValueError("Linked Blender libraries are not portable asset inputs")
    external_images = [image.filepath for image in bpy.data.images if image.source == "FILE"]
    if external_images:
        raise ValueError(f"External image paths are not allowed in the fixture: {external_images}")

    triangles = {}
    materials = set()
    for item in asset.objects:
        assert_identity(item)
        if item.type != "MESH":
            continue
        evaluated = item.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        triangles[item.name] = len(mesh.loop_triangles)
        materials.update(slot.material.name for slot in item.material_slots if slot.material)
        evaluated.to_mesh_clear()
    budgets = {
        "triangles_lod0_max": 24,
        "triangles_total_max": 72,
        "materials_max": 2,
        "textures_max": 0,
        "texture_bytes_max": 0,
        "collision_triangles_max": 24,
    }
    if triangles.get("Visual_LOD0", 0) > budgets["triangles_lod0_max"]:
        raise ValueError("LOD0 triangle budget exceeded")
    if sum(triangles.values()) > budgets["triangles_total_max"]:
        raise ValueError("Total triangle budget exceeded")
    if len(materials) > budgets["materials_max"]:
        raise ValueError("Material budget exceeded")
    if triangles.get("CollisionProxy", 0) > budgets["collision_triangles_max"]:
        raise ValueError("Collision triangle budget exceeded")
    if profile["format"] != "GLB" or profile["gltf_version"] != "2.0":
        raise ValueError("Only the pinned glTF 2.0 binary profile is supported")
    return {
        "required_nodes": sorted(REQUIRED_NODES),
        "nodes": sorted(names),
        "triangles": dict(sorted(triangles.items())),
        "triangle_total": sum(triangles.values()),
        "materials": sorted(materials),
        "textures": [],
        "budgets": budgets,
        "portable_paths": True,
        "identity_transforms": True,
        "metric_scale": 1.0,
    }


def export_glb(path: Path, profile: dict) -> None:
    asset = bpy.data.collections["Asset"]
    bpy.ops.object.select_all(action="DESELECT")
    for item in asset.objects:
        item.hide_set(False)
        item.select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["AssetRoot"]
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        check_existing=False,
        export_format="GLB",
        use_selection=profile["selected_objects_only"],
        export_yup=profile["y_up"],
        export_apply=profile["apply_modifiers"],
        export_extras=profile["export_custom_properties"],
        export_animations=profile["export_animations"],
        export_cameras=profile["export_cameras"],
        export_lights=profile["export_lights"],
        export_materials=profile["export_materials"],
        export_image_format=profile["image_format"],
        export_copyright=profile["copyright"],
    )


def inspect_glb(path: Path) -> dict:
    raw = path.read_bytes()
    if raw[:4] != b"glTF" or struct.unpack_from("<I", raw, 4)[0] != 2:
        raise ValueError("Export is not a glTF 2.0 binary")
    json_length, json_kind = struct.unpack_from("<II", raw, 12)
    if json_kind != 0x4E4F534A:
        raise ValueError("GLB does not begin with a JSON chunk")
    document = json.loads(raw[20 : 20 + json_length].decode("utf-8").rstrip(" \0"))
    external_uris = [buffer["uri"] for buffer in document.get("buffers", []) if "uri" in buffer]
    external_uris += [image["uri"] for image in document.get("images", []) if "uri" in image]
    if external_uris:
        raise ValueError(f"GLB contains nonportable external URIs: {external_uris}")
    return {
        "generator": document.get("asset", {}).get("generator", ""),
        "scene_count": len(document.get("scenes", [])),
        "node_names": sorted(node.get("name", "") for node in document.get("nodes", [])),
        "mesh_count": len(document.get("meshes", [])),
        "material_count": len(document.get("materials", [])),
        "external_uri_count": len(external_uris),
    }


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def render_contact_sheet(path: Path) -> None:
    scene = bpy.context.scene
    camera = bpy.data.objects["PreviewCamera"]
    views = [(10, -14, 10), (0, -17, 5.5), (-11, -10, 8)]
    rendered = []
    path.parent.mkdir(parents=True, exist_ok=True)
    for index, location in enumerate(views):
        camera.location = location
        point_camera(camera, Vector((0, 0, 0)))
        frame = path.with_name(f"{path.stem}-{index}.png")
        scene.render.filepath = str(frame)
        bpy.ops.render.render(write_still=True)
        rendered.append(frame)
    images = [bpy.data.images.load(str(frame), check_existing=False) for frame in rendered]
    width, height = images[0].size
    sheet = bpy.data.images.new("AssetContactSheet", width=width * len(images), height=height)
    pixels = [0.0] * (width * len(images) * height * 4)
    for image_index, image in enumerate(images):
        source = list(image.pixels)
        for row in range(height):
            source_start = row * width * 4
            target_start = (row * width * len(images) + image_index * width) * 4
            pixels[target_start : target_start + width * 4] = source[
                source_start : source_start + width * 4
            ]
    sheet.pixels = pixels
    sheet.filepath_raw = str(path)
    sheet.file_format = "PNG"
    sheet.save()
    for frame in rendered:
        frame.unlink()


def main() -> None:
    args = arguments()
    profile = json.loads(args.profile.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    inventory = lint(profile)
    export_glb(args.output, profile)
    render_contact_sheet(args.contact_sheet)
    inventory.update(
        {
            "schema_version": 1,
            "asset_id": "graybox-road-module",
            "blender_version": bpy.app.version_string,
            "blender_build_hash": bpy.app.build_hash.decode("ascii"),
            "source": {"path": portable_path(args.source), "sha256": sha256(args.source)},
            "profile": {"path": portable_path(args.profile), "sha256": sha256(args.profile)},
            "glb": {"path": portable_path(args.output), "sha256": sha256(args.output), **inspect_glb(args.output)},
            "contact_sheet": {
                "path": portable_path(args.contact_sheet),
                "sha256": sha256(args.contact_sheet),
                "width": bpy.data.images["AssetContactSheet"].size[0],
                "height": bpy.data.images["AssetContactSheet"].size[1],
            },
        }
    )
    args.inventory.parent.mkdir(parents=True, exist_ok=True)
    args.inventory.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    print(
        "CANNONBALL_ASSET_EXPORT_OK "
        f"asset=graybox-road-module triangles={inventory['triangle_total']} "
        f"materials={len(inventory['materials'])} sha256={inventory['glb']['sha256']}"
    )


if __name__ == "__main__":
    main()
