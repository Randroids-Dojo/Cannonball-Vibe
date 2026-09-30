"""Build the compact original front cradle, finite mounts and passages."""
import math
import bpy,bmesh
from mathutils import Vector
from . import geometry as geo, assembly_fields as owned
from .floor_panels import freeze,remove,coat_cut_faces

def build_raw():
    objects=bpy.data.objects;body=objects['LOD0_StructuralBody'];collection=body.users_collection[0];parent=body.parent
    changed={};refs={};proof={'scope':'Original modeled front cradle, complete end-cap supports and local service passages; no load/kinematic simulation. All original front arm meshes remain unchanged.','cut_bounds':[],'supports':{}}
    def prepare(name):
        o=objects[name];owned.CLEANUP.pop(name,None);refs[name]=owned.capture(o);changed[name]=o;return o
    body=prepare(body.name);tubs={s:prepare('LOD0_InnerWheelTub_'+('FL'if s<0 else'FR'))for s in(-1,1)}
    def points(o):
        ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
        try:return[tuple(ev.matrix_world@v.co)for v in m.vertices]
        finally:ev.to_mesh_clear()
    def cut(o,tool):
        coords=points(tool);proof['cut_bounds'].append({'object':o.name,'tool':tool.name,'bounds':[[min(p[i]for p in coords)for i in range(3)],[max(p[i]for p in coords)for i in range(3)]]})
        copy=tool.copy();copy.data=tool.data.copy();collection.objects.link(copy)
        try:
            freeze(copy);copy.data.materials.clear();copy.data.materials.append(o.data.materials[0])
            for f in copy.data.polygons:f.material_index=0
            geo.boolean(o,copy);coat_cut_faces(o,o.data.materials[0])
        finally:remove(copy)
    # Retain the actual original bottom skin: service relief starts6mm above
    # the existing side-floor underside. Side trays do not span the central
    # inherited access opening, so no complete undertray closure is claimed.
    cavity=geo.box('PrivateFrontCradleServiceCavity',(0,(1.14+1.77)/2,(.1515+.277)/2),(.840,1.77-1.14,.277-.1515),None,collection,radius=0)
    cut(body,cavity);remove(cavity)
    frame=objects['LOD0_FSubframe'];route=[(-.446,1.19,.212),(-.338,1.23,.212),(-.338,1.72,.212),(.338,1.72,.212),(.338,1.23,.212),(.446,1.19,.212)]
    vertices=[]
    for i,p in enumerate(route):
        t0=Vector(route[min(i+1,len(route)-1)])-Vector(route[max(i-1,0)])
        if i in(0,len(route)-1):
            t0.normalize();miter=Vector((-t0.y,t0.x,0))
        else:
            before=(Vector(p)-Vector(route[i-1])).normalized();after=(Vector(route[i+1])-Vector(p)).normalized()
            n0=Vector((-before.y,before.x,0));n1=Vector((-after.y,after.x,0));miter=(n0+n1)/(1+before.dot(after))
        for j in range(6):
            a=math.tau*j/6;vertices.append(Vector(p)+.024*math.cos(a)*miter+Vector((0,0,.024*math.sin(a))))
    faces=[tuple(reversed(range(6))),tuple(range(30,36))]
    for i in range(5):
        for j in range(6):faces.append((6*i+j,6*i+(j+1)%6,6*(i+1)+(j+1)%6,6*(i+1)+j))
    new=geo.mesh('PrivateFormedCradle',vertices,faces,frame.data.materials[0],collection,parent)
    frame.modifiers.clear();frame.data=new.data;remove(new);changed[frame.name]=frame
    cut(body,frame)
    proof['frame']={'route_source_m':route,'section_sides':6,'section_radius_m':.024,'corner_method':'Exact planar miter sections keep the straight top mounting strips at constant width; no shading proxy.'}
    top=max(v.co.z for v in frame.data.vertices)
    for side in(-1,1):
        for cy in(1.27,1.63):
            arm=objects['LOD0_FLowerLink_'+str(side)+str(cy)];ap=points(arm);assert len(ap)==16
            centers=[sum((Vector(p)for p in ap[i:i+8]),Vector())/8 for i in(0,8)]
            assert (centers[0]-Vector((side*.356,cy,.265))).length<1e-6
            bore=geo.tube('PrivateFrontArmPassage',[centers[0],centers[1]],.021,None,collection,sides=6)
            cut(body,bore);cut(tubs[side],bore);remove(bore)
            front=[centers[0]+1.375*(Vector(p)-centers[0])for p in ap[:8]]
            foot=[Vector((side*.338+dx,cy+dy,top))for dx,dy in[(-.008,-.010),(.008,-.010),(.008,.010),(-.008,.010)]]
            bm=bmesh.new()
            for p in front+foot:bm.verts.new(p)
            bm.verts.ensure_lookup_table();bmesh.ops.convex_hull(bm,input=list(bm.verts))
            for v in list(bm.verts):
                if not v.link_faces:bm.verts.remove(v)
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));mesh=bpy.data.meshes.new('PrivateFrontCapMount');bm.to_mesh(mesh);bm.free();mesh.update()
            name='LOD0_FrontLowerLinkMount_'+str(side)+'_'+str(cy);mount=bpy.data.objects.new(name,mesh);collection.objects.link(mount);mount.parent=parent;mesh.materials.append(arm.data.materials[0]);geo.project_uv(mount);changed[name]=mount
            proof['supports'][name]={'arm':arm.name,'center_source_m':list(centers[0]),'outward_axis_source':list((centers[1]-centers[0]).normalized()),'foot_top_z_m':top,'foot_size_m':[.016,.020],'front_radius_scale':1.375}
    brace=prepare('LOD0_TunnelBrace');moved=[]
    for v in brace.data.vertices:
        if abs(v.co.z-.18950000405311584)<1e-7:moved.append(v.index);v.co.z-=.002
    assert len(moved)==4;brace.data.update();geo.project_uv(brace)
    proof['brace_crown']={'moved_vertex_ids':moved,'z_change_m':-.002,'all_other_original_vertices':'exact','flat_end_mounting_faces':'unchanged; complete face check pending'}
    proof['cut_bounds'].append({'object':brace.name,'tool':'AuthoredBraceCrownRetreat','bounds':[[-.3160001,.0984999,.1874999],[.3160001,.1815001,.1895001]],'kind':'Bounded original-profile retreat; no Boolean tool'})
    proof['raw_counts']={n:geo.evaluated_counts(o)for n,o in changed.items()}
    return changed,proof,refs,owned

