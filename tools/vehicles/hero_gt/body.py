"""Hero GT body surfacing: spline-driven cage, creases, subdivision, panels.

The body is one watertight lofted cage: for each longitudinal station a
closed loop of 26 points (14 stations on the right half mirrored to the
left) evaluated from the longitudinal splines in :mod:`spec`. Faces carry a
panel id; edges along character lines carry creases. Catmull-Clark
subdivision and exact-boolean wheel arches are applied, then the mesh is
split by panel id into separate objects whose boundaries are shrunk by half
the shut-line width and given a dark rim wall, which is what makes gaps read
as gaps rather than as texture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import spec
from .curves import bump, lerp, smoothstep

LOOP_SIZE = 2 * spec.HALF_STATIONS - 2  # 26


def station_of(k: int) -> int:
    """Station index (0..13) for loop index ``k`` (0..25)."""
    return k if k < spec.HALF_STATIONS else LOOP_SIZE - k


def half_loop(y: float, p: spec.Profiles) -> list[tuple[float, float]]:
    """Right-half cross-section at ``y`` as (x, z), floor centre to roof centre."""
    floor = p.floor_z(y)
    sill = p.sill_z(y)
    shoulder = p.shoulder_z(y)
    belt = p.belt_z(y)
    top = p.top_z(y)
    bx = p.belt_x(y)
    # Arch blisters: 35 to 45 mm proud of the door skin over each wheel.
    blister = 0.040 * bump(y, spec.FRONT_AXLE_Y, 0.82) + 0.045 * bump(y, spec.REAR_AXLE_Y, 0.90)
    wide = bx + blister
    # Widest at the arch station a little above wheel-centre height, then a
    # tuck-under to the sill below and a shoulder crease with a rolled belt
    # above: the classic GT section.
    lower = [
        (0.0, floor),
        (bx - 0.30, floor),
        (bx - 0.135, sill * 0.55),
        (bx - 0.10, sill),
        (bx - 0.035 + blister * 0.6, lerp(sill, shoulder, 0.42)),
        (wide, lerp(sill, shoulder, 0.68)),
        (bx - 0.008 + blister * 0.35, shoulder),
        (bx - 0.032, belt - 0.03),
        (bx - 0.058, belt),
    ]
    # Greenhouse stations and hood/deck stations, blended near the cowl and deck.
    rail_x = p.roof_x(y)
    flat_x = p.roof_flat_x(y)
    rail_z = top - 0.03
    glass_x0, glass_z0 = bx - 0.058, belt
    glass = [
        (lerp(glass_x0, rail_x + 0.02, 0.36), lerp(glass_z0, rail_z, 0.36)),
        (lerp(glass_x0, rail_x + 0.02, 0.72), lerp(glass_z0, rail_z, 0.72)),
        (rail_x, rail_z),
        (flat_x, top - 0.004),
        (0.0, top),
    ]
    hood = [
        (bx * 0.80, lerp(belt, top, 0.32)),
        (bx * 0.58, lerp(belt, top, 0.66)),
        (bx * 0.38, lerp(belt, top, 0.90)),
        (bx * 0.19, lerp(belt, top, 0.985)),
        (0.0, top),
    ]
    w = smoothstep(spec.COWL_Y - 0.08, spec.COWL_Y + 0.08, y) * (
        1.0 - smoothstep(spec.DECK_Y - 0.08, spec.DECK_Y + 0.08, y))
    upper = [(lerp(h[0], g[0], w), lerp(h[1], g[1], w)) for h, g in zip(hood, glass)]
    return lower + upper


def full_loop(y: float, p: spec.Profiles) -> list[Vector]:
    right = half_loop(y, p)
    # Plan-view corner rounding over the last 0.32 m at either end so the
    # nose and tail read as designed corners instead of a squashed loop.
    distance = min(y - spec.NOSE_Y, spec.TAIL_Y - y)
    if distance < 0.30:
        t = max(0.0, distance) / 0.30
        factor = 0.70 + 0.30 * (1.0 - (1.0 - t) ** 2.6) ** (1.0 / 2.6)
        right = [(x * factor, z) for x, z in right]
    left = [(-x, z) for x, z in reversed(right[1:-1])]
    return [Vector((x, y, z)) for x, z in right + left]


def section_positions(step: float = 0.10) -> list[float]:
    """Longitudinal stations: a regular grid plus every panel boundary."""
    required = {
        spec.NOSE_Y, spec.TAIL_Y, spec.HOOD_FRONT_Y, spec.FRONT_BUMPER_Y, spec.HOOD_REAR_Y,
        spec.COWL_Y, spec.DOOR_FRONT_Y, spec.A_PILLAR_TOP_Y, spec.DOOR_REAR_Y,
        spec.REAR_ROOF_Y, spec.DECK_Y, spec.TRUNK_FRONT_Y, spec.TRUNK_REAR_Y,
        spec.REAR_BUMPER_Y, spec.FRONT_AXLE_Y, spec.REAR_AXLE_Y,
    }
    grid = []
    y = spec.NOSE_Y
    while y < spec.TAIL_Y:
        grid.append(round(y, 4))
        y += step
    values = sorted(set(grid) | required)
    merged: list[float] = []
    for value in values:
        if merged and abs(value - merged[-1]) < 0.035 and value not in required:
            continue
        if merged and abs(value - merged[-1]) < 0.035 and merged[-1] not in required:
            merged[-1] = value
            continue
        merged.append(value)
    return merged


def panel_for_face(y: float, station: int) -> int:
    """Panel id for a face whose lower station index is ``station``.

    Shut-line layout from the proportion sheet: a hood from the leading edge
    over the bumper to a shut just ahead of the cowl, a front bumper cover
    wrapping into the arches below the fender crest, doors between the
    A-pillar base and 0.12 m ahead of the rear arch, a trunk lid on the deck
    and a rear bumper cover below the tail lamp bar.
    """
    if station >= 8:
        if spec.COWL_Y <= y < spec.A_PILLAR_TOP_Y:
            return spec.PANEL_GLASS_FRONT
        if spec.A_PILLAR_TOP_Y <= y < spec.REAR_ROOF_Y:
            return spec.PANEL_GLASS_SIDE if station <= 10 else spec.PANEL_ROOF
        if spec.REAR_ROOF_Y <= y < spec.DECK_Y:
            return spec.PANEL_GLASS_REAR
        if spec.HOOD_FRONT_Y <= y < spec.HOOD_REAR_Y:
            return spec.PANEL_HOOD
        if spec.TRUNK_FRONT_Y <= y < spec.TRUNK_REAR_Y:
            return spec.PANEL_TRUNK
        if y < spec.HOOD_FRONT_Y:
            return spec.PANEL_FRONT_BUMPER
        if y >= spec.TRUNK_REAR_Y:
            return spec.PANEL_REAR_BUMPER
        return spec.PANEL_BODY
    if y < spec.FRONT_BUMPER_Y and (station <= spec.STATION_ARCH or y < spec.HOOD_FRONT_Y):
        return spec.PANEL_FRONT_BUMPER
    if y >= spec.REAR_BUMPER_Y and (station <= spec.STATION_ARCH or y >= spec.TRUNK_REAR_Y):
        return spec.PANEL_REAR_BUMPER
    if 3 <= station <= 7 and spec.DOOR_FRONT_Y <= y < spec.DOOR_REAR_Y:
        return spec.PANEL_DOOR
    if 2 <= station <= 7:
        if y < spec.DOOR_FRONT_Y:
            return spec.PANEL_FENDER_FRONT
        if y >= spec.DOOR_REAR_Y:
            return spec.PANEL_QUARTER
    return spec.PANEL_BODY


# Crease weights along the length at each station edge (right and left).
STATION_CREASES = {
    spec.STATION_FLOOR_EDGE: 0.55,
    spec.STATION_SILL_TOP: 0.45,
    spec.STATION_SHOULDER: 0.50,
    spec.STATION_BELT_TOP: 0.62,
    spec.STATION_ROOF_RAIL: 0.28,
}
# Crease weights around the loop at a section boundary (upper stations only).
SECTION_CREASES = {spec.COWL_Y: 0.35, spec.DECK_Y: 0.30}


def ladder_cap(bm: bmesh.types.BMesh, loop: list[bmesh.types.BMVert]) -> list[tuple[bmesh.types.BMFace, int]]:
    """Fill a section loop with horizontal quad bands (right station k to left
    station k), which subdivides into a clean rounded face instead of the
    starburst a single n-gon produces."""
    faces = []
    half = spec.HALF_STATIONS
    right = [loop[k] for k in range(half)]
    left = [loop[0]] + [loop[LOOP_SIZE - k] for k in range(1, half - 1)] + [loop[half - 1]]
    for k in range(half - 1):
        verts = [right[k], right[k + 1], left[k + 1], left[k]]
        unique = []
        for vert in verts:
            if vert not in unique:
                unique.append(vert)
        if len(unique) < 3:
            continue
        faces.append((bm.faces.new(unique), k))
    return faces


def cap_upper_panel(panel: int) -> int:
    return spec.PANEL_HOOD if panel == spec.PANEL_FRONT_BUMPER else spec.PANEL_TRUNK


@dataclass
class Hull:
    obj: bpy.types.Object
    panel_layer_name: str = "panel"


def build_cage(p: spec.Profiles, name: str = "HeroGtCage") -> Hull:
    bm = bmesh.new()
    panel_layer = bm.faces.layers.int.new("panel")
    crease_layer = bm.edges.layers.float.new("crease_edge")
    ys = section_positions()
    loops: list[list[bmesh.types.BMVert]] = []
    for index, y in enumerate(ys):
        points = full_loop(y, p)
        # Soften the very end loops vertically; the plan view is rounded in full_loop.
        if index == 0 or index == len(ys) - 1:
            centre = sum(points, Vector()) / len(points)
            points = [centre + (point - centre) * Vector((1.0, 1.0, 0.90)) for point in points]
        loops.append([bm.verts.new(point) for point in points])
    for s in range(len(loops) - 1):
        y_mid = 0.5 * (ys[s] + ys[s + 1])
        for k in range(LOOP_SIZE):
            a = loops[s][k]
            b = loops[s][(k + 1) % LOOP_SIZE]
            c = loops[s + 1][(k + 1) % LOOP_SIZE]
            d = loops[s + 1][k]
            face = bm.faces.new((a, b, c, d))
            face.smooth = True
            station = min(station_of(k), station_of((k + 1) % LOOP_SIZE))
            face[panel_layer] = panel_for_face(y_mid, station)
    for loop, panel in ((loops[0], spec.PANEL_FRONT_BUMPER), (loops[-1], spec.PANEL_REAR_BUMPER)):
        for face, station in ladder_cap(bm, loop):
            face.smooth = True
            face[panel_layer] = panel if station <= spec.STATION_ARCH else cap_upper_panel(panel)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # Creases: along-length edges at character stations.
    bm.verts.ensure_lookup_table()
    vert_station = {}
    for loop in loops:
        for k, vert in enumerate(loop):
            vert_station[vert.index if False else id(vert)] = station_of(k)
    for edge in bm.edges:
        v0, v1 = edge.verts
        s0, s1 = vert_station[id(v0)], vert_station[id(v1)]
        along_length = abs(v0.co.y - v1.co.y) > 1e-6 and s0 == s1
        if along_length and s0 in STATION_CREASES:
            edge[crease_layer] = STATION_CREASES[s0]
        elif not along_length:
            for y_key, weight in SECTION_CREASES.items():
                if abs(v0.co.y - y_key) < 1e-6 and min(s0, s1) >= 8:
                    edge[crease_layer] = max(edge[crease_layer], weight)
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return Hull(obj)


def arch_cutter(name: str, x: float, y: float, z: float, side: int) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=64, radius1=spec.ARCH_RADIUS, radius2=spec.ARCH_RADIUS, depth=1.0)
    bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=bm.verts)
    # A slightly squashed opening (wider than tall at the top) reads more like
    # a designed arch than a perfect circle.
    bmesh.ops.scale(bm, vec=Vector((1.0, 1.06, 1.0)), verts=bm.verts)
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    cutter = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(cutter)
    cutter.location = (x + side * 0.30, y, z + 0.02)
    return cutter


def apply_modifiers(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_apply(modifier=modifier.name)


def subdivide_and_cut(hull: Hull, levels: int, arches: bool, well_material: bpy.types.Material | None = None) -> None:
    obj = hull.obj
    if well_material is not None and well_material.name not in obj.data.materials:
        obj.data.materials.append(well_material)
    if levels > 0:
        modifier = obj.modifiers.new("Subdivision", "SUBSURF")
        modifier.levels = levels
        modifier.render_levels = levels
        modifier.subdivision_type = "CATMULL_CLARK"
        modifier.use_creases = True
    cutters = []
    if arches:
        for suffix, y in (("F", spec.FRONT_AXLE_Y), ("R", spec.REAR_AXLE_Y)):
            for side in (-1, 1):
                cutter = arch_cutter(f"ArchCutter{suffix}{side}", side * spec.WHEEL_X, y, spec.WHEEL_Z, side)
                if well_material is not None:
                    cutter.data.materials.append(well_material)
                boolean = obj.modifiers.new(f"Arch{suffix}{side}", "BOOLEAN")
                boolean.operation = "DIFFERENCE"
                boolean.solver = "EXACT"
                boolean.material_mode = "TRANSFER"
                boolean.object = cutter
                cutters.append(cutter)
    bpy.context.view_layer.update()
    apply_modifiers(obj)
    for cutter in cutters:
        bpy.data.objects.remove(cutter, do_unlink=True)


def panel_ids(obj: bpy.types.Object) -> dict[int, int]:
    attribute = obj.data.attributes.get("panel")
    counts: dict[int, int] = {}
    if attribute is None:
        return counts
    for item in attribute.data:
        counts[item.value] = counts.get(item.value, 0) + 1
    return counts


def _boundary_edges(bm: bmesh.types.BMesh) -> list[bmesh.types.BMEdge]:
    return [edge for edge in bm.edges if edge.is_boundary]


def extract_panel(
    hull: Hull,
    ids: set[int],
    name: str,
    materials: list[bpy.types.Material],
    *,
    gap: float = 0.0,
    recess: float = 0.0,
    rim: float = 0.0,
    rim_material_index: int = 1,
) -> bpy.types.Object | None:
    """Copy the faces whose panel id is in ``ids`` into a new object.

    ``gap`` shrinks the panel by that much along the surface at every open
    boundary (half a shut line per side); ``recess`` sinks the whole panel
    along its normals; ``rim`` extrudes the boundary inward by that depth so
    the shut line has a dark wall behind it.
    """
    source = hull.obj.data
    bm = bmesh.new()
    bm.from_mesh(source)
    layer = bm.faces.layers.int.get("panel")
    if layer is None:
        raise RuntimeError("hull lost its panel attribute")
    doomed = [face for face in bm.faces if face[layer] not in ids]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    if not bm.faces:
        bm.free()
        return None
    for face in bm.faces:
        # Faces the arch cutter left behind keep the well material (slot 1).
        face.material_index = 1 if face.material_index == 1 else 0
        face.smooth = True
    if gap > 0:
        result = bmesh.ops.inset_region(
            bm, faces=list(bm.faces), thickness=gap, depth=0.0,
            use_boundary=True, use_even_offset=False, use_interpolate=True,
        )
        bmesh.ops.delete(bm, geom=result["faces"], context="FACES")
    if recess != 0.0:
        bm.normal_update()
        for vert in bm.verts:
            vert.co -= vert.normal * recess
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    for material in materials:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if rim > 0:
        add_rim(obj, rim, rim_material_index)
    return obj


def add_rim(obj: bpy.types.Object, rim: float, rim_material_index: int = 1) -> int:
    """Extrude every open boundary of ``obj`` inward by ``rim`` as a dark wall.

    The extruded copies start with no normal of their own, so the inward
    direction is taken from the source vertex they duplicate. A negative
    ``rim`` extrudes outward, which recess floors use to grow their walls back
    to the body surface. Returns the number of rim faces added.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    boundary = _boundary_edges(bm)
    added = 0
    if boundary:
        targets = {}
        for edge in boundary:
            for vert in edge.verts:
                targets[tuple(round(c, 6) for c in vert.co)] = vert.co - vert.normal * rim
        extruded = bmesh.ops.extrude_edge_only(bm, edges=boundary)
        new_verts = [item for item in extruded["geom"] if isinstance(item, bmesh.types.BMVert)]
        new_faces = [item for item in extruded["geom"] if isinstance(item, bmesh.types.BMFace)]
        for vert in new_verts:
            key = tuple(round(c, 6) for c in vert.co)
            if key in targets:
                vert.co = targets[key]
        for face in new_faces:
            face.material_index = rim_material_index
            face.smooth = False
        added = len(new_faces)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    return added
