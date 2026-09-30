"""Pinned native controls for final-LOD indexed-shell coverage and exclusions."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time


NATIVE_NAMES = ('native-partition-complete', 'disconnected-crossings-excluded',
                'coincident-coordinates-not-welded', 'connected-fold-rejected',
                'shared-index-contact-kept-in-shell', 'native-topology-and-winding',
                'invalid-row-domain-rejections', 'partition-coverage-corruption-rejected')
CASES = ('positive', 'folded', 'disconnected-crossing', 'empty-lod1', 'empty-lod2',
         'no-lods', 'empty-mesh', 'open-shell', 'inconsistent-winding',
         'duplicate-face', 'missing-asset')
EXPECTED_NAMES = NATIVE_NAMES + tuple('native-cli-' + name for name in CASES) + ('report-negative-controls',)
COMMAND_NAMES = ('native-fixtures',) + tuple('native-cli-' + name for name in CASES)
PIN = ('5.1.2', 'ec6e62d40fa9')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_row(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf8', newline='\n')


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_report(report, source_hash):
    require(isinstance(report, dict), 'Lower-LOD control report must be an object')
    require(report.get('status') == 'passed' and report.get('source_sha256') == source_hash,
            'Lower-LOD control status/source mismatch')
    require(report.get('human_approval_reference') is None, 'Controls cannot approve a human gate')
    require(type(report.get('expected_controls')) is int and type(report.get('completed_controls')) is int
            and report['expected_controls'] == report['completed_controls'] == len(EXPECTED_NAMES),
            'Lower-LOD control counters incomplete')
    require(report.get('expected_control_names') == list(EXPECTED_NAMES), 'Lower-LOD control declaration changed')
    controls = report.get('controls')
    require(isinstance(controls, list) and all(isinstance(row, dict) for row in controls)
            and [row.get('name') for row in controls] == list(EXPECTED_NAMES)
            and all(row.get('status') == 'passed' for row in controls), 'Lower-LOD control rows incomplete')
    require(report.get('source_unchanged') is True and report.get('inputs_unchanged') is True,
            'Lower-LOD control inputs changed')
    for field in ('inputs', 'outputs', 'commands'):
        rows = report.get(field)
        require(isinstance(rows, list) and bool(rows) and all(isinstance(row, dict)
                and isinstance(row.get('path'), str) and bool(row['path'])
                and isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256'])
                and type(row.get('bytes')) is int and row['bytes'] >= 0 for row in rows),
                'Lower-LOD control ' + field + ' bindings absent or invalid')
    require([row.get('name') for row in report['commands']] == list(COMMAND_NAMES)
            and all(row.get('status') == 'passed' and type(row.get('exit_status')) is int
                    and type(row.get('expected_exit')) is int
                    and row['exit_status'] == row.get('expected_exit') for row in report['commands']),
            'Lower-LOD native command inventory incomplete')
    # These are fixed native fixture witnesses, not a certificate for arbitrary
    # model geometry. Preserve their actual index partitions and excluded hits.
    expected = (('tetra', [list(range(4))]), ('cube', [list(range(12))]),
                ('crossing', [list(range(4)), list(range(4, 8))]),
                ('coincident', [list(range(4)), list(range(4, 8))]),
                ('indexed', [list(range(8))]), ('folded', [list(range(12))]))
    partitions = controls[0].get('actual')
    require(isinstance(partitions, list) and len(partitions) == len(expected),
            'Lower-LOD native partition witness inventory is incomplete')
    for row, (name, groups) in zip(partitions, expected):
        require(isinstance(row, dict) and row.get('mesh') == name
                and type(row.get('triangles')) is int and row['triangles'] == sum(map(len, groups))
                and isinstance(row.get('groups'), list)
                and all(isinstance(group, list) and all(type(i) is int for i in group) for group in row['groups'])
                and row['groups'] == groups,
                'Lower-LOD native partition coverage or index types differ: ' + name)
    crossing = controls[1].get('certificate')
    require(isinstance(crossing, dict) and crossing.get('status') == 'passed'
            and crossing.get('name') == 'LOD1_Control_crossing',
            'Lower-LOD excluded-crossing certificate is absent')
    for key, value in (('triangles', 8), ('shell_count', 2), ('all_batch_aabb_candidates', 16),
                       ('tested_intrashell_candidates', 12), ('excluded_cross_shell_candidates', 4)):
        require(type(crossing.get(key)) is int and crossing[key] == value,
                'Lower-LOD excluded-crossing candidate count differs: ' + key)
    shells = crossing.get('shells')
    require(isinstance(shells, list) and len(shells) == 2, 'Lower-LOD crossing shell witnesses missing')
    for index, shell in enumerate(shells):
        indices = list(range(index * 4, (index + 1) * 4))
        require(isinstance(shell, dict) and shell.get('status') == 'passed'
                and type(shell.get('triangles')) is int and shell['triangles'] == 4
                and shell.get('bad_pairs') == []
                and isinstance(shell.get('source_triangle_indices'), list)
                and all(type(i) is int for i in shell['source_triangle_indices'])
                and shell['source_triangle_indices'] == indices,
                'Lower-LOD excluded-crossing shell coverage differs')
    witnesses = controls[1].get('excluded_actual_crossing_pairs')
    require(isinstance(witnesses, list) and len(witnesses) == 3,
            'Lower-LOD actual excluded-crossing witnesses are missing or incomplete')
    def points(value):
        return (isinstance(value, list) and bool(value)
                and all(isinstance(p, list) and len(p) == 3
                        and all(type(v) in (int, float) and -math.inf < v < math.inf for v in p) for p in value))
    for row, pair in zip(witnesses, ([3, 4], [3, 5], [3, 6])):
        require(isinstance(row, dict) and isinstance(row.get('triangles'), list)
                and all(type(i) is int for i in row['triangles']) and row['triangles'] == pair
                and row.get('shared_indices') == [], 'Lower-LOD excluded witness index identity differs')
        require(points(row.get('exact_intersection_points_m')) and points(row.get('outside_shared_simplex_m'))
                and all(p in row['exact_intersection_points_m'] for p in row['outside_shared_simplex_m']),
                'Lower-LOD excluded witness requires finite actual intersection points outside the shared simplex')
        triangles = row.get('actual_triangles_m')
        require(isinstance(triangles, list) and len(triangles) == 2
                and all(points(triangle) and len(triangle) == 3 for triangle in triangles),
                'Lower-LOD excluded witness actual triangles missing or nonfinite')


def tetra():
    return {'name': 'LOD1_Tetra', 'vertices': [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            'triangles': [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]}


def join(a, b):
    return {'name': 'LOD1_Joined', 'vertices': a['vertices'] + b['vertices'],
            'triangles': a['triangles'] + [[index + len(a['vertices']) for index in face] for face in b['triangles']]}


def geometry_fixtures():
    base = tetra()
    other = copy.deepcopy(base)
    other['vertices'] = [[.2 + .8 * value for value in point] for point in other['vertices']]
    crossing = join(base, other)
    coincident = join(base, base)
    indexed = copy.deepcopy(crossing)
    indexed['triangles'] = [[0 if i == 4 else i for i in face] for face in indexed['triangles']]
    cube = {'name': 'LOD1_Cube', 'vertices': [[-1., -1., -1.], [1., -1., -1.], [1., 1., -1.], [-1., 1., -1.],
            [-1., -1., 1.], [1., -1., 1.], [1., 1., 1.], [-1., 1., 1.]],
            'triangles': [[0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                          [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]}
    folded = copy.deepcopy(cube); folded['vertices'][6] = [-2., .5, .5]
    opened = copy.deepcopy(base); opened['triangles'].pop()
    winding = copy.deepcopy(base); winding['triangles'][0].reverse()
    reverse = copy.deepcopy(base); reverse['triangles'] = [face[::-1] for face in reverse['triangles']]
    duplicate = {'name': 'LOD1_Duplicate', 'vertices': base['vertices'][:3], 'triangles': [[0, 1, 2], [2, 1, 0]]}
    return {'tetra': base, 'cube': cube, 'crossing': crossing, 'coincident': coincident, 'indexed': indexed,
            'folded': folded, 'opened': opened, 'winding': winding, 'reverse': reverse, 'duplicate': duplicate}


def native(args):
    import bpy
    import lod_self_intersections as target
    require((bpy.app.version_string, bpy.app.build_hash.decode()) == PIN, 'Pinned Blender required')
    source_hash = sha(args.source)
    args.output.mkdir(parents=True, exist_ok=False)
    rows, controls, native_rows = geometry_fixtures(), [], {}
    def passed(name, **detail):
        controls.append({'name': name, 'status': 'passed', **detail})
    def actual_mesh(row, name):
        data = bpy.data.meshes.new(name)
        data.from_pydata(row['vertices'], [], row['triangles']); data.update(); data.calc_loop_triangles()
        return data, {'name': name, 'vertices': [list(v.co) for v in data.vertices],
                      'triangles': [list(t.vertices) for t in data.loop_triangles]}
    for name, row in rows.items():
        data, native_row = actual_mesh(row, 'LOD1_Control_' + name)
        native_rows[name] = native_row
        bpy.data.meshes.remove(data)
    partitions = []
    for name, expected in (('tetra', 1), ('cube', 1), ('crossing', 2), ('coincident', 2), ('indexed', 1), ('folded', 1)):
        row = native_rows[name]
        groups = target.partition(row)
        flat = [i for group in groups for i in group]
        require(len(groups) == expected and sorted(flat) == list(range(len(row['triangles'])))
                and len(flat) == len(set(flat)), 'Native partition triangle coverage mismatch')
        # Independent graph walk over shared original vertex indices.
        remaining, independent = set(range(len(row['triangles']))), []
        while remaining:
            todo, found = [min(remaining)], set()
            while todo:
                current = todo.pop()
                if current in found: continue
                found.add(current); remaining.discard(current)
                current_vertices = set(row['triangles'][current])
                todo += [i for i in sorted(remaining) if current_vertices.intersection(row['triangles'][i])]
            independent.append(sorted(found))
        require(groups == independent, 'Union-find differs from independent graph enumeration')
        partitions.append({'mesh': name, 'groups': groups, 'triangles': len(flat)})
    passed(NATIVE_NAMES[0], actual=partitions)
    crossing = target.shell_certificate(native_rows['crossing'])
    require(crossing['status'] == 'passed' and crossing['shell_count'] == 2
            and crossing['excluded_cross_shell_candidates'] > 0, 'Disconnected candidate exclusion incorrect')
    witnesses = [target.self_geometry.exact_pair(native_rows['crossing'], a, b) for a in range(4) for b in range(4, 8)]
    hits = [row for row in witnesses if row['outside_shared_simplex_m']]
    require(bool(hits), 'Fixture must contain actual excluded cross-shell intersections')
    passed(NATIVE_NAMES[1], certificate=crossing, excluded_actual_crossing_pairs=hits,
           scope='These cross-shell intersections are unassessed, never accepted fit')
    coincident = target.shell_certificate(native_rows['coincident'])
    require(coincident['status'] == 'passed' and coincident['shell_count'] == 2
            and coincident['excluded_cross_shell_candidates'] == 16, 'Coincident separate indices were welded')
    passed(NATIVE_NAMES[2], certificate=coincident)
    folded = target.shell_certificate(native_rows['folded'])
    require(folded['status'] == 'failed' and folded['shell_count'] == 1
            and folded['shells'][0]['bad_pairs'], 'Closed connected fold was not rejected')
    passed(NATIVE_NAMES[3], certificate=folded)
    indexed = target.shell_certificate(native_rows['indexed'])
    require(indexed['status'] == 'failed' and indexed['shell_count'] == 1
            and indexed['excluded_cross_shell_candidates'] == 0, 'Shared actual index incorrectly separates shells')
    passed(NATIVE_NAMES[4], certificate=indexed)
    topology = []
    for name, expected in (('tetra', None), ('cube', None), ('reverse', None), ('opened', 'not closed'),
                           ('winding', 'Inconsistent shell winding'), ('duplicate', 'Duplicate final')):
        try:
            proof = target.shell_certificate(native_rows[name])
        except ValueError as error:
            require(expected and expected in str(error), 'Unexpected topology rejection: ' + name)
            topology.append({'case': name, 'rejection': str(error)})
        else:
            require(expected is None and proof['status'] == 'passed', 'Invalid topology accepted: ' + name)
            topology.append({'case': name, 'status': 'passed'})
    passed(NATIVE_NAMES[5], cases=topology, limitation='Global winding reversal is consistent; outward volume is a separate contract')
    invalid = []
    for name, key, value in (('empty-vertices', 'vertices', []), ('empty-triangles', 'triangles', []),
                             ('negative-index', 'triangles', [[-1, 1, 2]]), ('boolean-index', 'triangles', [[False, 1, 2]]),
                             ('float-index', 'triangles', [[0., 1, 2]]), ('overflow-index', 'triangles', [[0, 1, 4]]),
                             ('repeated-index', 'triangles', [[0, 0, 2]]),
                             ('nan', 'vertices', [[math.nan, 0., 0.]] * 4),
                             ('infinity', 'vertices', [[math.inf, 0., 0.]] * 4),
                             ('degenerate', 'vertices', [[0., 0., 0.]] * 4)):
        row = copy.deepcopy(native_rows['tetra']); row[key] = value
        try:
            target.shell_certificate(row)
        except ValueError as error:
            invalid.append({'case': name, 'rejection': str(error)})
        else:
            raise ValueError('Invalid row accepted: ' + name)
    passed(NATIVE_NAMES[6], cases=invalid, scope='Deliberate in-memory domain mutations of a native extracted mesh')
    original = target.partition
    try:
        groups = original(native_rows['crossing'])
        target.partition = lambda row: [groups[0], *groups]
        try:
            target.shell_certificate(native_rows['crossing'])
        except ValueError as error:
            require('partition is incomplete' in str(error), 'Unexpected partition corruption rejection')
            passed(NATIVE_NAMES[7], rejection=str(error), injection='Duplicate complete shell group in controlled function override')
        else:
            raise ValueError('Duplicate partition coverage accepted')
    finally:
        target.partition = original
    require([row['name'] for row in controls] == list(NATIVE_NAMES), 'Native algorithm inventory incomplete')
    saved = []
    for case in CASES:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if case != 'missing-asset':
            collection = bpy.data.collections.new('Asset'); bpy.context.scene.collection.children.link(collection)
            for lod in (1, 2):
                if case == 'no-lods' or case == f'empty-lod{lod}': continue
                selected = {'folded': 'folded', 'disconnected-crossing': 'crossing', 'open-shell': 'opened',
                            'inconsistent-winding': 'winding', 'duplicate-face': 'duplicate'}.get(case, 'tetra') if lod == 1 else 'tetra'
                data, _ = actual_mesh(rows[selected], f'LOD{lod}_Fixture')
                if case == 'empty-mesh' and lod == 1:
                    bpy.data.meshes.remove(data); data = bpy.data.meshes.new('Empty')
                obj = bpy.data.objects.new(f'LOD{lod}_Fixture', data); collection.objects.link(obj)
        path = args.output / (case + '.blend')
        bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False)
        saved.append({'case': case, **file_row(path)})
    result = {'status': 'passed', 'source_sha256': source_hash, 'source_unchanged': sha(args.source) == source_hash,
              'blender_version': PIN[0], 'blender_build': PIN[1], 'python': sys.version,
              'native_meshes': native_rows, 'controls': controls, 'fixtures': saved,
              'scope': 'Temporary factory-scene fixtures only; supplied production source was hashed but never opened or changed'}
    require(result['source_unchanged'], 'Locked source changed')
    write(args.report, result)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--native-fixtures', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None)
    if args.native_fixtures: return native(args)
    if args.blender is None: parser.error('--blender is required')
    args.source, args.blender = args.source.resolve(strict=True), args.blender.resolve(strict=True)
    args.output, args.report = args.output.resolve(), args.report.resolve()
    scripts = Path(__file__).resolve().parent
    if args.output.exists() or args.report.exists() or args.output.is_relative_to(scripts) or scripts.is_relative_to(args.output):
        parser.error('Choose fresh paths outside the QA tool tree')
    if any(path.is_relative_to(args.output) for path in (args.source, args.blender)):
        parser.error('Output cannot contain a locked source or executable')
    args.output.mkdir(parents=True); args.report.parent.mkdir(parents=True, exist_ok=True)
    command_dir = args.output / 'commands'; command_dir.mkdir()
    import gate
    inputs = [file_row(path) for path in (args.source, args.blender, Path(__file__),
              *[scripts / name for name in ('lod_self_intersections.py', 'self_intersections.py',
                                            'self_geometry.py', 'exact_triangles.py', 'gate.py')])]
    record = {'task_id': 'P1-018', 'milestone': 'M5', 'status': 'running', 'source_sha256': sha(args.source),
              'start_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
              'human_approval_reference': None, 'inputs': inputs, 'commands': [], 'controls': [],
              'expected_controls': len(EXPECTED_NAMES), 'completed_controls': 0,
              'expected_control_names': list(EXPECTED_NAMES),
              'scope': 'Connected-shell topology/self-check controls. Cross-shell fit remains explicitly unassessed; no model/runtime/performance approval.'}
    write(args.report, record)
    env = {**os.environ, 'BLENDER_USER_CONFIG': str(args.output / 'config'),
           'BLENDER_USER_SCRIPTS': str(args.output / 'scripts'), 'PYTHONDONTWRITEBYTECODE': '1'}
    def command(name, script, arguments, output, expected):
        prefix = command_dir / f'{len(record["commands"]) + 1:02d}-{name}'
        argv = [str(args.blender), '--background', '--factory-startup', '--python-exit-code', '1',
                '--python', str(script), '--', *map(str, arguments)]
        begin = time.monotonic(); row = {'name': name, 'argv': argv, 'cwd': str(args.output),
                'start_utc': datetime.now(timezone.utc).isoformat(), 'timeout_seconds': 120,
                'environment': {k: env[k] for k in ('BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS', 'PYTHONDONTWRITEBYTECODE')}}
        try:
            process = subprocess.run(argv, cwd=args.output, env=env, capture_output=True, timeout=120, shell=False)
            code, stdout, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr = 124, error.stdout or b'', error.stderr or b''; row['timeout'] = True
        prefix.with_suffix('.stdout.log').write_bytes(stdout); prefix.with_suffix('.stderr.log').write_bytes(stderr)
        failure = None
        try:
            require(code == expected, f'{name}: expected exit{expected}, actual{code}')
            gate.positive_process(0, (stdout + b'\n' + stderr).decode('utf8', errors='replace'))
            require(output.is_file(), 'Native report missing: ' + name)
            row['status'] = 'passed'
        except Exception as error:
            failure = error; row.update(status='failed', failure=str(error))
        row.update(exit_status=code, expected_exit=expected, elapsed_seconds=time.monotonic() - begin,
                   outputs=[file_row(p) for p in (output, prefix.with_suffix('.stdout.log'), prefix.with_suffix('.stderr.log')) if p.is_file()])
        write(prefix.with_suffix('.json'), row)
        record['commands'].append({**file_row(prefix.with_suffix('.json')), 'name': name, 'status': row['status'],
                                   'exit_status': code, 'expected_exit': expected})
        print(json.dumps({'control': name, 'exit': code, 'status': row['status']}), flush=True)
        if failure: raise failure
        return gate.json_read(output)
    try:
        output = args.output / 'native-fixtures.json'
        native_report = command('native-fixtures', Path(__file__), ['--native-fixtures', '--source', args.source,
                                '--output', args.output / 'fixtures', '--report', output], output, 0)
        require(native_report['status'] == 'passed' and native_report['source_sha256'] == record['source_sha256']
                and native_report['source_unchanged'], 'Native fixture/source binding mismatch')
        require([row['name'] for row in native_report['controls']] == list(NATIVE_NAMES)
                and all(row['status'] == 'passed' for row in native_report['controls'])
                and [row['case'] for row in native_report['fixtures']] == list(CASES), 'Native fixture inventory incomplete')
        record['controls'] += native_report['controls']
        for fixture in native_report['fixtures']:
            case, source = fixture['case'], Path(fixture['path'])
            require(sha(source) == fixture['sha256'], 'Native saved fixture changed')
            expected = 0 if case in ('positive', 'disconnected-crossing') else 1
            output = args.output / ('cli-' + case + '.json')
            actual = command('native-cli-' + case, scripts / 'lod_self_intersections.py',
                             ['--source', source, '--output', output], output, expected)
            require(actual['source_sha256'] == fixture['sha256'] and actual['source_unchanged'], 'CLI actual saved-source binding differs')
            require(actual['status'] == ('passed' if expected == 0 else 'failed'), 'CLI rejection status mismatch')
            if case == 'positive':
                require(actual['lod_mesh_counts'] == {'1': 1, '2': 1} and actual['shell_count'] == 2
                        and actual['triangle_count'] == 8 and actual['excluded_cross_shell_candidates'] == 0,
                        'Positive final-LOD native extraction incomplete')
            elif case == 'disconnected-crossing':
                require(actual['shell_count'] == 3 and actual['excluded_cross_shell_candidates'] > 0,
                        'Excluded cross-shell domain not reported')
            elif case == 'folded':
                require(any(row['status'] == 'failed' and any(shell['bad_pairs'] for shell in row['shells']) for row in actual['rows']),
                        'Folded native mesh did not reject actual self intersections')
            else:
                reason = {'empty-lod1': 'Both final lower LODs', 'empty-lod2': 'Both final lower LODs',
                          'no-lods': 'Both final lower LODs', 'empty-mesh': 'Nonempty vertex array',
                          'open-shell': 'not closed', 'inconsistent-winding': 'Inconsistent shell winding',
                          'duplicate-face': 'Duplicate final', 'missing-asset': 'Asset'}[case]
                require(reason in actual.get('failure', ''), 'Native negative failed for an unintended reason')
            record['controls'].append({'name': 'native-cli-' + case, 'status': 'passed', 'fixture': fixture,
                                       'report': file_row(output), 'native_exit': expected})
        probe = copy.deepcopy(record)
        probe['controls'].append({'name': 'report-negative-controls', 'status': 'passed'})
        probe.update(status='passed', completed_controls=len(EXPECTED_NAMES), source_unchanged=True,
                     inputs_unchanged=True, outputs=[file_row(args.output / 'native-fixtures.json')])
        validate_report(probe, record['source_sha256'])
        negatives = []
        for kind in ('missing-row', 'duplicate-row', 'failed-row', 'float-count', 'missing-command', 'missing-hash', 'wrong-source',
                     'empty-partitions', 'missing-partition', 'duplicate-partition-index', 'boolean-partition-index',
                     'float-partition-count', 'missing-crossing-certificate', 'wrong-excluded-count', 'missing-shell',
                     'empty-crossing-witnesses', 'missing-crossing-witness', 'duplicate-crossing-pair',
                     'empty-outside-points', 'nonfinite-witness-point', 'missing-actual-triangle'):
            changed = copy.deepcopy(probe)
            if kind == 'missing-row': changed['controls'].pop()
            elif kind == 'duplicate-row': changed['controls'][-1] = changed['controls'][0]
            elif kind == 'failed-row': changed['controls'][0]['status'] = 'failed'
            elif kind == 'float-count': changed['completed_controls'] = float(len(EXPECTED_NAMES))
            elif kind == 'missing-command': changed['commands'].pop()
            elif kind == 'missing-hash': changed['outputs'][0].pop('sha256')
            elif kind == 'wrong-source': changed['source_sha256'] = '0' * 64
            elif kind == 'empty-partitions':
                changed['controls'][0]['actual'] = []
            elif kind == 'missing-partition':
                changed['controls'][0]['actual'].pop()
            elif kind == 'duplicate-partition-index':
                changed['controls'][0]['actual'][0]['groups'][0][-1] = 0
            elif kind == 'boolean-partition-index':
                changed['controls'][0]['actual'][0]['groups'][0][0] = False
            elif kind == 'float-partition-count':
                changed['controls'][0]['actual'][0]['triangles'] = 4.0
            elif kind == 'missing-crossing-certificate':
                changed['controls'][1].pop('certificate')
            elif kind == 'wrong-excluded-count':
                changed['controls'][1]['certificate']['excluded_cross_shell_candidates'] = 0
            elif kind == 'missing-shell':
                changed['controls'][1]['certificate']['shells'].pop()
            elif kind == 'empty-crossing-witnesses':
                changed['controls'][1]['excluded_actual_crossing_pairs'] = []
            elif kind == 'missing-crossing-witness':
                changed['controls'][1]['excluded_actual_crossing_pairs'].pop()
            elif kind == 'duplicate-crossing-pair':
                changed['controls'][1]['excluded_actual_crossing_pairs'][1]['triangles'] = [3, 4]
            elif kind == 'empty-outside-points':
                changed['controls'][1]['excluded_actual_crossing_pairs'][0]['outside_shared_simplex_m'] = []
            elif kind == 'nonfinite-witness-point':
                changed['controls'][1]['excluded_actual_crossing_pairs'][0]['outside_shared_simplex_m'][0][0] = math.nan
            else:
                changed['controls'][1]['excluded_actual_crossing_pairs'][0]['actual_triangles_m'].pop()
            try: validate_report(changed, record['source_sha256'])
            except ValueError as error: negatives.append({'case': kind, 'rejection': str(error)})
            else: raise ValueError('Malformed lower-LOD control report accepted: ' + kind)
        record['controls'].append({'name': 'report-negative-controls', 'status': 'passed', 'cases': negatives})
        record.update(status='passed', completed_controls=len(record['controls']))
    except Exception as error:
        record.update(status='failed', failure=type(error).__name__ + ': ' + str(error), completed_controls=len(record['controls']))
    finally:
        record.update(end_utc=datetime.now(timezone.utc).isoformat(), source_unchanged=sha(args.source) == record['source_sha256'],
                      inputs_unchanged=all(Path(r['path']).is_file() and sha(r['path']) == r['sha256'] for r in inputs),
                      outputs=[file_row(path) for path in sorted(args.output.rglob('*')) if path.is_file() and path != args.report])
        if record['status'] == 'passed':
            try: validate_report(record, record['source_sha256'])
            except Exception as error: record.update(status='failed', failure=str(error))
        write(args.report, record)
    print(json.dumps({'status': record['status'], 'completed_controls': record['completed_controls'],
                      'expected_controls': record['expected_controls']}), flush=True)
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
