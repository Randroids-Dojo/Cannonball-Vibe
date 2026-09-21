"""Constrained, source-topology simplification of an explicitly authored target.

Protected vertices and material seams are immutable. Every collapse satisfies
the manifold link condition, positive incident orientation, and a bound against
all inherited source facet planes. The latter is a local construction guard,
not a whole-surface Hausdorff certificate; final finite comparison is separate.
"""
import heapq,math
from collections import defaultdict
import numpy as np


def reduce(vertices,triangles,materials,protected,*,plane_error=.00035,target_triangles=3000):
    points=np.asarray(vertices,dtype=np.float64).copy();faces=np.asarray(triangles,dtype=np.int64).copy()
    count=len(points);active=np.ones(len(faces),dtype=bool);alive=np.ones(count,dtype=bool)
    locked=set(protected);incident=[set()for _ in points]
    p=points[faces];raw=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);area=np.linalg.norm(raw,axis=1)
    if min(area)<=1e-12:raise ValueError('Degenerate input target')
    normals=raw/area[:,None];planes=np.column_stack((normals,-np.sum(normals*p[:,0],axis=1)))
    quadrics=np.zeros((count,4,4));parents=[set()for _ in points]
    for fi,tri in enumerate(faces):
        q=np.outer(planes[fi],planes[fi])*max(area[fi],1e-10)
        for v in tri:incident[v].add(fi);parents[v].add(fi);quadrics[v]+=q
    edge_faces=defaultdict(list)
    for fi,t in enumerate(faces):
        for a,b in zip(t,np.roll(t,-1)):edge_faces[tuple(sorted((int(a),int(b))))].append(fi)
    for (a,b),fs in edge_faces.items():
        if len(fs)!=2 or len({materials[i]for i in fs})!=1:locked.update((a,b))
        elif float(np.dot(normals[fs[0]],normals[fs[1]]))<math.cos(math.radians(65)):locked.update((a,b))
    generation=[0]*count;queue=[];serial=0;accepted=[];rejections=defaultdict(int)
    def neighbors(v):return {int(x)for f in incident[v]for x in faces[f]if x!=v}
    def enqueue(u,v):
        nonlocal serial
        if u==v or not alive[u]or not alive[v]or u in locked and v in locked:return
        if u>v:u,v=v,u
        q=quadrics[u]+quadrics[v]
        if u in locked:candidates=[points[u]]
        elif v in locked:candidates=[points[v]]
        else:
            candidates=[points[u],points[v],(points[u]+points[v])/2]
            try:
                if np.linalg.cond(q[:3,:3])<1e10:candidates.append(np.linalg.solve(q[:3,:3],-q[:3,3]))
            except np.linalg.LinAlgError:pass
        costs=[float(np.r_[p,1.]@q@np.r_[p,1.])for p in candidates]
        at=min(range(len(costs)),key=costs.__getitem__);point=candidates[at]
        # Cost order is deterministic, and records refer to exact source IDs.
        heapq.heappush(queue,(max(0.,costs[at]),serial,u,v,generation[u],generation[v],point.copy()));serial+=1
    for u,v in edge_faces:enqueue(u,v)
    remaining=len(faces);worst_plane=0.;worst_turn=0.
    while queue and remaining>target_triangles:
        _,_,u,v,gu,gv,position=heapq.heappop(queue)
        if not alive[u]or not alive[v]or gu!=generation[u]or gv!=generation[v]:continue
        joined=incident[u]&incident[v]
        if len(joined)!=2:rejections['not_two_face_edge']+=1;continue
        opposite={int(x)for f in joined for x in faces[f]if x not in(u,v)}
        if neighbors(u)&neighbors(v)!=opposite:rejections['link_condition']+=1;continue
        if v in locked:u,v=v,u
        affected=incident[u]|incident[v];retained=sorted(affected-joined);source=parents[u]|parents[v]
        bound=float(np.max(np.abs(planes[list(source),:3]@position+planes[list(source),3])))
        if bound>plane_error:rejections['source_plane_bound']+=1;continue
        candidate=faces[retained].copy();candidate[candidate==v]=u
        xyz=points[candidate].copy();xyz[candidate==u]=position
        cross=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]);length=np.linalg.norm(cross,axis=1)
        if min(length,default=1)<=1e-12:rejections['degenerate']+=1;continue
        old=points[faces[retained]];oldcross=np.cross(old[:,1]-old[:,0],old[:,2]-old[:,0]);oldlength=np.linalg.norm(oldcross,axis=1)
        dots=np.sum(cross*oldcross,axis=1)/(length*oldlength)
        if min(dots,default=1)<.94:rejections['incident_orientation']+=1;continue
        if min(np.sum(cross*normals[retained],axis=1)/length,default=1)<.90:rejections['target_orientation']+=1;continue
        if max(np.linalg.norm(position-points[u]),np.linalg.norm(position-points[v]))>.15:rejections['large_span']+=1;continue
        # One immutable source vertex may survive; it cannot be moved.
        if u in locked and not np.array_equal(position,points[u]):raise ValueError('Locked vertex mutation')
        for f in affected:
            for oldv in faces[f]:incident[oldv].discard(f)
        for f in joined:active[f]=False
        faces[retained]=candidate;points[u]=position;alive[v]=False
        incident[v].clear();parents[u]=source;parents[v].clear();quadrics[u]+=quadrics[v]
        for f in retained:
            for newv in faces[f]:incident[newv].add(f)
        remaining-=2;generation[u]+=1;generation[v]+=1
        around=neighbors(u)
        for w in around:generation[w]+=1
        for a in around|{u}:
            for b in neighbors(a):enqueue(a,b)
        worst_plane=max(worst_plane,bound);worst_turn=max(worst_turn,math.degrees(math.acos(min(1.,max(-1.,float(min(dots,default=1)))))))
        accepted.append({'kept':u,'removed':v,'point':position.tolist(),'source_planes':len(source),'plane_bound_m':bound,'removed_faces':sorted(joined)})
    used=sorted({int(v)for f in np.flatnonzero(active)for v in faces[f]});mapping={v:i for i,v in enumerate(used)}
    fs=np.flatnonzero(active).tolist()
    result={'vertices':points[used].astype(np.float32).astype(float).tolist(),
      'triangles':[[mapping[int(v)]for v in faces[f]]for f in fs],'triangle_materials':[materials[f]for f in fs],
      'source_face_ids':fs,'source_vertex_ids':used,'protected_source_vertices':sorted(locked),
      'collapse_count':len(accepted),'collapses':accepted,'rejections':dict(rejections),
      'maximum_inherited_plane_bound_m':worst_plane,'maximum_single_collapse_incident_turn_degrees':worst_turn,
      'plane_error_limit_m':plane_error,'target_triangles':target_triangles,'whole_surface_bound_pending':True}
    for v in locked:
        if v not in mapping or result['vertices'][mapping[v]]!=vertices[v]:raise ValueError('Protected current vertex not retained exactly')
    return result
