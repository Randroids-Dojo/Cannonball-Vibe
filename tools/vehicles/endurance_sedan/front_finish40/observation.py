"""Read the actual completed legacy checkpoint before opening the current source."""
from pathlib import Path
import json

import bpy

from .native import capture
from .. import reserve_correspondence26, source_generation as records
from ..distance_lod import current_front
from ..distance_lod.binding import legacy_dependencies
from ..qa import shoulder_checkpoint
from ..qa.front_finish_report import COMPANION, NAMES, RECEIVERS, POLICY, revision_requested, require


def observe(root, construction):
    root = Path(root).resolve(strict=True)
    specification = records.read(root / 'docs/vehicles/endurance-sedan/specification.json')
    if not revision_requested(specification, construction, is_pipeline=True):
        return None
    from .. import front_compact40
    proof = construction[COMPANION]
    require((bpy.app.version, bpy.app.build_hash.decode()) == ((5, 1, 2), 'ec6e62d40fa9'),
            'Pinned native Blender build mismatch')
    files = [proof[key] for key in ('checkpoint', 'requested', 'constructor', 'generator', 'encoder')]
    records.verify_rows(files, root)
    source = (root / proof['checkpoint']['path']).resolve(strict=True)
    expected = records.file_row(source)
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
    require(bpy.context.scene.get('front_finish_phase') == 'completed-legacy-before-current-front',
            'Current front checkpoint is not the completed legacy phase')
    require(json.loads(bpy.context.scene['specification']) == specification,
            'Completed legacy checkpoint contains another specification')
    before = {name: capture(bpy.data.objects[name]) for name in NAMES}
    receivers = {name: capture(bpy.data.objects[name]) for name in RECEIVERS}
    materials = {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data)
                 for name in (*NAMES, *RECEIVERS)}
    require(before == proof['before'] and receivers == proof['receivers'] and
            materials == proof['before_material_response'], 'Actual completed legacy front input differs')
    protected = {obj.name: records.digest(reserve_correspondence26.raw(obj))
                 for obj in bpy.data.objects if obj.type == 'MESH' and obj.name not in NAMES}
    require(protected == proof['unowned_raw_before'], 'Actual completed legacy unowned domain differs')
    dependencies = legacy_dependencies()
    packet = current_front.make_packet(bpy.data.objects[NAMES[0]], construction,
        expected['sha256'], dependencies, shoulder_checkpoint.material_fields)
    legacy = current_front.verify_packet(bpy.data.objects[NAMES[0]], packet,
                                         dependencies, shoulder_checkpoint.material_fields)
    guide = front_compact40.extract_legacy_guide(construction)
    require(records.digest(guide) == records.digest(proof['contract']['legacy_guide']),
            'Current guide differs from independently verified legacy derivation')
    contract = {'schema': 'front-compact40-input.v1', 'receivers': receivers,
                'legacy_guide': guide, 'policy': POLICY}
    require(records.digest(contract) == records.digest(proof['contract']),
            'Current front contract differs from actual legacy inputs')
    regenerated = records.read_plain(front_compact40.build(before, contract=contract))
    requested = records.read(root / proof['requested']['path'])
    require(regenerated == requested, 'Current front request differs from independent original-input derivation')
    records.verify_rows(files, root)
    return {
        'schema': 'source-front-finish-observation40.v1', 'checkpoint': expected, 'policy': POLICY,
        'before': before, 'receivers': receivers, 'material_response': materials,
        'legacy_packet': packet, 'legacy_proof': legacy, 'contract': contract,
        'requested': records.file_row(root / proof['requested']['path']),
        'regenerated_request_sha256': records.digest(regenerated),
        'native': {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()},
        'source_saved': False,
    }
