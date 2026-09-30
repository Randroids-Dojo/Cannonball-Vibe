"""Bounded original-door sheet normal authorship; no scene/file I/O."""
import hashlib
import json
import math
from mathutils import Vector, geometry

SEMANTICS = ('LOD0_Door_FL', 'LOD0_Door_FR', 'LOD0_Door_RL', 'LOD0_Door_RR', 'LOD0_StructuralBody')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def angle(a, b):
    c = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*c), sum(x*y for x, y in zip(a, b))))


def unit(value):
    n = math.hypot(*value)
    if not math.isfinite(n) or n < .05:
        raise ValueError('Singular original sheet normal')
    return tuple(v/n for v in value)


def valid(values):
    return all(len(n) == 3 and all(math.isfinite(v) for v in n) and abs(math.hypot(*n)-1) <= 1e-6 for n in values)


def physical(obj):
    m = obj.data
    return {'vertices': [tuple(v.co) for v in m.vertices], 'edges': [tuple(e.vertices) for e in m.edges],
            'polygons': [(tuple(p.vertices), p.material_index, p.use_smooth) for p in m.polygons],
            'uvs': {u.name: [tuple(d.uv) for d in u.data] for u in m.uv_layers},
            'materials': [m.name if m else None for m in m.materials],
            'matrix': [list(r) for r in obj.matrix_world], 'parent': obj.parent.name if obj.parent else None}


def bounds(points):
    return tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3))


def overlaps(a, b, epsilon):
    return all(a[0][i] <= b[1][i]+epsilon and b[0][i] <= a[1][i]+epsilon for i in range(3))


def smooth(t):
    t = max(0., min(1., t))
    return t*t*(3-2*t)


