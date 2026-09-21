"""Original Meridian recessed-groove construction; caller owns scene I/O."""
import math
import json
from collections import defaultdict

import bpy
from mathutils import Vector


POLICY = {'schema': 'source-tire-groove38.v1', 'members': ['LOD0_Tire_FL', 'LOD0_Tire_FR', 'LOD0_Tire_RL', 'LOD0_Tire_RR'], 'original_radial_stations': 52, 'floor_radial_stations': 36, 'original_floor_radius_m': 0.3393, 'floor_radius_m': 0.339625, 'centers_x_m': [-0.068, -0.023, 0.023, 0.068], 'top_half_width_m': 0.003, 'floor_half_width_m': 0.002, 'tire_radius_m': 0.3433, 'tire_width_m': 0.255, 'uv_meters_per_repeat': 0.25, 'original_triangles_per_tire': 4728, 'new_triangles_per_tire': 4472, 'retained_triangles_per_tire': 3480, 'source_profile_ast_sha256': 'd4e2e7fec17d985c6ca8b586ec10da2918ed85c1bd43fdea16635c5332c47af4', 'form_error_m': 0.001, 'native_normal_degrees': 0.025, 'raw_normal_unit_error': 1e-06, 'uv_error': 1e-06, 'identity': 'Original fictional tessellation refinement; outer tire silhouette, original shoulder reliefs, sidewall and bead remain exact.'}
NAMES = tuple(POLICY['members'])
CENTERS = (-.068, -.023, .023, .068)
SEGMENTS = 36
RADIUS = .339625


def require(value, message):
    if not value:
        raise ValueError(message)


def capture_mesh(mesh):
    mesh.calc_loop_triangles()
    return {'vertices': [tuple(v.co) for v in mesh.vertices],
            'faces': [tuple(f.vertices) for f in mesh.loop_triangles],
            'normals': [[tuple(mesh.corner_normals[i].vector) for i in f.loops]
                        for f in mesh.loop_triangles],
            'uvs': {layer.name: [[tuple(layer.data[i].uv) for i in f.loops]
                                for f in mesh.loop_triangles] for layer in mesh.uv_layers},
            'materials': [f.material_index for f in mesh.loop_triangles]}


