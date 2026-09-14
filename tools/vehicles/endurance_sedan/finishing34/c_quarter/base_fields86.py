"""Independent full-face field and upper-domain certificate; no I/O."""
from fractions import Fraction as F
from collections import defaultdict
import math
from .boundary02 import sub, dot, cross, unit, angle
from .joint43 import distance2
from endurance_sedan.qa.exact_triangles import vector
from .fragment04 import clip
IDENTITY = [[F(1), F(0), F(0)], [F(0), F(1), F(0)], [F(0), F(0), F(1)]]

def bary(p, ps):
    a, b, c = map(vector, ps)
    p = vector(p)
    v = sub(b, a)
    w = sub(c, a)
    q = sub(p, a)
    vv = dot(v, v)
    vw = dot(v, w)
    ww = dot(w, w)
    d = vv * ww - vw * vw
    if d == 0:
        raise ValueError('Invalid complete reference triangle')
    b = (dot(q, v) * ww - dot(q, w) * vw) / d
    c = (dot(q, w) * vv - dot(q, v) * vw) / d
    return [1 - b - c, b, c]

def signed_area(poly):
    return sum((a[1] * b[2] - a[2] * b[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2 if len(poly) >= 3 else F(0)

def remove(poly, triangle):
    if signed_area(triangle) < 0:
        triangle = list(reversed(triangle))
    out = []
    inside = poly
    for a, b in zip(triangle, triangle[1:] + triangle[:1]):
        value = lambda p: (b[1] - a[1]) * (p[2] - a[2]) - (b[2] - a[2]) * (p[1] - a[1])
        values = [value(p) for p in IDENTITY]
        other = clip(inside, [-v for v in values])
        if other and signed_area(other) != 0:
            out.append(other)
        inside = clip(inside, values)
        if not inside:
            break
    return out

def check(row, proof, original_ideal):
    old = proof['original_member_row']
    body = proof['actual_body_row']
    owners = proof['native_origin_per_triangle']
    if len(owners) != len(row['triangles']) or len(original_ideal) != len(old['normals']):
        raise ValueError('Incorrect complete field inventory')
    maximum = {'position_m': 0.0, 'UV': 0.0, 'direct_encoding_deg': 0.0, 'retained_whole_field_cone_deg': 0.0}
    groups = defaultdict(list)
    foot = []
    positive = 0
    native_corners = 0
    for fi, (ids, ls, owner) in enumerate(zip(row['triangles'], row['triangle_loops'], owners)):
        if owner == 0:
            raise ValueError('Missing face owner')
        ref = old if owner > 0 else body
        ri = abs(owner) - 1
        if not 0 <= ri < len(ref['triangles']):
            raise ValueError('Face owner outside complete reference inventory')
        ps = [ref['vertices'][v] for v in ref['triangles'][ri]]
        ref_loops = ref['triangle_loops'][ri]
        actual = [row['vertices'][v] for v in ids]
        ds = [distance2(vector(p), ps) for p in actual]
        if max(ds) > F(1e-06) ** 2:
            raise ValueError(('Full face outside reference', fi, owner))
        maximum['position_m'] = max(maximum['position_m'], math.sqrt(float(max(ds))))
        ng = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
        if owner > 0:
            original_targets = [original_ideal[i] for i in ref_loops]
            if any((angle(original_targets[0], n) > 1e-09 for n in original_targets[1:])):
                raise ValueError('Input member is not the declared constant-facet target')
            target = original_targets[0]
            positive += 1
        else:
            target = [-v for v in ng]
            foot.append(fi)
        geometric = cross(sub(actual[1], actual[0]), sub(actual[2], actual[0]))
        if dot(geometric, target) <= 0:
            raise ValueError('Native face has reversed owner orientation')
        e = unit(sub(ps[1], ps[0]))
        v = cross(target, e)
        weights = [bary(p, ps) for p in actual]
        if owner > 0:
            groups[ri].append((fi, weights))
        for p, w, li in zip(actual, weights, ls):
            n = row['normals'][li]
            if not all((math.isfinite(q) for q in n)) or abs(math.hypot(*n) - 1) > 1e-06:
                raise ValueError('Invalid native normal')
            error = angle(n, target)
            if error > 0.025:
                raise ValueError(('Direct target encoding bound failed', fi, li, error))
            maximum['direct_encoding_deg'] = max(maximum['direct_encoding_deg'], error)
            native_corners += 1
            if owner > 0:
                for oi in ref_loops:
                    error = angle(n, old['normals'][oi])
                    if error > 0.025:
                        raise ValueError(('Whole original facet normal cone changed', fi, ri, error))
                    maximum['retained_whole_field_cone_deg'] = max(maximum['retained_whole_field_cone_deg'], error)
            for name, uvs in row['uvs'].items():
                ideal = [sum((float(t) * ref['uvs'][name][oi][k] for t, oi in zip(w, ref_loops))) for k in range(2)] if owner > 0 else [dot(sub(p, ps[0]), e) / 0.25, dot(sub(p, ps[0]), v) / 0.25]
                error = max((abs(a - b) for a, b in zip(uvs[li], ideal)))
                if error > 1e-05:
                    raise ValueError(('Complete affine native UV bound failed', fi, li, error))
                maximum['UV'] = max(maximum['UV'], error)
        if row['triangle_materials'][fi] != (old['triangle_materials'][ri] if owner > 0 else 0):
            raise ValueError('Member/foot material assignment changed')
    if row['materials'] != old['materials']:
        raise ValueError('Member material resources changed')
    upper = []
    worst = F(0)
    plane = F(1.011)
    for oi, tri in enumerate(old['triangles']):
        ps = [old['vertices'][v] for v in tri]
        poly = clip(IDENTITY, [F(p[2]) - plane for p in ps])
        if not poly or signed_area(poly) == 0:
            continue
        matches = groups.get(oi, [])
        if not matches:
            raise ValueError(('Complete upper member face lost', oi))
        remaining = [poly]
        for fi, w in matches:
            remaining = [q for p in remaining for q in remove(p, w)]
            if not remaining:
                break
        fragments = []
        for fragment in remaining:
            points = [[sum((w[k] * F(ps[k][c]) for k in range(3))) for c in range(3)] for w in fragment]
            distance, owner = min(((max((distance2(p, [row['vertices'][v] for v in row['triangles'][fi]]) for p in points)), fi) for fi, w in matches))
            if distance > F(1e-06) ** 2:
                raise ValueError(('Whole upper member domain uncovered', oi, math.sqrt(float(distance))))
            worst = max(worst, distance)
            fragments.append({'native_triangle': owner, 'maximum_distance_squared_m': str(distance), 'original_barycentric': [[str(v) for v in w] for w in fragment]})
        upper.append({'original_triangle': oi, 'native_pieces': [i for i, w in matches], 'complete_original_upper_barycentric': [[str(v) for v in w] for w in poly], 'rounding_remainders': fragments})
    if not upper or not foot:
        raise ValueError('Incomplete upper/foot semantic inventory')
    if max((row['vertices'][v][2] for i in foot for v in row['triangles'][i])) >= 1.011:
        raise ValueError('Authored foot extends into fixed upper member')
    return {'status': 'passed', 'native_corners': native_corners, 'retained_output_faces': positive, 'new_foot_faces': len(foot), 'maximum': maximum, 'whole_upper_original_faces': len(upper), 'upper_plane_m': 1.011, 'upper_coverage': upper, 'maximum_upper_rounding_remainder_distance_m': math.sqrt(float(worst)), 'method': 'Complete native triangle ownership by convex distance; all affine UV extrema at triangle corners; direct encoding against immediate original ideal targets. Every pair of old/new native corner normals in each constant-facet owner is inside the unchanged .025-degree cone, bounding all normalized interior interpolants without adding stage errors. Exact barycentric upper-domain subtraction includes long incident faces; each remaining convex fragment is bounded to a complete native face.', 'limitation': 'The authored low foot is below Z1.011m. This is full retained-output field and complete upper-domain coverage, not a claim that removed low member surfaces are retained.'}
