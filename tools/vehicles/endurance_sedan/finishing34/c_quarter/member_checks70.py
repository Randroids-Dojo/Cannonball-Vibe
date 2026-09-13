"""Finite native bearing and direct authored-field checks; no I/O."""
import math, struct
from fractions import Fraction as F
from .boundary02 import sub, dot, cross, unit, angle
from .joint43 import distance2
from endurance_sedan.qa.exact_triangles import intersection, vector

def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]

def fields(row, proof):
    targets = proof['ideal_targets']
    if len(targets) != len(row['normals']):
        raise ValueError('Incorrect full authored target length')
    max_n = 0.0
    max_uv = 0.0
    for i, (a, b) in enumerate(zip(targets, row['normals'])):
        if not all((math.isfinite(v) for v in a + b)) or min(math.hypot(*a), math.hypot(*b)) < 0.999999 or max(math.hypot(*a), math.hypot(*b)) > 1.000001:
            raise ValueError(('Invalid native/ideal normal', i))
        value = angle(a, b)
        if value > 0.025:
            raise ValueError(('Direct authored-normal encoding failed', i, value))
        max_n = max(max_n, value)
    for tri, loops in zip(row['triangles'], row['triangle_loops']):
        ps = [row['vertices'][v] for v in tri]
        n = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
        e = unit(sub(ps[1], ps[0]))
        v = cross(n, e)
        for p, li in zip(ps, loops):
            ideal = [dot(sub(p, ps[0]), e) / 0.25, dot(sub(p, ps[0]), v) / 0.25]
            for name, values in row['uvs'].items():
                error = max((abs(a - b) for a, b in zip(ideal, values[li])))
                max_uv = max(max_uv, error)
                if error > 1e-05:
                    raise ValueError(('New facet physical UV field changed', name, li, error))
    return {'status': 'passed', 'actual_corners': len(targets), 'maximum_direct_native_encoding_deg': max_n, 'maximum_authored_UV_error': max_uv, 'scope': 'Every actual new reinforcement loop against its original geometric facet target and facet-local orthonormal/.25 metre chart. No old member field equivalence is claimed.'}

def seats(member, skin, proof, contact):
    known = {}
    matched = []
    maximum = F(0)
    guard2 = F(1e-06) ** 2
    for record in proof['bearing_seats']:
        expected = [tuple((f32(v) for v in p)) for p in record['bearing_prism'][:3]]
        matches = [i for i, t in enumerate(member['triangles']) if set((tuple(member['vertices'][v]) for v in t)) == set(expected)]
        if len(matches) != 1:
            raise ValueError(('Actual complete bearing footprint missing/duplicated', record['actual_inner_triangle'], matches))
        fi = matches[0]
        actual = [member['vertices'][v] for v in member['triangles'][fi]]
        owner = record['actual_inner_triangle']
        reference = [skin['vertices'][v] for v in skin['triangles'][owner]]
        n = cross(sub(actual[1], actual[0]), sub(actual[2], actual[0]))
        nn = cross(sub(reference[1], reference[0]), sub(reference[2], reference[0]))
        if dot(n, nn) >= 0:
            raise ValueError('Bearing and actual inner skin have matching orientation')
        errors = [distance2(vector(p), reference) for p in actual]
        if max(errors) > guard2:
            raise ValueError('Complete native bearing triangle leaves the actual C facet')
        maximum = max(maximum, *errors)
        known[fi] = actual
        matched.append({'member_face': fi, 'actual_C_face': owner, 'native_top_vertex_inventory_exact': True, 'complete_triangle_to_C_distance_m': math.sqrt(float(max(errors))), 'area_m2': math.hypot(*n) / 2, 'opposing_orientation': True})
    if contact['native_three_ray_inside_vertices']:
        raise ValueError('C/member actual vertex inside opposite solid')
    classified = []
    for witness in contact['intersection_pairs']:
        ai, bi = (witness['a'], witness['b'])
        a = [member['vertices'][v] for v in member['triangles'][ai]]
        b = [skin['vertices'][v] for v in skin['triangles'][bi]]
        ps = intersection(a, b)
        if not ps:
            raise ValueError('Retained contact does not reproduce')
        error, owner = min(((max((distance2(p, triangle) for p in ps)), fi) for fi, triangle in known.items()))
        if error > guard2:
            raise ValueError(('Actual complete contact outside finite bearing', ai, bi, math.sqrt(float(error))))
        classified.append({'member_triangle': ai, 'C_triangle': bi, 'bearing_top': owner, 'maximum_contact_distance_squared_m': str(error)})
    if not classified:
        raise ValueError('No actual native finite bearing contact')
    return {'status': 'passed', 'whole_bearing_triangles': matched, 'complete_contact_pairs': classified, 'native_inside_vertices': 0, 'maximum_whole_bearing_to_C_distance_m': math.sqrt(float(maximum)), 'scope': 'Every bearing footprint is an entire native triangle carried by one actual inner C triangle. Exact dyadic actual contact polygons all lie in these finite native tops within the unchanged1um guard.'}
