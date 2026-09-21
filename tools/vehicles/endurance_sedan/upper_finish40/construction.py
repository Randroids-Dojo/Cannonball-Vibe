"""Construct current upper geometry from a real saved input boundary."""
from pathlib import Path
import json

import bpy

from . import native
from .. import corner_encoding, source_generation as records
from ..qa import shoulder_checkpoint
from ..qa.upper_finish_report import COMPANION, CONSTRUCTION_SCHEMA, INPUTS, NAMES, POLICY, SELECTOR, require


def construct(proof, root, stage_root):
    packaging = json.loads(bpy.context.scene['specification'])['original_packaging']
    if SELECTOR not in packaging:
        return None
    require(records.digest(packaging[SELECTOR]) == records.digest(POLICY), 'Unknown current upper revision')
    require(COMPANION not in proof, 'Current upper already constructed')
    from .. import upper_sections40
    from ..upper_sections40 import native_sections
    design_path = Path(upper_sections40.__file__).with_name('sections.json')
    design = records.read(design_path)
    require(design['input_roles'] == list(INPUTS), 'Current upper design input roles differ')
    before = native.input_rows()
    frames = {name: native.frame(bpy.data.objects[name]) for name in INPUTS}
    materials = {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data) for name in INPUTS}
    protected = {obj.name: native.protected(obj) for obj in bpy.data.objects
                 if obj.type == 'MESH' and obj.name not in NAMES}
    directory = stage_root / 'pre-upper40'
    directory.mkdir(parents=True, exist_ok=False)
    checkpoint, requested = directory / 'source.blend', directory / 'requested.json.gz'
    base_requested = directory / 'base-requested.json.gz'
    native_intermediate = directory / 'native-intermediate.json.gz'
    bpy.context.scene['upper_finish_phase'] = 'before-current-upper'
    bpy.context.view_layer.update()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint), compress=True, check_existing=False)
    plan = records.read_plain(upper_sections40.build(before, design))
    require(set(plan['parts']) == set(NAMES) and plan['Windshield_retained_original'] is True,
            'Current upper constructor changed ownership or original pane policy')
    records.write(base_requested, plan)
    require(records.read(base_requested) == plan, 'Base upper request readback differs')
    base_native = native.install(plan['parts'])
    actual_intermediate = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
    require(actual_intermediate == base_native['after'], 'Actual upper intermediate differs from native installation')
    records.write(native_intermediate, actual_intermediate)
    require(records.read(native_intermediate) == actual_intermediate, 'Actual upper intermediate readback differs')
    plan['parts'].update(native_sections.build(actual_intermediate))
    records.write(requested, plan)
    require(records.read(requested) == plan, 'Pre-encoding upper request readback differs')
    installed = native.install(plan['parts'])
    require(protected == {obj.name: native.protected(obj) for obj in bpy.data.objects
                          if obj.type == 'MESH' and obj.name not in NAMES},
            'Current upper changed an unowned original mesh or frame')
    require(materials == {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data)
                          for name in INPUTS}, 'Current upper changed original material-node response')
    value = {
        'schema': CONSTRUCTION_SCHEMA, 'policy': POLICY, 'source_phase': 'pre-lod',
        'checkpoint': records.file_row(checkpoint, root), 'requested': records.file_row(requested, root),
        'base_requested': records.file_row(base_requested, root),
        'native_intermediate': records.file_row(native_intermediate, root),
        'constructor': records.file_row(Path(__file__), root),
        'generator': records.file_row(Path(upper_sections40.__file__), root),
        'encoder': records.file_row(Path(corner_encoding.__file__), root),
        'design': records.file_row(design_path, root),
        **{role: records.file_row(path, root) for role, path in native_sections.input_paths().items()},
        'before': before, 'before_frames': frames, 'before_material_response': materials,
        'base_native': base_native, 'native': installed, 'unowned_raw_before': protected, 'unowned_raw_unchanged': True,
        'triangles_before': sum(len(before[name]['triangles']) for name in NAMES),
        'triangles_after': sum(len(row['triangles']) for row in installed['after'].values()),
        'independent_source_acceptance': False,
    }
    bpy.context.scene['upper_finish_phase'] = 'constructed'
    print('FRESH40 current upper sections; actual original pane, checkpoint and request retained', flush=True)
    return value
