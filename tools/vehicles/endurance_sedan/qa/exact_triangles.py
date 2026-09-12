"""Exact dyadic-input triangle intersection and shared-simplex guard.

All input floats are converted to their exact binary rational value. Plane signs,
section clipping and coplanar polygon clipping use Fraction without normalization.
This distinguishes strict actual intersections from tolerance/predicate witnesses.
"""
from fractions import Fraction as F

GUARD=F(1e-6)
def vector(p):return tuple(F(x) for x in p)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def scale(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unique(points):return list(dict.fromkeys(points))
def section(tri,origin,n):
    values=[dot(sub(p,origin),n) for p in tri]
    points=[p for p,v in zip(tri,values) if v==0]
    for i in range(3):
        j=(i+1)%3
        if values[i]*values[j]<0:
            points.append(add(tri[i],scale(sub(tri[j],tri[i]),values[i]/(values[i]-values[j]))))
    return unique(points)
def intersection(a,b):
    a=[vector(p) for p in a];b=[vector(p) for p in b]
    na=cross(sub(a[1],a[0]),sub(a[2],a[0]));nb=cross(sub(b[1],b[0]),sub(b[2],b[0]))
    if dot(na,na)==0 or dot(nb,nb)==0:raise ValueError('Exact degenerate triangle')
    da=[dot(sub(p,b[0]),nb) for p in a];db=[dot(sub(p,a[0]),na) for p in b]
    if min(da)>0 or max(da)<0 or min(db)>0 or max(db)<0:return []
    direction=cross(na,nb)
    if dot(direction,direction)==0:
        if any(v!=0 for v in da):return []
        polygon=a
        for i in range(3):
            p,q,inside=b[i],b[(i+1)%3],b[(i+2)%3]
            edge=cross(sub(q,p),nb)
            if dot(sub(inside,p),edge)<0:edge=scale(edge,-1)
            clipped=[]
            if not polygon:break
            for start,end in zip(polygon,polygon[1:]+polygon[:1]):
                ds,de=dot(sub(start,p),edge),dot(sub(end,p),edge)
                if ds>=0:clipped.append(start)
                if (ds<0)!=(de<0):clipped.append(add(start,scale(sub(end,start),ds/(ds-de))))
            polygon=unique(clipped)
        return polygon
    pa,pb=section(a,b[0],nb),section(b,a[0],na)
    if not pa or not pb:return []
    axis=max(range(3),key=lambda k:abs(direction[k]))
    lo=max(min(p[axis] for p in pa),min(p[axis] for p in pb))
    hi=min(max(p[axis] for p in pa),max(p[axis] for p in pb))
    if lo>hi:return []
    origin=pa[0]
    return unique([add(origin,scale(direction,(v-origin[axis])/direction[axis])) for v in (lo,hi)])
def distance_shared_squared(point,shared):
    if not shared or len(shared)>2:return None
    shared=[vector(p) for p in shared]
    if len(shared)==1:return dot(sub(point,shared[0]),sub(point,shared[0]))
    a,b=shared;delta=sub(b,a);length2=dot(delta,delta)
    if length2==0:return dot(sub(point,a),sub(point,a))
    t=min(F(1),max(F(0),dot(sub(point,a),delta)/length2))
    delta=sub(point,add(a,scale(sub(b,a),t)))
    return dot(delta,delta)
def inspect_pair(a,b,shared):
    points=intersection(a,b)
    outside=[];squared=[]
    for p in points:
        d=distance_shared_squared(p,shared)
        if d is None or d>GUARD*GUARD:
            outside.append(p);squared.append(d)
    return {'points':points,'outside':outside,'outside_shared_distance_squared':squared}
def jsonify(points):return [[float(x) for x in p] for p in points]
