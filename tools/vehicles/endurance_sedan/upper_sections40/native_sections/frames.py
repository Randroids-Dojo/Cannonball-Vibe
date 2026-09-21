"""Paired scope160 construction from actual encoded native intermediate rows."""
from pathlib import Path
import json,hashlib,copy,math
NAMES=('LOD0_DoorFrame_RL','LOD0_DoorFrame_RR')
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def plainrow(r):
 if not all(k in r for k in('normals','triangle_loops','uvs')):raise ValueError('Actual encoded native input required, not an ideal target row')
 return {'name':r['name'],'vertices':r['vertices'],'triangles':r['triangles'],'triangle_materials':r['triangle_materials'],'materials':r['materials'],'normal_corner_targets':[[r['normals'][l]for l in ls]for ls in r['triangle_loops']],'uv_corner_targets':{c:[[v[l]for l in ls]for ls in r['triangle_loops']]for c,v in r['uvs'].items()}}
def build(actual_rows):
 data=json.loads(Path(__file__).with_name('frame_sections.json').read_text())
 if set(actual_rows)!=set(NAMES):raise ValueError('Exact two actual rear Frame roles required')
 parts={}
 for n in NAMES:
  old=actual_rows[n];q=data['parts'][n];part=copy.deepcopy(plainrow(old))
  if digest(part)!=q['expected_actual_input_sha256']:raise ValueError(('Actual paired Frame native fields drifted',n))
  scope=q['scope'];mov=scope['movable_vertices']
  for i,p in zip(mov,q['proposed_positions_m'],strict=True):
   if math.dist(old['vertices'][i],p)>scope['maximum_displacement_m']:raise ValueError('Frame scope160 movement exceeded')
   part['vertices'][i]=p
  changed=[f for f,t in enumerate(old['triangles'])if set(t)&set(mov)]
  if not set(changed)<=set(scope['faces']):raise ValueError('Frame complete incident scope drift')
  for f in scope['normal_field_domain']:
   a,b,c=[part['vertices'][i]for i in part['triangles'][f]];u=[b[k]-a[k]for k in range(3)];v=[c[k]-a[k]for k in range(3)];nrm=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.hypot(*nrm)
   if length==0:raise ValueError('Degenerate paired Frame facet')
   nrm=[x/length for x in nrm];part['normal_corner_targets'][f]=[list(nrm)for _ in range(3)]
  if any(part['vertices'][i]!=old['vertices'][i]for i in range(len(old['vertices']))if i not in mov):raise ValueError('Outside Frame geometry changed')
  parts[n]=part
 return parts
