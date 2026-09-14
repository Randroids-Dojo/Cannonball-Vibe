"""Native constrained triangulation, exact retained domain/boundary verification."""
from collections import Counter
from fractions import Fraction
from mathutils import Vector,geometry

def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def winding(point,loop,coords):
 result=0
 for i,j in zip(loop,loop[1:]+loop[:1]):
  a,b=coords[i],coords[j]
  if a[1]<=point[1]<b[1] and cross(a,b,point)>0:result+=1
  if b[1]<=point[1]<a[1] and cross(a,b,point)<0:result-=1
 return result

def triangulate(loops,interior,points):
 ids=sorted(set(interior)|{i for loop in loops for i in loop})
 mapping={value:i for i,value in enumerate(ids)}
 coords={i:tuple(Fraction(float(c)) for c in points[i][:2]) for i in ids}
 boundary=[(a,b) for loop in loops for a,b in zip(loop,loop[1:]+loop[:1])]
 if len({tuple(sorted(e)) for e in boundary})!=len(boundary):raise ValueError('Repeated input boundary edge')
 result=geometry.delaunay_2d_cdt([Vector(points[i][:2]) for i in ids],
  [(mapping[a],mapping[b]) for a,b in boundary],[],0,1e-12,True)
 output,edges,faces,original_vertices,_,_=result
 if len(output)!=len(ids) or len(original_vertices)!=len(ids):raise ValueError('CDT changed original vertex inventory')
 remap={}
 for i,(p,parents) in enumerate(zip(output,original_vertices)):
  if len(parents)!=1:raise ValueError('CDT merged or invented a source vertex')
  original=ids[parents[0]]
  if tuple(p)!=tuple(float(c) for c in points[original][:2]):raise ValueError('CDT moved a source vertex')
  remap[i]=original
 if len(set(remap.values()))!=len(ids):raise ValueError('CDT source vertex mapping is not bijective')
 selected=[];outside=0
 for face in faces:
  if len(face)!=3:raise ValueError('CDT did not return triangles')
  tri=tuple(remap[i] for i in face)
  area=cross(*(coords[i] for i in tri))
  if area==0:raise ValueError('CDT produced a collapsed exact triangle')
  if area<0:tri=(tri[0],tri[2],tri[1])
  center=tuple(sum(coords[i][k] for i in tri)/3 for k in (0,1))
  domain=sum(winding(center,loop,coords) for loop in loops)
  if domain==1:selected.append(tri)
  elif domain==0:outside+=1
  else:raise ValueError('Overlapping or incorrectly wound source boundaries')
 directed=Counter((a,b) for tri in selected for a,b in zip(tri,tri[1:]+tri[:1]))
 if any(n!=1 for n in directed.values()):raise ValueError('Repeated directed triangle edge')
 actual_boundary={(a,b) for a,b in directed if (b,a) not in directed}
 if actual_boundary!=set(boundary):raise ValueError('Complete indexed source boundary not preserved')
 if {i for tri in selected for i in tri}!=set(ids):raise ValueError('Source point lies outside the retained domain')
 original_area=sum(coords[a][0]*coords[b][1]-coords[b][0]*coords[a][1] for a,b in boundary)
 actual_area=sum(cross(*(coords[i] for i in tri)) for tri in selected)
 if original_area<=0 or actual_area!=original_area:raise ValueError('Exact planar domain area mismatch')
 return selected,1,{'native_operation':'mathutils.geometry.delaunay_2d_cdt','epsilon_m':1e-12,
  'source_vertices_exact':len(ids),'boundary_loops':len(loops),'complete_indexed_boundary_exact':True,
  'discarded_outside_or_hole_triangles':outside,'retained_triangles':len(selected),
  'exact_domain_double_area_numerator':str(original_area.numerator),
  'exact_domain_double_area_denominator':str(original_area.denominator),
  'full_native_self_check_required':True}
