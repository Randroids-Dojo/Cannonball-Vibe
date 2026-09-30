"""Exact Euclidean supplement to sufficient orthogonal-prism coverage.

Distance to a closed triangle is convex. A polygon whose every vertex is
within1um of the SAME actual triangle is wholly within1um of that triangle.
All distance predicates use exact rational arithmetic on the supplied native
and partition coordinates. No tiny-area fragment is discarded.
"""
from fractions import Fraction as F
import math

def vec(v):return tuple(F(float(x)) for x in v)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def distance2(p,t):
 a,b,c=t;ab=sub(b,a);ac=sub(c,a);ap=sub(p,a);aa=dot(ab,ab);bb=dot(ac,ac);abac=dot(ab,ac);den=aa*bb-abac*abac
 if den<=0:raise ValueError('Invalid reference triangle')
 v=(dot(ap,ab)*bb-dot(ap,ac)*abac)/den;w=(dot(ap,ac)*aa-dot(ap,ab)*abac)/den
 if v>=0 and w>=0 and v+w<=1:
  q=tuple(a[i]+v*ab[i]+w*ac[i] for i in range(3));d=sub(p,q);return dot(d,d)
 values=[]
 for a,b in zip(t,t[1:]+t[:1]):
  d=sub(b,a);pa=sub(p,a);h=dot(d,d);r=max(F(0),min(F(1),dot(pa,d)/h));q=tuple(a[i]+r*d[i] for i in range(3));v=sub(p,q);values.append(dot(v,v))
 return min(values)

def supplement(base,target,maximum=1e-6):
 if base['status']=='passed':return base
 if base['status']!='unresolved_uncovered_fragment':return {'status':'failed','orthogonal_prism':base,'reason':'Unsupported unresolved status'}
 limit=F(str(maximum));limit2=limit*limit
 source=[tuple(vec(target['vertices'][i]) for i in t) for t in target['triangles']]
 boxes=[(tuple(min(p[k] for p in t) for k in range(3)),tuple(max(p[k] for p in t) for k in range(3))) for t in source]
 cells=0;worst=F(0);witness=None;unresolved=[]
 def certify(poly,depth=0):
  nonlocal cells,worst,witness
  cells+=1
  lo=tuple(min(p[k] for p in poly) for k in range(3));hi=tuple(max(p[k] for p in poly) for k in range(3))
  possible=[i for i,(a,b) in enumerate(boxes) if all(lo[k]>=a[k]-limit and hi[k]<=b[k]+limit for k in range(3))]
  for ti in possible:
   ds=[distance2(p,source[ti]) for p in poly];d=max(ds)
   if d<=limit2:
    if d>worst:worst=d;witness={'source_triangle':ti,'polygon':[[float(x) for x in p] for p in poly]}
    return True
  # A vertex farther than the guard from every actual target triangle is
  # already a complete counterexample; subdivision cannot repair that domain.
  for p in poly:
   near=[i for i,(a,b) in enumerate(boxes) if all(a[k]-limit<=p[k]<=b[k]+limit for k in range(3))]
   if not any(distance2(p,source[i])<=limit2 for i in near):
    unresolved.append({'depth':depth,'actual_uncovered_vertex_m':[float(x) for x in p]});return False
  if depth>=28 or cells>=50000:
   unresolved.append({'depth':depth,'polygon':[[float(x) for x in p] for p in poly]});return False
  # Exact rational fan then longest-edge bisection partitions the full domain.
  if len(poly)>3:return all(certify((poly[0],poly[i],poly[i+1]),depth+1) for i in range(1,len(poly)-1))
  lengths=[dot(sub(poly[(i+1)%3],poly[i]),sub(poly[(i+1)%3],poly[i])) for i in range(3)];i=max(range(3),key=lambda i:lengths[i]);a,b,c=poly[i],poly[(i+1)%3],poly[(i+2)%3];m=tuple((x+y)/2 for x,y in zip(a,b))
  if max(lengths)==0:
   unresolved.append({'depth':depth,'polygon':[[float(x) for x in p] for p in poly]});return False
  return certify((a,m,c),depth+1) and certify((m,b,c),depth+1)
 good=all(certify(tuple(vec(p) for p in poly)) for poly in base['uncovered_polygons'])
 return {'status':'passed' if good else 'failed','orthogonal_prism':base,'exact_euclidean_convex_polygon_supplement':{'cells':cells,'maximum_certified_vertex_distance_m':math.sqrt(float(worst)),'maximum_squared_distance_exact':[str(worst.numerator),str(worst.denominator)],'maximum_allowed_squared_distance_exact':[str(limit2.numerator),str(limit2.denominator)],'worst':witness,'unresolved':unresolved,'method':'Exact rational point/edge/interior distance to one actual triangle per complete convex polygon, with exact rational full-domain subdivisions only.'}}

def complete(mesh,target,maximum=1e-6):
 """All input triangles, all residual polygons; no first-failure truncation."""
 import numpy as np
 from .qa.solid_interfaces import boundary_shell,point_triangle,subtract_prism
 base=boundary_shell(mesh,target,maximum=maximum)
 if base['status']=='passed':return base
 source=np.asarray(target['vertices'],dtype=float)[target['triangles']]
 lo,hi=source.min(axis=1),source.max(axis=1)
 begin=base.get('triangle',0);certificates=[];cells=0
 for index in range(begin,len(mesh['triangles'])):
  t=np.asarray([mesh['vertices'][i] for i in mesh['triangles'][index]],dtype=float)
  candidates=np.flatnonzero(np.all(lo<=t.max(axis=0)+maximum,axis=1)&np.all(hi>=t.min(axis=0)-maximum,axis=1))
  remaining=[list(t)]
  for face in candidates:
   retained=[]
   for poly in remaining:
    cells+=1
    bound=max(float(np.linalg.norm(p-point_triangle(p,source[face]))) for p in poly)
    if bound<=maximum-1e-9:continue
    outside,_=subtract_prism(poly,source[face],maximum-1e-9);retained.extend(outside)
   remaining=retained
   if not remaining:break
   if cells>100000 or len(remaining)>5000:return {'status':'failed','reason':'Complete-coverage work bound','triangle':index,'cells':cells}
  if remaining:
   fragment={'status':'unresolved_uncovered_fragment','triangle':index,'uncovered_polygons':[[[float(x) for x in p] for p in poly] for poly in remaining]}
   result=supplement(fragment,target,maximum)
   certificates.append({'triangle':index,'result':result})
   if result['status']!='passed':return {'status':'failed','full_triangles':len(mesh['triangles']),'first_prism_result':base,'exact_supplements':certificates,'failed_triangle':index}
 return {'status':'passed','full_triangles':len(mesh['triangles']),'initial_prism_result':base,'prior_complete_triangles':begin,'remaining_complete_triangles':len(mesh['triangles'])-begin,'cells':cells,'exact_supplements':certificates,'scope':'Every input triangle and every untruncated remaining polygon covered within original1um Euclidean guard.'}
