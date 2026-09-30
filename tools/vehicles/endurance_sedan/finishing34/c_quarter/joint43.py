"""Complete actual C end-wall/quarter seat and retained negative geometry."""
from fractions import Fraction as F
import copy, gzip, hashlib, json, math
from endurance_sedan.qa.exact_triangles import intersection, vector, sub, dot, cross, add, scale

def distance2(p, triangle):
    a, b, c = map(vector, triangle)
    v = sub(b, a)
    w = sub(c, a)
    n = cross(v, w)
    n2 = dot(n, n)
    if n2 == 0:
        raise ValueError('Degenerate native joint triangle')
    error = dot(sub(p, a), n)
    projected = sub(p, scale(n, error / n2))
    q = sub(projected, a)
    wb = dot(cross(q, w), n) / n2
    wc = dot(cross(v, q), n) / n2
    if min(1 - wb - wc, wb, wc) >= 0:
        return error * error / n2
    answers = []
    for x, y in ((a, b), (b, c), (c, a)):
        d = sub(y, x)
        t = min(F(1), max(F(0), dot(sub(p, x), d) / dot(d, d)))
        q = sub(p, add(x, scale(d, t)))
        answers.append(dot(q, q))
    return min(answers)

def validate(skin, body, contacts):
    row = skin['row']
    proof = skin['proof']
    nu = len(proof['u_knots'])
    nv = len(proof['s_knots'])
    layer = nu * nv
    outer = set(range((nv - 1) * nu, nv * nu))
    inner = {i + layer for i in outer}
    allids = outer | inner
    seat = {fi: [row['vertices'][v] for v in t] for fi, t in enumerate(row['triangles']) if set(t) <= allids and set(t) & outer and set(t) & inner}
    if len(seat) != 2 * (nu - 1):
        raise ValueError('Actual C end-wall inventory differs')
    key = lambda points: tuple(sorted((tuple(p) for p in points)))
    lookup = {}
    for i, t in enumerate(body['triangles']):
        lookup.setdefault(key([body['vertices'][v] for v in t]), []).append(i)
    area2 = 0.0
    matched = []
    for fi, points in seat.items():
        found = lookup.get(key(points), [])
        if len(found) != 1:
            raise ValueError(('Complete native end-wall footprint missing or duplicated', fi, found))
        bi = found[0]
        other = [body['vertices'][v] for v in body['triangles'][bi]]
        a, b, c = map(vector, points)
        n = cross(sub(b, a), sub(c, a))
        x, y, z = map(vector, other)
        nn = cross(sub(y, x), sub(z, x))
        if dot(n, nn) >= 0:
            raise ValueError('Native end-wall solids have matching rather than opposing orientation')
        value = math.nextafter(math.sqrt(float(dot(n, n))), math.inf) / 2
        area2 += value
        matched.append({'C_face': fi, 'body_face': bi, 'area_m2': value, 'native_positions_exact': True, 'opposing_orientation_exact': True})
    if contacts['native_three_ray_inside_vertices']:
        raise ValueError('Actual source vertex is inside opposing solid')
    guard2 = F(1e-06) ** 2
    worst = F(0)
    domains = []
    for hit in contacts['intersection_pairs']:
        ai, bi = (hit['a'], hit['b'])
        a = [row['vertices'][v] for v in row['triangles'][ai]]
        b = [body['vertices'][v] for v in body['triangles'][bi]]
        points = intersection(a, b)
        if not points:
            raise ValueError('Retained actual contact no longer exists')
        choices = [(max((distance2(p, tri) for p in points)), fi) for fi, tri in seat.items()]
        distance, owner = min(choices)
        if distance > guard2:
            raise ValueError(('Actual complete triangle contact escapes the finite seat', ai, bi, math.sqrt(float(distance))))
        worst = max(worst, distance)
        domains.append({'C_face': ai, 'body_face': bi, 'complete_contact_owner_C_face': owner, 'maximum_distance_squared': str(distance)})
    return {'status': 'passed', 'complete_native_matched_faces': matched, 'complete_mating_area_upper_m2': area2, 'all_contact_pairs': len(domains), 'maximum_complete_contact_distance_m': math.nextafter(math.sqrt(float(worst)), math.inf), 'contact_domains': domains, 'native_inside_vertices': 0, 'method': 'Exact dyadic full triangle intersections rederived from candidate geometry. Every complete convex contact polygon lies inside one actual end-wall triangle plus the unchanged1um guard. Full native end-wall triangle sets match with opposite orientation; closed/exact-self source controls are separately bound.'}
