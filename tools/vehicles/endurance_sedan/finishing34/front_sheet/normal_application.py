"""Transactional normal-only application with complete native field guards."""
import collections
import math

from . import field_support as support
from . import sheet_reference as sheet


def prepare(obj, targets, selected_faces, evidence):
    state = sheet.native_state(obj)
    targets = [tuple(n) for n in targets]
    if len(targets) != len(state['normals']):
        raise ValueError('Incomplete prepared target inventory')
    selected = sorted(set(selected_faces))
    if (not selected or any(type(fi) is not int or not 0 <= fi < len(state['face_loops']) for fi in selected)
            or any(not sheet.numeric(n, 3) or abs(math.hypot(*n)-1) > 1e-6 for n in targets)):
        raise ValueError('Invalid finite target authorship')
    owned = {li for fi in selected for li in state['face_loops'][fi]}
    if any(targets[i] != n for i, n in enumerate(state['normals']) if i not in owned):
        raise ValueError('Requested normal changed outside the declared complete faces')
    actual = support.fields(obj)
    plan = {'schema': 'complete-front-sheet-normal-only.v1', 'object': obj.name,
            'physical': actual, 'physical_sha256': support.digest(actual), 'before': state['normals'],
            'targets': targets, 'selected_faces': selected,
            'authorship': [{'face': fi, 'loops': state['face_loops'][fi], 'targets': [targets[li] for li in state['face_loops'][fi]]}
                           for fi in selected],
            'evidence': evidence, 'triangles': len(state['triangles']), 'normal_guard_degrees': .025,
            'authored_field': 'Normalized affine interpolation of these explicit requested actual-corner targets on each unchanged actual triangle',
            'source_saved': False, 'visual_acceptance': None}
    plan['targets_sha256'] = support.digest(targets)
    return plan


def boundary(mesh, before, targets, actual, selected):
    edges = collections.defaultdict(list)
    for face in mesh.polygons:
        for li in face.loop_indices:
            edges[mesh.loops[li].edge_index].append(face.index)
    rows = []
    for ei, fs in sorted(edges.items()):
        if len(fs) != 2 or not any(fi in selected for fi in fs):
            continue
        endpoints = []
        for vi in mesh.edges[ei].vertices:
            ls = [next(li for li in mesh.polygons[fi].loop_indices if mesh.loops[li].vertex_index == vi) for fi in fs]
            endpoints.append({'vertex': vi, 'position': tuple(mesh.vertices[vi].co), 'loops': ls,
                              'before_degrees': support.angle(before[ls[0]], before[ls[1]]),
                              'requested_degrees': support.angle(targets[ls[0]], targets[ls[1]]),
                              'native_degrees': support.angle(actual[ls[0]], actual[ls[1]])})
        rows.append({'edge': ei, 'faces': fs, 'both_authored': all(fi in selected for fi in fs), 'endpoints': endpoints})
    return rows


def apply(obj, plan, encode):
    import bpy
    if plan['normal_guard_degrees'] != .025 or support.digest(plan['targets']) != plan['targets_sha256']:
        raise ValueError('Prepared target guard/inventory changed')
    if obj.name != plan['object'] or support.digest(support.fields(obj)) != plan['physical_sha256']:
        raise ValueError('Prepared source geometry/layout changed')
    if [tuple(n.vector) for n in obj.data.corner_normals] != list(plan['before']):
        raise ValueError('Prepared actual native input field changed')
    selected = set(plan['selected_faces'])
    if not selected or any(type(fi) is not int or not 0 <= fi < len(obj.data.polygons) for fi in selected):
        raise ValueError('Invalid complete selected face inventory')
    owned = {li for fi in selected for li in obj.data.polygons[fi].loop_indices}
    if any(tuple(n) != plan['before'][i] for i, n in enumerate(plan['targets']) if i not in owned):
        raise ValueError('Normal authorship escaped complete selected faces')
    original = obj.data
    staged = original.copy()
    try:
        result = encode(staged, plan['targets'])
        actual = [tuple(n.vector) for n in staged.corner_normals]
        if not result['passed'] or len(actual) != len(plan['targets']) or any(abs(math.hypot(*n)-1) > 1e-6 for n in actual):
            raise ValueError('Native encoding/raw-normal failure')
        staged.calc_loop_triangles()
        all_fields, outside = [], []
        for t in staged.loop_triangles:
            all_fields.append({'triangle': t.index, **support.complete_affine_angle([plan['targets'][li] for li in t.loops], [actual[li] for li in t.loops])})
            if t.polygon_index not in selected:
                outside.append({'triangle': t.index, **support.complete_affine_angle([plan['before'][li] for li in t.loops], [actual[li] for li in t.loops])})
        edges = boundary(staged, plan['before'], plan['targets'], actual, selected)
        obj.data = staged
        if support.fields(obj) != plan['physical'] or len(staged.loop_triangles) != plan['triangles']:
            raise ValueError('Normal-only transaction changed physical fields')
        proof = {'status': 'passed-unsaved-native-normal-domain', 'object': obj.name,
                 'new_targets': len(owned), 'authored_faces': len(selected), 'triangle_delta': 0,
                 'geometry_topology_uv_material_transform_exact': True, 'native_encoding': result,
                 'whole_requested_native_fields': all_fields, 'whole_outside_fields': outside,
                 'whole_requested_native_max_degrees': max(r['maximum_degrees'] for r in all_fields),
                 'whole_outside_max_degrees': max((r['maximum_degrees'] for r in outside), default=0),
                 'maximum_old_to_new_corner_degrees': max(support.angle(a, b) for a, b in zip(plan['before'], actual)),
                 'boundary': edges, 'visual_acceptance': None, 'source_saved': False}
        staged = None
        return proof
    except Exception:
        obj.data = original
        raise
    finally:
        if staged is not None and staged.users == 0:
            bpy.data.meshes.remove(staged)