def prepare(obj, reference, ownership, excluded_face_indices=()):
    if obj.name not in SEMANTICS or obj.type != 'MESH' or obj.modifiers:
        raise ValueError('Expected actual final unmodified door/body semantic')
    if any(obj.matrix_world[i][j] != (1. if i == j else 0.) for i in range(3) for j in range(3)):
        raise ValueError('Unexpected door normal basis')
    if not reference['triangles'] or not valid(reference['normals']):
        raise ValueError('Missing or invalid actual original reference')
    if len(reference['triangles']) != len(reference['triangle_loops']):
        raise ValueError('Incomplete reference corner inventory')
    is_body = obj.name == 'LOD0_StructuralBody'
    y_min, y_max = (-2.54, 2.40) if is_body else (-1.80, .80)
    excluded = frozenset(excluded_face_indices)
    if excluded and not is_body:
        raise ValueError('Receiver exclusions belong only to the actual body')
    if any(type(i) is not int or i < 0 or i >= len(obj.data.polygons) for i in excluded):
        raise ValueError('Invalid actual receiver face exclusion')
    rs = []
    for index, (tri, loops) in enumerate(zip(reference['triangles'], reference['triangle_loops'])):
        ps = [tuple(reference['vertices'][i]) for i in tri]
        box = bounds(ps)
        if min(abs(p[0]) for p in ps) < .84 or box[1][1] < y_min or box[0][1] > y_max or box[1][2] < .19 or box[0][2] > 1.06:
            continue
        ns = [tuple(reference['normals'][i]) for i in loops]
        one = ownership._patch((None, [Vector(p) for p in ps], [(0, 1, 2)], [[Vector(n) for n in ns]]))[0]
        if one[1][0] * ps[0][0] <= 0:
            continue
        rs.append({'index': index, 'points': ps, 'normals': ns, 'box': box, 'patch': one})
    if len(rs) < 100:
        raise ValueError('Incomplete finite original side reference')
    m = obj.data
    m.calc_loop_triangles()
    before = [tuple(n.vector) for n in m.corner_normals]
    if not valid(before):
        raise ValueError('Invalid current native field')
    per_face = {}
    for t in m.loop_triangles:
        per_face.setdefault(t.polygon_index, []).append(t)
    targets = list(before)
    authored = {}
    owned = []
    unmatched = []
    lookup = []
    for face in m.polygons:
        ps = [tuple(m.vertices[v].co) for v in face.vertices]
        box = bounds(ps)
        if min(abs(p[0]) for p in ps) < .84 or box[0][1] < y_min or box[1][1] > y_max or box[0][2] < .19 or box[1][2] > 1.06:
            continue
        if face.index in excluded:
            continue
        if face.normal.x * ps[0][0] <= (0. if is_body else .15):
            continue
        eligible = [r for r in rs if overlaps(box, r['box'], 1e-6)
                    and sum(face.normal[i]*r['patch'][1][i] for i in range(3)) >= .99985
                    and max(abs(sum((p[i]-r['points'][0][i])*r['patch'][1][i] for i in range(3))) for p in ps) <= 1e-6]
        patch = [r['patch'] for r in eligible]
        if not all(ownership._covers([tuple(m.vertices[v].co) for v in tri.vertices], patch) for tri in per_face[face.index]):
            unmatched.append(face.index)
            continue
        owned.append(face.index)
        for li in face.loop_indices:
            point = tuple(m.vertices[m.loops[li].vertex_index].co)
            choices = []
            for r in eligible:
                hit = geometry.closest_point_on_tri(Vector(point), *[Vector(p) for p in r['points']])
                distance = math.dist(point, tuple(hit))
                if distance > 2e-6:
                    continue
                value = geometry.barycentric_transform(hit, *[Vector(p) for p in r['points']], *[Vector(n) for n in r['normals']])
                choices.append((distance, r['index'], unit(value)))
            if not choices:
                raise ValueError('Owned actual sheet corner lacks finite reference')
            distance, ri, value = min(choices)
            if any(angle(value, n) > .025 for d, _, n in choices if d <= distance+1e-9):
                raise ValueError('Ambiguous native reference field at owned corner')
            weight = 1.
            target = unit(tuple((1-weight)*a+weight*b for a, b in zip(before[li], value)))
            targets[li] = target
            authored[li] = {'loop': li, 'vertex': m.loops[li].vertex_index, 'face': face.index, 'domain': 'original_outer_sheet', 'weight': weight}
            lookup.append({'loop': li, 'reference_triangle': ri, 'distance_m': distance, 'target': target})
    if len(owned) < 20:
        raise ValueError('Insufficient actual complete original sheet domain')
    # Continue only already-continuous corner fans on the actual thin bevel.
    # A complete triangle is bounded by its distances to one convex reference
    # triangle; no nearest-point-only assertion grants whole-face ownership.
    fans = {}
    for li in authored:
        fans.setdefault(m.loops[li].vertex_index, []).append(li)
    extensions = []
    rejected_fans = []
    owned_set = set(owned)
    for face in m.polygons:
        if face.index in owned_set or face.index in excluded:
            continue
        shared = [li for li in face.loop_indices if m.loops[li].vertex_index in fans]
        if not shared:
            continue
        ps = [tuple(m.vertices[v].co) for v in face.vertices]
        near = [r for r in rs if overlaps(bounds(ps), r['box'], .001201)]
        certs = []
        for tri in per_face[face.index]:
            pts = [tuple(m.vertices[v].co) for v in tri.vertices]
            candidates = []
            for r in near:
                ds = [math.dist(p, tuple(geometry.closest_point_on_tri(Vector(p), *[Vector(q) for q in r['points']]))) for p in pts]
                if max(ds) <= .001201:
                    candidates.append((max(ds), r['index']))
            if not candidates:
                break
            certs.append({'triangle': tri.index, 'convex_distance_bound_m': min(candidates)[0], 'reference_triangle': min(candidates)[1]})
        if len(certs) != len(per_face[face.index]):
            rejected_fans.append(face.index)
            continue
        for li in shared:
            matches = [old for old in fans[m.loops[li].vertex_index] if angle(before[old], before[li]) <= .025]
            if not matches:
                continue
            chosen = min(matches, key=lambda old: angle(before[old], before[li]))
            if any(angle(targets[chosen], targets[old]) > .025 for old in matches):
                raise ValueError('Conflicting originally continuous corner targets')
            targets[li] = targets[chosen]
            authored[li] = {'loop': li, 'vertex': m.loops[li].vertex_index, 'face': face.index, 'domain': 'actual_thin_bevel_fan', 'from_loop': chosen}
        extensions.append({'face': face.index, 'complete_triangles': certs})
    if not valid(targets):
        raise ValueError('Invalid prepared target field')
    return {'schema': 'door-and-complete-body-original-sheet-normal.v2', 'object': obj.name,
            'physical_sha256': digest(physical(obj)), 'reference_sha256': digest(reference),
            'before': before, 'targets': targets, 'targets_sha256': digest(targets),
            'authorship': list(authored.values()), 'original_sheet_faces': owned,
            'unmatched_candidate_faces': unmatched, 'bounded_bevel_faces': extensions,
            'unextended_adjacent_faces': rejected_fans, 'reference_lookups': lookup,
            'excluded_authored_receiver_faces': sorted(excluded),
            'original_sheet_y_domain_m': [y_min, y_max],
            'triangles': len(m.loop_triangles), 'source_saved': False}


