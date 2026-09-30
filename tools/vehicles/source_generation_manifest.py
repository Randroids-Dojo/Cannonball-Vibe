"""Read-only current-project sedan generation ancestry for the asset manifest.

The existing source binding loader remains authority for native generation
records. This bridge never opens Blender, rewrites historical paths, or grants
source geometry, runtime or human acceptance.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys

sys.dont_write_bytecode = True
from endurance_sedan.qa import gate  # noqa: E402

SOURCE = 'data/assets/vehicles/sources/endurance-sedan.blend'
BINDING = 'data/assets/vehicles/sources/endurance-sedan.source-binding.json'
SPECIFICATION = 'docs/vehicles/endurance-sedan/specification.json'
BUILDER = 'tools/vehicles/build_endurance_sedan.py'
PHASES = (('fresh-construction', 'tools/vehicles/create_endurance_sedan.py'),
          ('finalize-and-reopen', 'tools/vehicles/endurance_sedan/finalize_source.py'))


def file_row(path, root):
    path = Path(path).resolve(strict=True)
    gate.require(path.is_file() and path.is_relative_to(root), 'Manifest input leaves current project')
    logical = path.relative_to(root).as_posix()
    gate.relative_path(logical)
    return {'path': logical, 'sha256': gate.sha(path), 'bytes': path.stat().st_size}


def current_path(root, logical):
    gate.relative_path(logical)
    path = (root / logical).resolve(strict=True)
    gate.require(path.is_relative_to(root), 'Manifest path escapes current project')
    return path


def historical_relative(path, project):
    """Interpret recorded paths without resolving them on the current host."""
    gate.require(type(path) is str and type(project) is str, 'Historical path must be a string')
    path_type = PureWindowsPath if PureWindowsPath(project).drive else PurePosixPath
    parent, value = path_type(project), path_type(path)
    gate.require(parent.is_absolute() and value.is_absolute() and '..' not in value.parts,
                 'Invalid historical absolute path')
    try:
        logical = value.relative_to(parent).as_posix()
    except ValueError as error:
        raise ValueError('Historical command path escapes recorded candidate project') from error
    gate.relative_path(logical)
    return logical


def argument(argv, name):
    gate.require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv), 'Missing/duplicate native argument: ' + name)
    return argv[argv.index(name) + 1]


def validate_phase_command(command, expected_outputs, destinations, recorded_root):
    """Bind a phase's argv and complete unique output set to its declared roles."""
    observed = command.get('outputs')
    gate.require(type(observed) is list and all(type(row) is dict for row in observed),
                 'Missing native phase output inventory')
    names = [row.get('path') for row in observed]
    gate.require(all(type(name) is str for name in names) and len(names) == len(set(names))
                 and sorted(observed, key=lambda row: row['path'])
                 == sorted(expected_outputs, key=lambda row: row['path']),
                 'Native phase output roles or complete inventory differ')
    for option, row in destinations.items():
        gate.require(historical_relative(argument(command['argv'], option), recorded_root) == row['path'],
                     'Native phase destination differs from output role: ' + option)


def phase_output_contract(root, generation, historical, portable, pre_lod):
    by_role = {row['role']: {key: value for key, value in row.items() if key != 'role'}
               for row in generation['source_outputs']}
    gate.require(len(by_role) == len(generation['source_outputs']), 'Duplicate generation output role')
    base = PurePosixPath(pre_lod['path'])
    construction = file_row(current_path(root, base.with_suffix('.construction.json.gz').as_posix()), root)
    gate.require(construction['sha256'] == portable['roles']['construction']['sha256']
                 and construction['bytes'] == portable['roles']['construction']['bytes'],
                 'Fresh construction output differs from final companion')
    fresh = [pre_lod, construction, by_role['pre_front_source'],
             historical['source'], historical['construction_packet'], historical['shoulder_profile']]
    packaging = gate.strict_json(root / SPECIFICATION)['original_packaging']
    checkpoints = []
    if packaging.get('tire_groove_revision38') is not None:
        checkpoints.append('pre-grooves/source.blend')
    if 'tire_radial_revision40' in packaging:
        checkpoints.append('pre-tire40/source.blend')
    if 'repeated_detail_revision38' in packaging:
        checkpoints.append('pre-detail/source.blend')
    if 'valance_cover_revision39' in packaging:
        checkpoints += ['pre-cover/source.blend', 'pre-cover/requested.json.gz']
    if 'front_finish_revision40' in packaging:
        checkpoints += ['pre-front40/source.blend', 'pre-front40/requested.json.gz']
    if 'upper_finish_revision40' in packaging:
        checkpoints += ['pre-upper40/source.blend', 'pre-upper40/base-requested.json.gz',
                        'pre-upper40/native-intermediate.json.gz', 'pre-upper40/requested.json.gz']
    fresh += [file_row(current_path(root, (base.parent / name).as_posix()), root) for name in checkpoints]
    final = [portable['roles']['source'], by_role['lower_bundle'], by_role['native_finalization']]
    return [(fresh, {'--output': pre_lod}),
            (final, dict(zip(('--output', '--bundle', '--report'), final, strict=True)))]


