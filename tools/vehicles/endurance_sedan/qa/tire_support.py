"""Complete fixed zero-yaw tire support bounds; no scene or source I/O."""
import math
import numpy as np


def cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def point_segment(p, a, b):
    edge = b - a
    squared = float(edge @ edge)
    fraction = min(1., max(0., float((p - a) @ edge) / squared)) if squared else 0.
    return float(np.linalg.norm(p - (a + fraction * edge)))


def segment_distance(a, b, c, d):
    ab, cd = b - a, d - c
    values = (cross(ab, c - a), cross(ab, d - a), cross(cd, a - c), cross(cd, b - c))
    # Near-boundary intersections are deliberately treated as zero distance.
    epsilon = 1e-14
    if (min(values[:2]) <= epsilon and max(values[:2]) >= -epsilon
            and min(values[2:]) <= epsilon and max(values[2:]) >= -epsilon
            and np.all(np.maximum(np.minimum(a, b), np.minimum(c, d)) <=
                       np.minimum(np.maximum(a, b), np.maximum(c, d)) + epsilon)):
        return 0.
    return min(point_segment(a, c, d), point_segment(b, c, d),
               point_segment(c, a, b), point_segment(d, a, b))


def projected_distance(triangle, low, high):
    """Distance between the complete convex triangle and suspension segment."""
    a, b, c = triangle
    ends = (np.asarray((0., low)), np.asarray((0., high)))
    area = cross(b - a, c - a)
    if abs(area) > 1e-14:
        for point in ends:
            signs = [cross(v - u, point - u) for u, v in ((a, b), (b, c), (c, a))]
            if min(signs) >= -1e-14 or max(signs) <= 1e-14:
                return 0.
    return min(segment_distance(u, v, *ends) for u, v in ((a, b), (b, c), (c, a)))


def bounds(triangle, context):
    relative = triangle - context['center']
    lower, upper = float(relative[:, 0].min()), float(relative[:, 0].max())
    axial = 0. if lower <= 0 <= upper else min(abs(lower), abs(upper))
    radial = projected_distance(relative[:, 1:], *context['travel'])
    value = max((a * axial + b * radial - c) / math.hypot(a, b)
                for a, b, c in context['support'])
    return value - context['guard'], axial, radial


def whole_fixed_bound(vertices, triangles, wheel):
    """Optional sufficient bound; the caller separately excludes containment."""
    if len(wheel['angles']) != 1 or wheel['angles'][0] != 0. or wheel['angular_error'] != 0.:
        return None
    rows = []
    for index, face in enumerate(triangles):
        value, axial, radial = bounds(vertices[face], wheel)
        if value < wheel['required']:
            return None
        rows.append({'triangle': index, 'lower_bound_m': value,
                     'minimum_absolute_axial_m': axial, 'minimum_projected_radius_m': radial})
    if not rows:
        return None
    return {'status': 'continuous-bound-certified', 'lower_bound_m': min(row['lower_bound_m'] for row in rows),
            'method': 'Complete triangle axial and projected suspension-segment supports; actual zero yaw',
            'complete_triangle_domains': rows, 'leaves': len(rows), 'maximum_depth': 0}
