"""Current-input finite verification; source bodies bound in extraction01."""

from fractions import Fraction as F
import math

def sub(a,b):return [a[k]-b[k] for k in range(3)]

def dot(a,b):return sum(x*y for x,y in zip(a,b))

def segments(aa,bb,cc,dd):
    a,b,c,d=[[F(x) for x in p] for p in (aa,bb,cc,dd)]
    u,v,w=sub(b,a),sub(d,c),sub(a,c)
    uu,vv,uv,uw,vw=dot(u,u),dot(v,v),dot(u,v),dot(u,w),dot(v,w)
    candidates=[]
    for s in (F(0),F(1)):
        candidates.append((s,max(F(0),min(F(1),(vw+s*uv)/vv))))
    for t in (F(0),F(1)):
        candidates.append((max(F(0),min(F(1),(t*uv-uw)/uu)),t))
    det=uu*vv-uv*uv
    if det:
        s=(uv*vw-vv*uw)/det;t=(uu*vw-uv*uw)/det
        if 0<=s<=1 and 0<=t<=1:candidates.append((s,t))
    scored=[]
    for s,t in candidates:
        p=[a[k]+s*u[k] for k in range(3)];q=[c[k]+t*v[k] for k in range(3)];r=sub(p,q)
        scored.append((dot(r,r),s,t,p,q))
    distance,s,t,p,q=min(scored)
    return {'exact_distance_squared_m2':str(distance),'distance_m':math.sqrt(float(distance)),
            'parameters':[str(s),str(t)],'closest_points_m':[[float(x) for x in point] for point in (p,q)]}
