"""Edge-relative double precision point/triangle geometry for tiny joint sheets."""
import numpy as np


def point_triangle(point, triangle):
    point = np.asarray(point, dtype=float)
    a, b, c = np.asarray(triangle, dtype=float)
    ab, ac = b - a, c - a
    normal = np.cross(ab, ac)
    square = float(normal @ normal)
    if square > 0:
        projected = point - normal * float((point - a) @ normal) / square
        barycentric = [float(np.cross(b - projected, c - projected) @ normal) / square,
                       float(np.cross(c - projected, a - projected) @ normal) / square,
                       float(np.cross(a - projected, b - projected) @ normal) / square]
        if min(barycentric) >= 0:
            return projected
    candidates = []
    for start, end in ((a, b), (b, c), (c, a)):
        delta = end - start
        denominator = float(delta @ delta)
        t = min(1., max(0., float((point - start) @ delta) / denominator)) if denominator else 0.
        candidates.append(start + t * delta)
    return min(candidates, key=lambda p: float(np.linalg.norm(point - p)))


def split_halfspace(polygon, normal, constant):
    """Partition a convex polygon into closed inside/outside linear halfspaces."""
    inside, outside = [], []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        da, db = float(normal @ a - constant), float(normal @ b - constant)
        (inside if da >= 0 else outside).append(a)
        if (da < 0) != (db < 0):
            crossing = a + (b - a) * (da / (da - db))
            inside.append(crossing)
            outside.append(crossing)
    return inside, outside


def subtract_prism(polygon, triangle, height):
    """Remove the certified closed orthogonal prism above one target triangle."""
    a, b, c = triangle
    normal = np.cross(b - a, c - a)
    normal /= np.linalg.norm(normal)
    planes = []
    for start, end in ((a, b), (b, c), (c, a)):
        inward = np.cross(normal, end - start)
        inward /= np.linalg.norm(inward)
        planes.append((inward, float(inward @ start)))
    planes.extend(((normal, float(normal @ a) - height), (-normal, -float(normal @ a) - height)))
    inside, outside = polygon, []
    for direction, constant in planes:
        inside, fragment = split_halfspace(inside, direction, constant)
        if fragment:
            outside.append(fragment)
        if not inside:
            break
    return outside, inside
