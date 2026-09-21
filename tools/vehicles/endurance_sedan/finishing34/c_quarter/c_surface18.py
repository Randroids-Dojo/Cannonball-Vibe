"""C shape16 plus whole corrected Roof boundary field ownership."""
import math
from .boundary02 import unit, angle
from .c_surface16 import Surface as Prior

class Surface(Prior):

    def __init__(self, rows, plan, side):
        super().__init__(rows, plan, side)
        self.roof_row = rows['LOD0_Roof']
        self.roof_column = 0 if side == 'L' else 14
        row = self.roof_row
        start = self.roof_column * 17
        ids = (start, start + 1)
        owners = [fi for fi, t in enumerate(row['triangles']) if set(ids) <= set(t) and all((v < 255 for v in t))]
        if len(owners) != 1:
            raise ValueError('Roof boundary field owner is ambiguous')
        fi = owners[0]
        tri = row['triangles'][fi]
        loops = row['triangle_loops'][fi]
        self.roof_target_ends = [row['normals'][loops[tri.index(v)]] for v in ids]
        n = unit([0.0, -self.roof_edge(self.front)[2][2], 1.0])
        if max((angle(n, target) for target in self.roof_target_ends)) > 5.0:
            raise ValueError('Corrected Roof shading domains must be constructed before the C field')
        self.controls['roof_native_original_target'] = {'triangle': fi, 'vertices': ids, 'native_fields': self.roof_target_ends, 'scope': 'Source sharp-boundary Roof field is original authorship, before any C corner encoding.'}

    def normal(self, s, u):
        geometric = super().normal(s, u)
        ws = 1 - self.smooth((s - self.roof_s) / 0.15)
        wu = 1 - self.smooth((u - 0.045) / 0.255)
        if ws == 0 or wu == 0:
            return geometric
        y = max(self.roof_rear, self.front + (self.a[1] - self.front) * s)
        y0, y1 = (self.roof_points[0][1], self.roof_points[1][1])
        t = (y - y0) / (y1 - y0)
        original = unit([(1 - t) * self.roof_target_ends[0][k] + t * self.roof_target_ends[1][k] for k in range(3)])
        plane = unit([0.0, -self.roof_edge(self.front)[2][2], 1.0])
        return unit([geometric[k] + ws * wu * (original[k] - plane[k]) for k in range(3)])

def make(original, rows, plan, side, encode):
    import bpy
    from mathutils import Matrix
    from .boundary02 import cross, sub
    surface = Surface(rows, plan, side)
    ss = (0.0, 0.03, surface.roof_s, 0.11, 0.18, 0.28, 0.4, 0.53, 0.66, 0.78, 0.88, 0.95, 1.0)
    us = surface.us
    points = []
    normals = []
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
            uv.append([distance / 0.25, long[k] / 0.25])
        last = row
    count = len(points)
    points += [[p[k] - 0.0012 * n[k] for k in range(3)] for p, n in zip(points[:], normals)]
    faces = []
    targets = []
    uvs = {name: [] for name in rows[original.name]['uvs']}

    def emit(tri, kind, rim_uv=None):
        ps = [points[i] for i in tri]
        g = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
        faces.append(tri)
        for at, i in enumerate(tri):
            targets.append(normals[i % count] if kind == 'outer' else [-x for x in normals[i % count]] if kind == 'inner' else g)
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
    mesh = bpy.data.meshes.new('Private_CQuarter_CSkin18_' + side)
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
    return (obj, {'controls': surface.controls, 's_knots': ss, 'u_knots': us, 'ideal_normals': targets, 'encoding': encoded, 'vertices': len(points), 'triangles': len(faces), 'nominal_wall_m': 0.0012, 'authored_geometry': True, 'UV': 'Separate meter-based outer/inner arc charts and finite rim distance/thickness chart, .25 metres per UV unit.', 'limits': 'Private candidate skin only. The20mm receiver, reinforcement, complete fields and all joints remain separate required work.'}, surface)
