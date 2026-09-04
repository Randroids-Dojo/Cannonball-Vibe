"""Hero GT design specification: proportions, stations and budgets.

Every dimension is in metres in the authoring frame (Blender: X right, Y
forward with the nose at -Y, Z up, ground at Z=0). The physics contract fixes
the wheelbase, track, wheel radius and suspension rest length; everything
else follows the proportion sheet in docs/audits/p1-008/ (an original
front-engine grand tourer derived from DB12, Vantage, Roma, 812, AMG GT and
LC 500 measurements): 4.77 m long, 1.95 m wide, 1.30 m tall, front overhang
0.93 m, rear 1.00 m, cowl 1.10 m behind the front axle, windshield 62 degrees
from vertical, roof peak 1.85 m behind the front axle, 3 mm panel gaps.

The sheet measures x forward from the front axle; here y_blender = -1.42 - x.
"""

from __future__ import annotations

from dataclasses import dataclass

from .curves import Spline

# Physics contract (must match validate_and_export_hero_gt.py and the rig).
WHEELBASE = 2.84
TRACK = 1.64
WHEEL_RADIUS = 0.34
SUSPENSION_REST = 0.62
FRONT_AXLE_Y = -WHEELBASE / 2  # -1.42
REAR_AXLE_Y = WHEELBASE / 2  # 1.42
WHEEL_X = TRACK / 2  # 0.82
WHEEL_Z = 0.42  # design wheel-centre height at static ride height (arch centre)
# Physics: 1,450 kg over four 42 kN/m springs compress 0.085 m at rest; the
# chassis then sits 0.975 m above the road and the fully extended physics
# wheel centre is 0.255 m above the design ground. The rig raises the visual
# anchors by measured compression, so the visual wheel rests here at zero
# compression and returns to WHEEL_RADIUS above the road when loaded.
STATIC_COMPRESSION = 0.085
WHEEL_EXTENDED_Z = WHEEL_RADIUS - STATIC_COMPRESSION  # 0.255
ARCH_RADIUS = 0.395  # 55 mm gap over the tyre

# Overall envelope.
NOSE_Y = -2.35  # front overhang 0.93
TAIL_Y = 2.42  # rear overhang 1.00
GROUND_CLEARANCE = 0.11
HALF_WIDTH = 0.975  # 1.95 m over the arches
ROOF_HEIGHT = 1.30

# Longitudinal stations (Blender y).
HOOD_FRONT_Y = -2.17  # hood leading edge over the bumper
HOOD_REAR_Y = -0.50  # hood shut line
COWL_Y = -0.45  # windshield base, dash-to-axle 0.97
A_PILLAR_TOP_Y = 0.15  # windshield header
ROOF_PEAK_Y = 0.40
DOOR_FRONT_Y = -0.42
B_PILLAR_Y = 0.93
DOOR_REAR_Y = 0.86
REAR_ROOF_Y = 1.40  # C-pillar, backlight base
DECK_Y = 1.92  # backlight meets the deck
TRUNK_FRONT_Y = 1.94
TRUNK_REAR_Y = 2.38
FRONT_BUMPER_Y = -1.88  # bumper cover ends at the arch leading edge
REAR_BUMPER_Y = 1.95
MIRROR_Y = -0.38

# Lighting and details from the sheet.
HEADLAMP_Z = 0.66
HEADLAMP_X = 0.72
HEADLAMP_Y = (-2.02, -1.70)  # wraps from the nose back along the fender
TAIL_BAR_Z = 0.80  # below the bumper seam so the bar cuts one panel
TAIL_BAR_HALF_WIDTH = 0.85
EXHAUST_Z = 0.30
EXHAUST_X = (0.52, 0.66)
EXHAUST_DIAMETER = 0.09
PLATE_Z = 0.52
PLATE_SIZE = (0.305, 0.152)
GRILLE_SIZE = (0.95, 0.30)
GRILLE_Z = 0.45
DOOR_HANDLE_Z = 0.88
DOOR_HANDLE_Y = 0.73


@dataclass(frozen=True)
class Profiles:
    """Longitudinal splines that drive every cross-section."""

    top_z: Spline  # centreline silhouette
    belt_z: Spline  # fender crest / door top / deck edge height
    belt_x: Spline  # plan half-width at the beltline
    shoulder_z: Spline  # character line height (beltline minus ~60 mm)
    sill_z: Spline  # rocker top height
    floor_z: Spline  # underbody height
    roof_x: Spline  # greenhouse half-width at the cantrail
    roof_flat_x: Spline  # half-width of the flat roof panel


