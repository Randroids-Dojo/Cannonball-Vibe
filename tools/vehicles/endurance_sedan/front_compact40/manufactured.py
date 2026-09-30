"""Scope65 guide exterior plus complete manufactured primitive fields."""
import copy,numpy as np
from .primitives import primitive,target

def apply(actual,parts,primitive_domains,guide_proofs):
 proof={}
 for name,part in parts.items():
  old=actual[name];fitted=set(guide_proofs[name]['fitted_faces']);records=[];literal=[];transitions=[]
  for f,t in enumerate(part['triangles']):
   if f in fitted:continue
   sf=part['source_face_ids'][f];ps=[part['vertices'][v]for v in t];source_ps=[old['vertices'][v]for v in old['triangles'][sf]]
   if name=='LOD0_FrontBumper':d=primitive_domains[sf]
   else:d=primitive(source_ps);d['deformations']=[]
   if d['kind']!='generated_finite_transition':
    ns=[];origins=[]
    for p in ps:
     n,q,residual=target(np.asarray(p),d);ns.append(n.tolist());origins.append({'source_point':q.tolist(),'inverse_residual_m':residual})
    part['normal_corner_targets'][f]=ns;records.append({'face':f,'source_face':sf,'domain':d,'corners':origins})
   elif ps==source_ps:
    normals=[old['normals'][l][:]for l in old['triangle_loops'][sf]];xyz=np.asarray(ps);gn=np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]);gn/=np.linalg.norm(gn)
    if min(float(gn@np.asarray(n))for n in normals)>0:
     part['normal_corner_targets'][f]=normals;literal.append({'face':f,'source_face':sf})
    else:transitions.append(f)
   else:transitions.append(f)
  proof[name]={'manufactured':records,'literal_original_transition_fields':literal,'new_geometric_transition_fans':transitions,'nearest_old_normal_lookup':False,'exterior_guide_faces':sorted(fitted)}
 return proof
