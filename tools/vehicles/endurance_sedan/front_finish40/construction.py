"""Save the completed legacy boundary, then install current guide-derived fronts."""
from pathlib import Path
import json

import bpy

from . import native
from .. import corner_encoding, reserve_correspondence26, source_generation as records
from ..qa import shoulder_checkpoint
from ..qa.front_finish_report import COMPANION, NAMES, RECEIVERS, POLICY, SELECTOR, require


def construct(proof, root, stage_root):
    specification = json.loads(bpy.context.scene['specification'])
    packaging = specification['original_packaging']
    if SELECTOR not in packaging:
        return None
    require(records.digest(packaging[SELECTOR]) == records.digest(POLICY), 'Unknown current front revision')
    require(COMPANION not in proof, 'Current front already constructed')
    from .. import front_compact40
    before = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
    receivers = {name: native.capture(bpy.data.objects[name]) for name in RECEIVERS}
    materials = {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data)
                 for name in (*NAMES, *RECEIVERS)}
    protected = {obj.name: records.digest(reserve_correspondence26.raw(obj))
                 for obj in bpy.data.objects if obj.type == 'MESH' and obj.name not in NAMES}
    contract = {'schema': 'front-compact40-input.v1', 'receivers': receivers,
                'legacy_guide': front_compact40.extract_legacy_guide(proof), 'policy': POLICY}
    directory = stage_root / 'pre-front40'
    directory.mkdir(parents=True, exist_ok=False)
    checkpoint, requested = directory / 'source.blend', directory / 'requested.json.gz'
    bpy.context.scene['front_finish_phase'] = 'completed-legacy-before-current-front'
    bpy.context.view_layer.update()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint), compress=True, check_existing=False)
    plan = records.read_plain(front_compact40.build(before, contract=contract))
    require(set(plan['parts']) == set(NAMES), 'Current front constructor omitted a panel')
    records.write(requested, plan)
    require(records.read(requested) == plan, 'Pre-encoding front request readback differs')
    installed = native.install(plan['parts'])
    require(all(records.digest(reserve_correspondence26.raw(bpy.data.objects[name])) == value
                for name, value in protected.items()), 'Current front changed an unowned raw mesh')
    require(materials == {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data)
                          for name in (*NAMES, *RECEIVERS)}, 'Current front changed original material-node response')
    value = {
        'schema': 'source-front-finish-construction40.v1', 'policy': POLICY, 'source_phase': 'pre-lod',
        'checkpoint': records.file_row(checkpoint, root), 'requested': records.file_row(requested, root),
        'constructor': records.file_row(Path(__file__), root),
        'generator': records.file_row(Path(front_compact40.__file__), root),
        'encoder': records.file_row(Path(corner_encoding.__file__), root),
        'before': before, 'receivers': receivers, 'before_material_response': materials,
        'contract': contract, 'native': installed,
        'unowned_raw_before': protected, 'unowned_raw_unchanged': True,
        'triangles_before': sum(len(row['triangles']) for row in before.values()),
        'triangles_after': sum(len(row['triangles']) for row in installed['after'].values()),
        'independent_source_acceptance': False,
    }
    bpy.context.scene['front_finish_phase'] = 'constructed'
    print('FRESH40 current guide front; completed legacy source and pre-encoding request retained', flush=True)
    return value
