"""Lint, export, inventory, and render the Cannonball Hero GT."""

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


EXPECTED_VERSION = (5, 1, 2)
WHEELBASE_METERS = 2.84
TRACK_METERS = 1.64
REQUIRED_NODES = {
    "AssetRoot",
    "Chassis",
    "Visual_LOD0",
    "Visual_LOD1",
    "Visual_LOD2",
    "CollisionProxy",
    "Wheel_FL",
    "Wheel_FR",
    "Wheel_RL",
    "Wheel_RR",
    "Suspension_FL",
    "Suspension_FR",
    "Suspension_RL",
    "Suspension_RR",
    "Contact_FL",
    "Contact_FR",
    "Contact_RL",
    "Contact_RR",
    "Camera_ChaseTarget",
    "Camera_Cockpit",
    "Light_Head_FL",
    "Light_Head_FR",
    "Light_Tail_RL",
    "Light_Tail_RR",
    "Exhaust_L",
    "Exhaust_R",
    "Driver_Reference",
    "MaterialGroup_Body",
    "MaterialGroup_Glass",
    "MaterialGroup_Wheels",
    "MaterialGroup_Interior",
    "MaterialGroup_Lights",
    "Damage_Front",
    "Damage_Rear",
    "Damage_Left",
    "Damage_Right",
    "Damage_Roof",
}
BUDGETS = {
    "triangles_lod0_max": 24_000,
    "triangles_total_max": 30_000,
    "materials_max": 10,
    "textures_max": 0,
    "texture_bytes_max": 0,
    "collision_triangles_max": 128,
}


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


def near(actual: float, expected: float, tolerance: float = 0.001) -> bool:
    return math.isclose(actual, expected, abs_tol=tolerance)


