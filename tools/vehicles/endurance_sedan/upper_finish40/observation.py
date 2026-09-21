"""Reopen and independently regenerate upper targets from actual native inputs."""
from pathlib import Path
import json

import bpy

from . import native
from .. import source_generation as records
from ..qa import shoulder_checkpoint
from ..qa.upper_finish_report import COMPANION, FILE_ROLES, INPUTS, NAMES, OBSERVATION_SCHEMA, POLICY, revision_requested, require


def observe(root, construction):
    root = Path(root).resolve(strict=True)
    specification = records.read(root / 'docs/vehicles/endurance-sedan/specification.json')
    if not revision_requested(specification, construction, is_pipeline=True):
        return None
    from .. import upper_sections40
    from ..upper_sections40 import native_sections
    proof = construction[COMPANION]
    require((bpy.app.version, bpy.app.build_hash.decode()) == ((5, 1, 2), 'ec6e62d40fa9'),
            'Pinned native Blender build mismatch')
    files = [proof[key] for key in FILE_ROLES]
    records.verify_rows(files, root)
    source = root / proof['checkpoint']['path']
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
    require(bpy.context.scene.get('upper_finish_phase') == 'before-current-upper' and
            json.loads(bpy.context.scene['specification']) == specification,
            'Current upper checkpoint phase/specification differs')
    before = native.input_rows()
    frames = {name: native.frame(bpy.data.objects[name]) for name in INPUTS}
    materials = {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data) for name in INPUTS}
    require(before == proof['before'] and frames == proof['before_frames'] and
            materials == proof['before_material_response'], 'Actual upper native input differs')
    protected = {obj.name: native.protected(obj) for obj in bpy.data.objects
                 if obj.type == 'MESH' and obj.name not in NAMES}
    require(protected == proof['unowned_raw_before'], 'Actual upper unowned input domain differs')
    design_path = (root / proof['design']['path']).resolve(strict=True)
    require(design_path == Path(upper_sections40.__file__).with_name('sections.json').resolve(),
            'Current upper uses another authored design')
    for role, path in native_sections.input_paths().items():
        require((root / proof[role]['path']).resolve(strict=True) == path.resolve(strict=True),
                'Current upper uses another native section input: ' + role)
    regenerated = records.read_plain(upper_sections40.build(before, records.read(design_path)))
    base_requested = root / proof['base_requested']['path']
    require(regenerated == records.read(base_requested), 'Base upper request differs from actual input regeneration')
    base_native = native.install(regenerated['parts'])
    actual_intermediate = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
    intermediate = root / proof['native_intermediate']['path']
    require(base_native == proof['base_native'] and actual_intermediate == base_native['after']
            and actual_intermediate == records.read(intermediate), 'Regenerated actual native upper intermediate differs')
    require(protected == {obj.name: native.protected(obj) for obj in bpy.data.objects
                          if obj.type == 'MESH' and obj.name not in NAMES},
            'Independent native upper observation changed unowned input')
    regenerated['parts'].update(native_sections.build(actual_intermediate))
    requested = root / proof['requested']['path']
    require(regenerated == records.read(requested), 'Current upper request differs from actual input regeneration')
    records.verify_rows(files, root)
    return {'schema': OBSERVATION_SCHEMA, 'checkpoint': records.file_row(source),
            'requested': records.file_row(requested), 'design': records.file_row(design_path),
            'base_requested': records.file_row(base_requested), 'native_intermediate': records.file_row(intermediate),
            'regenerated_native_intermediate_sha256': records.digest(actual_intermediate),
            'policy': POLICY, 'before': before, 'frames': frames, 'materials': materials,
            'regenerated_request_sha256': records.digest(regenerated),
            'native': {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()},
            'source_saved': False}
