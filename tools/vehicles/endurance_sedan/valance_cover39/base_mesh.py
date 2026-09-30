"""Current-input cover construction: base_mesh. Source provenance is in the private port manifest."""

from collections import Counter, defaultdict

import math

import struct

from . import domain as domain07

from . import layout as layout11

def f32(v):return struct.unpack('f',struct.pack('f',float(v)))[0]

def unit(v):
 length=math.sqrt(sum(x*x for x in v))
 if not length or not math.isfinite(length):raise ValueError('Invalid authored normal')
 return [x/length for x in v]

def angle(a,b):return math.degrees(math.atan2(math.sqrt(sum(v*v for v in domain07.cross(a,b))),domain07.dot(a,b)))

def loops(triangles):
 edges=Counter((t[i],t[(i+1)%len(t)]) for t in triangles for i in range(len(t)))
 out={}
 for (a,b),count in edges.items():
  balance=count-edges[(b,a)]
  if balance<=0:continue
  if balance!=1 or a in out:raise ValueError('Invalid finite boundary degree')
  out[a]=b
 result=[]
 while out:
  start=min(out);poly=[start];v=out.pop(start)
  while v!=start:
   if v not in out:raise ValueError('Open finite boundary')
   poly.append(v);v=out.pop(v)
  if len(poly)<3:raise ValueError('Degenerate finite boundary')
  result.append(poly)
 return result

def ears(ids,points):
 """Exact projected ear clipping; all supplied boundary nodes remain used."""
 pending=list(ids);result=[]
 signed=sum(layout11.cross2(points[a],points[b]) for a,b in zip(pending,pending[1:]+pending[:1]))
 if not signed:raise ValueError('Zero projected polygon')
 sign=1 if signed>0 else -1
 def orient(a,b,c):return sign*layout11.cross2(layout11.sub2(points[b],points[a]),layout11.sub2(points[c],points[a]))
 while len(pending)>3:
  found=False
  for j,b in enumerate(pending):
   a,c=pending[j-1],pending[(j+1)%len(pending)]
   if orient(a,b,c)<=0:continue
   if any(v not in (a,b,c) and orient(a,b,v)>=0 and orient(b,c,v)>=0 and orient(c,a,v)>=0 for v in pending):continue
   result.append((a,b,c));pending.pop(j);found=True;break
  if not found:raise ValueError('Exact finite polygon cannot be triangulated')
 if len(pending)!=3 or orient(*pending)<=0:raise ValueError('Degenerate final ear')
 result.append(tuple(pending));return result

