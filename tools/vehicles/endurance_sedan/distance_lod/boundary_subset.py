"""Delete only verified disjoint private lower-LOD component domains."""
import copy
import json
import math
import bmesh
import bpy


def angle(a, b):
    na, nb = math.hypot(*a), math.hypot(*b)
    if not all(math.isfinite(x) for x in (*a, *b)) or abs(na-1)>1e-6 or abs(nb-1)>1e-6:
        raise ValueError('Invalid raw copy normal')
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross),sum(x*y for x,y in zip(a,b))))


def partition(original, entry, *, targets, hook, expected_entry_digest, expected_original_digest):
    if hook.digest(entry) != expected_entry_digest:
        raise ValueError('Stale or changed caller-locked component entry')
    if hook.digest(hook.raw_fields(original)) != expected_original_digest:
        raise ValueError('Stale or changed original private batch')
    if entry.get('batch') != original.name:
        raise ValueError('Component entry names a different native batch')
    components=entry.get('components')
    if not isinstance(components,list) or not components:
        raise ValueError('Missing complete component partition')
    names=[c.get('source_component') for c in components]
    if any(not isinstance(n,str) or not n for n in names) or len(set(names))!=len(names):
        raise ValueError('Ambiguous component semantic partition')
    for c in components:
        if any(type(c.get(k)) is not int or c[k]<0 for k in ('vertex_start','triangle_start')) or any(type(c.get(k)) is not int or c[k]<=0 for k in ('vertex_count','triangle_count')):
            raise ValueError('Invalid typed component range')
    if original.modifiers or original.type != 'MESH':
        raise ValueError('Final native modifier-free batch required')
    mesh = original.data
    mesh.calc_loop_triangles()
    if any(len(p.vertices) != 3 for p in mesh.polygons) or len(mesh.polygons) != len(mesh.loop_triangles):
        raise ValueError('Explicit final triangle polygon inventory required for deletion')
    components = entry.get('components')
    if not components or {c['source_component'] for c in components} != set(json.loads(original['source_components'])):
        raise ValueError('Complete native component provenance required')
    occupied_v, occupied_f, drop_v, drop_f = set(), set(), set(), set()
    for c in components:
        vertices = set(range(c['vertex_start'], c['vertex_start'] + c['vertex_count']))
        faces = set(range(c['triangle_start'], c['triangle_start'] + c['triangle_count']))
        if not vertices or not faces or occupied_v & vertices or occupied_f & faces:
            raise ValueError('Missing/overlapping native component ranges')
        if max(vertices) >= len(mesh.vertices) or max(faces) >= len(mesh.polygons):
            raise ValueError('Native component range outside actual batch')
        if any(not set(mesh.polygons[i].vertices) <= vertices for i in faces):
            raise ValueError('Native component face crosses its recorded vertex domain')
        occupied_v |= vertices
        occupied_f |= faces
        if c['source_component'] in targets:
            drop_v |= vertices
            drop_f |= faces
    if occupied_v != set(range(len(mesh.vertices))) or occupied_f != set(range(len(mesh.polygons))) or not drop_v:
        raise ValueError('Incomplete actual final batch partition')
    if any((bool(set(e.vertices) & drop_v) and not set(e.vertices) <= drop_v) for e in mesh.edges):
        raise ValueError('Target components share an edge with retained native geometry')
    return {'occupied_v':occupied_v,'occupied_f':occupied_f,'drop_v':drop_v,'drop_f':drop_f}


