"""Unaccepted original rear-seal and formed sill recipe; no scene save/export."""
import math
from . import geometry as geo

Y_STATIONS = (-.993, -.845, -.795, .650, .680)
SILL_OUTER_ABS_X = .820
SILL_THICKNESS = .003
ARC_DEGREES = (-4, 15, 35, 55, 75, 95)
ARC_MAX_STEP = 10.0


def linear(rows, y):
    if y <= rows[0][0]: return rows[0][1]
    for (a, av), (b, bv) in zip(rows, rows[1:]):
        if y <= b: return av + (bv-av)*(y-a)/(b-a)
    return rows[-1][1]


def original_seal_points(side, refined):
    angles = []
    for a, b in zip(ARC_DEGREES, ARC_DEGREES[1:]):
        steps = max(1, math.ceil((b-a)/ARC_MAX_STEP)) if refined else 1
        angles += [a+(b-a)*i/steps for i in range(steps)]
    angles.append(ARC_DEGREES[-1])
    outline = [(-.655, 1.019), (-.645, .306), (-.993, .306)]
    outline += [(-1.46+.459*math.cos(math.radians(a)), .3433+.459*math.sin(math.radians(a))) for a in angles]
    outline += [(-1.681, 1.022), (-1.264, 1.320), (-.661, 1.382)]
    return [(side*(.778 if z < 1 else .823-(z-1)*.48), y, z) for y, z in outline]


def build(collection, parent, rubber, sill_material):
    created = []
    for side, symbol in ((-1, 'L'), (1, 'R')):
        seal = geo.tube('PrivateCandidate04Seal_'+symbol, original_seal_points(side, True), .006, rubber, collection, parent, sides=8, closed=True)
        seal['candidate_replaces'] = 'LOD0_DoorApertureSeal_R'+symbol
        created.append(seal)
        vertices = []
        for y in Y_STATIONS:
            inner = linear(((.650, .785), (.757, .740)), y)
            top = linear(((-.845, .296), (-.795, .266)), y)
            knee = min(inner+.004, .789)
            for x, z in ((inner, top), (knee, .281), (SILL_OUTER_ABS_X, .281), (SILL_OUTER_ABS_X, .281-SILL_THICKNESS), (knee, .281-SILL_THICKNESS), (inner, top-SILL_THICKNESS)):
                vertices.append((side*x, y, z))
        faces = []
        for j in range(len(Y_STATIONS)-1):
            for k in range(6):
                a = 6*j+k; b = 6*j+(k+1)%6; c = 6*(j+1)+(k+1)%6; d = 6*(j+1)+k
                faces.extend(((a,b,c), (a,c,d)))
        faces += [(5,4,3,2,1,0), tuple(6*(len(Y_STATIONS)-1)+i for i in range(6))]
        sill = geo.mesh('PrivateCandidate04Sill_'+symbol, vertices, faces, sill_material, collection, parent)
        sill['candidate_replaces'] = 'LOD0_SillTread_'+symbol
        created.append(sill)
    return created, {
        'rear_seal': {'unchanged_control_points_and_radius': True, 'cross_section_radius_m': .006, 'angular_refinement_max_degrees': ARC_MAX_STEP, 'original_arc_angles_degrees': ARC_DEGREES, 'centerline_circle_radius_m': .459, 'parent_and_parked_contact_policy': 'unchanged; full door motion still required'},
        'sill': {'y_stations_m': Y_STATIONS, 'outer_abs_x_m': SILL_OUTER_ABS_X, 'inner_abs_x_m': 'exact original formed floor edge, .785 tapering afterY.650', 'top_z_m': 'inner edge follows .296 rear/.266 front; 4mm crosswise knee meets outer flatZ.281 below door edge' , 'thickness_m': SILL_THICKNESS, 'manufacturing_choice': 'Closed3mm formed metal scuff strip, folded down/up at its inboard edge to the actual floor; outer tread staysZ.281 below the rear door; original120mm flat pad replaced. EndY-.993 avoids wheel liner.'},
        'acceptance': 'Unaccepted original candidate; requires native baseline correspondence, closed/self, finite body/floor seats and all unrelated static/continuous door clearances.'
    }
