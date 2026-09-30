"""Current-input finite verification; source bodies bound in extraction01."""

import numpy as np

def row(triangles):
 return dict(vertices=np.asarray(triangles,dtype=float).reshape((-1,3)).tolist(),triangles=np.arange(len(triangles)*3).reshape((-1,3)).tolist())

def closest_all(point,triangles):
 p=np.asarray(point);a=triangles[:,0];ab=triangles[:,1]-a;ac=triangles[:,2]-a;n=np.cross(ab,ac);nn=np.sum(n*n,axis=1)
 h=np.divide(np.sum((p-a)*n,axis=1),nn,out=np.zeros(len(nn)),where=nn>0);hit=p-h[:,None]*n;hp=hit-a
 u=np.divide(np.sum(np.cross(hp,ac)*n,axis=1),nn,out=np.zeros(len(nn)),where=nn>0);v=np.divide(np.sum(np.cross(ab,hp)*n,axis=1),nn,out=np.zeros(len(nn)),where=nn>0)
 distances=np.where((nn>0)&(u>=0)&(v>=0)&(u+v<=1),h*h*nn,np.inf);best=hit.copy()
 for i,j in ((0,1),(1,2),(2,0)):
  start=triangles[:,i];e=triangles[:,j]-start;length=np.sum(e*e,axis=1)
  t=np.clip(np.divide(np.sum((p-start)*e,axis=1),length,out=np.zeros(len(length)),where=length>0),0,1);q=start+t[:,None]*e
  dd=np.sum((p-q)**2,axis=1);use=dd<distances;distances[use]=dd[use];best[use]=q[use]
 i=int(np.argmin(distances));return dict(distance_m=float(np.sqrt(distances[i])),target_triangle=i,point=best[i].tolist())

def complete(triangle,target,fi):
 other=fi.triangles(target);tri=np.asarray(triangle,dtype=float)
 for p in list(tri)+[tri.mean(0)]:
  witness=closest_all(p,other)
  if witness['distance_m']>fi.GUARD:return dict(status='failed',method='actual-point-counterexample',source_point=p.tolist(),nearest=witness)
 ids=np.flatnonzero(np.all(other.min(1)<=tri.max(0)+fi.GUARD,axis=1)&np.all(other.max(1)>=tri.min(0)-fi.GUARD,axis=1))
 for i in sorted(ids,key=lambda j:float(np.linalg.norm(other[j].mean(0)-tri.mean(0)))):
  bound=max(float(np.linalg.norm(p-fi.point_triangle(p,other[i]))) for p in tri)
  if bound<=fi.GUARD-1e-9:return dict(status='passed',method='whole-triangle-convex-distance',target_triangle=int(i),maximum_certified_surface_distance_m=bound,cells=1)
 return dict(fi.surface_cover(row([triangle]),target),method='unchanged-production-finite-prisms')

def cover(source,target,fi):
 rows=[dict(source_triangle=i,**complete(t,target,fi)) for i,t in enumerate(fi.triangles(source))]
 return dict(status='passed' if all(r['status']=='passed' for r in rows) else 'failed',full_triangles=len(rows),rows=rows,
  maximum_certified_surface_distance_m=max((r.get('maximum_certified_surface_distance_m',0) for r in rows if r['status']=='passed'),default=0),
  failures=[r for r in rows if r['status']!='passed'])
