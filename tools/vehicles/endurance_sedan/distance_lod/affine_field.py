"""Read-only affine field criterion: exact closed normal-triangle minimization.

This diagnoses a preservation criterion, not a LOD or source modification.
Only the Python standard library is used. Exact rational inputs are the actual
binary64 representations read from the source-bound native payload.
"""
from collections import defaultdict
from fractions import Fraction
from itertools import permutations
from pathlib import Path
import gzip
import hashlib
import json
import math

dot=lambda a,b:sum(x*y for x,y in zip(a,b))
sub=lambda a,b:tuple(x-y for x,y in zip(a,b))


def finite3(value):
    if not isinstance(value,(list,tuple)) or len(value)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in value):
        raise ValueError('Expected finite three-coordinate point')
    return tuple(Fraction(x) for x in value)


def closest_closed_triangle(values):
    if not isinstance(values,(list,tuple)) or len(values)!=3:
        raise ValueError('Expected complete normal-space triangle')
    points=[finite3(p) for p in values]
    choices=[]
    for i,p in enumerate(points):
        weights=[Fraction(0)]*3;weights[i]=Fraction(1)
        choices.append((dot(p,p),'vertex',tuple(weights),p))
    for i,j in ((0,1),(1,2),(2,0)):
        edge=sub(points[j],points[i]);length2=dot(edge,edge)
        if length2==0:continue
        t=-dot(points[i],edge)/length2
        if 0<t<1:
            q=tuple(a+t*b for a,b in zip(points[i],edge))
            weights=[Fraction(0)]*3;weights[i]=1-t;weights[j]=t
            choices.append((dot(q,q),'edge',tuple(weights),q))
    a,b,c=points;u=sub(b,a);v=sub(c,a)
    uu,uv,vv=dot(u,u),dot(u,v),dot(v,v)
    determinant=uu*vv-uv*uv
    assert determinant>=0
    if determinant>0:
        au,av=-dot(a,u),-dot(a,v)
        s=(vv*au-uv*av)/determinant
        t=(uu*av-uv*au)/determinant
        if s>=0 and t>=0 and s+t<=1:
            q=tuple(a[i]+s*u[i]+t*v[i] for i in range(3))
            choices.append((dot(q,q),'interior',(1-s-t,s,t),q))
    answer=min(choices,key=lambda row:row[0])
    squared,location,weights,q=answer
    assert all(w>=0 for w in weights) and sum(weights)==1
    assert q==tuple(sum(weights[j]*points[j][i] for j in range(3)) for i in range(3))
    return {'squared':squared,'location':location,'barycentric':weights,'point':q,
            'degenerate':determinant==0}


def sqrt_bound(value,upper):
    if value<0:raise ValueError('Negative squared magnitude')
    out=math.sqrt(float(value))
    if not math.isfinite(out):raise ValueError('Unresolved magnitude range')
    if upper:
        while Fraction(out)**2<value:out=math.nextafter(out,math.inf)
    else:
        while Fraction(out)**2>value:out=math.nextafter(out,0.)
    return out


def preserve_field(original,actual):
    if len(original)!=3 or len(actual)!=3:raise ValueError('Incomplete corner field')
    for value in list(original)+list(actual):
        finite3(value)
        if abs(math.hypot(*value)-1.)>1e-6:raise ValueError('Raw unit guard failed')
    closest=closest_closed_triangle(original)
    squared=closest['squared']
    if squared==0:raise ValueError('Singular original affine normal field')
    delta2=max(dot(sub(finite3(a),finite3(b)),sub(finite3(a),finite3(b))) for a,b in zip(original,actual))
    minimum=sqrt_bound(squared,False)
    delta=sqrt_bound(delta2,True)
    if minimum<=0:raise ValueError('Unresolved nonzero original field magnitude')
    if delta>=minimum:raise ValueError('Residual reaches original field length')
    ratio=delta/minimum
    if ratio:
        ratio=math.nextafter(ratio,math.inf)
        bound=math.nextafter(math.degrees(math.asin(ratio)),math.inf)
    else:bound=0.
    if bound>.025:raise ValueError('Complete affine field exceeds .025 degree guard')
    return {'minimum_original_length_lower':minimum,'maximum_residual_length_upper':delta,
            'angle_upper_degrees':bound,'minimum_location':closest['location'],
            'normal_triangle_degenerate':closest['degenerate'],
            'minimum_squared_exact':[str(squared.numerator),str(squared.denominator)],
            'minimum_barycentric':[float(v) for v in closest['barycentric']]}
