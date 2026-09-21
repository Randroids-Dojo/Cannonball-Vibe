"""Verify the reopened upper output against externally held actual-input evidence."""
from pathlib import Path

import bpy

from . import native
from .. import source_generation as records
from ..qa import shoulder_checkpoint
from ..qa.upper_finish_report import COMPANION, INPUTS, NAMES, RETAINED, OBSERVATION_SCHEMA, POLICY, require


def make_packet(construction, source_sha, root, observation, expected_observation_digest):
    proof = construction[COMPANION]
    require(type(observation) is dict and records.digest(observation) == expected_observation_digest,
            'Current upper lacks caller-held actual input observation')
    require(observation.get('schema') == OBSERVATION_SCHEMA and
            observation.get('policy') == POLICY and observation.get('source_saved') is False and
            observation.get('native') == {'version': '5.1.2', 'build': 'ec6e62d40fa9'},
            'Wrong current upper observation')
    files = {key: records.file_row(Path(root) / proof[key]['path'])
             for key in ('checkpoint', 'base_requested', 'native_intermediate', 'requested', 'design')}
    require(all(observation[key] == row for key, row in files.items()),
            'Current upper observation belongs to another input/request/design')
    require(observation['before'] == proof['before'] and observation['frames'] == proof['before_frames']
            and observation['materials'] == proof['before_material_response'],
            'Current upper actual-input observation differs')
    requested = records.read(files['requested']['path'])
    intermediate = records.read(files['native_intermediate']['path'])
    require(intermediate == proof['base_native']['after'] and
            records.digest(intermediate) == observation['regenerated_native_intermediate_sha256'],
            'Current upper native intermediate was not independently regenerated')
    require(records.digest(requested) == observation['regenerated_request_sha256'],
            'Current upper request was not independently regenerated')
    actual = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
    require(actual == proof['native']['after'], 'Current upper differs from constructed native fields')
    frames = {name: native.frame(bpy.data.objects[name]) for name in INPUTS}
    expected_frames = {name: dict(value, modifiers=[]) if name in NAMES else value
                       for name, value in proof['before_frames'].items()}
    require(frames == expected_frames, 'Current upper changed original rig frames or modifiers')
    retained = {name: native.protected(bpy.data.objects[name]) for name in RETAINED}
    require(retained == {name: proof['unowned_raw_before'][name] for name in RETAINED},
            'Current upper changed the original Windshield or aperture seals')
    materials = {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data) for name in INPUTS}
    require(materials == proof['before_material_response'], 'Current upper changed original material responses')
    core = {'schema': 'current-upper-fields40.v1', 'current_source_sha256': source_sha,
            'policy': POLICY, 'observation_sha256': expected_observation_digest, 'files': files,
            'native_intermediate_sha256': records.digest(intermediate),
            'requested': requested, 'current_native': actual, 'frames': frames,
            'retained': retained, 'materials': materials,
            'complete_fields': native.verify_fields(actual, requested['parts'])}
    return {'core': core, 'sha256': records.digest(core)}


def verify_packet(packet, *, expected_packet_digest):
    require(set(packet) == {'core', 'sha256'} and
            records.digest(packet['core']) == packet['sha256'] == expected_packet_digest,
            'Current upper packet differs from caller-held digest')
    core = packet['core']
    require(core['schema'] == 'current-upper-fields40.v1' and core['policy'] == POLICY,
            'Wrong current upper policy')
    records.verify_rows(core['files'].values())
    require(records.read(core['files']['requested']['path']) == core['requested'], 'Current upper request bytes differ')
    require(records.digest(records.read(core['files']['native_intermediate']['path']))
            == core['native_intermediate_sha256'], 'Current upper native intermediate bytes differ')
    actual = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
    require(actual == core['current_native'], 'Actual current upper native fields differ')
    require({name: native.frame(bpy.data.objects[name]) for name in INPUTS} == core['frames'],
            'Actual current upper rig frames differ')
    require({name: native.protected(bpy.data.objects[name]) for name in RETAINED} == core['retained'],
            'Actual retained original Windshield or aperture seals differ')
    require({name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data) for name in INPUTS}
            == core['materials'], 'Actual current upper material response differs')
    fields = native.verify_fields(actual, core['requested']['parts'])
    require(fields == core['complete_fields'], 'Current upper complete field verification differs')
    return {'status': 'passed-current-upper-chain', 'members': list(NAMES), 'panels': fields,
            'checkpoint_sha256': core['files']['checkpoint']['sha256'],
            'observation_sha256': core['observation_sha256'],
            'source_corners': sum(len(row['normals']) for row in actual.values()),
            'original_windshield_and_aperture_seals_retained': True,
            'source_saves': 0, 'exports': 0, 'GPU': False}
