"""Finite original arch bevel field proposal; no file/source IO or geometry edits."""
import collections
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


def prepare(obj, return_plan, projection, sheet_plan):
    from mathutils import Matrix
    import numpy as np
    if obj.name not in SEMANTICS or obj.type != 'MESH' or obj.modifiers or obj.matrix_world != Matrix.Identity(4):
        raise ValueError('Expected actual ground-frame front fender')
    if return_plan['object'] != obj.name or not return_plan['targets'] or return_plan['ambiguous_corners']:
        raise ValueError('Missing independent finite return reference')
    m = obj.data
    m.calc_loop_triangles()
    physical = fields(obj)
    before = [tuple(n.vector) for n in m.corner_normals]
    sheet_targets = sheet_plan['targets']
    if sheet_plan['object'] != obj.name or len(sheet_targets) != len(before):
        raise ValueError('Incorrect complete original-sheet target inventory')
    if before != list(return_plan['before']):
        raise ValueError('Return reference is stale for this actual native field')
    profile = return_plan['profile']
    if (profile['radius_m'] != .4483 or profile['facets'] != 64 or profile['wheel_z_m'] != .3433
            or profile['plane_and_footprint_guard_m'] != GEOMETRY_GUARD):
        raise ValueError('Unreviewed original cutter profile')
    for n in before:
        if not all(math.isfinite(v) for v in n) or abs(math.hypot(*n)-1) > 1e-6:
            raise ValueError('Invalid input native normal')
    for key in ('cb_fascia_cap', '__mod_weightednormals_faceweight'):
        attr = m.attributes.get(key)
        if attr is None or attr.domain != 'FACE' or attr.data_type != 'INT':
            raise ValueError('Missing actual FACE ownership')
    tag = m.attributes['cb_fascia_cap']
    strength = m.attributes['__mod_weightednormals_faceweight']
    points = [tuple(v.co) for v in m.vertices]
    return_faces = set()
    return_targets = {int(k): tuple(v) for k, v in return_plan['targets'].items()}
    independent_domains = []
    for row in return_plan['complete_facet_domains']:
        fi = row['face']
        if type(fi) is not int or not 0 <= fi < len(m.polygons) or fi in return_faces:
            raise ValueError('Invalid independent return face')
        face = m.polygons[fi]
        if [list(points[v]) for v in face.vertices] != row['vertices_m'] or row['wheel_y_m'] != 1.46:
            raise ValueError('Independent return geometry is not current front geometry')
        return_faces.add(fi)
        for li in face.loop_indices:
            p = points[m.loops[li].vertex_index]
            target = unit((0, (1.46-p[1])/.4483, (.3433-p[2])/.4483))
            if li not in return_targets or angle(target, return_targets[li]) > .00002:
                raise ValueError('Independent radial target mismatch')
        independent_domains.append(row)
    if set(return_targets) != {li for fi in return_faces for li in m.polygons[fi].loop_indices}:
        raise ValueError('Incomplete independent return target inventory')
    expected_profile = {'radius_m': .4483, 'facets': 64, 'wheel_y_m': [-1.46, 1.46],
                        'wheel_z_m': .3433, 'absolute_x_range_m': [.46, 1.30],
                        'plane_and_footprint_guard_m': 1e-6, 'face_alignment_min': .99999,
                        'authorship': 'New radial return field; original outer-skin normals remain unselected.'}
    if profile != expected_profile:
        raise ValueError('Independent cutter profile differs from the actual scoped contract')
    triangles_by_face = collections.defaultdict(list)
    for triangle in m.loop_triangles:
        triangles_by_face[triangle.polygon_index].append(triangle)
    independently_rederived = {}
    apothem = .4483*math.cos(math.pi/64)
    half_edge = .4483*math.sin(math.pi/64)
    for face in m.polygons:
        ps = [points[v] for v in face.vertices]
        if (not all(.46-1e-6 <= abs(p[0]) <= 1.30+1e-6 for p in ps)
                or min(p[0] for p in ps)*max(p[0] for p in ps) <= 0):
            continue
        choices = []
        for facet in range(64):
            a = (facet+.5)*math.tau/64
            ny, nz = math.cos(a), math.sin(a)
            if not all(-float(t.normal.y)*ny-float(t.normal.z)*nz >= .99999 for t in triangles_by_face[face.index]):
                continue
            if (max(abs((p[1]-1.46)*ny+(p[2]-.3433)*nz-apothem) for p in ps) <= 1e-6
                    and max(abs(-(p[1]-1.46)*nz+(p[2]-.3433)*ny) for p in ps) <= half_edge+1e-6):
                choices.append(facet)
        if len(choices) > 1:
            raise ValueError('Ambiguous actual finite return domain')
        if choices:
            independently_rederived[face.index] = choices[0]
    if set(independently_rederived) != return_faces:
        raise ValueError('Independent reference omits/adds an actual complete return face')
    for row in independent_domains:
        if type(row['facet']) is not int or row['facet'] != independently_rederived[row['face']]:
            raise ValueError('Independent reference facet identity mismatch')
    side = -1 if obj.name.endswith('_L') else 1
    # Actual retained outer geometry bounds the physical bevel, even where a
    # separately rebuilt partition prevents original field attribution. It is
    # not permission to author those other faces; only sheet_plan owns them.
    outer_faces = {p.index for p in m.polygons if tag.data[p.index].value == 0
                   and strength.data[p.index].value == 16384 and side*float(p.normal.x) > 0}
    triangle_rows = []
    by_face = collections.defaultdict(list)
    for t in m.loop_triangles:
        ps = [points[v] for v in t.vertices]
        row = {'triangle': t.index, 'face': t.polygon_index, 'points': ps, 'box': _box(ps)}
        triangle_rows.append(row)
        by_face[t.polygon_index].append(row)
    returns = [r for r in triangle_rows if r['face'] in return_faces]
    outers = [r for r in triangle_rows if r['face'] in outer_faces]
    if not outers:
        raise ValueError('No actual retained outward skin')
    edge_faces = collections.defaultdict(list)
    face_edges = {}
    for face in m.polygons:
        rows = [m.loops[li].edge_index for li in face.loop_indices]
        face_edges[face.index] = rows
        for ei in rows:
            edge_faces[ei].append(face.index)
    if any(len(fs) != 2 for fs in edge_faces.values()):
        raise ValueError('Nonmanifold actual fender boundary')
    eligible = {}
    for face in m.polygons:
        fi = face.index
        if fi in return_faces or tag.data[fi].value != 0 or strength.data[fi].value not in (-16384, 0):
            continue
        proof = []
        for row in by_face[fi]:
            a = _whole_near(row['points'], returns, projection.closest)
            b = _whole_near(row['points'], outers, projection.closest)
            if a is None or b is None:
                break
            proof.append({'triangle': row['triangle'], 'points': row['points'], 'return': a, 'outer': b})
        else:
            eligible[fi] = proof
    seeds = {f for fi in return_faces for ei in face_edges[fi] for f in edge_faces[ei] if f in eligible}
    bevel_faces = set(seeds)
    queue = list(sorted(seeds))
    while queue:
        fi = queue.pop()
        for ei in face_edges[fi]:
            for other in edge_faces[ei]:
                if other in eligible and other not in bevel_faces:
                    bevel_faces.add(other)
                    queue.append(other)
    if not bevel_faces:
        raise ValueError('No finite outer bevel transition strip')
    selected_faces = return_faces | bevel_faces
    vertices = sorted({v for fi in bevel_faces for v in m.polygons[fi].vertices})
    constraints = collections.defaultdict(list)
    boundaries = []
    for ei, fs in edge_faces.items():
        bevel = [f for f in fs if f in bevel_faces]
        if len(bevel) != 1:
            continue
        other = next(f for f in fs if f not in bevel_faces)
        if other in return_faces:
            kind = 'radial_return'
        elif other in outer_faces:
            kind = 'protected_outside'
        else:
            face = m.polygons[other]
            xs = [abs(points[v][0]) for v in face.vertices]
            inboard = min(abs(points[v][0]) for fi in return_faces for v in m.polygons[fi].vertices)
            if tag.data[other].value != 0 or strength.data[other].value not in (-16384, 0, 16384):
                raise ValueError('Unclassified outer bevel boundary: '+str(other))
            terminal = (strength.data[other].value in (-16384, 0)
                        and min(xs) <= inboard+BEVEL_WIDTH+GEOMETRY_GUARD
                        and max(xs)-min(xs) > BEVEL_WIDTH)
            # Existing bevel continuation outside the finite wheel region is
            # protected just like retained skin; it receives no new targets.
            kind = 'protected_terminal' if terminal else 'protected_outside'
        for vi in m.edges[ei].vertices:
            li = next(l for l in m.polygons[other].loop_indices if m.loops[l].vertex_index == vi)
            value = return_targets[li] if other in return_faces else sheet_targets[li]
            constraints[vi].append({'edge': ei, 'other_face': other, 'other_loop': li, 'kind': kind, 'target': value})
        boundaries.append({'edge': ei, 'vertices': list(m.edges[ei].vertices),
                           'bevel_face': bevel[0], 'other_face': other, 'kind': kind,
                           'other_points': [points[v] for v in m.polygons[other].vertices],
                           'other_normal': tuple(m.polygons[other].normal)})
    fixed = {}
    constraint_records = []
    for vi, rows in sorted(constraints.items()):
        terminal = [r for r in rows if r['kind'] == 'protected_terminal']
        # At an actual transverse end, the existing radial-to-terminal split
        # already has incompatible one-point limits. Preserve that endpoint
        # split, and close the bevel to the unchanged actual terminal field.
        # This does not author the terminal or extend a split to other vertices.
        fixed_rows = [r for r in rows if r['kind'] != 'radial_return'] if terminal else rows
        value = unit(tuple(sum(r['target'][i] for r in fixed_rows)/len(fixed_rows) for i in range(3)))
        error = max(angle(value, r['target']) for r in fixed_rows)
        spread = max(angle(a['target'], b['target']) for a in rows for b in rows)
        constraint_records.append({'vertex': vi, 'point': points[vi], 'conditions': rows, 'spread_degrees': spread,
                                   'fixed_conditions': fixed_rows, 'maximum_fixed_target_error_degrees': error,
                                   'preserved_existing_radial_terminal_endpoint_split': bool(terminal)})
        if error > NORMAL_GUARD:
            raise ValueError('Incompatible finite bevel boundary: '+json.dumps(constraint_records[-1]))
        fixed[vi] = value
    graph = {v: {} for v in vertices}
    for fi in bevel_faces:
        for ei in face_edges[fi]:
            a, b = m.edges[ei].vertices
            length = math.dist(points[a], points[b])
            if length <= 0:
                raise ValueError('Zero transition edge')
            graph[a][b] = graph[b][a] = 1/length
    free = [v for v in vertices if v not in fixed]
    at = {v: i for i, v in enumerate(free)}
    matrix = np.zeros((len(free), len(free)), dtype=np.float64)
    rhs = np.zeros((len(free), 3), dtype=np.float64)
    for vi in free:
        i = at[vi]
        for other, weight in graph[vi].items():
            matrix[i, i] += weight
            if other in at:
                matrix[i, at[other]] -= weight
            else:
                rhs[i] += weight*np.asarray(fixed[other])
    # New authored baseline from actual bevel surface tangents. The old
    # interior field is measured, not imposed as an appearance requirement.
    base_fans = {}
    for vi in vertices:
        corners = [li for fi in bevel_faces for li in m.polygons[fi].loop_indices
                   if m.loops[li].vertex_index == vi]
        spread = max(angle(before[a], before[b]) for a in corners for b in corners)
        total = [0., 0., 0.]
        total_weight = 0.
        contributions = []
        for triangle in m.loop_triangles:
            if triangle.polygon_index not in bevel_faces or vi not in triangle.vertices:
                continue
            others = [v for v in triangle.vertices if v != vi]
            a, b = (tuple(points[v][i]-points[vi][i] for i in range(3)) for v in others)
            weight = math.radians(angle(a, b))
            normal = tuple(float(v) for v in triangle.normal)
            for i in range(3):
                total[i] += weight*normal[i]
            total_weight += weight
            contributions.append({'triangle': triangle.index, 'corner_angle_radians': weight, 'normal': normal})
        if total_weight <= 0:
            raise ValueError('No actual bevel tangent at vertex')
        base_fans[vi] = {'loops': corners, 'old_spread_degrees': spread,
                         'actual_triangle_tangents': contributions,
                         'normal': unit(tuple(v/total_weight for v in total))}
    def rotation_log(a, b):
        axis = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
        sine = math.hypot(*axis)
        theta = math.atan2(sine, sum(x*y for x, y in zip(a, b)))
        if theta < 1e-12:
            return (0., 0., 0.)
        if sine < 1e-12:
            raise ValueError('Ambiguous opposed correction axis')
        return tuple(theta*v/sine for v in axis)
    def rotate(a, rotation):
        theta = math.hypot(*rotation)
        if theta < 1e-12:
            return a
        axis = tuple(v/theta for v in rotation)
        cross = (axis[1]*a[2]-axis[2]*a[1], axis[2]*a[0]-axis[0]*a[2], axis[0]*a[1]-axis[1]*a[0])
        dot = sum(x*y for x, y in zip(a, axis))
        return unit(tuple(math.cos(theta)*a[i]+math.sin(theta)*cross[i]+(1-math.cos(theta))*dot*axis[i] for i in range(3)))
    rotation_targets = {vi: rotation_log(base_fans[vi]['normal'], target) for vi, target in fixed.items()}
    rhs.fill(0.)
    for vi in free:
        for other, weight in graph[vi].items():
            if other in fixed:
                rhs[at[vi]] += weight*np.asarray(rotation_targets[other])
    vector_field = dict(fixed)
    residual = 0.
    if free:
        solved = np.linalg.solve(matrix, rhs)
        residual = float(np.max(np.abs(matrix@solved-rhs)))
        for v, value in zip(free, solved):
            vector_field[v] = rotate(base_fans[v]['normal'], tuple(float(x) for x in value))
    targets = list(sheet_targets)
    authorship = [{'loop': li, 'vertex': m.loops[li].vertex_index, 'face': fi,
                   'domain': 'complete_original_outer_sheet', 'target': targets[li]}
                  for fi in sheet_plan['selected_faces'] for li in m.polygons[fi].loop_indices]
    for li, target in sorted(return_targets.items()):
        targets[li] = target
        authorship.append({'loop': li, 'vertex': m.loops[li].vertex_index, 'domain': 'original_radial_return', 'target': target})
    for fi in sorted(bevel_faces):
        for li in m.polygons[fi].loop_indices:
            vi = m.loops[li].vertex_index
            targets[li] = vector_field[vi]
            authorship.append({'loop': li, 'vertex': vi, 'face': fi, 'domain': 'new_finite_bevel_transition', 'target': targets[li]})
    return {'schema': 'front-sheet-arch-finite-transition.v1', 'object': obj.name,
            'physical': physical, 'physical_sha256': digest(physical), 'before': before,
            'targets': targets, 'targets_sha256': digest(targets), 'authorship': authorship,
            'return_reference_sha256': digest(return_plan), 'independent_return_domains': independent_domains,
            'bevel_width_m': BEVEL_WIDTH, 'geometry_guard_m': GEOMETRY_GUARD,
            'complete_bevel_domains': [{'face': fi, 'triangles': eligible[fi]} for fi in sorted(bevel_faces)],
            'bevel_faces': sorted(bevel_faces), 'return_faces': sorted(return_faces),
            'boundary_constraints': constraint_records, 'boundary_edges': boundaries,
            'harmonic_free_vertices': free, 'harmonic_residual': residual,
            'base_bevel_fans': base_fans, 'fixed_rotation_logs_radians': rotation_targets,
            'authored_interpolation': 'Angle-weighted actual bevel tangents, harmonic shortest-rotation correction to fixed radial/outside boundaries; new authored interior field',
            'triangles': len(m.loop_triangles), 'normal_guard_degrees': NORMAL_GUARD,
            'scope': 'Completely owned original sheet plus finite outer bevel. Actual radial return and manufactured terminal field limits remain separate; existing radial/terminal endpoint splits are measured, not declared smooth. Geometry is fixed; no old damaged transition-field identity claim.'}


