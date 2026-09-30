"""Native carrier-subtracted direct closeout; reports-only unsaved proposal."""
import math
from fractions import Fraction as F
import bpy
import bmesh

def height(row,x,y):
    result=[]
    for ids in row['triangles']:
        a,b,c=[row['vertices'][i] for i in ids];u=[b[k]-a[k]for k in range(3)];v=[c[k]-a[k]for k in range(3)]
        n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        if n[2]>=0 or abs(n[2])<.5*math.hypot(*n):continue
        yy=max(y,-1.268);dx,dy=x-a[0],yy-a[1]
        q=(dx*v[1]-dy*v[0])/n[2];r=(u[0]*dy-u[1]*dx)/n[2]
        if min(q,r,1-q-r)<-1e-7:continue
        result.append(a[2]+q*u[2]+r*v[2]-n[1]/n[2]*(y-yy))
    if not result:raise ValueError('Missing actual lower roof chart')
    return min(result)

def ears(points,ids):
    if len(ids)==3:return [tuple(ids)]
    n=[0.,0.,0.]
    for a,b in zip(ids,ids[1:]+ids[:1]):
        p,q=points[a],points[b]
        for j,k,l in ((0,1,2),(1,2,0),(2,0,1)):n[j]+=(p[k]-q[k])*(p[l]+q[l])
    drop=max(range(3),key=lambda k:abs(n[k]));axes=[i for i in range(3)if i!=drop]
    ps={i:tuple(F(points[i][a])for a in axes)for i in ids}
    def cross(a,b,c):
        p,q,r=ps[a],ps[b],ps[c];return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    area=sum(ps[a][0]*ps[b][1]-ps[b][0]*ps[a][1]for a,b in zip(ids,ids[1:]+ids[:1]));sign=1 if area>0 else -1
    todo=list(ids);out=[]
    while len(todo)>3:
        choices=[]
        for j,b in enumerate(todo):
            a,c=todo[j-1],todo[(j+1)%len(todo)];size=sign*cross(a,b,c)
            if size<=0:continue
            if any(all(sign*cross(x,y,p)>=0 for x,y in ((a,b),(b,c),(c,a)))for p in todo if p not in (a,b,c)):continue
            choices.append((size,j,(a,b,c)))
        if not choices:raise ValueError('No exact projected ear; new polygon needs geometry correction')
        _,j,t=max(choices);out.append(t);todo.pop(j)
    out.append(tuple(todo));return out

def make(stamp,row,station_ids,carrier_rows,material):
    side='L' if stamp.name.endswith('L') else 'R';sign=-1 if side=='L' else 1
    roof=carrier_rows['LOD0_Roof'];ys=(-1.282,-1.270,-1.258,-1.245,-1.2297)
    points=[]
    for y in ys:
        points.extend([(sign*.666,y,height(roof,sign*.666,y)+.00025),(sign*.668,y,height(roof,sign*.668,y)+.00025),
                       (sign*.668,y,1.32),(sign*.666,y,1.32)])
    faces=[]
    for j in range(len(ys)-1):
        for k in range(4):faces.append((j*4+k,j*4+(k+1)%4,(j+1)*4+(k+1)%4,(j+1)*4+k))
    faces.extend([tuple(reversed(range(4))),tuple(range(16,20))])
    data=bpy.data.meshes.new('Private_RoofWeb13_'+side);data.from_pydata(points,[],faces);data.materials.append(material);data.update()
    bm=bmesh.new()
    try:bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data)
    finally:bm.free()
    obj=bpy.data.objects.new('LOD0_RearRoofClosure_'+side,data);bpy.context.scene.collection.objects.link(obj);stages=[]
    try:
        for name,delta in [('LOD0_PillarC_'+side,(0,-.00025,0)),('LOD0_BacklightSeal',(0,-.00025,0)),('LOD0_DoorApertureSeal_R'+side,(0,0,-.00025))]:
            r=carrier_rows[name];cm=bpy.data.meshes.new('Private_Carrier13');cm.from_pydata([[p[i]+delta[i]for i in range(3)]for p in r['vertices']],[],r['triangles']);cm.update()
            co=bpy.data.objects.new('Private_Carrier13',cm);bpy.context.scene.collection.objects.link(co)
            try:
                bpy.context.view_layer.objects.active=obj;m=obj.modifiers.new('Actual finite '+name,'BOOLEAN');m.operation='DIFFERENCE';m.solver='EXACT';m.object=co;bpy.ops.object.modifier_apply(modifier=m.name)
                obj.data.calc_loop_triangles();stages.append({'name':name,'triangles':len(obj.data.loop_triangles),'delta_m':delta})
            finally:bpy.data.objects.remove(co,do_unlink=True);bpy.data.meshes.remove(cm)
        old=obj.data;points=[tuple(p.co)for p in old.vertices];polys=[list(p.vertices)for p in old.polygons]
        triangles=[tri for ids in polys for tri in ears(points,ids)]
        data=bpy.data.meshes.new('Private_RoofWeb13_Triangles_'+side);data.from_pydata(points,[],triangles);data.materials.append(material);data.update();obj.data=data
        if not old.users:bpy.data.meshes.remove(old)
        for p in data.polygons:p.use_smooth=True
        data.update();data.set_sharp_from_angle(angle=math.radians(35));data.update();uv=data.uv_layers.new(name='SurfaceMeters')
        for p in data.polygons:
            axes=sorted(range(3),key=lambda k:abs(p.normal[k]))[:2]
            for li in p.loop_indices:
                v=data.vertices[data.loops[li].vertex_index].co;uv.data[li].uv=(v[axes[0]],v[axes[1]])
        data.update()
        return obj,{'side':side,'seed_vertices_m':points,'source_polygon_indices':polys,'native_ear_triangles':triangles,
            'stages':stages,'scope':'New closed web subtracts actual C tube and backlight gasket shifted rearward 0.25mm, plus aperture seal shifted down0.25mm. Explicit exact projected ears retain all current polygon boundary indices. All fit/topology results remain pending.'}
    except Exception:
        data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if not data.users:bpy.data.meshes.remove(data)
        raise
