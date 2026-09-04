"""Hero GT cockpit: dash, binnacle, screens, console, seats, door cards,
steering wheel, pedals, rear shelf and mirror.

Authoring frame (nose at -Y). The floor sits at the sill height, the H-point
at 0.55 m, the dash top just under the cowl. Everything is a rounded box or a
revolve so it stays cheap; the leather and suede textures carry the detail.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import spec
from .parts import _link, cylinder_bmesh, rounded_box, rounded_box_bmesh, smooth

FLOOR_Z = 0.31
H_POINT_Z = 0.55
SEAT_X = 0.36


def build_interior(collection, parent, materials, profiles: spec.Profiles) -> None:
    leather = materials["leather"]
    dash_leather = materials["dash_leather"]
    suede = materials["suede"]
    carbon = materials["carbon"]
    alu = materials["alu"]
    plastic = materials["plastic"]
    screen = materials["screen"]
    chrome = materials["chrome"]

    # Floor and tunnel.
    rounded_box("LOD0_Floor", (1.50, 2.40, 0.02), (0.0, 0.55, FLOOR_Z), collection, parent, plastic, bevel=0.0)
    rounded_box("LOD0_Tunnel", (0.30, 2.00, 0.22), (0.0, 0.60, FLOOR_Z + 0.11), collection, parent, plastic, bevel=0.03)
    # Dash: a leather slab with a rolled top, an instrument binnacle and a
    # centre screen, plus a carbon strip along the front edge.
    cowl_top = profiles.top_z(spec.COWL_Y) - 0.03
    dash = rounded_box_bmesh((1.56, 0.38, 0.28), (0.0, spec.COWL_Y + 0.14, cowl_top - 0.18), bevel=0.05, segments=3)
    for vert in dash.verts:
        # Rake the front face under the windshield and drop the rear edge.
        if vert.co.y < spec.COWL_Y + 0.06:
            vert.co.z -= 0.06 * (spec.COWL_Y + 0.06 - vert.co.y) / 0.12
    dash_obj = _link("LOD0_Dash", dash, collection, parent, [dash_leather])
    smooth(dash_obj, 40)
    rounded_box("LOD0_DashStrip", (1.40, 0.03, 0.05), (0.0, spec.COWL_Y + 0.32, cowl_top - 0.12), collection, parent, carbon, bevel=0.008)
    # Binnacle: a hooded cowl over the cluster, its top rounded and its rear
    # lip drawn back over the screen, tilted a little towards the driver.
    hood = rounded_box_bmesh((0.40, 0.22, 0.13), (0, 0, 0), bevel=0.05, segments=4)
    for vert in hood.verts:
        if vert.co.z > 0.0:
            vert.co.y += 0.03 * vert.co.z / 0.065
            vert.co.x *= 1.0 - 0.10 * vert.co.z / 0.065
    bmesh.ops.rotate(hood, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(math.radians(-8), 3, "X"), verts=hood.verts)
    bmesh.ops.translate(hood, vec=Vector((-SEAT_X, spec.COWL_Y + 0.21, cowl_top - 0.01)), verts=hood.verts)
    hood_obj = _link("LOD0_Binnacle", hood, collection, parent, [dash_leather])
    smooth(hood_obj, 45)
    rounded_box("LOD0_ClusterBezel", (0.33, 0.014, 0.115), (-SEAT_X, spec.COWL_Y + 0.325, cowl_top - 0.035), collection, parent, plastic,
                rotation=(math.radians(-10), 0, 0), bevel=0.006)
    rounded_box("LOD0_Cluster", (0.30, 0.006, 0.09), (-SEAT_X, spec.COWL_Y + 0.334, cowl_top - 0.035), collection, parent, screen,
                rotation=(math.radians(-10), 0, 0), bevel=0.004)
    rounded_box("LOD0_CentreScreenBezel", (0.34, 0.014, 0.21), (0.0, spec.COWL_Y + 0.305, cowl_top - 0.13), collection, parent, plastic,
                rotation=(math.radians(-12), 0, 0), bevel=0.008)
    rounded_box("LOD0_CentreScreen", (0.30, 0.012, 0.17), (0.0, spec.COWL_Y + 0.31, cowl_top - 0.13), collection, parent, screen,
                rotation=(math.radians(-12), 0, 0), bevel=0.004)
    # Air vents: slim dark slots with two alloy vanes each, outboard and centre.
    for index, x in enumerate((-0.64, -0.13, 0.13, 0.64)):
        y = spec.COWL_Y + 0.30
        z = cowl_top - 0.075
        rounded_box(f"LOD0_Vent_{index}", (0.11, 0.03, 0.036), (x, y, z), collection, parent, plastic, bevel=0.006)
        for vane in (-0.008, 0.008):
            rounded_box(f"LOD0_VentVane_{index}{'A' if vane < 0 else 'B'}", (0.10, 0.012, 0.004), (x, y + 0.012, z + vane),
                        collection, parent, alu, bevel=0.001)
    # Start button on the console, ahead of the drive selector.
    start = cylinder_bmesh(0.018, 0.012, (0.10, 0.02, FLOOR_Z + 0.482), axis="Z", segments=24)
    start_obj = _link("LOD0_StartButton", start, collection, parent, [alu])
    smooth(start_obj, 40)
    rounded_box("LOD0_Console", (0.30, 1.05, 0.26), (0.0, 0.40, FLOOR_Z + 0.34), collection, parent, dash_leather, bevel=0.03)
    rounded_box("LOD0_ConsoleTrim", (0.26, 0.60, 0.012), (0.0, 0.28, FLOOR_Z + 0.475), collection, parent, carbon, bevel=0.004)
    knob = cylinder_bmesh(0.03, 0.03, (0.0, 0.10, FLOOR_Z + 0.50), axis="Z", segments=24)
    knob_obj = _link("LOD0_DriveKnob", knob, collection, parent, [alu])
    smooth(knob_obj, 40)
    rounded_box("LOD0_Armrest", (0.24, 0.32, 0.06), (0.0, 0.62, FLOOR_Z + 0.50), collection, parent, leather, bevel=0.02)

    # Seats: cushion with bolsters, raked backrest with bolsters, headrest.
    for x, suffix in ((-SEAT_X, "L"), (SEAT_X, "R")):
        rounded_box(f"LOD0_SeatBase_{suffix}", (0.50, 0.54, 0.15), (x, 0.42, H_POINT_Z - 0.07), collection, parent, leather, bevel=0.04, segments=3)
        rounded_box(f"LOD0_SeatCentre_{suffix}", (0.30, 0.44, 0.02), (x, 0.40, H_POINT_Z + 0.005), collection, parent, suede, bevel=0.008)
        for bx in (-0.22, 0.22):
            rounded_box(f"LOD0_SeatBolster_{suffix}{'A' if bx < 0 else 'B'}", (0.10, 0.50, 0.10), (x + bx, 0.42, H_POINT_Z + 0.02),
                        collection, parent, leather, bevel=0.035, segments=3)
        rake = math.radians(-22)
        back_centre = Vector((x, 0.72, H_POINT_Z + 0.25))
        rounded_box(f"LOD0_SeatBack_{suffix}", (0.52, 0.13, 0.54), back_centre, collection, parent, leather,
                    rotation=(rake, 0, 0), bevel=0.04, segments=3)
        rounded_box(f"LOD0_SeatBackCentre_{suffix}", (0.28, 0.02, 0.42), back_centre + Vector((0, -0.07, 0)), collection, parent, suede,
                    rotation=(rake, 0, 0), bevel=0.006)
        for bx in (-0.22, 0.22):
            rounded_box(f"LOD0_SeatBackBolster_{suffix}{'A' if bx < 0 else 'B'}", (0.10, 0.10, 0.46),
                        back_centre + Vector((bx, -0.045, 0)), collection, parent, leather, rotation=(rake, 0, 0), bevel=0.035, segments=3)
        rounded_box(f"LOD0_Headrest_{suffix}", (0.26, 0.11, 0.14), back_centre + Vector((0, 0.12, 0.34)), collection, parent, leather,
                    rotation=(rake, 0, 0), bevel=0.035, segments=3)
        rounded_box(f"LOD0_SeatShell_{suffix}", (0.48, 0.05, 0.50), back_centre + Vector((0, 0.085, 0.01)), collection, parent, carbon,
                    rotation=(rake, 0, 0), bevel=0.02)

    # Door cards with an armrest and a pull handle.
    for side, suffix in ((-1, "L"), (1, "R")):
        x = side * (profiles.belt_x(0.2) - 0.10)
        rounded_box(f"LOD0_DoorCard_{suffix}", (0.05, 1.20, 0.56), (x, 0.22, 0.66), collection, parent, leather, bevel=0.02)
        rounded_box(f"LOD0_DoorArmrest_{suffix}", (0.12, 0.60, 0.05), (x - side * 0.05, 0.30, 0.72), collection, parent, dash_leather, bevel=0.015)
        rounded_box(f"LOD0_DoorPull_{suffix}", (0.04, 0.16, 0.03), (x - side * 0.10, 0.05, 0.80), collection, parent, alu, bevel=0.01)
        rounded_box(f"LOD0_DoorTrim_{suffix}", (0.03, 1.10, 0.06), (x - side * 0.01, 0.22, 0.95), collection, parent, carbon, bevel=0.008)

    # Steering wheel: rim torus, three spokes, hub, column.
    wheel_centre = Vector((-SEAT_X, spec.COWL_Y + 0.50, 0.88))
    tilt = Matrix.Rotation(math.radians(65), 3, "X")
    bm = bmesh.new()
    _torus(bm, 0.18, 0.019, 36, 12)
    for angle in (math.radians(0), math.radians(180), math.radians(270)):
        spoke = rounded_box_bmesh((0.034, 0.15, 0.018), (math.cos(angle) * 0.085, math.sin(angle) * 0.085, 0.0),
                                  rotation=(0, 0, angle + math.pi / 2), bevel=0.005)
        temp = bpy.data.meshes.new("TempSpoke")
        spoke.to_mesh(temp)
        spoke.free()
        bm.from_mesh(temp)
        bpy.data.meshes.remove(temp)
    hub = cylinder_bmesh(0.05, 0.05, (0, 0, 0), axis="Z", segments=24)
    bmesh.ops.scale(hub, vec=Vector((1.25, 0.9, 1.0)), verts=hub.verts)
    temp = bpy.data.meshes.new("TempHub")
    hub.to_mesh(temp)
    hub.free()
    bm.from_mesh(temp)
    bpy.data.meshes.remove(temp)
    bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=tilt, verts=bm.verts)
    bmesh.ops.translate(bm, vec=wheel_centre, verts=bm.verts)
    wheel_obj = _link("LOD0_SteeringWheel", bm, collection, parent, [leather])
    smooth(wheel_obj, 45)
    column = cylinder_bmesh(0.03, 0.22, (0, 0, 0), axis="Z", segments=20)
    bmesh.ops.rotate(column, cent=Vector((0, 0, 0)), matrix=tilt, verts=column.verts)
    bmesh.ops.translate(column, vec=wheel_centre + tilt @ Vector((0, 0, -0.13)), verts=column.verts)
    column_obj = _link("LOD0_SteeringColumn", column, collection, parent, [plastic])
    smooth(column_obj, 40)
    for x_offset in (-0.10, 0.0, 0.10):
        rounded_box(f"LOD0_Pedal_{int(x_offset * 100) + 10}", (0.06, 0.02, 0.10), (-SEAT_X + x_offset, spec.COWL_Y + 0.25, FLOOR_Z + 0.10),
                    collection, parent, alu, rotation=(math.radians(-30), 0, 0), bevel=0.006)

    # Rear bulkhead and parcel shelf under the backlight; rear-view mirror.
    rounded_box("LOD0_RearBulkhead", (1.50, 0.04, 0.60), (0.0, spec.REAR_ROOF_Y - 0.10, 0.62), collection, parent, leather, bevel=0.01)
    shelf_z = profiles.belt_z(spec.DECK_Y) - 0.06
    rounded_box("LOD0_ParcelShelf", (1.46, 0.62, 0.03), (0.0, spec.REAR_ROOF_Y + 0.22, shelf_z), collection, parent, suede, bevel=0.008)
    rounded_box("LOD0_RearViewMirror", (0.24, 0.03, 0.07), (0.0, spec.COWL_Y + 0.42, profiles.top_z(spec.COWL_Y + 0.42) - 0.09),
                collection, parent, plastic, bevel=0.01)
    rounded_box("LOD0_RearViewGlass", (0.22, 0.004, 0.06), (0.0, spec.COWL_Y + 0.437, profiles.top_z(spec.COWL_Y + 0.42) - 0.09),
                collection, parent, chrome, bevel=0.002)
    # Headliner: three suede panels that follow the roof from the windshield
    # header to the backlight, so the ceiling is there from the eye point.
    segments = 3
    span = (spec.REAR_ROOF_Y - spec.A_PILLAR_TOP_Y) / segments
    for index in range(segments):
        y0 = spec.A_PILLAR_TOP_Y + index * span
        centre_y = y0 + span / 2
        pitch = math.atan2(profiles.top_z(y0 + span) - profiles.top_z(y0), span)
        rounded_box(f"LOD0_Headliner_{index}", (1.30, span + 0.02, 0.012), (0.0, centre_y, profiles.top_z(centre_y) - 0.06),
                    collection, parent, suede, rotation=(pitch, 0, 0), bevel=0.0)
    # A-pillars and windshield header: suede-trimmed bars along the glass edge
    # from the cowl corners to the roof rail, set just inboard of the glass.
    cowl_x = profiles.belt_x(spec.COWL_Y) - 0.058 - 0.045
    cowl_z = profiles.belt_z(spec.COWL_Y) + 0.02
    rail_x = profiles.roof_x(spec.A_PILLAR_TOP_Y) - 0.035
    rail_z = profiles.top_z(spec.A_PILLAR_TOP_Y) - 0.06
    for side, suffix in ((-1, "L"), (1, "R")):
        start = Vector((side * cowl_x, spec.COWL_Y + 0.02, cowl_z))
        end = Vector((side * rail_x, spec.A_PILLAR_TOP_Y, rail_z))
        direction = end - start
        bar = rounded_box_bmesh((0.075, direction.length, 0.06), (0, 0, 0), bevel=0.014, segments=2)
        rotation = Vector((0, 1, 0)).rotation_difference(direction.normalized()).to_matrix()
        bmesh.ops.rotate(bar, cent=Vector((0, 0, 0)), matrix=rotation, verts=bar.verts)
        bmesh.ops.translate(bar, vec=(start + end) / 2, verts=bar.verts)
        pillar = _link(f"LOD0_APillar_{suffix}", bar, collection, parent, [suede])
        smooth(pillar, 40)
        # Sun visors folded up against the header.
        rounded_box(f"LOD0_SunVisor_{suffix}", (0.30, 0.15, 0.012), (side * 0.40, spec.A_PILLAR_TOP_Y + 0.10, profiles.top_z(spec.A_PILLAR_TOP_Y + 0.10) - 0.085),
                    collection, parent, suede, rotation=(math.radians(18), 0, 0), bevel=0.004)
    rounded_box("LOD0_WindshieldHeader", (2 * rail_x + 0.02, 0.09, 0.05), (0.0, spec.A_PILLAR_TOP_Y - 0.02, rail_z + 0.005),
                collection, parent, suede, bevel=0.012)


def _torus(bm, major, minor, segments, rings) -> None:
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
