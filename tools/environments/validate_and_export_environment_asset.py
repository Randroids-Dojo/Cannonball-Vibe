"""Lint, export, inventory, and render one contract-driven environment asset.

This generalises tools/assets/validate_and_export.py: the semantic node list,
budgets, expected bounds and contact-sheet views come from a JSON contract
next to the asset instead of being hard-coded, so every environment asset
(trees, rocks, roadside props) runs through the same gate.

  "$BLENDER_BIN" --background SOURCE.blend --python-exit-code 1 \
      --python tools/environments/validate_and_export_environment_asset.py -- \
      --source SOURCE.blend --contract CONTRACT.json --profile PROFILE.json \
      --output OUT.glb --inventory OUT.json --contact-sheet OUT.png
"""

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


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
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


def lod_triangles(asset: bpy.types.Collection, lod_name: str, triangles: dict) -> int:
    lod = bpy.data.objects.get(lod_name)
    if lod is None:
        return 0
    return sum(triangles.get(child.name, 0) for child in lod.children_recursive)


def lint(profile: dict, contract: dict) -> dict:
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
    required = set(contract["required_nodes"])
    missing = required - names
    if missing:
        raise ValueError(f"Missing semantic nodes: {sorted(missing)}")
    if bpy.data.libraries:
        raise ValueError("Linked Blender libraries are not portable asset inputs")
    external_images = [image.filepath for image in bpy.data.images if image.source == "FILE"]
    if external_images:
        raise ValueError(f"External image paths are not allowed: {external_images}")

    triangles = {}
    materials = {}
    for item in asset.objects:
        assert_identity(item)
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
    textures = {}
    for material in materials.values():
        if material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            image = node.image
            packed_bytes = len(image.packed_file.data) if image.packed_file else 0
            estimated_bytes = int(image.size[0]) * int(image.size[1]) * max(image.channels, 1)
            textures[image.name] = {"name": image.name, "source": image.source, "bytes": packed_bytes or estimated_bytes}
    texture_inventory = [textures[name] for name in sorted(textures)]
    texture_bytes_total = sum(texture["bytes"] for texture in texture_inventory)
    budgets = contract["budgets"]
    lod0 = lod_triangles(asset, "Visual_LOD0", triangles)
    if lod0 > budgets["triangles_lod0_max"]:
        raise ValueError(f"LOD0 triangle budget exceeded: {lod0} > {budgets['triangles_lod0_max']}")
    if sum(triangles.values()) > budgets["triangles_total_max"]:
        raise ValueError("Total triangle budget exceeded")
    if len(materials) > budgets["materials_max"]:
        raise ValueError("Material budget exceeded")
    if len(texture_inventory) > budgets["textures_max"]:
        raise ValueError("Texture count budget exceeded")
    if texture_bytes_total > budgets["texture_bytes_max"]:
        raise ValueError("Texture byte budget exceeded")
    if triangles.get("CollisionProxy", 0) > budgets["collision_triangles_max"]:
        raise ValueError("Collision triangle budget exceeded")
    if profile["format"] != "GLB" or profile["gltf_version"] != "2.0":
        raise ValueError("Only the pinned glTF 2.0 binary profile is supported")
    expected_axes = ("-Y", "+Z", "-Z", "+Y")
    actual_axes = (
        profile["source_forward_axis"],
        profile["source_up_axis"],
        profile["target_forward_axis"],
        profile["target_up_axis"],
    )
    if actual_axes != expected_axes:
        raise ValueError(f"Axis contract drift: expected {expected_axes}, got {actual_axes}")

    # Bounds of everything under Visual_LOD0, in metres.
    lod0_root = bpy.data.objects["Visual_LOD0"]
    minimum = Vector((math.inf,) * 3)
    maximum = Vector((-math.inf,) * 3)
    for child in lod0_root.children_recursive:
        if child.type != "MESH":
            continue
        for corner in child.bound_box:
            world = child.matrix_world @ Vector(corner)
            minimum = Vector(min(a, b) for a, b in zip(minimum, world))
            maximum = Vector(max(a, b) for a, b in zip(maximum, world))
    bounds = [round(maximum[i] - minimum[i], 3) for i in range(3)]
    expected_bounds = contract["bounds_meters"]
    tolerance = contract.get("bounds_tolerance_meters", 0.05)
    if any(abs(bounds[i] - expected_bounds[i]) > tolerance for i in range(3)):
        raise ValueError(f"LOD0 meter bounds drift: {bounds} vs {expected_bounds}")
    lod_counts = {
        name: lod_triangles(asset, name, triangles)
        for name in ("Visual_LOD0", "Visual_LOD1", "Visual_LOD2")
        if name in names
    }
    return {
        "required_nodes": sorted(required),
        "nodes": sorted(names),
        "triangles": dict(sorted(triangles.items())),
        "triangle_total": sum(triangles.values()),
        "lod_triangles": lod_counts,
        "lod0_triangle_total": lod0,
        "collision_triangle_total": triangles.get("CollisionProxy", 0),
        "materials": sorted(materials),
        "textures": texture_inventory,
        "texture_bytes_total": texture_bytes_total,
        "budgets": budgets,
        "portable_paths": True,
        "identity_transforms": True,
        "metric_scale": 1.0,
        "source_axes": {"forward": "-Y", "up": "+Z"},
        "godot_axes": {"forward": "-Z", "up": "+Y"},
        "bounds_meters": bounds,
    }


