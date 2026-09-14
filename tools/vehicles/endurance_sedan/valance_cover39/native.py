"""Current-input cover construction: native. Source provenance is in the private port manifest."""

import bpy

from . import mounts as mounts54

def apply(obj,plans,*,capture,encode):
    if obj.name!='LOD0_RearLowerValance' or obj.type!='MESH' or obj.modifiers:raise ValueError('Wrong original native cover')
    if [list(r) for r in obj.matrix_world]!=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]:raise ValueError('Unexpected original frame')
    if set(plans)!={obj.name,*mounts54.NAMES}:raise ValueError('Wrong complete five-part target inventory')
    if any(n in bpy.data.objects for n in mounts54.NAMES):raise ValueError('Support already exists')
    original=obj.data
    if len(original.materials)!=1 or any(p.material_index for p in original.polygons):raise ValueError('Unexpected current trim assignment')
    staged={};created=[];encoding={}
    try:
        for name,plan in plans.items():
            mesh=bpy.data.meshes.new(name+'_CommonReturnTrial');staged[name]=mesh
            mesh.from_pydata(plan['vertices'],[],plan['triangles']);mesh.update();mesh.materials.append(original.materials[0])
            if [list(p.vertices) for p in mesh.polygons]!=plan['triangles']:raise ValueError('Native ordering changed')
            for p in mesh.polygons:p.use_smooth=True;p.material_index=0
            for name_uv,rows in plan['triangle_uvs'].items():
                uv=mesh.uv_layers.new(name=name_uv)
                for p,values in zip(mesh.polygons,rows):
                    for li,value in zip(p.loop_indices,values):uv.data[li].uv=value
            targets=[n for ns in plan['requested_triangle_normals'] for n in ns]
            if len(targets)!=len(mesh.loops):raise ValueError('Incomplete requested corner field')
            encoding[name]=encode(mesh,targets)
            if not encoding[name]['passed']:raise ValueError('Native requested-target guard failed')
        obj.data=staged[obj.name]
        for name in mounts54.NAMES:
            support=bpy.data.objects.new(name,staged[name]);created.append(support)
            for c in obj.users_collection:c.objects.link(support)
            support.parent=obj.parent;support.matrix_parent_inverse=obj.matrix_parent_inverse.copy();support.matrix_world=obj.matrix_world.copy()
        bpy.context.view_layer.update()
        actual={name:capture(bpy.data.objects[name]) for name in plans}
        for name,row in actual.items():
            if row['vertices']!=plans[name]['vertices'] or row['triangles']!=plans[name]['triangles']:raise ValueError('Native installed geometry differs')
            if row['materials']!=plans[name]['materials']:raise ValueError('Native material changed')
        return dict(encoding=encoding,after=actual,source_saved=False,exported=False)
    except Exception:
        obj.data=original
        for o in created:bpy.data.objects.remove(o,do_unlink=True)
        for m in staged.values():
            if m.users==0:bpy.data.meshes.remove(m)
        raise
