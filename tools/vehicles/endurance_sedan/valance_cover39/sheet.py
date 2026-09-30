"""Current-input cover construction: sheet. Source provenance is in the private port manifest."""

from collections import defaultdict

import math

import numpy as np

from . import cover as cover36

GAUGE = .0012

def segment_pair(a,b,c,d):
    u=b-a;v=d-c;w=a-c
    aa=float(u@u);bb=float(u@v);cc=float(v@v);dd=float(u@w);ee=float(v@w)
    if aa==0:
        t=min(1.,max(0.,ee/cc)) if cc else 0.
        return a,c+t*v
    if cc==0:
        s=min(1.,max(0.,-dd/aa));return a+s*u,c
    den=aa*cc-bb*bb
    s=min(1.,max(0.,(bb*ee-cc*dd)/den)) if den>0 else 0.
    t=(bb*s+ee)/cc
    if t<0:t=0.;s=min(1.,max(0.,-dd/aa))
    elif t>1:t=1.;s=min(1.,max(0.,(bb-dd)/aa))
    return a+s*u,c+t*v

def triangle_pair(a,b,point_triangle):
    pairs=[(p,point_triangle(p,b)) for p in a]
    pairs.extend((point_triangle(p,a),p) for p in b)
    for i in range(3):
        for j in range(3):pairs.append(segment_pair(a[i],a[(i+1)%3],b[j],b[(j+1)%3]))
    p,q=min(pairs,key=lambda pq:float((pq[1]-pq[0])@(pq[1]-pq[0])))
    return float(np.linalg.norm(q-p)),p,q

def prepare(plan,point_triangle):
    """No source/report I/O. Preserve the outer profile; solve the inner sheet.

    Finite pair distance selects a separating plane. Its complete two-triangle
    support intervals are measured, and every inner vertex is constrained to
    the same inward halfspace. Corrections only increase Y, so every earlier
    valid plane remains satisfied. Final independent complete surface distance
    remains required on the actual installed native mesh.
    """
    result=dict(plan);vertices=np.asarray(plan['vertices'],dtype=float).copy()
    count=plan['front_vertex_count'];nt=plan['front_triangle_count']
    tris=np.asarray(plan['triangles'][:nt],dtype=int);outer=vertices[tris]
    xz=outer[:,:,[0,2]];lo=xz.min(1);hi=xz.max(1)
    pairs=[]
    for i in range(nt):
        lower=np.maximum(np.maximum(lo[i]-hi,lo-hi[i]),0.)
        for j in np.flatnonzero(np.sum(lower*lower,axis=1)<GAUGE*GAUGE):pairs.append((i,int(j)))
    records=[];sweeps=[]
    for iteration in range(12):
        changes=0;minimum=math.inf
        for oi,ii in pairs:
            ids=tris[ii]+count;inner=vertices[ids]
            d,p,q=triangle_pair(outer[oi],inner,point_triangle);minimum=min(minimum,d)
            if d>=GAUGE:continue
            if d<=0:raise ValueError('Crossed/zero finite sheet separation')
            n=(q-p)/d
            if n[1]<=0:raise ValueError('Finite gauge cannot be repaired by the shared inward sheet')
            maximum=float(np.max(outer[oi]@n));old_minimum=float(np.min(inner@n))
            # The requested separation uses actual convex support extrema, not
            # the closest-point pair as a substitute for complete coverage.
            constant=maximum+GAUGE
            new=[]
            for v in ids:
                target=(constant-n[0]*vertices[v,0]-n[2]*vertices[v,2])/n[1]
                if target>vertices[v,1]:
                    y=np.float32(target)
                    if float(y)<target:y=np.nextafter(y,np.float32(math.inf),dtype=np.float32)
                    old=float(vertices[v,1]);vertices[v,1]=float(y);new.append([int(v),old,float(y)])
            if new:
                changes+=len(new);records.append(dict(outer_triangle=oi,inner_triangle=ii,
                    old_finite_distance_m=d,normal=n.tolist(),outer_support_max=maximum,
                    old_inner_support_min=old_minimum,new_inner_support_min=float(np.min(vertices[ids]@n)),
                    requested_plane_constant=constant,changed_y=new))
        sweeps.append(dict(iteration=iteration,vertex_updates=changes,minimum_before_updates_m=minimum))
        if not changes:break
    else:raise ValueError('Finite sheet constraints did not converge in bounded sweeps')
    if not np.array_equal(vertices[:count],np.asarray(plan['vertices'][:count])):raise ValueError('Outer sheet changed')
    if not np.array_equal(vertices[count:,[0,2]],np.asarray(plan['vertices'])[count:,[0,2]]):raise ValueError('Inner X/Z changed')
    old=vertices.copy();vertices[:,1]=np.asarray(vertices[:,1]-.000999,dtype=np.float32)
    shifts=set((vertices[:,1]-old[:,1]).tolist())
    if len(shifts)!=1:raise ValueError('Outer placement is not one native rigid translation')
    alltri=np.asarray(plan['triangles'],dtype=int);normals=[];inner_sums=defaultdict(lambda:np.zeros(3))
    for t,d in zip(alltri,plan['triangle_domains']):
        if d=='inner':
            a,b,c=vertices[t];n=np.cross(b-a,c-a)
            for v in t:inner_sums[int(v)]+=n
    for i,(t,d) in enumerate(zip(alltri,plan['triangle_domains'])):
        if d=='outer':normals.append(plan['requested_triangle_normals'][i])
        elif d=='inner':normals.append([cover36.unit(inner_sums[int(v)]).tolist() for v in t])
        else:
            a,b,c=vertices[t];n=cover36.unit(np.cross(b-a,c-a)).tolist();normals.append([n]*3)
    uvs={name:[] for name in plan['triangle_uvs']}
    for t,d,ns in zip(alltri,plan['triangle_domains'],normals):
        axes=[0,2] if d in ('outer','inner') else [j for j in range(3) if j!=int(np.argmax(np.abs(ns[0])))]
        for name in uvs:uvs[name].append([[float(vertices[v,a])*4 for a in axes] for v in t])
    result.update(vertices=vertices.tolist(),requested_triangle_normals=normals,triangle_uvs=uvs,
        nominal_outer_y_reveal_m=.003999,common_translation_y_m=next(iter(shifts)),
        whole_neighbor_constraints=records,constraint_sweeps=sweeps,finite_candidate_pairs=len(pairs),
        geometry_authoring='Same third outer terminal profile; complete finite neighboring-facet constraints derive inner sheet, uniform nominal 3.999 mm reveal.')
    return result
