"""Complete affine-vector angular comparison on one finite parameter triangle."""
from fractions import Fraction as F
import math

def dot(a, b):
    return sum((x * y for x, y in zip(a, b)))

def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

def affine(values, w):
    return [sum((w[i] * values[i][k] for i in range(3))) for k in range(3)]

def angular_bound(original, candidate, max_depth=18):
    """Dyadic exact Bernstein cross/dot certificate, threshold strictly below .025deg.

    Cross(A,B) and dot(A,B) have six quadratic barycentric Bernstein controls.
    Every A and B inside the parameter triangle uses the same barycentric point.
    Their cross lies in the convex hull of its controls; dot is >=minimum control.
    A rational0.0004363323 slope is less than tan(.025degrees). No sampled pass.
    """
    a = [[F(x) for x in v] for v in original]
    b = [[F(x) for x in v] for v in candidate]
    identity = [[F(1), F(0), F(0)], [F(0), F(1), F(0)], [F(0), F(0), F(1)]]
    threshold = F(4363323, 10000000000)
    limit2 = threshold * threshold
    stack = [(identity, 0)]
    leaves = 0
    split_count = 0
    deepest = 0
    maximum_accepted_slope2 = F(0)
    unresolved = []
    while stack:
        tri, depth = stack.pop()
        aa = [affine(a, w) for w in tri]
        bb = [affine(b, w) for w in tri]
        cs = [cross(x, y) for x, y in zip(aa, bb)]
        ds = [dot(x, y) for x, y in zip(aa, bb)]
        for i, j in ((0, 1), (1, 2), (2, 0)):
            ca, cb = (cross(aa[i], bb[j]), cross(aa[j], bb[i]))
            cs.append([(x + y) / 2 for x, y in zip(ca, cb)])
            ds.append((dot(aa[i], bb[j]) + dot(aa[j], bb[i])) / 2)
        dmin = min(ds)
        cmax2 = max((dot(c, c) for c in cs))
        deepest = max(deepest, depth)
        if dmin > 0 and cmax2 <= limit2 * dmin * dmin:
            maximum_accepted_slope2 = max(maximum_accepted_slope2, cmax2 / (dmin * dmin))
            leaves += 1
            continue
        if depth == max_depth:
            unresolved.append({'parameter_triangle': [[str(x) for x in p] for p in tri], 'depth': depth, 'dot_lower': str(dmin), 'cross_squared_upper': str(cmax2)})
            if len(unresolved) >= 8:
                break
            continue
        ab = [(x + y) / 2 for x, y in zip(tri[0], tri[1])]
        bc = [(x + y) / 2 for x, y in zip(tri[1], tri[2])]
        ca = [(x + y) / 2 for x, y in zip(tri[2], tri[0])]
        stack.extend(((t, depth + 1) for t in ([tri[0], ab, ca], [ab, tri[1], bc], [ca, bc, tri[2]], [ab, bc, ca])))
        split_count += 1
    complete = not stack and (not unresolved)
    return {'status': 'passed' if complete else 'unresolved', 'complete': complete, 'accepted_leaves': leaves, 'subdivisions': split_count, 'maximum_depth': deepest, 'maximum_accepted_angle_bound_deg': math.degrees(math.atan(math.sqrt(float(maximum_accepted_slope2)))), 'strict_rational_slope_limit': str(threshold), 'unresolved': unresolved, 'unvisited_parameter_triangles': len(stack)}
