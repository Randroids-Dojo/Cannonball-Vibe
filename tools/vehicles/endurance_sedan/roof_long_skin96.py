"""Bounded actual-scene long C-skin/return trial. No I/O, save or export.

The outer surface is a tensor-cubic longitudinal Hermite construction, with
piecewise cubic cross profiles, corrected to the actual upper support edge.
"""
import math
from collections import defaultdict,Counter
import bpy,bmesh
from mathutils import Vector

START=-1.600
END_NOMINAL=-1.310
STATIONS=(-1.590,-1.565,-1.530,-1.490,-1.445,-1.400,-1.360,-1.330)
EPS=2e-7

def unit(v):
 d=math.hypot(*v)
 if not math.isfinite(d) or d<=1e-12:raise ValueError('Singular surface vector')
 return [x/d for x in v]
def lerp(a,b,t):return [x+(y-x)*t for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def mul(a,f):return [x*f for x in a]
def plus(a,b):return [x+y for x,y in zip(a,b)]
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

class Curve:
 def __init__(self,x,ys):
  self.x=x;self.ys=ys;self.m=[]
  h=[b-a for a,b in zip(x,x[1:])]
  if min(h)<=1e-10:raise ValueError('Collapsed profile knot')
  for k in range(3):
   v=[p[k] for p in ys];d=[(b-a)/hh for a,b,hh in zip(v,v[1:],h)];m=[d[0]]
   for i in range(1,len(x)-1):
    if d[i-1]*d[i]<=0:m.append(0.)
    else:
     w1=2*h[i]+h[i-1];w2=h[i]+2*h[i-1];m.append((w1+w2)/(w1/d[i-1]+w2/d[i]))
   m.append(d[-1]);self.m.append(m)
 def eval(self,x):
  if x<self.x[0]-1e-8 or x>self.x[-1]+1e-8:raise ValueError('Profile evaluation outside domain')
  i=next((j for j in range(len(self.x)-1) if x<=self.x[j+1]),len(self.x)-2);h=self.x[i+1]-self.x[i];t=(x-self.x[i])/h
  out=[];der=[]
  for k in range(3):
   a,b=self.ys[i][k],self.ys[i+1][k];u,v=self.m[k][i:i+2]
   out.append((2*t**3-3*t*t+1)*a+(t**3-2*t*t+t)*h*u+(-2*t**3+3*t*t)*b+(t**3-t*t)*h*v)
   der.append(((6*t*t-6*t)*a+(3*t*t-4*t+1)*h*u+(-6*t*t+6*t)*b+(3*t*t-2*t)*h*v)/h)
  return out,der


class LinearCurve:
 def __init__(self,x,ys):self.x=x;self.ys=ys
 def eval(self,x):
  if x<self.x[0]-1e-8 or x>self.x[-1]+1e-8:raise ValueError('Linear boundary outside domain')
  i=next((i for i in range(len(self.x)-1) if x<=self.x[i+1]),len(self.x)-2);h=self.x[i+1]-self.x[i]
  return lerp(self.ys[i],self.ys[i+1],(x-self.x[i])/h),mul(sub(self.ys[i+1],self.ys[i]),1/h)

def ordered(points,edges):
 ad=defaultdict(list)
 for a,b in edges:ad[a].append(b);ad[b].append(a)
 if not ad or any(len(v)!=2 for v in ad.values()):raise ValueError('Expected one degree-two section cycle')
 st=max(ad,key=lambda i:(points[i][2],-abs(points[i][0])));out=[st];prev=None;cur=st
 while True:
  nxt=next(v for v in ad[cur] if v!=prev)
  if nxt==st:break
  if nxt in out:raise ValueError('Repeated section point')
  out.append(nxt);prev,cur=cur,nxt
 if len(out)!=len(ad):raise ValueError('Multiple section cycles')
 area=sum(abs(points[a][0])*points[b][2]-abs(points[b][0])*points[a][2] for a,b in zip(out,out[1:]+out[:1]))
 if area<0:out=[out[0],*reversed(out[1:])]
 return out

def slice_cycle(row,y):
 points=[];segments=[];index={}
 def vertex(p):
  key=tuple(round(x,10) for x in p)
  if key not in index:index[key]=len(points);points.append(p)
  return index[key]
 for tri in row['triangles']:
  ps=[row['vertices'][i] for i in tri];hit=[]
  for a,b in zip(ps,ps[1:]+ps[:1]):
   if (a[1]<y)!=(b[1]<y):
    t=(y-a[1])/(b[1]-a[1]);hit.append(vertex(lerp(a,b,t)))
  if len(set(hit))==2:segments.append(tuple(hit))
 edges=list(set(tuple(sorted(e)) for e in segments))
 return [points[i] for i in ordered(points,edges)]

def feature_indices(ps):
 inner=min(range(len(ps)),key=lambda i:abs(ps[i][0]));outer=max(range(len(ps)),key=lambda i:abs(ps[i][0]));low=min(range(len(ps)),key=lambda i:ps[i][2])
 if not inner<low<outer:
  def turn(i):
   a=sub(ps[i],ps[i-1]);b=sub(ps[i+1],ps[i])
   return math.atan2(math.hypot(*cross(a,b)),sum(x*y for x,y in zip(a,b)))
  if outer-inner<2:raise ValueError('Missing finite inner return span')
  low=max(range(inner+1,outer),key=turn)
 ids=[0,inner,low,outer]
 if ids!=sorted(set(ids)):raise ValueError(('Reversed actual section features',ids))
 return ids
def parameter_path(ps):
 d=[0.]
 for a,b in zip(ps,ps[1:]):d.append(d[-1]+math.dist(a,b))
 if d[-1]<=1e-6:raise ValueError('Collapsed outer section')
 return [x/d[-1] for x in d]
def linear_path(ps,t):
 ts=parameter_path(ps);i=next((i for i in range(len(ts)-1) if t<=ts[i+1]),len(ts)-2)
 return lerp(ps[i],ps[i+1],(t-ts[i])/(ts[i+1]-ts[i]))

class Surface:
 def __init__(self,row,start,end,lower,upper):
  self.row=row;self.start=start;self.end=end;self.sign=-1 if row['name'].endswith('L') else 1
  self.feature_cache={}
  li=feature_indices(lower);ui=feature_indices(upper)
  if len(upper)!=10 or ui!=[0,1,2,3]:raise ValueError('Expected actual ten-point upper section')
  self.low=lower;self.up=upper;self.li=li
  self.outer0=lower[li[3]:]+lower[:1];self.outer1=upper[3:]+upper[:1]
  self.ts0=parameter_path(self.outer0);self.ts1=parameter_path(self.outer1)
  self.p0=LinearCurve(self.ts0,self.outer0);self.p1=Curve(self.ts1,self.outer1)
  before=slice_cycle(row,start-.0001);fi=feature_indices(before);prev=before[fi[3]:]+before[:1]
  lower_derivatives=[mul(sub(p,linear_path(prev,t)),1/.0001) for p,t in zip(self.outer0,self.ts0)]
  self.d0=LinearCurve([0.,1.],[lower_derivatives[0],lower_derivatives[-1]])
  next_y=min(p[1] for p in row['vertices'] if p[1]>end+1e-5)
  after=slice_cycle(row,next_y-1e-8);af=feature_indices(after)
  # Interpolated section arbitrarily close to the actual next native ring.
  outer_after=after[af[3]:]+after[:1]
  # Trace the exact corresponding native ring points by their old indices.
  station=[p for p in row['vertices'] if abs(p[1]-next_y)<EPS]
  if len(station)!=10:raise ValueError('Missing actual following ten-point ring')
  cycle=slice_cycle(row,next_y-1e-7);cf=feature_indices(cycle)
  major=[]
  for p in cycle:
   q=min(station,key=lambda q:math.dist(p,q))
   if q not in major:major.append(q)
  if len(major)!=10:raise ValueError('Next ring attribution failed')
  mi=feature_indices(major);outer_after=major[mi[3]:]+major[:1]
  if len(outer_after)!=len(self.outer1):raise ValueError('Outer ring correspondence failed')
  self.d1=Curve(self.ts1,[mul(sub(q,p),1/(next_y-end)) for p,q in zip(self.outer1,outer_after)])
  self.next_y=next_y
  self.support_knots=sorted(set([start,end,*[p[1] for p in row['vertices'] if start<p[1]<end]]))
 def hermite(self,y,t):
  h=self.end-self.start;u=(y-self.start)/h;p,pv=self.p0.eval(t);q,qv=self.p1.eval(t);a,av=self.d0.eval(t);b,bv=self.d1.eval(t)
  c=[2*u**3-3*u*u+1,(u**3-2*u*u+u)*h,-2*u**3+3*u*u,(u**3-u*u)*h]
  d=[(6*u*u-6*u)/h,3*u*u-4*u+1,(-6*u*u+6*u)/h,3*u*u-2*u]
  f=lambda weights,vs:[sum(w*v[k] for w,v in zip(weights,vs)) for k in range(3)]
  return f(c,[p,a,q,b]),f(d,[p,a,q,b]),f(c,[pv,av,qv,bv])
 def actual_features(self,y):
  if y in self.feature_cache:return self.feature_cache[y]
  if abs(y-self.start)<1e-9:ps=self.low
  elif abs(y-self.end)<1e-8:ps=self.up
  else:ps=slice_cycle(self.row,y)
  fs=feature_indices(ps);self.feature_cache[y]=[ps[i] for i in fs];return self.feature_cache[y]
 def evaluate(self,y,t):
  p,dy,dt=self.hermite(y,t);base,bdy,_=self.hermite(y,1.)
  actual=self.actual_features(y)[0]
  gap=min([abs(y-k) for k in self.support_knots if abs(y-k)>1e-8],default=.001)
  e=min(1e-5,gap/4)
  ya=max(self.start,y-e);yb=min(self.end,y+e)
  ad=mul(sub(self.actual_features(yb)[0],self.actual_features(ya)[0]),1/(yb-ya))
  correction=sub(actual,base);dc=sub(ad,bdy)
  p=plus(p,mul(correction,t));dy=plus(dy,mul(dc,t));dt=plus(dt,correction)
  n=unit(mul(cross(dt,dy),-self.sign))
  return p,n,dy,dt
 def point(self,y,t):return self.evaluate(y,t)[0]
 def inner(self,y):
  f=self.actual_features(y);d=self.point(y,0.)
  return f[0],f[1],plus(f[2],sub(d,f[3]))
 def record(self):
  return {'start_y_m':self.start,'end_y_m':self.end,'cross_parameters':self.ts1,'lower_profile_parameters':self.ts0,
   'lower_profile':self.outer0,'upper_profile':self.outer1,'lower_derivatives':self.d0.ys,'lower_derivative_parameters':self.d0.x,'upper_derivatives':self.d1.ys,
   'following_native_station_y_m':self.next_y,'support_knots':self.support_knots,
   'kind':'Longitudinal cubic Hermite skin, exact piecewise-linear lower boundary, monotone cubic upper/cross tracks and native upper-edge correction; outward differential field, connected return follows old local lip offset.'}

def make(obj,row,encode):
 if obj.name not in ('LOD0_StampedPillar_CL','LOD0_StampedPillar_CR') or obj.modifiers:raise ValueError('Expected frozen actual C mesh')
 if len(row['triangles'])!=448 or len(obj.data.polygons)!=448:raise ValueError('This trial requires actual57 triangular C topology')
 end=min({p[1] for p in row['vertices']},key=lambda y:abs(y-END_NOMINAL))
 if abs(end-END_NOMINAL)>EPS:raise ValueError('Missing current upper boundary')
 raw=[tuple(v.co) for v in obj.data.vertices];world=[list(obj.matrix_world@Vector(p)) for p in raw]
 if world!=row['vertices']:raise ValueError('Unexpected raw/evaluated vertex mapping')
 inv=obj.matrix_world.inverted();points=list(raw);wp=list(world);new_keys={tuple(p):i for i,p in enumerate(points)}
 faces=[];records=[];uvs={n:[] for n in row['uvs']};targets=[];mats=[];owned=[];outer_params={};corner_owners=[]
 def vertex(p):
  co=tuple(inv@Vector(p))
  if co not in new_keys:new_keys[co]=len(points);points.append(co);wp.append(list(obj.matrix_world@Vector(co)))
  return new_keys[co]
 def emit(ids,vals=None,ti=None,parameters=None):
  if len(set(ids))!=3:raise ValueError('Collapsed proposed triangle')
  faces.append(tuple(ids));records.append({'original_triangle':ti,'values':vals,'parameters':parameters})
  mats.append(0 if ti is None else row['triangle_materials'][ti])
  if ti is None:owned.append(len(faces)-1)
  for j,v in enumerate(ids):
   if vals is not None:targets.append(vals[j]['n']);corner_owners.append(vals[j].get('loop'))
   elif parameters is not None:
    y,t=parameters[j];n=surface.evaluate(y,t)[1];targets.append(list((obj.matrix_world.to_3x3().transposed()@Vector(n)).normalized()));corner_owners.append(None)
   else:targets.append(None);corner_owners.append(None)
   for name in uvs:uvs[name].append(vals[j]['uv'][name] if vals is not None else [abs(wp[v][0])*2,wp[v][1]*2+3])
 def retain(y,less):
  begin=len(faces)
  for ti,(tri,loops) in enumerate(zip(row['triangles'],row['triangle_loops'])):
   values=[{'p':wp[v],'v':v,'n':row['normals'][li],'uv':{n:row['uvs'][n][li] for n in uvs},'loop':li} for v,li in zip(tri,loops)]
   cl=[]
   for a,b in zip(values,values[1:]+values[:1]):
    ai=a['p'][1]<=y if less else a['p'][1]>=y;bi=b['p'][1]<=y if less else b['p'][1]>=y
    if ai:cl.append(a)
    if ai!=bi:
     t=(y-a['p'][1])/(b['p'][1]-a['p'][1]);p=lerp(a['p'],b['p'],t);p[1]=y
     if t<=1e-12:cl.append(a)
     elif t>=1-1e-12:cl.append(b)
     else:cl.append({'p':p,'v':vertex(p),'n':unit(lerp(a['n'],b['n'],t)),'uv':{n:lerp(a['uv'][n],b['uv'][n],t) for n in uvs},'loop':None})
   unique=[]
   for q in cl:
    if not unique or q['v']!=unique[-1]['v']:unique.append(q)
   if len(unique)>1 and unique[0]['v']==unique[-1]['v']:unique.pop()
   for k in range(1,len(unique)-1):
    v=[unique[i] for i in (0,k,k+1)];emit([q['v'] for q in v],v,ti)
  edges=Counter(tuple(sorted((a,b))) for f in faces[begin:] for a,b in zip(f,f[1:]+f[:1]))
  boundary=[e for e,n in edges.items() if n==1]
  if any(abs(wp[v][1]-y)>EPS for e in boundary for v in e):raise ValueError('Unexpected retained boundary')
  return ordered(wp,boundary)
 lower=retain(START,True);upper=retain(end,False)
 surface=Surface(row,START,end,[wp[i] for i in lower],[wp[i] for i in upper])
 lower_f=feature_indices([wp[i] for i in lower]);upper_f=feature_indices([wp[i] for i in upper])
 if len(lower)!=64 or upper_f!=[0,1,2,3]:raise ValueError(('Unexpected native boundary counts',len(lower),upper_f))
 ring_list=[];ring_y=[];ring_parameters=[]
 for y in STATIONS:
  b,i,l=surface.inner(y);ids=[vertex(b),vertex(i),vertex(l)]
  u=(y-START)/(end-START);low_parameters=[0.,.015,.040,.200,.550,.850,.980,1.]
  parameters=[a+(b-a)*u for a,b in zip(low_parameters,surface.ts1)]
  ids += [vertex(surface.point(y,t)) for t in parameters[:-1]]
  if len(ids)!=10 or len(set(ids))!=10:raise ValueError('Collapsed formed ring')
  ring_list.append(ids);ring_y.append(y);ring_parameters.append(parameters)
 ring_list.append(upper);ring_y.append(end);ring_parameters.append(surface.ts1)
 # Complete exact old lower polygon connects by four actual semantic sectors.
 destinations=[0,1,2,3]
 for k,a in enumerate(lower_f):
  b=lower_f[k+1] if k+1<4 else len(lower)
  old=[lower[j%len(lower)] for j in range(a,b+1)]
  da=destinations[k];db=destinations[k+1] if k+1<4 else 10
  new=[ring_list[0][j%10] for j in range(da,db+1)]
  # Monotone parameter zipper; outer sector uses its actual profile lengths.
  ta=parameter_path([wp[v] for v in old]);tb=ring_parameters[0] if k==3 else parameter_path([wp[v] for v in new])
  ia=ib=0
  while ia<len(old)-1 or ib<len(new)-1:
   advance_old=ib==len(new)-1 or (ia<len(old)-1 and ta[ia+1]<=tb[ib+1])
   if advance_old:
    ids=[old[ia],old[ia+1],new[ib]];param=[(START,ta[ia]),(START,ta[ia+1]),(ring_y[0],tb[ib])];ia+=1
   else:
    ids=[old[ia],new[ib+1],new[ib]];param=[(START,ta[ia]),(ring_y[0],tb[ib+1]),(ring_y[0],tb[ib])];ib+=1
   emit(ids,parameters=param if k==3 else None)
   if k<3:records[-1]['return_sector']=k
 for ai,(aa,bb) in enumerate(zip(ring_list,ring_list[1:])):
  for i in range(10):
   jj=(i+1)%10
   for loc in ((0,1,3),(0,3,2)):
    vertices=[aa[i],aa[jj],bb[i],bb[jj]];ids=[vertices[z] for z in loc]
    if i>=3:
     ys=[ring_y[ai],ring_y[ai],ring_y[ai+1],ring_y[ai+1]];ts=[ring_parameters[ai][i-3],ring_parameters[ai][i-2],ring_parameters[ai+1][i-3],ring_parameters[ai+1][i-2]];param=[(ys[z],ts[z]) for z in loc]
    else:param=None
    emit(ids,parameters=param)
    if i<3:records[-1]['return_sector']=i
 used=sorted({v for f in faces for v in f});remap={v:i for i,v in enumerate(used)}
 mesh=bpy.data.meshes.new(obj.name+'_PrivateLong96');mesh.from_pydata([points[v] for v in used],[],[tuple(remap[v] for v in f) for f in faces]);mesh.update()
 bm=bmesh.new()
 try:bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh)
 finally:bm.free()
 lookup={tuple(sorted(remap[v] for v in f)):i for i,f in enumerate(faces)}
 normal_targets=[];values={n:[] for n in uvs};owners=[];old_poly=[]
 for poly in mesh.polygons:
  old=lookup[tuple(sorted(poly.vertices))];poly.use_smooth=True;poly.material_index=mats[old];old_poly.append(old)
  for v in poly.vertices:
   j=3*old+faces[old].index(used[v]);normal_targets.append(targets[j]);owners.append(corner_owners[j])
   for name in uvs:values[name].append(uvs[name][j])
 mesh.set_sharp_from_angle(angle=math.radians(35));mesh.update();auto=[tuple(n.vector) for n in mesh.corner_normals]
 # A shared angle-weighted field follows the actual new skin facets. Sharp
 # connected-return faces retain their separate native smooth groups. This is
 # the expressly authored64-incident-face shading scope, not old-field reuse.
 skin_polys=[p.index for p in mesh.polygons if records[old_poly[p.index]]['parameters'] is not None]
 field_sum=defaultdict(lambda:Vector((0.,0.,0.)));skin_vertices=set()
 for pi in skin_polys:
  poly=mesh.polygons[pi];ids=list(poly.vertices);co=[mesh.vertices[v].co for v in ids]
  for k,v in enumerate(ids):
   a=(co[(k-1)%3]-co[k]).normalized();b=(co[(k+1)%3]-co[k]).normalized()
   angle=math.atan2(a.cross(b).length,a.dot(b));field_sum[v]+=poly.normal*angle;skin_vertices.add(v)
 skin_target={v:list(n.normalized()) for v,n in field_sum.items()}
 # At the existing upper ring, keep the actual adjacent retained skin field.
 upper_targets=defaultdict(list)
 for poly in mesh.polygons:
  rec=records[old_poly[poly.index]]
  if rec['original_triangle'] is None:continue
  for li in poly.loop_indices:
   v=mesh.loops[li].vertex_index
   if v in skin_vertices and abs(wp[used[v]][1]-end)<EPS:upper_targets[v].append(normal_targets[li])
 for v,choices in upper_targets.items():
  target=Vector(skin_target[v]);skin_target[v]=max(choices,key=lambda n:target.dot(Vector(n)))
 for pi in skin_polys:
  for li in mesh.polygons[pi].loop_indices:normal_targets[li]=skin_target[mesh.loops[li].vertex_index]
 # The three formed-return sectors are independently smoothed along their
 # real faces; no native transitive35-degree fan may cross a folded sector.
 return_incident=defaultdict(list)
 for poly in mesh.polygons:
  sector=records[old_poly[poly.index]].get('return_sector')
  if sector is None:continue
  ids=list(poly.vertices);co=[mesh.vertices[v].co for v in ids]
  for k,v in enumerate(ids):
   a=(co[(k-1)%3]-co[k]).normalized();b=(co[(k+1)%3]-co[k]).normalized()
   angle=math.atan2(a.cross(b).length,a.dot(b));return_incident[(sector,v)].append((poly.index,poly.normal.copy(),angle))
 # A complete35-degree cone per cluster, not transitive angle chaining.
 # This retains true folded-return splits and guarantees positive incidence.
 return_target={};cos_limit=math.cos(math.radians(35))
 for key,items in sorted(return_incident.items()):
  groups=[]
  for item in sorted(items,key=lambda q:q[0]):
   chosen=next((g for g in groups if all(item[1].dot(q[1])>=cos_limit for q in g)),None)
   if chosen is None:groups.append([item])
   else:chosen.append(item)
  for group in groups:
   normal=sum((n*w for _,n,w in group),Vector((0.,0.,0.))).normalized()
   for pi,_,_ in group:return_target[(pi,key[1])]=list(normal)
 for poly in mesh.polygons:
  if records[old_poly[poly.index]].get('return_sector') is None:continue
  for li in poly.loop_indices:normal_targets[li]=return_target[(poly.index,mesh.loops[li].vertex_index)]
 # Match each cut edge to its actual new incident face, preserving distinct
 # real folded-return normals. The old fragment's non-cut corners stay old.
 edge_faces=defaultdict(list)
 for poly in mesh.polygons:
  ids=list(poly.vertices)
  for a,b in zip(ids,ids[1:]+ids[:1]):edge_faces[tuple(sorted((a,b)))].append(poly.index)
 cut_targets={};cut_links=[];upper_links=[]
 for edge,owners2 in edge_faces.items():
  if len(owners2)!=2:continue
  at_lower=all(abs(wp[used[v]][1]-START)<EPS for v in edge);at_upper=all(abs(wp[used[v]][1]-end)<EPS for v in edge)
  if not at_lower and not at_upper:continue
  old_faces=[pi for pi in owners2 if records[old_poly[pi]]['original_triangle'] is not None]
  new_faces=[pi for pi in owners2 if records[old_poly[pi]]['original_triangle'] is None]
  if len(old_faces)!=1 or len(new_faces)!=1:continue
  old_pi,new_pi=old_faces[0],new_faces[0];owner=records[old_poly[old_pi]]['original_triangle']
  if at_upper:
   for v in edge:
    old_li=next(li for li in mesh.polygons[old_pi].loop_indices if mesh.loops[li].vertex_index==v)
    new_li=next(li for li in mesh.polygons[new_pi].loop_indices if mesh.loops[li].vertex_index==v)
    normal_targets[new_li]=normal_targets[old_li]
   upper_links.append({'edge':list(edge),'source_triangle':owner,'new_triangle':new_pi,'retained_fragment':old_pi})
   continue
  for v in edge:
   li=next(li for li in mesh.polygons[new_pi].loop_indices if mesh.loops[li].vertex_index==v)
   value=normal_targets[li] if normal_targets[li] is not None else auto[li]
   key=(owner,v)
   if key in cut_targets and math.dist(cut_targets[key],value)>1e-6:raise ValueError('Ambiguous authored cut field')
   cut_targets[key]=value
  cut_links.append({'edge':list(edge),'source_triangle':owner,'new_triangle':new_pi,'retained_fragment':old_pi})
 for poly in mesh.polygons:
  owner=records[old_poly[poly.index]]['original_triangle']
  if owner is None:continue
  for li in poly.loop_indices:
   key=(owner,mesh.loops[li].vertex_index)
   if key in cut_targets:normal_targets[li]=cut_targets[key]

 normal_targets=[n if n is not None else auto[i] for i,n in enumerate(normal_targets)]
 for name,v in values.items():
  layer=mesh.uv_layers.new(name=name)
  for d,x in zip(layer.data,v):d.uv=x
 for material in obj.data.materials:mesh.materials.append(material)
 code=encode(mesh,normal_targets)
 if not code['passed']:raise ValueError('Existing normal encoding guard failed')
 # Re-use original code only where both the whole native triangle and its
 # original per-corner encoding space are unchanged; validate actual decoding.
 original_codes=[tuple(x.value) for x in obj.data.attributes['custom_normal'].data]
 original_normals=[tuple(n.vector) for n in obj.data.corner_normals]
 exact_whole=0;outside=[]
 for poly,original in zip(mesh.polygons,old_poly):
  rec=records[original];ti=rec['original_triangle']
  if ti is None:continue
  old_coords=[raw[v] for v in row['triangles'][ti]];new_coords=[tuple(mesh.vertices[v].co) for v in poly.vertices]
  whole=set(old_coords)==set(new_coords)
  if whole:
   exact_whole+=1
   for li in poly.loop_indices:
    source=owners[li]
    if source is None:raise ValueError('Lost original whole-face corner owner')
    mesh.attributes['custom_normal'].data[li].value=original_codes[source];outside.append((li,source))
 mesh.update();decoded=[tuple(n.vector) for n in mesh.corner_normals]
 exact=sum(decoded[a]==original_normals[b] for a,b in outside)
 outside_error=max((math.degrees(math.atan2(math.hypot(*cross(decoded[a],original_normals[b])),sum(x*y for x,y in zip(decoded[a],original_normals[b])))) for a,b in outside),default=0.)
 if outside_error>.025:raise ValueError(('Outside native field drift',outside_error,exact,len(outside)))
 candidate=bpy.data.objects.new(obj.name+'_PrivateLong96',mesh);candidate.matrix_world=obj.matrix_world.copy();bpy.context.scene.collection.objects.link(candidate)
 # Rebind face ownership to actual output polygon order for independent tests.
 detail=[]
 for pi,original in enumerate(old_poly):
  rec=records[original];face=faces[original]
  params=None if rec['parameters'] is None else {remap[v]:list(p) for v,p in zip(face,rec['parameters'])}
  detail.append({'output_triangle':pi,'original_triangle':rec['original_triangle'],'skin_parameters':params,'return_sector':rec.get('return_sector')})
 return candidate,{'domain_y_m':[START,end],'surface':surface.record(),'ring_y_m':ring_y,'ring_cross_parameters':ring_parameters,'ring_world_points':[[wp[v] for v in ring] for ring in ring_list],
  'triangles':len(faces),'delta':len(faces)-len(row['triangles']),'retained_lower_boundary_edges':len(lower),'retained_upper_boundary_edges':len(upper),
  'exact_retained_whole_triangles':exact_whole,'outside_whole_corner_count':len(outside),'outside_whole_normals_bit_exact':exact,
  'outside_whole_max_normal_degrees':outside_error,'normal_encoding':code,'face_ownership':detail,
  'authored_local_normal_targets':normal_targets,'skin_triangles':skin_polys,'lower_cut_links':cut_links,'upper_cut_links':upper_links,
  'authored_shading_original_triangles':sorted(set(x['source_triangle'] for x in cut_links)),
  'scope':'Geometry authored only between exact cut sections; retained fragments keep original affine geometry/UV. New angle-weighted geometric skin targets and finite adjacent-fragment transition use authorized64-face shading scope. Upper boundary uses actual retained field; all original whole native triangles/corner codes outside remain exact. Native encoding and complete target interpolation are independently measured; no old-interior-normal reproduction is claimed inside shading scope.'},surface
