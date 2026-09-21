"""Geometry-integrated normal field independent of target triangulation.
The finite guide is observed source geometry. A local quadratic Monge fit uses
area quadrature rather than skinny-triangle corner averaging. Radial returns
and material/physical creases are separate named domains. No old N is used.
"""
import math
from collections import defaultdict
import numpy as np
from .arch import arch_faces

def unit(a):
 a=np.asarray(a,dtype=float);l=np.linalg.norm(a)
 if not math.isfinite(l)or l<1e-14:raise ValueError('Invalid field vector')
 return a/l

def geometry_fans(row,outer):
 ps=np.asarray(row['vertices']);ts=np.asarray(row['triangles']);xyz=ps[ts];cr=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]);ns=cr/np.linalg.norm(cr,axis=1)[:,None]
 incident=defaultdict(list);edges=defaultdict(list);graph=defaultdict(set);weights={};hard=[];arches=arch_faces(row)
 for f,t in enumerate(ts):
  for j,v in enumerate(t):
   incident[int(v)].append(f);a=xyz[f,(j+1)%3]-xyz[f,j];b=xyz[f,(j+2)%3]-xyz[f,j];weights[f,int(v)]=math.atan2(float(np.linalg.norm(np.cross(a,b))),float(a@b))
  for a,b in zip(t,np.roll(t,-1)):edges[tuple(sorted((int(a),int(b))))].append(f)
 for (a,b),fs in edges.items():
  if len(fs)!=2:raise ValueError('Open field source')
  f,g=fs
  if row['triangle_materials'][f]!=row['triangle_materials'][g]or(f in arches)!=(g in arches)or(f in outer)!=(g in outer)or ns[f]@ns[g]<math.cos(math.radians(30)):
   hard.append([a,b]);continue
  for v in(a,b):graph[v,f].add(g);graph[v,g].add(f)
 result=[[None]*3 for _ in ts];members={};records=[]
 for v,fs in incident.items():
  pending=set(fs)
  while pending:
   first=min(pending);pending.remove(first);todo=[first];fan=[]
   while todo:
    f=todo.pop();fan.append(f)
    for g in graph[v,f]:
     if g in pending:pending.remove(g);todo.append(g)
   radial=first in arches;n=unit([0,1.46-ps[v,1],.3433-ps[v,2]])if radial else unit(sum((ns[f]*weights[f,v]for f in fan),np.zeros(3)))
   if min(ns[f]@n for f in fan)<=0:raise ValueError(('Reference fan leaves its hemisphere',v,fan))
   for f in fan:result[f][list(ts[f]).index(v)]=n.tolist();members[f,v]=len(records)
   records.append({'vertex':v,'faces':sorted(fan),'target':n.tolist(),'domain':'radial return'if radial else'30degree physical fan'})
 return result,records,members,ns,hard,arches