def prepare(current,reference,triangle_domains,exact):
 """Caller supplies current native rows and independently proved finite roles.

 Roles cover every actual input triangle. The native wrapper must validate
 their complete current geometry against its own original ribbon/cutters.
 No scene/report/file operation or archived geometry occurs here.
 """
 domain07.validate(current);domain07.validate(reference)
 if len(triangle_domains)!=len(current['triangles']) or any(type(n) is not str for n in triangle_domains):raise ValueError('Incomplete current finite roles')
 if not set(triangle_domains).issubset({'front','back','top','bottom','left','right'}|{f'passage_{s}_{i}' for s in (-1,1) for i in range(8)}):raise ValueError('Unknown finite role')
 front={i for i,d in enumerate(triangle_domains) if d=='front'};back={i for i,d in enumerate(triangle_domains) if d=='back'}
 if not front or not back:raise ValueError('Missing outer or inboard surface')
 oldfront={v for i in front for v in current['triangles'][i]};oldback={v for i in back for v in current['triangles'][i]}
 if oldfront&oldback:raise ValueError('Outer and inboard fields share vertices')
 fixed=set(range(len(current['vertices'])))-oldfront
 mouth={v for i,d in enumerate(triangle_domains) if d.startswith('passage_') for v in current['triangles'][i]}
 xz=lambda i:tuple(exact.vector(current['vertices'][i])[j] for j in (0,2))
 protected={xz(i) for i in mouth&oldfront};raw,_=layout11.layout(current,reference,front,exact)
 owners=defaultdict(set)
 for row in raw:
  for p in row['xz']:owners[p].add(row['reference_triangle'])
 outer=[]
 for row in raw:
  p=row['xz'];keep=[]
  for i,q in enumerate(p):
   if q in protected or len(owners[q])>=3 or layout11.cross2(layout11.sub2(q,p[i-1]),layout11.sub2(p[(i+1)%len(p)],q))!=0:keep.append(q)
  outer.append(dict(reference_triangle=row['reference_triangle'],xz=keep))
 allpoints={p for row in outer for p in row['xz']};oldmap={xz(i):i for i in oldfront}
 if len(oldmap)!=len(oldfront):raise ValueError('Multiple outer depths at same X/Z')
 vertices=[list(v) for v in current['vertices']];point_ids={};rounding=[];patch=domain07.projected_carrier(reference)
 native_keys={}
 for q in sorted(allpoints):
  x,z=map(float,q);y,ref=domain07.rear_y(x,z,patch);position=[f32(x),f32(y-.003),f32(z)]
  if q in oldmap:index=oldmap[q];vertices[index]=position
  else:index=len(vertices);vertices.append(position)
  key=tuple(position)
  if key in native_keys:raise ValueError('Generated native coordinates collapse distinct layout vertices')
  native_keys[key]=index;point_ids[q]=index
  rounding.append(dict(vertex=index,reference_triangle=ref,ideal=[x,y-.003,z],native=position))
 # New front is one shared boundary. Return faces walk precisely this boundary.
 front_polygons=[[point_ids[p] for p in row['xz']] for row in outer]
 boundary=loops(front_polygons)
 if len(boundary)!=1:raise ValueError('Unexpected front boundary components')
 previous={b:a for a,b in zip(boundary[0],boundary[0][1:]+boundary[0][:1])}
 old_to_new={oldmap[q]:point_ids[q] for q in allpoints if q in oldmap}
 triangles=[];roles=[];old_triangle=[];requested_normals=[];uvs={k:[] for k in current['uvs']}
 def add(t,role,source=None):
  triangles.append(list(t));roles.append(role);old_triangle.append(source)
  if source is not None:
   li=current['triangle_loops'][source];requested_normals.append([current['normals'][i] for i in li])
   for layer in uvs:uvs[layer].append([current['uvs'][layer][i] for i in li])
  else:requested_normals.append(None)
 for i in sorted(back):add(current['triangles'][i],'back',i)
 for row in outer:
  ids=[point_ids[p] for p in row['xz']];coordinates={point_ids[p]:p for p in row['xz']}
  for t in ears(ids,coordinates):add(t,'front')
 returns={d:[] for d in sorted(set(triangle_domains)-{'front','back'})}
 for i,d in enumerate(triangle_domains):
  if d in returns:returns[d].append(current['triangles'][i])
 domain_normals={};domain_axes={};protected_normal_error=0.;protected_uv_error=0.
 for domain,faces in returns.items():
  source_ids=[i for i,d in enumerate(triangle_domains) if d==domain]
  targets=[current['normals'][li] for i in source_ids for li in current['triangle_loops'][i]]
  normal=unit([sum(v[j] for v in targets) for j in range(3)])
  maximum=max(angle(normal,v) for v in targets);protected_normal_error=max(protected_normal_error,maximum)
  if maximum>.025:raise ValueError('Current manufactured return field is not one bounded plane')
  axis=max(range(3),key=lambda i:abs(normal[i]));axes=[i for i in range(3) if i!=axis]
  for i in source_ids:
   for vi,li in zip(current['triangles'][i],current['triangle_loops'][i]):
    for layer in uvs:
     err=max(abs(current['uvs'][layer][li][j]-current['vertices'][vi][axes[j]]*4) for j in range(2))
     protected_uv_error=max(protected_uv_error,err)
     if err>1e-5:raise ValueError('Current return does not have the declared physical UV field')
  domain_normals[domain]=normal;domain_axes[domain]=axes
  for oldloop in loops(faces):
   if not any(i not in oldfront for i in oldloop):raise ValueError('Return lacks actual inboard boundary')
   start=next(i for i,v in enumerate(oldloop) if v not in oldfront);oldloop=oldloop[start:]+oldloop[:start]
   new=[];i=0
   while i<len(oldloop):
    v=oldloop[i]
    if v not in oldfront:new.append(v);i+=1;continue
    run=[]
    while i<len(oldloop) and oldloop[i] in oldfront:run.append(oldloop[i]);i+=1
    if run[0] not in old_to_new or run[-1] not in old_to_new:raise ValueError('Removed true manufactured corner')
    a,b=old_to_new[run[0]],old_to_new[run[-1]];new.append(a)
    while a!=b:
     if a not in previous:raise ValueError('Return is not on new outer boundary')
     a=previous[a];new.append(a)
     if len(new)>len(vertices)*2:raise ValueError('Wrong outer boundary orientation')
   if len(set(new))!=len(new):raise ValueError('Repeated return boundary vertex')
   coords={i:tuple(exact.vector(vertices[i])[j] for j in axes) for i in new}
   for t in ears(new,coords):add(t,domain)
 # A connected authored field on the new front only; manufacturing splits
 # retain separate requested normals on their actual native triangle loops.
 sums=defaultdict(lambda:[0.,0.,0.])
 for t,d in zip(triangles,roles):
  if d!='front':continue
  a,b,c=[vertices[v] for v in t];n=domain07.cross(domain07.sub(b,a),domain07.sub(c,a))
  for v in t:
   for j in range(3):sums[v][j]+=n[j]
 front_targets={v:unit(n) for v,n in sums.items()}
 # Rebuild per-triangle UV arrays in full order (copied backing first).
 for layer in uvs:uvs[layer]=[]
 for i,(t,d,source) in enumerate(zip(triangles,roles,old_triangle)):
  if source is not None:
   for layer in uvs:uvs[layer].append([current['uvs'][layer][li] for li in current['triangle_loops'][source]])
   continue
  requested_normals[i]=[front_targets[v] for v in t] if d=='front' else [domain_normals[d]]*3
  axes=[0,2] if d=='front' else domain_axes[d]
  for layer in uvs:uvs[layer].append([[vertices[v][j]*4 for j in axes] for v in t])
 used=sorted({v for t in triangles for v in t});mapping={v:i for i,v in enumerate(used)}
 if not fixed.issubset(used) or any(vertices[v]!=current['vertices'][v] for v in fixed):raise ValueError('Inboard footprint changed')
 for v in mouth&oldfront:
  if v not in used or any(vertices[v][j]!=current['vertices'][v][j] for j in (0,2)):raise ValueError('Original mouth cross-section changed')
 result=dict(name=current['name'],vertices=[vertices[v] for v in used],triangles=[[mapping[v] for v in t] for t in triangles],
  triangle_domains=roles,requested_triangle_normals=requested_normals,triangle_uvs=uvs,materials=current['materials'],
  preserved_old_vertex_map={str(v):mapping[v] for v in fixed},preserved_mouth_vertex_map={str(v):mapping[v] for v in mouth&oldfront},
  old_back_triangle_indices=[v for v in old_triangle if v is not None],ideal_front_vertices=rounding,
  original_return_normal_bound_degrees=protected_normal_error,original_return_world_uv_error=protected_uv_error,
  triangle_delta=len(triangles)-len(current['triangles']))
 domain07.validate(result)
 return result
