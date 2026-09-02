"""Create the project-original procedural Hero GT Blender source.

Second generation of the Hero GT: a lofted, Catmull-Clark subdivided grand
tourer body with booleaned wheel arches, a split greenhouse, spoked wheels with
brakes, LED light bars, mirrors and a cockpit, replacing the stacked-box
baseline of 2026-07-18. The semantic contract is unchanged: the same 37 nodes,
2.84 m wheelbase, 1.64 m track, 0.34 m wheel radius, 0.62 m suspension rest
length, three LODs, box collision proxy, no textures, at most ten materials.

Blender axes: X right, Z up. The model is authored nose-at--Y, Blender's own
front convention, and mirrored across Y as the last step so the nose sits at
+Y: the glTF exporter maps Blender +Y to Godot -Z, which is the direction
CannonballVehicle drives and where its front axle raycasts sit. The v1 export
profile assumed -Y mapped to -Z, which put the first-generation nose at +Z,
behind the physics front axle, so its steering wheels and headlights showed at
the tail in every chase capture.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


WHEELS = {
    "FL": (-0.82, -1.42, 0.42),
    "FR": (0.82, -1.42, 0.42),
    "RL": (-0.82, 1.42, 0.42),
    "RR": (0.82, 1.42, 0.42),
}

# Body cross-sections from nose to tail. Each is the right half of a closed
# loop, from the underside edge up to the centreline, as (x, z) pairs. Every
# section has the same point count so the loft is a clean quad grid.
SECTIONS = [
    (-2.24, [(0.56, 0.30), (0.82, 0.33), (0.89, 0.44), (0.88, 0.57), (0.76, 0.66), (0.44, 0.70), (0.0, 0.71)]),
    (-2.02, [(0.64, 0.27), (0.91, 0.31), (0.95, 0.48), (0.935, 0.66), (0.83, 0.77), (0.48, 0.81), (0.0, 0.825)]),
    (-1.60, [(0.67, 0.25), (0.935, 0.30), (0.955, 0.53), (0.945, 0.74), (0.86, 0.855), (0.52, 0.905), (0.0, 0.92)]),
    (-1.05, [(0.68, 0.25), (0.94, 0.30), (0.955, 0.56), (0.945, 0.80), (0.875, 0.925), (0.56, 0.975), (0.0, 0.99)]),
    (-0.58, [(0.68, 0.25), (0.94, 0.30), (0.955, 0.57), (0.945, 0.84), (0.885, 0.975), (0.62, 1.04), (0.0, 1.065)]),
    (-0.18, [(0.68, 0.25), (0.94, 0.30), (0.95, 0.57), (0.94, 0.87), (0.88, 1.005), (0.66, 1.31), (0.0, 1.455)]),
    (0.32, [(0.68, 0.25), (0.94, 0.30), (0.95, 0.57), (0.94, 0.87), (0.88, 1.01), (0.70, 1.37), (0.0, 1.53)]),
    (0.82, [(0.68, 0.25), (0.94, 0.30), (0.95, 0.57), (0.94, 0.87), (0.88, 1.005), (0.66, 1.31), (0.0, 1.445)]),
    (1.32, [(0.68, 0.25), (0.94, 0.30), (0.95, 0.565), (0.94, 0.85), (0.88, 0.985), (0.62, 1.06), (0.0, 1.10)]),
    (1.84, [(0.64, 0.27), (0.92, 0.325), (0.94, 0.555), (0.92, 0.79), (0.82, 0.905), (0.50, 0.96), (0.0, 0.98)]),
    (2.24, [(0.54, 0.33), (0.82, 0.37), (0.87, 0.51), (0.85, 0.67), (0.69, 0.78), (0.41, 0.825), (0.0, 0.835)]),
]
# Loop strips are indexed by the profile edge they sit on: right side 0..5
# (underside to roof edge), left side 7..12 mirrored (7 is the upper roof edge).
GLASS_STRIPS = {4, 8}  # side windows
UPPER_STRIPS = {5, 7}  # roof edge strips on either side of the centreline
ROOF_SECTIONS = {5, 6}  # section pairs (5->6, 6->7) whose upper strips are roof
WINDSHIELD_SECTION = 4  # section pair 4->5
REAR_GLASS_SECTION = 7  # section pair 7->8
CABIN_SECTIONS = {5, 6}  # section pairs with side glass


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


# ----------------------------------------------------------------- materials


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.45,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 4.0,
    coat: float = 0.0,
    coat_roughness: float = 0.05,
    alpha: float = 1.0,
    specular: float = 0.5,
) -> bpy.types.Material:
    value = bpy.data.materials.new(name)
    value.diffuse_color = color
    value.use_backface_culling = True
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Specular IOR Level"].default_value = specular
    if coat > 0:
        shader.inputs["Coat Weight"].default_value = coat
        shader.inputs["Coat Roughness"].default_value = coat_roughness
    if emission is not None:
        shader.inputs["Emission Color"].default_value = emission
        shader.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        shader.inputs["Alpha"].default_value = alpha
        value.surface_render_method = "BLENDED"
        value.use_backface_culling = True
    return value


# ----------------------------------------------------------------- helpers


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


def mesh_from_bmesh(name: str, bm: bmesh.types.BMesh, collection, parent, surfaces: list[bpy.types.Material]):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    for surface in surfaces:
        mesh.materials.append(surface)
    value = bpy.data.objects.new(name, mesh)
    collection.objects.link(value)
    value.parent = parent
    value["semantic_role"] = name
    return value


def smooth(obj: bpy.types.Object, angle_degrees: float = 40.0) -> None:
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    with bpy.context.temp_override(object=obj, selected_editable_objects=[obj], active_object=obj):
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_degrees))


def apply_modifiers(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_apply(modifier=modifier.name)


def rotation_matrix(rotation: tuple[float, float, float]) -> Matrix:
    return Matrix.Rotation(rotation[0], 3, "X") @ Matrix.Rotation(rotation[1], 3, "Y") @ Matrix.Rotation(rotation[2], 3, "Z")


def box(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    collection,
    parent,
    surface,
    bevel: float = 0.02,
    rotation: tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(bevel, min(size) * 0.45), segments=2, affect="EDGES")
    if rotation != (0, 0, 0):
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=rotation_matrix(rotation), verts=bm.verts)
    value = mesh_from_bmesh(name, bm, collection, parent, [surface])
    value.location = location
    smooth(value, 35)
    return value


def cylinder(
    name: str,
    radius: float,
    depth: float,
    collection,
    parent,
    surface,
    *,
    vertices: int = 32,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    axis: str = "X",
    bevel: float = 0.0,
) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=vertices, radius1=radius, radius2=radius, depth=depth)
    if axis == "X":
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=bm.verts)
    elif axis == "Y":
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "X"), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES")
    value = mesh_from_bmesh(name, bm, collection, parent, [surface])
    value.location = location
    smooth(value, 40)
    return value


def torus(name, major, minor, collection, parent, surface, location, rotation=(0, 0, 0), segments=32, rings=12):
    bm = bmesh.new()
    verts = []
    for i in range(segments):
        a = i / segments * math.tau
        centre = Vector((math.cos(a) * major, math.sin(a) * major, 0.0))
        ring = []
        for j in range(rings):
            b = j / rings * math.tau
            radial = Vector((math.cos(a), math.sin(a), 0.0)) * (minor * math.cos(b))
            ring.append(bm.verts.new(centre + radial + Vector((0, 0, minor * math.sin(b)))))
        verts.append(ring)
    for i in range(segments):
        for j in range(rings):
            bm.faces.new((verts[i][j], verts[(i + 1) % segments][j], verts[(i + 1) % segments][(j + 1) % rings], verts[i][(j + 1) % rings]))
    if rotation != (0, 0, 0):
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=rotation_matrix(rotation), verts=bm.verts)
    value = mesh_from_bmesh(name, bm, collection, parent, [surface])
    value.location = location
    smooth(value, 60)
    return value


# ----------------------------------------------------------------- body loft


def section_loop(points: list[tuple[float, float]]) -> list[Vector]:
    right = [Vector((x, 0.0, z)) for x, z in points]
    left = [Vector((-x, 0.0, z)) for x, z in reversed(points[:-1])]
    return right + left


def build_body_loft(subdivisions: int, materials: dict[str, bpy.types.Material], split: bool):
    """Returns a dict of part name -> object (body, glass, roof) or a single hull."""
    bm = bmesh.new()
    loops = []
    for y, points in SECTIONS:
        loop = []
        for point in section_loop(points):
            loop.append(bm.verts.new(Vector((point.x, y, point.z))))
        loops.append(loop)
    loop_size = len(loops[0])
    # material index tags per face: 0 body, 1 glass, 2 roof
    for s in range(len(loops) - 1):
        for k in range(loop_size):
            a = loops[s][k]
            b = loops[s][(k + 1) % loop_size]
            c = loops[s + 1][(k + 1) % loop_size]
            d = loops[s + 1][k]
            face = bm.faces.new((a, b, c, d))
            face.smooth = True
            tag = 0
            if s in CABIN_SECTIONS and k in GLASS_STRIPS:
                tag = 1
            if s in (WINDSHIELD_SECTION, REAR_GLASS_SECTION) and k in (GLASS_STRIPS | UPPER_STRIPS):
                tag = 1
            if s in ROOF_SECTIONS and k in UPPER_STRIPS:
                tag = 2
            face.material_index = tag
    front = bm.faces.new(list(reversed(loops[0])))
    rear = bm.faces.new(loops[-1])
    front.smooth = rear.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("HeroGtHullMesh")
    bm.to_mesh(mesh)
    bm.free()
    hull = bpy.data.objects.new("HeroGtHull", mesh)
    bpy.context.scene.collection.objects.link(hull)
    for key in ("body", "glass", "roof"):
        mesh.materials.append(materials[key])
    if subdivisions > 0:
        modifier = hull.modifiers.new("Subdivision", "SUBSURF")
        modifier.levels = subdivisions
        modifier.render_levels = subdivisions
        modifier.subdivision_type = "CATMULL_CLARK"
    # wheel arches cut into the dense surface
    cutters = []
    for suffix, (x, y, z) in WHEELS.items():
        cutter_bm = bmesh.new()
        bmesh.ops.create_cone(cutter_bm, cap_ends=True, cap_tris=False, segments=48, radius1=0.425, radius2=0.425, depth=0.62)
        bmesh.ops.rotate(cutter_bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=cutter_bm.verts)
        cutter_mesh = bpy.data.meshes.new(f"ArchCutter{suffix}Mesh")
        cutter_bm.to_mesh(cutter_mesh)
        cutter_bm.free()
        cutter = bpy.data.objects.new(f"ArchCutter{suffix}", cutter_mesh)
        bpy.context.scene.collection.objects.link(cutter)
        cutter.location = (x + (0.30 if x > 0 else -0.30), y, z + 0.02)
        boolean = hull.modifiers.new(f"Arch{suffix}", "BOOLEAN")
        boolean.operation = "DIFFERENCE"
        boolean.solver = "EXACT"
        boolean.object = cutter
        cutters.append(cutter)
    bpy.context.view_layer.update()
    apply_modifiers(hull)
    for cutter in cutters:
        bpy.data.objects.remove(cutter, do_unlink=True)
    for polygon in hull.data.polygons:
        polygon.use_smooth = True
    if not split:
        return {"hull": hull}
    parts = {}
    for index, key in enumerate(("body", "glass", "roof")):
        parts[key] = extract_material_faces(hull, index, materials[key])
    bpy.data.objects.remove(hull, do_unlink=True)
    return parts


def extract_material_faces(source: bpy.types.Object, material_index: int, surface: bpy.types.Material) -> bpy.types.Object:
    bm = bmesh.new()
    bm.from_mesh(source.data)
    bm.faces.ensure_lookup_table()
    doomed = [face for face in bm.faces if face.material_index != material_index]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    for face in bm.faces:
        face.material_index = 0
        face.smooth = True
    mesh = bpy.data.meshes.new(f"Part{material_index}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(surface)
    value = bpy.data.objects.new(f"Part{material_index}", mesh)
    bpy.context.scene.collection.objects.link(value)
    return value


def adopt(obj: bpy.types.Object, name: str, collection, parent, smooth_angle: float = 35.0) -> bpy.types.Object:
    obj.name = name
    obj.data.name = f"{name}Mesh"
    move_to_collection(obj, collection)
    obj.parent = parent
    obj["semantic_role"] = name
    smooth(obj, smooth_angle)
    return obj


# ----------------------------------------------------------------- wheels


def build_wheel(wheel, suffix, collection, tire, metal, brake, disc):
    side = 1 if wheel.matrix_world.translation.x > 0 else -1
    build_tire(f"LOD0_Tire_{suffix}", collection, wheel, tire)
    # Rim barrel: a ring, open in the middle so the spokes read.
    bm = bmesh.new()
    outer_a, inner_a, outer_b, inner_b = [], [], [], []
    segments = 36
    for i in range(segments):
        a = i / segments * math.tau
        c, s = math.cos(a), math.sin(a)
        outer_a.append(bm.verts.new(Vector((-0.125, c * 0.228, s * 0.228))))
        inner_a.append(bm.verts.new(Vector((-0.125, c * 0.195, s * 0.195))))
        outer_b.append(bm.verts.new(Vector((0.125, c * 0.228, s * 0.228))))
        inner_b.append(bm.verts.new(Vector((0.125, c * 0.195, s * 0.195))))
    for i in range(segments):
        j = (i + 1) % segments
        bm.faces.new((outer_a[i], outer_a[j], outer_b[j], outer_b[i]))
        bm.faces.new((inner_b[i], inner_b[j], inner_a[j], inner_a[i]))
        bm.faces.new((outer_a[j], outer_a[i], inner_a[i], inner_a[j]))
        bm.faces.new((outer_b[i], outer_b[j], inner_b[j], inner_b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    barrel = mesh_from_bmesh(f"LOD0_Rim_{suffix}", bm, collection, wheel, [metal])
    smooth(barrel, 40)
    # Spokes: five blades from the hub to the barrel on the outer face. The
    # rotation is baked into the mesh so every node keeps an identity transform.
    for index in range(5):
        angle = index / 5 * math.tau + (0.3 if side > 0 else -0.3)
        spoke = box(
            f"LOD0_Spoke_{suffix}_{index}", (0.028, 0.048, 0.17), (0, 0, 0), collection, wheel, metal,
            bevel=0.006, rotation=(angle + math.pi / 2, 0.0, 0.0),
        )
        spoke.location = (side * 0.105, math.cos(angle) * 0.115, math.sin(angle) * 0.115)
    cylinder(f"LOD0_Hub_{suffix}", 0.058, 0.05, collection, wheel, metal, vertices=24, location=(side * 0.105, 0, 0), bevel=0.008)
    cylinder(f"LOD0_Brake_{suffix}", 0.165, 0.028, collection, wheel, disc, vertices=36, location=(side * 0.03, 0, 0))
    box(f"LOD0_Caliper_{suffix}", (0.05, 0.16, 0.10), (side * 0.03, -0.06, 0.115), collection, wheel, brake,
        bevel=0.012, rotation=(math.radians(-28), 0, 0))


def build_well(name, collection, parent, surface, side, location):
    """A wheel-well liner: a cylindrical shell behind the wheel, open toward the arch."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32, radius1=0.415, radius2=0.415, depth=0.44)
    bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=bm.verts)
    bm.faces.ensure_lookup_table()
    outer = [face for face in bm.faces if face.normal.x * side > 0.9]
    bmesh.ops.delete(bm, geom=outer, context="FACES")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # Inside faces must render: flip so normals point inward toward the wheel.
    bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    value = mesh_from_bmesh(name, bm, collection, parent, [surface])
    value.location = location
    smooth(value, 40)
    return value


