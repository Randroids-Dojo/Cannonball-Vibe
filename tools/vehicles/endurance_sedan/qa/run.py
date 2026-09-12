"""Reproduce the independent source QA gate from one locked editable .blend."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

from gate import STAGES, completed_inventory, inventory, json_read, positive_process, sha, stage_report, load_source_binding


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, document):
    path.write_text(json.dumps(document, indent=2, allow_nan=False) + '\n', encoding='utf8', newline='\n')


class Runner:
    def __init__(self, source, blender, output, scripts):
        self.source, self.blender, self.output, self.scripts = source, blender, output, scripts
        self.source_sha = sha(source)
        self.blender_sha = sha(blender)
        self.sequence = 0
        self.commands = []
        self.locked_outputs = {}
        self.initial_inputs = {str(path): sha(path) for path in (source, blender, *sorted(scripts.glob('*')))
                               if path.is_file()}
        self.environment = dict(os.environ)
        self.environment.update(BLENDER_USER_CONFIG=str(output / 'blender-user-config'),
                                BLENDER_USER_SCRIPTS=str(output / 'blender-user-scripts'),
                                PYTHONDONTWRITEBYTECODE='1')

    def command(self, name, script, arguments, outputs, timeout=900, native=True,
                expected_exit=0, positive=True):
        self.sequence += 1
        prefix = self.output / 'commands' / f'{self.sequence:02d}-{name}'
        argv = ([str(self.blender), '--background', '--factory-startup', '--python-exit-code', '1',
                 '--python', str(self.scripts / script), '--', *map(str, arguments)] if native else
                [sys.executable, str(self.scripts / script), *map(str, arguments)])
        before = {str(path): sha(path) for path in (self.source, self.blender, *sorted(self.scripts.glob('*')))
                  if path.is_file()}
        for path in arguments:
            if isinstance(path, Path) and path.is_file() and path not in outputs:
                before[str(path)] = sha(path)
        for path, digest in (self.initial_inputs | self.locked_outputs).items():
            if not Path(path).is_file() or sha(Path(path)) != digest:
                raise ValueError('Retained input changed between QA stages: ' + path)
            before[path] = digest
        row = {'name': name, 'argv': argv, 'cwd': str(self.output), 'start_utc': utc(),
               'expected_exit': expected_exit, 'positive_command': positive,
               'inputs': [{'path': path, 'sha256': digest} for path, digest in before.items()],
               'timeout_seconds': timeout}
        started = time.perf_counter()
        try:
            process = subprocess.run(argv, cwd=self.output, env=self.environment,
                                     capture_output=True, timeout=timeout)
            code, stdout, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as failure:
            code, stdout, stderr = 124, failure.stdout or b'', failure.stderr or b''
            row['timeout'] = True
        prefix.with_suffix('.stdout.log').write_bytes(stdout)
        prefix.with_suffix('.stderr.log').write_bytes(stderr)
        row.update(exit_status=code, end_utc=utc(), elapsed_seconds=time.perf_counter() - started,
                   inputs_unchanged=all(Path(path).is_file() and sha(Path(path)) == digest for path, digest in before.items()))
        paths = [prefix.with_suffix('.stdout.log'), prefix.with_suffix('.stderr.log'), *outputs]
        row['outputs'] = [{'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
                          for path in paths if path.is_file()]
        error = None
        try:
            if code != expected_exit:
                raise ValueError(f'Expected exit{expected_exit}; actual{code}')
            if positive:
                positive_process(code, (stdout + b'\n' + stderr).decode('utf8', errors='replace'))
            if not row['inputs_unchanged']:
                raise ValueError('Locked source, executable or retained QA tool changed during execution')
            if any(not path.is_file() for path in outputs):
                raise ValueError('Required output missing after native process completion')
            row['status'] = 'passed'
        except Exception as failure:
            error = failure
            row.update(status='failed', failure=str(failure))
        record = prefix.with_suffix('.json')
        write(record, row)
        self.commands.append({'path': str(record), 'sha256': sha(record), 'status': row['status']})
        print(json.dumps({'stage': name, 'native_exit': code, 'process_status': row['status'],
                          'elapsed_seconds': row['elapsed_seconds']}), flush=True)
        if error:
            raise error
        self.locked_outputs.update({str(path): sha(path) for path in outputs})
        return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--source-binding', type=Path, required=True)
    parser.add_argument('--construction-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, blender, output = args.source.resolve(strict=True), args.blender.resolve(strict=True), args.output.resolve()
    original = Path(__file__).resolve().parent
    if not source.is_file() or source.suffix.lower() != '.blend' or not blender.is_file():
        parser.error('Existing .blend source and Blender executable are required')
    if output.exists() or output == original or output.is_relative_to(original) or original.is_relative_to(output):
        parser.error('Choose a fresh output directory outside the QA tool/source tree')
    if source.is_relative_to(output) or blender.is_relative_to(output):
        parser.error('Output must not contain any locked input')
    try:
        source_lock = load_source_binding(args.source_binding, source, args.construction_root, output)
    except Exception as failure:
        output.mkdir(parents=True)
        result = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': utc(),
                  'platform': platform.platform(), 'python': sys.version,
                  'status': 'failed', 'stage': 'source-binding-preflight',
                  'source': str(source), 'source_sha256': sha(source),
                  'binding_argument': str(args.source_binding),
                  'construction_root_argument': str(args.construction_root),
                  'blender': str(blender), 'blender_sha256': sha(blender),
                  'required_stages': list(STAGES), 'completed_stages': 0, 'commands': [],
                  'failure': str(failure), 'traceback': traceback.format_exc(),
                  'human_approval_reference': None}
        write(output / 'evidence.json', result)
        print(json.dumps({'status': 'failed', 'stage': result['stage'], 'evidence': str(output / 'evidence.json')}), flush=True)
        return 1
    output.mkdir(parents=True)
    scripts = output / 'tools'
    scripts.mkdir()
    for path in sorted(original.iterdir()):
        if path.is_file() and path.suffix in ('.py', '.json'):
            shutil.copyfile(path, scripts / path.name)
    (output / 'commands').mkdir()
    runner = Runner(source, blender, output, scripts)
    runner.initial_inputs.update({str(p): sha(p) for p in original.iterdir() if p.is_file() and p.suffix in (".py", ".json")})
    runner.initial_inputs.update({str(row.path): row.sha256 for row in source_lock.inputs})
    try:
        revision = subprocess.check_output(['git', '-C', str(original), 'rev-parse', 'HEAD'], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    result = {'task_id': 'P1-018', 'milestone': 'M5', 'start_utc': utc(),
              'git_revision': revision, 'platform': platform.platform(), 'python': sys.version,
              'source': str(source), 'source_sha256': runner.source_sha,
              'source_generation_binding': {'path': str(source_lock.binding.path), 'sha256': source_lock.binding.sha256},
              'constructor_inputs_sha256': source_lock.constructor_inputs_sha256,
              'source_generation_inputs': [{'path': str(r.path), 'sha256': r.sha256, 'bytes': r.bytes} for r in source_lock.inputs],
              'blender': str(blender), 'blender_sha256': runner.blender_sha,
              'required_stages': list(STAGES), 'completed_stages': 0, 'stages': [],
              'status': 'running', 'human_approval_reference': None,
              'scope': 'Independent source geometry/control certificates only. Export byte reproducibility, runtime behavior/media/performance/platform and human approvals are separate required evidence.'}
    summary = output / 'evidence.json'
    write(summary, result)
    geometry = output / 'evaluated-meshes.json.gz'
    opening = output / 'opening-drivers.json'
    motion = output / 'motion-drivers.json'
    paths = {name: output / (name + '.json') for name in STAGES}
    paths['shoulder-field'] = output / 'shoulder-field' / 'report.json'
    import seat_finish_report
    context = {'source_lock': source_lock, 'geometry': geometry}
    shoulder_tools = [source_lock.builder.path, source_lock.helper.path, source_lock.ownership.path,
                      *[scripts / n for n in ('shoulder_check.py', 'shoulder_checkpoint.py', 'shoulder_report.py')]]
    context['shoulder_tools'] = {str(p): {'path': str(p), 'sha256': runner.initial_inputs[str(p)],
                                         'bytes': p.stat().st_size} for p in shoulder_tools}
    stages = [
        ('extraction', 'extract.py', ['--source', source, '--output', output, '--opening-steps', '100'],
         [geometry, output / 'evaluated-inventory.json']),
        ('shoulder-field', 'shoulder_check.py', ['--source', source, '--packet', source_lock.packet.path,
         '--profile', source_lock.profile.path, '--builder', source_lock.builder.path,
         '--geometry', geometry, '--helper', source_lock.helper.path, '--ownership', source_lock.ownership.path,
         '--construction-root', source_lock.root, '--output', output / 'shoulder-field'],
         [paths['shoulder-field'], output / 'shoulder-field/native-payload.json.gz', output / 'shoulder-field/fresh-reference.json']),
        ('self-intersections', 'self_intersections.py', ['--source', source, '--geometry', geometry, '--output', paths['self-intersections']], [paths['self-intersections']]),
        ('self-controls', 'self_controls.py', ['--blender', blender, '--source', source, '--geometry', geometry, '--output', output / 'self-controls-native', '--report', paths['self-controls']], [paths['self-controls']]),
        ('lod-self-intersections', 'lod_self_intersections.py', ['--source', source, '--output', paths['lod-self-intersections']], [paths['lod-self-intersections']]),
        ('lod-self-controls', 'lod_self_controls.py', ['--blender', blender, '--source', source, '--output', output / 'lod-self-controls-native', '--report', paths['lod-self-controls']], [paths['lod-self-controls']]),
        ('source-controls', 'source_controls.py', ['--source', source, '--output', paths['source-controls']], [paths['source-controls']]),
        ('source-lights', 'source_lights.py', ['--source', source, '--output', paths['source-lights']], [paths['source-lights']]),
        ('opening-drivers', 'opening_drivers.py', ['--source', source, '--output', opening], [opening]),
        ('motion-drivers', 'motion_drivers.py', ['--source', source, '--output', motion], [motion]),
        ('optical-seats', 'optical_seats.py', ['--geometry', geometry, '--output', paths['optical-seats']], [paths['optical-seats']]),
        ('finish-interfaces', 'seat_finish_interfaces.py', ['--geometry', geometry, '--output', paths['finish-interfaces']], [paths['finish-interfaces']]),
        ('cupholder-interfaces', 'cupholder_interfaces.py', ['--geometry', geometry, '--output', paths['cupholder-interfaces']], [paths['cupholder-interfaces']]),
        ('static-interfaces', 'static_interfaces.py', ['--geometry', geometry, '--optical-report', paths['optical-seats'], '--finish-report', paths['finish-interfaces'], '--output', paths['static-interfaces']], [paths['static-interfaces'], output / 'static-interfaces.intersection-solids.json.gz']),
        ('openings', 'openings.py', ['--input', geometry, '--drivers', opening, '--output', paths['openings']], [paths['openings']]),
        ('opening-containment', 'initial_containment.py', ['--geometry', geometry, '--certificate', paths['openings'], '--kind', 'openings', '--output', paths['opening-containment']], [paths['opening-containment']]),
        ('tires', 'tires.py', ['--input', geometry, '--drivers', motion, '--openings', opening, '--output', paths['tires']], [paths['tires']]),
        ('wiper-glass', 'wipers.py', ['--source', source, '--geometry', geometry, '--motion-contract', motion, '--output', paths['wiper-glass']], [paths['wiper-glass']]),
        ('wiper-interassembly', 'wiper_interassembly.py', ['--source', source, '--geometry', geometry, '--motion-contract', motion, '--opening-contract', opening, '--seconds', '780', '--output', paths['wiper-interassembly']], [paths['wiper-interassembly']]),
        ('wiper-containment', 'initial_containment.py', ['--geometry', geometry, '--certificate', paths['wiper-interassembly'], '--kind', 'wipers', '--output', paths['wiper-containment']], [paths['wiper-containment']]),
        ('negative-controls', 'negative_controls.py', ['--blender', blender, '--source', source, '--geometry', geometry, '--motion-contract', motion, '--opening-contract', opening, '--output', output / 'negative', '--report', paths['negative-controls']], [paths['negative-controls']]),
    ]
    try:
        for name, script, arguments, outputs in stages:
            runner.command(name, script, arguments, outputs, native=name not in ('negative-controls','self-controls','lod-self-controls'))
            if name == 'extraction':
                metrics = inventory(json_read(output / 'evaluated-inventory.json'), geometry, runner.source_sha)
                context['geometry_sha256'] = runner.locked_outputs[str(geometry)]
                context['seat_inputs'] = {str(p): (runner.initial_inputs | runner.locked_outputs)[str(p)]
                                          for p in (geometry, source, *[scripts / n for n in seat_finish_report.DEPENDENCIES])}
                write(output / 'run-binding.json', {
                    'source_generation_binding_sha256': source_lock.binding.sha256,
                    'source_sha256': runner.source_sha, 'geometry_sha256': context['geometry_sha256'],
                    'seat_inputs': context['seat_inputs'], 'shoulder_tools': context['shoulder_tools']})
                runner.locked_outputs[str(output / 'run-binding.json')] = sha(output / 'run-binding.json')
            else:
                if name == 'static-interfaces':
                    context['finish_report'] = json_read(paths['finish-interfaces'])
                    context['optical_report'] = json_read(paths['optical-seats'])
                metrics = stage_report(name, json_read(paths[name]), runner.source_sha, context=context)
            result['stages'].append({'name': name, **metrics})
            result['completed_stages'] = len(result['stages'])
            result['commands'] = runner.commands
            write(summary, result)
        completed_inventory(result['stages'])
        source_lock.verify()
        result['status'] = 'passed'
    except Exception as failure:
        result.update(status='failed', failure=str(failure), traceback=traceback.format_exc())
    finally:
        result.update(end_utc=utc(), source_unchanged=sha(source) == runner.source_sha,
                      blender_unchanged=sha(blender) == runner.blender_sha, commands=runner.commands,
                      tool_snapshot=[{'path': str(path), 'sha256': sha(path)} for path in sorted(scripts.iterdir()) if path.is_file()])
        result['all_locked_inputs_unchanged'] = all(Path(p).is_file() and sha(Path(p)) == h
                                                   for p, h in (runner.initial_inputs | runner.locked_outputs).items())
        if not result['source_unchanged'] or not result['blender_unchanged'] or not result['all_locked_inputs_unchanged']:
            result['status'] = 'failed'
        result['outputs'] = [{'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
                             for path in sorted(output.rglob('*')) if path.is_file() and path != summary]
        write(summary, result)
    print(json.dumps({'status': result['status'], 'completed_stages': result['completed_stages'], 'evidence': str(summary)}), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
