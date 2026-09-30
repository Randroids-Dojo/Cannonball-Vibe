"""Current-input cover construction: cover. Source provenance is in the private port manifest."""

from collections import defaultdict

import math

import struct

import numpy as np

from . import domain as domain07

from . import base_mesh as mesh16

GAUGE=.0012

def f32(v):return struct.unpack('f',struct.pack('f',float(v)))[0]

def unit(v):
    a=np.asarray(v,dtype=float);length=float(np.linalg.norm(a))
    if not np.isfinite(a).all() or length==0:raise ValueError('Invalid new field/direction')
    return a/length

def triangle_points(row):return np.asarray(row['vertices'],dtype=float)[row['triangles']]

def curve(xmax,zmin):
    controls=np.asarray([[.755,zmin],[.760,zmin],[xmax,.270],[xmax,.275]])
    result=[]
    for i in range(13):
        t=i/12;u=1-t
        result.append((u*u*u*controls[0]+3*u*u*t*controls[1]+3*u*t*t*controls[2]+t*t*t*controls[3]).tolist())
    if any(result[i+1][0]<=result[i][0] or result[i+1][1]<=result[i][1] for i in range(12)):
        raise ValueError('Terminal curve is not monotone')
    slopes=[(b[1]-a[1])/(b[0]-a[0]) for a,b in zip(result,result[1:])]
    if any(b<a for a,b in zip(slopes,slopes[1:])):raise ValueError('Terminal curve is not convex')
    return controls.tolist(),result

def reference_owners(plan,reference,point_triangle):
    """Every whole actual front triangle maps to one actual carrier facet.

    Convexity of distance to that finite triangle bounds the entire triangle
    by the three retained vertex distances; no centroid-only ownership.
    """
    ref=triangle_points(reference);normals=np.cross(ref[:,1]-ref[:,0],ref[:,2]-ref[:,0])
    lengths=np.linalg.norm(normals,axis=1);normals/=lengths[:,None]
    result={}
    for i,(t,d) in enumerate(zip(triangle_points(plan),plan['triangle_domains'])):
        if d!='front':continue
        source=t+np.asarray([0.,.003,0.])
        candidates=np.flatnonzero((normals[:,1]<0)&np.all(ref.min(1)<=source.max(0)+1e-6,axis=1)&np.all(ref.max(1)>=source.min(0)-1e-6,axis=1))
        good=[]
        for j in candidates:
            bound=max(float(np.linalg.norm(p-point_triangle(p,ref[j]))) for p in source)
            if bound<=1e-6:good.append((bound,int(j)))
        if not good:raise ValueError('No complete finite original carrier owner for planned front triangle '+str(i))
        bound,j=min(good)
        result[i]=dict(reference_triangle=j,whole_distance_bound_m=bound,normal=normals[j].tolist())
    return result

