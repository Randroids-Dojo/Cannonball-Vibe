"""Finite local-strip partition and explicit outside-field counterexample search."""
from fractions import Fraction as F
import math
from .boundary02 import dot, sub, cross, unit, angle

def clip(poly, values):
    out = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        da = dot(a, values)
        db = dot(b, values)
        if da >= 0:
            out.append(a)
        if da * db < 0:
            t = da / (da - db)
            out.append([a[k] + t * (b[k] - a[k]) for k in range(3)])
    result = []
    for p in out:
        if not result or p != result[-1]:
            result.append(p)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result

def split(body, planning, width=0.015):
    identity = [[F(1), F(0), F(0)], [F(0), F(1), F(0)], [F(0), F(0), F(1)]]
    answer = []
    for side, plan in planning.items():
        a = plan['seed_a']
        b = plan['seed_b']
        q = plan['toward_C_xy']
        d = unit([b[0] - a[0], b[1] - a[1], 0.0])
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        values = lambda p: [dot(sub(p, a), d), length - dot(sub(p, a), d), -dot(sub(p, a), q), width + dot(sub(p, a), q)]
        for fi, (ids, loops) in enumerate(zip(body['triangles'], body['triangle_loops'])):
            ps = [body['vertices'][v] for v in ids]
            n = cross(sub(ps[1], ps[0]), sub(ps[2], ps[0]))
            if min((p[2] for p in ps)) < 0.9 or n[2] <= 0:
                continue
            vals = [[F(v) for v in values(p)] for p in ps]
            if any((max((v[k] for v in vals)) < 0 for k in range(4))):
                continue
            pending = identity
            outside = []
            for k in range(4):
                ds = [v[k] for v in vals]
                piece = clip(pending, [-v for v in ds])
                if len(piece) >= 3:
                    outside.append(piece)
                pending = clip(pending, ds)
                if len(pending) < 3:
                    break
            if len(pending) < 3:
                continue
            cross2 = lambda p, q: p[0] * q[1] - p[1] * q[0]
            area = lambda poly: abs(sum((cross2([a[1], a[2]], [b[1], b[2]]) for a, b in zip(poly, poly[1:] + poly[:1])))) / 2
            expected = F(1, 2)
            total = area(pending) + sum((area(poly) for poly in outside))
            if total != expected:
                raise ValueError(('Partition does not cover original triangle exactly', fi, total))
            if area(pending) == 0:
                continue
            pieces = []
            ns = [body['normals'][l] for l in loops]
            for poly in outside:
                for j in range(1, len(poly) - 1):
                    tri = [poly[0], poly[j], poly[j + 1]]
                    if area(tri) == 0:
                        continue
                    pts = [[sum((float(w[k]) * ps[k][c] for k in range(3))) for c in range(3)] for w in tri]
                    new = [unit([sum((float(w[k]) * ns[k][c] for k in range(3))) for c in range(3)]) for w in tri]
                    worst = {'angle_deg': 0.0}
                    for x in range(17):
                        for y in range(17 - x):
                            local = [x / 16, y / 16, 1 - (x + y) / 16]
                            bary = [sum((local[k] * float(tri[k][c]) for k in range(3))) for c in range(3)]
                            old_n = unit([sum((bary[k] * ns[k][c] for k in range(3))) for c in range(3)])
                            new_n = unit([sum((local[k] * new[k][c] for k in range(3))) for c in range(3)])
                            err = angle(old_n, new_n)
                            if err > worst['angle_deg']:
                                worst = {'angle_deg': err, 'new_barycentric': local, 'old_barycentric': bary, 'original_field': old_n, 'new_field': new_n}
                    pieces.append({'original_barycentric': [[str(v) for v in w] for w in tri], 'points': pts, 'new_corner_targets': new, 'sampled_worst': worst})
            answer.append({'side': side, 'triangle': fi, 'inside_original_barycentric': [[str(v) for v in w] for w in pending], 'outside_pieces': pieces, 'complete_fraction_area': str(total), 'original_points': ps, 'original_normals': ns})
    return answer