def build_tire(name, collection, parent, surface):
    """A tyre ring: tread band, rounded shoulders and sidewalls down to the bead."""
    bm = bmesh.new()
    profile = [
        (-0.1275, 0.205), (-0.1275, 0.300), (-0.105, 0.332), (-0.06, 0.340),
        (0.06, 0.340), (0.105, 0.332), (0.1275, 0.300), (0.1275, 0.205),
    ]
    segments = 48
    rings = []
    for x, r in profile:
        ring = []
        for i in range(segments):
            a = i / segments * math.tau
            ring.append(bm.verts.new(Vector((x, math.cos(a) * r, math.sin(a) * r))))
        rings.append(ring)
    for p in range(len(profile) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((rings[p][i], rings[p][j], rings[p + 1][j], rings[p + 1][i]))
    for i in range(segments):
        j = (i + 1) % segments
        bm.faces.new((rings[-1][i], rings[-1][j], rings[0][j], rings[0][i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    value = mesh_from_bmesh(name, bm, collection, parent, [surface])
    smooth(value, 50)
    return value


# ----------------------------------------------------------------- main


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

    # Metallic paint is a dielectric base coat with a clear coat over it; a high
    # metallic term leaves almost no diffuse blue at grazing angles.
    body = material("Material_Body", (0.040, 0.125, 0.270, 1.0), metallic=0.22, roughness=0.38, coat=1.0, coat_roughness=0.05)
    carbon = material("Material_Carbon", (0.012, 0.014, 0.018, 1.0), metallic=0.25, roughness=0.32, coat=0.6, coat_roughness=0.08)
    glass = material("Material_Glass", (0.006, 0.012, 0.022, 1.0), metallic=0.0, roughness=0.08, alpha=0.74, specular=0.35)
    tire = material("Material_Tire", (0.010, 0.010, 0.011, 1.0), roughness=0.86)
    metal = material("Material_Wheel", (0.16, 0.17, 0.19, 1.0), metallic=0.95, roughness=0.22)
    brake = material("Material_Brake", (0.55, 0.035, 0.02, 1.0), metallic=0.3, roughness=0.35)
    headlight = material("Material_Headlight", (0.85, 0.93, 1.0, 1.0), roughness=0.10, emission=(0.72, 0.86, 1.0, 1.0), emission_strength=5.0)
    taillight = material("Material_Taillight", (0.65, 0.01, 0.015, 1.0), roughness=0.15, emission=(1.0, 0.015, 0.02, 1.0), emission_strength=4.0)
    interior = material("Material_Interior", (0.030, 0.028, 0.026, 1.0), roughness=0.62)
    chrome = material("Material_Trim", (0.55, 0.56, 0.58, 1.0), metallic=1.0, roughness=0.12)
    materials = {"body": body, "glass": glass, "roof": body}

    root = empty("AssetRoot", asset, role="asset_root")
    root["asset_id"] = "hero-gt"
    chassis = empty("Chassis", asset, root, role="chassis")
    lod0 = empty("Visual_LOD0", asset, chassis, role="lod_0")
    lod1 = empty("Visual_LOD1", asset, chassis, role="lod_1")
    lod2 = empty("Visual_LOD2", asset, chassis, role="lod_2")
    lod1.hide_render = True
    lod2.hide_render = True

    # LOD0: subdivided loft split into the cockpit-exclusion parts.
    parts = build_body_loft(2, materials, split=True)
    adopt(parts["body"], "LOD0_LowerBody", asset, lod0, 42)
    adopt(parts["glass"], "LOD0_Cabin", asset, lod0, 60)
    adopt(parts["roof"], "LOD0_RoofSpine", asset, lod0, 60)

    for suffix, (x, y, z) in WHEELS.items():
        side = 1 if x > 0 else -1
        build_well(f"LOD0_Well_{suffix}", asset, lod0, carbon, side, (side * 0.62, y, z + 0.02))

    box("LOD0_FrontSplitter", (1.80, 0.36, 0.06), (0, -2.14, 0.27), asset, lod0, carbon, 0.018)
    box("LOD0_RearDiffuser", (1.72, 0.34, 0.12), (0, 2.12, 0.30), asset, lod0, carbon, 0.02)
    box("LOD0_LeftSill", (0.10, 2.40, 0.10), (-0.905, 0.10, 0.29), asset, lod0, carbon, 0.02)
    box("LOD0_RightSill", (0.10, 2.40, 0.10), (0.905, 0.10, 0.29), asset, lod0, carbon, 0.02)
    box("LOD0_Grille", (1.10, 0.06, 0.24), (0, -2.235, 0.55), asset, lod0, carbon, 0.012)
    box("LOD0_RearBlade", (1.40, 0.08, 0.05), (0, 2.215, 0.905), asset, lod0, carbon, 0.012)
    box("LOD0_Housing_FL", (0.62, 0.10, 0.16), (-0.52, -2.20, 0.745), asset, lod0, carbon, 0.02)
    box("LOD0_Housing_FR", (0.62, 0.10, 0.16), (0.52, -2.20, 0.745), asset, lod0, carbon, 0.02)
    box("LOD0_Headlight_FL", (0.54, 0.04, 0.05), (-0.52, -2.245, 0.76), asset, lod0, headlight, 0.012)
    box("LOD0_Headlight_FR", (0.54, 0.04, 0.05), (0.52, -2.245, 0.76), asset, lod0, headlight, 0.012)
    box("LOD0_Taillight_RL", (0.70, 0.04, 0.05), (-0.50, 2.235, 0.80), asset, lod0, taillight, 0.012)
    box("LOD0_Taillight_RR", (0.70, 0.04, 0.05), (0.50, 2.235, 0.80), asset, lod0, taillight, 0.012)
    box("LOD0_TailBar", (0.36, 0.03, 0.03), (0.0, 2.235, 0.80), asset, lod0, taillight, 0.008)
    for suffix, sign in (("L", -1), ("R", 1)):
        box(f"LOD0_MirrorStalk_{suffix}", (0.12, 0.04, 0.03), (sign * 1.00, -0.42, 1.02), asset, lod0, carbon, 0.008)
        box(f"LOD0_Mirror_{suffix}", (0.20, 0.11, 0.09), (sign * 1.06, -0.40, 1.04), asset, lod0, body, 0.02)
        cylinder(f"LOD0_ExhaustTip_{suffix}", 0.045, 0.14, asset, lod0, chrome, vertices=20, location=(sign * 0.52, 2.20, 0.35), axis="Y")

    build_interior(asset, lod0, interior, chrome)

    lod1_parts = build_body_loft(1, materials, split=True)
    adopt(lod1_parts["body"], "LOD1_Body", asset, lod1, 42)
    adopt(lod1_parts["glass"], "LOD1_Cabin", asset, lod1, 60)
    adopt(lod1_parts["roof"], "LOD1_Roof", asset, lod1, 60)
    build_static_wheels("LOD1_Wheels", asset, lod1, tire, 16)
    lod2_parts = build_body_loft(0, {"body": body, "glass": body, "roof": body}, split=False)
    adopt(lod2_parts["hull"], "LOD2_Silhouette", asset, lod2, 30)
    build_static_wheels("LOD2_Wheels", asset, lod2, tire, 8)

    for suffix, location in WHEELS.items():
        suspension = empty(f"Suspension_{suffix}", asset, root, (location[0], location[1], 0.66), role="suspension_anchor")
        suspension["rest_length_m"] = 0.62
        wheel = empty(f"Wheel_{suffix}", asset, suspension, (0, 0, -0.24), role="wheel_pivot")
        wheel["radius_m"] = 0.34
        bpy.context.view_layer.update()
        build_wheel(wheel, suffix, asset, tire, metal, brake, chrome)
        empty(f"Contact_{suffix}", asset, root, (location[0], location[1], 0.08), role="contact_anchor")

    collision = box("CollisionProxy", (1.86, 4.45, 0.64), (0, 0, 0.62), asset, root, carbon, 0.0)
    collision.hide_render = True
    collision["collision_kind"] = "box"

    empty("Camera_ChaseTarget", asset, root, (0, 0.75, 1.16), role="camera_target")
    empty("Camera_Cockpit", asset, root, (0, -0.15, 1.28), role="camera_anchor")
    empty("Light_Head_FL", asset, root, (-0.52, -2.26, 0.76), role="light_anchor")
    empty("Light_Head_FR", asset, root, (0.52, -2.26, 0.76), role="light_anchor")
    empty("Light_Tail_RL", asset, root, (-0.50, 2.26, 0.80), role="light_anchor")
    empty("Light_Tail_RR", asset, root, (0.50, 2.26, 0.80), role="light_anchor")
    empty("Exhaust_L", asset, root, (-0.52, 2.27, 0.35), role="exhaust_anchor")
    empty("Exhaust_R", asset, root, (0.52, 2.27, 0.35), role="exhaust_anchor")
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

    mirror_nose_to_positive_y(asset)
    build_preview(preview)
    for item in asset.objects:
        if any(abs(component - 1.0) > 1e-6 for component in item.scale):
            raise RuntimeError(f"{item.name} carries scale")
        if any(abs(component) > 1e-6 for component in item.rotation_euler):
            raise RuntimeError(f"{item.name} carries rotation")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=True)
    print(f"CANNONBALL_HERO_GT_SOURCE_OK path={args.output}")


def mirror_nose_to_positive_y(asset: bpy.types.Collection) -> None:
    """Mirrors every asset object across the XZ plane so the nose is at +Y.

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


def build_static_wheels(name: str, collection, parent, surface, segments: int) -> None:
    bm = bmesh.new()
    for x, y, z in WHEELS.values():
        wheel_bm = bmesh.new()
        bmesh.ops.create_cone(wheel_bm, cap_ends=True, cap_tris=False, segments=segments, radius1=0.34, radius2=0.34, depth=0.255)
        bmesh.ops.rotate(wheel_bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=wheel_bm.verts)
        bmesh.ops.translate(wheel_bm, vec=Vector((x, y, z)), verts=wheel_bm.verts)
        temp = bpy.data.meshes.new("TempWheel")
        wheel_bm.to_mesh(temp)
        wheel_bm.free()
        bm.from_mesh(temp)
        bpy.data.meshes.remove(temp)
    value = mesh_from_bmesh(name, bm, collection, parent, [surface])
    smooth(value, 40)


def build_interior(collection, parent, interior, chrome) -> None:
    bm = bmesh.new()

    def add_box(size, location, rotation_x=0.0):
        part = bmesh.new()
        bmesh.ops.create_cube(part, size=1.0)
        bmesh.ops.scale(part, vec=Vector(size), verts=part.verts)
        bmesh.ops.bevel(part, geom=list(part.edges), offset=min(size) * 0.25, segments=2, affect="EDGES")
        if rotation_x:
            bmesh.ops.rotate(part, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(rotation_x, 3, "X"), verts=part.verts)
        bmesh.ops.translate(part, vec=Vector(location), verts=part.verts)
        temp = bpy.data.meshes.new("TempInterior")
        part.to_mesh(temp)
        part.free()
        bm.from_mesh(temp)
        bpy.data.meshes.remove(temp)

    add_box((1.40, 2.10, 0.06), (0, 0.35, 0.60))
    add_box((1.30, 0.40, 0.16), (0, -0.60, 0.86))
    add_box((1.30, 0.18, 0.08), (0, -0.44, 0.92))
    add_box((0.28, 1.20, 0.22), (0, 0.10, 0.74))
    add_box((0.05, 1.60, 0.30), (-0.68, 0.25, 0.78))
    add_box((0.05, 1.60, 0.30), (0.68, 0.25, 0.78))
    for x in (-0.36, 0.36):
        add_box((0.52, 0.52, 0.16), (x, 0.28, 0.72))
        add_box((0.52, 0.14, 0.62), (x, 0.56, 1.02), rotation_x=math.radians(-14))
        add_box((0.28, 0.10, 0.18), (x, 0.66, 1.34), rotation_x=math.radians(-14))
    value = mesh_from_bmesh("LOD0_Interior", bm, collection, parent, [interior])
    smooth(value, 45)
    torus("LOD0_SteeringWheel", 0.17, 0.018, collection, parent, chrome, (-0.31, -0.28, 0.94), rotation=(math.radians(68), 0, 0))


def build_preview(preview) -> None:
    floor_material = material("PreviewFloorMaterial", (0.025, 0.03, 0.04, 1.0), roughness=0.86)
    box("PreviewFloor", (24, 24, 0.08), (0, 0, -0.04), preview, None, floor_material, 0)
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


if __name__ == "__main__":
    main()