def prepare(outer_plan,reference,exact,point_triangle):
    """No file/scene access. Inputs are freshly prepared current source rows."""
    domain07.validate(outer_plan);domain07.validate(reference)
    owners=reference_owners(outer_plan,reference,point_triangle)
    front_ids={i for i,d in enumerate(outer_plan['triangle_domains']) if d=='front'}
    front_vertices={v for i in front_ids for v in outer_plan['triangles'][i]}
    aperture_ids={v for t,d in zip(outer_plan['triangles'],outer_plan['triangle_domains']) if d.startswith('passage_') for v in t}&front_vertices
    apertures={tuple(outer_plan['vertices'][v]) for v in aperture_ids}
    points0=[outer_plan['vertices'][v] for v in front_vertices]
    xmax=max(abs(p[0]) for p in points0);zmin=min(p[2] for p in points0)
    controls,outline=curve(xmax,zmin)
    clips=[]
    for sign in (-1,1):
        for a,b in zip(outline,outline[1:]):
            ax,az=map(exact.F,a);bx,bz=map(exact.F,b)
            dx,dz=bx-ax,bz-az
            clips.append(((exact.F(-sign)*dz,exact.F(0),dx),dx*az-dz*ax))
    verts=[];lookup={};ideal={};polys=[];removed=[];source_ids=[];vertex_quantization=[]
    for i in sorted(front_ids):
        original=[exact.vector(outer_plan['vertices'][v]) for v in outer_plan['triangles'][i]]
        hit,out=exact.partition(original,clips)
        for p in out:
            native=np.asarray([[float(x) for x in q] for q in p])
            if np.any(abs(native[:,0])<.755-1e-12) or np.any(abs(native[:,0])>.825+1e-12) or np.any(native[:,2]>.275+1e-12) or np.any(native[:,2]<zmin-1e-12):
                raise ValueError('Changed fragment leaves authorized terminal band')
            removed.append(dict(source_triangle=i,points=native.tolist()))
        if not hit:continue
        ids=[]
        for q in hit:
            p=tuple(f32(v) for v in q)
            if p not in lookup:
                index=len(verts);lookup[p]=index;verts.append(list(p));ideal[index]=q
                vertex_quantization.append(dict(vertex=index,ideal=list(map(float,q)),native=list(p),error_m=math.sqrt(sum((float(x)-y)**2 for x,y in zip(q,p)))))
            index=lookup[p]
            if not ids or ids[-1]!=index:ids.append(index)
        if len(ids)>1 and ids[0]==ids[-1]:ids.pop()
        if len(ids)<3:raise ValueError('Clipped positive surface collapses in native coordinates')
        polys.append(ids);source_ids.append(i)
    front=[];original_ids=[]
    for poly,source in zip(polys,source_ids):
        coords={i:(ideal[i][0],ideal[i][2]) for i in poly}
        for t in mesh16.ears(poly,coords):front.append(list(t));original_ids.append(source)
    boundary=mesh16.loops(front)
    if len(boundary)!=1:raise ValueError('Unexpected disconnected/holed outer boundary')
    incident=defaultdict(list);sums=defaultdict(lambda:np.zeros(3))
    for t,source in zip(front,original_ids):
        a,b,c=np.asarray(verts)[t];weight=float(np.linalg.norm(np.cross(b-a,c-a)))
        if not weight:raise ValueError('Degenerate clipped outer triangle')
        n=np.asarray(owners[source]['normal'])
        for v in t:incident[v].append(n);sums[v]+=weight*n
    count=len(verts);inner=[];offsets=[];outer_targets={}
    for i,p0 in enumerate(verts):
        p=np.asarray(p0);normal=unit(sums[i]);outer_targets[i]=normal.tolist()
        constrained=tuple(p0) in apertures
        direction=np.asarray([0.,1.,0.])
        dots=[-float(np.dot(n,direction)) for n in incident[i]]
        if min(dots)<=0:raise ValueError('No shared inward normal cone')
        length=max(GAUGE/d for d in dots);q=p+length*direction
        native=np.asarray([f32(v) for v in q])
        if constrained and any(native[j]!=p[j] for j in (0,2)):raise ValueError('Aperture X/Z changed')
        inner.append(native.tolist())
        depths=[-float(np.dot(n,native-p)) for n in incident[i]]
        offsets.append(dict(vertex=i,aperture_xz_fixed=constrained,direction=direction.tolist(),ideal_length_m=length,
                            native_displacement_m=float(np.linalg.norm(native-p)),incident_normal_depth_range_m=[min(depths),max(depths)]))
    vertices=verts+inner;triangles=list(front);domains=['outer']*len(front)
    normals=[[outer_targets[v] for v in t] for t in front]
    source_triangles=list(original_ids)
    inner_faces=[[v+count for v in reversed(t)] for t in front]
    inner_sums=defaultdict(lambda:np.zeros(3))
    for t in inner_faces:
        a,b,c=np.asarray(vertices)[t];n=np.cross(b-a,c-a)
        if not np.linalg.norm(n):raise ValueError('Degenerate inner triangle')
        for v in t:inner_sums[v]+=n
    for t,source in zip(inner_faces,original_ids):
        triangles.append(t);domains.append('inner');normals.append([unit(inner_sums[v]).tolist() for v in t]);source_triangles.append(source)
    for loop in boundary:
        for a,b in zip(loop,loop[1:]+loop[:1]):
            for t in ([b,a,a+count],[b,a+count,b+count]):
                v=np.asarray(vertices)[t];n=unit(np.cross(v[1]-v[0],v[2]-v[0])).tolist()
                triangles.append(t);domains.append('rim');normals.append([n]*3);source_triangles.append(None)
    uvs={}
    # The input's physical UV layer names come from actual current mesh data.
    names=list(outer_plan['triangle_uvs'])
    for name in names:
        uvs[name]=[]
        for t,d,ns in zip(triangles,domains,normals):
            axes=[0,2] if d in ('outer','inner') else [j for j in range(3) if j!=int(np.argmax(np.abs(ns[0])))]
            uvs[name].append([[vertices[v][a]*4 for a in axes] for v in t])
    result=dict(name=outer_plan['name'],vertices=vertices,triangles=triangles,triangle_domains=domains,
                requested_triangle_normals=normals,triangle_uvs=uvs,materials=outer_plan['materials'],
                source_front_triangle=source_triangles,reference_owners={str(k):v for k,v in owners.items()},
                terminal_bezier_controls=controls,terminal_polyline=outline,exact_changed_fragments=removed,
                quantization=vertex_quantization,offsets=offsets,front_vertex_count=count,front_triangle_count=len(front),
                front_boundary=boundary,original_aperture_xyz=[list(v) for v in sorted(apertures)],
                cover_triangle_delta_from_original=len(triangles)-324,
                geometry_authoring='Third outer form unchanged; shared inner height field constrained by finite incident normal-gauge planes.')
    domain07.validate(result)
    if any(r['error_m']>1e-6 for r in vertex_quantization):raise ValueError('Native vertex conversion exceeds existing geometry guard')
    return result