def apply(obj, plan, encode):
    import bpy
    if obj.name != plan['object'] or digest(fields(obj)) != plan['physical_sha256']:
        raise ValueError('Native geometry differs from prepared authorship')
    before = [tuple(n.vector) for n in obj.data.corner_normals]
    if before != list(plan['before']) or digest(plan['targets']) != plan['targets_sha256']:
        raise ValueError('Prepared target/source field changed')
    selected = {r['loop'] for r in plan['authorship']}
    if any(plan['targets'][i] != n for i, n in enumerate(before) if i not in selected):
        raise ValueError('Requested field escaped finite authorship')
    staged = obj.data.copy()
    old = obj.data
    try:
        result = encode(staged, plan['targets'])
        actual = [tuple(n.vector) for n in staged.corner_normals]
        errors = [angle(a, b) for a, b in zip(actual, plan['targets'])]
        outside = [angle(before[i], n) for i, n in enumerate(actual) if i not in selected]
        if not result['passed'] or max(errors) > NORMAL_GUARD or max(outside, default=0) > NORMAL_GUARD:
            raise ValueError('Unchanged native field guard failed')
        staged.calc_loop_triangles()
        whole_targets, whole_outside = [], []
        for triangle in staged.loop_triangles:
            loops = list(triangle.loops)
            whole_targets.append({'triangle': triangle.index, **complete_affine_angle([plan['targets'][i] for i in loops], [actual[i] for i in loops])})
            if not selected.intersection(loops):
                whole_outside.append({'triangle': triangle.index, **complete_affine_angle([before[i] for i in loops], [actual[i] for i in loops])})
        boundary = []
        for row in plan['boundary_edges']:
            values = []
            for vi in row['vertices']:
                a = next(l for l in staged.polygons[row['bevel_face']].loop_indices if staged.loops[l].vertex_index == vi)
                b = next(l for l in staged.polygons[row['other_face']].loop_indices if staged.loops[l].vertex_index == vi)
                values.append({'vertex': vi, 'before_degrees': angle(before[a], before[b]),
                               'requested_degrees': angle(plan['targets'][a], plan['targets'][b]),
                               'native_degrees': angle(actual[a], actual[b])})
            boundary.append({**row, 'endpoint_agreement': values})
        obj.data = staged
        if fields(obj) != plan['physical']:
            raise ValueError('Geometry/topology/UV/material/transform changed')
        staged.calc_loop_triangles()
        if len(staged.loop_triangles) != plan['triangles']:
            raise ValueError('Triangle count changed')
        proof = {'object': obj.name, 'status': 'native-field-trial-passed', 'new_targets': len(selected),
                 'bevel_faces': len(plan['bevel_faces']), 'return_faces': len(plan['return_faces']),
                 'maximum_encoding_degrees': max(errors), 'maximum_outside_degrees': max(outside, default=0),
                 'outside_corners': len(outside), 'boundary': boundary,
                 'maximum_native_boundary_jump_degrees': max(r['native_degrees'] for b in boundary for r in b['endpoint_agreement']),
                 'boundary_maxima_by_kind': {kind: {
                     'edges': sum(b['kind'] == kind for b in boundary),
                     'before_degrees': max((r['before_degrees'] for b in boundary if b['kind'] == kind for r in b['endpoint_agreement']), default=0),
                     'requested_degrees': max((r['requested_degrees'] for b in boundary if b['kind'] == kind for r in b['endpoint_agreement']), default=0),
                     'native_degrees': max((r['native_degrees'] for b in boundary if b['kind'] == kind for r in b['endpoint_agreement']), default=0)
                 } for kind in ('radial_return', 'protected_outside', 'protected_terminal')},
                 'native_encoding': result, 'physical_exact': True, 'triangle_delta': 0,
                 'whole_target_native_fields': whole_targets, 'whole_outside_fields': whole_outside,
                 'whole_target_maximum_degrees': max(r['maximum_degrees'] for r in whole_targets),
                 'whole_outside_maximum_degrees': max(r['maximum_degrees'] for r in whole_outside),
                 'whole_field_method': 'Complete degree-two Bernstein cross/dot bounds; subdivision keeps affine vectors unnormalized and discards no remainder',
                 'targets_sha256': plan['targets_sha256'], 'visual_acceptance': None, 'source_saved': False}
        staged = None
        return proof
    except Exception:
        obj.data = old
        raise
    finally:
        if staged is not None and staged.users == 0:
            bpy.data.meshes.remove(staged)
