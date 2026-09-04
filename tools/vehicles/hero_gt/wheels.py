"""Hero GT wheels: 275/35 R20 tyre, ten-spoke forged rim, drilled disc, caliper.

Everything is built in the wheel's local frame: the axle is local X (the
rig rotates the ``Wheel_*`` pivot about X), +X points outboard on the right
side of the car and the caller mirrors the outboard sign for the left side.
The tyre and rim rotate with the pivot; the disc and caliper are parented
to the suspension so they stay still, as on the real car.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import spec

TYRE_WIDTH = 0.275
TYRE_RADIUS = spec.WHEEL_RADIUS  # 0.34
RIM_RADIUS = 0.254  # 20 inch
RIM_WIDTH = 0.24  # 9.5 inch
SPOKES = 5
DISC_RADIUS = 0.19  # 380 mm
DISC_THICKNESS = 0.034


def _link(name: str, bm: bmesh.types.BMesh, parent, collection, materials) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    for material in materials:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.parent = parent
    obj["semantic_role"] = name
    return obj


def _smooth(obj: bpy.types.Object, angle: float) -> None:
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    with bpy.context.temp_override(object=obj, selected_editable_objects=[obj], active_object=obj):
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))


def revolve(profile: list[tuple[float, float]], segments: int, closed: bool = True) -> tuple[bmesh.types.BMesh, list[list]]:
    """Revolve an (x, r) profile about the X axis into rings of vertices."""
    bm = bmesh.new()
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
    if closed:
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((rings[-1][i], rings[-1][j], rings[0][j], rings[0][i]))
    return bm, rings


def tyre_profile() -> list[tuple[float, float]]:
    """(x, r) from the inboard bead round the tread to the outboard bead.

    A 275/35 section: 96 mm sidewall with a modest bulge, square shoulders
    and four circumferential grooves in the tread band; the tread texture
    supplies the block pattern between them.
    """
    half = TYRE_WIDTH / 2
    bead = RIM_RADIUS + 0.002
    shoulder = TYRE_RADIUS - 0.012
    profile = [
        (-half + 0.026, bead),
        (-half + 0.004, bead + 0.022),
        (-half - 0.004, RIM_RADIUS + 0.052),
        (-half - 0.002, TYRE_RADIUS - 0.030),
        (-half + 0.010, shoulder),
        (-half + 0.026, TYRE_RADIUS - 0.003),
    ]
    tread = []
    for g in (-0.078, -0.027, 0.027, 0.078):
        tread.append((g - 0.007, TYRE_RADIUS))
        tread.append((g - 0.0045, TYRE_RADIUS - 0.0085))
        tread.append((g + 0.0045, TYRE_RADIUS - 0.0085))
        tread.append((g + 0.007, TYRE_RADIUS))
    profile.extend(tread)
    profile.extend([
        (half - 0.026, TYRE_RADIUS - 0.003),
        (half - 0.010, shoulder),
        (half + 0.002, TYRE_RADIUS - 0.030),
        (half + 0.004, RIM_RADIUS + 0.052),
        (half - 0.004, bead + 0.022),
        (half - 0.026, bead),
    ])
    return profile


def build_tyre(name: str, parent, collection, tread_material, sidewall_material, segments: int = 96) -> bpy.types.Object:
    """Tyre ring: plain rubber sidewalls, tread texture rolling around the crown.

    The tread band (the profile rings between the shoulders) takes material
    slot 0 with the tread set; the sidewalls and beads take slot 1 with the
    grained rubber. UVs on the tread run u across the width and v around the
    circumference, tiled so a block pattern authored top-to-bottom rolls in
    the driving direction; the sidewall UVs are the same wrap at a coarser
    tiling so the grain never stretches.
    """
    profile = tyre_profile()
    bm, rings = revolve(profile, segments, closed=True)
    half = TYRE_WIDTH / 2
    tread_start = -half + 0.026
    tread_end = half - 0.026
    ring_x = [x for x, _ in profile]
    ring_index = {}
    for p, ring in enumerate(rings):
        for i, vert in enumerate(ring):
            ring_index[id(vert)] = (p, i)
    uv_layer = bm.loops.layers.uv.new("UVMap")
    arc = [0.0]
    for (x0, r0), (x1, r1) in zip(profile, profile[1:]):
        arc.append(arc[-1] + math.hypot(x1 - x0, r1 - r0))
    total = arc[-1]
    tread_repeats = 22.0
    side_repeats = 12.0
    for face in bm.faces:
        rows = [ring_index[id(loop.vert)][0] for loop in face.loops]
        columns = [ring_index[id(loop.vert)][1] for loop in face.loops]
        low, high = min(rows), max(rows)
        on_tread = ring_x[low] >= tread_start - 1e-6 and ring_x[high] <= tread_end + 1e-6 and high - low == 1
        face.material_index = 0 if on_tread else 1
        wraps = 0 in columns and segments - 1 in columns
        repeats = tread_repeats if on_tread else side_repeats
        for loop in face.loops:
            p, i = ring_index[id(loop.vert)]
            column = i
            if wraps and i == 0:
                column = segments
            v = column / segments * repeats
            if on_tread:
                u = (ring_x[p] - tread_start) / (tread_end - tread_start)
            else:
                u = arc[p] / total * 3.0
            loop[uv_layer].uv = (u, v)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _link(name, bm, parent, collection, [tread_material, sidewall_material])
    _smooth(obj, 50)
    return obj


def build_rim(name: str, parent, collection, side: int, face_material, barrel_material) -> list[bpy.types.Object]:
    """Barrel with a flush outer lip, five twin spokes and a hub with lug recesses."""
    objects = []
    lip = RIM_RADIUS
    inner = RIM_RADIUS - 0.020
    half = RIM_WIDTH / 2
    outboard = side * (half + 0.012)  # lip sits nearly flush with the sidewall
    inboard = -side * half
    x_lip = outboard - side * 0.020  # spoke plane at the lip
    x_hub = outboard - side * 0.058  # spoke plane at the hub (concave dish)
    profile = [
        (inboard, inner + 0.006),
        (inboard, lip),
        (inboard + side * 0.010, lip),
        (inboard + side * 0.018, inner + 0.006),
        (x_hub - side * 0.030, inner - 0.002),
        (x_lip - side * 0.012, inner),
        (outboard - side * 0.010, lip - 0.004),
        (outboard, lip),
        (outboard, lip - 0.014),
        (x_lip, lip - 0.020),
        (x_lip, inner - 0.010),
        (x_hub - side * 0.030, inner - 0.012),
        (inboard + side * 0.022, inner - 0.012),
        (inboard, inner + 0.006),
    ]
    bm, _ = revolve(profile, 72, closed=False)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    barrel = _link(f"{name}_Barrel", bm, parent, collection, [barrel_material])
    _smooth(barrel, 42)
    objects.append(barrel)
    bm = bmesh.new()
    pair_half_angle = math.radians(5.5)
    for index in range(SPOKES):
        base = index / SPOKES * math.tau + (0.30 if side > 0 else -0.30)
        for sign in (-1, 1):
            # Radial spokes in near-parallel pairs; the lip end is buried in
            # the barrel so the join never shows.
            _spoke(bm, side, base + sign * pair_half_angle, base + sign * pair_half_angle * 1.15, x_hub, x_lip, inner + 0.010)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.0022, segments=1, affect="EDGES")
    spokes = _link(f"{name}_Spokes", bm, parent, collection, [face_material])
    _smooth(spokes, 40)
    objects.append(spokes)
    hub_profile = [
        (x_hub - side * 0.030, 0.026),
        (x_hub - side * 0.030, 0.088),
        (x_hub - side * 0.004, 0.090),
        (x_hub, 0.086),
        (x_hub, 0.036),
        (x_hub + side * 0.008, 0.032),
        (x_hub + side * 0.010, 0.020),
        (x_hub + side * 0.010, 0.0),
    ]
    hub_bm, _ = revolve(hub_profile, 40, closed=False)
    bmesh.ops.recalc_face_normals(hub_bm, faces=hub_bm.faces)
    hub = _link(f"{name}_Hub", hub_bm, parent, collection, [face_material])
    _smooth(hub, 40)
    objects.append(hub)
    lug_bm = bmesh.new()
    for index in range(5):
        a = index / 5 * math.tau + 0.2
        centre = Vector((x_hub + side * 0.001, math.cos(a) * 0.058, math.sin(a) * 0.058))
        geometry = bmesh.ops.create_cone(lug_bm, cap_ends=True, cap_tris=False, segments=12, radius1=0.010, radius2=0.010, depth=0.012)
        newest = geometry["verts"]
        bmesh.ops.rotate(lug_bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=newest)
        bmesh.ops.translate(lug_bm, vec=centre, verts=newest)
    bmesh.ops.recalc_face_normals(lug_bm, faces=lug_bm.faces)
    lugs = _link(f"{name}_Lugs", lug_bm, parent, collection, [barrel_material])
    _smooth(lugs, 40)
    objects.append(lugs)
    return objects


def _spoke(bm, side, hub_angle, lip_angle, x_hub, x_lip, r_lip) -> None:
    """One tapered rectangular spoke from the hub face to the barrel, dished."""
    r_hub = 0.078
    steps = 5
    width_hub, width_lip = 0.030, 0.021
    depth_hub, depth_lip = 0.030, 0.020
    rings = []
    for s in range(steps + 1):
        t = s / steps
        ease = 1.0 - (1.0 - t) ** 2
        angle = hub_angle + (lip_angle - hub_angle) * t
        radius = r_hub + (r_lip - r_hub) * t
        x = x_hub + (x_lip - x_hub) * ease
        width = width_hub + (width_lip - width_hub) * t
        depth = depth_hub + (depth_lip - depth_hub) * t
        radial = Vector((0.0, math.cos(angle), math.sin(angle)))
        tangent = Vector((0.0, -math.sin(angle), math.cos(angle)))
        axial = Vector((side, 0.0, 0.0))
        centre = radial * radius + Vector((x, 0.0, 0.0))
        corners = [
            centre + tangent * (width / 2),
            centre + tangent * (width / 2) - axial * depth,
            centre - tangent * (width / 2) - axial * depth,
            centre - tangent * (width / 2),
        ]
        rings.append([bm.verts.new(c) for c in corners])
    for s in range(steps):
        a, b = rings[s], rings[s + 1]
        for i in range(4):
            bm.faces.new((a[i], b[i], b[(i + 1) % 4], a[(i + 1) % 4]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def build_brake(name: str, parent, collection, side: int, disc_material, hat_material, caliper_material, drilled: bool = True) -> list[bpy.types.Object]:
    """Disc with drilled face, hat, and a six-piston caliper on the leading edge."""
    objects = []
    x0 = side * 0.03
    thickness = DISC_THICKNESS
    profile = [
        (x0 - side * thickness / 2, 0.09),
        (x0 - side * thickness / 2, DISC_RADIUS),
        (x0 + side * thickness / 2, DISC_RADIUS),
        (x0 + side * thickness / 2, 0.09),
    ]
    bm, _ = revolve(profile, 72, closed=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    disc = _link(f"{name}_Disc", bm, parent, collection, [disc_material])
    _smooth(disc, 40)
    objects.append(disc)
    if drilled:
        cutter_bm = bmesh.new()
        for ring_radius, count, phase in ((0.128, 12, 0.0), (0.158, 16, 0.1), (0.182, 20, 0.05)):
            for index in range(count):
                a = index / count * math.tau + phase
                geometry = bmesh.ops.create_cone(cutter_bm, cap_ends=True, cap_tris=False, segments=10, radius1=0.006, radius2=0.006, depth=thickness + 0.02)
                verts = geometry["verts"]
                bmesh.ops.rotate(cutter_bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=verts)
                bmesh.ops.translate(cutter_bm, vec=Vector((x0, math.cos(a) * ring_radius, math.sin(a) * ring_radius)), verts=verts)
        cutter = _link(f"{name}_DiscCutter", cutter_bm, None, collection, [])
        boolean = disc.modifiers.new("Drill", "BOOLEAN")
        boolean.operation = "DIFFERENCE"
        boolean.solver = "EXACT"
        boolean.object = cutter
        bpy.context.view_layer.objects.active = disc
        with bpy.context.temp_override(object=disc, active_object=disc):
            bpy.ops.object.modifier_apply(modifier=boolean.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
        _smooth(disc, 40)
    hat_profile = [
        (x0 - side * 0.010, 0.0),
        (x0 - side * 0.010, 0.082),
        (x0 - side * 0.016, 0.088),
        (x0 - side * 0.045, 0.088),
        (x0 - side * 0.045, 0.06),
        (x0 - side * 0.035, 0.0),
    ]
    bm, _ = revolve(hat_profile, 40, closed=False)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    hat = _link(f"{name}_Hat", bm, parent, collection, [hat_material])
    _smooth(hat, 40)
    objects.append(hat)
    # Caliper: an arc block straddling the disc, leading edge (towards -Y is
    # forward in the authoring frame, so the caliper sits at the rear-top).
    bm = bmesh.new()
    a0, a1 = math.radians(28), math.radians(84)
    r_in, r_out = DISC_RADIUS - 0.070, DISC_RADIUS + 0.014
    x_in, x_out = x0 - side * 0.045, x0 + side * 0.045
    steps = 8
    rings = []
    for s in range(steps + 1):
        a = a0 + (a1 - a0) * s / steps
        c, sn = math.cos(a), math.sin(a)
        rings.append([
            bm.verts.new(Vector((x_in, c * r_in, sn * r_in))),
            bm.verts.new(Vector((x_out, c * r_in, sn * r_in))),
            bm.verts.new(Vector((x_out, c * r_out, sn * r_out))),
            bm.verts.new(Vector((x_in, c * r_out, sn * r_out))),
        ])
    for s in range(steps):
        a, b = rings[s], rings[s + 1]
        for i in range(4):
            bm.faces.new((a[i], b[i], b[(i + 1) % 4], a[(i + 1) % 4]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.006, segments=2, affect="EDGES")
    caliper = _link(f"{name}_Caliper", bm, parent, collection, [caliper_material])
    _smooth(caliper, 40)
    objects.append(caliper)
    return objects


def build_well(name: str, parent, collection, material, side: int, location) -> bpy.types.Object:
    """Wheel-well liner: an open cylindrical shell behind the arch."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=48, radius1=spec.ARCH_RADIUS + 0.01, radius2=spec.ARCH_RADIUS + 0.01, depth=0.50)
    bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=bm.verts)
    bm.faces.ensure_lookup_table()
    outer = [face for face in bm.faces if face.normal.x * side > 0.9]
    bmesh.ops.delete(bm, geom=outer, context="FACES")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    obj = _link(name, bm, parent, collection, [material])
    obj.location = location
    _smooth(obj, 40)
    return obj


