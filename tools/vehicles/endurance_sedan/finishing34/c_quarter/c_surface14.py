"""Private paired C-sheet boundary/control construction. No I/O/save/export/render.

This is a native shape trial, not an installed body receiver or accepted joint.
"""
import math
import bpy
from mathutils import Matrix
from .boundary02 import sub, dot, cross, unit, section

def hermite(a, b, da, db, t, h):
    return (2 * t * t * t - 3 * t * t + 1) * a + (t * t * t - 2 * t * t + t) * h * da + (-2 * t * t * t + 3 * t * t) * b + (t * t * t - t * t) * h * db

class Cubic:

    def __init__(self, pairs, start=None, end=None):
        self.x, self.v = zip(*sorted(pairs))
        n = len(self.x)
        hs = [self.x[i + 1] - self.x[i] for i in range(n - 1)]
        if any((h <= 0 for h in hs)):
            raise ValueError('Repeated surface control parameter')
        a = [0.0] * n
        b = [1.0] * n
        c = [0.0] * n
        d = [0.0] * n
        if start is not None:
            b[0] = 2 * hs[0]
            c[0] = hs[0]
            d[0] = 6 * ((self.v[1] - self.v[0]) / hs[0] - start)
        if end is not None:
            a[-1] = hs[-1]
            b[-1] = 2 * hs[-1]
            d[-1] = 6 * (end - (self.v[-1] - self.v[-2]) / hs[-1])
        for i in range(1, n - 1):
            a[i] = hs[i - 1]
            b[i] = 2 * (hs[i - 1] + hs[i])
            c[i] = hs[i]
            d[i] = 6 * ((self.v[i + 1] - self.v[i]) / hs[i] - (self.v[i] - self.v[i - 1]) / hs[i - 1])
        for i in range(1, n):
            w = a[i] / b[i - 1]
            b[i] -= w * c[i - 1]
            d[i] -= w * d[i - 1]
        self.m = [0.0] * n
        self.m[-1] = d[-1] / b[-1]
        for i in range(n - 2, -1, -1):
            self.m[i] = (d[i] - c[i] * self.m[i + 1]) / b[i]

    def __call__(self, x):
        k = next((i for i in range(len(self.x) - 1) if x <= self.x[i + 1]), len(self.x) - 2)
        h = self.x[k + 1] - self.x[k]
        a = (self.x[k + 1] - x) / h
        b = (x - self.x[k]) / h
        return a * self.v[k] + b * self.v[k + 1] + ((a * a * a - a) * self.m[k] + (b * b * b - b) * self.m[k + 1]) * h * h / 6

def frame_top(row, y):
    ss = section(row, y)
    if not ss:
        raise ValueError(('Actual frame has no section', y))
    return max((p for s in ss for p in s['points']), key=lambda p: p[2])

