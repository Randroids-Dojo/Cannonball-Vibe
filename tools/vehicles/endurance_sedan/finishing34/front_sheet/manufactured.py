"""Independent complete finite original cutter-return classification."""
import collections
import json
import math

from . import sheet_reference as sheet


def radial_returns(state, profile):
    expected = {'radius_m': .4483, 'facets': 64, 'wheel_y_m': [-1.46, 1.46],
                'wheel_z_m': .3433, 'absolute_x_range_m': [.46, 1.30],
                'plane_and_footprint_guard_m': 1e-6, 'face_alignment_min': .99999,
                'authorship': 'New radial return field; original outer-skin normals remain unselected.'}
    if json.dumps(profile, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError('Unreviewed independently supplied original arch profile')
    by_face = collections.defaultdict(list)
    for ti, t in enumerate(state['triangles']):
        by_face[t['face']].append((ti, t))
    apothem = .4483*math.cos(math.pi/64)
    half = .4483*math.sin(math.pi/64)
    result = []
    for fi, triangles in by_face.items():
        ps = [state['points'][vi] for _, t in triangles for vi in t['vertices']]
        if (not all(.46-1e-6 <= abs(p[0]) <= 1.30+1e-6 for p in ps)
                or min(p[0] for p in ps)*max(p[0] for p in ps) <= 0):
            continue
        normals = [sheet.normal([state['points'][vi] for vi in t['vertices']]) for _, t in triangles]
        choices = []
        for cy in (-1.46, 1.46):
            for facet in range(64):
                a = (facet+.5)*math.tau/64
                ny, nz = math.cos(a), math.sin(a)
                if not all(-n[1]*ny-n[2]*nz >= .99999 for n in normals):
                    continue
                error = max(abs((p[1]-cy)*ny+(p[2]-.3433)*nz-apothem) for p in ps)
                footprint = max(abs(-(p[1]-cy)*nz+(p[2]-.3433)*ny) for p in ps)
                if error <= 1e-6 and footprint <= half+1e-6:
                    choices.append({'face': fi, 'facet': facet, 'wheel_y_m': cy,
                                    'triangles': [ti for ti, _ in triangles], 'actual_points': ps,
                                    'plane_error_m': error, 'tangent_extent_m': footprint})
        if len(choices) > 1:
            raise ValueError('Ambiguous actual protected finite return')
        result.extend(choices)
    return result