def verify_retained(original, obj, entry, vertex_map, face_map, edge_map, *, targets, hook,
                    expected_entry_digest, expected_original_digest):
    domain=partition(original,entry,targets=targets,hook=hook,expected_entry_digest=expected_entry_digest,expected_original_digest=expected_original_digest)
    occupied_v,occupied_f,drop_v,drop_f=(domain[k] for k in ('occupied_v','occupied_f','drop_v','drop_f'))
    mesh=original.data
    before=hook.raw_fields(original)
    for mapping,expected_keys,size in ((vertex_map,occupied_v-drop_v,len(obj.data.vertices)),(face_map,occupied_f-drop_f,len(obj.data.polygons)),(edge_map,{e.index for e in mesh.edges if not set(e.vertices)&drop_v},len(obj.data.edges))):
        if set(mapping)!=expected_keys or any(type(v) is not int for v in mapping.values()) or set(mapping.values())!=set(range(size)) or len(mapping)!=size:
            raise ValueError('Incomplete retained native element map')
    components=entry['components']
    after = hook.raw_fields(obj)
    for key in ('matrix', 'parent', 'materials', 'modifier_types'):
        if before[key] != after[key]:
            raise ValueError('Retained batch object field changed: ' + key)
    for old, new in vertex_map.items():
        if before['vertices'][old] != after['vertices'][new]:
            raise ValueError('Retained native position changed')
    for old, new in edge_map.items():
        if {vertex_map[i] for i in before['edges'][old]} != set(after['edges'][new]) or before['sharp'][old] != after['sharp'][new]:
            raise ValueError('Retained native edge/sharp changed')
    maximum_angle, exact_normals, checked_loops = 0., True, 0
    for old, new in face_map.items():
        old_face, new_face = mesh.polygons[old], obj.data.polygons[new]
        expected = [vertex_map[i] for i in old_face.vertices]
        actual = list(new_face.vertices)
        if not any(actual == expected[k:] + expected[:k] for k in range(3)):
            raise ValueError('Retained native face/winding changed')
        if old_face.material_index != new_face.material_index or old_face.use_smooth != new_face.use_smooth:
            raise ValueError('Retained native material/smoothing changed')
        new_loop_by_vertex = {obj.data.loops[i].vertex_index: i for i in new_face.loop_indices}
        for old_loop in old_face.loop_indices:
            new_loop = new_loop_by_vertex[vertex_map[mesh.loops[old_loop].vertex_index]]
            if set(before['uv']) != set(after['uv']) or any(before['uv'][name][old_loop] != after['uv'][name][new_loop] for name in before['uv']):
                raise ValueError('Retained raw native UV changed')
            a, b = before['normals'][old_loop], after['normals'][new_loop]
            maximum_angle = max(maximum_angle, angle(a, b))
            exact_normals &= a == b
            checked_loops += 1
    if maximum_angle > .025:
        raise ValueError('Retained native decoded field copy exceeded .025 degrees: ' + str(maximum_angle))
    retained = []
    for c in components:
        if c['source_component'] in targets:
            continue
        vertices = sorted(vertex_map[i] for i in range(c['vertex_start'], c['vertex_start'] + c['vertex_count']))
        faces = sorted(face_map[i] for i in range(c['triangle_start'], c['triangle_start'] + c['triangle_count']))
        if vertices != list(range(vertices[0], vertices[0] + len(vertices))) or faces != list(range(faces[0], faces[0] + len(faces))):
            raise ValueError('Retained source component indices are no longer contiguous')
        row = copy.deepcopy(c)
        row.update(vertex_start=vertices[0], triangle_start=faces[0], range_domain='Final native private batch after deletion of disjoint boundary components; original retained fields verified')
        retained.append(row)
    obj['source_components'] = json.dumps([c['source_component'] for c in retained])
    obj['lod_index'] = int(original['lod_index'])
    new_entry = {k: copy.deepcopy(entry[k]) for k in ('lod', 'parent', 'material')}
    new_entry.update(batch=obj.name, components=retained, triangles_after=len(obj.data.polygons),
        method='Private native subset without rebake; complete retained element/field correspondence',
        prior_batch=original.name, prior_entry_digest=hook.digest(entry))
    proof = {'original_batch': original.name, 'new_batch': obj.name,
        'removed_components': [c['source_component'] for c in components if c['source_component'] in targets],
        'removed_vertices': sorted(drop_v), 'removed_triangles': sorted(drop_f),
        'retained_old_to_new_vertices': vertex_map, 'retained_old_to_new_triangles': face_map,
        'retained_old_to_new_edges': edge_map, 'retained_checked_corners': checked_loops,
        'positions_UVs_materials_winding_smooth_sharp_matrix_parent_exact': True,
        'decoded_corner_vectors_exact': exact_normals, 'maximum_decoded_corner_angle_degrees': maximum_angle,
        'raw_before_sha256': hook.digest(before), 'raw_after_sha256': hook.digest(after)}
    return new_entry, proof

def trim_native_components(original, entry, collection, *, targets, hook,
                           expected_entry_digest, expected_original_digest):
    domain=partition(original,entry,targets=targets,hook=hook,expected_entry_digest=expected_entry_digest,expected_original_digest=expected_original_digest)
    occupied_v,occupied_f,drop_v,drop_f=(domain[k] for k in ('occupied_v','occupied_f','drop_v','drop_f'))
    mesh=original.data
    before = hook.raw_fields(original)
    obj = original.copy()
    obj.data = original.data.copy()
    obj.name = original.name + '_BoundaryRemainder'
    collection.objects.link(obj)
    obj.matrix_world = original.matrix_world.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        verts, faces, edges = list(bm.verts), list(bm.faces), list(bm.edges)
        bmesh.ops.delete(bm, geom=[verts[i] for i in sorted(drop_v)], context='VERTS')
        bm.verts.index_update()
        bm.faces.index_update()
        bm.edges.index_update()
        vertex_map = {i: v.index for i, v in enumerate(verts) if v.is_valid}
        face_map = {i: f.index for i, f in enumerate(faces) if f.is_valid}
        edge_map = {i: e.index for i, e in enumerate(edges) if e.is_valid}
        if set(vertex_map) != occupied_v - drop_v or set(face_map) != occupied_f - drop_f:
            raise ValueError('Native delete changed unexpected elements')
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    bpy.context.view_layer.update()
    new_entry,proof=verify_retained(original,obj,entry,vertex_map,face_map,edge_map,targets=targets,hook=hook,
        expected_entry_digest=expected_entry_digest,expected_original_digest=expected_original_digest)
    return obj,new_entry,proof
