"""All-triangle cloth self-contact, including coplanar and indexed seam cases.

Adapted from the retained candidate10 rejection/candidate11 positive control.
This module reads only supplied evaluated triangles and has no file side effects.
"""
import itertools
import math

EPS = 1e-9
GUARD = 1e-6


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def add(a, b):
    return tuple(x+y for x, y in zip(a, b))


def scale(a, factor):
    return tuple(x*factor for x in a)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def normal(tri):
    value = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
    length = norm(value)
    if not length > 0:
        raise ValueError('Degenerate cloth triangle')
    return scale(value, 1/length)


def plane_section(tri, origin, n):
    values = [dot(sub(p, origin), n) for p in tri]
    points = [p for p, value in zip(tri, values) if abs(value) <= EPS]
    for i in range(3):
        j = (i+1) % 3
        if values[i]*values[j] < 0:
            t = values[i]/(values[i]-values[j])
            points.append(add(tri[i], scale(sub(tri[j], tri[i]), t)))
    return points


def triangle_intersection(a, b):
    na, nb = normal(a), normal(b)
    da = [dot(sub(p, b[0]), nb) for p in a]
    db = [dot(sub(p, a[0]), na) for p in b]
    if min(da) > EPS or max(da) < -EPS or min(db) > EPS or max(db) < -EPS:
        return []
    direction = cross(na, nb)
    length = norm(direction)
    if length <= 1e-10:
        if max(abs(v) for v in da) > EPS:
            return []
        polygon = list(a)
        for i in range(3):
            p, q, inside = b[i], b[(i+1) % 3], b[(i+2) % 3]
            edge_normal = cross(sub(q, p), nb)
            if dot(sub(inside, p), edge_normal) < 0:
                edge_normal = scale(edge_normal, -1)
            edge_normal = scale(edge_normal, 1/norm(edge_normal))
            clipped = []
            if not polygon:
                break
            for start, end in zip(polygon, polygon[1:]+polygon[:1]):
                ds, de = dot(sub(start, p), edge_normal), dot(sub(end, p), edge_normal)
                if ds >= -EPS:
                    clipped.append(start)
                if (ds < -EPS) != (de < -EPS):
                    t = ds/(ds-de)
                    clipped.append(add(start, scale(sub(end, start), t)))
            polygon = clipped
        return polygon
    direction = scale(direction, 1/length)
    pa, pb = plane_section(a, b[0], nb), plane_section(b, a[0], na)
    if not pa or not pb:
        return []
    alo, ahi = min(dot(p, direction) for p in pa), max(dot(p, direction) for p in pa)
    blo, bhi = min(dot(p, direction) for p in pb), max(dot(p, direction) for p in pb)
    lo, hi = max(alo, blo), min(ahi, bhi)
    if lo > hi + EPS:
        return []
    origin = pa[0]
    reference = dot(origin, direction)
    return [add(origin, scale(direction, t-reference)) for t in (lo, hi)]


def distance_shared(point, vertices):
    if not vertices or len(vertices) > 2:
        return math.inf  # Repeated triangles cannot become an allowed seam.
    if len(vertices) == 1:
        return norm(sub(point, vertices[0]))
    a, b = vertices
    delta = sub(b, a)
    length2 = dot(delta, delta)
    if not length2 > 0:
        return norm(sub(point, a))
    t = min(1., max(0., dot(sub(point, a), delta)/length2))
    return norm(sub(point, add(a, scale(delta, t))))


def inspect(row):
    bad, candidates, total = [], 0, 0
    for ai, bi in itertools.combinations(range(len(row['triangles'])), 2):
        total += 1
        ia, ib = row['triangles'][ai], row['triangles'][bi]
        a, b = [row['vertices'][i] for i in ia], [row['vertices'][i] for i in ib]
        if any(max(p[k] for p in a) < min(p[k] for p in b)-EPS
               or max(p[k] for p in b) < min(p[k] for p in a)-EPS for k in range(3)):
            continue
        candidates += 1
        points = triangle_intersection(a, b)
        shared = [row['vertices'][i] for i in set(ia) & set(ib)]
        outside = [p for p in points if distance_shared(p, shared) > GUARD]
        if outside:
            bad.append({'triangles': [ai, bi], 'shared_indices': sorted(set(ia) & set(ib)),
                        'full_intersection_points': points, 'outside_shared_simplex': outside})
    return {'name': row['name'], 'all_triangle_pairs': total, 'aabb_refined_pairs': candidates,
            'unrelated_intersections': bad, 'status': 'passed' if not bad else 'failed'}
