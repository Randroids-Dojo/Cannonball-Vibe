"""Create the project-original deterministic graybox road-module Blender source."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    value = bpy.data.materials.new(name)
    value.diffuse_color = color
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.82
    return value


def box_mesh(
    name: str,
    size: tuple[float, float, float],
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    surface: bpy.types.Material | None,
) -> bpy.types.Object:
    x, y, z = (axis / 2 for axis in size)
    vertices = [
        (-x, -y, -z),
        (x, -y, -z),
        (x, y, -z),
        (-x, y, -z),
        (-x, -y, z),
        (x, -y, z),
        (x, y, z),
        (-x, y, z),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (4, 0, 3, 7),
    ]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(surface) if surface else None
    mesh.update()
    value = bpy.data.objects.new(name, mesh)
    value.parent = parent
    value["semantic_role"] = name
    collection.objects.link(value)
    return value


def main() -> None:
    args = arguments()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 384
    scene.render.resolution_y = 288
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.color = (0.018, 0.024, 0.035)

    asset = bpy.data.collections.new("Asset")
    scene.collection.children.link(asset)
    preview = bpy.data.collections.new("Preview")
    scene.collection.children.link(preview)

    root = bpy.data.objects.new("AssetRoot", None)
    root["semantic_role"] = "asset_root"
    root["asset_id"] = "graybox-road-module"
    asset.objects.link(root)
    pavement = material("Material_Pavement", (0.075, 0.085, 0.095, 1.0))
    collision = material("Material_CollisionDebug", (0.2, 0.45, 0.8, 1.0))
    lod0 = box_mesh("Visual_LOD0", (7.2, 12.0, 0.24), asset, root, pavement)
    lod0["lod_index"] = 0
    lod1 = box_mesh("Visual_LOD1", (7.2, 12.0, 0.18), asset, root, pavement)
    lod1.hide_render = True
    lod1["lod_index"] = 1
    proxy = box_mesh("CollisionProxy", (7.0, 11.8, 0.20), asset, root, collision)
    proxy.hide_render = True
    proxy["collision_kind"] = "convex"
    anchor = bpy.data.objects.new("Anchor_Origin", None)
    anchor.parent = root
    anchor["semantic_role"] = "placement_anchor"
    asset.objects.link(anchor)

    floor = box_mesh("PreviewFloor", (28.0, 28.0, 0.1), preview, root, pavement)
    floor.location.z = -0.22
    floor.parent = None
    floor["preview_only"] = True

    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    preview.objects.link(camera)
    scene.camera = camera
    camera_data.lens = 48

    key_data = bpy.data.lights.new("PreviewKey", "AREA")
    key_data.energy = 1100
    key_data.shape = "DISK"
    key_data.size = 8
    key = bpy.data.objects.new("PreviewKey", key_data)
    key.location = (6, -5, 10)
    preview.objects.link(key)

    fill_data = bpy.data.lights.new("PreviewFill", "AREA")
    fill_data.energy = 650
    fill_data.size = 10
    fill = bpy.data.objects.new("PreviewFill", fill_data)
    fill.location = (-7, 3, 7)
    preview.objects.link(fill)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=True)
    print(f"CANNONBALL_ASSET_SOURCE_OK path={args.output}")


if __name__ == "__main__":
    main()
