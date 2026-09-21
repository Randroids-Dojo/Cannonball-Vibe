"""Complete original formed-perimeter field, with real boundary directions.

The original 18mm formed perimeter is identified before the historical front
maps and transported through their exact topology lineage. A single vector
Dirichlet field connects the current exterior guide to the analytic cap.
Manufactured plane and material splits retain their own limits.
"""
import math
from collections import defaultdict
import numpy as np
from .primitives import unit

def apply(actual,parts,primitive_domains,guide_proofs):
 name='LOD0_FrontBumper';row=parts[name];p=np.asarray(row['vertices']);ts=row['triangles'];domains=primitive_domains
 selected={f for f,s in enumerate(row['source_face_ids'])if domains[s]['kind']=='generated_finite_transition'and domains[s].get('initial_marker')==2 and domains[s].get('initial_strength')==16384}
 if not selected:raise ValueError('Missing actual formed perimeter domain')
 edges=defaultdict(list);incident=defaultdict(set);graph=defaultdict(dict)
 for f,t in enumerate(ts):
  for v in t:incident[v].add(f)
  for a,b in zip(t,t[1:]+t[:1]):edges[tuple(sorted((a,b)))].append(f)
 for f in selected:
  t=ts[f]
  for a,b in zip(t,t[1:]+t[:1]):
   d=float(np.linalg.norm(p[a]-p[b]))
   if d<=1e-12:raise ValueError('Degenerate formed perimeter edge')
   graph[a][b]=graph[b][a]=1./d
 fitted=set(guide_proofs[name]['fitted_faces']);boundary={};records=[]
 for v in sorted(graph):
  outside=incident[v]-selected
  if not outside:continue
  # Sheet-side analytic/finite guide takes the outside limit at a real
  # zero-width meeting corner; otherwise use only the continuous formed-cap limit. Actual optical/intake
  # cut planes meet at a manufactured crease and do not prescribe the smooth
  # outer skin direction. Their independent normal fields remain unchanged.
  choices=sorted(outside&fitted)or sorted(f for f in outside if domains[row['source_face_ids'][f]]['kind']=='original_formed_cap')
  if not choices:continue
  ns=[row['normal_corner_targets'][f][ts[f].index(v)]for f in choices];n=unit(np.sum(np.asarray(ns),axis=0))
  boundary[v]=n;records.append({'vertex':v,'outside_faces':choices,'target':n.tolist(),'limit':'current exterior guide'if outside&fitted else'continuous analytic original formed-cap field',
   'incident_limit_spread_degrees':max(math.degrees(math.acos(max(-1.,min(1.,float(unit(q)@n)))))for q in ns)})
 pending=set(graph);components=[];maxres=0.;result={}
 while pending:
  seed=min(pending);pending.remove(seed);todo=[seed];verts=[]
  while todo:
   v=todo.pop();verts.append(v)
   for w in graph[v]:
    if w in pending:pending.remove(w);todo.append(w)
  fixed=sorted(set(verts)&set(boundary));free=sorted(set(verts)-set(boundary))
  if not fixed:raise ValueError(('Unanchored complete formed perimeter component',verts))
  at={v:i for i,v in enumerate(free)};A=np.zeros((len(free),len(free)));b=np.zeros((len(free),3))
  for v in free:
   i=at[v]
   for w,weight in graph[v].items():
    A[i,i]+=weight
    if w in at:A[i,at[w]]-=weight
    else:b[i]+=weight*boundary[w]
  values=np.linalg.solve(A,b)if free else np.empty((0,3))
  residual=float(np.max(abs(A@values-b)))if free else 0.;maxres=max(maxres,residual)
  for v,n in zip(free,values):result[v]=unit(n)
  for v in fixed:result[v]=boundary[v]
  components.append({'vertices':sorted(verts),'fixed_vertices':fixed,'free_vertices':free,'linear_residual':residual})
 minimum=1.
 for f in sorted(selected):
  xyz=p[ts[f]];gn=unit(np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]));normals=[result[v]for v in ts[f]];hem=min(float(gn@n)for n in normals);minimum=min(minimum,hem)
  if hem<=0:raise ValueError(('Authored formed-perimeter field leaves actual triangle hemisphere',f,hem))
  row['normal_corner_targets'][f]=[n.tolist()for n in normals]
 return {'object':name,'selected_faces':sorted(selected),'original_source_faces':[row['source_face_ids'][f]for f in sorted(selected)],'boundary':records,'components':components,
  'maximum_linear_residual':maxres,'minimum_triangle_hemisphere':minimum,'cut_plane_boundary_policy':'Separate manufactured crease; no cut-wall direction imposed on continuous pre-cut formed skin','source_domain':'actual cb_fascia_cap=2 formed18mm perimeter; axis planes and independent material limits excluded',
  'geometry_UV_materials_unchanged':True,'normal_derivation':'single complete vector Dirichlet interpolation, edge inverse-length weights, normalized only after solve; no nearest old normals'}
