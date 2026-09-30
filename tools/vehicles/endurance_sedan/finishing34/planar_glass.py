"""Separate native normals at the faces of an actual planar glass solid.

This intentionally changes only the source face smoothing domain. Solidify,
the editable sheet, and every evaluated geometric/UV/material value stay live.
"""
import math

NAMES = ('LOD0_Windshield', 'LOD0_Backlight')


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def unit(a):
    length = math.hypot(*a)
    if not math.isfinite(length) or length <= 0:
        raise ValueError('Invalid glass surface direction')
    return tuple(v/length for v in a)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def angle(a, b):
    a, b = unit(a), unit(b)
    return math.degrees(math.atan2(math.hypot(*cross(a, b)), dot(a, b)))


def prepare(obj):
    if obj.name not in NAMES or obj.type != 'MESH':
        raise ValueError('Expected declared front/rear pane')
    if [m.type for m in obj.modifiers] != ['SOLIDIFY']:
        raise ValueError('Expected live pane Solidify')
    modifier = obj.modifiers[0]
    if abs(modifier.thickness-.0045) > 1e-9 or modifier.offset != -1 or not modifier.use_even_offset:
        raise ValueError('Changed physical pane thickness construction')
    mesh = obj.data
    if mesh.has_custom_normals:
        raise ValueError('Unexpected existing custom glass normals')
    mesh.calc_loop_triangles()
    vertices = [tuple(v.co) for v in mesh.vertices]
    vectors = [cross(sub(vertices[t.vertices[1]], vertices[t.vertices[0]]),
                     sub(vertices[t.vertices[2]], vertices[t.vertices[0]]))
               for t in mesh.loop_triangles]
    plane = unit(tuple(math.fsum(n[i] for n in vectors) for i in range(3)))
    residual = max(abs(dot(plane, sub(v, vertices[0]))) for v in vertices)
    if residual > 2e-7 or any(angle(n, plane) > .001 for n in vectors):
        raise ValueError('Pane is not the declared consistently oriented planar sheet')
    if not all(p.use_smooth for p in mesh.polygons):
        raise ValueError('Expected untouched smooth source sheet')
    return {'name': obj.name, 'source_plane': plane, 'plane_residual_m': residual,
            'vertices': vertices, 'polygons': [list(p.vertices) for p in mesh.polygons],
            'source_triangle_count': len(mesh.loop_triangles), 'source_polygon_count': len(mesh.polygons)}


def apply(obj, plan):
    if prepare(obj) != plan:
        raise ValueError('Source pane changed after domain preparation')
    # Every source cell belongs to the same actual flat pane. Native Solidify
    # propagates flat face ownership to its opposed pane and manufactured rims.
    # This behavior is verified on the evaluated output by the caller.
    for face in obj.data.polygons:
        face.use_smooth = False
    obj.data.update()


def verify(obj, plan):
    import bpy
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        mesh.calc_loop_triangles()
        vertices = [tuple(v.co) for v in mesh.vertices]
        normal_rows = [tuple(n.vector) for n in mesh.corner_normals]
        if any(not all(math.isfinite(v) for v in n) or abs(math.hypot(*n)-1) > 1e-6 for n in normal_rows):
            raise ValueError('Invalid evaluated native glass normal')
        outer, inner, rim = [], [], []
        triangles = []
        for tri in mesh.loop_triangles:
            points = [vertices[v] for v in tri.vertices]
            geometric = unit(cross(sub(points[1], points[0]), sub(points[2], points[0])))
            alignment = dot(geometric, plan['source_plane'])
            if alignment > .999999:
                domain = 'outer'; target = plan['source_plane']; outer.append(tri.index)
            elif alignment < -.999999:
                domain = 'inner'; target = tuple(-v for v in plan['source_plane']); inner.append(tri.index)
            elif abs(alignment) < 1e-4:
                domain = 'rim'; target = geometric; rim.append(tri.index)
            else:
                raise ValueError('Unexpected nonplanar glass return')
            errors = [angle(normal_rows[i], target) for i in tri.loops]
            if max(errors) > .025:
                raise ValueError('Complete native planar-domain target exceeded0.025degrees')
            triangles.append({'triangle': tri.index, 'polygon': tri.polygon_index,
                              'loops': list(tri.loops), 'domain': domain,
                              'target': target, 'corner_degrees': errors})
        if len(outer) != plan['source_triangle_count'] or len(inner) != len(outer) or not rim:
            raise ValueError('Incomplete native sheet/return domains')
        if any(p.use_smooth for p in mesh.polygons):
            raise ValueError('Native Solidify did not retain face-domain separation')
        return {'name': obj.name, 'triangles': triangles, 'outer_count': len(outer),
                'inner_count': len(inner), 'rim_count': len(rim),
                'maximum_complete_target_degrees': max(max(t['corner_degrees']) for t in triangles),
                'whole_triangle_argument': 'Each target is constant on its complete actual triangle. All three unit native corner vectors lie in its convex positive cone below0.025degrees, so normalized interpolants stay in that cone.',
                'native_unit_guard': 1e-6, 'plan': plan}
    finally:
        evaluated.to_mesh_clear()