def build_mesh(old, materials, mesh_name, encoder, *, source_stations=52):
    # Default52 preserves the historical groove38 stage. Current44 is a
    # separately selected and verified construction using the same four strips.
    require(type(source_stations) is int and source_stations in (52, 44),
            'Unmeasured tire station policy')
    expected_raw = {52: 4728, 44: 4268}[source_stations]
    saving = 16 * (source_stations - SEGMENTS)
    expected_final = expected_raw - saving
    require(len(old['faces']) == expected_raw and set(old['uvs']) == {'SurfaceMeters'},
            'Changed original tire inventory')
    vertices = list(old['vertices'])
    incident = defaultdict(list)
    for face, normals in zip(old['faces'], old['normals']):
        for vertex, normal in zip(face, normals):
            incident[vertex].append(normal)

    def theta(index):
        _, y, z = vertices[index]
        value = math.atan2(y, z) % math.tau
        return 0. if abs(value-math.tau) < 1e-6 or value < 1e-6 else value

    def ring(x):
        ids = [i for i, v in enumerate(old['vertices']) if abs(v[0]-x) < 1e-7
               and math.hypot(v[1], v[2]) > .338]
        ids.sort(key=theta)
        require(len(ids) == source_stations, 'Missing complete original groove ring')
        require(all(abs(theta(i)-j*math.tau/source_stations) < 1e-6 for j, i in enumerate(ids)),
                'Wrong original angular station')
        return ids

    new_normals = {}
    removed = set()
    strips = []
    grooves = []
    for center in CENTERS:
        original_rings = [ring(center+dx) for dx in (-.003, -.002, .002, .003)]
        allowed_vertices = set(sum(original_rings, []))
        old_faces = [i for i, face in enumerate(old['faces']) if set(face) <= allowed_vertices]
        require(len(old_faces) == 6 * source_stations and not removed.intersection(old_faces),
                'Changed finite groove strip domain')
        removed.update(old_faces)
        rings = [original_rings[0]]
        for source_ring in original_rings[1:3]:
            x = vertices[source_ring[0]][0]
            generated = []
            for j in range(SEGMENTS):
                angle = j*math.tau/SEGMENTS
                index = len(vertices)
                vertices.append((x, RADIUS*math.sin(angle), RADIUS*math.cos(angle)))
                generated.append(index)
                u = angle*source_stations/math.tau
                left = int(math.floor(u)) % source_stations
                right = (left+1) % source_stations
                a, b = Vector(vertices[source_ring[left]]), Vector(vertices[source_ring[right]])
                # Intersect the original polygonal ring edge with this radial ray.
                tangent = Vector((0., math.cos(angle), -math.sin(angle)))
                fraction = -a.dot(tangent)/(b-a).dot(tangent)
                require(-1e-6 <= fraction <= 1+1e-6, 'Source angular interpolation outside edge')
                na = Vector(incident[source_ring[left]][0])
                nb = Vector(incident[source_ring[right]][0])
                new_normals[index] = tuple(na.lerp(nb, max(0., min(1., fraction))).normalized())
            rings.append(generated)
        rings.append(original_rings[-1])
        triangles = []
        for left, right in zip(rings, rings[1:]):
            i = j = 0
            while i < len(left) or j < len(right):
                next_left = (i+1)/len(left) if i < len(left) else math.inf
                next_right = (j+1)/len(right) if j < len(right) else math.inf
                a, b = left[i % len(left)], right[j % len(right)]
                if abs(next_left-next_right) <= 1e-12:
                    c, d = right[(j+1) % len(right)], left[(i+1) % len(left)]
                    triangles.extend(((a,b,c), (a,c,d)))
                    i += 1
                    j += 1
                elif next_left < next_right:
                    triangles.append((a,b,left[(i+1) % len(left)]))
                    i += 1
                else:
                    triangles.append((a,b,right[(j+1) % len(right)]))
                    j += 1
        require(len(triangles) == 2 * source_stations + 4 * SEGMENTS, 'Incomplete mixed-ring tessellation')
        strips.extend(triangles)
        grooves.append({'center_x_m': center, 'original_faces': old_faces,
                        'original_rings': original_rings, 'new_rings': rings,
                        'generated_triangle_count': len(triangles)})

    retained = [i for i in range(len(old['faces'])) if i not in removed]
    faces = [old['faces'][i] for i in retained] + strips
    used = sorted(set(v for face in faces for v in face))
    remap = {v: i for i, v in enumerate(used)}
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata([vertices[i] for i in used], [], [tuple(remap[v] for v in face) for face in faces])
    mesh.update()
    for material in materials:
        mesh.materials.append(material)
    uv = mesh.uv_layers.new(name='SurfaceMeters')
    targets = []
    for index, polygon in enumerate(mesh.polygons):
        polygon.use_smooth = True
        if index < len(retained):
            source_index = retained[index]
            polygon.material_index = old['materials'][source_index]
            targets.extend(old['normals'][source_index])
            for loop, value in zip(polygon.loop_indices, old['uvs']['SurfaceMeters'][source_index]):
                uv.data[loop].uv = value
        else:
            face = faces[index]
            axes = [a for a in range(3) if a != max(range(3), key=lambda k: abs(polygon.normal[k]))]
            for loop, vertex in zip(polygon.loop_indices, face):
                targets.append(new_normals[vertex] if vertex in new_normals else incident[vertex][0])
                uv.data[loop].uv = tuple(vertices[vertex][a]/.25 for a in axes)
    encoding = encoder.encode(mesh, targets)
    require(encoding['passed'], 'Native groove normal encoding guard failed')
    mesh.calc_loop_triangles()
    require(len(mesh.loop_triangles) == expected_final, 'Unexpected final tire triangle count')
    after = capture_mesh(mesh)
    max_outside_angle = 0.
    max_outside_uv = 0.
    for index, source_index in enumerate(retained):
        require(tuple(tuple(after['vertices'][v]) for v in after['faces'][index]) ==
                tuple(tuple(old['vertices'][v]) for v in old['faces'][source_index]),
                'Original outside triangle positions/order changed')
        for a, b in zip(after['normals'][index], old['normals'][source_index]):
            max_outside_angle = max(max_outside_angle, encoder.angle(a,b))
        for a, b in zip(after['uvs']['SurfaceMeters'][index], old['uvs']['SurfaceMeters'][source_index]):
            max_outside_uv = max(max_outside_uv, *(abs(x-y) for x,y in zip(a,b)))
    require(max_outside_angle <= .025 and max_outside_uv <= 1e-6, 'Outside native field changed')
    return mesh, {'before': old, 'after': after, 'targets': [list(v) for v in targets], 'retained_original_face_indices': retained,
            'old_modified_face_indices': sorted(removed),
            'new_modified_face_indices': list(range(len(retained), len(faces))),
            'outside_maximum_normal_degrees': max_outside_angle,
            'outside_maximum_uv_error': max_outside_uv, 'encoding': encoding,
            'grooves': grooves, 'triangle_saving': saving}


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def capture(obj):
    from . import reserve_correspondence26, bevel_reserve26
    from .qa.shoulder_checkpoint import material_fields
    require(obj.type == 'MESH' and not obj.modifiers, 'Evaluated native tire required')
    codes = obj.data.attributes.get('custom_normal')
    properties = {key: value for key, value in obj.items() if key not in ('lod_index', 'maximum_lod')}
    for key in ('lod_index', 'maximum_lod'):
        if key in obj:
            require(obj[key] == 0, 'Unexpected tire distance metadata')
    return plain({'name': obj.name, 'mesh': capture_mesh(obj.data),
        'raw': reserve_correspondence26.raw(obj), 'modifiers': bevel_reserve26.modifier_state(obj),
        'normal_codes': [list(row.value) for row in codes.data] if codes is not None else None,
        'matrix_basis': [list(row) for row in obj.matrix_basis],
        'matrix_parent_inverse': [list(row) for row in obj.matrix_parent_inverse],
        'properties': properties, 'material_response': material_fields(obj.data)})


