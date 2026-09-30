"""Current-source exact lower-boundary and permitted-strip planning; no bpy/I/O imports in functions."""
from fractions import Fraction as F
import math

def sub(a, b):
    return [x - y for x, y in zip(a, b)]

def dot(a, b):
    return sum((x * y for x, y in zip(a, b)))

def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

def unit(a):
    return [x / math.hypot(*a) for x in a]

def angle(a, b):
    return math.degrees(math.atan2(math.hypot(*cross(a, b)), dot(a, b)))

def turn(a, b):
    return a[0] * b[1] - a[1] * b[0]

def line_chart(body, a, b):
    af, bf = [list(map(F, p)) for p in (a, b)]
    d = sub(bf, af)
    found = []
    for ti, ids in enumerate(body['triangles']):
        raw = [body['vertices'][v] for v in ids]
        if any((max((p[k] for p in raw)) < min(a[k], b[k]) or min((p[k] for p in raw)) > max(a[k], b[k]) for k in (0, 1))):
            continue
        ps = [list(map(F, p)) for p in raw]
        v, w = (sub(ps[1], ps[0]), sub(ps[2], ps[0]))
        n = cross(v, w)
        if n[2] <= 0:
            continue
        det = turn(v, w)
        q = sub(af, ps[0])
        va = turn(q, w) / det
        vb = turn(d, w) / det
        wa = turn(v, q) / det
        wb = turn(v, d) / det
        bary0 = [1 - va - wa, va, wa]
        bary1 = [-vb - wb, vb, wb]
        lo, hi = (F(0), F(1))
        for c, e in zip(bary0, bary1):
            if e == 0:
                if c < 0:
                    lo, hi = (F(1), F(0))
                    break
            elif e > 0:
                lo = max(lo, -c / e)
            else:
                hi = min(hi, -c / e)
        if lo >= hi:
            continue
        found.append(dict(triangle=ti, lo=lo, hi=hi, h0=sum((c * p[2] for c, p in zip(bary0, ps))), h1=sum((c * p[2] for c, p in zip(bary1, ps))), normal=n, bary0=bary0, bary1=bary1))
    knots = {F(0), F(1), *[v for r in found for v in (r['lo'], r['hi'])]}
    for i, a1 in enumerate(found):
        for b1 in found[i + 1:]:
            if a1['h1'] == b1['h1']:
                continue
            t = (b1['h0'] - a1['h0']) / (a1['h1'] - b1['h1'])
            if max(a1['lo'], b1['lo']) < t < min(a1['hi'], b1['hi']):
                knots.add(t)
    knots = sorted(knots)
    spans = []
    for lo, hi in zip(knots, knots[1:]):
        t = (lo + hi) / 2
        owners = [r for r in found if r['lo'] <= t <= r['hi']]
        if not owners:
            raise ValueError(('Uncovered actual upper-body interval', a, b, str(lo), str(hi)))
        h = max((r['h0'] + r['h1'] * t for r in owners))
        owners = [r for r in owners if r['h0'] + r['h1'] * t == h]
        r = owners[0]
        if any(((o['h0'], o['h1']) != (r['h0'], r['h1']) for o in owners)):
            raise ValueError('Ambiguous exact upper chart')
        ends = []
        fields = []
        for q in (lo, hi):
            ends.append([af[0] + d[0] * q, af[1] + d[1] * q, r['h0'] + r['h1'] * q])
            weights = [float(c + e * q) for c, e in zip(r['bary0'], r['bary1'])]
            ns = [body['normals'][l] for l in body['triangle_loops'][r['triangle']]]
            fields.append(unit([sum((w * n[k] for w, n in zip(weights, ns))) for k in range(3)]))
        spans.append({'parameter': [str(lo), str(hi)], 'owner_triangles': [o['triangle'] for o in owners], 'points': [[float(c) for c in p] for p in ends], 'exact_points': [[str(c) for c in p] for p in ends], 'geometry_normal': unit([float(x) for x in r['normal']]), 'native_normal_ends': fields})
    return spans