def export_glb(path: Path, profile: dict) -> None:
    asset = bpy.data.collections["Asset"]
    bpy.ops.object.select_all(action="DESELECT")
    for item in asset.objects:
        item.hide_set(False)
        item.select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["AssetRoot"]
    path.parent.mkdir(parents=True, exist_ok=True)
    options = dict(
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
    if "vertex_colors" in profile:
        options["export_vertex_color"] = profile["vertex_colors"]
        options["export_active_vertex_color_when_no_material"] = True
    bpy.ops.export_scene.gltf(**options)


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
    color_attribute_meshes = sum(
        1 for mesh in document.get("meshes", [])
        for primitive in mesh.get("primitives", [])
        if "COLOR_0" in primitive.get("attributes", {})
    )
    return {
        "generator": document.get("asset", {}).get("generator", ""),
        "scene_count": len(document.get("scenes", [])),
        "node_names": sorted(node.get("name", "") for node in document.get("nodes", [])),
        "mesh_count": len(document.get("meshes", [])),
        "material_count": len(document.get("materials", [])),
        "external_uri_count": len(external_uris),
        "color_attribute_primitive_count": color_attribute_meshes,
    }


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def render_contact_sheet(path: Path, contract: dict) -> None:
    scene = bpy.context.scene
    camera = bpy.data.objects["PreviewCamera"]
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = contract.get("contact_sheet_width", 384)
    scene.render.resolution_y = contract.get("contact_sheet_height", 512)
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_layers[0].material_override = None
    target = Vector(contract.get("contact_sheet_target", (0, 0, 0.5)))
    views = [tuple(view) for view in contract["contact_sheet_views"]]
    rendered = []
    path.parent.mkdir(parents=True, exist_ok=True)
    # hide_render does not cascade from an empty to its children, so every
    # mesh outside Visual_LOD0 is hidden explicitly for the LOD0 review views.
    lod0 = bpy.data.objects["Visual_LOD0"]
    lod0_meshes = {child.name for child in lod0.children_recursive}
    hidden = []
    for item in bpy.data.collections["Asset"].objects:
        if item.type == "MESH" and item.name not in lod0_meshes and not item.hide_render:
            item.hide_render = True
            hidden.append(item)
    for index, location in enumerate(views):
        camera.location = location
        point_camera(camera, target)
        frame = path.with_name(f"{path.stem}-{index}.png")
        scene.render.filepath = str(frame)
        bpy.ops.render.render(write_still=True)
        rendered.append(frame)
    for item in hidden:
        item.hide_render = False
    images = [bpy.data.images.load(str(frame), check_existing=False) for frame in rendered]
    width, height = images[0].size
    sheet = bpy.data.images.new("AssetContactSheet", width=width * len(images), height=height)
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
    for name in ("source", "contract", "output", "inventory", "contact_sheet", "profile"):
        setattr(args, name, getattr(args, name).resolve())
    profile = json.loads(args.profile.read_text())
    contract = json.loads(args.contract.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    inventory = lint(profile, contract)
    export_glb(args.output, profile)
    render_contact_sheet(args.contact_sheet, contract)
    inventory.update(
        {
            "schema_version": 1,
            "asset_id": contract["asset_id"],
            "blender_version": bpy.app.version_string,
            "blender_build_hash": bpy.app.build_hash.decode("ascii"),
            "source": {"path": portable_path(args.source), "sha256": sha256(args.source)},
            "contract": {"path": portable_path(args.contract), "sha256": sha256(args.contract)},
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
        f"asset={contract['asset_id']} triangles={inventory['triangle_total']} "
        f"lod0={inventory['lod0_triangle_total']} materials={len(inventory['materials'])} "
        f"sha256={inventory['glb']['sha256']}"
    )


if __name__ == "__main__":
    main()
