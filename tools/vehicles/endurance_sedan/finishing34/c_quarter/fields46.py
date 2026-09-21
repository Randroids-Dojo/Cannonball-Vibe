"""Direct complete retained fields and new-target encoding; no scene mutation."""
from fractions import Fraction as F
import math
from .boundary02 import sub, dot, cross, unit, angle
from .fragment04 import clip
from .strip23 import area, polygon_clip
from .outside_field05 import angular_bound
SIN_LIMIT = F(43633229, 10 ** 11)

def whole_angle(a, b):
    if len(a) != 3 or len(b) != 3 or any((len(v) != 3 or not all((math.isfinite(x) for x in v)) or math.hypot(*v) <= 1e-12 for v in a + b)):
        raise ValueError('Malformed finite normal field')
    actual = [angle(x, y) for x, y in zip(a, b)]
    if max(actual) > 0.025:
        raise ValueError(('Direct corner field differs', max(actual)))
    af = [list(map(F, n)) for n in a]
    bf = [list(map(F, n)) for n in b]
    v = [sum((n[k] for n in af)) for k in range(3)]
    v2 = dot(v, v)
    minimum = min((dot(n, v) for n in af))
    e2 = max((dot(sub(x, y), sub(x, y)) for x, y in zip(af, bf)))
    if minimum > 0 and e2 * v2 <= SIN_LIMIT * SIN_LIMIT * minimum * minimum:
        bound = math.degrees(math.asin(math.sqrt(float(e2 * v2 / (minimum * minimum)))))
        return {'complete': True, 'angle_upper_deg': math.nextafter(bound, math.inf), 'method': 'Exact rational affine-vector error ball divided by a separating-axis lower bound on the full original-vector norm.'}
    if angle([sum((n[k] for n in a)) for k in range(3)], [sum((n[k] for n in b)) for k in range(3)]) > 0.025:
        raise ValueError('Interior field counterexample')
    out = angular_bound(a, b)
    if not out['complete']:
        raise ValueError(('Whole field unresolved', out))
    return {'complete': True, 'angle_upper_deg': out['maximum_accepted_angle_bound_deg'], 'method': 'Exact Bernstein cross/dot subdivision', 'details': out}

def face(old, new, owner, weights, face_index):
    if type(owner) is not int or not 0 <= owner < len(old['triangles']):
        raise ValueError('Invalid original owner')
    if len(weights) != 3 or any((len(w) != 3 for w in weights)):
        raise ValueError('Malformed exact barycentric map')
    ws = [[F(x) for x in w] for w in weights]
    if any((sum(w) != 1 or min(w) < 0 for w in ws)) or area([(w[1], w[2]) for w in ws]) <= 0:
        raise ValueError('Invalid oriented original simplex map')
    original = old['triangles'][owner]
    old_loops = old['triangle_loops'][owner]
    new_loops = new['triangle_loops'][face_index]
    tri = new['triangles'][face_index]
    if len(tri) != 3 or len(new_loops) != 3:
        raise ValueError('Expected native triangular output')
    if old['triangle_materials'][owner] != new['triangle_materials'][face_index]:
        raise ValueError('Changed retained material')
    expected = [[sum((w[j] * F(old['vertices'][original[j]][k]) for j in range(3))) for k in range(3)] for w in ws]
    distances = [math.sqrt(float(sum(((F(new['vertices'][v][k]) - p[k]) ** 2 for k in range(3))))) for v, p in zip(tri, expected)]
    if max(distances) > 1e-06:
        raise ValueError(('Retained position field changed', max(distances)))
    uv = 0.0
    for name in old['uvs']:
        for loop, w in zip(new_loops, ws):
            for k in range(2):
                value = sum((w[j] * F(old['uvs'][name][old_loops[j]][k]) for j in range(3)))
                error = abs(F(new['uvs'][name][loop][k]) - value)
                uv = max(uv, float(error))
    if uv > 1e-05:
        raise ValueError(('Retained UV field changed', uv))
    a = [[sum((float(w[j]) * old['normals'][old_loops[j]][k] for j in range(3))) for k in range(3)] for w in ws]
    normals = [new['normals'][l] for l in new_loops]
    field = whole_angle(a, normals)
    return {'position_upper_m': max(distances), 'uv_component_upper': uv, 'normal': field, 'source_barycentric_area': str(area([(w[1], w[2]) for w in ws]))}

