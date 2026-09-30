"""Original open upper inlet, derived from the actual frozen front surface."""
import math
import bpy
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree
from . import triangle_projection41 as projection

OUTLINE = [(-.38,.783),(.38,.783),(.345,.708),(.08,.695),(-.08,.695),(-.345,.708)]

def apply(obj, geo, encode, *, ideal_stream=None):
    graph=bpy.context.evaluated_depsgraph_get()
    old=bpy.data.meshes.new_from_object(obj.evaluated_get(graph),preserve_all_data_layers=True,depsgraph=graph)
    obj.modifiers.clear();obj.data=old;old.calc_loop_triangles()
    assert len(old.polygons)==len(old.loop_triangles)
    vertices=[p.co.copy() for p in old.vertices]
    tris=[tuple(t.vertices) for t in old.loop_triangles]
    old_mats=[old.polygons[t.polygon_index].material_index for t in old.loop_triangles]
    old_ns=[[old.corner_normals[i].vector.copy() for i in t.loops] for t in old.loop_triangles]
    original_targets=(ideal_stream.input(len(old.loops)) if ideal_stream is not None
                      else [tuple(n.vector) for n in old.corner_normals])
    old_ideal=[[Vector(original_targets[i]) for i in t.loops] for t in old.loop_triangles]
    old_uv={u.name:[[u.data[i].uv.copy() for i in t.loops] for t in old.loop_triangles] for u in old.uv_layers}
    rear_plane=2.2300000190734863
    paint_index=list(old.materials).index(bpy.data.materials['Material_Paint'])
    rear_reference=[i for i,tri in enumerate(tris) if old_mats[i]==paint_index
                    and all(vertices[k].y==rear_plane for k in tri)
                    and (vertices[tri[1]]-vertices[tri[0]]).cross(vertices[tri[2]]-vertices[tri[0]]).normalized().y<-.99999]
    if not rear_reference or set(old_uv)!={'SurfaceMeters'}:raise ValueError('Declared rear closure/chart missing')
    old_chart_delta=0.0
    for i in rear_reference:
        authored=[Vector((vertices[k].x/.25,vertices[k].z/.25)) for k in tris[i]]
        old_chart_delta=max(old_chart_delta,*(max(abs(a[k]-b[k]) for k in (0,1)) for a,b in zip(authored,old_uv['SurfaceMeters'][i])))
        old_uv['SurfaceMeters'][i]=authored
    tree=BVHTree.FromPolygons(vertices,tris,all_triangles=True,epsilon=0)
    exact={tuple(sorted(tuple(vertices[i]) for i in tri)):j for j,tri in enumerate(tris)}
    assert len(exact)==len(tris)
    collection=obj.users_collection[0]
    n=len(OUTLINE)
    points=[(x,y,z) for y in (2.17,2.51) for x,z in OUTLINE]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    trim=bpy.data.materials['Material_Trim']
    cutter=geo.mesh('Construction_UpperInletCutter',points,faces,trim,collection)
    if trim not in list(old.materials):old.materials.append(trim)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    modifier=obj.modifiers.new('Original upper inlet','BOOLEAN')
    modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter,do_unlink=True)
    mesh=obj.data;mesh.calc_loop_triangles()
    new_vertices=[tuple(v.co) for v in mesh.vertices]
    new_tris=[tuple(t.vertices) for t in mesh.loop_triangles]
    new_mats=[mesh.polygons[t.polygon_index].material_index for t in mesh.loop_triangles]
    targets=[];charts={name:[] for name in old_uv};owners=[];worst=0.
    trim_index=list(mesh.materials).index(trim)
    for i,tri in enumerate(new_tris):
        ps=[Vector(new_vertices[k]) for k in tri]
        normal=(ps[1]-ps[0]).cross(ps[2]-ps[0]).normalized()
        original=exact.get(tuple(sorted(tuple(p) for p in ps)))
        kind='retained_exact'
        if original is None:
            center=sum(ps,Vector())/3
            _,reference_normal,near,_=tree.find_nearest(center)
            candidate=[vertices[k] for k in tris[near]]
            distances=[math.dist(p,projection.closest(p,candidate)) for p in ps]
            if normal.dot(reference_normal)>.99999 and max(distances)<=2e-7:
                original=near;kind='subdivided_interpolated';worst=max(worst,max(distances))
        if original is not None:
            ref=[vertices[k] for k in tris[original]]
            for p in ps:
                if kind=='retained_exact':
                    j=next(j for j,q in enumerate(ref) if tuple(q)==tuple(p))
                    targets.append(old_ideal[original][j])
                    for name in charts:charts[name].append(tuple(old_uv[name][original][j]))
                else:
                    targets.append(geometry.barycentric_transform(p,*ref,*old_ideal[original]).normalized())
                    for name in charts:
                        vs=[Vector((v.x,v.y,0)) for v in old_uv[name][original]]
                        value=geometry.barycentric_transform(p,*ref,*vs)
                        charts[name].append((value.x,value.y))
            owners.append({'face':i,'kind':kind,'reference_face':original})
        else:
            from . import planar_transfer39, surface_normals
            owned=planar_transfer39.transfer(ps,normal,new_mats[i],vertices,tris,old_ns,old_uv,old_mats,surface_normals)
            if owned is not None:
                ideal_owned=planar_transfer39.transfer(ps,normal,new_mats[i],vertices,tris,old_ideal,old_uv,old_mats,surface_normals)
                if ideal_owned is None:raise ValueError('Native planar owner has no complete ideal-field owner')
                if ideal_owned['proof']['reference_faces']!=owned['proof']['reference_faces']:
                    raise ValueError('Ideal/native planar ownership differs')
                targets.extend(ideal_owned['normals'])
                for name in charts:charts[name].extend(owned['charts'][name])
                owners.append({'face':i,'kind':'retained_complete_planar_patch',**owned['proof']})
                continue
            # New Boolean walls have the declared cutter boundary as their plane.
            boundary=any(max(abs((p.x-a[0])*(b[1]-a[1])-(p.z-a[1])*(b[0]-a[0])) for p in ps)<2e-7
                         for a,b in zip(OUTLINE,OUTLINE[1:]+OUTLINE[:1]))
            if not boundary:raise ValueError('Unattributed changed face '+str(i))
            targets.extend([normal]*3);new_mats[i]=trim_index
            for name in charts:
                for p in ps:charts[name].append((p.y/.25,(p.x if abs(normal.z)>.5 else p.z)/.25))
            owners.append({'face':i,'kind':'new_return_wall','reference_face':None})
    rear_final=[]
    for i,tri in enumerate(new_tris):
        ps=[Vector(new_vertices[k]) for k in tri]
        if new_mats[i]!=paint_index or not all(p.y==rear_plane for p in ps):continue
        if (ps[1]-ps[0]).cross(ps[2]-ps[0]).normalized().y>=-.99999:continue
        targets[i*3:i*3+3]=[Vector((0,-1,0))]*3
        charts['SurfaceMeters'][i*3:i*3+3]=[(p.x/.25,p.z/.25) for p in ps]
        owners[i]['authored_rear_closure_field']=True;rear_final.append(i)
    if not rear_final:raise ValueError('Declared rear closure disappeared')
    tri_mesh=bpy.data.meshes.new(obj.name+'UpperInlet')
    tri_mesh.from_pydata(new_vertices,[],new_tris)
    for mat in mesh.materials:tri_mesh.materials.append(mat)
    for face,mat in zip(tri_mesh.polygons,new_mats):face.material_index=mat;face.use_smooth=True
    for name,uvs in charts.items():tri_mesh.uv_layers.new(name=name).data.foreach_set('uv',[v for uv in uvs for v in uv])
    tri_mesh.update();obj.data=tri_mesh
    encoded=encode(tri_mesh,targets)
    if not encoded['passed']:raise ValueError('Inlet normal target native encoding failed')
    if ideal_stream is not None:ideal_stream.accept(targets,len(tri_mesh.loops))
    from . import planar_transfer39
    complete_native_fields=planar_transfer39.verify_native(owners,old_ns,[list(n.vector) for n in tri_mesh.corner_normals])
    rear_uv_error=max(abs(tri_mesh.uv_layers['SurfaceMeters'].data[i*3+j].uv[k]-charts['SurfaceMeters'][i*3+j][k])
                      for i in rear_final for j in range(3) for k in (0,1))
    if rear_uv_error>1e-5:raise ValueError('Authored rear chart native target error')
    from . import front_postcut28
    fan=front_postcut28.apply(obj,[tuple(v) for v in vertices],encode,ideal_normals=targets)
    if fan['repairs']:
        mapped=[n for row in fan['outside_faces'] for n in targets[3*row['old_face']:3*row['old_face']+3]]
        mapped.extend([(0.,-1.,0.) for _ in range(3*len(fan['repairs']))])
        if ideal_stream is not None:ideal_stream.accept(mapped,len(obj.data.loops))
    slats=[];seats=[]
    for index,z in enumerate((.726,.753),1):
        half=.345+(.38-.345)*(z-.708)/(.783-.708)
        xs=[(-half-.002)+(2*half+.004)*i/8 for i in range(9)]
        slat_vertices=[]
        for x in xs:
            hit,_,_,_=tree.ray_cast(Vector((x,3,z)),Vector((0,-1,0)),2.)
            if hit is None:raise ValueError('Slat front surface sample missed')
            front=hit.y-.012;back=front-.020
            slat_vertices.extend(((x,front,z-.00175),(x,front,z+.00175),(x,back,z+.00175),(x,back,z-.00175)))
        slat_faces=[(3,2,1,0),(32,33,34,35)]
        for i in range(8):
            for j in range(4):slat_faces.append((i*4+j,i*4+(j+1)%4,(i+1)*4+(j+1)%4,(i+1)*4+j))
        slat=geo.mesh('LOD0_AuxiliaryIntakeSlat_'+str(index),slat_vertices,slat_faces,trim,collection,obj.parent)
        slat['original_design']='Measured curved 3.5mm upper inlet slat; finite end seats require assembly verification'
        slats.append(slat)
        seats.append({'object':slat.name,'z_m':z,'nominal_end_insertion_m':.002,'front_inset_m':.012,'depth_m':.020})
    from collections import Counter
    return slats,{'outline_xz_m':OUTLINE,'slats':seats,'before_triangles':len(tris),'after_bumper_triangles':len(obj.data.polygons),'before_fan_bumper_triangles':len(new_tris),
                  'generated_rear_fan':fan,'owners_describe':'First actual inlet encoding before optional generated-fan repair',
                  'owners':owners,'owner_counts':dict(Counter(o['kind'] for o in owners)),
                  'maximum_subdivision_projection_m':worst,'subdivided_normal_targets_are_interpolated':True,
                  'normal_encoding':encoded,'complete_planar_native_fields':complete_native_fields,
                  'authored_rear_closure':{'plane_y_m':rear_plane,'source_faces':rear_reference,'final_faces':rear_final,
                      'normal_target':[0,-1,0],'UV_formula':'(X/0.25m,Z/0.25m)',
                      'maximum_old_to_authored_uv_component_delta':old_chart_delta,
                      'native_authored_uv_error':rear_uv_error,'old_field_equivalence':False},
                  'flow_or_thermal_simulation':False}
