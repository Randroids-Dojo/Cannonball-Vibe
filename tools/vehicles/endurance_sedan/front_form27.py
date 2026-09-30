"""Apply original front recipes to current construction with caller-owned checkpoints."""
import bpy
from . import geometry as geo, corner_encoding as codec, roof_feature26 as native
from . import front_bend27, front_planar27, front_lamp27, front_inlet27
from . import front_field_capture27, shoulder_field02, front_rear_planar28
from . import front_target_transport28 as transport, arch_finish26, arch_native26
from .qa import shoulder_checkpoint
from .qa.self_geometry import scan

NATIVE_KEYS=('nonmanifold_edges','duplicate_faces','degenerate_faces','degenerate_triangles',
             'triangulated_nonmanifold_edges','triangulated_duplicate_faces',
             'nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals')


def apply(checkpoint,shoulder_packet):
    source=[o for o in bpy.data.collections['Asset'].all_objects
            if o.type=='MESH' and o.name.startswith('LOD0_') and not o.get('source_preview_only')]
    chosen=[o for o in source if max(p[1] for p in native.row(o)['vertices'])>front_bend27.START]
    original={o.name:native.row(o) for o in chosen}
    bumper=bpy.data.objects['LOD0_FrontBumper']
    recorder=front_field_capture27.Recorder(bumper,shoulder_field02.fields,
                                           shoulder_checkpoint.material_fields,codec.encode)
    arch=arch_finish26.prepare(bumper,arch_native26)
    core=shoulder_packet['core']
    ideal=transport.seed(core['checkpoint']['core']['before'],core['witness'],arch['targets'],recorder.initial)
    stream=transport.Stream(ideal)
    first=[];second=[]
    for obj in chosen:
        if obj==bumper:
            item=recorder.run('bend',lambda enc:front_bend27.apply(obj,native.row,enc,ideal_stream=stream))
            item['complete_planar_walls']=recorder.run('planar',lambda enc:front_planar27.apply(obj,enc,ideal_stream=stream))
        else:
            item=front_bend27.apply(obj,native.row,codec.encode)
        first.append(item)
    for obj in source:
        if front_lamp27.kind(obj.name):
            if obj==bumper:
                item=recorder.run('lamp',lambda enc:front_lamp27.apply(obj,native.row,enc,ideal_stream=stream))
            else:
                item=front_lamp27.apply(obj,native.row,codec.encode)
            second.append(item)
    def partial():
        return {'initial':recorder.initial,'completed_stages':recorder.stages,
                'current':recorder.state(),'final_source_binding':None,'partial':True}
    rear=recorder.run('rear_planar',lambda enc:front_rear_planar28.apply(bumper,enc,ideal_stream=stream))
    checkpoint('pre-inlet',partial(),True)
    try:
        slats,inlet=recorder.run('inlet',lambda enc:front_inlet27.apply(bumper,geo,enc,ideal_stream=stream),
                                 proof_selector=lambda value:value[1])
    except Exception:
        checkpoint('inlet-failed',partial(),False)
        raise
    field_packet=recorder.packet()
    checkpoint('front-fields',field_packet,False)
    audited={o.name:o for o in chosen+slats}
    audited.update({o.name:o for o in source if front_lamp27.kind(o.name)})
    checks=[]
    for name,obj in sorted(audited.items()):
        counts=geo.evaluated_counts(obj);exact=scan(native.row(obj),validate=True)
        item={'name':name,'native':counts,'exact_self':exact,
              'passed':not any(counts[k] for k in NATIVE_KEYS) and exact['status']=='passed'}
        checks.append(item)
        print('FRONT27 native '+name+' '+str(item['passed']),flush=True)
    proof={'original_current_rows':original,'nose_field':first,'optical_field':second,'upper_inlet':inlet,
           'rear_planar':rear,'ideal_seed':ideal,'final_ideal_targets':stream.current,
           'field_packet':field_packet,'all_changed_native_checks':checks,
           'actual_final_rows':{n:native.row(o) for n,o in audited.items()},
           'historical_source_or_mesh_input':None,'full_fit_motion_export_runtime_acceptance':None}
    if not all(c['passed'] for c in checks):
        checkpoint('front-native-failed',proof,False)
        raise ValueError('Current original front native defects: '+str([c['name'] for c in checks if not c['passed']]))
    return proof