def apply(obj, plan, encode):
    import bpy
    if obj.name != plan['object'] or digest(physical(obj)) != plan['physical_sha256']:
        raise ValueError('Actual source changed after preparation')
    before = [tuple(n.vector) for n in obj.data.corner_normals]
    if before != plan['before'] or digest(plan['targets']) != plan['targets_sha256']:
        raise ValueError('Actual targets or original field changed')
    selected = {r['loop'] for r in plan['authorship']}
    if any(plan['targets'][i] != n for i, n in enumerate(before) if i not in selected):
        raise ValueError('Unauthorized target outside authored domain')
    old = obj.data
    old_physical = physical(obj)
    stage = old.copy()
    obj.data = stage
    try:
        # Preserve the old independent native codes exactly outside ownership.
        independent = all(e.use_edge_sharp for e in old.edges)
        codes = [tuple(c.value) for c in old.attributes['custom_normal'].data] if old.has_custom_normals and independent else None
        encoded = encode(stage, plan['targets'])
        if not encoded['passed']:
            raise ValueError('Unchanged0.025-degree native encoding guard failed')
        if codes is not None:
            for i, code in enumerate(codes):
                if i not in selected:
                    stage.attributes['custom_normal'].data[i].value = code
            stage.update()
        actual = [tuple(n.vector) for n in stage.corner_normals]
        if not valid(actual):
            raise ValueError('Invalid actual native field after encoding')
        outside = [angle(a, b) for i, (a, b) in enumerate(zip(before, actual)) if i not in selected]
        if max(outside, default=0) > .025 or max(angle(a, b) for a, b in zip(plan['targets'], actual)) > .025:
            raise ValueError('Native target or outside normal bound failed')
        if physical(obj) != old_physical:
            raise ValueError('Normal authorship changed a protected physical field')
        stage.calc_loop_triangles()
        if len(stage.loop_triangles) != plan['triangles']:
            raise ValueError('Unexpected triangle cost')
        if codes is not None and any(actual[i] != n for i, n in enumerate(before) if i not in selected):
            raise ValueError('Independent unowned native codes did not preserve their fields')
        return {'object': obj.name, 'status': 'corner_native_trial_passed',
                'original_sheet_faces': len(plan['original_sheet_faces']),
                'bounded_bevel_faces': len(plan['bounded_bevel_faces']), 'authored_corners': len(selected),
                'unmatched_candidate_faces': plan['unmatched_candidate_faces'],
                'unextended_adjacent_faces': plan['unextended_adjacent_faces'],
                'maximum_outside_corner_degrees': max(outside, default=0),
                'outside_vectors_exact': all(actual[i] == n for i, n in enumerate(before) if i not in selected),
                'outside_corners': len(before)-len(selected), 'encoding': encoded,
                'geometry_UV_material_transform_exact': True, 'triangles': plan['triangles'],
                'complete_interpolated_field_check_pending': True, 'source_saved': False,
                'visual_acceptance': None, 'human_approval_reference': None}
    except BaseException:
        obj.data = old
        if stage.users == 0:
            bpy.data.meshes.remove(stage)
        raise
