"""Preserve attributed Boolean surfaces while correcting proven local crossings.

Pass the project's exact self scan and strict evaluated-count validator explicitly.
No report path, vertex ID, object name, source checksum or physical tolerance is
used to select a correction. All changes remain staged until the complete mesh
has no exact crossings and unchanged coordinates/count/material/parent contracts.
"""
from collections import defaultdict
import math
import bmesh
import bpy

def _sub(a,b):return tuple(x-y for x,y in zip(a,b))
def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def _triangle_key(row,index):
    points=[tuple(row['vertices'][v]) for v in row['triangles'][index]]
    return min(tuple(points),tuple(points[1:]+points[:1]),tuple(points[2:]+points[:2]))

def _crossing_keys(row,proof):
    return {tuple(sorted(_triangle_key(row,i) for i in pair['triangles'])) for pair in proof['bad_pairs']}

def _candidates(row,maximum_altitude_m=1e-6):
    vertices=row['vertices'];triangles=row['triangles'];edge_faces=defaultdict(list)
    for index,tri in enumerate(triangles):
        for a,b in zip(tri,tri[1:]+tri[:1]):edge_faces[tuple(sorted((a,b)))].append(index)
    result=[];seen=set()
    for index,tri in enumerate(triangles):
        length2,edge=max((_dot(_sub(vertices[a],vertices[b]),_sub(vertices[a],vertices[b])),tuple(sorted((a,b)))) for a,b in zip(tri,tri[1:]+tri[:1]))
        if length2<=0 or not math.isfinite(length2):raise ValueError('Invalid triangle edge')
        adjacent=edge_faces[edge]
        if len(adjacent)!=2 or edge in seen:continue
        if any(len(row['polygons'][row['polygon_indices'][ti]])!=3 for ti in adjacent):continue
        a,b=(vertices[i] for i in edge);third=next(i for i in tri if i not in edge);c=vertices[third]
        direction=_sub(b,a);fraction=_dot(_sub(c,a),direction)/length2
        if not 0<fraction<1:continue
        deviation=math.sqrt(sum((c[k]-(a[k]+fraction*direction[k]))**2 for k in range(3)))
        if not math.isfinite(deviation) or deviation>maximum_altitude_m:continue
        other=next(i for i in adjacent if i!=index);opposite=next(i for i in triangles[other] if i not in edge)
        if opposite==third:continue
        seen.add(edge)
        result.append({'edge':edge,'thin_vertex':third,'opposite_vertex':opposite,'fraction':fraction,'altitude_m':deviation})
    return sorted(result,key=lambda r:(r['altitude_m'],r['edge']))

def _native(obj):
    bpy.context.view_layer.update();m=obj.data;m.calc_loop_triangles()
    return {'name':obj.name,'vertices':[list(obj.matrix_world@v.co) for v in m.vertices],
        'triangles':[list(t.vertices) for t in m.loop_triangles],
        'normals':[[list(m.corner_normals[i].vector) for i in t.loops] for t in m.loop_triangles],
        'uvs':{layer.name:[[list(layer.data[i].uv) for i in t.loops] for t in m.loop_triangles] for layer in m.uv_layers},
        'materials':[t.material_index for t in m.loop_triangles],
        'polygon_indices':[t.polygon_index for t in m.loop_triangles],'polygons':[list(p.vertices) for p in m.polygons]}

