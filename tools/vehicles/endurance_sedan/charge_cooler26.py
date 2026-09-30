"""Unsaved original compact charge-cooler proposal. Caller owns source/IO.

All eight replacements are staged before assignment. All original receiver
objects remain exact. No hidden-mate or whole-pair exception is implemented here.
"""
import math
import bpy
from mathutils import Vector

COOLER_CENTER=(.130,1.849,.804)
COOLER_SIZE=(.230,.216,.140)
HOT=[(.111,1.274,.865),(.111,1.290,.914),(.150,1.420,.917),(.135,1.570,.884),(.065,1.680,.834),(.065,1.747,.834)]
COLD=[(.239,1.850,.790),(.300,1.850,.790),(.318,1.805,.682),(.385,1.780,.635),(.432,1.730,.665),(.434,1.6475,.716),(.425945436482630,1.628054563517370,.716),(.398,1.620,.716)]
COLD_RADII=[.028,.028]+[.022]*6
COOLANT=[(.241,1.900,.766),(.300,1.900,.766),(.335,1.870,.624),(.560,1.895,.605),(.651,1.951,.600),(.650,2.087,.600),(.600,2.107,.565),(.550,2.107,.550),(.515,2.107,.550)]
PADS=[(.177,.764,.018,.014),(.207,.754,.018,.014)]

def mirror(points,side):return [(side*x,y,z) for x,y,z in points]
def remove(obj):
 data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
 if data.users==0:bpy.data.meshes.remove(data)
def freeze(obj):
 graph=bpy.context.evaluated_depsgraph_get();data=bpy.data.meshes.new_from_object(obj.evaluated_get(graph),preserve_all_data_layers=True,depsgraph=graph)
 old=obj.data;obj.modifiers.clear();obj.data=data
 if old.users==0:bpy.data.meshes.remove(old)
def explicit_input(obj):
 # The authored tube's actual triangles, not warped original quads, are the
 # intended solid before a native Boolean. New fields remain authored here.
 old=obj.data;old.calc_loop_triangles()
 triangles=[tuple(t.vertices) for t in old.loop_triangles]
 flags=[old.polygons[t.polygon_index].use_smooth for t in old.loop_triangles]
 loops=[tuple(t.loops) for t in old.loop_triangles]
 data=bpy.data.meshes.new(obj.name+'ActualTriangleInput')
 data.from_pydata([tuple(v.co) for v in old.vertices],[],triangles)
 for mat in old.materials:data.materials.append(mat)
 for p,flag in zip(data.polygons,flags):p.use_smooth=flag
 for layer in old.uv_layers:
  output=data.uv_layers.new(name=layer.name)
  output.data.foreach_set('uv',[c for ids in loops for i in ids for c in layer.data[i].uv])
 data.update();obj.data=data
 if old.users==0:bpy.data.meshes.remove(old)

def caps_flat(obj):
 for p in obj.data.polygons:p.use_smooth=len(p.vertices)==4
 obj.data.update()
def material_only(obj,material):
 obj.data.materials.clear();obj.data.materials.append(material)
 for p in obj.data.polygons:p.material_index=0

def compact_tube(geo,name,points,radii,material,collection,sides,overrides):
 points=[Vector(p) for p in points];count=len(points)
 tangents=[(points[min(i+1,count-1)]-points[max(0,i-1)]).normalized() for i in range(count)]
 for index,direction in overrides.items():tangents[index]=Vector(direction).normalized()
 guide=Vector((0,0,1)) if abs(tangents[0].z)<.95 else Vector((0,1,0))
 normals=[tangents[0].cross(guide).normalized()]
 for previous,tangent in zip(tangents,tangents[1:]):
  n=previous.rotation_difference(tangent)@normals[-1]
  normals.append((n-tangent*n.dot(tangent)).normalized())
 vertices=[]
 for i,(p,t,n) in enumerate(zip(points,tangents,normals)):
  b=t.cross(n).normalized();r=radii[i] if isinstance(radii,(list,tuple)) else radii
  vertices.extend(p+r*(math.cos(j*math.tau/sides)*n+math.sin(j*math.tau/sides)*b) for j in range(sides))
 faces=[(i*sides+j,i*sides+(j+1)%sides,(i+1)*sides+(j+1)%sides,(i+1)*sides+j) for i in range(count-1) for j in range(sides)]
 faces.extend([tuple(reversed(range(sides))),tuple((count-1)*sides+j for j in range(sides))])
 obj=geo.mesh(name,vertices,faces,material,collection,smooth=True);caps_flat(obj)
 return obj