def complete_inputs(root, generation, portable):
    """Verify actual full .py/.json inventories, including JSON LOD profiles."""
    wanted = {path.relative_to(root).as_posix() for path in (root / 'tools/vehicles').rglob('*')
              if path.is_file() and path.suffix in ('.py', '.json')}
    wanted.update((SPECIFICATION, 'docs/vehicles/endurance-sedan/blockout-integration.json'))
    rows = generation['input_artifacts']
    actual = [row['path'] for row in rows]
    gate.require(len(actual) == len(set(actual)) and set(actual) == wanted,
                 'Complete current generation .py/.json/specification input inventory differs')
    package = {path.relative_to(root).as_posix() for path in (root / 'tools/vehicles/endurance_sedan').rglob('*')
               if path.is_file() and path.suffix in ('.py', '.json')}
    lower = [row['path'] for row in portable['input_files']]
    gate.require(len(lower) == len(set(lower)) and set(lower) == package,
                 'Complete lower package .py/.json inventory differs')
    for row in [*rows, *portable['input_files']]:
        gate.artifact(row, root)


def verify_commands(root, generation, historical, generation_directory, portable, pre_lod, finalization):
    outputs, phases = [], []
    recorded_root = generation['candidate_project']
    output_contract = phase_output_contract(root, generation, historical, portable, pre_lod)
    for command, (label, script), (expected_outputs, destinations) in zip(
            generation['commands'], PHASES, output_contract, strict=True):
        gate.require(command['label'] == label and command['cwd'] == recorded_root, 'Native phase/cwd differs')
        gate.require(historical_relative(argument(command['argv'], '--python'), recorded_root) == script,
                     'Native phase uses another source script')
        validate_phase_command(command, expected_outputs, destinations, recorded_root)
        path = generation_directory / 'commands' / (label + '.json')
        gate.require(gate.strict_json(path) == command, 'Retained native command differs from generation record')
        outputs.append(file_row(path, root))
        phases.append({'label': label, 'script': file_row(root / script, root),
                       'command': outputs[-1], 'inputs': list(generation['input_artifacts'])})
    old_record = gate.strict_json(root / historical['generation_record']['path'])
    gate.require(old_record['native_command_record'] == outputs[0]
                 and old_record['argv'] == generation['commands'][0]['argv']
                 and old_record['logs'] == generation['commands'][0]['logs'],
                 'Historical shoulder command ancestry differs from actual fresh phase')
    native_command = generation['commands'][1]
    lock_logical = historical_relative(argument(native_command['argv'], '--input-lock'), recorded_root)
    native_lock_path = current_path(root, lock_logical)
    native_lock = gate.strict_json(native_lock_path)
    gate.require(gate.sha(native_lock_path) == finalization['input_lock_sha256']
                 and gate.digest(native_lock) == finalization['expected_lock_digest']
                 == argument(native_command['argv'], '--expected-lock-digest'),
                 'Actual pre-LOD input lock differs from finalized native invocation')

    def normalized(row):
        return {**row, 'path': historical_relative(row['path'], recorded_root)}

    expected = {**portable, 'roles': {**portable['roles'], 'source': pre_lod}}
    observed = {**native_lock, 'roles': {name: normalized(row) for name, row in native_lock['roles'].items()},
                'input_files': [normalized(row) for row in native_lock['input_files']],
                'generation_inputs': [normalized(row) for row in native_lock['generation_inputs']]}
    gate.require(observed == expected, 'Native pre-LOD and portable final input locks differ outside final source role')
    phases[1]['inputs'] += [pre_lod, portable['roles']['construction'], file_row(native_lock_path, root)]
    return phases, [*outputs, file_row(native_lock_path, root)]


