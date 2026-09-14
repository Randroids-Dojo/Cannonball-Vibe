"""Current two-pane domain adapter; manufactured rim fields stay original.

Copied from frozen combined29 glass_field with only current source-domain binding,
plane eligibility and complete final witness verification added.
"""
import sys
sys.dont_write_bytecode=True
import json
import math

import bmesh
import numpy as np
from mathutils import Vector
from .binding import read, sha, digest, plain, CURRENT_GLASS

_construction_cache={}



def require(value,message):
    if not value:
        raise ValueError(message)


def verify_current_witness(source,record,native_record,dependencies):
    """Regenerate the actual flat source plane and every evaluated domain."""
    module=dependencies['planar_glass'];plan=record['plan'];mesh=source.data
    require(source.name in module.NAMES and source.parent and source.parent.name=='Visual_LOD0','Wrong current pane source/parent')
    require([m.type for m in source.modifiers]==['SOLIDIFY'],'Wrong current pane modifier inventory')
    modifier=source.modifiers[0]
    require(abs(modifier.thickness-.0045)<=1e-9 and modifier.offset==-1 and modifier.use_even_offset,
        'Changed current physical pane thickness profile')
    require(not mesh.has_custom_normals and not any(p.use_smooth for p in mesh.polygons),'Changed current native pane smoothing domains')
    require([list(v.co) for v in mesh.vertices]==plan['vertices'] and [list(p.vertices) for p in mesh.polygons]==plan['polygons'],
        'Current raw pane differs from original geometric checkpoint')
    mesh.calc_loop_triangles()
    points=[tuple(v.co) for v in mesh.vertices]
    vectors=[module.cross(module.sub(points[t.vertices[1]],points[t.vertices[0]]),module.sub(points[t.vertices[2]],points[t.vertices[0]])) for t in mesh.loop_triangles]
    plane=module.unit(tuple(math.fsum(n[i] for n in vectors) for i in range(3)))
    residual=max(abs(module.dot(plane,module.sub(p,points[0]))) for p in points)
    require(list(plane)==plan['source_plane'] and residual==plan['plane_residual_m']
        and residual<=2e-7 and all(module.angle(n,plane)<=.001 for n in vectors),'Wrong independently derived current pane plane')
    require(len(mesh.loop_triangles)==plan['source_triangle_count'] and len(mesh.polygons)==plan['source_polygon_count'],
        'Wrong original pane face inventory')
    actual=plain(module.verify(source,plan))
    require(actual==record,'Missing/extra/changed current pane or rim domain witness')
    evaluated=plain(dependencies['native_fields'].evaluated(source))
    require(evaluated==native_record,'Current complete evaluated pane geometry/UV/normal/material differs')
    domains=[r['domain'] for r in actual['triangles']]
    require({d:domains.count(d) for d in set(domains)}=={'outer':96,'inner':96,'rim':56},
        'Current exact two-pane/four-rim construction domain changed')
    return {'domains':domains,'source_plane':list(plane),'native_proof_sha256':digest(actual),
        'native_fields_sha256':digest(evaluated)}


def preflight(source,parent,context):
    import bpy
    from . import front_feature_current
    require(parent is not None and parent.name in {'Visual_LOD1','Visual_LOD2'},'Wrong current lower pane parent')
    front_feature_current.bind(bpy.data.objects['LOD0_FrontBumper'],context)
    require(context['profile']['current_glass']==CURRENT_GLASS,'Changed authorized current glass domain profile')
    expected=context['expected']
    require(sha(context['construction_path'])==expected['construction_sha256'],'Changed current glass construction companion')
    key=expected['construction_sha256']
    if key not in _construction_cache:
        data=read(context['construction_path'])['current_surface34']
        _construction_cache[key]={name:(data['glass'][name],data['final_native_fields'][name])
            for name in context['dependencies']['planar_glass'].NAMES}
    require(source.name in _construction_cache[key],'Missing current declared glass source')
    record,native=_construction_cache[key][source.name]
    result=verify_current_witness(source,record,native,context['dependencies'])
    result['binding']={'current_source_sha256':expected['source_sha256'],
        'construction_sha256':key,'caller_binding_digest':context['expected_binding_digest'],
        'profile_sha256':digest(CURRENT_GLASS),'original_native_fields_sha256':result['native_fields_sha256']}
    return result


