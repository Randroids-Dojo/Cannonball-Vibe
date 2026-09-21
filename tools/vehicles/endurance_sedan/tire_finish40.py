"""Saved predecessor and actual independent replay for current44 source tires."""
from pathlib import Path
import copy
import json

import bpy

from . import current_tire40, tire_grooves38 as grooves, source_generation as records
from .qa.tire_finish_report import (POLICY, NAMES, SELECTOR, COMPANION, SCHEMA,
    OBSERVATION_SCHEMA, HELPERS, revision_requested, require)


def _files(root):
    return {key: records.file_row(Path(__file__).with_name(name), root) for key, name in HELPERS.items()}


def _unchanged():
    from . import reserve_correspondence26
    return {obj.name: records.digest(reserve_correspondence26.raw(obj)) for obj in bpy.data.objects
            if obj.type == 'MESH' and obj.name not in NAMES}


def construct(proof, root, stage_root):
    spec = json.loads(bpy.context.scene['specification'])
    if SELECTOR not in spec['original_packaging']:
        require(COMPANION not in proof, 'Undeclared current tire companion')
        return None
    require(spec['original_packaging'][SELECTOR] == POLICY and COMPANION not in proof,
            'Unknown or already constructed current tire stage')
    require('tire_grooves38' in proof, 'Current tire needs completed historical grooves')
    before = {name: grooves.capture(bpy.data.objects[name]) for name in NAMES}
    require(before == {name: proof['tire_grooves38']['tires'][name]['after_native'] for name in NAMES},
            'Current tire must follow the genuine historical52 result')
    untouched = _unchanged()
    directory = stage_root / 'pre-tire40'
    directory.mkdir(parents=True, exist_ok=False)
    checkpoint = directory / 'source.blend'
    bpy.context.scene['tire_radial_phase'] = 'pre-construction-checkpoint'
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint), compress=True, check_existing=False)
    collection = bpy.data.collections.new('CurrentTire40Construction')
    bpy.context.scene.collection.children.link(collection)
    pending, witnesses = {}, {}
    try:
        for name in NAMES:
            pending[name], witnesses[name] = current_tire40.build_mesh(collection, bpy.data.objects[name], spec)
        # Commit only the complete four-tire recipe after all native controls.
        for name in NAMES:
            bpy.data.objects[name].data = pending[name]
        bpy.context.view_layer.update()
        after = {name: grooves.capture(bpy.data.objects[name]) for name in NAMES}
        require(untouched == _unchanged(), 'Current tire stage changed an unowned mesh')
        value = records.read_plain({'schema': SCHEMA, 'policy': POLICY, 'source_phase': 'pre-lod',
            'checkpoint': records.file_row(checkpoint, root), **_files(root),
            'legacy_construction_sha256': records.digest(proof['tire_grooves38']),
            'before': before, 'after': after, 'tires': witnesses, 'unowned_raw_before': untouched,
            'original_parent_and_materials_unchanged': True, 'source_saved': False, 'exported': False})
        revision_requested(spec, {**proof, COMPANION: value})
        verify_current(value)
        bpy.context.scene['tire_radial_phase'] = 'constructed'
        print('FRESH40 current44 tires; actual historical52 predecessor retained', flush=True)
        return value
    finally:
        bpy.data.collections.remove(collection)
        for mesh in pending.values():
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def verify_current(proof):
    require(proof['schema'] == SCHEMA and proof['policy'] == POLICY, 'Wrong current tire witness policy')
    require(set(proof['before']) == set(proof['after']) == set(proof['tires']) == set(NAMES),
            'Missing current tire complete live domain')
    results = {}
    for name in NAMES:
        obj = bpy.data.objects.get(name)
        require(obj is not None and grooves.capture(obj) == proof['after'][name],
                'Actual current44 native tire differs: ' + name)
        before, after = proof['before'][name], proof['after'][name]
        require(len(before['mesh']['faces']) == 4472 and len(after['mesh']['faces']) == 4140,
                'Wrong actual historical/current tire counts')
        for key in ('matrix_basis', 'matrix_parent_inverse', 'properties', 'material_response', 'modifiers'):
            require(before[key] == after[key], 'Current tire changed original rigid/material domain: ' + key)
        require(before['raw']['parent'] == after['raw']['parent'] == name.replace('LOD0_Tire_', 'Wheel_'),
                'Current tire rigid parent differs')
        results[name] = {'status': 'passed', 'triangles': 4140, 'actual_native_fields_exact': True}
    return results


