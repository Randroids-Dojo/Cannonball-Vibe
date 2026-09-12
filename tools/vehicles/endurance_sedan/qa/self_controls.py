"""Run pinned-Blender rejection and exhaustive self-intersection controls.

Constructed predicates, native temporary meshes and deliberately malformed JSON
are verification fixtures. They never replace the full authored-source scan.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys
import time


PIN = ('5.1.2', 'ec6e62d40fa9')
SEED = 35128
ACTUAL_MESHES = ('LOD0_PillarA_L', 'LOD0_PillarA_R', 'LOD0_FDamper_-1',
                 'LOD0_HeadlightSideReturn_L1', 'LOD0_DoorLatch_FL',
                 'LOD0_BrakeDuctInterior_L', 'LOD0_FrontBeltRelease_-1')
ALGORITHM_NAMES = ('exact-predicate-18-fixtures-648-permutations',
                   'aabb-260-triangles-33670-exhaustive-pairs',
                   'seed35128-504-exhaustive-pairs',
                   'native-mesh-loop-triangle-controls',
                   'actual-source-seven-mesh-rational-replay')
ALGORITHM_COUNTS = (18, 33670, 504, 4, 7)
CLI_NAMES = ('cli-valid', 'cli-crossing', 'cli-shared-edge', 'cli-source-mismatch',
             'cli-empty-inventory', 'cli-payload-type', 'cli-empty-vertices',
             'cli-empty-triangles', 'cli-negative-index', 'cli-boolean-index',
             'cli-float-index', 'cli-out-of-range-index', 'cli-repeated-index',
             'cli-nested-index', 'cli-name-mismatch', 'cli-nonfinite-nan',
             'cli-nonfinite-infinity', 'cli-boolean-coordinate', 'cli-short-coordinate',
             'cli-degenerate', 'cli-area-at-limit', 'cli-area-below-limit',
             'cli-area-above-limit', 'cli-duplicate-json-key', 'cli-invalid-gzip',
             'cli-preview-exclusion', 'cli-truthy-preview-not-excluded',
             'cli-lower-lod-only', 'cli-empty-prefix', 'cli-unmatched-prefix',
             'cli-source-extension', 'cli-no-overwrite', 'cli-source-mutated',
             'cli-geometry-mutated', 'cli-pinned-metadata-rejection')
EXTRA_NAMES = ('three-native-process-deterministic-core', 'actual-source-cli-pair',
               'report-inventory-negative-controls')
EXPECTED_NAMES = ALGORITHM_NAMES + CLI_NAMES + EXTRA_NAMES
COMMAND_NAMES = ('native-controls',) + CLI_NAMES + ('native-core-1', 'native-core-9013', 'actual-source-cli-pair')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n',
                          encoding='utf8', newline='\n')


def file_row(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_report(report, source_sha):
    """Reject omitted/duplicated controls or unbound native command inventories."""
    require(isinstance(report, dict), 'Self control report must be an object')
    require(report.get('status') == 'passed' and report.get('source_sha256') == source_sha,
            'Self controls are failed or source binding differs')
    require(report.get('human_approval_reference') is None,
            'Self controls cannot introduce human approval')
    require(type(report.get('expected_controls')) is int and type(report.get('completed_controls')) is int
            and report['expected_controls'] == report['completed_controls'] == len(EXPECTED_NAMES),
            'Self control count is incomplete')
    require(report.get('expected_control_names') == list(EXPECTED_NAMES),
            'Self control declaration differs')
    rows = report.get('controls')
    require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
            and [r.get('name') for r in rows] == list(EXPECTED_NAMES)
            and all(r.get('status') == 'passed' for r in rows),
            'Self control rows are missing, duplicated, reordered or failed')
    require(report.get('inputs_unchanged') is True and report.get('source_unchanged') is True,
            'Self control inputs changed')
    for field in ('inputs', 'outputs', 'commands'):
        require(isinstance(report.get(field), list) and bool(report[field]),
                'Self controls have no ' + field)
        require(all(isinstance(r, dict) and isinstance(r.get('path'), str) and r['path']
                    and isinstance(r.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', r['sha256'])
                    and type(r.get('bytes')) is int and r['bytes'] >= 0 for r in report[field]),
                'Self controls contain an invalid ' + field + ' file binding')
    require([r.get('name') for r in report['commands']] == list(COMMAND_NAMES)
            and all(r.get('status') == 'passed' and type(r.get('exit_status')) is int
                    and type(r.get('expected_exit')) is int
                    and r['exit_status'] == r.get('expected_exit') for r in report['commands']),
            'Self control native command inventory is missing, reordered or failed')
    # The name/status inventory does not establish that the declared numerical
    # fixture scope was exercised. Bind all five measurements to their retained
    # native report; outer file verification remains responsible for its bytes.
    native_report = rows[0].get('report')
    require(isinstance(native_report, dict) and native_report in report['outputs'],
            'Self algorithm detail is not bound to a retained native output')
    for row, expected in zip(rows[:len(ALGORITHM_NAMES)], ALGORITHM_COUNTS):
        require(type(row.get('count')) is int and row['count'] == expected,
                'Self algorithm measured fixture count is absent or differs: ' + row['name'])
        require(row.get('report') == native_report,
                'Self algorithm measurements refer to different or absent native outputs')


def mesh(name, vertices, triangles, properties=None):
    return {'name': name, 'vertices': vertices, 'triangles': triangles,
            'properties': properties or {}}


def fixtures():
    a = [[0., 0., 0.], [2., 0., 0.], [0., 2., 0.]]
    def separate(name, b):
        return mesh(name, a + b, [[0, 1, 2], [3, 4, 5]])
    rows = [
        (mesh('shared_edge_only', a + [[0., -2., 0.]], [[0, 1, 2], [1, 0, 3]]), False),
        (mesh('shared_edge_nonplanar_only', a + [[0., 0., 2.]], [[0, 1, 2], [1, 0, 3]]), False),
        (mesh('shared_edge_extra_area', a + [[.2, .2, 0.]], [[0, 1, 2], [0, 1, 3]]), True),
        (mesh('shared_point_only', a + [[-.5, -.5, 1.], [1., 0., 1.]], [[0, 1, 2], [0, 3, 4]]), False),
        (mesh('shared_point_crossing', a + [[.5, .5, -1.], [.5, .5, 1.]], [[0, 1, 2], [0, 3, 4]]), True),
        (separate('unindexed_coordinate_touch', [[2., 0., 0.], [3., 0., 0.], [2., -1., 0.]]), True),
        (separate('unindexed_coplanar_area', [[.25, .25, 0.], [1., .25, 0.], [.25, 1., 0.]]), True),
        (separate('unindexed_crossing', [[.5, .5, -1.], [.5, .5, 1.], [1., .5, 0.]]), True),
        (separate('sub_eps_parallel_separation', [[x, y, 1e-10] for x, y, _ in a]), False),
        (separate('coplanar_bbox_overlap_separated', [[1.5, 1.5, 0.], [2.5, 1.5, 0.], [1.5, 2.5, 0.]]), False),
        (mesh('duplicate_face', a, [[0, 1, 2], [0, 1, 2]]), True),
        (mesh('opposing_duplicate', a, [[0, 1, 2], [2, 1, 0]]), True),
    ]
    for label, amount, bad in (('below', math.nextafter(1e-6, 0), False),
                               ('equal', 1e-6, False),
                               ('above', math.nextafter(1e-6, math.inf), True)):
        rows += [(mesh('indexed_point_guard_' + label, a + [[amount, 0., -1.], [amount, 0., 1.]],
                       [[0, 1, 2], [0, 3, 4]]), bad),
                 (mesh('indexed_edge_guard_' + label, a + [[1., amount, 0.]],
                       [[0, 1, 2], [0, 1, 3]]), bad)]
    return rows


def algorithm_controls():
    import self_geometry as geometry
    exact = geometry.exact
    declared = fixtures()
    predicate = []
    for row, expected in declared:
        full, fast = geometry.scan(row, validate=True), geometry.scan(row)
        require(full['bad_pairs'] == fast['bad_pairs'] and bool(fast['bad_pairs']) == expected,
                'Predicate mismatch: ' + row['name'])
        a, b = [[row['vertices'][i] for i in face] for face in row['triangles']]
        baseline = set(exact.intersection(a, b))
        for aa, bb in itertools.product(itertools.permutations(a), itertools.permutations(b)):
            require(set(exact.intersection(aa, bb)) == baseline
                    and set(exact.intersection(bb, aa)) == baseline,
                    'Vertex order or triangle swap changes exact predicate')
        predicate.append({'name': row['name'], 'expected_bad': expected, 'actual': fast,
                          'permutations': 36, 'swapped_pair_checked': True})
    vertices, faces = [], []
    for index in range(260):
        x = 0. if index in (0, 127, 128, 255, 256, 259) else float(index * 4)
        faces.append(list(range(len(vertices), len(vertices) + 3)))
        vertices += [[x, 0., 0.], [x + 1., 0., 0.], [x, 1., 0.]]
    boundary = mesh('block_boundaries260', vertices, faces)
    expected_pairs = []
    for ai, bi in itertools.combinations(range(260), 2):
        a, b = [[vertices[i] for i in face] for face in (faces[ai], faces[bi])]
        if all(max(p[k] for p in a) >= min(p[k] for p in b) - 1e-9
               and max(p[k] for p in b) >= min(p[k] for p in a) - 1e-9 for k in range(3)):
            expected_pairs.append((ai, bi))
    require(len(expected_pairs) == 15 and geometry.candidates(boundary) == expected_pairs,
            'Vectorized128-row enumeration differs from complete scalar enumeration')
    rng, random_rows = random.Random(SEED), []
    for sample in range(18):
        vertices, faces = [], []
        while len(faces) < 8:
            points = [[rng.randrange(-8, 9) / 8 for _ in range(3)] for _ in range(3)]
            if exact.cross(exact.sub(points[1], points[0]), exact.sub(points[2], points[0])) == (0, 0, 0):
                continue
            faces.append(list(range(len(vertices), len(vertices) + 3)))
            vertices += points
        row = mesh(f'seed{SEED}_{sample}', vertices, faces)
        all_bad = [hit for ai, bi in itertools.combinations(range(8), 2)
                   if (hit := geometry.exact_pair(row, ai, bi))['outside_shared_simplex_m']]
        replay, fast = geometry.scan(row, validate=True), geometry.scan(row)
        require(replay['bad_pairs'] == fast['bad_pairs'] == all_bad,
                'Broad phase or integer prefilter missed an exhaustive exact hit')
        random_rows.append({'sample': sample, 'all_pairs': 28, 'mesh': row, 'actual': fast})
    return {'predicate_fixtures': [{'mesh': row, 'expected_bad': bad} for row, bad in declared],
            'predicates': predicate, 'block_boundary': {'mesh': boundary, 'all_pairs': 33670,
            'expected_candidates': expected_pairs}, 'random_rows': random_rows,
            'seed': SEED, 'guard_m': 1e-6, 'aabb_padding_m': 1e-9,
            'semantics': 'Exact binary inputs;1um exemption only around shared indexed simplex. '
                         'Broad-phase padding is not a contact or clearance tolerance.'}


def native_main(args):
    import bpy
    import self_geometry as geometry
    import self_intersections as driver
    require((bpy.app.version_string, bpy.app.build_hash.decode()) == PIN, 'Pinned Blender required')
    if args.native_mode in ('source-mutated', 'geometry-mutated', 'wrong-pin'):
        target = args.source if args.native_mode == 'source-mutated' else args.geometry
        original = geometry.scan
        def changed(row, *positional, **kwargs):
            found = original(row, *positional, **kwargs)
            with target.open('ab') as stream:
                stream.write(b'\nQA_INPUT_MUTATION\n')
            return found
        if args.native_mode == 'wrong-pin':
            from types import SimpleNamespace
            # Deliberate metadata-only negative, inside the already verified real
            # pinned engine. This does not claim execution of a different engine.
            driver.bpy = SimpleNamespace(app=SimpleNamespace(version_string='0.0.0', build_hash=b'wrong'))
        else:
            geometry.scan = changed
        return driver.main(['--source', str(args.source), '--geometry', str(args.geometry),
                            '--output', str(args.report)])
    source_hash = sha(args.source)
    before = {str(p): sha(p) for p in (args.source, args.geometry, Path(__file__),
              Path(geometry.__file__), Path(geometry.exact.__file__), Path(driver.__file__))}
    core = algorithm_controls()
    core_bytes = json.dumps(core, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    result = {'status': 'passed', 'source_sha256': source_hash, 'core': core,
              'core_sha256': hashlib.sha256(core_bytes).hexdigest(), 'blender_version': PIN[0],
              'blender_build': PIN[1], 'numpy': geometry.np.__version__, 'python': sys.version,
              'hash_seed': os.environ.get('PYTHONHASHSEED'), 'native_meshes': [], 'actual_meshes': []}
    if args.native_mode == 'all':
        for fixture, bad in [fixtures()[i] for i in (0, 7, 10, 11)]:
            data = bpy.data.meshes.new('SelfControl_' + fixture['name'])
            try:
                data.from_pydata(fixture['vertices'], [], fixture['triangles'])
                data.update(); data.calc_loop_triangles()
                row = mesh('LOD0_Native_' + fixture['name'], [list(v.co) for v in data.vertices],
                           [list(t.vertices) for t in data.loop_triangles])
                driver.validate_row(row['name'], row)
                scan = geometry.scan(row, validate=True)
                require(bool(scan['bad_pairs']) == bad, 'Native Mesh fixture mismatch')
                result['native_meshes'].append({'expected_bad': bad, 'mesh': row, 'actual': scan})
            finally:
                bpy.data.meshes.remove(data)
        payload = driver.strict_json(gzip.decompress(args.geometry.read_bytes()))
        require(payload['source_sha256'] == source_hash, 'Actual extraction source mismatch')
        for name in ACTUAL_MESHES:
            row = payload['meshes'][name]
            driver.validate_row(name, row)
            replay, fast = geometry.scan(row, validate=True), geometry.scan(row)
            require(replay['bad_pairs'] == fast['bad_pairs'], 'Actual-mesh prefilter mismatch')
            result['actual_meshes'].append({'name': name, 'every_candidate_rationally_replayed': True,
                                          'actual': replay, 'fast_rational_calls': fast['rational_pair_calls']})
    result['inputs_unchanged'] = all(sha(p) == digest for p, digest in before.items())
    require(result['inputs_unchanged'], 'Native control input changed')
    write(args.report, result)
    print(json.dumps({'status': 'passed', 'mode': args.native_mode, 'core_sha256': result['core_sha256']}), flush=True)
    return 0


def cli_cases(source_hash):
    good = mesh('LOD0_Valid', [[0., 0., 0.], [2., 0., 0.], [0., 2., 0.]], [[0, 1, 2]])
    payload = {'source_sha256': source_hash, 'meshes': {good['name']: good}}
    cases = []
    def add(name, changed=None, failure=None, **extra):
        cases.append({'name': name, 'payload': copy.deepcopy(payload if changed is None else changed),
                      'failure': failure, **extra})
    def row_case(name, field, value, failure):
        changed = copy.deepcopy(payload); changed['meshes']['LOD0_Valid'][field] = value
        add(name, changed, failure)
    add('cli-valid')
    for name, index in (('cli-crossing', 7), ('cli-shared-edge', 0)):
        fixture = copy.deepcopy(fixtures()[index][0]); fixture['name'] = 'LOD0_Valid'
        add(name, {'source_sha256': source_hash, 'meshes': {'LOD0_Valid': fixture}},
            crossing=name == 'cli-crossing')
    add('cli-source-mismatch', {**payload, 'source_sha256': '0' * 64}, 'not bound')
    add('cli-empty-inventory', {**payload, 'meshes': {}}, 'Nonempty mesh inventory')
    add('cli-payload-type', [], 'not bound')
    row_case('cli-empty-vertices', 'vertices', [], 'Nonempty vertex array')
    row_case('cli-empty-triangles', 'triangles', [], 'Nonempty triangle array')
    for name, face in (('negative', [-3, -2, -1]), ('boolean', [False, True, 2]),
                       ('float', [0., 1., 2.]), ('out-of-range', [0, 1, 3]),
                       ('repeated', [0, 0, 2]), ('nested', [[0], 1, 2])):
        row_case('cli-' + name + '-index', 'triangles', [face],
                 'unhashable' if name == 'nested' else 'Invalid triangle indices')
    row_case('cli-name-mismatch', 'name', 'LOD0_Wrong', 'name/key mismatch')
    for name, value in (('nan', math.nan), ('infinity', math.inf)):
        row_case('cli-nonfinite-' + name, 'vertices', [[value, 0., 0.], [1., 0., 0.], [0., 1., 0.]], 'Nonfinite JSON')
    row_case('cli-boolean-coordinate', 'vertices', [[False, 0., 0.], [1., 0., 0.], [0., 1., 0.]], 'Invalid finite3D')
    row_case('cli-short-coordinate', 'vertices', [[0., 0.], [1., 0., 0.], [0., 1., 0.]], 'Invalid finite3D')
    row_case('cli-degenerate', 'vertices', [[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]], 'Degenerate')
    for label, height, error in (('at', 2e-12, 'Degenerate'),
                                  ('below', math.nextafter(2e-12, 0), 'Degenerate'),
                                  ('above', math.nextafter(2e-12, math.inf), None)):
        row_case('cli-area-' + label + '-limit', 'vertices',
                 [[0., 0., 0.], [1., 0., 0.], [0., height, 0.]], error)
    add('cli-duplicate-json-key', failure='Duplicate JSON key', duplicate_key=True)
    add('cli-invalid-gzip', failure='Not a gzipped file', invalid_gzip=True)
    preview = copy.deepcopy(fixtures()[7][0]); preview['name'] = 'LOD0_Preview'
    preview['properties'] = {'source_preview_only': True}
    add('cli-preview-exclusion', {**payload, 'meshes': {'LOD0_Valid': good, 'LOD0_Preview': preview}}, preview=True)
    preview = copy.deepcopy(preview); preview['properties']['source_preview_only'] = 1
    add('cli-truthy-preview-not-excluded', {**payload, 'meshes': {'LOD0_Valid': good, 'LOD0_Preview': preview}}, crossing=True)
    lower = copy.deepcopy(good); lower['name'] = 'LOD1_Only'
    add('cli-lower-lod-only', {**payload, 'meshes': {'LOD1_Only': lower}}, 'No eligible original LOD0')
    add('cli-empty-prefix', failure='Requested mesh prefix did not match', includes=[''])
    add('cli-unmatched-prefix', failure='Requested mesh prefix did not match', includes=['LOD0_Valid', 'LOD0_Missing'])
    add('cli-source-extension', failure='Editable .blend source required', extension=True)
    add('cli-no-overwrite', overwrite=True)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--native-mode', choices=('all', 'core', 'source-mutated', 'geometry-mutated', 'wrong-pin'))
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None)
    if args.native_mode:
        return native_main(args)
    if args.blender is None or args.output is None:
        parser.error('--blender and --output are required for the control runner')
    for name in ('source', 'geometry', 'blender'):
        setattr(args, name, getattr(args, name).resolve(strict=True))
    args.output, args.report = args.output.resolve(), args.report.resolve()
    scripts = Path(__file__).resolve().parent
    if args.output.exists() or args.report.exists() or args.output.is_relative_to(scripts) or scripts.is_relative_to(args.output):
        parser.error('Choose fresh control output/report paths outside the QA source tree')
    if any(p.is_relative_to(args.output) for p in (args.source, args.geometry, args.blender)):
        parser.error('Output cannot contain locked inputs')
    args.output.mkdir(parents=True); args.report.parent.mkdir(parents=True, exist_ok=True)
    commands_dir = args.output / 'commands'; commands_dir.mkdir()
    import gate
    source_hash = sha(args.source)
    locked = [args.source, args.geometry, args.blender, Path(__file__),
              *[scripts / name for name in ('self_intersections.py', 'self_geometry.py', 'exact_triangles.py', 'gate.py')]]
    inputs = [file_row(p) for p in locked]
    record = {'task_id': 'P1-018', 'milestone': 'M5', 'status': 'running',
              'start_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
              'source_sha256': source_hash, 'seed': SEED, 'human_approval_reference': None,
              'expected_controls': len(EXPECTED_NAMES), 'completed_controls': 0,
              'expected_control_names': list(EXPECTED_NAMES), 'controls': [], 'commands': [], 'inputs': inputs,
              'scope': 'Pinned-engine CLI/data rejection, constructed and actual-native-mesh predicate controls. '
                       'Full source self intersections, interassembly clearance, lower LODs and rendering are separate.'}
    write(args.report, record)
    environment = dict(os.environ)
    environment.update(BLENDER_USER_CONFIG=str(args.output / 'blender-user-config'),
                       BLENDER_USER_SCRIPTS=str(args.output / 'blender-user-scripts'),
                       PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0')
    def passed(name, **detail):
        record['controls'].append({'name': name, 'status': 'passed', **detail})
    def command(name, script, arguments, output, expected_exit=0, seed='0'):
        prefix = commands_dir / f'{len(record["commands"]) + 1:02d}-{name}'
        argv = [str(args.blender), '--background', '--factory-startup', '--python-exit-code', '1',
                '--python', str(script), '--', *map(str, arguments)]
        begin = time.monotonic()
        row = {'name': name, 'argv': argv, 'cwd': str(args.output), 'expected_exit': expected_exit,
               'start_utc': datetime.now(timezone.utc).isoformat(), 'timeout_seconds': 180,
               'environment_overrides': {**{k: environment[k] for k in ('BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS', 'PYTHONDONTWRITEBYTECODE')},
                                         'PYTHONHASHSEED': seed}}
        try:
            proc = subprocess.run(argv, cwd=args.output, env={**environment, 'PYTHONHASHSEED': seed},
                                  capture_output=True, timeout=180, shell=False)
            code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr = 124, error.stdout or b'', error.stderr or b''
            row['timeout'] = True
        prefix.with_suffix('.stdout.log').write_bytes(stdout)
        prefix.with_suffix('.stderr.log').write_bytes(stderr)
        row.update(exit_status=code, elapsed_seconds=time.monotonic() - begin,
                   end_utc=datetime.now(timezone.utc).isoformat())
        failure = None
        try:
            require(code == expected_exit, f'{name}: expected exit{expected_exit}, actual{code}')
            # Negative reports are structured, so no native fatal/driver diagnostic
            # is expected or waived even when the deliberate CLI exit is nonzero.
            gate.positive_process(0, (stdout + b'\n' + stderr).decode('utf8', errors='replace'))
            require(output.is_file(), name + ': required report absent')
            row['status'] = 'passed'
        except Exception as error:
            failure = error; row.update(status='failed', failure=str(error))
        row['outputs'] = [file_row(p) for p in (prefix.with_suffix('.stdout.log'), prefix.with_suffix('.stderr.log'), output) if p.is_file()]
        write(prefix.with_suffix('.json'), row)
        record['commands'].append({**file_row(prefix.with_suffix('.json')), 'name': name,
                                   'status': row['status'], 'exit_status': code, 'expected_exit': expected_exit})
        print(json.dumps({'control': name, 'exit': code, 'status': row['status']}), flush=True)
        if failure:
            raise failure
        return gate.json_read(output)
    try:
        native = args.output / 'native-controls.json'
        data = command('native-controls', Path(__file__), ['--native-mode', 'all', '--source', args.source,
                       '--geometry', args.geometry, '--report', native], native)
        require(data['status'] == 'passed' and data['source_sha256'] == source_hash
                and data['inputs_unchanged'], 'Native controls did not complete')
        counts = [len(data['core']['predicates']), data['core']['block_boundary']['all_pairs'],
                  sum(r['all_pairs'] for r in data['core']['random_rows']), len(data['native_meshes']), len(data['actual_meshes'])]
        require(counts == list(ALGORITHM_COUNTS), 'Native control inventory incomplete')
        for name, count in zip(ALGORITHM_NAMES, counts):
            passed(name, count=count, report=file_row(native))
        for case in cli_cases(source_hash):
            folder = args.output / case['name']; folder.mkdir()
            geometry, output, source = folder / 'fixture.json.gz', folder / 'result.json', args.source
            raw = json.dumps(case['payload'], allow_nan=True)
            if case.get('duplicate_key'):
                raw = raw.replace('"source_sha256":', '"source_sha256":"duplicate", "source_sha256":', 1)
            geometry.write_bytes(b'not-gzip' if case.get('invalid_gzip') else gzip.compress(raw.encode(), mtime=0))
            if case.get('extension'):
                source = folder / 'source.txt'; source.write_bytes(b'fixture-only-nonblend')
            old = None
            if case.get('overwrite'):
                output.write_bytes(b'{"retained":true}\n'); old = sha(output)
            code = 2 if old else 1 if case['failure'] or case.get('crossing') else 0
            argv = ['--source', source, '--geometry', geometry, '--output', output]
            for prefix in case.get('includes', []):
                argv += ['--include', prefix]
            actual = command(case['name'], scripts / 'self_intersections.py', argv, output, code)
            if old:
                require(sha(output) == old and actual == {'retained': True}, 'CLI overwrote existing evidence')
            else:
                require(actual['status'] == ('passed' if code == 0 else 'failed'), 'CLI report status mismatch')
                if case['failure']:
                    require(case['failure'] in actual.get('failure', ''), 'Wrong intended rejection: ' + case['name'])
                elif case.get('crossing'):
                    require(actual['strict_crossing_pairs'] > 0 and 'failure' not in actual,
                            'Geometry negative did not fail on actual triangle intersections')
                else:
                    require(actual['strict_crossing_pairs'] == 0 and actual['mesh_count'] == 1,
                            'Positive fixture geometry inventory incorrect')
                if case.get('preview'):
                    require(actual['excluded_preview_or_other_lod'] == ['LOD0_Preview'], 'Preview exclusion not reported')
            passed(case['name'], actual_exit=code, intended_rejection=case['failure'],
                   input=file_row(geometry), report=file_row(output), fixture='Deliberate JSON fixture; not actual source geometry')
        for name, mode in (('cli-source-mutated', 'source-mutated'), ('cli-geometry-mutated', 'geometry-mutated'),
                           ('cli-pinned-metadata-rejection', 'wrong-pin')):
            folder = args.output / name; folder.mkdir()
            source = folder / 'source.blend'; shutil.copyfile(args.source, source)
            geometry, output = folder / 'fixture.json.gz', folder / 'result.json'
            geometry.write_bytes(gzip.compress(json.dumps(cli_cases(source_hash)[0]['payload']).encode(), mtime=0))
            initial = [file_row(source), file_row(geometry)]
            actual = command(name, Path(__file__), ['--native-mode', mode, '--source', source,
                             '--geometry', geometry, '--report', output], output, 1)
            require(actual['status'] == 'failed', 'Input/pin mutation accepted')
            expected = 'Pinned Blender identity required' if mode == 'wrong-pin' else 'Locked input changed during self scan'
            require(expected in actual['failure'], 'Unexpected mutation failure')
            if mode != 'wrong-pin':
                require(actual['inputs_unchanged'] is False, 'Input mutation not detected')
            passed(name, before=initial, after=[file_row(source), file_row(geometry)], report=file_row(output),
                   injection='Declared control only; native Blender identity is verified before metadata injection')
        cores = [data['core_sha256']]
        for seed in ('1', '9013'):
            output = args.output / ('native-core-' + seed + '.json')
            actual = command('native-core-' + seed, Path(__file__), ['--native-mode', 'core', '--source', args.source,
                             '--geometry', args.geometry, '--report', output], output, seed=seed)
            cores.append(actual['core_sha256'])
        require(len(set(cores)) == 1, 'Native semantic core differs between fresh hash-seed processes')
        passed(EXTRA_NAMES[0], seeds=['0', '1', '9013'], core_sha256=cores[0],
               semantics='Core excludes paths, tool platform strings, UTC and elapsed time; this run covers only the recorded platform')
        output = args.output / 'actual-source-cli.json'
        actual = command(EXTRA_NAMES[1], scripts / 'self_intersections.py', ['--source', args.source,
                         '--geometry', args.geometry, '--include', 'LOD0_PillarA_', '--output', output], output)
        require(actual['status'] == 'passed' and actual['selected_meshes'] == ['LOD0_PillarA_L', 'LOD0_PillarA_R']
                and actual['strict_crossing_pairs'] == 0 and actual['source_sha256'] == source_hash,
                'Current actual-source A-pillar positive is incomplete or intersects')
        passed(EXTRA_NAMES[1], report=file_row(output), note='Only the declared actual pair; full-source scan remains a separate required stage')
        # This is a complete metadata fixture whose negative mutations exercise
        # omission/failure rejection; no fictitious engine result is accepted.
        probe = copy.deepcopy(record)
        probe['controls'].append({'name': EXTRA_NAMES[2], 'status': 'passed'})
        probe.update(status='passed', completed_controls=len(EXPECTED_NAMES),
                     inputs_unchanged=True, source_unchanged=True, outputs=[file_row(native)])
        validate_report(probe, source_hash)
        rejected = []
        for kind in ('missing-row', 'duplicate-row', 'failed-row', 'no-inventory', 'count-only',
                     'wrong-source', 'no-commands', 'float-count', 'truncated-commands',
                     'bad-output-digest', 'missing-input-digest', 'zero-fixture-count',
                     'missing-fixture-count', 'float-fixture-count', 'boolean-fixture-count',
                     'different-native-report', 'unbound-native-report'):
            changed = copy.deepcopy(probe)
            if kind == 'missing-row': changed['controls'].pop()
            elif kind == 'duplicate-row': changed['controls'][-1] = changed['controls'][0]
            elif kind == 'failed-row': changed['controls'][0]['status'] = 'failed'
            elif kind == 'no-inventory': changed.pop('expected_control_names')
            elif kind == 'count-only': changed['controls'] = []
            elif kind == 'wrong-source': changed['source_sha256'] = '0' * 64
            elif kind == 'no-commands': changed['commands'] = []
            elif kind == 'float-count': changed['completed_controls'] = float(len(EXPECTED_NAMES))
            elif kind == 'truncated-commands': changed['commands'].pop()
            elif kind == 'bad-output-digest': changed['outputs'][0]['sha256'] = 'unverified'
            elif kind == 'missing-input-digest': changed['inputs'][0].pop('sha256')
            elif kind == 'zero-fixture-count':
                changed['controls'][0]['count'] = 0
            elif kind == 'missing-fixture-count':
                changed['controls'][1].pop('count')
            elif kind == 'float-fixture-count':
                changed['controls'][2]['count'] = 504.0
            elif kind == 'boolean-fixture-count':
                changed['controls'][3]['count'] = True
            elif kind == 'different-native-report':
                changed['controls'][4].pop('report')
            else:
                for row in changed['controls'][:len(ALGORITHM_NAMES)]:
                    row['report']['sha256'] = '0' * 64
            try:
                validate_report(changed, source_hash)
            except ValueError as failure:
                rejected.append({'case': kind, 'rejection': str(failure)})
            else:
                raise ValueError('Malformed control report accepted: ' + kind)
        passed(EXTRA_NAMES[2], rejected=rejected, fixture='Metadata-only validator controls')
        record.update(status='passed', completed_controls=len(record['controls']))
    except Exception as error:
        record.update(status='failed', failure=type(error).__name__ + ': ' + str(error),
                      completed_controls=len(record['controls']))
    finally:
        record.update(end_utc=datetime.now(timezone.utc).isoformat(), source_unchanged=sha(args.source) == source_hash,
                      inputs_unchanged=all(Path(r['path']).is_file() and sha(r['path']) == r['sha256'] for r in inputs),
                      outputs=[file_row(p) for p in sorted(args.output.rglob('*')) if p.is_file() and p != args.report])
        if record['status'] == 'passed':
            try:
                validate_report(record, source_hash)
            except Exception as error:
                record.update(status='failed', failure=type(error).__name__ + ': ' + str(error))
        write(args.report, record)
    print(json.dumps({'status': record['status'], 'completed_controls': record['completed_controls'],
                      'expected_controls': record['expected_controls']}), flush=True)
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
