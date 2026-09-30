"""Retain original sections of eight cosmetic/stiffener ribbons, unsaved.

No source/report loading and no saves/exports. End caps, selected native
vertices, original material, UV corner charts and requested corner normals
are retained. New coarse faces are a deliberate bounded source-shape trial.
"""
import math

import bpy
import numpy as np


TARGETS={**{'LOD0_BrakeDuctVane_'+side+str(i):(25,4,(0,4,8,12,16,20,24))
             for side in ('L','R') for i in range(3)},
         **{'LOD0_TrunkRib_'+side:(12,6,(0,4,8,11)) for side in ('-1','1')}}


def angle(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    return math.degrees(math.atan2(float(np.linalg.norm(np.cross(a,b))),float(a@b)))


def row(obj):
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());data=evaluated.to_mesh()
    try:
        data.calc_loop_triangles()
        ancestors=[];parent=obj.parent
        while parent:ancestors.append(parent.name);parent=parent.parent
        return {'name':obj.name,'vertices':[list(evaluated.matrix_world@v.co) for v in data.vertices],
                'triangles':[list(t.vertices) for t in data.loop_triangles],
                'properties':{k:obj[k] for k in obj.keys()},'ancestors':ancestors,
                'rest_world_matrix':[list(r) for r in evaluated.matrix_world],
                'material_names':[m.name if m else None for m in data.materials]}
    finally:evaluated.to_mesh_clear()


def build_one(obj,n,k,retained):
    graph=bpy.context.evaluated_depsgraph_get()
    old=bpy.data.meshes.new_from_object(obj.evaluated_get(graph),preserve_all_data_layers=True,depsgraph=graph)
    old.calc_loop_triangles()
    if len(old.vertices)!=n*k or len(old.loop_triangles)!=(n-1)*2*k+2*(k-2):
        raise ValueError('Original complete ring inventory required: '+obj.name)
    if len(old.materials)!=1 or not old.uv_layers:
        raise ValueError('Original one-material UV ribbon required')
    normals=[tuple(v.vector) for v in old.corner_normals]
    lookup={};cells={};caps=[]
    for triangle in old.loop_triangles:
        face=list(triangle.vertices);stations={v//k for v in face};sides={v%k for v in face}
        if len(stations)==1:
            station=next(iter(stations))
            if station not in (0,n-1):raise ValueError('Interior cap in original ribbon')
            owner=('cap',station);caps.append((face,owner))
        else:
            if len(stations)!=2 or max(stations)-min(stations)!=1:raise ValueError('Nonadjacent original ring face')
            possible=[j for j in range(k) if sides=={j,(j+1)%k}]
            if len(possible)!=1:raise ValueError('Original angular cell unclear')
            owner=('side',possible[0]);cells.setdefault((min(stations),possible[0]),[]).append(face)
        for vertex,loop in zip(face,triangle.loops):
            value={'normal':normals[loop],'uvs':[tuple(layer.data[loop].uv) for layer in old.uv_layers],
                   'smooth':old.polygons[triangle.polygon_index].use_smooth}
            key=(owner,vertex)
            if key in lookup:
                previous=lookup[key]
                if previous['uvs']!=value['uvs'] or angle(previous['normal'],value['normal'])>1e-5:
                    raise ValueError('Retained corner crosses an original field discontinuity')
            lookup[key]=value
    if len(cells)!=(n-1)*k or any(len(v)!=2 for v in cells.values()):
        raise ValueError('Incomplete original side-cell inventory')
    kept=[i*k+j for i in retained for j in range(k)];mapping={v:i for i,v in enumerate(kept)}
    faces=[];owners=[];old_corners=[]
    for a,b in zip(retained,retained[1:]):
        for j in range(k):
            triangles=cells[(a,j)];edges=[]
            for f in triangles:
                for x,y in zip(f,f[1:]+f[:1]):
                    if (y,x) in edges:edges.remove((y,x))
                    else:edges.append((x,y))
            if len(edges)!=4:raise ValueError('Original two-triangle cell does not cover one quad')
            cycle=[a*k+j]
            for _ in range(3):cycle.append(next(y for x,y in edges if x==cycle[-1]))
            if next(y for x,y in edges if x==cycle[-1])!=cycle[0]:raise ValueError('Invalid oriented cell boundary')
            source=[v if v//k==a else b*k+v%k for v in cycle]
            faces.append([mapping[v] for v in source]);owners.append(('side',j));old_corners.append(source)
    for face,owner in caps:
        faces.append([mapping[v] for v in face]);owners.append(owner);old_corners.append(face)
    mesh=bpy.data.meshes.new(obj.name+'RetainedSections')
    mesh.from_pydata([tuple(old.vertices[v].co) for v in kept],[],faces);mesh.update()
    mesh.materials.append(old.materials[0])
    layers=[mesh.uv_layers.new(name=x.name) for x in old.uv_layers]
    targets=[]
    for polygon,owner,original_vertices in zip(mesh.polygons,owners,old_corners):
        polygon.use_smooth=all(lookup[(owner,v)]['smooth'] for v in original_vertices)
        for loop,vertex in zip(polygon.loop_indices,original_vertices):
            value=lookup[(owner,vertex)];targets.append(value['normal'])
            for layer,uv in zip(layers,value['uvs']):layer.data[loop].uv=uv
    mesh.normals_split_custom_set(targets);mesh.update()
    actual=[tuple(n.vector) for n in mesh.corner_normals]
    maximum=max(angle(a,b) for a,b in zip(actual,targets))
    if maximum>.025:raise ValueError('Target-to-native normal guard failed: '+str(maximum))
    assert all(tuple(mesh.vertices[i].co)==tuple(old.vertices[v].co) for i,v in enumerate(kept))
    for polygon,owner,original_vertices in zip(mesh.polygons,owners,old_corners):
        for loop,vertex in zip(polygon.loop_indices,original_vertices):
            assert [tuple(layer.data[loop].uv) for layer in layers]==lookup[(owner,vertex)]['uvs']
    mesh.calc_loop_triangles();original_count=len(old.loop_triangles)
    expected=(len(retained)-1)*k*2+2*(k-2)
    if len(mesh.loop_triangles)!=expected:raise ValueError('Unexpected new triangulation inventory')
    obj.modifiers.clear();obj.data=mesh
    obj['ribbon_detail_form']='Original end caps and retained native sections; source-detail reserve'
    result={'name':obj.name,'original_triangles':original_count,'new_triangles':expected,
            'triangle_delta':expected-original_count,'original_stations':n,'cross_section_sides':k,
            'retained_stations':list(retained),'native_retained_vertices_exact':True,
            'all_retained_uv_corners_exact':True,'uv_layers':[x.name for x in layers],
            'normal_target_to_native_maximum_degrees':maximum,'normal_guard_degrees':.025,
            'normal_field_scope':'Exact original targets at retained corners; interpolation over the changed source surface is authored anew.',
            'original_end_cap_triangles_exact':len(caps)}
    bpy.data.meshes.remove(old)
    return obj,result


def build():
    if any(n not in bpy.data.objects for n in TARGETS):raise ValueError('All eight original ribbons required')
    result=[build_one(bpy.data.objects[n],*v) for n,v in TARGETS.items()]
    bpy.context.view_layer.update()
    return [x[0] for x in result],[x[1] for x in result]
