"""Four-role strict current-input staging data, no scene/save/render/export API."""
from pathlib import Path
import copy,hashlib,json
PAYLOAD_SHA='6138c40a40591ed474abd44c26ad2719a676fbf21449eacd586bf57920b80ddb'
NAMES=('LOD0_RoofSideRail_L','LOD0_RoofSideRail_R','LOD0_StampedPillar_CL','LOD0_StampedPillar_CR')
def canonical(r):
 ns=r.get('normal_corner_targets')or[[r['normals'][i]for i in t]for t in r['triangle_loops']]
 uv=r.get('uv_corner_targets')or{k:[[v[i]for i in t]for t in r['triangle_loops']]for k,v in r['uvs'].items()}
 return {'name':r['name'],'vertices':r['vertices'],'triangles':r['triangles'],'materials':r['materials'],'triangle_materials':r['triangle_materials'],'normal_corner_targets':ns,'uv_corner_targets':uv}
def build(actual_rows,contract=None):
 p=Path(__file__).with_name('roof_sections.json');raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA:raise ValueError('Frozen958 payload drift')
 d=json.loads(raw)
 if set(actual_rows)!=set(NAMES):raise ValueError('Exact four current input roles required')
 for n in NAMES:
  if canonical(actual_rows[n])!=d['input_parts'][n]:raise ValueError('Actual current component field drift: '+n)
 return copy.deepcopy(d['parts'])