def section(row, y):
    """Every oriented triangle intersection at one source-coordinate plane."""
    answer = []
    for fi, (tri, loops) in enumerate(zip(row['triangles'], row['triangle_loops'])):
        ps = [row['vertices'][v] for v in tri]
        hits = []
        for i in range(3):
            a, b = (ps[i], ps[(i + 1) % 3])
            if a[1] == y:
                hits.append((list(a), list(row['normals'][loops[i]])))
            if a[1] < y < b[1] or b[1] < y < a[1]:
                t = (y - a[1]) / (b[1] - a[1])
                p = [a[k] + t * (b[k] - a[k]) for k in range(3)]
                p[1] = y
                n = unit([row['normals'][loops[i]][k] * (1 - t) + row['normals'][loops[(i + 1) % 3]][k] * t for k in range(3)])
                hits.append((p, n))
        uniq = {tuple(p): (p, n) for p, n in hits}
        if len(uniq) == 2:
            q = list(uniq.values())
            g = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
            answer.append({'triangle': fi, 'points': [r[0] for r in q], 'field': [r[1] for r in q], 'geometry_normal': g})
    return answer

def plan(rows):
    body = rows['LOD0_StructuralBody']
    seal = rows['LOD0_BacklightSeal']
    report = {}
    for side in ('L', 'R'):
        sign = -1 if side == 'L' else 1
        frame = rows['LOD0_DoorFrame_R' + side]
        a = [sign * (max((abs(p[0]) for p in seal['vertices'])) + 0.002), min((p[1] for p in seal['vertices'])) - 0.004, 0.0]
        b = [sign * (max((abs(p[0]) for p in frame['vertices'])) + 0.008), min((p[1] for p in frame['vertices'])) - 0.112, 0.0]
        spans = line_chart(body, a, b)
        a = spans[0]['points'][0]
        b = spans[-1]['points'][1]
        d = unit([b[0] - a[0], b[1] - a[1], 0.0])
        q = [-d[1], d[0], 0.0]
        if dot(q, sub([0.0, -1.2, 1.35], a)) < 0:
            q = [-v for v in q]
        owners = sorted({ti for s in spans for ti in s['owner_triangles']})
        triangles = []
        for ti in owners:
            ps = [body['vertices'][v] for v in body['triangles'][ti]]
            triangles.append({'triangle': ti, 'vertices': body['triangles'][ti], 'points': ps, 'outward_distances_m': [-dot(sub(p, a), q) for p in ps], 'maximum_edge_m': max((math.dist(x, y) for x, y in zip(ps, ps[1:] + ps[:1])))})
        jumps = [{'at': b1['points'][0], 'geometry_deg': angle(a1['geometry_normal'], b1['geometry_normal']), 'native_deg': angle(a1['native_normal_ends'][1], b1['native_normal_ends'][0])} for a1, b1 in zip(spans, spans[1:])]
        offsets = []
        for width in (0.015, 0.0175, 0.02):
            aa = [a[k] - width * q[k] for k in range(3)]
            bb = [b[k] - width * q[k] for k in range(3)]
            try:
                cut = line_chart(body, aa, bb)
                offsets.append({'xy_width_m': width, 'spans': cut, 'status': 'complete'})
            except ValueError as error:
                offsets.append({'xy_width_m': width, 'status': 'uncovered', 'error': str(error)})
        report[side] = {'seed_a': a, 'seed_b': b, 'toward_C_xy': q, 'spans': spans, 'jumps': jumps, 'original_crossed_triangles': triangles, 'offset_curves': offsets, 'upper_sections': {str(y): {n: section(rows[n], y) for n in ('LOD0_StampedPillar_C' + side, 'LOD0_RoofSideRail_' + side, 'LOD0_Roof', 'LOD0_DoorFrame_R' + side, 'LOD0_BacklightSeal')} for y in (-1.23, -1.25, -1.269, -1.29, -1.31)}}
    return report
