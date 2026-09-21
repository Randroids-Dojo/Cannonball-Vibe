"""Actual pre-late rear cap provenance and complete finite carrier ownership."""
import math
from mathutils import Vector, geometry
from . import rear_surface_field as original
from . import staged_normals as native
from .floor_panels import freeze

MARKER = 'cb_fascia_cap'
STRENGTH = '__mod_weightednormals_faceweight'
SCHEMA = 'actual-pre-late-rear-cap.v1'


def _attribute(mesh, name, required=True):
    attr = mesh.attributes.get(name)
    if attr is None:
        if required:
            raise ValueError('Missing rear carrier provenance: ' + name)
        return None
    if attr.domain != 'FACE' or attr.data_type != 'INT':
        raise ValueError('Invalid rear carrier provenance type: ' + name)
    if name == MARKER and any(row.value not in (0, 1, 2) for row in attr.data):
        raise ValueError('Undeclared rear carrier face class')
    return attr


def capture(obj, reference, ownership):
    """Root calls once before late cuts; the existing original field proves scope."""
    if obj.get('cb_rear_cap_carrier_captured'):
        raise ValueError('Capture actual rear cap exactly once')
    freeze(obj)
    plan = original.prepare(obj, reference, original.PROFILE, ownership)
    selected = {row['face'] for row in plan['new_cap_domain']}
    if len(selected) < 10:
        raise ValueError('Incomplete actual pre-late cap')
    mesh = obj.data
    marker = _attribute(mesh, MARKER, required=False)
    if marker is None:
        marker = mesh.attributes.new(name=MARKER, type='INT', domain='FACE')
    if any(row.value == 2 for row in marker.data):
        raise ValueError('Rear cap class already assigned')
    strength = _attribute(mesh, STRENGTH)
    triangles = []
    for face in mesh.polygons:
        if face.index not in selected:
            continue
        if strength.data[face.index].value != 16384 or len(face.vertices) != 3:
            raise ValueError('Unexpected pre-late cap triangle or strength')
        marker.data[face.index].value = 2
        triangles.append(list(face.vertices))
    payload = {
        'schema': SCHEMA,
        'object': obj.name,
        'coordinate_frame': [list(row) for row in obj.matrix_world],
        'coordinate_space': 'native-source-local-meters',
        'original_reference_sha256': native.digest(reference),
        'physical_sha256': native.fingerprint(mesh),
        'vertices': [list(v.co) for v in mesh.vertices],
        'triangles': triangles,
        'original_cap_faces': sorted(selected),
    }
    packet = {'payload': payload, 'sha256': native.digest(payload)}
    obj['cb_rear_cap_carrier_captured'] = True
    return packet


def validate(packet, obj, reference):
    if type(packet) is not dict or set(packet) != {'payload', 'sha256'}:
        raise ValueError('Incomplete actual carrier packet')
    p = packet['payload']
    keys = {'schema', 'object', 'coordinate_frame', 'coordinate_space',
            'original_reference_sha256', 'physical_sha256', 'vertices',
            'triangles', 'original_cap_faces'}
    if type(p) is not dict or set(p) != keys:
        raise ValueError('Incomplete actual carrier payload')
    if p['schema'] != SCHEMA or p['object'] != obj.name or obj.name not in original.PROFILE['semantics']:
        raise ValueError('Actual carrier object identity differs')
    frame = p['coordinate_frame']
    if type(frame) is not list or len(frame) != 4 or not all(
        type(row) is list and len(row) == 4 and all(type(v) in (float, int) and math.isfinite(v) for v in row)
        for row in frame
    ):
        raise ValueError('Malformed actual carrier coordinate frame')
    if p['coordinate_frame'] != [list(row) for row in obj.matrix_world] or p['coordinate_space'] != 'native-source-local-meters':
        raise ValueError('Actual carrier coordinate identity differs')
    for value in (packet['sha256'], p['physical_sha256'], p['original_reference_sha256']):
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Malformed actual carrier digest')
    if p['original_reference_sha256'] != native.digest(reference) or packet['sha256'] != native.digest(p):
        raise ValueError('Actual carrier content differs')
    def vec(v):
        return type(v) is list and len(v) == 3 and all(type(c) in (float, int) and math.isfinite(c) for c in v)
    if type(p['vertices']) is not list or not p['vertices'] or not all(vec(v) for v in p['vertices']):
        raise ValueError('Malformed carrier vertices')
    if type(p['triangles']) is not list or len(p['triangles']) < 10:
        raise ValueError('Incomplete actual triangle partition')
    seen = set()
    for tri in p['triangles']:
        if type(tri) is not list or len(tri) != 3 or not all(type(i) is int and 0 <= i < len(p['vertices']) for i in tri) or len(set(tri)) != 3:
            raise ValueError('Invalid actual triangle indices')
        key = tuple(sorted(tri))
        if key in seen:
            raise ValueError('Duplicate actual carrier triangle')
        seen.add(key)
        a, b, c = (Vector(p['vertices'][i]) for i in tri)
        if (b-a).cross(c-a).length_squared == 0:
            raise ValueError('Degenerate actual carrier triangle')
    faces = p['original_cap_faces']
    if type(faces) is not list or len(faces) != len(p['triangles']) or any(type(i) is not int or i < 0 for i in faces) or faces != sorted(set(faces)):
        raise ValueError('Invalid original cap face inventory')
    return p