def default_profiles() -> Profiles:
    return Profiles(
        top_z=Spline([
            (NOSE_Y, 0.62), (HOOD_FRONT_Y, 0.74), (-1.80, 0.805), (FRONT_AXLE_Y, 0.84),
            (-1.0, 0.885), (-0.72, 0.925), (COWL_Y, 0.98), (-0.15, 1.15),
            (A_PILLAR_TOP_Y, 1.27), (ROOF_PEAK_Y, ROOF_HEIGHT), (1.0, 1.28),
            (REAR_ROOF_Y, 1.21), (1.68, 1.09), (DECK_Y, 0.995), (2.20, 0.98), (TAIL_Y, 0.975),
        ], tension=0.12),
        belt_z=Spline([
            (NOSE_Y, 0.60), (HOOD_FRONT_Y, 0.72), (-1.80, 0.82), (FRONT_AXLE_Y, 0.865),
            (-1.0, 0.90), (-0.72, 0.935), (COWL_Y, 0.975), (0.30, 0.99), (B_PILLAR_Y, 1.00),
            (REAR_AXLE_Y, 1.02), (DECK_Y, 1.03), (2.15, 1.00), (TAIL_Y, 0.97),
        ], tension=0.1),
        belt_x=Spline([
            (NOSE_Y, 0.74), (-2.10, 0.86), (-1.85, 0.93), (FRONT_AXLE_Y, HALF_WIDTH),
            (-1.0, 0.955), (COWL_Y, 0.945), (0.30, 0.932), (B_PILLAR_Y, 0.93),
            (REAR_AXLE_Y, HALF_WIDTH), (2.0, 0.955), (TAIL_Y, 0.88),
        ], tension=0.1),
        shoulder_z=Spline([
            (NOSE_Y, 0.48), (HOOD_FRONT_Y, 0.58), (FRONT_AXLE_Y, 0.70), (COWL_Y, 0.875),
            (B_PILLAR_Y, 0.905), (REAR_AXLE_Y, 0.93), (TAIL_Y, 0.87),
        ]),
        sill_z=Spline([(NOSE_Y, 0.30), (-1.0, 0.32), (0.0, 0.32), (1.0, 0.32), (TAIL_Y, 0.30)]),
        floor_z=Spline([
            (NOSE_Y, 0.20), (-2.0, 0.125), (-1.0, GROUND_CLEARANCE), (1.0, GROUND_CLEARANCE),
            (1.9, 0.14), (TAIL_Y, 0.30),
        ]),
        roof_x=Spline([
            (NOSE_Y, 0.55), (COWL_Y, 0.66), (A_PILLAR_TOP_Y, 0.74), (ROOF_PEAK_Y, 0.79),
            (B_PILLAR_Y, 0.81), (REAR_ROOF_Y, 0.77), (DECK_Y, 0.66), (TAIL_Y, 0.55),
        ]),
        roof_flat_x=Spline([
            (NOSE_Y, 0.35), (COWL_Y, 0.48), (A_PILLAR_TOP_Y, 0.58), (ROOF_PEAK_Y, 0.64),
            (B_PILLAR_Y, 0.65), (REAR_ROOF_Y, 0.60), (DECK_Y, 0.50), (TAIL_Y, 0.38),
        ]),
    )


# Station indices of the half-loop (floor centre to roof centre).
STATION_FLOOR_CENTRE = 0
STATION_FLOOR_EDGE = 1
STATION_SILL_BOTTOM = 2
STATION_SILL_TOP = 3
STATION_LOWER = 4
STATION_ARCH = 5
STATION_SHOULDER = 6
STATION_BELT = 7
STATION_BELT_TOP = 8
STATION_GLASS_LOW = 9
STATION_GLASS_HIGH = 10
STATION_ROOF_RAIL = 11
STATION_ROOF_EDGE = 12
STATION_ROOF_CENTRE = 13
HALF_STATIONS = 14

# Panel identifiers stored on faces so shut lines can be cut after subdivision.
PANEL_BODY = 0
PANEL_HOOD = 1
PANEL_ROOF = 2
PANEL_DOOR = 3
PANEL_TRUNK = 4
PANEL_FRONT_BUMPER = 5
PANEL_REAR_BUMPER = 6
PANEL_GLASS_FRONT = 7
PANEL_GLASS_SIDE = 8
PANEL_GLASS_REAR = 9
PANEL_FENDER_FRONT = 10
PANEL_QUARTER = 11

PANEL_NAMES = {
    PANEL_BODY: "Body",
    PANEL_HOOD: "Hood",
    PANEL_ROOF: "Roof",
    PANEL_DOOR: "Door",
    PANEL_TRUNK: "Trunk",
    PANEL_FRONT_BUMPER: "FrontBumper",
    PANEL_REAR_BUMPER: "RearBumper",
    PANEL_GLASS_FRONT: "Windshield",
    PANEL_GLASS_SIDE: "SideGlass",
    PANEL_GLASS_REAR: "RearGlass",
    PANEL_FENDER_FRONT: "FrontFender",
    PANEL_QUARTER: "Quarter",
}
GLASS_PANELS = {PANEL_GLASS_FRONT, PANEL_GLASS_SIDE, PANEL_GLASS_REAR}

PANEL_GAP = 0.003  # shut-line width in metres (sheet: 3 mm hood and doors)
BUMPER_GAP = 0.004
PANEL_RIM = 0.02  # depth of the dark wall behind a shut line
