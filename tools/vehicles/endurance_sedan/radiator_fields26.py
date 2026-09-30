"""Restore current radiator fields on complete retained faces. No IO."""
import math
from types import SimpleNamespace
from mathutils import Vector,geometry

def apply(obj,original,ownership,encode):
 mesh=obj.data;mesh.calc_loop_triangles()
 assert all(abs(obj.matrix_world[i][j]-(1 if i==j else 0))<1e-12 for i in range(4) for j in range(4)), 'Expected actual static source frame'
 source_normals=[[Vector(original['normals'][i]) for i in loops] for loops in original['triangle_loops']]
 reference=(original['name'],original['vertices'],original['triangles'],source_normals)
 patch=ownership._patch(reference)
 by_face={}
 for t in mesh.loop_triangles:by_face.setdefault(t.polygon_index,[]).append(tuple(t.vertices))
 owned=[]
 for f in mesh.polygons:
  if all(ownership._covers([tuple(mesh.vertices[i].co) for i in t],patch) for t in by_face[f.index]):owned.append(f.index)
 owned=set(owned)
 targets=[]
 class MeshProxy:
  def __getattr__(self,k):return getattr(mesh,k)
  def normals_split_custom_set(self,values):targets.extend(tuple(Vector(v).normalized()) for v in values)
 metric=ownership.restore_owned(SimpleNamespace(data=MeshProxy()),[reference])
 assert len(targets)==len(mesh.loops)
 uvs={n:mesh.uv_layers.get(n) or mesh.uv_layers.new(name=n) for n in original['uvs']}
 owners=[]
 for f in mesh.polygons:
  if f.index not in owned:continue
  for index in f.loop_indices:
   p=mesh.vertices[mesh.loops[index].vertex_index].co;choices=[]
   for ti,t in enumerate(original['triangles']):
    ps=[Vector(original['vertices'][i]) for i in t]
    normal=(ps[1]-ps[0]).cross(ps[2]-ps[0]).normalized()
    if f.normal.dot(normal)<.99985:continue
    q=geometry.closest_point_on_tri(p,*ps);distance=(p-q).length
    if distance>1e-6:continue
    choices.append((distance,ti,q,ps))
   if not choices:raise ValueError(('Retained face corner lacks source UV chart',f.index,index))
   distance,ti,q,ps=min(choices,key=lambda q:q[:2]);loops=original['triangle_loops'][ti]
   for name,layer in uvs.items():
    values=[Vector((*original['uvs'][name][i],0)) for i in loops]
    value=geometry.barycentric_transform(q,*ps,*values);layer.data[index].uv=value.xy
   owners.append({'loop':index,'source_triangle':ti,'distance_m':distance})
 decoded=encode(mesh,targets)
 if not decoded['passed']:raise ValueError(('Radiator native target encoding',decoded))
 return {'complete_retained_faces':sorted(owned),'retained_corner_charts':owners,'ownership':metric,'encoding':decoded,'targets':targets,
         'claim':'Only complete original-face coverage gets current original field/UV targets; actual new pocket faces keep authored native normals. Whole outside-cut interpolation proof remains caller obligation.'}