def verify_output(obj,proof,expected_digest):
    """Full native output witness; no aggregate report flag grants acceptance."""
    from . import front_feature_current
    require(digest(proof)==expected_digest,'Caller current pane witness digest mismatch')
    mesh=obj.data;mesh.calc_loop_triangles()
    require(plain(physical(mesh))==proof['final_physical'],'Current lower pane physical/UV/material field changed')
    require([list(r) for r in obj.matrix_world]==proof['final_matrix'] and obj.parent.name==proof['parent'],
        'Current lower pane transform/parent changed')
    actual=[tuple(n.vector) for n in mesh.corner_normals];targets=proof['complete_target_normals']
    require(len(actual)==len(targets) and all(all(math.isfinite(v) for v in n) and abs(math.hypot(*n)-1)<=1e-6 for n in actual),
        'Invalid current lower pane raw normal field')
    errors=[angle(a,b) for a,b in zip(actual,targets)]
    require(max(errors)<=.025,'Current lower pane target-normal guard failed')
    reference=proof['source_geometry_and_target_corner_inventory'];rim=set(proof['current_rim_indices'])
    assignments=proof['field_assignments']
    require(len(assignments)==len(mesh.polygons) and [r['face'] for r in assignments]==list(range(len(mesh.polygons))),
        'Missing/duplicate complete current pane output assignment')
    found=set();rim_rows=[];constant_errors=[]
    for assignment,face in zip(assignments,mesh.polygons):
        ps=[tuple(mesh.vertices[v].co) for v in face.vertices]
        if assignment['domain']=='complete-original-variable-field-triangle':
            index=assignment['source_triangle']
            require(index in rim and index not in found,'Extra/duplicate current retained rim triangle')
            found.add(index);row=reference[index]
            require(key(ps)==key(row['points']),'Current rim triangle geometry changed')
            mapping={tuple(p):tuple(n) for p,n in zip(row['points'],row['normals'])}
            rim_rows.append(front_feature_current._base.affine.preserve_field(
                [mapping[tuple(mesh.vertices[mesh.loops[li].vertex_index].co)] for li in face.loop_indices],
                [actual[li] for li in face.loop_indices]))
        else:
            require(assignment['domain']=='complete-constant-original-patch' and assignment['patch'] in (0,1),
                'Unknown current plane-field owner')
            patch=assignment['patch'];normal=proof['constant_plane_normals'][patch]
            native_error=max(angle(normal,actual[li]) for li in face.loop_indices)
            original_error=max(angle(normal,n) for i in proof['constant_plane_source_indices'][patch] for n in reference[i]['normals'])
            bound=native_error+original_error
            require(bound<=.025,'Complete original/current constant-pane field guard failed')
            constant_errors.append(bound)
    require(found==rim and len(rim)==56,'Omitted current manufactured rim domain')
    return {'retained_complete_rim_triangles':len(found),'complete_output_triangles':len(mesh.loop_triangles),
        'maximum_current_target_degrees':max(errors),'complete_constant_field_upper_degrees':max(constant_errors),
        'complete_rim_affine_upper_degrees':max(r['angle_upper_degrees'] for r in rim_rows),
        'raw_unit_error_max':max(abs(math.hypot(*n)-1) for n in actual),
        'source_domains':{'outer':96,'inner':96,'rim':56},'rim_field_rows':rim_rows,
        'complete_field_argument':'Constant pane cones plus exact retained rim affine fields; all source/new plane coverage and affine UV checked by construction.'}


def angle(a, b):
    a, b = np.array(a, dtype=np.float64), np.array(b, dtype=np.float64)
    return math.degrees(math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b)))


def key(points):
    values = [tuple(p) for p in points]
    return min(tuple(values[i:] + values[:i]) for i in range(3))


def physical(mesh):
    return {'vertices': [tuple(v.co) for v in mesh.vertices],
            'polygons': [tuple(p.vertices) for p in mesh.polygons],
            'UV': {u.name: [tuple(v.uv) for v in u.data] for u in mesh.uv_layers},
            'materials': [m.name if m else None for m in mesh.materials],
            'polygon_materials': [p.material_index for p in mesh.polygons],
            'smooth': [p.use_smooth for p in mesh.polygons]}