def make(obj):
    from . import corner_encoding
    require(obj.name in NAMES, 'Wrong semantic tire')
    before = capture(obj)
    mesh, witness = build_mesh(before['mesh'], list(obj.data.materials),
                               obj.name + '_Groove38', corner_encoding)
    obj.data = mesh
    after = capture(obj)
    return plain({'policy': POLICY, 'before_native': before, 'after_native': after,
                  'construction': witness})


def current_matches(obj, witness):
    """Exact recapture for an already independently verified immutable witness."""
    require(obj.name in NAMES and witness['policy'] == POLICY, 'Unknown high-tire source revision')
    before, after = witness['before_native'], witness['after_native']
    require(before['name'] == after['name'] == obj.name, 'Mismatched high tire member')
    require(capture(obj) == after, 'Actual high tire differs from current construction witness')
    for key in ('matrix_basis', 'matrix_parent_inverse', 'properties', 'material_response', 'modifiers'):
        require(before[key] == after[key], 'Tire rigid/material domain changed: ' + key)
    require(before['raw']['parent'] == after['raw']['parent'] == obj.name.replace('LOD0_Tire_', 'Wheel_'),
            'Wrong original/current tire rigid parent')
    return {'status': 'passed', 'name': obj.name, 'actual_native_fields_exact': True}


def verify_current(obj, witness):
    """Independently replay a bound current checkpoint, with no source scene I/O."""
    from collections import Counter, defaultdict
    import numpy as np
    from . import corner_encoding, complete_boundary26
    from .qa.lod_self_intersections import shell_certificate
    current_matches(obj, witness)
    before, after = witness['before_native'], witness['after_native']
    generated = None
    try:
        generated, replay = build_mesh(before['mesh'], list(obj.data.materials),
                                        '_PrivateGroove38Check', corner_encoding)
        require(plain(replay) == witness['construction'], 'Groove constructor/domain/target replay differs')
        require(plain(capture_mesh(generated)) == after['mesh'], 'Complete regenerated native groove mesh differs')
        codes = generated.attributes.get('custom_normal')
        require(codes is not None and [list(row.value) for row in codes.data] == after['normal_codes'],
                'Regenerated native corner codes differ')
        changed = {}
        for key, mesh, indices in (
            ('before', before['mesh'], replay['old_modified_face_indices']),
            ('after', after['mesh'], replay['new_modified_face_indices'])):
            changed[key] = {'name': obj.name, 'vertices': mesh['vertices'],
                            'triangles': [mesh['faces'][index] for index in indices]}
        form = {key: complete_boundary26.complete(changed[key], changed[other], maximum=.001)
                for key, other in (('before', 'after'), ('after', 'before'))}
        require(all(row['status'] == 'passed' for row in form.values()), 'Complete groove surface bound failed')
        actual = after['mesh']
        row = {'name': obj.name, 'vertices': actual['vertices'], 'triangles': actual['faces']}
        shell = shell_certificate(row)
        require(shell['status'] == 'passed', 'Groove indexed shell or exact self intersection failed')
        links = defaultdict(list)
        for face in actual['faces']:
            for i, vertex in enumerate(face):
                links[vertex].append((face[(i + 1) % 3], face[(i + 2) % 3]))
        for vertex, edges in links.items():
            degree = Counter(v for edge in edges for v in edge)
            reached = {edges[0][0]}
            while True:
                extended = reached | {b for a, b in edges if a in reached} | {a for a, b in edges if b in reached}
                if reached == extended:
                    break
                reached = extended
            require(reached == set(degree) and all(value == 2 for value in degree.values()),
                    'Groove vertex link has more than one fan: ' + str(vertex))
        points = np.asarray(actual['vertices'])[actual['faces']]
        areas = np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1) * .5
        normals = np.asarray(actual['normals']).reshape(-1, 3)
        unit_error = float(np.abs(np.linalg.norm(normals, axis=1) - 1).max())
        require(float(areas.min()) > 1e-12 and unit_error <= 1e-6, 'Native tire area/unit guard failed')
        return {'status': 'passed', 'name': obj.name, 'triangles': len(actual['faces']),
                'retained_original_triangles': len(replay['retained_original_face_indices']),
                'minimum_area_m2': float(areas.min()), 'maximum_raw_normal_unit_error': unit_error,
                'form': form, 'shell': shell, 'single_vertex_fans': len(links),
                'replay_exact': True, 'source_saved': False}
    finally:
        if generated is not None:
            bpy.data.meshes.remove(generated)
