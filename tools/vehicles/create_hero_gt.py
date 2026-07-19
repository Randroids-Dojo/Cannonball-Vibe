"""Create the project-original procedural Hero GT Blender source."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy


WHEELS = {
    "FL": (-0.82, -1.42, 0.42),
    "FR": (0.82, -1.42, 0.42),
    "RL": (-0.82, 1.42, 0.42),
    "RR": (0.82, 1.42, 0.42),
}


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.45,
    emission: tuple[float, float, float, float] | None = None,
) -> bpy.types.Material:
    value = bpy.data.materials.new(name)
    value.diffuse_color = color
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if emission is not None:
        shader.inputs["Emission Color"].default_value = emission
        shader.inputs["Emission Strength"].default_value = 4.0
    return value


def move_to_collection(value: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for owner in list(value.users_collection):
        owner.objects.unlink(value)
    collection.objects.link(value)


def empty(
    name: str,
    collection: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    role: str | None = None,
) -> bpy.types.Object:
    value = bpy.data.objects.new(name, None)
    collection.objects.link(value)
    value.parent = parent
    value.location = location
    value.empty_display_type = "PLAIN_AXES"
    value.empty_display_size = 0.12
    value["semantic_role"] = role or name
    return value


def cube(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    surface: bpy.types.Material,
    bevel: float = 0.08,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    value = bpy.context.object
    value.name = name
    value.scale = tuple(axis / 2 for axis in size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        modifier = value.modifiers.new("EdgeSoftening", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
        bpy.context.view_layer.objects.active = value
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    move_to_collection(value, collection)
    value.parent = parent
    value.location = location
    value.data.materials.append(surface)
    value["semantic_role"] = name
    return value


def cylinder(
    name: str,
    radius: float,
    depth: float,
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    surface: bpy.types.Material,
    *,
    vertices: int = 32,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth)
    value = bpy.context.object
    value.name = name
    value.rotation_euler.y = math.pi / 2
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bevel = value.modifiers.new("SidewallRound", "BEVEL")
    bevel.width = min(radius * 0.08, 0.028)
    bevel.segments = 2
    bpy.context.view_layer.objects.active = value
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    move_to_collection(value, collection)
    value.parent = parent
    value.location = location
    value.data.materials.append(surface)
    value["semantic_role"] = name
    return value


def build_wheel(
    wheel: bpy.types.Object,
    suffix: str,
    collection: bpy.types.Collection,
    tire: bpy.types.Material,
    metal: bpy.types.Material,
    brake: bpy.types.Material,
) -> None:
    cylinder(f"LOD0_Tire_{suffix}", 0.34, 0.255, collection, wheel, tire, vertices=40)
    cylinder(f"LOD0_Rim_{suffix}", 0.225, 0.266, collection, wheel, metal, vertices=32)
    cylinder(f"LOD0_Brake_{suffix}", 0.15, 0.273, collection, wheel, brake, vertices=24)
    cylinder(f"LOD0_Hub_{suffix}", 0.055, 0.282, collection, wheel, metal, vertices=20)


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
    scene.world = bpy.data.worlds.new("HeroGtPreviewWorld")
    scene.world.color = (0.012, 0.018, 0.032)

    asset = bpy.data.collections.new("Asset")
    scene.collection.children.link(asset)
    preview = bpy.data.collections.new("Preview")
    scene.collection.children.link(preview)

    body = material("Material_Body", (0.055, 0.16, 0.28, 1.0), metallic=0.82, roughness=0.2)
    carbon = material("Material_Carbon", (0.012, 0.016, 0.022, 1.0), metallic=0.35, roughness=0.25)
    glass = material("Material_Glass", (0.025, 0.09, 0.15, 1.0), metallic=0.15, roughness=0.08)
    tire = material("Material_Tire", (0.012, 0.012, 0.014, 1.0), roughness=0.88)
    metal = material("Material_Wheel", (0.12, 0.14, 0.17, 1.0), metallic=0.92, roughness=0.2)
    brake = material("Material_Brake", (0.45, 0.035, 0.025, 1.0), metallic=0.55, roughness=0.33)
    headlight = material(
        "Material_Headlight", (0.78, 0.91, 1.0, 1.0), roughness=0.12,
        emission=(0.65, 0.85, 1.0, 1.0),
    )
    taillight = material(
        "Material_Taillight", (0.7, 0.015, 0.02, 1.0), roughness=0.18,
        emission=(1.0, 0.01, 0.015, 1.0),
    )
    interior = material("Material_Interior", (0.035, 0.03, 0.028, 1.0), roughness=0.58)

    root = empty("AssetRoot", asset, role="asset_root")
    root["asset_id"] = "hero-gt"
    chassis = empty("Chassis", asset, root, role="chassis")
    lod0 = empty("Visual_LOD0", asset, chassis, role="lod_0")
    lod1 = empty("Visual_LOD1", asset, chassis, role="lod_1")
    lod2 = empty("Visual_LOD2", asset, chassis, role="lod_2")
    lod1.hide_render = True
    lod2.hide_render = True

    # Low, long-hood grand-tourer silhouette with a pinched waist and planted tail.
    cube("LOD0_LowerBody", (1.90, 4.48, 0.44), (0, 0.03, 0.60), asset, lod0, body, 0.16)
    cube("LOD0_Hood", (1.70, 1.62, 0.24), (0, -1.22, 0.88), asset, lod0, body, 0.13)
    cube("LOD0_RearDeck", (1.74, 1.08, 0.24), (0, 1.45, 0.87), asset, lod0, body, 0.12)
    cube("LOD0_Cabin", (1.54, 1.72, 0.58), (0, 0.34, 1.13), asset, lod0, glass, 0.22)
    cube("LOD0_RoofSpine", (1.15, 1.22, 0.10), (0, 0.43, 1.45), asset, lod0, body, 0.08)
    cube("LOD0_FrontSplitter", (1.82, 0.34, 0.10), (0, -2.16, 0.30), asset, lod0, carbon, 0.035)
    cube("LOD0_RearDiffuser", (1.76, 0.30, 0.13), (0, 2.14, 0.31), asset, lod0, carbon, 0.04)
    cube("LOD0_LeftSill", (0.14, 2.58, 0.13), (-0.91, 0.12, 0.35), asset, lod0, carbon, 0.045)
    cube("LOD0_RightSill", (0.14, 2.58, 0.13), (0.91, 0.12, 0.35), asset, lod0, carbon, 0.045)
    cube("LOD0_Grille", (1.15, 0.08, 0.28), (0, -2.235, 0.54), asset, lod0, carbon, 0.025)
    cube("LOD0_RearBlade", (1.34, 0.10, 0.08), (0, 2.205, 0.78), asset, lod0, carbon, 0.025)
    cube("LOD0_Interior", (1.26, 1.30, 0.18), (0, 0.40, 0.94), asset, lod0, interior, 0.10)
    cube("LOD0_Headlight_FL", (0.54, 0.09, 0.12), (-0.56, -2.225, 0.76), asset, lod0, headlight, 0.035)
    cube("LOD0_Headlight_FR", (0.54, 0.09, 0.12), (0.56, -2.225, 0.76), asset, lod0, headlight, 0.035)
    cube("LOD0_Taillight_RL", (0.58, 0.09, 0.10), (-0.57, 2.225, 0.77), asset, lod0, taillight, 0.03)
    cube("LOD0_Taillight_RR", (0.58, 0.09, 0.10), (0.57, 2.225, 0.77), asset, lod0, taillight, 0.03)

    # Coarser silhouettes preserve scale and color at distance.
    cube("LOD1_Body", (1.90, 4.48, 0.60), (0, 0.03, 0.69), asset, lod1, body, 0.13)
    cube("LOD1_Cabin", (1.50, 1.62, 0.52), (0, 0.34, 1.15), asset, lod1, glass, 0.18)
    cube("LOD2_Silhouette", (1.88, 4.42, 0.72), (0, 0.03, 0.76), asset, lod2, body, 0.10)

    for suffix, location in WHEELS.items():
        suspension = empty(
            f"Suspension_{suffix}", asset, root,
            (location[0], location[1], 0.66), role="suspension_anchor",
        )
        suspension["rest_length_m"] = 0.62
        wheel = empty(f"Wheel_{suffix}", asset, suspension, (0, 0, -0.24), role="wheel_pivot")
        wheel["radius_m"] = 0.34
        build_wheel(wheel, suffix, asset, tire, metal, brake)
        empty(
            f"Contact_{suffix}", asset, root,
            (location[0], location[1], 0.08), role="contact_anchor",
        )

    collision = cube(
        "CollisionProxy", (1.86, 4.45, 0.64), (0, 0, 0.62), asset, root, carbon, 0.04,
    )
    collision.hide_render = True
    collision["collision_kind"] = "box"

    empty("Camera_ChaseTarget", asset, root, (0, 0.75, 1.16), role="camera_target")
    empty("Camera_Cockpit", asset, root, (0, -0.15, 1.28), role="camera_anchor")
    empty("Light_Head_FL", asset, root, (-0.56, -2.24, 0.76), role="light_anchor")
    empty("Light_Head_FR", asset, root, (0.56, -2.24, 0.76), role="light_anchor")
    empty("Light_Tail_RL", asset, root, (-0.57, 2.24, 0.77), role="light_anchor")
    empty("Light_Tail_RR", asset, root, (0.57, 2.24, 0.77), role="light_anchor")
    empty("Exhaust_L", asset, root, (-0.52, 2.24, 0.35), role="exhaust_anchor")
    empty("Exhaust_R", asset, root, (0.52, 2.24, 0.35), role="exhaust_anchor")
    empty("Driver_Reference", asset, root, (-0.31, -0.02, 1.05), role="driver_anchor")
    for name, location in {
        "Damage_Front": (0, -2.18, 0.67),
        "Damage_Rear": (0, 2.18, 0.67),
        "Damage_Left": (-0.94, 0, 0.66),
        "Damage_Right": (0.94, 0, 0.66),
        "Damage_Roof": (0, 0.35, 1.48),
    }.items():
        empty(name, asset, root, location, role="damage_zone")
    for name in (
        "MaterialGroup_Body", "MaterialGroup_Glass", "MaterialGroup_Wheels",
        "MaterialGroup_Interior", "MaterialGroup_Lights",
    ):
        empty(name, asset, root, role="material_group")

    floor_material = material("PreviewFloorMaterial", (0.025, 0.03, 0.04, 1.0), roughness=0.86)
    floor = cube("PreviewFloor", (24, 24, 0.08), (0, 0, -0.04), preview, root, floor_material, 0)
    floor.parent = None
    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    preview.objects.link(camera)
    scene.camera = camera
    camera_data.lens = 58
    for name, energy, size, location in (
        ("PreviewKey", 1250, 7.0, (6, -7, 9)),
        ("PreviewFill", 800, 8.0, (-7, -1, 6)),
        ("PreviewRim", 1050, 5.0, (3, 7, 5)),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        preview.objects.link(light)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=True)
    print(f"CANNONBALL_HERO_GT_SOURCE_OK path={args.output}")


if __name__ == "__main__":
    main()
