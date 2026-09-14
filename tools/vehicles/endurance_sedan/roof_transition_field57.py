"""Match the new visible C transition's cut-boundary field to actual retained faces.

No I/O, scene load/save/export, geometry mutation or automatic broad smoothing.
"""
from collections import defaultdict
import math
import bpy
from mathutils import Vector
CUT=-1.400
FIRST=-1.380
EPS=2e-7

def cycle(row,y):
    edges=set()
    for tri in row['triangles']:
        for a,b in zip(tri,tri[1:]+tri[:1]):
            if abs(row['vertices'][a][1]-y)<EPS and abs(row['vertices'][b][1]-y)<EPS:
                edges.add(tuple(sorted((a,b))))
    adj=defaultdict(list)
    for a,b in edges:adj[a].append(b);adj[b].append(a)
    if not adj or any(len(v)!=2 for v in adj.values()):raise ValueError('Expected one actual closed station cycle')
    start=max(adj,key=lambda i:(row['vertices'][i][2],-abs(row['vertices'][i][0])))
    out=[start];previous=None;current=start
    while True:
        nxt=next(v for v in adj[current] if v!=previous)
        if nxt==start:break
        if nxt in out:raise ValueError('Repeated station-cycle vertex')
        out.append(nxt);previous,current=current,nxt
    if len(out)!=len(adj):raise ValueError('Multiple station cycles')
    area=sum(abs(row['vertices'][a][0])*row['vertices'][b][2]-abs(row['vertices'][b][0])*row['vertices'][a][2] for a,b in zip(out,out[1:]+out[:1]))
    if area<0:out=[out[0],*reversed(out[1:])]
    return out

def make(obj,row,encode):
    if obj.name not in ('LOD0_StampedPillar_CL','LOD0_StampedPillar_CR') or obj.type!='MESH':raise ValueError('Wrong transition-field target')
    if obj.modifiers:raise ValueError('Expected actual frozen final mesh without modifiers')
    if len(row['triangles'])!=448:raise ValueError('This bounded trial requires the frozen50 C topology')
    if any(not v.value for v in obj.data.attributes['sharp_edge'].data):raise ValueError('Expected original independent native corner spaces')
    cut=cycle(row,CUT);first=cycle(row,FIRST)
    if len(first)!=10:raise ValueError('Expected actual six-span first station')
    cut_d=max(range(len(cut)),key=lambda j:abs(row['vertices'][cut[j]][0]))
    cut_a=max(range(len(cut)),key=lambda j:abs(row['vertices'][cut[j]][0])+row['vertices'][cut[j]][2])
    first_d=max(range(len(first)),key=lambda j:abs(row['vertices'][first[j]][0]))
    if first_d!=3 or not 0<cut_d<cut_a<len(cut):raise ValueError('Unexpected actual outer/top station feature ordering')
    visible_cut=set([*cut[cut_d:],cut[0]]);visible_first=set([*first[first_d:],first[0]])
    retained={i for i,t in enumerate(row['triangles']) if max(row['vertices'][v][1] for v in t)<CUT+EPS}
    fan=[]
    for i,t in enumerate(row['triangles']):
        if i in retained:continue
        if all(v in visible_cut|visible_first for v in t) and any(v in visible_cut for v in t) and any(v in visible_first for v in t):fan.append(i)
    if len(fan)!=19:raise ValueError(('Expected actual visible outer/top fan only',fan))
    edge_owners=defaultdict(list)
    for ti in retained:
        tri=row['triangles'][ti]
        for a,b in zip(tri,tri[1:]+tri[:1]):
            if a in cut and b in cut:edge_owners[tuple(sorted((a,b)))].append(ti)
    targets=[tuple(n) for n in row['normals']];changed={};witnesses=[]
    for ti in fan:
        tri=row['triangles'][ti];anchors=[v for v in tri if v in cut]
        if len(anchors)==2:edge=tuple(sorted(anchors))
        elif len(anchors)==1 and anchors[0] in (cut[cut_a],cut[0]):
            j=cut.index(anchors[0]);edge=tuple(sorted((cut[j-1],cut[j])))
        else:raise ValueError('Unowned fan anchor domain')
        owners=edge_owners[edge]
        if len(owners)!=1:raise ValueError('Ambiguous retained boundary-face owner')
        owner=owners[0]
        for vertex in anchors:
            li=row['triangle_loops'][ti][tri.index(vertex)]
            source_loop=row['triangle_loops'][owner][row['triangles'][owner].index(vertex)]
            targets[li]=tuple(row['normals'][source_loop]);changed[li]=source_loop
            witnesses.append({'triangle':ti,'loop':li,'vertex':vertex,'retained_triangle':owner,'retained_loop':source_loop,'position_m':row['vertices'][vertex]})
    mesh=obj.data.copy();mesh.name=obj.name+'_PrivateBoundary57'
    if len(mesh.loops)!=len(targets):raise ValueError('Actual raw/evaluated loop mismatch')
    original_codes=[tuple(v.value) for v in mesh.attributes['custom_normal'].data]
    original_normals=[tuple(n.vector) for n in mesh.corner_normals]
    if original_normals!=[tuple(n) for n in row['normals']]:raise ValueError('Actual raw/evaluated normal mismatch')
    code=encode(mesh,targets)
    if not code['passed']:raise ValueError('Existing native normal-encoding guard failed')
    for i,value in enumerate(original_codes):
        if i not in changed:mesh.attributes['custom_normal'].data[i].value=value
    mesh.update()
    actual=[tuple(n.vector) for n in mesh.corner_normals]
    outside=[i for i,n in enumerate(actual) if i not in changed and n!=original_normals[i]]
    if outside:raise ValueError(('Unexpected outside native field change',outside[:8]))
    candidate=bpy.data.objects.new(obj.name+'_PrivateBoundary57',mesh);candidate.matrix_world=obj.matrix_world.copy();bpy.context.scene.collection.objects.link(candidate)
    return candidate,{'cut_y_m':CUT,'first_y_m':FIRST,'visible_transition_triangles':fan,'changed_corner_count':len(changed),'actual_owned_boundary_witnesses':witnesses,'normal_encoding':code,'outside_normals_exact':len(actual)-len(changed),'all_geometry_unchanged':True,'triangle_delta':0,'scope':'Only cut-boundary corner fields on the19 actual visible outer/top fan triangles. Each copied target has one retained face/edge owner. Fold underside, regular rolled field, and every other corner are unchanged.'}
