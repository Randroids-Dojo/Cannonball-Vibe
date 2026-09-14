"""Keep historical and final source authority separate in generation binding v2."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineLock:
    historical: object
    pre_lod: object
    pre_front: object
    construction: object
    lower_bundle: object
    generation: object
    portable_input_lock: dict
    repeated_detail: object | None = None


def load(path, source, root, output, legacy_loader):
    if __package__:
        from .gate import (Input, SourceLock, artifact, digest, keys, positive_process,
                           require, sha, strict_json)
        from .repeated_detail_report import lock_optional
    else:
        from gate import (Input, SourceLock, artifact, digest, keys, positive_process,
                          require, sha, strict_json)
        from repeated_detail_report import lock_optional

    path, source, root = Path(path).resolve(strict=True), Path(source).resolve(strict=True), Path(root).resolve(strict=True)
    document = strict_json(path)
    roles = ('source', 'pre_lod_source', 'pre_front_source', 'construction', 'lower_bundle', 'historical_binding', 'generation_record')
    keys(document, ('schema', *roles, 'source_input_lock'), 'v2 source binding')
    require(document['schema'] == 'endurance-sedan-source-generation-binding.v2', 'Wrong v2 binding schema')
    files = {name: artifact(document[name], root) for name in roles}
    require(files['source'].path == source and source.suffix.lower() == '.blend', 'Wrong actual final source')
    require(len({row.path for row in files.values()}) == len(files), 'Aliased v2 source artifacts')
    historical_document = strict_json(files['historical_binding'].path)
    require(historical_document['schema'] == 'endurance-sedan-source-generation-binding.v1',
            'Historical shoulder binding must keep v1 semantics')
    historical_source = artifact(historical_document['source'], root)
    require(historical_source.path != source, 'Historical shoulder source cannot replace final source')
    require(historical_source.path not in (files['pre_front_source'].path, files['pre_lod_source'].path),
            'Historical shoulder, pre-front and pre-LOD sources must be distinct native phase artifacts')
    historical = legacy_loader(files['historical_binding'].path, historical_source.path, root, output)
    construction = strict_json(files['construction'].path)
    require(construction['construction_inputs'] == historical_document['construction_inputs']
            and digest(construction['construction_inputs']) == historical.constructor_inputs_sha256,
            'Historical and final constructor inputs differ')
    generation = strict_json(files['generation_record'].path)
    require(generation['schema'] == 'endurance-sedan-source-generation-record.v2'
            and generation['status'] == 'passed' and generation['exit_status'] == 0,
            'Source generation did not pass')
    require(generation['constructor_inputs_sha256'] == historical.constructor_inputs_sha256,
            'Generation constructor digest differs')
    input_files = [artifact(row, root) for row in generation['input_artifacts']]
    require(input_files and len({row.path for row in input_files}) == len(input_files),
            'Missing or duplicated full generation inputs')
    commands = generation['commands']
    require([row['label'] for row in commands] == ['fresh-construction', 'finalize-and-reopen'],
            'Both actual source phases are required')
    logs = []
    phase_outputs = []
    fresh_outputs = []
    for command in commands:
        require(command['exit_status'] == 0 and not command.get('timed_out'), 'Failed native generation phase')
        require(isinstance(command['argv'], list) and command['argv'] and
                all(isinstance(arg, str) and arg for arg in command['argv']), 'Missing exact native argv')
        require(len(command['logs']) == 2, 'Separate actual stdout/stderr required')
        actual_logs = [artifact(row, root) for row in command['logs']]
        require(actual_logs[0].path != actual_logs[1].path, 'Aliased native logs')
        positive_process(0, '\n'.join(row.path.read_text(encoding='utf-8', errors='replace') for row in actual_logs))
        logs.extend(actual_logs)
        actual_phase_outputs = [artifact(row, root) for row in command['outputs']]
        phase_outputs.extend(actual_phase_outputs)
        if command['label'] == 'fresh-construction':
            fresh_outputs = actual_phase_outputs
    source_outputs = generation['source_outputs']
    expected_roles = {'source', 'pre_lod_source', 'pre_front_source', 'construction', 'lower_bundle', 'historical_binding', 'native_finalization'}
    require(len(source_outputs) == len(expected_roles) and {row['role'] for row in source_outputs} == expected_roles,
            'Incomplete generation output roles')
    actual_outputs = {}
    for row in source_outputs:
        keys(row, ('role', 'path', 'sha256', 'bytes'), 'generation output')
        actual_outputs[row['role']] = artifact({k: row[k] for k in ('path', 'sha256', 'bytes')}, root)
    for name in expected_roles - {'native_finalization'}:
        require(actual_outputs[name] == files[name], 'Generation output differs from supplied v2 binding: ' + name)
    require(files['pre_front_source'] in phase_outputs and historical_source in phase_outputs,
            'Both actual historical shoulder and pre-front source outputs are required')
    finalization = strict_json(actual_outputs['native_finalization'].path)
    require(finalization['status'] == 'passed' and finalization['source_reopened'] is True
            and finalization['source_bytes_unchanged_after_reopen'] is True
            and finalization['source'] == document['source'] and finalization['bundle'] == document['lower_bundle'],
            'Final source was not independently reopened and verified')
    portable = document['source_input_lock']
    require(portable == generation['source_input_lock'], 'Final caller input lock differs')
    require(portable['schema'] == 'distance-lod-source-input38.v1', 'Wrong lower input schema')
    role_rows = {name: artifact(row, root) for name, row in portable['roles'].items()}
    require(role_rows['source'] == files['source'] and role_rows['construction'] == files['construction'],
            'Lower check is bound to another source or companion')
    lower_inputs = [artifact(row, root) for row in portable['input_files']]
    originals = portable['generation_inputs']
    require(len(originals) == len(construction['construction_inputs']), 'Incomplete original generation map')
    old_by_name = {row['path']: row for row in construction['construction_inputs']}
    require(len({row['logical_path'] for row in originals}) == len(originals), 'Duplicate original logical input')
    for row in originals:
        keys(row, ('logical_path', 'path', 'sha256', 'bytes'), 'original generation map')
        original = old_by_name.get(row['logical_path'])
        require(original is not None and row['path'] == row['logical_path']
                and all(row[key] == original[key] for key in ('sha256', 'bytes')),
                'Original construction map differs from caller input')
        lower_inputs.append(artifact({k: row[k] for k in ('path', 'sha256', 'bytes')}, root))
    bundle = strict_json(files['lower_bundle'].path)
    require(bundle['schema'] == 'endurance-sedan-final-lower38.v1'
            and bundle['final_input_lock'] == portable, 'Wrong final lower proof binding')
    for name, expected in (('final_source', files['source']), ('original_source', files['pre_lod_source'])):
        require(bundle[name]['sha256'] == expected.sha256 and bundle[name]['bytes'] == expected.bytes,
                'Lower construction references another actual source')
    require(bundle['proof']['status'] == 'passed-native-construction', 'Lower native construction failed')
    tire_inputs = []
    if 'tire_grooves38' in construction:
        tire = construction['tire_grooves38']
        require(tire['schema'] == 'source-tire-groove-construction38.v1', 'Wrong high-tire companion schema')
        tire_inputs = [artifact(tire[key], root) for key in ('checkpoint', 'constructor', 'encoder')]
        require(tire_inputs[0] in phase_outputs, 'Actual pre-groove checkpoint is absent from generation outputs')
        require(all(row in input_files for row in tire_inputs[1:]), 'Tire constructor/encoder absent from locked generation inputs')
    logical_paths = {'constructor': root / 'tools/vehicles/endurance_sedan/repeated_detail38.py',
                     'encoder': root / 'tools/vehicles/endurance_sedan/corner_encoding.py'}
    detail = lock_optional(strict_json(role_rows['specification'].path), construction,
        is_pipeline=True, artifact=lambda row: artifact(row, root), generation_inputs=input_files,
        phase_outputs=fresh_outputs,
        source_artifacts=[*files.values(), historical_source, *role_rows.values(), *tire_inputs],
        logical_files={key: row for key, logical in logical_paths.items() for row in input_files if row.path == logical})
    detail_inputs = [] if detail is None else [detail.checkpoint, detail.constructor, detail.encoder]
    binding = Input(path, sha(path), path.stat().st_size)
    inputs = (binding, *files.values(), *historical.inputs, *input_files, *logs,
              *phase_outputs, *actual_outputs.values(), *role_rows.values(), *lower_inputs, *tire_inputs, *detail_inputs)
    destination = Path(output).resolve()
    require(not destination.exists() and all(not row.path.is_relative_to(destination) for row in inputs),
            'New QA output must not contain locked source inputs')
    pipeline = PipelineLock(historical, files['pre_lod_source'], files['pre_front_source'], files['construction'],
                            files['lower_bundle'], files['generation_record'], portable, repeated_detail=detail)
    lock = SourceLock(root, binding, files['source'], historical.packet, historical.profile,
                      historical.builder, historical.helper, historical.ownership,
                      historical.constructor_inputs_sha256, tuple(inputs), pipeline=pipeline)
    lock.verify()
    return lock


def validate_stage(report, lock, mode):
    if __package__:
        from .gate import require
    else:
        from gate import require
    require(lock.pipeline is not None and report['mode'] == mode, 'Missing current source stage context')
    require(report['status'] == 'passed' and report['source_sha256'] == lock.source.sha256
            and report['source_binding_sha256'] == lock.binding.sha256
            and report['all_locked_inputs_unchanged'] is True and report['source_saved'] is False,
            'Current native stage is incomplete or bound to another source')
    require(report['human_approval_reference'] is None, 'Native stage cannot supply human approval')
    if mode == 'front':
        require(report['pre_front_source_sha256'] == lock.pipeline.pre_front.sha256
                and report['actual_pre_front_checkpoint_exact'] is True and report['source_corners'] > 0,
                'Historical-to-current front chain is incomplete')
    else:
        require(report['complete_final_lower_count'] > 0 and report['indexed_shell_count'] > 0
                and report['budget']['passed'] is True, 'Current lower source validation is incomplete')
    return {'status': 'passed', 'mode': mode, 'payload': report['payload']}
