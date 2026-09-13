"""Transactional unsaved application; numerical/source helpers are injected."""
import math

def apply(obj, plan, *, encode, capture_fields, complete_affine_angle, angle):
    import bpy
    if obj.name!=plan['object'] or obj.modifiers:raise ValueError('Wrong native finite-surface target')
    mesh=obj.data;mesh.calc_loop_triangles()
    if ([list(v.co) for v in mesh.vertices]!=plan['positions_before']
            or [list(n.vector) for n in mesh.corner_normals]!=plan['normals_before']):
        raise ValueError('Prepared native surface changed before apply')
    actual=capture_fields(obj)
    if actual!=plan['physical_before']:raise ValueError('Prepared topology/UV/material/rig changed')
    free=set(plan['domain']['free_vertices']);selected=set(plan['domain']['selected_faces'])
    if not selected or any(type(fi) is not int or not 0<=fi<len(mesh.polygons) for fi in selected):
        raise ValueError('Invalid complete finite face domain')
    incident={v.index:set() for v in mesh.vertices}
    edge_faces={}
    for face in mesh.polygons:
        for vi in face.vertices:incident[vi].add(face.index)
        for li in face.loop_indices:edge_faces.setdefault(mesh.loops[li].edge_index,[]).append(face.index)
    expected_vertices={vi for fi in selected for vi in mesh.polygons[fi].vertices}
    expected_free={vi for vi in expected_vertices if incident[vi] and incident[vi].issubset(selected)}
    expected_fixed=expected_vertices-expected_free
    if free!=expected_free or set(plan['domain']['fixed_vertices'])!=expected_fixed:
        raise ValueError('Forged or incomplete fixed-boundary/free-vertex incidence')
    expected_boundary={tuple(sorted(mesh.edges[ei].vertices)):tuple(sorted(fs)) for ei,fs in edge_faces.items()
        if len(set(fs)&selected)==1}
    supplied_boundary={tuple(sorted(r['vertices'])):tuple(sorted(r['triangles'])) for r in plan['domain']['boundary']}
    if (expected_boundary!=supplied_boundary or len(supplied_boundary)!=len(plan['domain']['boundary'])
            or any(len(fs)!=2 for fs in expected_boundary.values())):
        raise ValueError('Forged or incomplete whole finite boundary inventory')
    if any(plan['positions'][vi]!=plan['positions_before'][vi] for vi in expected_fixed):
        raise ValueError('Moved actual fixed rim/deck boundary')
    owned={li for fi in selected for li in mesh.polygons[fi].loop_indices}
    if (len(plan['positions'])!=len(mesh.vertices) or len(plan['targets'])!=len(mesh.loops)
            or any(list(v.co)!=plan['positions'][v.index] for v in mesh.vertices if v.index not in free)
            or any(plan['targets'][i]!=plan['normals_before'][i] for i in range(len(mesh.loops)) if i not in owned)):
        raise ValueError('Finite surface plan escapes geometry/field ownership')
    if any(len(n)!=3 or any(not math.isfinite(v) for v in n) or abs(math.hypot(*n)-1)>1e-6 for n in plan['targets']):
        raise ValueError('Invalid explicit requested target')
    staged=mesh.copy()
    try:
        for v,p in zip(staged.vertices,plan['positions']):v.co=p
        staged.update()
        result=encode(staged,plan['targets'])
        if not result['passed']:raise ValueError('Native target encoding failed')
        ns=[tuple(n.vector) for n in staged.corner_normals]
        if any(not all(math.isfinite(x) for x in n) or abs(math.hypot(*n)-1)>1e-6 for n in ns):raise ValueError('Invalid native raw normal')
        staged.calc_loop_triangles();all_fields=[];outside=[]
        for ti in staged.loop_triangles:
            all_fields.append(dict(triangle=ti.index,**complete_affine_angle([plan['targets'][li] for li in ti.loops],[ns[li] for li in ti.loops])))
            if ti.polygon_index not in selected:
                outside.append(dict(triangle=ti.index,**complete_affine_angle([plan['normals_before'][li] for li in ti.loops],[ns[li] for li in ti.loops])))
        obj.data=staged;after=capture_fields(obj)
        before_other={k:v for k,v in actual.items() if k!='positions'}
        if before_other!={k:v for k,v in after.items() if k!='positions'}:raise ValueError('Finite surface changed topology/UV/material/rig')
        if [list(v.co) for v in staged.vertices]!=plan['positions']:raise ValueError('Native position storage differs from prepared float32 geometry')
        # Whole edge preservation follows from identical endpoint positions and
        # identical requested endpoint vectors on the unchanged field partition.
        boundaries=[]
        for row in plan['domain']['boundary']:
            for vi in row['vertices']:
                for fi in row['triangles']:
                    li=next(li for li in staged.polygons[fi].loop_indices if staged.loops[li].vertex_index==vi)
                    if plan['targets'][li]!=plan['normals_before'][li]:raise ValueError('Changed fixed boundary field')
            boundaries.append(dict(**row,whole_edge_positions_exact=True,whole_requested_edge_field_exact=True))
        proof=dict(status='passed-unsaved-finite-geometry-and-encoding',native_encoding=result,
            changed_vertices=len(plan['changed_vertices']),selected_triangles=len(selected),triangle_delta=0,
            topology_uv_material_rig_exact=True,whole_target_native_fields=all_fields,whole_outside_fields=outside,
            whole_target_native_max_degrees=max(r['maximum_degrees'] for r in all_fields),
            whole_outside_max_degrees=max(r['maximum_degrees'] for r in outside),
            boundary=boundaries,source_saved=False,exported=False,visual_acceptance=False)
        staged=None
        return proof
    except Exception:
        obj.data=mesh
        raise
    finally:
        if staged is not None and staged.users==0:bpy.data.meshes.remove(staged)