def repair(obj,exact_scan,evaluated_counts,allow_sliver_flip=True):
    """Call after the final Boolean, while its actual n-gons still exist.

    Do not freeze evaluated loop triangles immediately before this call: doing so
    discards the n-gon boundary that identifies the faulty diagonal. Modifiers
    must already be applied; the unchanged four-door/floor producers meet this
    precondition after their final Booleans. A clean input returns untouched.
    """
    if obj.modifiers:raise ValueError('Boolean repair requires applied modifiers')
    original=_native(obj);first=exact_scan(original)
    if not first['bad_pairs']:return {'changed':False,'proof':first}
    counts=evaluated_counts(obj)
    keys=('nonmanifold_edges','duplicate_faces','degenerate_faces','degenerate_triangles','triangulated_nonmanifold_edges','triangulated_duplicate_faces')
    if any(counts[k] for k in keys):raise ValueError('Input is not a valid closed attributed mesh')
    if not obj.data.has_custom_normals:raise ValueError('Expected saved custom corner normals')
    selected={original['polygon_indices'][i] for pair in first['bad_pairs'] for i in pair['triangles']}
    selected={i for i in selected if len(obj.data.polygons[i].vertices)>3}
    affected={v for i in selected for v in obj.data.polygons[i].vertices}
    old_codes=[tuple(v.value) for v in obj.data.attributes['custom_normal'].data]
    old_normals=[tuple(v.vector) for v in obj.data.corner_normals]
    original_vertices=[tuple(v.co) for v in obj.data.vertices]
    stage=obj.copy();stage.data=obj.data.copy();bpy.context.scene.collection.objects.link(stage)
    applied=False;attempts=[]
    try:
        bm=bmesh.new();bm.from_mesh(stage.data);bm.faces.ensure_lookup_table()
        loop_id=bm.loops.layers.int.new('repair_original_loop');target=bm.loops.layers.float_vector.new('repair_target_normal')
        index=0
        for face in bm.faces:
            for loop in face.loops:
                loop[loop_id]=index;loop[target]=old_normals[index];index+=1
        bmesh.ops.triangulate(bm,faces=[f for f in bm.faces if f.index in selected],quad_method='BEAUTY',ngon_method='BEAUTY')
        bm.to_mesh(stage.data);bm.free();stage.data.update()
        current=_native(stage);proof=exact_scan(current)
        for _ in range(4):
            if not proof['bad_pairs']:break
            if not allow_sliver_flip:raise ValueError('Crossing remains after n-gon repair')
            accepted=False
            for proposal in _candidates(current):
                candidate=stage.copy();candidate.data=stage.data.copy();bpy.context.scene.collection.objects.link(candidate)
                edit=bmesh.new();edit.from_mesh(candidate.data);edit.verts.ensure_lookup_table()
                edge=next(e for e in edit.edges if tuple(sorted(v.index for v in e.verts))==proposal['edge'])
                authorship=[edit.faces.layers.int.get(name) for name in ('cb_fascia_cap','__mod_weightednormals_faceweight')]
                crosses_authorship=any(layer is not None and len({face[layer] for face in edge.link_faces})!=1 for layer in authorship)
                if crosses_authorship or len({f.material_index for f in edge.link_faces})!=1 or len({f.smooth for f in edge.link_faces})!=1:
                    edit.free();data=candidate.data;bpy.data.objects.remove(candidate,do_unlink=True);bpy.data.meshes.remove(data);continue
                bmesh.ops.rotate_edges(edit,edges=[edge],use_ccw=False);edit.to_mesh(candidate.data);edit.free();candidate.data.update()
                proposed=_native(candidate);trial=exact_scan(proposed);valid=evaluated_counts(candidate)
                passed=(proposed['vertices']==original['vertices'] and len(proposed['triangles'])==len(original['triangles'])
                    and not any(valid[k] for k in keys) and _crossing_keys(proposed,trial)<_crossing_keys(current,proof))
                attempts.append({**proposal,'accepted':passed,'remaining_pairs':len(trial['bad_pairs'])})
                if passed:
                    old_data=stage.data;stage.data=candidate.data;bpy.data.objects.remove(candidate,do_unlink=True);bpy.data.meshes.remove(old_data)
                    affected.update((*proposal['edge'],proposal['thin_vertex'],proposal['opposite_vertex']))
                    current,proof=proposed,trial;accepted=True;break
                data=candidate.data;bpy.data.objects.remove(candidate,do_unlink=True);bpy.data.meshes.remove(data)
            if not accepted:raise ValueError('No bounded diagonal reduces the exact crossing set')
        if proof['bad_pairs']:raise ValueError('Boolean diagonal repair did not converge')
        mesh=stage.data
        targets=[tuple(v.vector) for v in mesh.attributes['repair_target_normal'].data]
        if any(not all(math.isfinite(q) for q in n) or _dot(n,n)<=1e-12 for n in targets):raise ValueError('Invalid target normal')
        mesh.normals_split_custom_set(targets)
        ids=[v.value for v in mesh.attributes['repair_original_loop'].data]
        for i,loop in enumerate(mesh.loops):
            if loop.vertex_index not in affected:mesh.attributes['custom_normal'].data[i].value=old_codes[ids[i]]
        mesh.attributes.remove(mesh.attributes['repair_target_normal']);mesh.attributes.remove(mesh.attributes['repair_original_loop']);mesh.update()
        final=_native(stage);final_proof=exact_scan(final);valid=evaluated_counts(stage)
        if final_proof['bad_pairs'] or any(valid[k] for k in keys):raise ValueError('Final attributed surface rejected')
        if [tuple(v.co) for v in mesh.vertices]!=original_vertices or len(final['triangles'])!=len(original['triangles']):raise ValueError('Changed coordinates or triangle count')
        old_tri={_triangle_key(original,i):i for i in range(len(original['triangles']))};outside=0;maximum_normal_angle=0.
        for ti,tri in enumerate(final['triangles']):
            key=_triangle_key(final,ti)
            if key not in old_tri:continue
            oi=old_tri[key]
            for vertex in tri:
                ni=tri.index(vertex);si=original['triangles'][oi].index(vertex)
                a,b=original['normals'][oi][si],final['normals'][ti][ni]
                angle=math.degrees(math.acos(max(-1.,min(1.,_dot(a,b)/math.sqrt(_dot(a,a)*_dot(b,b))))))
                if not math.isfinite(angle) or angle>0.1:raise ValueError('Unbounded corner-normal re-encoding')
                maximum_normal_angle=max(maximum_normal_angle,angle)
                if any(original['uvs'][k][oi][si]!=final['uvs'][k][ti][ni] for k in original['uvs']):raise ValueError('Changed existing UV corner')
                if not set(tri)&affected:
                    outside+=1
                    if a!=b or original['materials'][oi]!=final['materials'][ti]:raise ValueError('Changed outside-domain attribute')
        obj.data=mesh;applied=True
        return {'changed':True,'selected_original_polygons':sorted(selected),'affected_vertices':sorted(affected),
            'attempts':attempts,'initial_pairs':len(first['bad_pairs']),'outside_exact_corners':outside,
            'maximum_common_normal_angle_degrees':maximum_normal_angle,'positions_exact':True,'triangle_count_exact':True,
            'validity':valid,'proof':final_proof}
    finally:
        data=stage.data;bpy.data.objects.remove(stage,do_unlink=True)
        if not applied and data.users==0:bpy.data.meshes.remove(data)
