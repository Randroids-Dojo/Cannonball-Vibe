"""Create the project-original Hero GT Blender source (third generation).

A front-engine grand tourer built to the proportion sheet in
docs/audits/p1-008/: a spline-lofted, creased, Catmull-Clark body split into
panels with 3 mm shut lines and dark rim walls, conformal lamp and grille
apertures, 275/35 R20 tyres on ten-spoke forged rims with drilled discs and
calipers, a leather-and-suede cockpit, and sourced CC0 PBR textures. The
semantic contract is unchanged: the same 37 nodes, 2.84 m wheelbase, 1.64 m
track, 0.34 m wheel radius, 0.62 m suspension rest length, three LODs and a
box collision proxy.

Blender axes: X right, Z up. The model is authored nose-at--Y and mirrored
across Y as the last step so the nose sits at +Y, which the glTF exporter
maps to Godot -Z, the direction CannonballVehicle drives.

Run inside the pinned Blender:
  blender -b --python tools/vehicles/create_hero_gt.py -- --output data/assets/vehicles/sources/hero-gt.blend
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hero_gt import body, interior, materials, parts, spec, wheels  # noqa: E402

WHEEL_POSITIONS = {
    "FL": (-spec.WHEEL_X, spec.FRONT_AXLE_Y),
    "FR": (spec.WHEEL_X, spec.FRONT_AXLE_Y),
    "RL": (-spec.WHEEL_X, spec.REAR_AXLE_Y),
    "RR": (spec.WHEEL_X, spec.REAR_AXLE_Y),
}


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    return parser.parse_args(argv)


def move_to_collection(value: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for owner in list(value.users_collection):
        owner.objects.unlink(value)
    collection.objects.link(value)


def empty(name, collection, parent=None, location=(0.0, 0.0, 0.0), role=None) -> bpy.types.Object:
    value = bpy.data.objects.new(name, None)
    collection.objects.link(value)
    value.parent = parent
    value.location = location
    value.empty_display_type = "PLAIN_AXES"
    value.empty_display_size = 0.12
    value["semantic_role"] = role or name
    return value


def adopt(obj: bpy.types.Object, name: str, collection, parent) -> bpy.types.Object:
    obj.name = name
    obj.data.name = f"{name}Mesh"
    move_to_collection(obj, collection)
    obj.parent = parent
    obj["semantic_role"] = name
    return obj


def build_lod0(asset, lod0, mats, profiles) -> dict[str, bpy.types.Object]:
    paint, dark = mats["paint"], mats["dark"]
    hull = body.build_cage(profiles)
    hull.obj.data.materials.append(paint)
    body.subdivide_and_cut(hull, 2, arches=True, well_material=dark)
    panel_specs = {
        "LOD0_Body": ({spec.PANEL_BODY, spec.PANEL_FENDER_FRONT, spec.PANEL_QUARTER}, dict()),
        "LOD0_RoofSpine": ({spec.PANEL_ROOF}, dict()),
        "LOD0_Hood": ({spec.PANEL_HOOD}, dict(gap=spec.PANEL_GAP / 2, rim=0.014)),
        "LOD0_Trunk": ({spec.PANEL_TRUNK}, dict(gap=spec.PANEL_GAP / 2, rim=0.014)),
        "LOD0_Door": ({spec.PANEL_DOOR}, dict(gap=spec.PANEL_GAP / 2)),
        "LOD0_FrontBumper": ({spec.PANEL_FRONT_BUMPER}, dict(gap=spec.BUMPER_GAP / 2)),
        "LOD0_RearBumper": ({spec.PANEL_REAR_BUMPER}, dict(gap=spec.BUMPER_GAP / 2)),
    }
    panels = {}
    for name, (ids, options) in panel_specs.items():
        obj = body.extract_panel(hull, ids, name, [paint, dark], **options)
        if obj is None:
            raise RuntimeError(f"panel {name} has no faces")
        panels[name] = adopt(obj, name, asset, lod0)
    glass = body.extract_panel(hull, spec.GLASS_PANELS, "LOD0_Cabin", [mats["glass"], dark], gap=0.004, recess=0.006)
    if glass is None:
        raise RuntimeError("glass has no faces")
    panels["LOD0_Cabin"] = adopt(glass, "LOD0_Cabin", asset, lod0)
    bpy.data.objects.remove(hull.obj, do_unlink=True)
    apertures = {}
    for obj in parts.cut(panels["LOD0_FrontBumper"], parts.front_cutters(profiles) + parts.lamp_cutters(profiles)):
        apertures[obj.name.replace("Aperture", "")] = obj
    for obj in parts.cut(panels["LOD0_RearBumper"], parts.rear_cutters()):
        apertures[obj.name.replace("Aperture", "")] = obj
    for obj in parts.cut(panels["LOD0_Door"], parts.side_cutters(profiles)):
        bpy.data.objects.remove(obj, do_unlink=True)
    for name, rim in (("LOD0_FrontBumper", 0.014), ("LOD0_RearBumper", 0.014), ("LOD0_Door", 0.014), ("LOD0_Body", 0.02), ("LOD0_RoofSpine", 0.012)):
        body.add_rim(panels[name], rim)
    part_materials = {key: mats[key] for key in (
        "paint", "housing", "cavity", "grille", "carbon", "chrome", "headlamp", "led", "lens_glass", "taillamp",
        "lens_glass_red", "plate")}
    parts.build_front_parts(asset, lod0, part_materials, apertures)
    parts.build_rear_parts(asset, lod0, part_materials, apertures)
    parts.build_side_parts(asset, lod0, part_materials, profiles)
    for obj in apertures.values():
        bpy.data.objects.remove(obj, do_unlink=True)
    interior.build_interior(asset, lod0, mats, profiles)
    for suffix, (x, y) in WHEEL_POSITIONS.items():
        side = 1 if x > 0 else -1
        wheels.build_well(f"LOD0_Well_{suffix}", lod0, asset, mats["well"], side, (side * 0.62, y, spec.WHEEL_Z + 0.02))
    return panels


def build_lod1(asset, lod1, mats, profiles) -> None:
    hull = body.build_cage(profiles, name="HeroGtLod1Cage")
    hull.obj.data.materials.append(mats["paint"])
    body.subdivide_and_cut(hull, 1, arches=True, well_material=mats["dark"])
    body_obj = body.extract_panel(hull, set(spec.PANEL_NAMES) - spec.GLASS_PANELS, "LOD1_Body", [mats["paint"], mats["dark"]])
    glass = body.extract_panel(hull, spec.GLASS_PANELS, "LOD1_Cabin", [mats["glass"], mats["dark"]])
    bpy.data.objects.remove(hull.obj, do_unlink=True)
    adopt(body_obj, "LOD1_Body", asset, lod1)
    adopt(glass, "LOD1_Cabin", asset, lod1)
    for suffix, (x, y) in WHEEL_POSITIONS.items():
        wheels.build_static_wheel(f"LOD1_Wheel_{suffix}", lod1, asset, (x, y, spec.WHEEL_Z), mats["tyre"], mats["rim"], 24)


def build_lod2(asset, lod2, mats, profiles) -> None:
    hull = body.build_cage(profiles, name="HeroGtLod2Cage")
    hull.obj.data.materials.append(mats["paint"])
    body.subdivide_and_cut(hull, 0, arches=True, well_material=mats["dark"])
    adopt(hull.obj, "LOD2_Silhouette", asset, lod2)
    for polygon in hull.obj.data.polygons:
        polygon.use_smooth = True
    for suffix, (x, y) in WHEEL_POSITIONS.items():
        wheels.build_static_wheel(f"LOD2_Wheel_{suffix}", lod2, asset, (x, y, spec.WHEEL_Z), mats["tyre"], mats["rim"], 10)


def build_preview(preview) -> None:
    floor_material = materials.principled("PreviewFloorMaterial", (0.025, 0.03, 0.04, 1.0), roughness=0.86)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((24, 24, 0.08)), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, 0, -0.04)), verts=bm.verts)
    mesh = bpy.data.meshes.new("PreviewFloorMesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(floor_material)
    floor = bpy.data.objects.new("PreviewFloor", mesh)
    preview.objects.link(floor)
    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    preview.objects.link(camera)
    bpy.context.scene.camera = camera
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


def mirror_nose_to_positive_y(asset: bpy.types.Collection) -> None:
    """Mirror every asset object across the XZ plane so the nose is at +Y.

    Object locations are relative to their parents, so negating Y at every
    level mirrors the hierarchy consistently; mesh data is mirrored in place
    and its faces reversed so the normals still point outward. Left and right
    are preserved (X is untouched), which a 180-degree rotation would not do.
    """
    for item in asset.objects:
        item.location.y = -item.location.y
        if item.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(item.data)
        bmesh.ops.scale(bm, vec=Vector((1.0, -1.0, 1.0)), verts=bm.verts)
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.to_mesh(item.data)
        bm.free()
    bpy.context.view_layer.update()


def main() -> None:
    args = arguments()
    args.output = args.output.resolve()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("HeroGtPreviewWorld")
    scene.world.color = (0.012, 0.018, 0.032)

    asset = bpy.data.collections.new("Asset")
    scene.collection.children.link(asset)
    preview = bpy.data.collections.new("Preview")
    scene.collection.children.link(preview)

    textures = materials.Textures(args.repo_root)
    mats = materials.build_materials(textures)
    profiles = spec.default_profiles()

    root = empty("AssetRoot", asset, role="asset_root")
    root["asset_id"] = "hero-gt"
    root["generation"] = 3
    chassis = empty("Chassis", asset, root, role="chassis")
    lod0 = empty("Visual_LOD0", asset, chassis, role="lod_0")
    lod1 = empty("Visual_LOD1", asset, chassis, role="lod_1")
    lod2 = empty("Visual_LOD2", asset, chassis, role="lod_2")
    lod1.hide_render = True
    lod2.hide_render = True

    build_lod0(asset, lod0, mats, profiles)
    build_lod1(asset, lod1, mats, profiles)
    build_lod2(asset, lod2, mats, profiles)

    wheel_materials = {key: mats[key] for key in ("tyre", "tyre_side", "rim", "rim_dark", "disc", "hat", "caliper")}
    # The rig raises each anchor by the measured spring compression, so the
    # anchor's rest height must be where the physics wheel sits at zero
    # compression: the chassis mounts the rig 0.975 m below its origin (its
    # static rest height), the physics wheel origin is 0.18 m below the
    # chassis origin and the wheel hangs a further 0.54 m (the rest length)
    # when fully extended, which puts the extended wheel centre 0.255 m above
    # the design ground. At the 0.085 m static compression it returns to
    # 0.34 m, the tyre radius, and the tyre touches the road.
    for suffix, (x, y) in WHEEL_POSITIONS.items():
        side = 1 if x > 0 else -1
        suspension = empty(f"Suspension_{suffix}", asset, root, (x, y, spec.WHEEL_EXTENDED_Z + 0.24), role="suspension_anchor")
        suspension["rest_length_m"] = spec.SUSPENSION_REST
        wheel = empty(f"Wheel_{suffix}", asset, suspension, (0, 0, -0.24), role="wheel_pivot")
        wheel["radius_m"] = spec.WHEEL_RADIUS
        bpy.context.view_layer.update()
        wheels.build_wheel(wheel, suspension, suffix, asset, side, wheel_materials)
        for obj in asset.objects:
            if obj.parent is suspension and obj.type == "MESH":
                obj.location = (0, 0, -0.24)
        empty(f"Contact_{suffix}", asset, root, (x, y, spec.WHEEL_EXTENDED_Z - spec.WHEEL_RADIUS), role="contact_anchor")

    collision_bm = bmesh.new()
    bmesh.ops.create_cube(collision_bm, size=1.0)
    bmesh.ops.scale(collision_bm, vec=Vector((1.90, 4.70, 0.66)), verts=collision_bm.verts)
    collision_mesh = bpy.data.meshes.new("CollisionProxyMesh")
    collision_bm.to_mesh(collision_mesh)
    collision_bm.free()
    collision_mesh.materials.append(mats["dark"])
    collision = bpy.data.objects.new("CollisionProxy", collision_mesh)
    asset.objects.link(collision)
    collision.parent = root
    collision.location = (0, 0.03, 0.64)
    collision.hide_render = True
    collision["collision_kind"] = "box"
    collision["semantic_role"] = "CollisionProxy"

    empty("Camera_ChaseTarget", asset, root, (0, 0.75, 1.16), role="camera_target")
    # Driver eye: 0.57 m above the 0.55 m H-point, 0.18 m under the headliner.
    empty("Camera_Cockpit", asset, root, (-0.34, 0.02, 1.12), role="camera_anchor")
    y0, y1 = spec.HEADLAMP_Y
    empty("Light_Head_FL", asset, root, (-spec.HEADLAMP_X - 0.12, (y0 + y1) / 2, spec.HEADLAMP_Z), role="light_anchor")
    empty("Light_Head_FR", asset, root, (spec.HEADLAMP_X + 0.12, (y0 + y1) / 2, spec.HEADLAMP_Z), role="light_anchor")
    empty("Light_Tail_RL", asset, root, (-0.60, spec.TAIL_Y - 0.02, spec.TAIL_BAR_Z), role="light_anchor")
    empty("Light_Tail_RR", asset, root, (0.60, spec.TAIL_Y - 0.02, spec.TAIL_BAR_Z), role="light_anchor")
    empty("Exhaust_L", asset, root, (-spec.EXHAUST_X[1], spec.TAIL_Y - 0.02, spec.EXHAUST_Z), role="exhaust_anchor")
    empty("Exhaust_R", asset, root, (spec.EXHAUST_X[1], spec.TAIL_Y - 0.02, spec.EXHAUST_Z), role="exhaust_anchor")
    empty("Driver_Reference", asset, root, (-interior.SEAT_X, 0.30, interior.H_POINT_Z + 0.50), role="driver_anchor")
    for name, location in {
        "Damage_Front": (0, spec.NOSE_Y + 0.15, 0.62),
        "Damage_Rear": (0, spec.TAIL_Y - 0.15, 0.70),
        "Damage_Left": (-spec.HALF_WIDTH + 0.02, 0, 0.70),
        "Damage_Right": (spec.HALF_WIDTH - 0.02, 0, 0.70),
        "Damage_Roof": (0, spec.ROOF_PEAK_Y, spec.ROOF_HEIGHT - 0.01),
    }.items():
        empty(name, asset, root, location, role="damage_zone")
    for name in (
        "MaterialGroup_Body", "MaterialGroup_Glass", "MaterialGroup_Wheels",
        "MaterialGroup_Interior", "MaterialGroup_Lights",
    ):
        empty(name, asset, root, role="material_group")

    for obj in asset.objects:
        if obj.type == "MESH" and not obj.data.uv_layers:
            materials.box_uv(obj, 1.0)

    mirror_nose_to_positive_y(asset)
    build_preview(preview)
    # Pack every sourced texture into the .blend so the source is portable
    # and the exporter embeds the same bytes into the GLB.
    for image in bpy.data.images:
        if image.source == "FILE" and image.packed_file is None:
            image.pack()
    for item in asset.objects:
        if any(abs(component - 1.0) > 1e-6 for component in item.scale):
            raise RuntimeError(f"{item.name} carries scale")
        if any(abs(component) > 1e-6 for component in item.rotation_euler):
            raise RuntimeError(f"{item.name} carries rotation")
    lod0_faces = sum(len(o.data.polygons) for o in asset.objects if o.type == "MESH" and (o.name.startswith("LOD0_") or o.parent is not None and o.parent.name.startswith(("Wheel_", "Suspension_"))))
    total_faces = sum(len(o.data.polygons) for o in asset.objects if o.type == "MESH")
    print(f"CANNONBALL_HERO_GT_FACES lod0={lod0_faces} total={total_faces} meshes={sum(1 for o in asset.objects if o.type == 'MESH')}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=True)
    print(f"CANNONBALL_HERO_GT_SOURCE_OK path={args.output}")


if __name__ == "__main__":
    main()
