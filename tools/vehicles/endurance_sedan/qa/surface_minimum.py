"""Exact triangle-feature distance, with explicit solid-contact witnesses."""
import heapq
import itertools
import math

from geometry import Mesh, bounds, box_distance2, contact, tree, triangle_distance


class Distances:
    def __init__(self, rows):
        self.rows = rows
        self.cache = {}

    def item(self, name):
        if name not in self.cache:
            mesh = Mesh(self.rows[name])
            triangles = []
            for tri in mesh.triangles:
                points = [mesh.vertices[i] for i in tri]
                triangles.append((points, bounds(points)))
            self.cache[name] = mesh, triangles, tree(triangles)
        return self.cache[name]

    def minimum(self, an, bn):
        a, at, ar = self.item(an)
        b, bt, br = self.item(bn)
        observed = contact(a, b)
        if observed:
            return {'distance_m': 0.0, 'contact': observed, 'triangle_pairs_evaluated': 0}
        best, witness, count = math.inf, None, 0
        for first, second in ((a, b), (b, a)):
            for index, vertex in enumerate(first.vertices):
                point, _, face, distance = second.bvh.find_nearest(vertex)
                if distance < best:
                    best = distance
                    witness = {'kind': 'vertex_face', 'vertex_mesh': first.name, 'vertex': index,
                               'face_mesh': second.name, 'face': face,
                               'point_a': list(vertex), 'point_b': list(point)}
        serial = itertools.count()
        queue = [(box_distance2(ar[0], br[0]), next(serial), ar, br)]
        while queue:
            lower, _, left, right = heapq.heappop(queue)
            if lower >= best * best:
                continue
            if left[1] is not None and right[1] is not None:
                for ai in left[1]:
                    for bi in right[1]:
                        if box_distance2(at[ai][1], bt[bi][1]) >= best * best:
                            continue
                        distance, p, q = triangle_distance(at[ai][0], bt[bi][0])
                        count += 1
                        if distance < best:
                            best = distance
                            witness = {'kind': 'triangle_features', 'triangles': [ai, bi],
                                       'point_a': list(p), 'point_b': list(q)}
            else:
                split_left = right[1] is not None or (left[1] is None and sum(
                    (left[0][1][i]-left[0][0][i])**2 for i in range(3)) >= sum(
                    (right[0][1][i]-right[0][0][i])**2 for i in range(3)))
                children = [(child, right) for child in left[2:]] if split_left else [
                    (left, child) for child in right[2:]]
                for x, y in children:
                    lower = box_distance2(x[0], y[0])
                    if lower < best * best:
                        heapq.heappush(queue, (lower, next(serial), x, y))
        return {'distance_m': best, 'witness': witness, 'triangle_pairs_evaluated': count}