def build_wheel(wheel_pivot, suspension, suffix: str, collection, side: int, materials: dict) -> None:
    """Complete wheel under its pivot and brake under the suspension anchor."""
    build_tyre(f"LOD0_Tyre_{suffix}", wheel_pivot, collection, materials["tyre"], materials["tyre_side"])
    build_rim(f"LOD0_Rim_{suffix}", wheel_pivot, collection, side, materials["rim"], materials["rim_dark"])
    brake_parent = suspension
    for obj in build_brake(f"LOD0_Brake_{suffix}", brake_parent, collection, side, materials["disc"], materials["hat"], materials["caliper"]):
        # The brake sits at the wheel centre: the pivot is 0.24 below the anchor.
        obj.location = (wheel_pivot.location.x, wheel_pivot.location.y, wheel_pivot.location.z)


def build_static_wheel(name: str, parent, collection, location, tyre_material, rim_material, segments: int) -> None:
    """Simplified wheel for LOD1/LOD2: tyre ring plus a dished disc face."""
    half = TYRE_WIDTH / 2
    profile = [
        (-half + 0.02, RIM_RADIUS), (-half, RIM_RADIUS + 0.05), (-half + 0.02, TYRE_RADIUS),
        (half - 0.02, TYRE_RADIUS), (half, RIM_RADIUS + 0.05), (half - 0.02, RIM_RADIUS),
    ]
    bm, _ = revolve(profile, segments, closed=True)
    bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    tyre = _link(f"{name}_Tyre", bm, parent, collection, [tyre_material])
    _smooth(tyre, 45)
    side = 1 if location[0] > 0 else -1
    x = location[0] + side * (RIM_WIDTH / 2 - 0.03)
    disc_bm, _ = revolve([(x - side * 0.04, 0.0), (x - side * 0.04, 0.09), (x, RIM_RADIUS - 0.01)], max(segments, 12), closed=False)
    bmesh.ops.translate(disc_bm, vec=Vector((0, location[1], location[2])), verts=disc_bm.verts)
    bmesh.ops.recalc_face_normals(disc_bm, faces=disc_bm.faces)
    face = _link(f"{name}_Face", disc_bm, parent, collection, [rim_material])
    _smooth(face, 45)
