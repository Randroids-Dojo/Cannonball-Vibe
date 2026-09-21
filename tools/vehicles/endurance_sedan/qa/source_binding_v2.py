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
    valance_cover: object | None = None
    front_finish: object | None = None
    upper_finish: object | None = None
    current_tire: object | None = None


def load(path, source, root, output, legacy_loader):
    if __package__:
        from .gate import (Input, SourceLock, artifact, digest, keys, positive_process,
                           require, sha, strict_json)
        from .repeated_detail_report import lock_optional
        from .valance_cover_report import lock_optional as lock_cover
        from .front_finish_report import lock_optional as lock_front
        from .upper_finish_report import lock_optional as lock_upper
        from .tire_finish_report import lock_optional as lock_tire, HELPERS as TIRE_HELPERS
    else:
        from gate import (Input, SourceLock, artifact, digest, keys, positive_process,
                          require, sha, strict_json)
        from repeated_detail_report import lock_optional
        from valance_cover_report import lock_optional as lock_cover
        from front_finish_report import lock_optional as lock_front
        from upper_finish_report import lock_optional as lock_upper
        from tire_finish_report import lock_optional as lock_tire, HELPERS as TIRE_HELPERS

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
    cover_paths = {'constructor': root / 'tools/vehicles/endurance_sedan/valance_cover39/construction.py',
                   'encoder': root / 'tools/vehicles/endurance_sedan/corner_encoding.py'}
    cover = lock_cover(strict_json(role_rows['specification'].path), construction,
        is_pipeline=True, artifact=lambda row: artifact(row, root), generation_inputs=input_files,
        phase_outputs=fresh_outputs,
        source_artifacts=[*files.values(), historical_source, *role_rows.values(), *tire_inputs, *detail_inputs],
        logical_files={key: row for key, logical in cover_paths.items()
                       for row in input_files if row.path == logical})
    cover_inputs = [] if cover is None else [cover.checkpoint, cover.requested, cover.constructor, cover.encoder]
    front_paths = {'constructor': root / 'tools/vehicles/endurance_sedan/front_finish40/construction.py',
                   'generator': root / 'tools/vehicles/endurance_sedan/front_compact40/__init__.py',
                   'encoder': root / 'tools/vehicles/endurance_sedan/corner_encoding.py'}
    front = lock_front(strict_json(role_rows['specification'].path), construction,
        is_pipeline=True, artifact=lambda row: artifact(row, root), generation_inputs=input_files,
        phase_outputs=fresh_outputs,
        source_artifacts=[*files.values(), historical_source, *role_rows.values(), *tire_inputs,
                          *detail_inputs, *cover_inputs],
        logical_files={key: row for key, logical in front_paths.items()
                       for row in input_files if row.path == logical})
    front_inputs = [] if front is None else [front.checkpoint, front.requested, front.constructor,
                                            front.generator, front.encoder]
    upper_paths = {'constructor': root / 'tools/vehicles/endurance_sedan/upper_finish40/construction.py',
                   'generator': root / 'tools/vehicles/endurance_sedan/upper_sections40/__init__.py',
                   'encoder': root / 'tools/vehicles/endurance_sedan/corner_encoding.py',
                   'design': root / 'tools/vehicles/endurance_sedan/upper_sections40/sections.json',
                   **{role: root / 'tools/vehicles/endurance_sedan/upper_sections40/native_sections' / filename
                      for role, filename in (
                          ('native_generator', '__init__.py'), ('roof_generator', 'roof.py'),
                          ('roof_design', 'roof_sections.json'), ('frame_generator', 'frames.py'),
                          ('frame_design', 'frame_sections.json'))}}
    upper = lock_upper(strict_json(role_rows['specification'].path), construction,
        is_pipeline=True, artifact=lambda row: artifact(row, root), generation_inputs=input_files,
        phase_outputs=fresh_outputs,
        source_artifacts=[*files.values(), historical_source, *role_rows.values(), *tire_inputs,
                          *detail_inputs, *cover_inputs, *front_inputs],
        logical_files={key: row for key, logical in upper_paths.items()
                       for row in input_files if row.path == logical})
    upper_inputs = [] if upper is None else list(upper.artifacts)
    tire_paths = {key: root / 'tools/vehicles/endurance_sedan' / name for key, name in TIRE_HELPERS.items()}
    current_tire = lock_tire(strict_json(role_rows['specification'].path), construction,
        artifact=lambda row: artifact(row, root), generation_inputs=input_files, phase_outputs=fresh_outputs,
        source_artifacts=[*files.values(), historical_source, *role_rows.values(), *tire_inputs,
                          *detail_inputs, *cover_inputs, *front_inputs, *upper_inputs],
        logical_files={key: row for key, logical in tire_paths.items() for row in input_files if row.path == logical})
    current_tire_inputs = [] if current_tire is None else list(current_tire.artifacts)
    binding = Input(path, sha(path), path.stat().st_size)
    inputs = (binding, *files.values(), *historical.inputs, *input_files, *logs,
              *phase_outputs, *actual_outputs.values(), *role_rows.values(), *lower_inputs, *tire_inputs,
              *detail_inputs, *cover_inputs, *front_inputs, *upper_inputs, *current_tire_inputs)
    destination = Path(output).resolve()
    require(not destination.exists() and all(not row.path.is_relative_to(destination) for row in inputs),
            'New QA output must not contain locked source inputs')
    pipeline = PipelineLock(historical, files['pre_lod_source'], files['pre_front_source'], files['construction'],
                            files['lower_bundle'], files['generation_record'], portable,
                            repeated_detail=detail, valance_cover=cover, front_finish=front, upper_finish=upper,
                            current_tire=current_tire)
    lock = SourceLock(root, binding, files['source'], historical.packet, historical.profile,
                      historical.builder, historical.helper, historical.ownership,
                      historical.constructor_inputs_sha256, tuple(inputs), pipeline=pipeline)
    lock.verify()
    return lock