def build(source, parent, collection, *, bake_batch, surfaces, encoder, certificate, context):
    current = preflight(source, parent, context)
    if source.name not in {'LOD0_Windshield', 'LOD0_Backlight'} or source.parent is None or source.parent.name != 'Visual_LOD0':
        raise ValueError('Exact cabin-pane source semantics required')
    if parent is None or parent.name not in {'Visual_LOD1', 'Visual_LOD2'}:
        raise ValueError('Only declared lower-LOD parents')
    if len(source.data.materials) != 1 or source.data.materials[0].name not in {'Material_Glass', 'Material_GlassPrivacy'}:
        raise ValueError('Cabin-pane material mismatch')
    name = 'LOD' + parent.name[-1] + '_Field_' + source.name.removeprefix('LOD0_')
    obj, original_entry = bake_batch(name, [source], parent, collection, source.data.materials[0])
    data = obj.data
    data.calc_loop_triangles()
    # Capture the actual evaluated original before the generic baker's encoding.
    graph = __import__('bpy').context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(graph)
    native = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        native.calc_loop_triangles()
        if native.uv_layers.active is None:
            raise ValueError('Missing original glass UV layer')
        for normal in native.corner_normals:
            values = tuple(normal.vector)
            if not all(math.isfinite(v) for v in values) or abs(math.hypot(*values) - 1.) > 1e-6:
                raise ValueError('Original raw glass normal is nonfinite or nonunit')
        transform = parent.matrix_world.inverted() @ source.matrix_world
        nt = transform.to_3x3().inverted().transposed()
        reference = []
        for tri in native.loop_triangles:
            points = [tuple(transform @ native.vertices[i].co) for i in tri.vertices]
            normals = [tuple((nt @ native.corner_normals[i].vector).normalized()) for i in tri.loops]
            uv = [tuple(native.uv_layers.active.data[i].uv) for i in tri.loops]
            gn = np.cross(np.array(points[1]) - points[0], np.array(points[2]) - points[0])
            gn /= np.linalg.norm(gn)
            reference.append({'points': points, 'normals': normals, 'UV': uv, 'normal': gn.tolist(),
                'constant': current['domains'][tri.index] in ('outer', 'inner') and max(angle(gn, n) for n in normals) <= .001,
                'current_domain': current['domains'][tri.index],
                'smooth': native.polygons[tri.polygon_index].use_smooth})
    finally:
        evaluated.to_mesh_clear()
    if len(reference) != len(data.polygons) or any(key(r['points']) != key([data.vertices[i].co for i in p.vertices]) for r, p in zip(reference, data.polygons)):
        raise ValueError('Native pre-bake triangle correspondence missing')
    edit = bmesh.new()
    edit.from_mesh(data)
    edit.faces.ensure_lookup_table()
    selected = {edit.faces[i] for i, r in enumerate(reference) if r['constant']}
    groups = []
    while selected:
        first = min(selected, key=lambda f: f.index)
        group, queue = {first}, [first]
        selected.remove(first)
        normal, plane = np.array(reference[first.index]['normal']), np.array(reference[first.index]['points'][0])
        while queue:
            face = queue.pop()
            for edge in face.edges:
                for other in edge.link_faces:
                    if other not in selected:
                        continue
                    r = reference[other.index]
                    if angle(normal, r['normal']) > .001 or max(abs((np.array(p) - plane) @ normal) for p in r['points']) > 1e-6:
                        continue
                    group.add(other)
                    selected.remove(other)
                    queue.append(other)
        if len(group) >= 2:
            groups.append((sorted(group, key=lambda f: f.index), normal, plane))
    patches, removed = [], set()
    for faces, normal, plane in groups:
        indices = [f.index for f in faces]
        removed.update(indices)
        # Every source corner in the patch must follow one affine UV field.
        points = np.array([p for i in indices for p in reference[i]['points']])
        uv = np.array([p for i in indices for p in reference[i]['UV']])
        basis = np.c_[points, np.ones(len(points))]
        fit = np.linalg.lstsq(basis, uv, rcond=None)[0]
        residual = float(np.max(np.abs(basis @ fit - uv)))
        if residual > 1e-6:
            raise ValueError('Constant glass patch does not preserve an affine UV field')
        patch_reference = (None, [Vector(p) for p in points],
            [tuple(range(i, i + 3)) for i in range(0, len(points), 3)],
            [[Vector(n) for n in reference[index]['normals']] for index in indices])
        patches.append({'indices': indices, 'normal': normal, 'plane': plane, 'UV_affine': fit,
                        'UV_source_residual': residual, 'coverage': surfaces._patch(patch_reference)})
    expected_panes={i for i,d in enumerate(current['domains']) if d in ('outer','inner')}
    if removed != expected_panes:
        raise ValueError('Incomplete or extra current plane-patch selection; rim triangles are protected')
    if len(patches) != 2:
        raise ValueError('Expected exactly two opposite connected planar constant interiors')
    if angle(patches[0]['normal'], patches[1]['normal']) < 179.99:
        raise ValueError('Laminate constant interiors are not opposite')
    for faces, _, _ in groups:
        result = bmesh.ops.dissolve_faces(edit, faces=faces, use_verts=True)
        regions = [item for item in result['region'] if isinstance(item, bmesh.types.BMFace)]
        if len(regions) != 1:
            raise ValueError('Constant patch did not produce one connected boundary')
        face = regions[0]
        boundary = [loop.vert for loop in face.loops]
        uv_layer = edit.loops.layers.uv.active
        uv_values = [loop[uv_layer].uv.copy() for loop in face.loops]
        smooth, material_index = face.smooth, face.material_index
        center_co = sum((v.co for v in boundary), Vector()) / len(boundary)
        center_uv = sum(uv_values, __import__('mathutils').Vector((0., 0.))) / len(uv_values)
        center = edit.verts.new(center_co)
        bmesh.ops.delete(edit, geom=[face], context='FACES_ONLY')
        for i, vertex in enumerate(boundary):
            next_index = (i + 1) % len(boundary)
            new_face = edit.faces.new((vertex, boundary[next_index], center))
            new_face.smooth, new_face.material_index = smooth, material_index
            for loop, uv in zip(new_face.loops, (uv_values[i], uv_values[next_index], center_uv)):
                loop[uv_layer].uv = uv
    if any(len(face.verts) != 3 for face in edit.faces):
        raise ValueError('Constant-patch center fan or retained triangle inventory failed')
    edit.to_mesh(data)
    edit.free()
    data.update()
    data.calc_loop_triangles()
    retained = {key(reference[i]['points']): (i, reference[i]) for i in range(len(reference)) if i not in removed}
    new_retained, targets, assignments, patch_triangles = set(), [None] * len(data.loops), [], [[], []]
    maximum_uv, target_original = 0., []
    patch_UV_errors = [0., 0.]
    for face in data.polygons:
        if len(face.vertices) != 3:
            raise ValueError('Nontriangle result')
        points = [tuple(data.vertices[i].co) for i in face.vertices]
        original = retained.get(key(points))
        if original:
            index, record = original
            new_retained.add(index)
            mapping = {tuple(p): (n, uv) for p, n, uv in zip(record['points'], record['normals'], record['UV'])}
            for loop in face.loop_indices:
                target, uv = mapping[tuple(data.vertices[data.loops[loop].vertex_index].co)]
                targets[loop] = target
                maximum_uv = max(maximum_uv, max(abs(x - y) for x, y in zip(uv, data.uv_layers.active.data[loop].uv)))
                target_original.append(loop)
            assignments.append({'face': face.index, 'domain': 'complete-original-variable-field-triangle', 'source_triangle': index})
        else:
            owners = [i for i, p in enumerate(patches) if surfaces._covers(points, p['coverage'])]
            if len(owners) != 1:
                raise ValueError('Whole generated triangle lacks a unique constant source patch')
            owner = owners[0]
            p = patches[owner]
            patch_triangles[owner].append(points)
            for loop in face.loop_indices:
                point = tuple(data.vertices[data.loops[loop].vertex_index].co)
                targets[loop] = tuple(p['normal'])
                uv = np.r_[point, 1.] @ p['UV_affine']
                error = float(np.max(np.abs(uv - tuple(data.uv_layers.active.data[loop].uv))))
                maximum_uv = max(maximum_uv, error)
                patch_UV_errors[owner] = max(patch_UV_errors[owner], error)
            assignments.append({'face': face.index, 'domain': 'complete-constant-original-patch', 'patch': owner})
    if new_retained != set(range(len(reference))) - removed or any(t is None for t in targets):
        raise ValueError('Original variable-field or final-corner inventory incomplete')
    if maximum_uv > 1e-6:
        raise ValueError('UV field bound failed')
    complete_UV_bounds = [p['UV_source_residual'] + error for p, error in zip(patches, patch_UV_errors)]
    if any(not math.isfinite(error) or error > 1e-6 for error in complete_UV_bounds):
        raise ValueError('Complete original/generated glass UV field bound failed')
    for i, patch in enumerate(patches):
        inverse = (None, [Vector(p) for tri in patch_triangles[i] for p in tri],
            [tuple(range(j, j + 3)) for j in range(0, len(patch_triangles[i]) * 3, 3)],
            [[Vector(patch['normal'])] * 3 for _ in patch_triangles[i]])
        reverse = surfaces._patch(inverse)
        if not all(surfaces._covers(reference[index]['points'], reverse) for index in patch['indices']):
            raise ValueError('Original constant patch is not completely covered in reverse')
    before_encoding = physical(data)
    sharp_before = [e.use_edge_sharp for e in data.edges]
    encoding = encoder(data, targets)
    if not encoding['passed'] or physical(data) != before_encoding:
        raise ValueError('Native target/physical encoding guard failed')
    actual = [tuple(n.vector) for n in data.corner_normals]
    errors = [angle(a, b) for a, b in zip(actual, targets)]
    if max(errors) > .025 or any(abs(math.hypot(*n) - 1) > 1e-6 for n in actual):
        raise ValueError('Native normal field guard failed')
    native_row = {'name': obj.name, 'vertices': [list(v.co) for v in data.vertices],
                  'triangles': [list(t.vertices) for t in data.loop_triangles]}
    self_proof = certificate(native_row)
    if self_proof['status'] != 'passed':
        raise ValueError('Indexed shell self check failed')
    obj['source_components'] = json.dumps([source.name])
    proof = {'source': source.name, 'parent': parent.name, 'source_triangles': len(reference),
        'retained_complete_original_triangles': len(new_retained), 'derived_triangles': len(data.loop_triangles),
        'constant_patch_source_triangles': [len(p['indices']) for p in patches],
        'constant_patch_result_triangles': [len(ts) for ts in patch_triangles],
        'complete_two_way_coverage_guard_m': 1e-6, 'maximum_UV_error': maximum_uv,
        'complete_piecewise_UV_error_bounds': complete_UV_bounds,
        'source_constant_normal_bound_degrees': .001, 'maximum_native_target_error_degrees': max(errors),
        'maximum_original_variable_corner_error_degrees': max(errors[i] for i in target_original),
        'raw_unit_error_max': max(abs(math.hypot(*n) - 1) for n in actual),
        'sharp_edge_changes': [{'edge': i, 'before': old, 'after': data.edges[i].use_edge_sharp} for i, old in enumerate(sharp_before) if old != data.edges[i].use_edge_sharp],
        'field_assignments': assignments, 'normal_encoding': encoding, 'shell_proof': self_proof,
        'source_geometry_and_target_corner_inventory': reference,
        'physical_UV_material_smooth_fields_unchanged_by_encoding': True}
    proof.update(current_source_binding=current['binding'], current_original_domains=current['domains'],
        current_rim_indices=[i for i,d in enumerate(current['domains']) if d=='rim'],
        complete_target_normals=targets, constant_plane_normals=[p['normal'].tolist() for p in patches],
        constant_plane_source_indices=[p['indices'] for p in patches],
        final_physical=plain(physical(data)), final_matrix=[list(r) for r in obj.matrix_world])
    proof['final_current_field']=verify_output(obj,proof,digest(proof))
    return obj, proof
