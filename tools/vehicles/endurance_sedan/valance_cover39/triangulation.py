"""Current-input cover construction: triangulation. Source provenance is in the private port manifest."""

import functools

def ears(ids,points):
    ids=tuple(ids)
    if len(ids)!=len(set(ids)):raise ValueError('Repeated finite polygon vertex')
    def cross(a,b,c):
        u,v,w=points[a],points[b],points[c]
        return (v[0]-u[0])*(w[1]-u[1])-(v[1]-u[1])*(w[0]-u[0])
    area=sum(points[a][0]*points[b][1]-points[a][1]*points[b][0] for a,b in zip(ids,ids[1:]+ids[:1]))
    if not area:raise ValueError('Zero finite polygon area')
    sign=1 if area>0 else -1;attempts=0
    @functools.lru_cache(None)
    def solve(pending):
        nonlocal attempts
        attempts+=1
        if attempts>10000:raise ValueError('Finite polygon triangulation budget exhausted')
        if len(pending)==3:return (pending,) if sign*cross(*pending)>0 else None
        choices=[]
        for j,b in enumerate(pending):
            a,c=pending[j-1],pending[(j+1)%len(pending)]
            if sign*cross(a,b,c)<=0:continue
            if any(v not in (a,b,c) and sign*cross(a,b,v)>=0 and sign*cross(b,c,v)>=0 and sign*cross(c,a,v)>=0 for v in pending):continue
            # Prefer well-spaced actual ears; no point or boundary adjustment.
            q=[points[v] for v in (a,b,c)];length=sum(float((u[0]-v[0])**2+(u[1]-v[1])**2) for u,v in zip(q,q[1:]+q[:1]))
            quality=abs(float(cross(a,b,c)))/length
            choices.append((-quality,j,(a,b,c)))
        for _,j,t in sorted(choices):
            result=solve(pending[:j]+pending[j+1:])
            if result is not None:return (t,)+result
        return None
    result=solve(ids)
    if result is None:raise ValueError('Actual finite polygon is not triangulatable: '+str([(v,[float(x) for x in points[v]]) for v in ids]))
    return list(result)