def validate_stage(report, lock, mode):
    if __package__:
        from .gate import require, strict_json
        from .front_finish_report import NAMES
    else:
        from gate import require, strict_json
        from front_finish_report import NAMES
    require(lock.pipeline is not None and report['mode'] == mode, 'Missing current source stage context')
    require(report['status'] == 'passed' and report['source_sha256'] == lock.source.sha256
            and report['source_binding_sha256'] == lock.binding.sha256
            and report['all_locked_inputs_unchanged'] is True and report['source_saved'] is False,
            'Current native stage is incomplete or bound to another source')
    require(report['human_approval_reference'] is None, 'Native stage cannot supply human approval')
    if mode == 'front':
        upper = getattr(lock.pipeline, 'upper_finish', None)
        if upper is not None:
            if __package__:
                from .upper_finish_report import NAMES as UPPER_NAMES
            else:
                from upper_finish_report import NAMES as UPPER_NAMES
            proof = report.get('current_upper')
            requested_upper = strict_json(upper.requested.path)['parts']
            require(type(proof) is dict and report.get('native_upper_checkpoint_observed') is True
                    and proof['status'] == 'passed-current-upper-chain'
                    and proof['checkpoint_sha256'] == upper.checkpoint.sha256
                    and proof['members'] == list(UPPER_NAMES)
                    and set(proof['panels']) == set(requested_upper) == set(UPPER_NAMES)
                    and proof['original_windshield_and_aperture_seals_retained'] is True,
                    'Current upper lacks the complete actual input and native output proof')
            for name in UPPER_NAMES:
                count = len(requested_upper[name]['triangles'])
                fields = proof['panels'][name]
                require(fields['triangles'] == count and fields['corners'] == 3 * count
                        and len(fields['complete_target_fields']) == count,
                        'Current upper field inventory differs: ' + name)
            require(proof['source_corners'] == sum(row['corners'] for row in proof['panels'].values()),
                    'Current upper aggregate field inventory differs')
        else:
            require(report.get('current_upper') is None and
                    report.get('native_upper_checkpoint_observed', False) is False,
                    'Legacy source unexpectedly claims current upper proof')
        require(report['pre_front_source_sha256'] == lock.pipeline.pre_front.sha256
                and report['actual_pre_front_checkpoint_exact'] is True and report['source_corners'] > 0,
                'Historical-to-current front chain is incomplete')
        if lock.pipeline.front_finish is not None:
            current = lock.pipeline.front_finish
            requested = strict_json(current.requested.path)['parts']
            require(report.get('native_completed_legacy_front_observed') is True and
                    report.get('completed_legacy_front_sha256') == current.checkpoint.sha256,
                    'Current front lacks the actual completed legacy checkpoint')
            panels = report.get('current_front_panels', {})
            require(report.get('current_front_members') == list(NAMES) and
                    set(panels) == set(requested) == set(NAMES),
                    'Current front stage must exercise all three current panels')
            for name in NAMES:
                count = len(requested[name]['triangles'])
                require(panels[name]['triangles'] == count and panels[name]['corners'] == 3 * count
                        and len(panels[name]['complete_target_fields']) == count,
                        'Current front panel field inventory differs from bound request: ' + name)
            require(report['source_corners'] == sum(row['corners'] for row in panels.values()),
                    'Current front aggregate field inventory differs')
        else:
            require(report.get('native_completed_legacy_front_observed') is False and
                    not any(key in report for key in ('current_front_members', 'current_front_panels',
                                                     'completed_legacy_front_sha256')),
                    'Legacy source stage unexpectedly claims current front revision')
    elif mode == 'front-controls':
        if __package__:
            from .front_controls40 import EXPECTED_NAMES, GROUPS
        else:
            from front_controls40 import EXPECTED_NAMES, GROUPS
        require(lock.pipeline.front_finish is not None and
                report.get('native_completed_legacy_front_observed') is True,
                'Current-front controls require the selected observed revision')
        value = report['current_front_controls']
        require(value['schema'] == 'current-front-controls40.v1' and value['status'] == 'passed'
                and value['selected_current_front'] is True and value['source_sha256'] == lock.source.sha256
                and all(value[key] is False for key in ('source_saved', 'exported', 'GPU')),
                'Current-front controls are incomplete or bound to another source')
        controls = value['controls']
        require(value['expected_names'] == list(EXPECTED_NAMES)
                and value['negative_count'] == len(controls) == len(EXPECTED_NAMES)
                and {row['name'] for row in controls} == set(EXPECTED_NAMES),
                'Incomplete current-front counterexample identity inventory')
        require(set(value['groups']) == set(GROUPS)
                and all(value['groups'][group] == [row['name'] for row in controls if row['group'] == group]
                        and value['groups'][group] for group in GROUPS),
                'Incomplete current-front counterexample groups')
        require(all(row['status'] == 'rejected' and row['observed_exception'] == 'ValueError'
                    and row['group'] in GROUPS and row['required_predicates']
                    and any(text in row['observed_predicate'] for text in row['required_predicates'])
                    for row in controls), 'Current-front counterexample accepted or wrong predicate')
        positive = value['positive_current']
        require(positive['source']['sha256'] == lock.source.sha256
                and positive['context_digest'] == value['context_digest']
                and positive['current_packet_digest'] == value['packet_digest']
                and positive['legacy_observation_sha256'] == value['observation_digest']
                and positive['proof']['members'] == list(NAMES),
                'Current-front control baseline lacks the held current proof')
        suffixes = ('MixedProtectedFront', 'ProtectedFrontFender_L', 'ProtectedFrontFender_R')
        expected_lower = {'LOD' + str(level) + '_' + suffix: name
                          for level in (1, 2) for name, suffix in zip(NAMES, suffixes, strict=True)}
        require(set(value['positive_lower_fields']) == set(expected_lower)
                and all(value['positive_lower_fields'][name]['source'] == source
                        for name, source in expected_lower.items()),
                'Current-front controls lack all six actual lower baselines')
        budget = value['actual_budget']
        require(budget['passed'] is True and set(budget['counts']) == {'0', '1', '2'}
                and budget['counts']['0'] <= 150000
                and budget['total'] == sum(budget['counts'].values()) + sum(budget['collision'].values())
                and budget['total'] <= 200000 and budget['material_count'] <= 32,
                'Current-front controls lack an actual within-budget baseline')
        restored = value['restoration']
        require(all(restored[key] is True for key in (
                    'all_actual_object_fields_and_materials_exact', 'all_mesh_datablock_identities_exact',
                    'held_inputs_exact', 'caller_chain_proof_presence_and_identity_restored', 'feature_cache_restored'))
                and restored['object_count'] > 0 and restored['mesh_count'] > 0
                and restored['before_native_digest'] == restored['after_native_digest']
                and restored['before_inputs'] == restored['after_inputs'],
                'Current-front controls did not restore all actual inputs')
    else:
        require(report['complete_final_lower_count'] > 0 and report['indexed_shell_count'] > 0
                and report['budget']['passed'] is True, 'Current lower source validation is incomplete')
    return {'status': 'passed', 'mode': mode, 'payload': report['payload']}
