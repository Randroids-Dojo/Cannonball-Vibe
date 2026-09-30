"""Bind actual current panels to independently observed and regenerated inputs."""
from pathlib import Path

import bpy

from . import native
from .. import source_generation as records
from ..qa import shoulder_checkpoint
from ..qa.front_finish_report import COMPANION, NAMES, RECEIVERS, POLICY, require


def make_packet(construction, source_sha, root, observation, expected_observation_digest):
    proof = construction[COMPANION]
    require(type(observation) is dict and records.digest(observation) == expected_observation_digest,
            'Current front lacks caller-held actual legacy observation')
    require(observation.get('schema') == 'source-front-finish-observation40.v1' and
            observation.get('policy') == POLICY and observation.get('source_saved') is False and
            observation.get('native') == {'version': '5.1.2', 'build': 'ec6e62d40fa9'},
            'Wrong current front legacy observation')
    checkpoint = records.file_row(Path(root) / proof['checkpoint']['path'])
    requested_file = records.file_row(Path(root) / proof['requested']['path'])
    require(observation['checkpoint'] == checkpoint and observation['requested'] == requested_file,
            'Current front observation belongs to another checkpoint/request')
    require(observation['legacy_proof']['status'] == 'passed-current-native-chain' and
            observation['legacy_packet']['sha256'] == records.digest(observation['legacy_packet']['core']) and
            observation['legacy_packet']['core']['current_source_sha256'] == checkpoint['sha256'],
            'Current front lacks the strict completed legacy proof')
    require(observation['before'] == proof['before'] and observation['receivers'] == proof['receivers'] and
            observation['material_response'] == proof['before_material_response'] and
            observation['contract'] == proof['contract'], 'Current front actual-input observation differs')
    requested = records.read(requested_file['path'])
    require(records.digest(requested) == observation['regenerated_request_sha256'],
            'Current front request was not independently regenerated')
    current = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
    receivers = {name: native.capture(bpy.data.objects[name]) for name in RECEIVERS}
    materials = {name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data)
                 for name in (*NAMES, *RECEIVERS)}
    require(current == proof['native']['after'], 'Current front differs from constructed native rows')
    require(receivers == proof['receivers'] and materials == proof['before_material_response'],
            'Current front receiver or full material response changed')
    fields = native.verify_fields(current, requested['parts'])
    core = {
        'schema': 'current-guide-front40.v1', 'current_source_sha256': source_sha,
        'policy': POLICY, 'legacy_observation_sha256': expected_observation_digest,
        'legacy_checkpoint': checkpoint, 'legacy_packet_sha256': observation['legacy_packet']['sha256'],
        'legacy_proof': observation['legacy_proof'], 'requested_file': requested_file,
        'requested': requested, 'contract': observation['contract'],
        'current_native': current, 'receivers': receivers, 'material_response': materials,
        'complete_fields': fields,
    }
    return {'core': core, 'sha256': records.digest(core)}


def verify_packet(packet, *, expected_packet_digest):
    require(set(packet) == {'core', 'sha256'} and
            records.digest(packet['core']) == packet['sha256'] == expected_packet_digest,
            'Current guide front packet differs from caller-held digest')
    core = packet['core']
    require(core['schema'] == 'current-guide-front40.v1' and core['policy'] == POLICY,
            'Wrong current guide front policy')
    records.verify_rows([core['legacy_checkpoint'], core['requested_file']])
    require(records.read(core['requested_file']['path']) == core['requested'], 'Current front request bytes differ')
    actual = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
    require(actual == core['current_native'], 'Actual current front native fields differ')
    require({name: native.capture(bpy.data.objects[name]) for name in RECEIVERS} == core['receivers'],
            'Actual current front receivers differ')
    require({name: shoulder_checkpoint.material_fields(bpy.data.objects[name].data)
             for name in (*NAMES, *RECEIVERS)} == core['material_response'],
            'Actual current front material-node response differs')
    fields = native.verify_fields(actual, core['requested']['parts'])
    require(fields == core['complete_fields'], 'Current complete front field verification differs')
    return {
        'status': 'passed-current-three-panel-chain', 'members': list(NAMES),
        'legacy_checkpoint_sha256': core['legacy_checkpoint']['sha256'],
        'legacy_packet_sha256': core['legacy_packet_sha256'],
        'legacy_observation_sha256': core['legacy_observation_sha256'],
        'source_vertices': sum(len(row['vertices']) for row in actual.values()),
        'source_triangles': sum(len(row['triangles']) for row in actual.values()),
        'source_corners': sum(len(row['normals']) for row in actual.values()),
        'panels': fields, 'source_saves': 0, 'exports': 0, 'GPU': False,
    }
