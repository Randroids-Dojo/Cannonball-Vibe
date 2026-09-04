"""Quick Eevee preview of the body surfacing for iteration (not a gate).

Run inside the pinned Blender:
  blender -b --python tools/vehicles/hero_gt/preview.py -- --output DIR [--levels 2]
Renders four views into DIR: front three-quarter, rear three-quarter, side, top.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hero_gt import body, interior, materials, parts, spec, wheels  # noqa: E402


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--levels", type=int, default=2)
    parser.add_argument("--size", type=int, default=960)
    parser.add_argument("--part", choices=("all", "body", "wheel"), default="all")
    parser.add_argument("--textured", action="store_true", help="use the sourced-texture materials and build the interior")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    return parser.parse_args(argv)


def simple_material(name, color, metallic=0.0, roughness=0.4, coat=0.0, alpha=1.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if coat:
        shader.inputs["Coat Weight"].default_value = coat
        shader.inputs["Coat Roughness"].default_value = 0.04
    if alpha < 1:
        shader.inputs["Alpha"].default_value = alpha
        material.surface_render_method = "BLENDED"
    material.use_backface_culling = True
    return material


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.size
    scene.render.resolution_y = int(args.size * 9 / 16)
    scene.render.image_settings.file_format = "PNG"
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.55, 0.62, 0.72, 1.0)
    background.inputs[1].default_value = 1.0

    textured = None
    if args.textured:
        textured = materials.build_materials(materials.Textures(args.repo_root))
        paint, dark, glass = textured["paint"], textured["dark"], textured["glass"]
        wheel_materials = {key: textured[key] for key in ("tyre", "rim", "rim_dark", "disc", "hat", "caliper")}
    else:
        paint = simple_material("Paint", (0.040, 0.125, 0.270, 1.0), metallic=0.22, roughness=0.36, coat=1.0)
        dark = simple_material("Dark", (0.01, 0.01, 0.011, 1.0), roughness=0.7)
        glass = simple_material("Glass", (0.02, 0.03, 0.04, 1.0), roughness=0.05, alpha=0.6)
        tyre_material = simple_material("Tyre", (0.012, 0.012, 0.013, 1.0), roughness=0.82)
        rim_material = simple_material("Rim", (0.62, 0.63, 0.65, 1.0), metallic=1.0, roughness=0.22)
        rim_dark = simple_material("RimDark", (0.05, 0.05, 0.055, 1.0), metallic=0.8, roughness=0.5)
        disc_material = simple_material("Disc", (0.55, 0.55, 0.56, 1.0), metallic=1.0, roughness=0.38)
        caliper_material = simple_material("Caliper", (0.60, 0.04, 0.02, 1.0), roughness=0.35, coat=0.5)
        wheel_materials = {"tyre": tyre_material, "rim": rim_material, "rim_dark": rim_dark, "disc": disc_material, "hat": rim_dark, "caliper": caliper_material}
    if args.part == "wheel":
        pivot = bpy.data.objects.new("Wheel_FR", None)
        scene.collection.objects.link(pivot)
        pivot.location = (0.0, 0.0, spec.WHEEL_RADIUS)
        anchor = bpy.data.objects.new("Suspension_FR", None)
        scene.collection.objects.link(anchor)
        wheels.build_wheel(pivot, anchor, "FR", scene.collection, 1, wheel_materials)
        for obj in scene.collection.objects:
            if obj.parent is anchor:
                obj.location = pivot.location
        total = sum(len(obj.data.polygons) for obj in scene.collection.objects if obj.type == "MESH")
        print("wheel faces", total)
        render_views(scene, args, {
            "wheel_front": ((1.6, -1.2, 0.55), (0.12, 0, 0.34)),
            "wheel_side": ((2.3, 0.0, 0.34), (0.12, 0, 0.34)),
            "wheel_back": ((-1.4, 1.2, 0.5), (-0.1, 0, 0.34)),
        })
        return
    profiles = spec.default_profiles()
    hull = body.build_cage(profiles)
    hull.obj.data.materials.append(paint)
    body.subdivide_and_cut(hull, args.levels, arches=True, well_material=dark)
    counts = body.panel_ids(hull.obj)
    print("panel face counts", {spec.PANEL_NAMES.get(k, k): v for k, v in sorted(counts.items())})
    panel_specs = {
        "Body": ({spec.PANEL_BODY, spec.PANEL_FENDER_FRONT, spec.PANEL_QUARTER, spec.PANEL_ROOF}, dict(rim=0.0)),
        "Hood": ({spec.PANEL_HOOD}, dict(gap=spec.PANEL_GAP / 2, rim=0.014)),
        "Trunk": ({spec.PANEL_TRUNK}, dict(gap=spec.PANEL_GAP / 2, rim=0.014)),
        "Door": ({spec.PANEL_DOOR}, dict(gap=spec.PANEL_GAP / 2, rim=0.0)),
        "FrontBumper": ({spec.PANEL_FRONT_BUMPER}, dict(gap=spec.BUMPER_GAP / 2, rim=0.0)),
        "RearBumper": ({spec.PANEL_REAR_BUMPER}, dict(gap=spec.BUMPER_GAP / 2, rim=0.0)),
    }
    panels = {}
    for name, (ids, options) in panel_specs.items():
        obj = body.extract_panel(hull, ids, name, [paint, dark], **options)
        if obj is None:
            print("missing panel", name)
        panels[name] = obj
    glass_obj = body.extract_panel(hull, spec.GLASS_PANELS, "Glass", [glass, dark], gap=0.004, recess=0.006, rim=0.0)
    if glass_obj is None:
        print("missing glass")
    bpy.data.objects.remove(hull.obj, do_unlink=True)
    apertures = {}
    for obj in parts.cut(panels["FrontBumper"], parts.front_cutters(profiles)):
        apertures[obj.name.replace("Aperture", "")] = obj
    for obj in parts.cut(panels["RearBumper"], parts.rear_cutters()):
        apertures[obj.name.replace("Aperture", "")] = obj
    for obj in parts.cut(panels["Body"], parts.lamp_cutters(profiles)):
        apertures[obj.name.replace("Aperture", "")] = obj
    for obj in parts.cut(panels["Door"], parts.side_cutters(profiles)):
        bpy.data.objects.remove(obj, do_unlink=True)
    for name in ("FrontBumper", "RearBumper", "Door"):
        body.add_rim(panels[name], 0.014)
    body.add_rim(panels["Body"], 0.02)
    if textured is not None:
        part_materials = {key: textured[key] for key in (
            "paint", "housing", "cavity", "grille", "carbon", "chrome", "headlamp", "led", "lens_glass", "taillamp",
            "lens_glass_red", "plate")}
        parts.build_front_parts(scene.collection, None, part_materials, apertures)
        parts.build_rear_parts(scene.collection, None, part_materials, apertures)
        parts.build_side_parts(scene.collection, None, part_materials, profiles)
        interior.build_interior(scene.collection, None, textured, profiles)
        for obj in apertures.values():
            bpy.data.objects.remove(obj, do_unlink=True)
        for obj in scene.collection.objects:
            if obj.type == "MESH" and not obj.data.uv_layers:
                materials.box_uv(obj, 1.0)
        finish_scene(scene, args, wheel_materials, dark)
        return
    chrome = simple_material("Chrome", (0.9, 0.9, 0.92, 1.0), metallic=1.0, roughness=0.06)
    carbon = simple_material("Carbon", (0.015, 0.016, 0.02, 1.0), metallic=0.2, roughness=0.3, coat=0.8)
    housing = simple_material("Housing", (0.02, 0.02, 0.022, 1.0), roughness=0.55)
    cavity = simple_material("Cavity", (0.004, 0.004, 0.005, 1.0), roughness=0.9)
    grille = simple_material("Grille", (0.03, 0.03, 0.032, 1.0), metallic=0.6, roughness=0.5)
    headlamp = simple_material("Headlamp", (0.9, 0.95, 1.0, 1.0), roughness=0.1)
    headlamp.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.8, 0.9, 1.0, 1.0)
    headlamp.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
    led = simple_material("Led", (1.0, 1.0, 1.0, 1.0), roughness=0.2)
    led.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.85, 0.92, 1.0, 1.0)
    led.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 6.0
    taillamp = simple_material("Taillamp", (0.6, 0.02, 0.02, 1.0), roughness=0.2)
    taillamp.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.02, 0.02, 1.0)
    taillamp.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 5.0
    lens_glass = simple_material("LensGlass", (0.6, 0.65, 0.7, 1.0), roughness=0.03, alpha=0.25)
    lens_glass_red = simple_material("LensGlassRed", (0.6, 0.05, 0.04, 1.0), roughness=0.05, alpha=0.45)
    plate = simple_material("Plate", (0.85, 0.85, 0.82, 1.0), roughness=0.5)
    part_materials = {
        "paint": paint, "housing": housing, "cavity": cavity, "grille": grille, "carbon": carbon, "chrome": chrome,
        "headlamp": headlamp, "led": led, "lens_glass": lens_glass, "taillamp": taillamp, "lens_glass_red": lens_glass_red,
        "plate": plate,
    }
    parts.build_front_parts(scene.collection, None, part_materials, apertures)
    parts.build_rear_parts(scene.collection, None, part_materials, apertures)
    parts.build_side_parts(scene.collection, None, part_materials, profiles)
    for obj in apertures.values():
        bpy.data.objects.remove(obj, do_unlink=True)
    finish_scene(scene, args, wheel_materials, dark)


def finish_scene(scene, args, wheel_materials, dark) -> None:
    for suffix, (x, y) in (("FL", (-spec.WHEEL_X, spec.FRONT_AXLE_Y)), ("FR", (spec.WHEEL_X, spec.FRONT_AXLE_Y)),
                           ("RL", (-spec.WHEEL_X, spec.REAR_AXLE_Y)), ("RR", (spec.WHEEL_X, spec.REAR_AXLE_Y))):
        side = 1 if x > 0 else -1
        anchor = bpy.data.objects.new(f"Suspension_{suffix}", None)
        scene.collection.objects.link(anchor)
        anchor.location = (x, y, spec.WHEEL_Z + 0.24)
        pivot = bpy.data.objects.new(f"Wheel_{suffix}", None)
        scene.collection.objects.link(pivot)
        pivot.parent = anchor
        pivot.location = (0, 0, -0.24)
        wheels.build_wheel(pivot, anchor, suffix, scene.collection, side, wheel_materials)
        for obj in scene.collection.objects:
            if obj.parent is anchor and obj.type == "MESH":
                obj.location = (0, 0, -0.24)
        wheels.build_well(f"Well_{suffix}", None, scene.collection, dark, side, (side * 0.62, y, spec.WHEEL_Z + 0.02))
    for obj in list(scene.collection.objects):
        if obj.type == "MESH":
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            with bpy.context.temp_override(object=obj, selected_editable_objects=[obj], active_object=obj):
                bpy.ops.object.shade_smooth_by_angle(angle=math.radians(32))
    total = sum(len(obj.data.polygons) for obj in scene.collection.objects if obj.type == "MESH")
    print("preview faces", total)

    floor_material = simple_material("Floor", (0.18, 0.19, 0.20, 1.0), roughness=0.9)
    bpy.ops.mesh.primitive_plane_add(size=30)
    floor = bpy.context.active_object
    floor.data.materials.append(floor_material)

    render_views(scene, args, {
        "front34": ((5.2, -6.4, 2.2), (0, -0.2, 0.62)),
        "rear34": ((-5.0, 6.2, 2.0), (0, 0.3, 0.62)),
        "side": ((8.4, 0.0, 1.15), (0, 0, 0.62)),
        "door": ((4.2, 0.3, 1.0), (0.9, 0.3, 0.7)),
        "wheel": ((2.4, -2.2, 0.7), (0.9, -1.42, 0.42)),
        "hoodcorner": ((2.2, -3.6, 1.5), (0.7, -2.1, 0.72)),
        "tail": ((-2.4, 4.6, 1.2), (0.0, 2.3, 0.6)),
        "nose": ((1.9, -4.4, 0.9), (0.0, -2.3, 0.55)),
        "cockpit": ((0.30, 0.42, 1.00), (-0.30, -0.60, 0.84)),
        "lamp": ((2.5, -3.3, 1.15), (0.9, -1.86, 0.66)),
        "cabin": ((-2.4, 0.6, 1.25), (0.1, 0.1, 0.72)),
        "top": ((0.0, -0.4, 9.5), (0, 0.0, 0.6)),
        "front": ((0.0, -8.5, 1.1), (0, 0, 0.6)),
    })


def render_views(scene, args, views) -> None:
    for name, energy, location in (("Key", 1400, (5, -6, 8)), ("Fill", 700, (-7, -2, 5)), ("Rim", 1000, (2, 7, 6))):
        if scene.collection.objects.get(name) is not None:
            continue
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = 6
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        scene.collection.objects.link(light)
        look_at(light, Vector((0, 0, 0.6)))
    camera_data = bpy.data.cameras.new("Camera")
    camera_data.lens = 50
    camera = bpy.data.objects.new("Camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    glass = scene.collection.objects.get("Glass")
    for name, (location, target) in views.items():
        camera.location = location
        look_at(camera, Vector(target))
        camera_data.lens = 30 if name == "cockpit" else 50
        if glass is not None:
            glass.hide_render = name in ("cockpit", "cabin")
        scene.render.filepath = str(args.output / f"{name}.png")
        bpy.ops.render.render(write_still=True)
    print("CANNONBALL_HERO_GT_PREVIEW_OK")


if __name__ == "__main__":
    main()
