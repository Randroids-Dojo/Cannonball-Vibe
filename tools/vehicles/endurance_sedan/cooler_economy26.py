"""Remove only redundant vertices on already authored plane intersections.

Positions retained, closed simplicial link, no flipped/tiny replacement face,
and <=0.1um endpoint-to-EVERY-incident-plane are construction guards. Caller
must still prove exact self and complete bidirectional1um surface coverage.
No scene IO, no semantic selection, no tolerance inferred from material names.
"""
from collections import defaultdict,Counter
import math
import numpy as np
import bpy

def simplify(obj,geo):
 data=obj.data;data.calc_loop_triangles()
 world=np.asarray([list(obj.matrix_world@v.co) for v in data.vertices]);local=[tuple(v.co) for v in data.vertices]
 faces=[tuple(t.vertices) for t in data.loop_triangles];flags=[bool(data.polygons[t.polygon_index].use_smooth) for t in data.loop_triangles]
 original_count=len(faces);operations=[]
 for _ in range(400):
  incident=defaultdict(list);neighbors=defaultdict(set);edge_faces=defaultdict(list)
  for i,t in enumerate(faces):
   for a in t:incident[a].append(i);neighbors[a].update(set(t)-{a})
   for a,b in zip(t,t[1:]+t[:1]):edge_faces[tuple(sorted((a,b)))].append(i)
  accepted=None
  for v,indices in sorted(incident.items()):
   if len(indices)<3:continue
   tri=world[np.asarray([faces[i] for i in indices])];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(cross,axis=1);normal=cross/length[:,None]
   for to in sorted(neighbors[v]):
    pair=edge_faces[tuple(sorted((v,to)))];opposites={p for i in pair for p in faces[i] if p not in (v,to)}
    if len(pair)!=2 or len(opposites)!=2 or (neighbors[v]&neighbors[to])!=opposites:continue
    residual=np.abs(np.einsum('ij,ij->i',world[to]-tri[:,0],normal));maximum=float(residual.max())
    if maximum>1e-7:continue
    proposed=[];newflags=[];valid=True
    for index in indices:
     old=faces[index];new=tuple(to if x==v else x for x in old)
     if len(set(new))<3:continue
     a,b,c=world[list(new)];cross_new=np.cross(b-a,c-a);a0,b0,c0=world[list(old)];cross_old=np.cross(b0-a0,c0-a0)
     if np.linalg.norm(cross_new)*.5<=1e-12 or float(cross_new@cross_old)<=0:valid=False;break
     proposed.append((index,new));newflags.append(flags[index])
    if not valid:continue
    kept=[(t,flag) for i,(t,flag) in enumerate(zip(faces,flags)) if i not in indices]+[(t,flag) for (_,t),flag in zip(proposed,newflags)]
    if any(n!=1 for n in Counter(tuple(sorted(t)) for t,_ in kept).values()):continue
    if len(kept)!=len(faces)-2:continue
    accepted=(v,to,maximum,kept,indices);break
   if accepted:break
  if not accepted:break
  v,to,maximum,kept,indices=accepted
  operations.append({'removed_vertex':v,'retained_endpoint':to,'maximum_all_incident_plane_residual_m':maximum,'old_incident_triangles':[faces[i] for i in indices],'old_index':len(operations)})
  faces=[t for t,_ in kept];flags=[f for _,f in kept]
 used=sorted({i for t in faces for i in t});index={v:i for i,v in enumerate(used)}
 out=bpy.data.meshes.new(obj.name+'ReducedPlaneVertices')
 out.from_pydata([local[i] for i in used],[],[tuple(index[i] for i in t) for t in faces])
 for material in data.materials:out.materials.append(material)
 for polygon,flag in zip(out.polygons,flags):polygon.use_smooth=flag
 out.update();obj.data=out;geo.project_uv(obj)
 return {'original_triangles':original_count,'final_triangles':len(faces),'removed_triangles':original_count-len(faces),'operations':operations,'all_output_positions_retained':True,'original_vertex_indices':used,'new_fields':'Automatic flat/smooth field on the newly authored surfaces; UV meter projection is reauthored on these parts only.'}
