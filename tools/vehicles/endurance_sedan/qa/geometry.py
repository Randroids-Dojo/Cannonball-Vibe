"""Closed-mesh contact witnesses and exact triangle-distance primitives."""
import math
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree

class Mesh:

    def __init__(self, row, delta=None):
        self.name = row['name']
        self.vertices = [Vector(p) for p in row['vertices']]
        if delta is not None:
            self.vertices = [delta @ p for p in self.vertices]
        self.triangles = row['triangles']
        self.low = Vector([min((p[i] for p in self.vertices)) for i in range(3)])
        self.high = Vector([max((p[i] for p in self.vertices)) for i in range(3)])
        self.bvh = BVHTree.FromPolygons(self.vertices, self.triangles, all_triangles=True, epsilon=0.0)

    def contains_box(self, point, epsilon=1e-06):
        return all((self.low[i] + epsilon < point[i] < self.high[i] - epsilon for i in range(3)))

    def inside(self, point):
        nearest, normal, face, distance = self.bvh.find_nearest(point)
        if distance is None or distance < 1e-06:
            return None
        counts = []
        for direction in (Vector((1, 0.371, 0.173)).normalized(), Vector((-0.219, 1, 0.413)).normalized(), Vector((0.337, -0.183, 1)).normalized()):
            origin = point.copy()
            count = 0
            for _ in range(100):
                hit, _, _, _ = self.bvh.ray_cast(origin, direction, 100)
                if hit is None:
                    break
                count += 1
                origin = hit + direction * 2e-06
            counts.append(count)
        return {'inside_all_three_rays': all((n % 2 == 1 for n in counts)), 'ray_hit_counts': counts, 'surface_distance_m': distance, 'nearest_surface_source_m': list(nearest)}

def overlap_bounds(a, b):
    return all((a.high[i] >= b.low[i] and b.high[i] >= a.low[i] for i in range(3)))

def segment_hit(start, end, vertices):
    direction = end - start
    if direction.length < 1e-10:
        return None
    hit = geometry.intersect_ray_tri(*vertices, direction, start, True)
    if hit is None:
        return None
    t = (hit - start).dot(direction) / direction.length_squared
    return hit if -1e-07 <= t <= 1 + 1e-07 else None

def contact(a, b):
    if not overlap_bounds(a, b):
        return None
    for first, second in ((a, b), (b, a)):
        for index, p in enumerate(first.vertices):
            if not second.contains_box(p):
                continue
            nearest, normal, _, distance = second.bvh.find_nearest(p)
            if distance is None or distance < 1e-06 or (p - nearest).dot(normal) >= -1e-06:
                continue
            inside = second.inside(p)
            if inside and inside['inside_all_three_rays']:
                return {'kind': 'actual_vertex_inside_solid', 'surface_mesh': first.name, 'solid_mesh': second.name, 'vertex_index': index, 'point_source_m': list(p), **inside}
    pairs = a.bvh.overlap(b.bvh)
    for ai, bi in pairs:
        av = [a.vertices[i] for i in a.triangles[ai]]
        bv = [b.vertices[i] for i in b.triangles[bi]]
        for first, second in ((av, bv), (bv, av)):
            for i in range(3):
                point = segment_hit(first[i], first[(i + 1) % 3], second)
                if point is not None:
                    return {'kind': 'actual_surface_triangle_intersection', 'mesh_a': a.name, 'mesh_b': b.name, 'triangle_a': ai, 'triangle_b': bi, 'point_source_m': list(point), 'triangle_a_vertices': [list(p) for p in av], 'triangle_b_vertices': [list(p) for p in bv]}
    return None

def bounds(v):
    return (tuple((min((p[i] for p in v)) for i in range(3))), tuple((max((p[i] for p in v)) for i in range(3))))

def box_distance2(a, b):
    return sum((max(0.0, a[0][i] - b[1][i], b[0][i] - a[1][i]) ** 2 for i in range(3)))

def tree(triangles, indices=None):
    if indices is None:
        indices = list(range(len(triangles)))
    low = tuple((min((triangles[i][1][0][j] for i in indices)) for j in range(3)))
    high = tuple((max((triangles[i][1][1][j] for i in indices)) for j in range(3)))
    box = (low, high)
    if len(indices) <= 12:
        return (box, indices, None, None)
    axis = max(range(3), key=lambda j: high[j] - low[j])
    indices.sort(key=lambda i: sum((triangles[i][1][k][axis] for k in (0, 1))))
    mid = len(indices) // 2
    return (box, None, tree(triangles, indices[:mid]), tree(triangles, indices[mid:]))

def segment_distance(a, b, c, d):
    u = b - a
    v = d - c
    w = a - c
    aa = u.dot(u)
    bb = u.dot(v)
    cc = v.dot(v)
    dd = u.dot(w)
    ee = v.dot(w)
    den = aa * cc - bb * bb
    if aa < 1e-20 or cc < 1e-20:
        return min(((a - c).length, a, c), ((a - d).length, a, d), ((b - c).length, b, c), ((b - d).length, b, d), key=lambda z: z[0])
    s = max(0.0, min(1.0, (bb * ee - cc * dd) / den)) if den > 1e-20 else 0.0
    t = (bb * s + ee) / cc
    if t < 0:
        t = 0.0
        s = max(0.0, min(1.0, -dd / aa))
    elif t > 1:
        t = 1.0
        s = max(0.0, min(1.0, (bb - dd) / aa))
    x = a + s * u
    y = c + t * v
    return ((x - y).length, x, y)

def vertex_edge_triangle_distance(av, bv):
    best = (math.inf, None, None)
    for first, second, swap in ((av, bv, False), (bv, av, True)):
        for point in first:
            q = geometry.closest_point_on_tri(point, *second)
            dist = (point - q).length
            if dist < best[0]:
                best = (dist, q, point) if swap else (dist, point, q)
    for i in range(3):
        for j in range(3):
            dist, x, y = segment_distance(av[i], av[(i + 1) % 3], bv[j], bv[(j + 1) % 3])
            if dist < best[0]:
                best = (dist, x, y)
    return best

def triangle_distance(av, bv):
    for first, second in ((av, bv), (bv, av)):
        for i in range(3):
            delta = first[(i + 1) % 3] - first[i]
            if delta.length_squared < 1e-24:
                continue
            hit = geometry.intersect_ray_tri(*second, delta, first[i], True)
            if hit is not None and -1e-8 <= (hit-first[i]).dot(delta)/delta.length_squared <= 1+1e-8:
                return 0.0, hit, hit
    return vertex_edge_triangle_distance(av, bv)