def apply(geo,row,repair,exact_scan,simplify,fields):
 originals={n:bpy.data.objects[n] for side in (-1,1) for n in ('LOD0_WaterToAirChargeCooler_'+str(side),'LOD0_HotChargePipe_'+str(side),'LOD0_ColdChargePipe_'+str(side),'LOD0_ChargeCoolantHose_'+str(side))}
 originals['LOD0_ChargeCoolingRadiator']=bpy.data.objects['LOD0_ChargeCoolingRadiator']
 before={n:row(o) for n,o in originals.items()};staged={};made=[];proof=[]
 try:
  for side in (-1,1):
   name='LOD0_WaterToAirChargeCooler_'+str(side);old=originals[name];col=old.users_collection[0];mat=old.data.materials[0]
   body=geo.box('Private_CoolerBody',mirror([COOLER_CENTER],side)[0],COOLER_SIZE,mat,col,radius=.012)
   made.append(body);body.modifiers[0].segments=1;freeze(body);staged[name]=body;uncut_body=row(body)
   hot_name='LOD0_HotChargePipe_'+str(side);hot=compact_tube(geo,'Private_CoolerHot',mirror(HOT,side),.030,originals[hot_name].data.materials[0],col,10,{4:(0,1,0),5:(0,1,0)})
   made.append(hot);caps_flat(hot);explicit_input(hot);untrimmed_hot=row(hot)
   # Trim the actual new pipe against the exact unchanged turbo outer mesh.
   receiver='LOD0_HotVTurbo_'+str(side);old_receiver=row(bpy.data.objects[receiver])
   cut=geo.mesh('Private_ExactTurboReceiver',old_receiver['vertices'],old_receiver['triangles'],None,col)
   made.append(cut);geo.boolean(hot,cut);remove(cut);made.remove(cut)
   material_only(hot,originals[hot_name].data.materials[0])
   hot.data.normals_split_custom_set([tuple(n.vector) for n in hot.data.corner_normals])
   hot_repair=repair(hot,exact_scan,geo.evaluated_counts)
   staged[hot_name]=hot
   cold_name='LOD0_ColdChargePipe_'+str(side);cold=compact_tube(geo,'Private_CoolerCold',mirror(COLD,side),COLD_RADII,originals[cold_name].data.materials[0],col,10,{0:(side,0,0),1:(side,0,0),5:(0,-1,0),7:(-side,0,0)})
   made.append(cold);caps_flat(cold);explicit_input(cold)
   plenum_name='LOD0_IntakePlenum_'+str(side);plenum=row(bpy.data.objects[plenum_name])
   cutter=geo.mesh('Private_ExactPlenumReceiver',plenum['vertices'],plenum['triangles'],None,col)
   made.append(cutter);geo.boolean(cold,cutter);remove(cutter);made.remove(cutter)
   material_only(cold,originals[cold_name].data.materials[0]);staged[cold_name]=cold
   water_name='LOD0_ChargeCoolantHose_'+str(side)
   water=compact_tube(geo,'Private_CoolerCoolant',mirror(COOLANT,side),.012,originals[water_name].data.materials[0],col,8,{0:(side,0,0),1:(side,0,0),7:(-side,0,0),8:(-side,0,0)})
   made.append(water);staged[water_name]=water
   # Straight first/last port spans keep each fitted receiving pocket planar
   # longitudinally; the generated actual evaluated pipe is the cutter.
   for pipe_name in (hot_name,cold_name,water_name):
    actual=row(staged[pipe_name]);cutter=geo.mesh('Private_ActualCoolerPort',actual['vertices'],actual['triangles'],None,col)
    made.append(cutter);geo.boolean(body,cutter);remove(cutter);made.remove(cutter)
   material_only(body,mat)
   bank=row(bpy.data.objects['LOD0_V8CylinderBank_'+str(side)]);bank_front=max(p[1] for p in bank['vertices']);back=min(p[1] for p in row(body)['vertices'])
   assert abs(bank_front-1.7365000247955322)<1e-7 and abs(back-1.741)<1e-7
   for i,(x,z,w,h) in enumerate(PADS):
    pname='LOD0_ChargeCoolerMount_'+str(side)+'_'+str(i);assert pname not in bpy.data.objects
    pad=geo.box('Private_CoolerMount',(side*x,(bank_front+back)/2,z),(w,back-bank_front,h),mat,col,radius=0)
    made.append(pad);staged[pname]=pad
   proof.append({'side':side,'cooler_center_source_m':mirror([COOLER_CENTER],side)[0],'cooler_size_m':COOLER_SIZE,'hot_points_m':mirror(HOT,side),'cold_points_m':mirror(COLD,side),'cold_radii_m':COLD_RADII,'coolant_points_m':mirror(COOLANT,side),'cross_section_sides':{'hot':10,'cold':10,'coolant':8},'bank_front_y_m':bank_front,'cooler_back_y_m':back,'turbo_receiver_unchanged':row(bpy.data.objects[receiver])==old_receiver,'new_uncut_cooler':uncut_body,'untrimmed_hot':untrimmed_hot,'hot_attributed_repair':hot_repair,'plenum_receiver_unchanged':row(bpy.data.objects[plenum_name])==plenum})
  # Actual current radiator receives both completely new coolant tail surfaces.
  rn='LOD0_ChargeCoolingRadiator';receiver=originals[rn]
  rad=receiver.copy();rad.data=receiver.data.copy();rad.parent=None;rad.matrix_world=receiver.matrix_world.copy()
  receiver.users_collection[0].objects.link(rad);made.append(rad);freeze(rad)
  assert row(rad)['vertices']==before[rn]['vertices'] and row(rad)['triangles']==before[rn]['triangles']
  for side in (-1,1):
   actual=row(staged['LOD0_ChargeCoolantHose_'+str(side)])
   cutter=geo.mesh('Private_ActualRadiatorPort',actual['vertices'],actual['triangles'],None,receiver.users_collection[0])
   made.append(cutter);geo.boolean(rad,cutter);remove(cutter);made.remove(cutter)
  material_only(rad,receiver.data.materials[0]);staged[rn]=rad
  # Whole newly authored bodies/hoses may lose only redundant native coplanar
  # vertices. The existing radiator is excluded from that authored field scope.
  for name,obj in staged.items():
   if True:
    metric=simplify(obj,geo)
    for p in proof:
     if name.endswith('_'+str(p['side'])):p.setdefault('redundant_planar_vertices',{})[name]=metric
  proof[0]['radiator_current_original']=before[rn]
  proof[0]['radiator_retained_fields']=fields(rad,before[rn])
  # All geometry prepared; assign the staged data only now. Native caller must
  # validate complete surfaces before recommending this unaccepted candidate.
  result=[]
  for name,obj in list(staged.items()):
   if name in originals:
    dst=originals[name];inverse=dst.matrix_world.inverted()
    for v in obj.data.vertices:v.co=inverse@(obj.matrix_world@v.co)
    dst.modifiers.clear();dst.data=obj.data
    bpy.data.objects.remove(obj,do_unlink=True);made.remove(obj);result.append(dst)
   else:
    template=originals['LOD0_WaterToAirChargeCooler_'+name.split('_')[-2]]
    obj.name=name;obj.parent=template.parent;obj.matrix_world=template.matrix_world.copy()
    result.append(obj);made.remove(obj)
  bpy.context.view_layer.update()
  return result,proof,before
 except:
  for obj in list(made):
   if obj.name in bpy.data.objects:remove(obj)
  raise
