"""Current-scene structural and finish composition; caller owns save/export."""
from pathlib import Path
import gzip
import hashlib
import json
import bpy

from . import assembly_finish, late_assembly, model, surface_normals, component_finish26
from . import cooling_core, sound_grilles, acoustic_finish02, duct_vanes, duct_vane_support, paint_finish
from . import rear_surface_field, rear_cut_skin, shoulder_field02
from .floor_panels import freeze
from .qa import shoulder_checkpoint

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def inputs(root,constructor):
    special={root/'docs/vehicles/endurance-sedan/specification.json':'specification',
             constructor:'constructor',Path(shoulder_field02.__file__):'normal_module',
             Path(surface_normals.__file__):'ownership_module'}
    paths=set(special)|{p for p in (root/'tools/vehicles/endurance_sedan').rglob('*') if p.is_file() and p.suffix in ('.py','.json')}
    return [{'role':special.get(p,'constructor_component'),'path':p.relative_to(root).as_posix(),
             'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)]

def apply(collection,parent,mats,root,constructor,texture_output):
    locked=inputs(root,constructor)
    proof={'construction_inputs':locked,'fresh_scene':True,'old_source_input':None,'front_prefix29':model.BODY_FRONT_PREFIX_FIELD}
    _,proof['assembly']=assembly_finish.apply(collection,parent,mats)
    print('FRESH26 first assembly complete',flush=True)
    reference=model.BODY_REAR_REFERENCE
    carriers={name:rear_cut_skin.capture(bpy.data.objects[name],reference,surface_normals)
              for name in rear_surface_field.PROFILE['semantics']}
    proof['rear_carriers']=carriers
    from . import roof_feature26
    proof['prelate_rear34']=roof_feature26.row(bpy.data.objects['LOD0_RearBumper'])
    _,proof['late']=late_assembly.apply()
    _,proof['core']=cooling_core.apply()
    _,proof['speakers']=sound_grilles.build()
    proof['acoustic']=acoustic_finish02.apply(proof['speakers'])
    vanes,proof['vanes']=duct_vanes.build()
    supported,proof['vane_support']=duct_vane_support.apply()
    assert [o.name for o in vanes]==[o.name for o in supported]
    proof['paint']=paint_finish.apply()
    for name in ('LOD0_StructuralBody','LOD0_FrontBumper','LOD0_RearBumper'):freeze(bpy.data.objects[name])
    bumper=bpy.data.objects['LOD0_FrontBumper'];profile=shoulder_field02.EXPECTED_PROFILE
    checkpoint=shoulder_checkpoint.capture_checkpoint(bumper,model.BODY_FRONT_SHOULDER_REFERENCE,
        profile,locked,shoulder_field02,provenance={'kind':'native-construction-boundary',
                                                 'phase':'final-geometry-before-shoulder-apply'})
    witness=shoulder_field02.apply(bumper,model.BODY_FRONT_SHOULDER_REFERENCE,profile,surface_normals)
    proof['shoulder']=shoulder_checkpoint.complete_packet(checkpoint,witness)
    proof['shoulder_after_native']=shoulder_checkpoint.native_state(bumper,shoulder_field02)
    # Later arch finishing changes the bumper's sharp edges. Keep the actual
    # shoulder result available for its own unchanged historical validation.
    stage_root=texture_output.parent.parent
    shoulder_directory=stage_root/'shoulder'
    shoulder_directory.mkdir(parents=True,exist_ok=False)
    shoulder_source=shoulder_directory/'source.blend'
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(shoulder_source),compress=True,check_existing=False)
    retain(proof,shoulder_source)
    proof['rear']=[rear_cut_skin.apply(bpy.data.objects[name],carriers[name],reference,surface_normals)
                   for name in rear_surface_field.PROFILE['semantics']]
    proof['component26']=component_finish26.apply(reference,model.BODY_UPPER_SURFACE)
    from . import portable_finish26
    proof['portable26']=portable_finish26.apply(texture_output)
    from . import front_form27
    proof['front_before_native']=shoulder_checkpoint.native_state(bumper,shoulder_field02)
    stage_root=texture_output.parent.parent
    def checkpoint_stage(stage,packet,save_scene):
        directory=stage_root/stage;directory.mkdir(parents=True,exist_ok=False)
        output=directory/'source.blend'
        if save_scene:
            bpy.context.preferences.filepaths.save_version=0
            bpy.ops.wm.save_as_mainfile(filepath=str(output))
            retain(proof,output)
        target=directory/'native-stage.json.gz'
        with target.open('xb') as stream:
            with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as zipped:
                zipped.write(json.dumps({'stage':stage,'packet':packet,
                    'source_sha256':sha(output) if save_scene else None,
                    'final_source_binding':None},separators=(',',':'),allow_nan=False).encode())
        print('FRESH27 retained '+stage,flush=True)
    checkpoint_stage('pre-front',proof['front_before_native'],True)
    proof['front_form27']=front_form27.apply(checkpoint_stage,proof['shoulder'])
    assert proof['front_form27']['field_packet']['core']['initial']==proof['front_before_native']
    from .finishing34 import finish
    proof['current_surface34']=finish.apply(proof)
    from . import tire_grooves38, source_generation
    declared=json.loads(bpy.context.scene['specification'])['original_packaging'].get('tire_groove_revision38')
    if declared is not None:
        if declared!=tire_grooves38.POLICY:raise ValueError('Unknown original tire groove revision')
        directory=stage_root/'pre-grooves';directory.mkdir(parents=True,exist_ok=False)
        checkpoint=directory/'source.blend'
        bpy.context.scene['tire_groove_phase']='pre-construction-checkpoint'
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint),compress=True,check_existing=False)
        tire_proof={'schema':'source-tire-groove-construction38.v1','policy':tire_grooves38.POLICY,
            'checkpoint':source_generation.file_row(checkpoint,root),
            'constructor':source_generation.file_row(Path(tire_grooves38.__file__),root),
            'encoder':source_generation.file_row(Path(__file__).with_name('corner_encoding.py'),root),
            'tires':{name:tire_grooves38.make(bpy.data.objects[name]) for name in tire_grooves38.NAMES}}
        proof['tire_grooves38']=tire_proof
        bpy.context.scene['tire_groove_phase']='constructed'
        print('FRESH38 original recessed grooves; actual pre-groove source retained',flush=True)
    # Keep this after all current source repairs and before the final count.
    # Lower LOD generation consumes the subsequently saved actual source.
    from . import repeated_detail38
    specification=json.loads(bpy.context.scene['specification'])
    if 'repeated_detail_revision38' in specification['original_packaging']:
        if specification['original_packaging']['repeated_detail_revision38']!=repeated_detail38.POLICY:
            raise ValueError('Unknown repeated detail revision38')
        directory=stage_root/'pre-detail';directory.mkdir(parents=True,exist_ok=False)
        checkpoint=directory/'source.blend'
        bpy.context.view_layer.update()
        bpy.context.scene['repeated_detail_phase']='pre-construction-checkpoint'
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint),compress=True,check_existing=False)
        detail_proof=repeated_detail38.apply(
            specification,objects={obj.name:obj for obj in collection.all_objects},source_phase='pre-lod')
        detail_proof.update(checkpoint=source_generation.file_row(checkpoint,root),
            constructor=source_generation.file_row(Path(repeated_detail38.__file__),root),
            encoder=source_generation.file_row(Path(__file__).with_name('corner_encoding.py'),root))
        proof['repeated_detail38']=detail_proof
        bpy.context.scene['repeated_detail_phase']='constructed'
    bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get();count=0
    for obj in collection.all_objects:
        if obj.type!='MESH' or not obj.name.startswith('LOD0_') or obj.get('source_preview_only'):continue
        evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
        count+=len(mesh.loop_triangles);evaluated.to_mesh_clear()
    proof['measured_lod0_triangles']=count
    proof['lod0_ceiling']=150000;proof['roof_included']=True
    assert all(sha(root/r['path'])==r['sha256'] for r in locked)
    print('FRESH26 all geometry/fields complete; LOD0 '+str(count),flush=True)
    return proof

def retain(proof,source):
    def compressed(path,value):
        assert not path.exists()
        with path.open('xb') as stream:
            with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as zipped:
                zipped.write(json.dumps(value,separators=(',',':'),allow_nan=False).encode())
    compressed(source.with_suffix('.construction.json.gz'),proof)
    compressed(source.with_suffix('.shoulder.json.gz'),proof['shoulder'])
    source.with_suffix('.shoulder-profile.json').write_text(json.dumps(shoulder_field02.EXPECTED_PROFILE,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('FRESH26 companions retained',flush=True)
