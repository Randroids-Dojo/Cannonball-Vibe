"""Unsaved geometric bilinear centers for the two final warped outer quads."""
import math
from collections import Counter
import bpy
from mathutils import Vector

def make(obj,row,station_ids,encode):
    if obj.modifiers or len(obj.data.polygons)!=len(row['triangles']):raise ValueError('Expected current explicit native triangles')
    data=obj.data;points=[list(v.co)for v in data.vertices];old_normals=[list(n.vector)for n in data.corner_normals]
    groups=[];covered=set();replacement={}
    for r in (3,4):
        quad={station_ids[r][3],station_ids[r][4],station_ids[r+1][3],station_ids[r+1][4]}
        tids=[i for i,t in enumerate(row['triangles'])if set(t)<=quad]
        if len(tids)!=2:raise ValueError('Actual outer quad is not exactly two native triangles')
        if any(set(data.polygons[i].vertices)!=set(row['triangles'][i])for i in tids):raise ValueError('Native polygon/triangle alignment changed')
        edges=Counter(tuple(sorted((t[i],t[(i+1)%3])))for ti in tids for t in [row['triangles'][ti]]for i in range(3))
        boundary=[(t[i],t[(i+1)%3])for ti in tids for t in[row['triangles'][ti]]for i in range(3)if edges[tuple(sorted((t[i],t[(i+1)%3]))) ]==1]
        nxt=dict(boundary);start=station_ids[r][3];loop=[start]
        while len(loop)<4:loop.append(nxt[loop[-1]])
        if nxt[loop[-1]]!=start or len(set(loop))!=4:raise ValueError('Invalid complete oriented quad boundary')
        materials={data.polygons[i].material_index for i in tids}
        if len(materials)!=1:raise ValueError('Quad crosses a material boundary')
        uvs={name:{}for name in row['uvs']}
        for ti in tids:
            p=data.polygons[ti]
            for li in p.loop_indices:
                vi=data.loops[li].vertex_index
                for name in uvs:
                    uv=list(data.uv_layers[name].data[li].uv)
                    if vi in uvs[name]and math.dist(uv,uvs[name][vi])>1e-7:raise ValueError('Quad crosses an actual UV seam')
                    uvs[name][vi]=uv
        center=[sum(points[i][k]for i in quad)*.25 for k in range(3)];ci=len(points);points.append(center)
        for name in uvs:uvs[name][ci]=[sum(uvs[name][i][k]for i in quad)*.25 for k in range(2)]
        shared=set(row['triangles'][tids[0]])&set(row['triangles'][tids[1]])
        if len(shared)!=2:raise ValueError('Expected one actual original diagonal')
        mid=[sum(points[i][k]for i in shared)*.5 for k in range(3)]
        entry={'old_triangles':tids,'new_faces':[(a,b,ci)for a,b in boundary],'uvs':uvs,'material':next(iter(materials)),
            'center_index':ci,'center_local_m':center,'old_diagonal_midpoint_local_m':mid,'parameter_correspondence_maximum_m':math.dist(center,mid)}
        groups.append(entry);replacement[min(tids)]=entry;covered.update(tids)
    faces=[];loop_uv={n:[]for n in row['uvs']};prior_normals=[];materials=[];owners=[]
    for pi,p in enumerate(data.polygons):
        if pi in replacement:
            g=replacement[pi]
            for face in g['new_faces']:
                faces.append(face);materials.append(g['material']);owners.append(None)
                for vi in face:
                    prior_normals.append(None)
                    for name in loop_uv:loop_uv[name].append(g['uvs'][name][vi])
        elif pi not in covered:
            faces.append(tuple(p.vertices));materials.append(p.material_index);owners.append(pi)
            for li in p.loop_indices:
                prior_normals.append(old_normals[li])
                for name in loop_uv:loop_uv[name].append(list(data.uv_layers[name].data[li].uv))
    mesh=bpy.data.meshes.new(obj.name+'_BilinearCenters');mesh.from_pydata(points,[],faces)
    for m in data.materials:mesh.materials.append(m)
    for p,mat in zip(mesh.polygons,materials):p.material_index=mat;p.use_smooth=True
    mesh.update();mesh.set_sharp_from_angle(angle=math.radians(35));mesh.update();auto=[list(n.vector)for n in mesh.corner_normals]
    targets=[];i=0
    for p in mesh.polygons:
        upper=min((obj.matrix_world@mesh.vertices[v].co).y for v in p.vertices)>=-1.3100001
        for li in p.loop_indices:
            targets.append(auto[li]if upper else prior_normals[li]);i+=1
    if any(n is None for n in targets):raise ValueError('Missing preserved lower field')
    for name,values in loop_uv.items():
        layer=mesh.uv_layers.new(name=name)
        for i,v in enumerate(values):layer.data[i].uv=v
    mesh.update();coding=encode(mesh,targets)
    candidate=bpy.data.objects.new(obj.name+'_PrivateCenters20',mesh);candidate.matrix_world=obj.matrix_world.copy();bpy.context.scene.collection.objects.link(candidate)
    return candidate,{'groups':groups,'normal_encoder':coding,'triangle_delta':len(faces)-len(data.polygons),
        'original_vertex_count':len(data.vertices),'original_vertices_exact':all(list(a.co)==list(b.co)for a,b in zip(data.vertices,mesh.vertices)),
        'unchanged_face_old_indices':owners,'scope':'Two true bilinear quad centers change the geometric interior and replace each old diagonal with four complete triangles. All original vertices and quad boundary edges are fixed; unchanged face UVs/materials exact. Upper geometry-derived normal field is authored afresh, and lower native targets are preserved. No visual acceptance.'}
