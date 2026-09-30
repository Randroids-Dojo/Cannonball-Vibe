"""Retessellate only native n-gons with a degenerate evaluated triangle.

Keep every original vertex, face boundary, ownership value and corner UV.
The caller retains its bounded vertex cleanup, exact self repair and complete
assembly/carrier checks. This helper does not merge neighboring face domains.
"""
from collections import Counter
import math
import bmesh
import bpy
from . import geometry as geo


def _boundary(faces):
    result = Counter()
    for vertices in faces:
        for a, b in zip(vertices, vertices[1:] + vertices[:1]):
            result[tuple(sorted((a, b)))] += 1 if a < b else -1
    return {key: value for key, value in result.items() if value}


def _angle(a, b):
    cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.sqrt(sum(v*v for v in cross)), sum(x*y for x, y in zip(a, b))))


def repair(obj, encode=None):
    """Call before bounded vertex cleanup; an ineligible triangle stays for it."""
    if obj.modifiers:
        raise ValueError('Sliver-face repair requires applied native geometry')
    mesh = obj.data
    for name in ('cb_fascia_cap', '__mod_weightednormals_faceweight'):
        attr = mesh.attributes.get(name)
        if attr is not None and (attr.domain != 'FACE' or attr.data_type != 'INT'):
            raise ValueError('Malformed sliver-face ownership: ' + name)
    mesh.calc_loop_triangles()
    bad = [tri for tri in mesh.loop_triangles
           if (mesh.vertices[tri.vertices[1]].co-mesh.vertices[tri.vertices[0]].co).cross(
               mesh.vertices[tri.vertices[2]].co-mesh.vertices[tri.vertices[0]].co).length/2 <= 1e-12]
    selected = {tri.polygon_index for tri in bad if len(mesh.polygons[tri.polygon_index].vertices) > 3}
    if not selected:
        return {'changed': False, 'remaining_degenerate_triangles': len(bad)}
    vertices = [tuple(v.co) for v in mesh.vertices]
    faces = [list(f.vertices) for f in mesh.polygons]
    corner_lookup = [{mesh.loops[li].vertex_index: li for li in f.loop_indices} for f in mesh.polygons]
    if any(len(lookup) != len(face) for lookup, face in zip(corner_lookup, faces)):
        raise ValueError('Repeated source face vertex')
    normals = [tuple(n.vector) for n in mesh.corner_normals]
    uv = {layer.name: [tuple(value.uv) for value in layer.data] for layer in mesh.uv_layers}
    # Blender may omit an all-zero built-in material_index attribute after
    # BMesh conversion; compare the actual polygon material indices below.
    attrs = {a.name: [r.value for r in a.data] for a in mesh.attributes
             if a.domain == 'FACE' and a.data_type == 'INT' and a.name != 'material_index'}
    materials = [f.material_index for f in mesh.polygons]
    smooth = [f.use_smooth for f in mesh.polygons]
    old_count = len(mesh.loop_triangles)
    parent_name = '_sliver_original_face'
    if mesh.attributes.get(parent_name) is not None:
        raise ValueError('Sliver repair already in progress')
    stage = obj.copy()
    stage.data = mesh.copy()
    bpy.context.scene.collection.objects.link(stage)
    applied = False
    try:
        bm = bmesh.new()
        bm.from_mesh(stage.data)
        bm.faces.ensure_lookup_table()
        parent = bm.faces.layers.int.new(parent_name)
        for face in bm.faces:
            face[parent] = face.index + 1
        bmesh.ops.triangulate(bm, faces=[bm.faces[i] for i in sorted(selected)],
                              quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.to_mesh(stage.data)
        bm.free()
        current = stage.data
        current.update()
        current.calc_loop_triangles()
        if [tuple(v.co) for v in current.vertices] != vertices or len(current.loop_triangles) != old_count:
            raise ValueError('Sliver triangulation changed vertices or triangle count')
        parent_rows = current.attributes[parent_name]
        owners = [value.value-1 for value in parent_rows.data]
        children = {i: [] for i in range(len(faces))}
        targets = [None] * len(current.loops)
        for face in current.polygons:
            owner = owners[face.index]
            if not 0 <= owner < len(faces) or not set(face.vertices) <= set(faces[owner]):
                raise ValueError('Invalid sliver parent ownership')
            children[owner].append(list(face.vertices))
            if owner not in selected and list(face.vertices) != faces[owner]:
                raise ValueError('Unselected face changed')
            if face.material_index != materials[owner] or face.use_smooth != smooth[owner]:
                raise ValueError('Changed sliver face finish')
            for name, values in attrs.items():
                attr = current.attributes.get(name)
                if attr is None or attr.domain != 'FACE' or attr.data_type != 'INT' or attr.data[face.index].value != values[owner]:
                    raise ValueError('Changed sliver face ownership: ' + name)
            for li in face.loop_indices:
                old_loop = corner_lookup[owner][current.loops[li].vertex_index]
                if any(tuple(current.uv_layers[name].data[li].uv) != values[old_loop] for name, values in uv.items()):
                    raise ValueError('Changed sliver corner UV')
                targets[li] = normals[old_loop]
        for owner, parts in children.items():
            if _boundary(parts) != _boundary([faces[owner]]):
                raise ValueError('Changed original face boundary')
        remaining = []
        for tri in current.loop_triangles:
            a, b, c = [current.vertices[i].co for i in tri.vertices]
            if (b-a).cross(c-a).length/2 <= 1e-12:
                return {
                    'changed': False,
                    'attempted': True,
                    'staged_trial_discarded': True,
                    'reason': 'Same-face triangulation left unresolved degenerate geometry',
                    'selected_original_faces': sorted(selected),
                    'original_degenerate_triangles': [
                        {'triangle': t.index, 'face': t.polygon_index,
                         'vertices': list(t.vertices),
                         'points': [list(mesh.vertices[i].co) for i in t.vertices]}
                        for t in bad
                    ],
                    'trial_unresolved_original_face': owners[tri.polygon_index],
                    'trial_unresolved_vertices': list(tri.vertices),
                    'remaining_degenerate_triangles': len(bad),
                    'scope': 'Original input retained exactly; subsequent strict ownership-safe vertex cleanup and all final gates are still required.'
                }
        initial_deltas = [_angle(tuple(n.vector), target) for n, target in zip(current.corner_normals, targets)]
        initial_maximum = max(initial_deltas, default=0.)
        encoding = None
        if any(not math.isfinite(delta) or delta > .025 for delta in initial_deltas):
            if encode is None:
                raise ValueError('Native sliver targets require bounded re-encoding')
            # The reviewed encoder may replace normal-code spaces, but cannot
            # change geometry, UVs, finish or the discrete parent ownership.
            def conserved():
                return ([tuple(v.co) for v in current.vertices],
                        [(tuple(f.vertices), f.material_index, f.use_smooth) for f in current.polygons],
                        {layer.name: [tuple(v.uv) for v in layer.data] for layer in current.uv_layers},
                        {a.name: [v.value for v in a.data] for a in current.attributes if a.domain == 'FACE' and a.data_type == 'INT'})
            before_encoding = conserved()
            encoding = encode(current, targets)
            if type(encoding) is not dict or encoding.get('passed') is not True or conserved() != before_encoding:
                raise ValueError('Rejected sliver target encoding or changed its physical data')
        maximum_normal_delta = 0.
        for actual, target in zip(current.corner_normals, targets):
            value = tuple(actual.vector)
            if not all(math.isfinite(v) for v in value) or abs(math.sqrt(sum(v*v for v in value))-1) > 1e-6:
                raise ValueError('Invalid retessellated native normal')
            delta = _angle(value, target)
            if not math.isfinite(delta) or delta > .025:
                raise ValueError('Changed sliver native corner field')
            maximum_normal_delta = max(maximum_normal_delta, delta)
        current.attributes.remove(current.attributes[parent_name])
        counts = geo.evaluated_counts(stage)
        if any(counts[key] for key in ('duplicate_faces', 'nonmanifold_edges',
                                       'triangulated_duplicate_faces', 'triangulated_nonmanifold_edges',
                                       'nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals')):
            raise ValueError('Retessellated mesh failed topology or normal guards')
        obj.data = current
        applied = True
        return {'changed': True, 'selected_original_faces': sorted(selected),
                'vertices_exact': True, 'triangle_count_exact': True,
                'all_original_face_boundaries_exact': True, 'all_face_ownership_exact': True,
                'all_corner_uvs_exact': True, 'maximum_native_corner_delta_degrees': maximum_normal_delta,
                'initial_native_corner_delta_degrees': initial_maximum, 'native_encoding': encoding,
                'remaining_degenerate_triangles': len(remaining),
                'counts': counts, 'scope': 'Same-face tessellation only. Full exact self and complete affected surface/carrier verification remain required.'}
    finally:
        data = stage.data
        bpy.data.objects.remove(stage, do_unlink=True)
        if not applied and data.users == 0:
            bpy.data.meshes.remove(data)
