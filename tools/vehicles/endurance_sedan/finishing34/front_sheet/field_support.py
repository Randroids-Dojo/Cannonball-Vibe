"""Finite original arch bevel field proposal; no file/source IO or geometry edits."""
import hashlib
import json
import math

SEMANTICS = ('LOD0_FrontFender_L', 'LOD0_FrontFender_R')
BEVEL_WIDTH = .0012
GEOMETRY_GUARD = 1e-6
NORMAL_GUARD = .025


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def angle(a, b):
    cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross), sum(x*y for x, y in zip(a, b))))


def unit(value):
    length = math.hypot(*value)
    if not math.isfinite(length) or length < .5:
        raise ValueError('Invalid authored transition vector')
    return tuple(v/length for v in value)


def fields(obj):
    m = obj.data
    attributes = {}
    for a in m.attributes:
        if a.name in ('custom_normal', 'sharp_edge', 'position', '.edge_verts', '.corner_vert', '.corner_edge'):
            continue
        rows = []
        for item in a.data:
            key = next(k for k in ('value', 'vector', 'color') if hasattr(item, k))
            v = getattr(item, key)
            rows.append(v if isinstance(v, (str, int, float, bool)) else tuple(v))
        attributes[a.name] = (a.domain, a.data_type, rows)
    return {'positions': [tuple(v.co) for v in m.vertices],
            'polygons': [(tuple(p.vertices), p.material_index, p.use_smooth) for p in m.polygons],
            'edges': [(tuple(e.vertices), e.use_seam) for e in m.edges],
            'loops': [(l.vertex_index, l.edge_index) for l in m.loops],
            'uvs': {u.name: [tuple(v.uv) for v in u.data] for u in m.uv_layers},
            'materials': [v.name if v else None for v in m.materials], 'attributes': attributes,
            'matrix_world': [tuple(r) for r in obj.matrix_world],
            'matrix_local': [tuple(r) for r in obj.matrix_local],
            'parent': obj.parent.name if obj.parent else None,
            'modifiers': [(v.name, v.type) for v in obj.modifiers]}


def _box(points):
    return tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3))


def _near_boxes(a, b, width):
    return all(a[0][i] <= b[1][i]+width and b[0][i] <= a[1][i]+width for i in range(3))


def _whole_near(points, references, closest):
    """Complete finite union bound, with no discarded unresolved pieces."""
    width = BEVEL_WIDTH+GEOMETRY_GUARD
    leaves = []
    pending = [(points, 0)]
    while pending:
        piece, depth = pending.pop()
        box = _box(piece)
        nearby = [r for r in references if _near_boxes(box, r['box'], width)]
        if not nearby:
            return None
        candidates = []
        nearest_vertices = [math.inf]*3
        for ref in nearby:
            distances = [closest(p, ref['points'])[0] for p in piece]
            nearest_vertices = [min(a, b) for a, b in zip(nearest_vertices, distances)]
            if max(distances) <= width:
                candidates.append((max(distances), ref['triangle'], distances))
        if candidates:
            maximum, ti, distances = min(candidates)
            leaves.append({'points': piece, 'reference_triangle': ti,
                           'vertex_distances_m': distances,
                           'whole_piece_convex_distance_bound_m': maximum, 'depth': depth})
            continue
        if max(nearest_vertices) > width or depth >= 18:
            return None
        # Midpoint bisection partitions the entire actual triangle; it is
        # diagnostic arithmetic only and adds no native source vertices.
        i, j = max(((0, 1), (1, 2), (2, 0)), key=lambda pair: math.dist(piece[pair[0]], piece[pair[1]]))
        k = next(v for v in range(3) if v not in (i, j))
        middle = tuple((a+b)*.5 for a, b in zip(piece[i], piece[j]))
        pending.append(([piece[i], middle, piece[k]], depth+1))
        pending.append(([middle, piece[j], piece[k]], depth+1))
    return {'complete_partition': leaves, 'whole_triangle_union_distance_bound_m': max(r['whole_piece_convex_distance_bound_m'] for r in leaves),
            'unresolved_pieces': 0, 'guard_m': width}


def complete_affine_angle(a, b, guard=NORMAL_GUARD):
    """Degree-two cross/dot Bernstein bound on the complete affine fields."""
    def cross(x, y):
        return (x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0])
    def dot(x, y):
        return sum(v*w for v, w in zip(x, y))
    pending = [(a, b, 0)]
    leaves = []
    while pending:
        x, y, depth = pending.pop()
        cs = [cross(x[i], y[i]) for i in range(3)]
        ds = [dot(x[i], y[i]) for i in range(3)]
        for i, j in ((0, 1), (1, 2), (2, 0)):
            cs.append(tuple((v+w)*.5 for v, w in zip(cross(x[i], y[j]), cross(x[j], y[i]))))
            ds.append((dot(x[i], y[j])+dot(x[j], y[i]))*.5)
        bound = math.degrees(math.atan2(max(math.hypot(*c) for c in cs), min(ds))) if min(ds) > 0 else math.inf
        if bound <= guard:
            leaves.append((bound, depth))
            continue
        if depth >= 16 or any(angle(v, w) > guard for v, w in zip(x, y)):
            raise ValueError('Complete affine field guard failed: '+str((bound, depth)))
        i, j = max(((0, 1), (1, 2), (2, 0)), key=lambda e: math.dist(x[e[0]], x[e[1]])+math.dist(y[e[0]], y[e[1]]))
        k = next(v for v in range(3) if v not in (i, j))
        mx = tuple((v+w)*.5 for v, w in zip(x[i], x[j]))
        my = tuple((v+w)*.5 for v, w in zip(y[i], y[j]))
        # Do not normalize intermediate vectors: they remain the original
        # piecewise affine fields, partitioned over the full barycentric domain.
        pending.append(([x[i], mx, x[k]], [y[i], my, y[k]], depth+1))
        pending.append(([mx, x[j], x[k]], [my, y[j], y[k]], depth+1))
    return {'maximum_degrees': max(v for v, _ in leaves), 'leaves': len(leaves),
            'maximum_depth': max(d for _, d in leaves), 'unresolved': 0}