def load_ancestry(root, *, source=SOURCE, binding=BINDING, specification=SPECIFICATION):
    root = Path(root).resolve(strict=True)
    source_path, binding_path = current_path(root, source), current_path(root, binding)
    spec_path = current_path(root, specification)
    lock = gate.load_source_binding(binding_path, source_path, root,
        root / 'data/assets/vehicles/sources/.unused-manifest-source-preflight')
    gate.require(lock.pipeline is not None, 'Current sedan manifest requires actual v2 generation binding')
    document = gate.strict_json(binding_path)
    portable = lock.pipeline.portable_input_lock
    gate.require(set(portable['roles']) == {'source', 'construction', 'constructor', 'geometry', 'profile', 'specification'},
                 'Unknown or incomplete lower input roles')
    gate.require(file_row(spec_path, root) == portable['roles']['specification'], 'Current specification differs from source generation')
    generation = gate.strict_json(lock.pipeline.generation.path)
    complete_inputs(root, generation, portable)
    historical = gate.strict_json(root / document['historical_binding']['path'])
    final_row = next(row for row in generation['source_outputs'] if row['role'] == 'native_finalization')
    finalization = gate.strict_json(root / final_row['path'])
    phases, extra = verify_commands(root, generation, historical, lock.pipeline.generation.path.parent,
        portable, document['pre_lod_source'], finalization)
    bundle = gate.strict_json(lock.pipeline.lower_bundle.path)
    gate.require(finalization['budget'] == bundle['proof']['live']['budget'], 'Finalization and complete lower budget differ')
    gate.require(finalization['indexed_shell_count'] == bundle['proof']['indexed_shell_count'], 'Finalization shell coverage differs')
    inputs = [file_row(row.path, root) for row in lock.inputs]
    tree = [file_row(path, root) for path in sorted(lock.pipeline.generation.path.parent.rglob('*')) if path.is_file()]
    rows = {row['path']: row for row in [*inputs, *extra, *tree]}
    gate.require(len({name.casefold() for name in rows}) == len(rows), 'Aliased generation artifact paths')
    for row in [*inputs, *extra, *tree]:
        gate.require(rows[row['path']] == row, 'Conflicting generation artifact identities')
    builder = file_row(root / BUILDER, root)
    gate.require(builder in generation['input_artifacts'], 'Two-phase builder missing from its generation inputs')
    derived = {row['path'] for row in tree}
    derived.update(document[name]['path'] for name in ('construction', 'lower_bundle'))
    derived.add(binding)
    lock.verify()
    return {'schema': 'sedan-manifest-source-generation.v1', 'status': 'validated-generation-ancestry-only',
            'source': file_row(source_path, root), 'specification': file_row(spec_path, root),
            'binding': file_row(binding_path, root), 'builder': builder,
            'artifacts': [rows[name] for name in sorted(rows)], 'derived_paths': sorted(derived), 'phases': phases,
            'expected_export': {'source_sha256': lock.source.sha256, 'binding_sha256': lock.binding.sha256,
                'construction_sha256': lock.pipeline.construction.sha256, 'lower_bundle_sha256': lock.pipeline.lower_bundle.sha256,
                'complete_lower_meshes': len(bundle['payload']['meshes']),
                'indexed_shell_count': bundle['proof']['indexed_shell_count'], 'budget': finalization['budget']},
            'checks': {'generation_inputs': len(generation['input_artifacts']), 'lower_inputs': len(portable['input_files']),
                       'generation_tree_files': len(tree), 'required_source_qa_stages': len(gate.source_stages(lock))},
            'limits': 'File and command ancestry only. No native geometry, complete source QA, export reproducibility, runtime or human acceptance is inferred.'}


def validate_export_verification(value, ancestry):
    gate.require(type(value) is dict, 'Missing actual exported source_generation_verification')
    for key, expected in ancestry['expected_export'].items():
        gate.require(value.get(key) == expected, 'Export source-generation verification differs: ' + key)
    gate.require(value.get('status') == 'passed' and value.get('source_saved') is False
                 and value.get('all_locked_inputs_unchanged') is True and value.get('human_approval_reference') is None,
                 'Export source verification did not pass its original immutable-source contract')
    gate.hash_value(value.get('current_front_proof_sha256'))
    gate.require(type(value.get('source_corners')) is int and value['source_corners'] > 0, 'Missing native front-corner coverage')
    error = value.get('raw_normal_maximum_unit_error')
    gate.require(type(error) in (int, float) and math.isfinite(error) and 0 <= error <= 1e-6,
                 'Native raw-normal unit guard failed')
    budget = value['budget']
    gate.require(budget['passed'] is True and budget['counts']['0'] <= 150000 and budget['total'] <= 200000
                 and budget['material_count'] <= 32 and 0 < sum(budget['collision'].values()) <= 128,
                 'Source budget exceeds the unchanged content ceiling')
    return {**ancestry, 'status': 'validated-ancestry-and-export-binding'}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve(strict=True)
    path = current_path(root, args.inventory)
    before = file_row(path, root)
    inventory = gate.strict_json(path)
    ancestry = load_ancestry(root)
    gate.require(inventory.get('asset_id') == 'endurance-sedan' and inventory.get('status') == 'passed'
                 and inventory['source']['sha256'] == ancestry['source']['sha256']
                 and inventory['specification_sha256'] == ancestry['specification']['sha256'],
                 'Actual exported inventory differs from generation source/specification')
    result = validate_export_verification(inventory.get('source_generation_verification'), ancestry)
    gate.require(file_row(path, root) == before, 'Export inventory changed during manifest validation')
    result['export_inventory'] = before
    print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))


if __name__ == '__main__':
    main()