def observe(root, construction, legacy_observation):
    root = Path(root).resolve(strict=True)
    spec = records.read(root / 'docs/vehicles/endurance-sedan/specification.json')
    if not revision_requested(spec, construction):
        return legacy_observation
    proof = construction[COMPANION]
    require(_files(root) == {key: proof[key] for key in HELPERS}, 'Current tire helper bindings differ')
    files = [proof['checkpoint'], *[proof[key] for key in HELPERS]]
    records.verify_rows(files, root)
    path = root / proof['checkpoint']['path']
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    require(bpy.context.scene.get('tire_radial_phase') == 'pre-construction-checkpoint'
            and json.loads(bpy.context.scene['specification']) == spec,
            'Current tire predecessor phase/specification differs')
    observed = {name: grooves.capture(bpy.data.objects[name]) for name in NAMES}
    require(observed == proof['before'] and _unchanged() == proof['unowned_raw_before'],
            'Actual current tire predecessor fields differ')
    collection = bpy.data.collections.new('CurrentTire40Observation')
    bpy.context.scene.collection.children.link(collection)
    legacy_replay, regenerated = {}, {}
    try:
        for name in NAMES:
            obj = bpy.data.objects[name]
            legacy_replay[name] = grooves.verify_current(obj, construction['tire_grooves38']['tires'][name])
            mesh, witness = current_tire40.build_mesh(collection, obj, spec)
            try:
                require(witness == proof['tires'][name], 'Independent current tire construction differs: ' + name)
                require(grooves.plain(grooves.capture_mesh(mesh)) == proof['after'][name]['mesh'],
                        'Independent current tire native result differs: ' + name)
                regenerated[name] = records.digest(witness)
            finally:
                bpy.data.meshes.remove(mesh)
    finally:
        bpy.data.collections.remove(collection)
    require(observed == {name: grooves.capture(bpy.data.objects[name]) for name in NAMES}
            and _unchanged() == proof['unowned_raw_before'], 'Tire observation changed original source')
    records.verify_rows(files, root)
    return records.read_plain({'schema': OBSERVATION_SCHEMA, 'policy': POLICY,
        'legacy': legacy_observation, 'checkpoint': records.file_row(path),
        'files': {key: records.file_row(root / proof[key]['path']) for key in HELPERS},
        'observed_before': observed, 'regenerated_witnesses': regenerated, 'legacy_replay': legacy_replay,
        'native': {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()},
        'source_saved': False, 'exported': False})


def prepare(inputs, spec, construction, observation, expected_digest):
    if not revision_requested(spec, construction):
        require(not isinstance(observation, dict) or observation.get('schema') != OBSERVATION_SCHEMA,
                'Undeclared current tire observation')
        return None
    require(isinstance(observation, dict) and records.digest(observation) == expected_digest,
            'Caller-held current tire observation differs')
    require(observation.get('schema') == OBSERVATION_SCHEMA and observation.get('policy') == POLICY,
            'Wrong current tire independent observation')
    require(set(observation) == {'schema', 'policy', 'legacy', 'checkpoint', 'files', 'observed_before',
            'regenerated_witnesses', 'legacy_replay', 'native', 'source_saved', 'exported'}
            and observation['native'] == {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()}
            and observation['source_saved'] is False and observation['exported'] is False,
            'Incomplete actual current tire observation')
    proof = construction[COMPANION]
    root = Path(__file__).resolve().parents[3]
    require(_files(root) == {key: proof[key] for key in HELPERS}, 'Current tire actual helper paths differ')
    records.verify_rows([proof['checkpoint'], *[proof[key] for key in HELPERS]], root)
    require(observation['files'] == {key: records.file_row(root / proof[key]['path']) for key in HELPERS},
            'Current tire observed helper files differ')
    require(observation['checkpoint'] == records.file_row(root / proof['checkpoint']['path'])
            and observation['observed_before'] == proof['before']
            and observation['regenerated_witnesses'] == {name: records.digest(proof['tires'][name]) for name in NAMES}
            and set(observation['legacy_replay']) == set(NAMES)
            and all(row['status'] == 'passed' and row['replay_exact'] for row in observation['legacy_replay'].values()),
            'Incomplete current tire independent source/replay binding')
    verify_current(proof)
    return {'proof': copy.deepcopy(proof), 'observation': copy.deepcopy(observation),
        'binding': {'schema': SCHEMA, 'policy': POLICY, 'proof_sha256': records.digest(proof),
                    'observation_sha256': expected_digest,
                    'checkpoint': copy.deepcopy(observation['checkpoint'])}}


def validate_cached(cached, binding):
    require(cached['binding'] == binding and records.digest(cached['proof']) == binding['proof_sha256']
            and records.digest(cached['observation']) == binding['observation_sha256'],
            'Changed independently verified current tire context')
    root = Path(__file__).resolve().parents[3]
    proof = cached['proof']
    require(_files(root) == {key: proof[key] for key in HELPERS}, 'Current tire helper bytes changed')
    records.verify_rows([proof['checkpoint'], *[proof[key] for key in HELPERS]], root)
    return verify_current(proof)