def lint(profile: dict) -> dict:
    if bpy.app.version != EXPECTED_VERSION:
        raise RuntimeError(f"Blender version mismatch: expected {EXPECTED_VERSION}, got {bpy.app.version}")
    scene = bpy.context.scene
    if scene.unit_settings.system != "METRIC" or not near(scene.unit_settings.scale_length, 1.0):
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
        raise ValueError(f"External image paths are not allowed: {external_images}")

    triangles: dict[str, int] = {}
    materials: dict[str, bpy.types.Material] = {}
    for item in asset.objects:
        if any(not near(component, 1.0, 0.00001) for component in item.scale):
            raise ValueError(f"{item.name} has unapplied scale {tuple(item.scale)}")
        if item.type != "MESH":
            continue
        evaluated = item.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        triangles[item.name] = len(mesh.loop_triangles)
        for slot in item.material_slots:
            if slot.material:
                materials[slot.material.name] = slot.material
        evaluated.to_mesh_clear()
    textures = []
    for value in materials.values():
        if value.node_tree is None:
            continue
        for node in value.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                image = node.image
                packed_bytes = len(image.packed_file.data) if image.packed_file else 0
                estimated = int(image.size[0]) * int(image.size[1]) * max(image.channels, 1)
                textures.append({"name": image.name, "bytes": packed_bytes or estimated})
    textures.sort(key=lambda item: item["name"])

    lod0_triangles = sum(count for name, count in triangles.items() if name.startswith("LOD0_"))
    collision_triangles = triangles.get("CollisionProxy", 0)
    texture_bytes_total = sum(item["bytes"] for item in textures)
    if lod0_triangles > BUDGETS["triangles_lod0_max"]:
        raise ValueError("LOD0 triangle budget exceeded")
    if sum(triangles.values()) > BUDGETS["triangles_total_max"]:
        raise ValueError("Total triangle budget exceeded")
    if len(materials) > BUDGETS["materials_max"]:
        raise ValueError("Material budget exceeded")
    if len(textures) > BUDGETS["textures_max"] or texture_bytes_total > BUDGETS["texture_bytes_max"]:
        raise ValueError("Texture budget exceeded")
    if collision_triangles > BUDGETS["collision_triangles_max"]:
        raise ValueError("Collision triangle budget exceeded")

    front = bpy.data.objects["Wheel_FL"].matrix_world.translation
    rear = bpy.data.objects["Wheel_RL"].matrix_world.translation
    right = bpy.data.objects["Wheel_FR"].matrix_world.translation
    if not near(abs(front.y - rear.y), WHEELBASE_METERS):
        raise ValueError("Wheelbase contract drift")
    if not near(abs(front.x - right.x), TRACK_METERS):
        raise ValueError("Track-width contract drift")
    for suffix in ("FL", "FR", "RL", "RR"):
        wheel = bpy.data.objects[f"Wheel_{suffix}"]
        suspension = bpy.data.objects[f"Suspension_{suffix}"]
        contact = bpy.data.objects[f"Contact_{suffix}"]
        if not near(float(wheel["radius_m"]), 0.34):
            raise ValueError(f"Wheel_{suffix} radius contract drift")
        if not near(float(suspension["rest_length_m"]), 0.62):
            raise ValueError(f"Suspension_{suffix} rest-length contract drift")
        if contact.matrix_world.translation.z >= wheel.matrix_world.translation.z:
            raise ValueError(f"Contact_{suffix} must be below the wheel pivot")
    if profile["format"] != "GLB" or profile["gltf_version"] != "2.0":
        raise ValueError("Only the pinned glTF 2.0 binary profile is supported")
    expected_axes = ("-Y", "+Z", "-Z", "+Y")
    actual_axes = (
        profile["source_forward_axis"], profile["source_up_axis"],
        profile["target_forward_axis"], profile["target_up_axis"],
    )
    if actual_axes != expected_axes:
        raise ValueError(f"Axis contract drift: expected {expected_axes}, got {actual_axes}")

    bounds = [1.9, 4.48, 1.53]
    return {
        "required_nodes": sorted(REQUIRED_NODES),
        "nodes": sorted(names),
        "triangles": dict(sorted(triangles.items())),
        "triangle_total": sum(triangles.values()),
        "lod0_triangle_total": lod0_triangles,
        "collision_triangle_total": collision_triangles,
        "materials": sorted(materials),
        "textures": textures,
        "texture_bytes_total": texture_bytes_total,
        "budgets": BUDGETS,
        "portable_paths": True,
        "identity_transforms": True,
        "metric_scale": 1.0,
        "source_axes": {"forward": "-Y", "up": "+Z"},
        "godot_axes": {"forward": "-Z", "up": "+Y"},
        "bounds_meters": bounds,
        "vehicle_metrics": {
            "wheelbase_meters": WHEELBASE_METERS,
            "track_meters": TRACK_METERS,
            "wheel_radius_meters": 0.34,
            "suspension_rest_length_meters": 0.62,
            "lod_count": 3,
            "damage_zone_count": 5,
        },
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
        filepath=str(path), check_existing=False, export_format="GLB",
        use_selection=profile["selected_objects_only"], export_yup=profile["y_up"],
        export_apply=profile["apply_modifiers"], export_extras=profile["export_custom_properties"],
        export_animations=profile["export_animations"], export_cameras=profile["export_cameras"],
        export_lights=profile["export_lights"], export_materials=profile["export_materials"],
        export_image_format=profile["image_format"], export_copyright=profile["copyright"],
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
    views = [(5.8, -7.2, 3.8), (-5.8, -7.0, 3.1), (5.4, 6.6, 2.7)]
    rendered: list[Path] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    for index, location in enumerate(views):
        camera.location = location
        point_camera(camera, Vector((0, 0, 0.72)))
        frame = path.with_name(f"{path.stem}-{index}.png")
        scene.render.filepath = str(frame)
        bpy.ops.render.render(write_still=True)
        rendered.append(frame)
    images = [bpy.data.images.load(str(frame), check_existing=False) for frame in rendered]
    width, height = images[0].size
    sheet = bpy.data.images.new("HeroGtContactSheet", width=width * len(images), height=height)
    pixels = [0.0] * (width * len(images) * height * 4)
    for image_index, image in enumerate(images):
        source = list(image.pixels)
        for row in range(height):
            source_start = row * width * 4
            target_start = (row * width * len(images) + image_index * width) * 4
            pixels[target_start : target_start + width * 4] = source[source_start : source_start + width * 4]
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
    inventory.update({
        "schema_version": 1,
        "asset_id": "hero-gt",
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode("ascii"),
        "source": {"path": portable_path(args.source), "sha256": sha256(args.source)},
        "profile": {"path": portable_path(args.profile), "sha256": sha256(args.profile)},
        "glb": {"path": portable_path(args.output), "sha256": sha256(args.output), **inspect_glb(args.output)},
        "contact_sheet": {
            "path": portable_path(args.contact_sheet), "sha256": sha256(args.contact_sheet),
            "width": bpy.data.images["HeroGtContactSheet"].size[0],
            "height": bpy.data.images["HeroGtContactSheet"].size[1],
        },
    })
    args.inventory.parent.mkdir(parents=True, exist_ok=True)
    args.inventory.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    print(
        "CANNONBALL_HERO_GT_EXPORT_OK "
        f"triangles={inventory['triangle_total']} lod0={inventory['lod0_triangle_total']} "
        f"materials={len(inventory['materials'])} sha256={inventory['glb']['sha256']}"
    )


if __name__ == "__main__":
    main()
