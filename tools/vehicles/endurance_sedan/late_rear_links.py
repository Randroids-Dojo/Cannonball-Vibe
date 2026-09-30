"""Form the original rear arms while preserving their actual endpoint rings."""
import bpy
from . import geometry as geo
from .floor_panels import remove

def build():
    changed={};proof={'scope':'Original fictional formed rearward links around the existing exhaust; exact original endpoint rings remain, no mechanical/load simulation. Body relief and mounting seats are pending this raw fit diagnosis.'}
    for side in(-1,1):
        name='LOD0_RLowerLink_'+str(side)+'-1.65';old=bpy.data.objects[name]
        ev=old.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        try:original=[tuple(ev.matrix_world@v.co)for v in mesh.vertices]
        finally:ev.to_mesh_clear()
        assert len(original)==16
        points=[(side*.356,-1.650,.265),(side*.399,-1.601,.181),(side*.470,-1.525,.183),(side*.535,-1.460,.292)]
        new=geo.tube('PrivateFormedRearLink',points,.016,old.data.materials[0],old.users_collection[0],old.parent,sides=8)
        assert len(new.data.vertices)==32
        for i,p in enumerate(original[:8]):new.data.vertices[i].co=p
        for i,p in enumerate(original[8:]):new.data.vertices[24+i].co=p
        new.data.update();geo.project_uv(new)
        old.modifiers.clear();old.data=new.data;remove(new)
        assert [tuple(v.co)for v in old.data.vertices[:8]]==original[:8]
        assert [tuple(v.co)for v in old.data.vertices[-8:]]==original[8:]
        changed[name]=old
        proof[name]={'route_source_m':points,'nominal_radius_m':.016,'original_endpoint_rings':original,'endpoint_rings_exact':True}
    return changed,proof
