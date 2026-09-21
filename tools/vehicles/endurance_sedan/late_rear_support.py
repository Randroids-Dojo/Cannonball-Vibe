"""Build the formed rear links, finite support mounts and body passages."""
import time,math
import bpy
from . import geometry as geo, assembly_fields as owned
from . import late_rear_links, late_rear_mounts, boolean_surface
from .floor_panels import freeze,remove,coat_cut_faces
from .qa.self_geometry import scan

def build():
    if bpy.context.scene.get('cb_late_rear_support_applied'):raise ValueError('Apply rear support14 once')
    objects=bpy.data.objects;body=objects['LOD0_StructuralBody'];collection=body.users_collection[0];parent=body.parent
    owned.CLEANUP.pop(body.name,None);refs=owned.capture(body);changed,arm_proof=late_rear_links.build();changed[body.name]=body;proof={'scope':'Original modeled formed rear arms and their mounts; exhaust/fuel routes remain unchanged. Wheel/link/spring endpoints, seat/rail/belt geometry and floor remain fixed. No kinematic/load simulation. Front link/tub/body issues remain separate.','cut_bounds':[],'support_caps':[],'routes':{}}
    def points(o):
        ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
        try:return[tuple(ev.matrix_world@v.co)for v in m.vertices]
        finally:ev.to_mesh_clear()
    def cut(o,tool):
        started=time.perf_counter();print('cut-start',o.name,tool.name,flush=True)
        pts=points(tool);proof['cut_bounds'].append({'object':o.name,'tool':tool.name,'bounds':[[min(p[i]for p in pts)for i in range(3)],[max(p[i]for p in pts)for i in range(3)]]})
        copy=tool.copy();copy.data=tool.data.copy();collection.objects.link(copy)
        try:
            freeze(copy);copy.data.materials.clear();copy.data.materials.append(o.data.materials[0])
            for face in copy.data.polygons:face.material_index=0
            geo.boolean(o,copy);coat_cut_faces(o,o.data.materials[0])
        finally:remove(copy)
        print('cut-end',o.name,tool.name,time.perf_counter()-started,flush=True)
    proof['formed_arm_recipe']=arm_proof
    for side in(-1,1):
        name='LOD0_RLowerLink_'+str(side)+'-1.65';arm=objects[name]
        route=arm_proof[name]['route_source_m'];vertices=[]
        for i,v in enumerate(arm.data.vertices):
            p=route[i//8];vertices.append(tuple(p[j]+1.5*(float(v.co[j])-p[j])for j in range(3)))
        faces=[tuple(p.vertices)for p in arm.data.polygons]
        bore=geo.mesh('PrivateLocalFormedArmRelief_'+str(side),vertices,faces,None,collection)
        cut(body,bore);remove(bore)
        proof['routes'][name]={'points_source_m':route,'nominal_arm_radius_m':.016,'cutter_radial_scale':1.5,'fixed_connections':'Actual original first/last eight-vertex endpoint rings retained byte-exact in native coordinates.'}
        for cy,ylow,yhigh in[(-1.29,-1.328,-1.2765)]:
            name='LOD0_RearLowerLinkMount_'+str(side)+'_'+str(cy)
            mount=geo.box(name,(side*.356,(ylow+yhigh)/2,(.240+.286)/2),(.052,yhigh-ylow,.046),objects['LOD0_RLowerLink_'+str(side)+str(cy)].data.materials[0],collection,parent,radius=0)
            link=objects['LOD0_RLowerLink_'+str(side)+str(cy)];cut(mount,link)
            geo.repair_triangulation(mount);mount.data.update()
            mount.data.normals_split_custom_set([tuple(p.normal)for p in mount.data.polygons for _ in p.loop_indices]);geo.project_uv(mount)
            changed[name]=mount
            proof['support_caps'].append({'mount':name,'support':body.name,'link':link.name,'bottom_z_m':.240,'finite_xy_m':[[side*.356-.026,ylow],[side*.356+.026,yhigh]],'top_z_m':.286,'interpretation':'Compact fixed formed mount with an actual shaped link-end recess and planar body seat, not a claim of rubber/bolt mechanics or structural load capacity.'})
    print('body-clean-start',flush=True);owned.clean(body)
    proof['pre_repair_counts']=geo.evaluated_counts(body)
    if any(proof['pre_repair_counts'][k]for k in('zero_corner_normals','nonfinite_corner_normals','nonunit_corner_normals')):raise ValueError('New local body relief native normals invalid')
    print('body-exact-repair-start',flush=True)
    proof['body_exact_repair']=boolean_surface.repair(body,scan,geo.evaluated_counts)
    print('body-field-restore-start',flush=True);proof['body_fields']=owned.restore(body,refs)
    if not proof['body_fields']['native_encoding']['passed']:raise ValueError('Body native field encoding failed')
    rear_mounts,rear_proof=late_rear_mounts.replace_rear_mounts()
    changed.update(rear_mounts);proof['rear_end_cap_mounts']=rear_proof
    bpy.context.scene['cb_late_rear_support_applied']=True
    return changed,proof