class Fit:
 def __init__(self,guide):
  self.guide=guide;self.ps=np.asarray(guide['vertices']);self.ts=np.asarray(guide['triangles']);self.xyz=self.ps[self.ts];cr=np.cross(self.xyz[:,1]-self.xyz[:,0],self.xyz[:,2]-self.xyz[:,0]);self.area=np.linalg.norm(cr,axis=1)/2;self.ns=cr/(2*self.area[:,None]);self.center=self.xyz.mean(axis=1)
  # Positive six-point degree-four quadrature, exact for a quadratic fit's
  # unweighted Gram polynomial. The smooth distance kernel is evaluated at
  # each point; no tessellation-independent exactness is claimed for it.
  a=.445948490915965;b=.108103018168070;c=.091576213509771;d=.816847572980459
  self.bary=np.array([[a,a,b],[a,b,a],[b,a,a],[c,c,d],[c,d,c],[d,c,c]])
  self.qw=np.array([.223381589678011]*3+[.109951743655322]*3)
 def normal(self,p,seed,radius=.065):
  p=np.asarray(p);n=unit(seed);axis=np.eye(3)[int(np.argmin(abs(n)))];u=unit(np.cross(axis,n));v=np.cross(n,u)
  near=np.flatnonzero((np.linalg.norm(self.center-p,axis=1)<radius*2)&(self.ns@n>math.cos(math.radians(60))))
  if not len(near):raise ValueError('No finite guide support')
  # An isolated finite triangle supplies an exact planar tangent, not six
  # independently observed curvature coefficients. This is a separate
  # geometric support class; multi-facet quadratic rank remains mandatory.
  if len(near)==1:
   i=int(near[0]);target=self.ns[i].copy()
   if target@n<=0:raise ValueError('Single-facet plane reverses its physical fan')
   return target,{'guide_faces':[i],'radius_m':radius,'support_model':'actual isolated finite planar facet','area_weighted_rms_m':0.,'finite_plane_points_m':self.xyz[i].tolist(),'normal':target.tolist()}
  samples=np.einsum('qj,fjk->fqk',self.bary,self.xyz[near]);delta=samples-p;uv=np.stack((delta@u,delta@v),axis=-1)/radius;z=delta@n/radius;dist=np.linalg.norm(delta,axis=-1)/radius
  weights=self.area[near,None]*self.qw[None,:]*np.exp(-3*dist*dist)
  x=uv[:,:,0].ravel();y=uv[:,:,1].ravel();A=np.column_stack([np.ones(len(x)),x,y,x*x,x*y,y*y]);w=np.sqrt(weights.ravel());Aw=A*w[:,None];zw=z.ravel()*w
  coef,res,rank,singular=np.linalg.lstsq(Aw,zw,rcond=1e-10)
  if rank!=6:raise ValueError(('Underdetermined finite guide quadratic',rank,len(near)))
  target=unit(n-coef[1]*u-coef[2]*v)
  residual=float(np.sqrt(np.sum(weights*(np.einsum('ij,j->i',A,coef).reshape(z.shape)-z)**2)/np.sum(weights))*radius)
  return target,{'guide_faces':near.tolist(),'radius_m':radius,'area_weighted_rms_m':residual,'condition_number':float(singular[0]/singular[-1]),'coefficients':coef.tolist(),'basis':[u.tolist(),v.tolist(),n.tolist()]}

def build(row,candidate,guide,domain):
 outer=set(domain['outer_sheet_source_triangles']);selected={f for f,s in enumerate(candidate['source_face_ids'])if s in outer};base,fans,membership,ns,hard,arches=geometry_fans(candidate,selected);fit=Fit(guide);ps=np.asarray(candidate['vertices']);ts=np.asarray(candidate['triangles']);records=[];replaced=set()
 for fan in fans:
  fs=fan['faces'];v=fan['vertex'];chosen=[f for f in fs if f in selected and f not in arches]
  if not chosen:continue
  # A single physical fan gets one fit; selection does not create a shading
  # seam at an otherwise continuous retained/generated fragment boundary.
  area=[]
  for f in chosen:
   p=ps[ts[f]];area.append(np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0])))
  seed=unit(np.average(ns[chosen],axis=0,weights=area));target,proof=fit.normal(ps[v],seed)
  positive=min(float(ns[f]@target)for f in fs)
  if positive<=0:raise ValueError(('Finite guide fit crosses physical fan hemisphere',v,fs,positive))
  for f in fs:base[f][list(ts[f]).index(v)]=target.tolist();replaced.add(f)
  records.append({'vertex':v,'faces':fs,'selected_seed_faces':chosen,'target':target.tolist(),'minimum_hemisphere':positive,**proof})
 return base,{'schema':'complete-front-geometric-field40.v1','guide_kind':guide['kind'],'old_native_normals_used':False,'guide_fits':records,'physical_fans':fans,'hard_edges':hard,'radial_returns':arches,'fitted_faces':sorted(replaced),'source_outer_domain':sorted(outer),'quad_rule':'positive six-point degree-four triangle area quadrature','field_scope':'complete three-panel authored normals; original geometry unchanged'}