class Surface:

    def __init__(self, rows, plan, side):
        self.side = side
        self.sign = -1 if side == 'L' else 1
        self.plan = plan
        c = rows['LOD0_StampedPillar_C' + side]
        rail = rows['LOD0_RoofSideRail_' + side]
        roof = rows['LOD0_Roof']
        self.front = max((p[1] for p in c['vertices']))
        cap = [[self.sign * p[0], p[1], p[2]] for p in c['vertices'] if p[1] == self.front]
        ps = sorted((p for p in cap if p[0] > 0.685), key=lambda p: p[0])
        upper = []
        for p in ps:
            while len(upper) > 1:
                a, b = upper[-2:]
                turn = (b[0] - a[0]) * (p[2] - b[2]) - (b[2] - a[2]) * (p[0] - b[0])
                if turn < 0:
                    break
                upper.pop()
            upper.append(p)
        if len(upper) != 7:
            raise ValueError(('Unexpected actual upper C/rail outer chain', upper))
        cumulative = [0.0]
        for a, b in zip(upper, upper[1:]):
            cumulative.append(cumulative[-1] + math.dist(a, b))
        self.us = [v / cumulative[-1] for v in cumulative]
        self.top_points = upper
        self.top = [Cubic(list(zip(self.us, [p[k] for p in upper]))) for k in range(3)]
        self.a = [self.sign * plan['seed_a'][0], *plan['seed_a'][1:]]
        self.b = [self.sign * plan['seed_b'][0], *plan['seed_b'][1:]]

        def body_at(u):
            for span in plan['spans']:
                lo, hi = map(lambda q: float(__import__('fractions').Fraction(q)), span['parameter'])
                if lo - 1e-12 <= u <= hi + 1e-12:
                    t = (u - lo) / (hi - lo)
                    a, b = span['points']
                    p = [(1 - t) * a[k] + t * b[k] for k in range(3)]
                    p[0] *= self.sign
                    return p
            raise ValueError(('Missing exact body upper chart at parameter', u))
        self.body_seed = [body_at(k / 8) for k in range(9)]
        self.bottom = [Cubic([(k / 8, p[i]) for k, p in enumerate(self.body_seed)]) for i in range(3)]
        toward = [self.sign * plan['toward_C_xy'][0], plan['toward_C_xy'][1], 0.0]
        self.end_d = []
        for u in (0.0, 1.0):
            original = plan['spans'][0 if u == 0 else -1]['geometry_normal']
            n = [self.sign * original[0], *original[1:]]
            d = [-0.24 * toward[0], -0.24 * toward[1], 0.0]
            d[2] = -(n[0] * d[0] + n[1] * d[1]) / n[2]
            self.end_d.append(d)
        seal = rows['LOD0_BacklightSeal']
        i_points = [(0.0, upper[0])]
        for y in (-1.27, -1.31, -1.38, -1.47, -1.58, -1.69, -1.8, -1.88):
            candidates = [s for s in section(seal, y) if self.sign * s['geometry_normal'][0] > 0.9 and min((self.sign * p[0] for p in s['points'])) > 0.65]
            if not candidates:
                raise ValueError(('Missing actual fixed seal outer face', side, y))
            segment = max(candidates, key=lambda s: sum((self.sign * p[0] for p in s['points'])))
            p = [sum((a[k] for a in segment['points'])) / 2 + 0.001 * segment['geometry_normal'][k] for k in range(3)]
            p[0] *= self.sign
            s = (y - self.front) / (self.a[1] - self.front)
            i_points.append((s, p))
        i_points.append((1.0, self.a))
        frame = rows['LOD0_DoorFrame_R' + side]
        o_points = [(0.0, upper[-1])]
        for y in (-1.25, -1.27, -1.3, -1.33, -1.37, -1.42, -1.48, -1.54, -1.6, -1.625):
            p = frame_top(frame, y)
            p = [self.sign * p[0] - 0.003, p[1], p[2] + 0.004]
            s = (y - self.front) / (self.b[1] - self.front)
            o_points.append((s, p))
        o_points.append((1.0, self.b))
        self.controls = {'inner': i_points, 'outer': o_points, 'lower': self.body_seed, 'upper': upper, 'lower_d': self.end_d}
        old_section = section(rail, -1.22)
        start_d = []
        for target, end in ((upper[0], self.a), (upper[-1], self.b)):
            samples = [p for s in old_section for p in s['points'] if self.sign * p[0] > 0.685 and s['geometry_normal'][2] > 0]
            q = min(samples, key=lambda p: abs(self.sign * p[0] - target[0]))
            q = [self.sign * q[0], q[1], q[2]]
            derivative = [(q[k] - target[k]) / (q[1] - target[1]) * (end[1] - self.front) for k in range(3)]
            start_d.append(derivative)
        self.start_d = start_d
        self.inner = [Cubic([(s, p[k]) for s, p in i_points], start_d[0][k], self.end_d[0][k]) for k in range(3)]
        self.outer = [Cubic([(s, p[k]) for s, p in o_points], start_d[1][k], self.end_d[1][k]) for k in range(3)]

    def base(self, s, u):
        i = [f(s) for f in self.inner]
        o = [f(s) for f in self.outer]
        t = [f(u) for f in self.top]
        b = [f(u) for f in self.bottom]
        return [(1 - u) * i[k] + u * o[k] + (1 - s) * t[k] + s * b[k] - ((1 - s) * ((1 - u) * self.top_points[0][k] + u * self.top_points[-1][k]) + s * ((1 - u) * self.a[k] + u * self.b[k])) for k in range(3)]

    def point(self, s, u):
        p = self.base(s, u)
        e = 1e-05
        for at, basis, desired in ((0.0, s * (1 - s) ** 2, [(1 - u) * self.start_d[0][k] + u * self.start_d[1][k] for k in range(3)]), (1.0, s * s * (s - 1), [(1 - u) * self.end_d[0][k] + u * self.end_d[1][k] for k in range(3)])):
            derivative = [(a - b) / (2 * e) for a, b in zip(self.base(at + e, u), self.base(at - e, u))]
            p = [p[k] + basis * (desired[k] - derivative[k]) for k in range(3)]
        return [self.sign * p[0], p[1], p[2]]

    def normal(self, s, u):
        e = 1e-05
        ds = sub(self.point(s + e, u), self.point(s - e, u))
        du = sub(self.point(s, u + e), self.point(s, u - e))
        n = unit(cross(ds, du))
        return n if self.sign > 0 else [-v for v in n]

