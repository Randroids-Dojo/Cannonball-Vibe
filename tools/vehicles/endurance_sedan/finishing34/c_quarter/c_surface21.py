"""C shape18 with an exactly shared evaluated Roof underside edge.

All Roof geometry stays fixed. The inboard 1.2 mm C return conforms to the
actual Solidify underside at its joint; elsewhere it remains an authored offset.
"""
import math
from .boundary02 import unit, cross, sub
from .c_surface18 import Surface as Previous

class Surface(Previous):

    def inner_point(self, s, u):
        p = self.point(s, u)
        n = self.normal(s, u)
        result = [p[k] - 0.0012 * n[k] for k in range(3)]
        ws = 1 - self.smooth((s - self.roof_s) / 0.15)
        wu = 1 - self.smooth((u - 0.045) / 0.255)
        if ws == 0 or wu == 0:
            return result
        anchor = self.point(s, 0.0)
        normal = self.normal(s, 0.0)
        base = [anchor[k] - 0.0012 * normal[k] for k in range(3)]
        y = max(self.roof_rear, self.front + (self.a[1] - self.front) * s)
        top, inside, d = self.roof_edge(y)
        desired = [anchor[k] + (self.sign if k == 0 else 1.0) * (inside[k] - top[k]) for k in range(3)]
        return [result[k] + ws * wu * (desired[k] - base[k]) for k in range(3)]

    def inner_normal(self, s, u):
        e = 1e-05
        ds = sub(self.inner_point(s + e, u), self.inner_point(s - e, u))
        du = sub(self.inner_point(s, u + e), self.inner_point(s, u - e))
        n = unit(cross(ds, du))
        return [-self.sign * v for v in n]

def make(original, rows, plan, side, encode):
    import bpy
    from mathutils import Matrix
    from .boundary02 import cross, sub
    surface = Surface(rows, plan, side)
    ss = (0.0, 0.03, surface.roof_s, 0.11, 0.18, 0.28, 0.4, 0.53, 0.66, 0.78, 0.88, 0.95, 1.0)
    us = surface.us
    points = []
    normals = []
    inside_points = []
    inside_normals = []
    uv = []
    long = [0.0] * len(us)
    last = None
    for s in ss:
        row = [surface.point(s, u) for u in us]
        distance = 0.0
        for k, (u, p) in enumerate(zip(us, row)):
            if k:
                distance += math.dist(row[k - 1], p)
            if last:
                long[k] += math.dist(last[k], p)
            points.append(p)
            normals.append(surface.normal(s, u))
            inside_points.append(surface.inner_point(s, u))
            inside_normals.append(surface.inner_normal(s, u))
            uv.append([distance / 0.25, long[k] / 0.25])
        last = row
    count = len(points)
    points += inside_points
    faces = []
    targets = []
    uvs = {name: [] for name in rows[original.name]['uvs']}

    def emit(tri, kind, rim_uv=None):
        ps = [points[i] for i in tri]
        g = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
        faces.append(tri)
        for at, i in enumerate(tri):
            targets.append(normals[i % count] if kind == 'outer' else inside_normals[i % count] if kind == 'inner' else g)
            for name in uvs:
                uvs[name].append(uv[i % count] if rim_uv is None else rim_uv[at])
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
    rim_length = 0.0
    for uses in edges.values():
        if len(uses) == 1:
            a, b = uses[0]
            length = math.dist(points[a], points[b])
            x0, x1 = (rim_length / 0.25, (rim_length + length) / 0.25)
            th = 0.0012 / 0.25
            emit([b, a, a + count], 'rim', [[x1, 0.0], [x0, 0.0], [x0, th]])
            emit([b, a + count, b + count], 'rim', [[x1, 0.0], [x0, th], [x1, th]])
            rim_length += length
    mesh = bpy.data.meshes.new('Private_CQuarter_CSkin21_' + side)
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
    return (obj, {'controls': surface.controls, 's_knots': ss, 'u_knots': us, 'ideal_normals': targets, 'encoding': encoded, 'vertices': len(points), 'triangles': len(faces), 'nominal_wall_m': 0.0012, 'roof_joint': 'Outer and underside boundary both derive from the actual fixed evaluated Roof; finite contact/field proof is required separately', 'authored_geometry': True, 'UV': 'Separate meter-based outer/inner arc charts and finite rim distance/thickness chart, .25 metres per UV unit.', 'limits': 'Private candidate skin only. The20mm receiver, reinforcement, complete fields and all joints remain separate required work.'}, surface)
