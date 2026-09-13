"""Current-source tank repair and explicitly authored flat manufactured faces.

Reference rows must be captured from the actual receiver before its hose cut.
All tools are explicit callbacks; this module has no report or source-file IO.
"""
import math
import bpy


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _unit(vector):
    length = math.hypot(*vector)
    if not math.isfinite(length) or length <= 0:
        raise ValueError('Invalid tank facet normal')
    return tuple(v/length for v in vector)


def _normal(points):
    return _unit(_cross(_sub(points[1], points[0]), _sub(points[2], points[0])))


def _quality(obj, evaluated_counts):
    result = evaluated_counts(obj)
    keys = ('nonmanifold_edges', 'duplicate_faces', 'degenerate_faces',
            'degenerate_triangles', 'triangulated_nonmanifold_edges',
            'triangulated_duplicate_faces', 'nonfinite_corner_normals',
            'zero_corner_normals', 'nonunit_corner_normals')
    if any(result[k] for k in keys):
        raise ValueError('Tank native mesh quality failed')
    return result


def repair_tank(obj, original_receiver, hose, *, row, boolean_surface,
                encode, closest, boundary_shell, exact_scan, evaluated_counts):
    """Stage a bounded repair; publish object data only after every guard passes."""
    if obj.modifiers or len(obj.data.materials) != 1:
        raise ValueError('Tank requires applied geometry and one retained material')
    reference = original_receiver
    if not reference['triangles'] or set(reference['uvs']) != {u.name for u in obj.data.uv_layers}:
        raise ValueError('Missing current original receiver geometry or UV layers')
    before = row(obj)
    stage = obj.copy()
    stage.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(stage)
    applied = False
    try:
        initial_targets = [tuple(n.vector) for n in stage.data.corner_normals]
        initial_encoding = None
        if not stage.data.has_custom_normals:
            initial_encoding = encode(stage.data, initial_targets)
            if not initial_encoding['passed']:
                raise ValueError('Initial tank native encoding failed')
        correction = boolean_surface.repair(stage, exact_scan, evaluated_counts)
        if correction.get('maximum_common_normal_angle_degrees', 0) > .025:
            raise ValueError('Boolean correction exceeds retained corner target guard')
        mesh = stage.data
        mesh.calc_loop_triangles()
        world = [tuple(stage.matrix_world @ v.co) for v in mesh.vertices]
        ref_points = [[reference['vertices'][v] for v in tri] for tri in reference['triangles']]
        ref_normals = [_normal(points) for points in ref_points]
        targets = [None] * len(mesh.loops)
        faces = []
        max_uv_encoding = 0.
        for face in mesh.polygons:
            triangles = [t for t in mesh.loop_triangles if t.polygon_index == face.index]
            largest = max(triangles, key=lambda t: math.hypot(*_cross(
                _sub(world[t.vertices[1]], world[t.vertices[0]]),
                _sub(world[t.vertices[2]], world[t.vertices[0]]))))
            face_points = [world[v] for v in face.vertices]
            normal = _normal([world[v] for v in largest.vertices])
            origin = world[largest.vertices[0]]
            planarity = max(abs(_dot(_sub(p, origin), normal)) for p in face_points)
            if planarity > 1e-6:
                raise ValueError('Tank polygon is not planar within the existing1um guard')
            if any(_dot(normal, _cross(_sub(world[t.vertices[1]], world[t.vertices[0]]),
                                      _sub(world[t.vertices[2]], world[t.vertices[0]]))) <= 0 for t in triangles):
                raise ValueError('Tank facet winding is inconsistent')
            local_normal = _normal([tuple(mesh.vertices[v].co) for v in largest.vertices])
            for loop in face.loop_indices:
                targets[loop] = local_normal
            part = {'name': obj.name + '_face', 'vertices': [list(p) for p in world],
                    'triangles': [list(t.vertices) for t in triangles]}
            parallel = [i for i, n in enumerate(ref_normals) if _dot(normal, n) > .99999]
            reference_patch = {**reference, 'triangles': [reference['triangles'][i] for i in parallel]}
            support = boundary_shell(part, reference_patch, maximum=1e-6) if parallel else {'status': 'failed'}
            if support['status'] == 'passed':
                for loop in face.loop_indices:
                    point = world[mesh.loops[loop].vertex_index]
                    options = [(closest(point, ref_points[i]), i) for i in parallel]
                    (distance, weights), original_tri = min(options, key=lambda x: x[0][0])
                    if distance > 1e-6:
                        raise ValueError('Tank UV corner lacks original surface ownership')
                    original_loops = reference['triangle_loops'][original_tri]
                    for name, values in reference['uvs'].items():
                        old = [values[i] for i in original_loops]
                        exact = next((k for k, p in enumerate(ref_points[original_tri]) if tuple(p) == point), None)
                        uv = tuple(old[exact]) if exact is not None else tuple(sum(weights[k]*old[k][j] for k in range(3)) for j in range(2))
                        mesh.uv_layers[name].data[loop].uv = uv
                        actual = tuple(mesh.uv_layers[name].data[loop].uv)
                        max_uv_encoding = max(max_uv_encoding, *(abs(a-b) for a, b in zip(actual, uv)))
                domain = 'original_outer_receiver'
            else:
                support = boundary_shell(part, hose, maximum=1e-6)
                if support['status'] != 'passed':
                    raise ValueError('Tank face is neither original outer skin nor actual hose socket')
                domain = 'actual_hose_receiving_surface'
            faces.append({'polygon': face.index, 'domain': domain, 'full_triangles': len(triangles),
                          'maximum_planarity_m': planarity, 'support': support,
                          'new_local_normal_target': list(local_normal)})
        if max_uv_encoding > 1e-5:
            raise ValueError('Restored original UV exceeds existing native UV guard')
        encoded = encode(mesh, targets)
        if not encoded['passed'] or encoded['maximum_native_decoded_degrees'] > .025:
            raise ValueError('Authored flat tank field encoding failed')
        after = row(stage)
        if before['vertices'] != after['vertices'] or len(before['triangles']) != len(after['triangles']):
            raise ValueError('Tank repair changed original coordinates or triangle count')
        if before['materials'] != after['materials'] or set(after['triangle_materials']) != {0}:
            raise ValueError('Tank repair changed material ownership')
        quality = _quality(stage, evaluated_counts)
        self_result = exact_scan(after)
        if self_result['status'] != 'passed' or self_result['bad_pairs']:
            raise ValueError('Tank exact self check failed')
        surfaces = [boundary_shell(a, b, maximum=1e-6) for a, b in ((before, after), (after, before))]
        if any(r['status'] != 'passed' for r in surfaces):
            raise ValueError('Tank repair changes the complete original boundary')
        obj.data = mesh
        applied = True
        return {'initial_encoding': initial_encoding, 'boolean_repair': correction,
                'faces': faces, 'new_flat_field_encoding': encoded, 'maximum_uv_native_encoding': max_uv_encoding,
                'quality': quality, 'exact_self': self_result, 'complete_surface_correspondence': surfaces,
                'original_vertices_exact': True, 'triangle_delta': 0,
                'old_interpolation_preservation_claim': False}
    finally:
        data = stage.data
        bpy.data.objects.remove(stage, do_unlink=True)
        if not applied and data.users == 0:
            bpy.data.meshes.remove(data)