def make(original, rows, plan, side, encode):
    surface = Surface(rows, plan, side)
    ss = (0.0, 0.03, 0.065, 0.11, 0.18, 0.28, 0.4, 0.53, 0.66, 0.78, 0.88, 0.95, 1.0)
    us = surface.us
    points = []
    normals = []
    uv = []
    for j, s in enumerate(ss):
        row = [surface.point(s, u) for u in us]
        distance = 0.0
        for k, (u, p) in enumerate(zip(us, row)):
            if k:
                distance += math.dist(row[k - 1], p)
            points.append(p)
            normals.append(surface.normal(s, u))
            uv.append([distance / 0.25, math.dist(surface.point(0.0, u), p) / 0.25])
    count = len(points)
    points += [[p[k] - 0.0012 * n[k] for k in range(3)] for p, n in zip(points[:], normals)]
    faces = []
    targets = []
    uvs = {name: [] for name in rows[original.name]['uvs']}

    def emit(tri, kind):
        ps = [points[i] for i in tri]
        g = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
        faces.append(tri)
        for i in tri:
            targets.append(normals[i % count] if kind == 'outer' else [-x for x in normals[i % count]] if kind == 'inner' else g)
            for name in uvs:
                uvs[name].append(uv[i % count])
    outer = []
    for j in range(len(ss) - 1):
        for k in range(len(us) - 1):
            a = j * len(us) + k
            b = a + 1
            c = a + len(us)
            d = c + 1
            ts = [[a, c, d], [a, d, b]]
            if side == 'L':
                ts = [list(reversed(t)) for t in ts]
            for t in ts:
                outer.append(t)
                emit(t, 'outer')
                emit([i + count for i in reversed(t)], 'inner')
    edges = {}
    for tri in outer:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append((a, b))
    for uses in edges.values():
        if len(uses) == 1:
            a, b = uses[0]
            emit([b, a, a + count], 'rim')
            emit([b, a + count, b + count], 'rim')
    mesh = bpy.data.meshes.new('Private_CQuarter_CSkin14_' + side)
    mesh.from_pydata(points, [], faces)
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    for material in original.data.materials:
        mesh.materials.append(material)
    for name, values in uvs.items():
        layer = mesh.uv_layers.new(name=name)
        for datum, target in zip(layer.data, values):
            datum.uv = target
    encoded = encode(mesh, targets)
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = Matrix.Identity(4)
    return (obj, {'controls': surface.controls, 's_knots': ss, 'u_knots': us, 'ideal_normals': targets, 'encoding': encoded, 'vertices': len(points), 'triangles': len(faces), 'nominal_wall_m': 0.0012, 'authored_geometry': True, 'limits': 'Shape-only private skin. Actual receiver/reinforcement and all finite support/clearance must pass before a root installation.'}, surface)
