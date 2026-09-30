"""Finite formed mount behind the unchanged rearward arm end-cap plane."""
import math
import bpy,bmesh
from mathutils import Vector
from . import geometry as geo

def replace_rear_mounts():
    changed={};proof={}
    for side in(-1,1):
        arm=bpy.data.objects['LOD0_RLowerLink_'+str(side)+'-1.65']
        points=[arm.matrix_world@v.co for v in arm.data.vertices]
        assert len(points)==32,'Expected the measured four-ring formed arm'
        first=points[:8];last=points[-8:]
        center=sum(first,Vector())/8;outer=sum(last,Vector())/8;axis=(outer-center).normalized()
        front=[center+1.375*(p-center)for p in first]
        vertices=list(front)
        for depth in(.018,.042):
            vertices.extend(Vector((p.x-axis.x*depth,p.y-axis.y*depth,.240))for p in front)
        bm=bmesh.new()
        for p in vertices:bm.verts.new(p)
        bm.verts.ensure_lookup_table();bmesh.ops.convex_hull(bm,input=list(bm.verts))
        for v in list(bm.verts):
            if not v.link_faces:bm.verts.remove(v)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        data=bpy.data.meshes.new('PrivateRearEndCapMountMesh');bm.to_mesh(data);bm.free();data.update()
        name='LOD0_RearLowerLinkMount_'+str(side)+'_-1.65';obj=bpy.data.objects.get(name)
        if obj is None:
            obj=bpy.data.objects.new(name,data);arm.users_collection[0].objects.link(obj);obj.parent=arm.parent
        else:obj.modifiers.clear();obj.data=data
        data.materials.append(arm.data.materials[0]);geo.project_uv(obj)
        for face in data.polygons:face.use_smooth=False
        data.update()
        changed[name]=obj
        proof[name]={'arm':arm.name,'center_source_m':list(center),'outward_axis_source':list(axis),'original_end_cap_vertices':[list(p)for p in first],'front_radius_scale':1.375,'upper_shape':'Compact convex gusset from the full end face to the fixed flat foot','foot_depths_m':[.018,.042],'foot_z_m':.240,'intent':'Closed compact fixed mount with a planar complete arm-end face and a wider foot behind the clearance passage; no bearing, bolt or load simulation claim.'}
    return changed,proof
