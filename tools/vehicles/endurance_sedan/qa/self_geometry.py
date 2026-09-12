"""Exact original authored-mesh self intersections; assembly contacts are separate.

The vectorized128-row AABB enumeration and exact integer/rational predicates
were independently replayed against exhaustive controls and native source
failures. They do not use normalized-plane epsilon tests.
"""
import numpy as np
import exact_triangles as exact
from types import SimpleNamespace

policy=SimpleNamespace(EPS=1e-9)

def candidates(row):
    vertices=np.asarray(row['vertices'],dtype=np.float64)
    faces=np.asarray(row['triangles'],dtype=np.int64)
    xyz=vertices[faces];lo=xyz.min(axis=1);hi=xyz.max(axis=1);n=len(faces)
    result=[]
    # Every upper-triangle pair is covered by one128-row block. The six binary64
    # inequalities are exactly the original ribbon_self AABB predicate.
    for start in range(0,n,128):
        end=min(n,start+128)
        mask=np.arange(n)[None,:]>np.arange(start,end)[:,None]
        for axis in range(3):
            mask &= hi[start:end,axis,None]>=lo[None,:,axis]-policy.EPS
            mask &= hi[None,:,axis]>=lo[start:end,axis,None]-policy.EPS
        ai,bi=np.nonzero(mask)
        result.extend((int(a+start),int(b)) for a,b in zip(ai,bi))
    return result

def dot(a,b):return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def sub(a,b):return (a[0]-b[0],a[1]-b[1],a[2]-b[2])

def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def prepare(row):
    ratios=[[float(x).as_integer_ratio() for x in p] for p in row['vertices']]
    bits=max(q.bit_length()-1 for p in ratios for _,q in p)
    vertices=[tuple(p*(1<<(bits-(q.bit_length()-1))) for p,q in r) for r in ratios]
    normals=[]
    for face in row['triangles']:
        a,b,c=[vertices[i] for i in face];n=cross(sub(b,a),sub(c,a))
        if n==(0,0,0):raise ValueError('Exact degenerate triangle')
        normals.append(n)
    return vertices,normals,bits

def prefilter(row,prep,ai,bi):
    vertices,normals,_=prep;ia,ib=row['triangles'][ai],row['triangles'][bi]
    a,b=[vertices[i] for i in ia],[vertices[i] for i in ib];na,nb=normals[ai],normals[bi]
    da=[dot(sub(p,b[0]),nb) for p in a];db=[dot(sub(p,a[0]),na) for p in b]
    if min(da)>0 or max(da)<0 or min(db)>0 or max(db)<0:return 'strict_plane_separation'
    shared=set(ia)&set(ib)
    if len(shared)==2:
        if any(d!=0 for d in db):return 'noncoplanar_indexed_edge_only'
        p,q=[vertices[i] for i in sorted(shared)]
        ta=vertices[next(i for i in ia if i not in shared)];tb=vertices[next(i for i in ib if i not in shared)]
        sa=dot(cross(sub(q,p),sub(ta,p)),na);sb=dot(cross(sub(q,p),sub(tb,p)),na)
        if sa*sb<0:return 'coplanar_opposite_sides_indexed_edge_only'
    if len(shared)==1:
        for ids,values in ((ia,da),(ib,db)):
            if (min(values)>=0 or max(values)<=0) and {i for i,d in zip(ids,values) if d==0}==shared:
                return 'plane_section_indexed_point_only'
    if cross(na,nb)==(0,0,0) and all(d==0 for d in da):
        for tri,other,n in ((a,b,na),(b,a,nb)):
            for i in range(3):
                p,q,inside=tri[i],tri[(i+1)%3],tri[(i+2)%3]
                edge=cross(sub(q,p),n)
                if dot(sub(inside,p),edge)<0:edge=tuple(-x for x in edge)
                values=[dot(sub(p2,p),edge) for p2 in other]
                if max(values)<0:return 'coplanar_strict_edge_separation'
    return None

def exact_pair(row,ai,bi):
    ia,ib=row['triangles'][ai],row['triangles'][bi]
    a,b=[[row['vertices'][i] for i in face] for face in (ia,ib)]
    shared=sorted(set(ia)&set(ib))
    result=exact.inspect_pair(a,b,[row['vertices'][i] for i in shared])
    return {'triangles':[ai,bi],'shared_indices':shared,
            'exact_intersection_points_m':exact.jsonify(result['points']),
            'outside_shared_simplex_m':exact.jsonify(result['outside']),
            'actual_triangles_m':[a,b]}

def scan(row,validate=False):
    prep=prepare(row);pairs=candidates(row);bad=[];counts={};calls=0
    for ai,bi in pairs:
        reason=prefilter(row,prep,ai,bi)
        if reason:counts[reason]=counts.get(reason,0)+1
        if reason and not validate:continue
        found=exact_pair(row,ai,bi);calls+=1
        if reason:assert not found['outside_shared_simplex_m'],(row['name'],reason,found)
        if found['outside_shared_simplex_m']:bad.append(found)
    return {'name':row['name'],'vertices':len(row['vertices']),'triangles':len(row['triangles']),
            'aabb_candidates':len(pairs),'integer_coordinate_denominator_bits':prep[2],
            'exact_integer_prefilter_counts':counts,'rational_pair_calls':calls,'bad_pairs':bad,
            'status':'failed' if bad else 'passed'}