def build():
    from . import boolean_surface
    from .qa.self_geometry import scan
    if bpy.context.scene.get('cb_late_front_support_applied'):raise ValueError('Apply front cradle04 exactly once')
    changed,proof,refs,owned=build_raw();proof['exact_repair']={};proof['fields']={}
    for name,ref in refs.items():
        obj=changed[name];print('repair-start',name,flush=True);owned.clean(obj)
        # Stabilize the explicit original field in independent native corner
        # spaces before the unchanged strict diagonal helper re-encodes it.
        # Preserve only plain integer ownership values across allocation.
        tags=[v.value for v in obj.data.attributes[owned.ATTRIBUTE].data]
        stable=owned.restore(obj,ref)
        if not stable['native_encoding']['passed']:raise ValueError('Pre-repair original field rejected '+name)
        assert len(tags)==len(obj.data.polygons)
        attr=obj.data.attributes.new(name=owned.ATTRIBUTE,type='INT',domain='FACE')
        for value,tag in zip(attr.data,tags):value.value=tag
        proof.setdefault('pre_repair_fields',{})[name]=stable
        proof['exact_repair'][name]=boolean_surface.repair(obj,scan,geo.evaluated_counts)
        print('restore-start',name,flush=True);proof['fields'][name]=owned.restore(obj,ref)
        if not proof['fields'][name]['native_encoding']['passed']:raise ValueError('Native original field rejected '+name)
    bpy.context.scene['cb_late_front_support_applied']=True
    return changed,proof