def validate(payload, plans):
    old = payload['original']
    new = payload['candidate']
    proof = payload['proof']
    owners = proof['original_triangle_owners']
    maps = proof['original_barycentric_correspondence']
    count = len(new['triangles'])
    if len(owners) != count or len(maps) != count or len(new['triangle_loops']) != count or (len(new['triangle_materials']) != count):
        raise ValueError('Output face inventory differs')
    if old['materials'] != new['materials'] or set(old['uvs']) != set(new['uvs']):
        raise ValueError('Output material/UV schema changed')
    records = []
    by_owner = {}
    new_fields = []
    for i, (owner, w) in enumerate(zip(owners, maps)):
        if owner is not None:
            record = face(old, new, owner, w, i)
            records.append({'face': i, 'owner': owner, **record})
            by_owner.setdefault(owner, []).append([[F(x) for x in z] for z in w])
        else:
            if w is not None:
                raise ValueError('Authored face masquerades as old correspondence')
            ls = new['triangle_loops'][i]
            new_fields.append({'face': i, **whole_angle([proof['ideal_targets'][l] for l in ls], [new['normals'][l] for l in ls])})
    identity = [[F(1), F(0), F(0)], [F(0), F(1), F(0)], [F(0), F(0), F(1)]]
    owned = {}
    for side, p in plans.items():
        a = list(map(F, p['seed_a']))
        b = list(map(F, p['seed_b']))
        d = list(map(F, unit([float(b[k] - a[k]) if k < 2 else 0.0 for k in range(3)])))
        q = list(map(F, p['toward_C_xy']))
        length = F(math.hypot(float(b[0] - a[0]), float(b[1] - a[1])))
        limits = (-F(0.0045), length + F(0.0045), -F(0.007), F(0.0085))
        for fi in proof['patches'][side]['original_triangles']:
            values = []
            for v in old['triangles'][fi]:
                point = list(map(F, old['vertices'][v]))
                u = dot(sub(point, a), d)
                v1 = dot(sub(point, a), q)
                values.append([u - limits[0], limits[1] - u, v1 - limits[2], limits[3] - v1])
            poly = identity
            for k in range(4):
                poly = clip(poly, [v[k] for v in values])
            if len(poly) < 3 or area([(w[1], w[2]) for w in poly]) <= 0:
                raise ValueError('Incorrect authored original-face domain')
            owned[fi] = [(w[1], w[2]) for w in poly]
    coverage = []
    for fi in range(len(old['triangles'])):
        pieces = [[(w[1], w[2]) for w in p] for p in by_owner.get(fi, [])]
        expected = F(1, 2) - area(owned.get(fi, []))
        if sum((area(p) for p in pieces)) != expected:
            raise ValueError(('Complete outside source coverage differs', fi))
        for i, p in enumerate(pieces):
            if fi in owned and area(polygon_clip(p, owned[fi])) > 0:
                raise ValueError('Retained fragment covers authored domain')
            for q in pieces[i + 1:]:
                if area(polygon_clip(p, q)) > 0:
                    raise ValueError('Repeated retained source coverage')
        if fi in owned:
            coverage.append({'original_triangle': fi, 'complete_outside_area': str(expected), 'fragments': len(pieces)})
    return {'status': 'passed', 'retained_faces': len(records), 'authored_faces': len(new_fields), 'complete_original_faces_accounted': len(old['triangles']), 'maximum_position_upper_m': max((r['position_upper_m'] for r in records)), 'maximum_uv_component_upper': max((r['uv_component_upper'] for r in records)), 'maximum_complete_old_vs_native_normal_deg': max((r['normal']['angle_upper_deg'] for r in records)), 'maximum_complete_new_target_vs_native_normal_deg': max((r['angle_upper_deg'] for r in new_fields)), 'coverage': coverage, 'retained_field_records': records, 'new_target_records': new_fields}
