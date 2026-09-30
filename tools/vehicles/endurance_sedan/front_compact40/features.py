"""Physical feature inventory; broad guide and closure interiors stay reducible.

Feature selection does not alter source geometry or field tolerances. Plane
labels identify the existing finite lamp/intake/vent walls, never an infinite
geometric exemption. Complete actual material fans and arch facets stay fixed.
"""
from collections import defaultdict
import numpy as np
from .arch import arch_faces
from .bvh import Tree

def derive(parts,guide,manufactured):
 out={}
 for name,row in parts.items():
  ts=row['triangles'];vs=row['vertices'];xyz=np.asarray(vs)[ts];edges=defaultdict(list);incident=defaultdict(set)
  for f,t in enumerate(ts):
   for v in t:incident[v].add(f)
   for a,b in zip(t,t[1:]+t[:1]):edges[tuple(sorted((a,b)))].append(f)
  if any(len(fs)!=2 for fs in edges.values()):raise ValueError('Open current source feature shell')
  trim={f for f,m in enumerate(row['triangle_materials'])if row['materials'][m]=='Material_Trim'}
  boundary={v for e,fs in edges.items()if len({row['triangle_materials'][f]for f in fs})>1 for v in e}
  material=trim|{f for v in boundary for f in incident[v]};radial=set(arch_faces(row));walls=set();shoulder=set();inventory=[]
  for q in manufactured[name]['manufactured']:
   d=q['domain'];n=d.get('normal');f=q['face'];purpose=None
   if d['kind']=='original_plane':
    axis=int(np.argmax(np.abs(n)));coordinate=float(np.mean([p['source_point'][axis]for p in q['corners']]))
    # The allowance only groups observed native fragments under their authored
    # nominal plane. Every selected output facet is preserved literally.
    if name=='LOD0_FrontBumper':
     catalog={0:(.4105,.8595,.5525,.6045,.8275),1:(2.06,2.07),2:(.673,.815,.3625,.5975,.347,.561)}
     if any(abs((abs(coordinate)if axis==0 else coordinate)-v)<=.0002 for v in catalog[axis]):purpose='finite lamp/intake/outboard-duct receiving wall'
    else:
     catalog={0:(.923,),1:(.758,),2:(.56,.64,.80,.88)}
     if any(abs((abs(coordinate)if axis==0 else coordinate)-v)<=.000002 for v in catalog[axis]):purpose='finite paired side-vent aperture wall'
     if axis==1 and abs(coordinate-1.8665)<=.000002:purpose='finite fender-to-bumper closure section';shoulder.add(f)
   elif name=='LOD0_FrontBumper'and d.get('owner_kind')=='new_return_wall':
    # The authored rear closure is a hidden broad plane, not the inlet rim.
    if n is not None and abs(n[1])<.9999:purpose='finite central inlet return wall'
   if purpose:
    walls.add(f);inventory.append({'face':f,'purpose':purpose,'domain':d})
    if name=='LOD0_FrontBumper':shoulder.add(f)
  seeds=walls|radial|material
  tree=Tree(xyz[sorted(seeds)]);seed_list=sorted(seeds);distances={};bevel=set();witnesses=[]
  for f in range(len(ts)):
   if f in seeds:continue
   # The existing final bevel is1.2mm. A finite1.201mm collar retains only
   # complete thin edge facets; it does not lock an arbitrary Z band or fan.
   qs=[]
   for v in ts[f]:
    if v not in distances:distances[v]=tree.nearest(vs[v])
    qs.append(distances[v])
   if max(q[0]for q in qs)<=.001201:
    bevel.add(f);witnesses.append({'face':f,'corner_distances_m':[q[0]for q in qs],'finite_receiver_faces':[seed_list[q[1]]for q in qs]})
  families={'trim_and_material_boundary_fans':sorted(material),'arch_returns':sorted(radial),'generated_bevel_returns':sorted(bevel|walls-shoulder),'shoulder_lamp':sorted(shoulder)}
  allfaces=set().union(*(set(fs)for fs in families.values()));vertices={v for f in allfaces for v in ts[f]};protected={f for f,t in enumerate(ts)if set(t)<=vertices}
  if not shoulder or not radial:raise ValueError(('Missing real current closure/arch feature',name))
  out[name]={'protected_triangle_indices':sorted(protected),'protected_vertex_indices':sorted(vertices),'feature_triangles':families,
   'oriented_membership':{k:[{'triangle':f,'indices':ts[f][:],'points':[vs[v][:]for v in ts[f]],'material_index':row['triangle_materials'][f]}for f in fs]for k,fs in families.items()},
   'derivation':'Complete actual Trim/material fans; literal64-facet arch returns; actual lamp/duct/vent return walls and fender front closure; complete finite1.201mm adjacent edge facets',
   'physical_wall_inventory':inventory,'finite_edge_collar':witnesses,'broad_guide_interiors_protected':False,
   'nonfeature_domains':'Broad fitted carrier interiors, broad hidden rear/floor/engine closure interiors, and generic old transition lineage alone are not lower-LOD feature locks; source field and native lower guards remain unchanged'}
 return out
