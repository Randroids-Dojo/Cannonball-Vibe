"""Current-input finite verification; source bodies bound in extraction01."""

from fractions import Fraction as F
import math
from .segment_distance import sub,dot,segments

def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def point_plane(p,tri):
    p=tuple(F(x) for x in p);a,b,c=[tuple(F(x) for x in v) for v in tri]
    n=cross(sub(b,a),sub(c,a));nn=dot(n,n)
    if not nn:raise ValueError('Exact degenerate gauge triangle')
    distance=dot(sub(p,a),n);q=[p[k]-distance*n[k]/nn for k in range(3)]
    tests=[dot(cross(sub(y,x),sub(q,x)),n) for x,y in ((a,b),(b,c),(c,a))]
    if min(tests)<0:return None
    return distance*distance/nn,list(p),q

def triangles(a,b):
    candidates=[]
    for first,second in ((a,b),(b,a)):
        for p in first:
            result=point_plane(p,second)
            if result:candidates.append(result)
    for p,q in zip(a,a[1:]+a[:1]):
        for r,s in zip(b,b[1:]+b[:1]):
            result=segments(p,q,r,s)
            candidates.append((F(result['exact_distance_squared_m2']),*result['closest_points_m']))
    value,p,q=min(candidates,key=lambda r:r[0])
    return {'distance_m':math.sqrt(float(value)),'exact_distance_squared_m2':str(value),
            'closest_points_m':[[float(v) for v in x] for x in (p,q)]}
