"""Hero GT exterior parts: apertures, lamps, grille, splitter, diffuser,
mirrors, handles, wipers, exhausts, plate, badges.

Everything works on the extracted panel objects from :mod:`body` and in the
authoring frame (nose at -Y). Apertures are cut with exact booleans before
the panels receive their rim walls, so every opening edge gets the same dark
wall a shut line has.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import spec


def _link(name: str, bm: bmesh.types.BMesh, collection, parent, materials) -> bpy.types.Object:
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


def smooth(obj: bpy.types.Object, angle: float = 40.0) -> None:
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    with bpy.context.temp_override(object=obj, selected_editable_objects=[obj], active_object=obj):
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))


def rotation_matrix(rotation) -> Matrix:
    return Matrix.Rotation(rotation[0], 3, "X") @ Matrix.Rotation(rotation[1], 3, "Y") @ Matrix.Rotation(rotation[2], 3, "Z")


def rounded_box_bmesh(size, location, rotation=(0, 0, 0), bevel=0.01, segments=2) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(bevel, min(size) * 0.45), segments=segments, affect="EDGES")
    if rotation != (0, 0, 0):
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=rotation_matrix(rotation), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return bm


def rounded_box(name, size, location, collection, parent, material, rotation=(0, 0, 0), bevel=0.01, segments=2, angle=35.0):
    bm = rounded_box_bmesh(size, location, rotation, bevel, segments)
    obj = _link(name, bm, collection, parent, [material])
    smooth(obj, angle)
    return obj


def cylinder_bmesh(radius, depth, location, axis="Y", segments=32, radius2=None) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius if radius2 is None else radius2, depth=depth)
    if axis == "X":
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=bm.verts)
    elif axis == "Y":
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.pi / 2, 3, "X"), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return bm


def cutter_object(name: str, bm: bmesh.types.BMesh) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def cut(panel: bpy.types.Object, cutters: list[bpy.types.Object]) -> list[bpy.types.Object]:
    """Cut every convex cutter out of an open panel.

    Booleans need a closed target, and on an open shell the exact solver
    welds the cutter's own faces into the result. Instead the panel is
    bisected by each face plane of the convex cutter (only faces overlapping
    the cutter's bounding box are touched), then every face whose centre lies
    behind all of the planes is moved into a new object: the aperture piece,
    which conforms to the body surface and is what lamp covers, recess floors
    and grille inserts are built from. Returns one aperture object per cutter.
    """
    bm = bmesh.new()
    bm.from_mesh(panel.data)
    apertures = []
    for cutter in cutters:
        planes = []
        for polygon in cutter.data.polygons:
            normal = polygon.normal.copy()
            point = polygon.center.copy()
            if all(abs(normal.dot(other_normal) - 1.0) > 1e-4 or abs((point - other_point).dot(normal)) > 1e-5
                   for other_normal, other_point in planes):
                planes.append((normal, point))
        lo = Vector((min(v.co.x for v in cutter.data.vertices), min(v.co.y for v in cutter.data.vertices), min(v.co.z for v in cutter.data.vertices)))
        hi = Vector((max(v.co.x for v in cutter.data.vertices), max(v.co.y for v in cutter.data.vertices), max(v.co.z for v in cutter.data.vertices)))
        margin = 0.01

        def overlapping():
            faces = []
            for face in bm.faces:
                fx = [v.co.x for v in face.verts]
                fy = [v.co.y for v in face.verts]
                fz = [v.co.z for v in face.verts]
                if (max(fx) >= lo.x - margin and min(fx) <= hi.x + margin and
                        max(fy) >= lo.y - margin and min(fy) <= hi.y + margin and
                        max(fz) >= lo.z - margin and min(fz) <= hi.z + margin):
                    faces.append(face)
            return faces

        for normal, point in planes:
            faces = overlapping()
            if not faces:
                break
            geom = list({v for f in faces for v in f.verts}) + list({e for f in faces for e in f.edges}) + faces
            bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=point, plane_no=normal, clear_inner=False, clear_outer=False)
        doomed = []
        for face in overlapping():
            centre = face.calc_center_median()
            if all((centre - point).dot(normal) <= 1e-5 for normal, point in planes):
                doomed.append(face)
        piece = bmesh.new()
        lookup = {}
        for face in doomed:
            verts = []
            for vert in face.verts:
                key = id(vert)
                if key not in lookup:
                    lookup[key] = piece.verts.new(vert.co)
                verts.append(lookup[key])
            try:
                new_face = piece.faces.new(verts)
                new_face.smooth = True
            except ValueError:
                pass
        bmesh.ops.remove_doubles(piece, verts=piece.verts, dist=1e-6)
        bmesh.ops.recalc_face_normals(piece, faces=piece.faces)
        mesh = bpy.data.meshes.new(f"{cutter.name}ApertureMesh")
        piece.to_mesh(mesh)
        piece.free()
        aperture = bpy.data.objects.new(f"{cutter.name}Aperture", mesh)
        bpy.context.scene.collection.objects.link(aperture)
        apertures.append(aperture)
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
        bpy.data.objects.remove(cutter, do_unlink=True)
    bm.to_mesh(panel.data)
    bm.free()
    return apertures


def aperture_frame(aperture: bpy.types.Object) -> tuple[Vector, Vector]:
    """Area-weighted centre and mean outward normal of an aperture piece."""
    total = 0.0
    centre = Vector()
    normal = Vector()
    for polygon in aperture.data.polygons:
        total += polygon.area
        centre += polygon.center * polygon.area
        normal += polygon.normal * polygon.area
    if total > 0:
        centre /= total
    if normal.length > 0:
        normal.normalize()
    return centre, normal


def offset_copy(aperture: bpy.types.Object, name: str, depth: float, material, collection, parent, gap: float = 0.0, walls: bool = False, wall_material=None) -> bpy.types.Object:
    """A copy of the aperture faces sunk ``depth`` along their normals.

    ``gap`` shrinks the copy inward along the surface; ``walls`` extrudes the
    boundary back out to the surface so the copy reads as a recess floor.
    """
    bm = bmesh.new()
    bm.from_mesh(aperture.data)
    for face in bm.faces:
        face.material_index = 0
        face.smooth = True
    if gap > 0:
        result = bmesh.ops.inset_region(bm, faces=list(bm.faces), thickness=gap, depth=0.0, use_boundary=True, use_even_offset=False)
        bmesh.ops.delete(bm, geom=result["faces"], context="FACES")
    bm.normal_update()
    for vert in bm.verts:
        vert.co -= vert.normal * depth
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    mesh.materials.append(wall_material or material)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.parent = parent
    obj["semantic_role"] = name
    if walls and depth > 0:
        from . import body as body_module
        body_module.add_rim(obj, -depth, 1)
    smooth(obj, 40)
    return obj


# ----------------------------------------------------------------- front end


def surface_x(profiles: spec.Profiles, y: float, z: float) -> float:
    """Body half-width at height z for the station y (linear between stations)."""
    from . import body as body_module
    points = body_module.half_loop(y, profiles)
    for (x0, z0), (x1, z1) in zip(points, points[1:]):
        if min(z0, z1) <= z <= max(z0, z1) and z1 != z0:
            t = (z - z0) / (z1 - z0)
            return x0 + (x1 - x0) * t
    return max(x for x, _ in points)


def surface_z(profiles: spec.Profiles, y: float, x: float) -> float:
    """Upper-surface height at plan position (x, y) for the station y."""
    from . import body as body_module
    points = body_module.half_loop(y, profiles)
    upper = points[spec.STATION_BELT:]
    ax = abs(x)
    for (x0, z0), (x1, z1) in zip(upper, upper[1:]):
        if min(x0, x1) <= ax <= max(x0, x1) and x1 != x0:
            return z0 + (z1 - z0) * (ax - x0) / (x1 - x0)
    return max(z for _, z in points)


def front_cutters(profiles: spec.Profiles) -> list[bpy.types.Object]:
    """Grille aperture, two lower intakes and two headlamp recesses."""
    nose = spec.NOSE_Y
    cutters = []
    width, height = spec.GRILLE_SIZE
    cutters.append(cutter_object("GrilleCutter", rounded_box_bmesh(
        (width, 0.40, height), (0.0, nose + 0.06, spec.GRILLE_Z), bevel=0.06, segments=4)))
    for side in (-1, 1):
        cutters.append(cutter_object(f"Intake{'L' if side < 0 else 'R'}Cutter", rounded_box_bmesh(
            (0.20, 0.34, 0.11), (side * 0.72, nose + 0.10, 0.30), bevel=0.03, segments=4)))
    return cutters


def lamp_cutters(profiles: spec.Profiles) -> list[bpy.types.Object]:
    """Headlamp recesses on the fascia above the grille corners.

    Each is a slim horizontal bar that starts on the front face and sweeps
    back around the corner, so it reads from the front and the side.
    """
    cutters = []
    for side in (-1, 1):
        cutters.append(cutter_object(f"Headlamp{'FL' if side < 0 else 'FR'}Cutter", rounded_box_bmesh(
            (0.44, 0.34, 0.082), (side * spec.HEADLAMP_X, spec.NOSE_Y + 0.10, spec.HEADLAMP_Z),
            rotation=(0, 0, side * math.radians(-24)), bevel=0.025, segments=3)))
    return cutters


def build_front_parts(collection, parent, materials, apertures: dict[str, bpy.types.Object]) -> None:
    nose = spec.NOSE_Y
    # Grille: cavity floor with walls, perforated mesh insert, nose badge.
    grille = apertures["GrilleCutter"]
    offset_copy(grille, "LOD0_GrilleCavity", 0.22, materials["cavity"], collection, parent, walls=True)
    mesh = offset_copy(grille, "LOD0_GrilleMesh", 0.05, materials["grille"], collection, parent, gap=0.004)
    _planar_uv(mesh, scale=6.0)
    centre, normal = aperture_frame(grille)
    badge = cylinder_bmesh(0.045, 0.012, (0, 0, 0), axis="Y", segments=32)
    bmesh.ops.scale(badge, vec=Vector((1.5, 1.0, 0.7)), verts=badge.verts)
    bmesh.ops.translate(badge, vec=centre - normal * 0.03 + Vector((0, 0, 0.10)), verts=badge.verts)
    badge_obj = _link("LOD0_NoseBadge", badge, collection, parent, [materials["chrome"]])
    smooth(badge_obj, 40)
    for suffix in ("L", "R"):
        intake = apertures[f"Intake{suffix}Cutter"]
        offset_copy(intake, f"LOD0_IntakeCavity_{suffix}", 0.16, materials["cavity"], collection, parent, walls=True)
        mesh = offset_copy(intake, f"LOD0_IntakeMesh_{suffix}", 0.04, materials["grille"], collection, parent, gap=0.004)
        _planar_uv(mesh, scale=6.0)
    # Splitter blade: mostly under the bumper, 50 mm proud of its lip.
    rounded_box("LOD0_Splitter", (1.72, 0.30, 0.024), (0.0, nose + 0.16, 0.135), collection, parent, materials["carbon"], bevel=0.006)
    # Headlamps: housing floor, projector with chrome bezel, LED strip along
    # the top edge, clear cover flush with the body.
    for suffix in ("FL", "FR"):
        lamp = apertures[f"Headlamp{suffix}Cutter"]
        side = -1 if suffix == "FL" else 1
        centre, normal = aperture_frame(lamp)
        offset_copy(lamp, f"LOD0_LampHousing_{suffix}", 0.10, materials["housing"], collection, parent, walls=True)
        along = Vector((0, 0, 1)).cross(normal).normalized()
        lens_centre = centre - normal * 0.055 + along * (0.05 * side)
        bezel = cylinder_bmesh(0.042, 0.05, (0, 0, 0), axis="Y", segments=32, radius2=0.048)
        rotation = normal.to_track_quat("Y", "Z").to_matrix()
        bmesh.ops.rotate(bezel, cent=Vector((0, 0, 0)), matrix=rotation, verts=bezel.verts)
        bmesh.ops.translate(bezel, vec=lens_centre, verts=bezel.verts)
        bezel_obj = _link(f"LOD0_LampBezel_{suffix}", bezel, collection, parent, [materials["chrome"]])
        smooth(bezel_obj, 40)
        lens = cylinder_bmesh(0.035, 0.012, (0, 0, 0), axis="Y", segments=32)
        bmesh.ops.rotate(lens, cent=Vector((0, 0, 0)), matrix=rotation, verts=lens.verts)
        bmesh.ops.translate(lens, vec=lens_centre + normal * 0.02, verts=lens.verts)
        lens_obj = _link(f"LOD0_LampLens_{suffix}", lens, collection, parent, [materials["headlamp"]])
        smooth(lens_obj, 40)
        zs = [v.co.z for v in lamp.data.vertices]
        strip = offset_copy(lamp, f"LOD0_LampStrip_{suffix}", 0.02, materials["led"], collection, parent, gap=0.006)
        keep_z = max(zs) - 0.03
        bm = bmesh.new()
        bm.from_mesh(strip.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z < keep_z], context="FACES")
        bm.to_mesh(strip.data)
        bm.free()
        offset_copy(lamp, f"LOD0_LampCover_{suffix}", 0.001, materials["lens_glass"], collection, parent)


# ----------------------------------------------------------------- rear end


def rear_cutters() -> list[bpy.types.Object]:
    tail = spec.TAIL_Y
    cutters = [
        cutter_object("TailBarCutter", rounded_box_bmesh(
            (spec.TAIL_BAR_HALF_WIDTH * 2, 0.40, 0.065), (0.0, tail - 0.10, spec.TAIL_BAR_Z), bevel=0.025, segments=3)),
        cutter_object("PlateCutter", rounded_box_bmesh(
            (spec.PLATE_SIZE[0] + 0.05, 0.30, spec.PLATE_SIZE[1] + 0.04), (0.0, tail - 0.08, spec.PLATE_Z), bevel=0.02, segments=2)),
    ]
    for x in spec.EXHAUST_X:
        for side in (-1, 1):
            cutters.append(cutter_object(f"Exhaust{'L' if side < 0 else 'R'}{int(x * 100)}Cutter", cylinder_bmesh(
                spec.EXHAUST_DIAMETER / 2 + 0.008, 0.40, (side * x, tail - 0.10, spec.EXHAUST_Z), axis="Y", segments=24)))
    return cutters


def build_rear_parts(collection, parent, materials, apertures: dict[str, bpy.types.Object]) -> None:
    tail = spec.TAIL_Y
    bar = apertures["TailBarCutter"]
    offset_copy(bar, "LOD0_TailBarHousing", 0.05, materials["housing"], collection, parent, walls=True)
    offset_copy(bar, "LOD0_TailBar", 0.018, materials["taillamp"], collection, parent, gap=0.005)
    offset_copy(bar, "LOD0_TailBarCover", 0.001, materials["lens_glass_red"], collection, parent)
    plate_aperture = apertures["PlateCutter"]
    offset_copy(plate_aperture, "LOD0_PlateRecess", 0.035, materials["housing"], collection, parent, walls=True)
    plate_w, plate_h = spec.PLATE_SIZE
    centre, normal = aperture_frame(plate_aperture)
    plate = rounded_box("LOD0_Plate", (plate_w, 0.008, plate_h), centre - normal * 0.025, collection, parent, materials["plate"], bevel=0.004)
    _planar_uv(plate, scale=1.0 / plate_w, axis="y")
    # Diffuser: a carbon tray with five vertical fins under the bumper, rising to the rear.
    rounded_box("LOD0_DiffuserTray", (1.30, 0.34, 0.02), (0.0, tail - 0.30, 0.245), collection, parent, materials["carbon"],
                rotation=(math.radians(-8), 0, 0), bevel=0.006)
    for x in (-0.50, -0.25, 0.0, 0.25, 0.50):
        rounded_box(f"LOD0_DiffuserFin_{int(x * 100) + 50}", (0.012, 0.30, 0.08), (x, tail - 0.30, 0.29),
                    collection, parent, materials["carbon"], rotation=(math.radians(-8), 0, 0), bevel=0.004)
    # Exhaust tips: dark bore behind the aperture, chrome ring set just inside it.
    for x in spec.EXHAUST_X:
        for side in (-1, 1):
            name = f"Exhaust{'L' if side < 0 else 'R'}{int(x * 100)}"
            aperture = apertures[f"{name}Cutter"]
            offset_copy(aperture, f"LOD0_{name}_Bore", 0.14, materials["cavity"], collection, parent, walls=True)
            centre, normal = aperture_frame(aperture)
            radius = spec.EXHAUST_DIAMETER / 2
            ring = cylinder_bmesh(radius, 0.10, (0, 0, 0), axis="Y", segments=28)
            bmesh.ops.translate(ring, vec=centre - normal * 0.045, verts=ring.verts)
            ring_obj = _link(f"LOD0_{name}_Tip", ring, collection, parent, [materials["chrome"]])
            smooth(ring_obj, 40)
            bore = cylinder_bmesh(radius - 0.006, 0.10, (0, 0, 0), axis="Y", segments=28)
            bmesh.ops.reverse_faces(bore, faces=list(bore.faces))
            bmesh.ops.translate(bore, vec=centre - normal * 0.05, verts=bore.verts)
            bore_obj = _link(f"LOD0_{name}_Inner", bore, collection, parent, [materials["cavity"]])
            smooth(bore_obj, 40)
    # Rear badge bar just above the lamp bar.
    rounded_box("LOD0_TailBadge", (0.16, 0.006, 0.03), (0.0, tail - 0.003, spec.TAIL_BAR_Z + 0.09), collection, parent, materials["chrome"], bevel=0.004)


# ----------------------------------------------------------------- side and top


def side_cutters(profiles: spec.Profiles) -> list[bpy.types.Object]:
    """Door-handle recesses and the fuel-filler door outline."""
    cutters = []
    for side in (-1, 1):
        x = profiles.belt_x(spec.DOOR_HANDLE_Y) - 0.02
        cutters.append(cutter_object(f"HandleCutter{side}", rounded_box_bmesh(
            (0.06, 0.15, 0.03), (side * x, spec.DOOR_HANDLE_Y, spec.DOOR_HANDLE_Z), bevel=0.012, segments=2)))
    return cutters


def build_side_parts(collection, parent, materials, profiles: spec.Profiles) -> None:
    for side in (-1, 1):
        suffix = "L" if side < 0 else "R"
        x = profiles.belt_x(spec.DOOR_HANDLE_Y)
        rounded_box(f"LOD0_HandleRecess_{suffix}", (0.05, 0.16, 0.036), (side * (x - 0.03), spec.DOOR_HANDLE_Y, spec.DOOR_HANDLE_Z),
                    collection, parent, materials["housing"], bevel=0.012)
        rounded_box(f"LOD0_Handle_{suffix}", (0.012, 0.12, 0.022), (side * (x - 0.012), spec.DOOR_HANDLE_Y, spec.DOOR_HANDLE_Z),
                    collection, parent, materials["paint"], bevel=0.005)
        # Mirror: a stalk off the door top at the A-pillar base, a teardrop
        # housing with its rear face flattened for the glass.
        belt_x = profiles.belt_x(spec.MIRROR_Y)
        belt_z = profiles.belt_z(spec.MIRROR_Y)
        mirror_x = side * (belt_x + 0.075)
        mirror_z = belt_z + 0.035
        rounded_box(f"LOD0_MirrorStalk_{suffix}", (0.13, 0.045, 0.02), (side * (belt_x + 0.01), spec.MIRROR_Y, belt_z + 0.012),
                    collection, parent, materials["housing"], rotation=(0, side * math.radians(-15), 0), bevel=0.006)
        # Housing: a pebble with a flat rear face, its outer end drawn back
        # and its nose tapered so it reads as a cast shell rather than a ball.
        housing = bmesh.new()
        bmesh.ops.create_uvsphere(housing, u_segments=28, v_segments=16, radius=0.5)
        bmesh.ops.scale(housing, vec=Vector((0.21, 0.13, 0.072)), verts=housing.verts)
        for vert in housing.verts:
            # Thinner and narrower towards the leading edge, flat at the glass.
            taper = 0.80 + 0.20 * (vert.co.y + 0.065) / 0.13
            vert.co.z *= taper
            if vert.co.y > 0.042:
                vert.co.y = 0.042
        bmesh.ops.rotate(housing, cent=Vector((0, 0, 0)), matrix=rotation_matrix((0, side * math.radians(6), side * math.radians(-8))), verts=housing.verts)
        bmesh.ops.translate(housing, vec=Vector((mirror_x, spec.MIRROR_Y, mirror_z)), verts=housing.verts)
        housing_obj = _link(f"LOD0_MirrorHousing_{suffix}", housing, collection, parent, [materials["paint"]])
        smooth(housing_obj, 50)
        glass = cylinder_bmesh(0.036, 0.004, (0, 0, 0), axis="Y", segments=28)
        bmesh.ops.scale(glass, vec=Vector((2.2, 1.0, 1.0)), verts=glass.verts)
        bmesh.ops.translate(glass, vec=Vector((mirror_x, spec.MIRROR_Y + 0.047, mirror_z)), verts=glass.verts)
        glass_obj = _link(f"LOD0_MirrorGlass_{suffix}", glass, collection, parent, [materials["chrome"]])
        smooth(glass_obj, 40)
        # Sill blade tucked under the rocker.
        sill_x = profiles.belt_x(0.2) - 0.105
        rounded_box(f"LOD0_SillBlade_{suffix}", (0.07, 2.05, 0.04), (side * sill_x, 0.22, profiles.sill_z(0.2) - 0.10),
                    collection, parent, materials["carbon"], bevel=0.008)
    # Wipers parked on the cowl panel behind the hood shut line, ahead of the
    # glass and well below the eye line now that the cowl sits at 0.915 m.
    for index, x in enumerate((-0.42, 0.18)):
        y = spec.COWL_Y + 0.012
        rounded_box(f"LOD0_Wiper_{index}", (0.46, 0.012, 0.006), (x, y, surface_z(profiles, y, x) - 0.004),
                    collection, parent, materials["housing"], rotation=(0, 0, math.radians(-5)), bevel=0.0025)
    # Shark-fin antenna at the rear of the roof.
    fin = rounded_box_bmesh((0.028, 0.15, 0.036), (0.0, spec.REAR_ROOF_Y - 0.16, profiles.top_z(spec.REAR_ROOF_Y - 0.16) + 0.008), bevel=0.008)
    for vert in fin.verts:
        if vert.co.z > profiles.top_z(spec.REAR_ROOF_Y - 0.16) + 0.02:
            vert.co.y += 0.05
    fin_obj = _link("LOD0_Antenna", fin, collection, parent, [materials["paint"]])
    smooth(fin_obj, 40)


def _planar_uv(obj: bpy.types.Object, scale: float, axis: str = "y") -> None:
    """Project UVs along an axis for tiling textures on flat inserts."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            if axis == "y":
                loop[uv_layer].uv = (co.x * scale, co.z * scale)
            elif axis == "x":
                loop[uv_layer].uv = (co.y * scale, co.z * scale)
            else:
                loop[uv_layer].uv = (co.x * scale, co.y * scale)
    bm.to_mesh(obj.data)
    bm.free()
