"""Explicit smooth field on complete finite original wheel-cut facets."""
import math
from mathutils import Matrix, Vector

PROFILE = {'radius_m': .4483, 'facets': 64, 'wheel_y_m': [-1.46, 1.46],
           'wheel_z_m': .3433, 'absolute_x_range_m': [.46, 1.30],
           'plane_and_footprint_guard_m': 1e-6,
           'face_alignment_min': .99999,
           'authorship': 'New radial return field; original outer-skin normals remain unselected.'}


def prepare(obj, native):
    if obj.modifiers or obj.type != 'MESH' or obj.matrix_world != Matrix.Identity(4):
        raise ValueError('Arch field requires final ground-frame native geometry')
    mesh = obj.data
    if not mesh.has_custom_normals:
        raise ValueError('Missing original decoded corner field')
    mesh.calc_loop_triangles()
    triangles_by_face = {}
    for triangle in mesh.loop_triangles:
        triangles_by_face.setdefault(triangle.polygon_index, []).append(triangle)
    before = [tuple(n.vector) for n in mesh.corner_normals]
    if not all(native.valid_normal(n) for n in before):
        raise ValueError('Invalid native input normal')
    guard = PROFILE['plane_and_footprint_guard_m']
    radius, count = PROFILE['radius_m'], PROFILE['facets']
    apothem = radius * math.cos(math.pi / count)
    half_edge = radius * math.sin(math.pi / count)
    targets, domains = {}, []
    for face in mesh.polygons:
        points = [mesh.vertices[i].co for i in face.vertices]
        if not all(.46 - guard <= abs(p.x) <= 1.30 + guard for p in points):
            continue
        if min(p.x for p in points) * max(p.x for p in points) <= 0:
            continue
        choices = []
        for cy in PROFILE['wheel_y_m']:
            for facet in range(count):
                a = (facet + .5) * math.tau / count
                ny, nz = math.cos(a), math.sin(a)
                desired = Vector((0, -ny, -nz))
                if not all(triangle.normal.dot(desired) >= PROFILE['face_alignment_min']
                           for triangle in triangles_by_face[face.index]):
                    continue
                plane_error = max(abs((p.y - cy) * ny + (p.z - .3433) * nz - apothem) for p in points)
                footprint = max(abs(-(p.y - cy) * nz + (p.z - .3433) * ny) for p in points)
                if plane_error <= guard and footprint <= half_edge + guard:
                    choices.append((cy, facet, plane_error, footprint))
        if len(choices) > 1:
            raise ValueError('Ambiguous complete finite cutter facet')
        if not choices:
            continue
        cy, facet, error, footprint = choices[0]
        for li in face.loop_indices:
            p = mesh.vertices[mesh.loops[li].vertex_index].co
            target = Vector((0, cy - p.y, .3433 - p.z)).normalized()
            targets[li] = tuple(target)
        domains.append({'face': face.index, 'evaluated_triangles': [t.index for t in triangles_by_face[face.index]], 'wheel_y_m': cy, 'facet': facet,
                        'plane_error_m': error, 'tangent_extent_m': footprint,
                        'vertices_m': [list(p) for p in points]})
    return {'object': obj.name, 'before': before, 'targets': targets,
            'ambiguous_corners': [], 'profile': PROFILE,
            'profile_sha256': native.digest(PROFILE), 'complete_facet_domains': domains,
            'input_target_error_max_degrees': max((native.angle(before[i], n) for i, n in targets.items()), default=0),
            'scope': 'Authored smooth radial normals only on complete finite original cutter facets; geometry and all unselected fields remain independently guarded.'}


def apply(obj, native):
    plan = prepare(obj, native)
    if not plan['targets']:
        return {'object': obj.name, 'status': 'no-complete-cutter-facets', 'target_count': 0}
    return native.apply_targets(obj, plan)