def prepare(obj, packet, reference, ownership):
    """Compose unchanged side targets with this new, fully bounded cap field."""
    p = validate(packet, obj, reference)
    plan = original.prepare(obj, reference, original.PROFILE, ownership)
    mesh = obj.data
    marker = _attribute(mesh, MARKER)
    strength = _attribute(mesh, STRENGTH)
    old_cap_faces = {fi for fi, domain in plan['domains'].items() if domain.startswith('new-analytic')}
    old_cap_loops = {li for fi in old_cap_faces for li in mesh.polygons[fi].loop_indices}
    removed = set(old_cap_loops)
    for row in plan['propagated']:
        if any(seed in old_cap_loops for seed in row['seeds']):
            removed.add(row['loop'])
    # An unproved tagged face may not keep a side-seeded target either.
    for face in mesh.polygons:
        if marker.data[face.index].value == 2:
            removed.update(face.loop_indices)
    for li in removed:
        plan['targets'].pop(li, None)
    plan['domains'] = {fi: domain for fi, domain in plan['domains'].items() if fi not in old_cap_faces}
    plan['propagated'] = [row for row in plan['propagated'] if row['loop'] not in removed]
    vertices = [Vector(v) for v in p['vertices']]
    normals = [[Vector((0, -1, 0))]*3 for _ in p['triangles']]
    patch = ownership._patch((None, vertices, p['triangles'], normals))
    projected = [Vector((v.x, 0., v.z)) for v in vertices]
    xz_patch = ownership._patch((None, projected, p['triangles'], normals))
    planes = [[vertices[i] for i in tri] for tri in p['triangles']]
    triangles = {}
    for tri in mesh.loop_triangles:
        triangles.setdefault(tri.polygon_index, []).append([tuple(mesh.vertices[i].co) for i in tri.vertices])
    outcomes = []
    accepted = []
    cap_candidates = set(plan['cap_candidate_faces'])
    for face in mesh.polygons:
        marked = marker.data[face.index].value == 2
        if not marked and face.index not in cap_candidates:
            continue
        row = {'face': face.index, 'loops': list(face.loop_indices), 'marker': marker.data[face.index].value,
               'strength': strength.data[face.index].value, 'area_m2': float(face.area)}
        outcomes.append(row)
        if not marked or row['strength'] != 16384:
            row['accepted'] = False
            row['reason'] = 'missing-actual-carrier-provenance'
            continue
        actual = triangles[face.index]
        projected_triangles = [[(v[0], 0., v[2]) for v in tri] for tri in actual]
        collapsed = [i for i, tri in enumerate(projected_triangles) if (Vector(tri[1])-Vector(tri[0])).cross(Vector(tri[2])-Vector(tri[0])).length_squared == 0]
        full_3d = all(ownership._covers(tri, patch) for tri in actual)
        full_xz = not collapsed and all(ownership._covers(tri, xz_patch) for tri in projected_triangles)
        distances = [min((geometry.closest_point_on_tri(mesh.vertices[i].co, *tri)-mesh.vertices[i].co).length for tri in planes) for i in face.vertices]
        row.update(whole_3d_owned_1um=full_3d, whole_xz_owned_1um=full_xz,
                   corner_distances_m=distances, zero_xz_triangles=collapsed)
        row['accepted'] = full_3d and full_xz and max(distances) <= 2e-6
        if not row['accepted']:
            row['reason'] = 'incomplete-actual-carrier-support'
            continue
        accepted.append(face.index)
        plan['domains'][face.index] = 'new-analytic-actual-pre-late-cap'
        for li in face.loop_indices:
            plan['targets'][li] = original.cap_normal(mesh.vertices[mesh.loops[li].vertex_index].co.x, original.PROFILE)
    if len(accepted) < 10:
        raise ValueError('Incomplete final actual cap domain')
    plan['actual_carrier_sha256'] = packet['sha256']
    plan['actual_carrier_outcomes'] = outcomes
    plan['actual_carrier_accepted_faces'] = accepted
    plan['removed_previous_cap_targets'] = sorted(removed)
    plan['new_cap_domain'] = [row for row in outcomes if row['accepted']]
    plan['scope'] = 'Original complete-owned side field plus new continuous cap on the actual pre-late evaluated triangle carrier. Complete3D1um, completeXZ1um and corner2um guards all required. No cap fan propagation or old-cap interpolation preservation claim.'
    return plan


def apply(obj, packet, reference, ownership):
    plan = prepare(obj, packet, reference, ownership)
    result = native.apply_targets(obj, plan)
    result['corner_targets'] = {str(li): n for li, n in plan['targets'].items()}
    return result
