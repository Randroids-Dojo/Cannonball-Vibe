"""Complete piecewise-planar width certificate for the proposed body receiver.

Projected patches must cover the rectangle exactly once. Parallel section
length is affine between every polygon-vertex event, so its maximum occurs
at a retained event. This measures actual surface arc, not XY width.
"""
from fractions import Fraction as F
import math
from .boundary02 import sub, dot, cross, unit

def area(poly):
    return sum((a[0] * b[1] - a[1] * b[0] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2 if len(poly) >= 3 else F(0)

def clip(poly, axis, value, greater):
    out = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        da = (a[axis] - value) * (1 if greater else -1)
        db = (b[axis] - value) * (1 if greater else -1)
        if da >= 0:
            out.append(a)
        if da * db < 0:
            t = da / (da - db)
            out.append(tuple((a[k] + t * (b[k] - a[k]) for k in range(2))))
    return list(dict.fromkeys(out))

def polygon_clip(poly, boundary):
    for x, y in zip(boundary, boundary[1:] + boundary[:1]):
        out = []
        e = sub(y, x)
        for a, b in zip(poly, poly[1:] + poly[:1]):
            da = cross((*e, 0), (*sub(a, x), 0))[2]
            db = cross((*e, 0), (*sub(b, x), 0))[2]
            if da >= 0:
                out.append(a)
            if da * db < 0:
                t = da / (da - db)
                out.append(tuple((a[k] + t * (b[k] - a[k]) for k in range(2))))
        poly = list(dict.fromkeys(out))
        if len(poly) < 3:
            return []
    return poly

def chart(body, plan, inside=0.009, outside=0.0075, ends=0.005):
    a = list(map(F, plan['seed_a']))
    b = list(map(F, plan['seed_b']))
    d = list(map(F, unit([float(b[k] - a[k]) if k < 2 else 0.0 for k in range(3)])))
    q = list(map(F, plan['toward_C_xy']))
    length = F(math.hypot(float(b[0] - a[0]), float(b[1] - a[1])))
    bounds = (-F(ends), length + F(ends), -F(outside), F(inside))
    polys = []

    def xy(p):
        return (dot(sub(p, a), d), dot(sub(p, a), q))
    for fi, tri in enumerate(body['triangles']):
        ps = [list(map(F, body['vertices'][v])) for v in tri]
        if min((p[2] for p in ps)) < F(0.9):
            continue
        normal = cross(sub(ps[1], ps[0]), sub(ps[2], ps[0]))
        if normal[2] <= 0:
            continue
        uv = [xy(p) for p in ps]
        if area(uv) < 0:
            uv.reverse()
        if any((max((p[k] for p in uv)) < lo or min((p[k] for p in uv)) > hi for k, lo, hi in ((0, bounds[0], bounds[1]), (1, bounds[2], bounds[3])))):
            continue
        for k, value, gt in ((0, bounds[0], True), (0, bounds[1], False), (1, bounds[2], True), (1, bounds[3], False)):
            uv = clip(uv, k, value, gt)
        if len(uv) < 3 or area(uv) == 0:
            continue
        polys.append({'triangle': fi, 'poly': uv, 'normal': normal, 'origin': ps[0]})
    overlaps = []
    for i, poly in enumerate(polys):
        for other in polys[i + 1:]:
            overlap = polygon_clip(poly['poly'], other['poly'])
            if area(overlap) > 0:
                overlaps.append([poly['triangle'], other['triangle'], str(area(overlap))])
    expected = (bounds[1] - bounds[0]) * (bounds[3] - bounds[2])
    total = sum((area(r['poly']) for r in polys))
    if overlaps or total != expected:
        raise ValueError(('Actual upper chart is not a complete single cover', overlaps, str(total - expected)))
    determinant = d[0] * q[1] - d[1] * q[0]

    def source(u, v, row):
        x = a[0] + (u * q[1] - d[1] * v) / determinant
        y = a[1] + (d[0] * v - u * q[0]) / determinant
        n = row['normal']
        p = row['origin']
        z = p[2] - (n[0] * (x - p[0]) + n[1] * (y - p[1])) / n[2]
        return (x, y, z)
    events = sorted({p[0] for r in polys for p in r['poly']})
    samples = []
    for event in events:
        sections = []
        for r in polys:
            hits = []
            for a1, b1 in zip(r['poly'], r['poly'][1:] + r['poly'][:1]):
                if a1[0] == event:
                    hits.append(a1[1])
                if a1[0] < event < b1[0] or b1[0] < event < a1[0]:
                    hits.append(a1[1] + (event - a1[0]) / (b1[0] - a1[0]) * (b1[1] - a1[1]))
            if len(set(hits)) < 2:
                continue
            lo, hi = (min(hits), max(hits))
            if lo < hi:
                sections.append((lo, hi, r))
        unique = {}
        for lo, hi, r in sections:
            p0, p1 = (source(event, lo, r), source(event, hi, r))
            key = (lo, hi, p0, p1)
            unique[key] = (lo, hi, p0, p1, r['triangle'])
        intervals = sorted(unique.values())
        cursor = bounds[2]
        distance = 0.0
        used = []
        for lo, hi, p0, p1, fi in intervals:
            if lo < cursor:
                if hi <= cursor:
                    continue
                raise ValueError('Partial duplicate section interval')
            if lo != cursor:
                raise ValueError('Section coverage gap')
            value = sum(((x - y) ** 2 for x, y in zip(p0, p1)))
            length_bound = math.nextafter(math.sqrt(float(value)), math.inf)
            distance = math.nextafter(distance + length_bound, math.inf)
            cursor = hi
            used.append({'triangle': fi, 'v_interval': [str(lo), str(hi)], 'arc_bound_m': length_bound})
        if cursor != bounds[3]:
            raise ValueError('Incomplete finite parallel section')
        samples.append({'u_m': float(event), 'arc_upper_m': distance, 'pieces': used})
    return {'proposed_xy_width_m': inside + outside, 'proposed_inside_xy_m': inside, 'proposed_outside_xy_m': outside, 'end_extension_xy_m': ends, 'actual_triangles': [r['triangle'] for r in polys], 'complete_single_chart_exact_area': str(expected), 'no_positive_area_projection_overlaps': True, 'complete_max_surface_arc_upper_m': max((r['arc_upper_m'] for r in samples)), 'critical_sections': samples, 'method': 'Exact dyadic clipped single-cover chart. Complete parallel-section arc maximum is at polygon-vertex U events, because each contributing planar interval length is affine between events. Each square root and total are rounded upward in binary64.'}
