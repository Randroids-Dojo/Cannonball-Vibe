"""Build an isolated editable sedan from locked project inputs and empty Blender.

The output is a reviewable candidate project. This command never installs its
source, exports an asset, changes the game DLL, or approves a human gate.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

from endurance_sedan import source_generation as records
from endurance_sedan.qa.gate import positive_process


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    blender = args.blender_bin.resolve(strict=True)
    records.require(not output.exists(), 'Choose a new candidate directory; earlier work is retained')
    package = original / 'tools/vehicles'
    records.require(not output.is_relative_to(package), 'Output must be outside the constructor tree')
    inputs = sorted({path for path in package.rglob('*') if path.is_file() and path.suffix in ('.py', '.json')}
                    | {original / ('docs/vehicles/endurance-sedan/' + name)
                       for name in ('specification.json', 'blockout-integration.json')})
    initial = [records.file_row(path, original) for path in inputs]
    output.mkdir(parents=True)
    project = output / 'project'
    for path in inputs:
        destination = project / path.relative_to(original)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    records.verify_rows(initial, project)
    records.verify_rows(initial, original)
    sources = project / 'data/assets/vehicles/sources'
    generation = sources / 'endurance-sedan-generation'
    commands = generation / 'commands'
    commands.mkdir(parents=True)
    pre_lod = generation / 'pre-lod/source.blend'
    final = sources / 'endurance-sedan.blend'
    construction = sources / 'endurance-sedan.construction.json.gz'
    lower_bundle = sources / 'endurance-sedan.lower.json.gz'
    source_binding = sources / 'endurance-sedan.source-binding.json'
    report = {'schema': 'endurance-sedan-source-generation-record.v2', 'task_id': 'P1-018',
              'milestone': 'M5', 'start_utc': utc(), 'platform': platform.platform(),
              'python': sys.version, 'status': 'running', 'exit_status': None,
              'original_project': str(original), 'candidate_project': str(project),
              'blender': records.file_row(blender), 'input_artifacts': initial,
              'commands': [], 'source_outputs': [], 'human_approval_reference': None}
    try:
        report['git_revision'] = subprocess.check_output(
            ['git', '-C', str(original), 'rev-parse', 'HEAD'], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        report['git_revision'] = None

    def native(label, script, arguments, phase_outputs):
        argv = [str(blender), '--background', '--factory-startup', '--threads', '2',
                '--python-exit-code', '1', '--python', str(project / script), '--', *map(str, arguments)]
        row = {'label': label, 'argv': argv, 'cwd': str(project), 'start_utc': utc()}
        stdout, stderr = commands / (label + '.stdout.log'), commands / (label + '.stderr.log')
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                           BLENDER_USER_CONFIG=str(output / 'blender-config'),
                           BLENDER_USER_SCRIPTS=str(output / 'blender-scripts'))
        started = time.monotonic()
        try:
            with stdout.open('xb') as out, stderr.open('xb') as err:
                process = subprocess.run(argv, cwd=project, env=environment, stdout=out, stderr=err,
                    timeout=3600, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                code = process.returncode
        except subprocess.TimeoutExpired:
            code = 124
            row['timed_out'] = True
        row.update(exit_status=code, end_utc=utc(), elapsed_seconds=time.monotonic() - started,
                   logs=[records.file_row(path, project) for path in (stdout, stderr)])
        row['outputs'] = [records.file_row(path, project) for path in phase_outputs if path.is_file()]
        report['commands'].append(row)
        records.write(commands / (label + '.json'), row)
        positive_process(code, stdout.read_text(encoding='utf-8', errors='replace') + '\n' +
                         stderr.read_text(encoding='utf-8', errors='replace'))
        records.require(all(path.is_file() for path in phase_outputs), 'Native phase omitted a required output')
        records.verify_rows(initial, project)
        records.verify_rows([report['blender']])
        print('SEDAN_BUILD_PHASE ' + str({'label': label, 'exit_status': code,
                                         'elapsed_seconds': row['elapsed_seconds']}), flush=True)
        return row

    try:
        pre_front = pre_lod.parent / 'pre-front/source.blend'
        historical_source = pre_lod.parent / 'shoulder/source.blend'
        historical_packet = historical_source.with_suffix('.shoulder.json.gz')
        historical_profile = historical_source.with_suffix('.shoulder-profile.json')
        tire_revision = records.read(project / 'docs/vehicles/endurance-sedan/specification.json')['original_packaging'].get('tire_groove_revision38')
        tire_checkpoint = [pre_lod.parent / 'pre-grooves/source.blend'] if tire_revision is not None else []
        detail_policy = records.read(project / 'docs/vehicles/endurance-sedan/specification.json')['original_packaging']
        detail_checkpoint = [pre_lod.parent / 'pre-detail/source.blend'] if 'repeated_detail_revision38' in detail_policy else []
        first = native('fresh-construction', 'tools/vehicles/create_endurance_sedan.py',
            ['--output', pre_lod, '--stage', 'production', '--surface-preview'],
            [pre_lod, pre_lod.with_suffix('.construction.json.gz'), pre_front, historical_source,
             historical_packet, historical_profile, *tire_checkpoint, *detail_checkpoint])
        shutil.copyfile(pre_lod.with_suffix('.construction.json.gz'), construction)
        companion = records.read(construction)
        constructors = companion['construction_inputs']
        records.verify_rows(constructors, project)
        historical_record = generation / 'historical-record.json'
        historical_outputs = [dict(records.file_row(path, project), role=role) for role, path in (
            ('source', historical_source), ('construction_packet', historical_packet),
            ('shoulder_profile', historical_profile))]
        records.write(historical_record, {
            'schema': 'endurance-sedan-source-generation-record.v1', 'exit_status': 0,
            'constructor_inputs_sha256': records.digest(constructors), 'source_outputs': historical_outputs,
            'argv': first['argv'], 'checkpoint_phase': 'final-geometry-before-shoulder-apply',
            'logs': first['logs'], 'start_utc': first['start_utc'], 'end_utc': first['end_utc'],
            'native_command_record': records.file_row(commands / 'fresh-construction.json', project)})
        builder = project / 'tools/vehicles/endurance_sedan/fresh_reference.py'
        historical_binding = generation / 'historical-source-binding.json'
        records.write(historical_binding, {
            'schema': 'endurance-sedan-source-generation-binding.v1',
            **{role: records.file_row(path, project) for role, path in (
                ('source', historical_source), ('construction_packet', historical_packet),
                ('shoulder_profile', historical_profile), ('reference_builder', builder),
                ('generation_record', historical_record))},
            'builder_inputs': [records.file_row(project / row['path'], project) for row in constructors],
            'construction_inputs': constructors, 'constructor_inputs_sha256': records.digest(constructors)})
        lock = records.lower_lock(project, pre_lod, construction)
        lock_path = generation / 'lower-input-lock.json'
        records.write(lock_path, lock)
        native_report = generation / 'native-finalization.json'
        native('finalize-and-reopen', 'tools/vehicles/endurance_sedan/finalize_source.py',
            ['--input-lock', lock_path, '--expected-lock-digest', records.digest(lock),
             '--output', final, '--bundle', lower_bundle, '--report', native_report],
            [final, lower_bundle, native_report])
        finished = records.read(native_report)
        records.require(finished['status'] == 'passed' and finished['source_reopened'],
                        'Native saved-source finalization is incomplete')
        final_lock = records.lower_lock(project, final, construction)
        report.update(status='passed', exit_status=0, end_utc=utc(),
            constructor_inputs_sha256=records.digest(constructors),
            source_outputs=[dict(records.file_row(path, project), role=role) for role, path in (
                ('source', final), ('pre_lod_source', pre_lod), ('pre_front_source', pre_front), ('construction', construction),
                ('lower_bundle', lower_bundle), ('historical_binding', historical_binding),
                ('native_finalization', native_report))],
            source_input_lock=records.portable_lock(final_lock, project))
        generation_record = generation / 'generation-record.json'
        records.write(generation_record, report)
        records.write(source_binding, {'schema': 'endurance-sedan-source-generation-binding.v2',
            **{role: records.file_row(path, project) for role, path in (
                ('source', final), ('pre_lod_source', pre_lod), ('pre_front_source', pre_front), ('construction', construction),
                ('lower_bundle', lower_bundle), ('historical_binding', historical_binding),
                ('generation_record', generation_record))},
            'source_input_lock': records.portable_lock(final_lock, project)})
        records.verify_rows(initial, project)
        report['original_worktree_inputs_unchanged'] = all(
            (original / row['path']).is_file() and records.sha(original / row['path']) == row['sha256']
            for row in initial)
        report['locked_snapshot_inputs_unchanged'] = True
        report['delivered_binding'] = records.file_row(source_binding, project)
    except BaseException as failure:
        report.update(status='failed', exit_status=1, end_utc=utc(),
                      error=type(failure).__name__ + ': ' + str(failure), traceback=traceback.format_exc())
        print(report['traceback'], flush=True)
    records.write(output / 'build-result.json', report)
    print('SEDAN_BUILD_COMPLETE ' + str({'status': report['status'], 'candidate': str(project),
                                       'source_binding': str(source_binding)}), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
