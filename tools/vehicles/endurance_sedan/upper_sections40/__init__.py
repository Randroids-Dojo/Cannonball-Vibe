"""Finite authored upper sections joined to freshly constructed native inputs.

The versioned design contains editable section vertices/connectivity and
direct authored corner targets. Existing boundary vertices and retained face
fields are read from actual inputs. No report or .blend is opened here.
The original Windshield role is intentionally absent from returned parts.
"""
import copy,hashlib,json,math
from . import windshield, rear_channel40
KEYS=('vertices','triangles','normals','triangle_loops','uvs','triangle_materials','materials')
GEOMETRY=('vertices','triangles','triangle_materials','materials')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def field_row(row):
 r=copy.deepcopy(row)
 if 'normal_corner_targets'not in r:r['normal_corner_targets']=[[r['normals'][l][:]for l in ls]for ls in r['triangle_loops']]
 if 'uv_corner_targets'not in r:r['uv_corner_targets']={c:[[values[l][:]for l in ls]for ls in r['triangle_loops']]for c,values in r['uvs'].items()}
 return r
def complete(row):
 r=copy.deepcopy(row);r['triangle_loops']=[[3*i,3*i+1,3*i+2]for i in range(len(r['triangles']))]
 r['normals']=[n[:]for ns in r['normal_corner_targets']for n in ns]
 r['uvs']={c:[v[:]for tri in values for v in tri]for c,values in r['uv_corner_targets'].items()}
 return r
def section(current,definition):
 if digest({k:current[k]for k in GEOMETRY})!=definition['expected_geometry_sha256']:raise ValueError(('Finite input section geometry/material drift',current['name']))
 old=field_row(current);vertices=[]
 for v in definition['vertices']:
  vertices.append(current['vertices'][v['source_vertex']][:]if 'source_vertex'in v else v['position_m'][:])
 row={'name':current['name'],'vertices':vertices,'triangles':copy.deepcopy(definition['triangles']),'materials':current['materials'][:],
      'triangle_materials':definition['triangle_materials'][:],'normal_corner_targets':[],'uv_corner_targets':{c:[]for c in current['uvs']}}
 retained=[];new=[];field=[]
 for f,entry in enumerate(definition['faces']):
  owner=entry.get('source_face');order=entry.get('corner_order')
  if owner is not None:
   if [vertices[v]for v in row['triangles'][f]]!=[current['vertices'][current['triangles'][owner][j]]for j in order]:raise ValueError('Finite retained oriented boundary differs')
   retained.append({'output_face':f,'source_face':owner,'corner_order':order})
  else:new.append(f)
  if 'targets'in entry:ns=entry['targets'];field.append(f)
  else:ns=[old['normal_corner_targets'][owner][j]for j in order]
  row['normal_corner_targets'].append(copy.deepcopy(ns))
  for c in row['uv_corner_targets']:
   uv=entry['uvs'][c]if'uvs'in entry else[old['uv_corner_targets'][c][owner][j]for j in order]
   row['uv_corner_targets'][c].append(copy.deepcopy(uv))
 return complete(row),{'retained_faces':retained,'new_geometry_faces':new,'new_field_faces':field,'removed_source_faces':definition['removed_source_faces'],
   'retained_input_vertex_references':sum('source_vertex'in v for v in definition['vertices']),'new_authored_vertices':sum('position_m'in v for v in definition['vertices'])}

def build(actual_rows,design,observe=None):
 if type(design)is not dict or design.get('schema')!='upper-sections40-source.v1':raise ValueError('Versioned upper source design required')
 if set(actual_rows)!=set(design['input_roles']):raise ValueError('Complete31 actual upper input roles required')
 for n,r in actual_rows.items():
  if digest({k:r[k]for k in KEYS})!=design['input_bindings'][n]:raise ValueError(('Actual upper source input changed',n))
 rows={n:field_row(r)for n,r in actual_rows.items()};proof=[];changed=set()
 for stage in design['stages']:
  current={};masks={}
  for n,d in stage['sections'].items():current[n],masks[n]=section(rows[n],d)
  if observe:observe('frozen_section_masks_'+stage['name'],copy.deepcopy(masks))
  rows.update(current);changed.update(current);proof.append({'stage':stage['name'],'parts':masks})
 planar=windshield.build(rows,actual_rows['LOD0_Windshield'])
 # The source pane, live Solidify, raw loops and no-custom-normal state stay
 # with the authoritative input object. Only Roof/header gasket are assigned.
 for n in('LOD0_Roof','LOD0_WindshieldSeal'):rows[n]=complete(planar['parts'][n]);changed.add(n)
 proof.append({'stage':'planar_original_Windshield_header','masks':planar['masks'],'shared_header_stations':planar['shared_header_stations'],'pane_assignment':False})
 rear_inputs={n:rows[n]for n in design['rear_input_roles']}
 rear=rear_channel40.build(rear_inputs,observe=observe)
 for n,r in rear['parts'].items():rows[n]=complete(r);changed.add(n)
 changed.discard('LOD0_Windshield')
 # Internal native-compatible observations serve construction only. Output
 # plans expose one authoritative corner-target stream, with no stale input
 # loop/normal/UV arrays that contradict newly authored topology.
 raw_fields={'normals','triangle_loops','uvs'}
 parts={n:{k:v for k,v in rows[n].items() if k not in raw_fields} for n in sorted(changed)}
 rear['parts']={n:{k:v for k,v in r.items() if k not in raw_fields} for n,r in rear['parts'].items()}
 return {'schema':'upper-sections40-output.v1','parts':parts,'upper_proof':proof,'rear_proof':rear,'Windshield_retained_original':True,
  'net_triangles':sum(len(r['triangles'])-len(actual_rows[n]['triangles'])for n,r in parts.items()),
  'source_saved':False,'fresh_input_only':True,'acceptance':'Finite source reconstruction; complete current combined physical/motion/visual/source gates remain pending'}
