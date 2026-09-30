"""Compose the original late assembly directly in the current Blender scene.

No report path, saved geometry payload, file import or export supplies any part.
The caller owns source saving, final LOD generation and independent verification.
"""
import time
import bpy
from . import late_first_fit, late_rear_support, late_front_support, late_body_fields

def apply():
    if bpy.context.scene.get('cb_late_assembly_applied'):raise ValueError('Apply late assembly exactly once')
    body=bpy.data.objects['LOD0_StructuralBody'];original=late_body_fields.capture(body)
    changed={};proof={'scope':'Original current-scene late assembly. Final source, visual, motion and runtime verification remain required.','order':['first_fit','rear','front'],'stages':{},'cut_bounds':[]}
    for name,module in [('first_fit',late_first_fit),('rear',late_rear_support),('front',late_front_support)]:
        start=time.perf_counter();print('late-stage-start',name,flush=True)
        outputs,details=module.build();changed.update(outputs);proof['stages'][name]=details
        proof['cut_bounds'].extend(details.get('cut_bounds',[]))
        for obj,rows in details.get('cuts',{}).items():proof['cut_bounds'].extend({'object':obj,**r}for r in rows)
        print('late-stage-end',name,time.perf_counter()-start,flush=True)
    proof['final_original_body_reset']=late_body_fields.restore(body,original,[r for r in proof['cut_bounds']if r['object']==body.name])
    bpy.context.scene['cb_late_assembly_applied']=True
    return changed,proof
