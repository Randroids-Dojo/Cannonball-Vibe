"""Execute load-bearing native rejection controls through the source QA gates."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from gate import STAGES, completed_inventory, json_read, positive_process, sha
from run import Runner, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--motion-contract', type=Path, required=True)
    parser.add_argument('--opening-contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    for name in ('blender', 'source', 'geometry', 'motion_contract', 'opening_contract'):
        setattr(args, name, getattr(args, name).resolve(strict=True))
    args.output, args.report = args.output.resolve(), args.report.resolve()
    assert not args.output.exists() and not args.report.exists()
    args.output.mkdir()
    (args.output / 'commands').mkdir()
    scripts = Path(__file__).resolve().parent
    runner = Runner(args.source, args.blender, args.output, scripts)
    controls = []
    def passed(name, detail):
        controls.append({'name': name, 'status': 'passed', **detail})
    expected = ['native-topology-valid', 'native-topology-zero-area', 'native-topology-duplicate', 'native-topology-open',
                'closed-containment-rejected', 'closed-containment-corrected',
                'exact-interface-seat', 'interface-intrusion-rejected', 'opening-endpoints-clear',
                'middle-opening-rejected', 'corrected-opening-domain', 'native-invalid-driver-rejected',
                'native-corrected-driver', 'wiper-geometry-rejections', 'wiper-scalar-extrema',
                'wiper-triangle-rejection', 'missing-stage-rejected']
    result = {'task_id': 'P1-018', 'milestone': 'M5', 'start_utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': sha(args.source), 'expected_controls': expected, 'completed_controls': [],
              'status': 'running', 'human_approval_reference': None,
              'scope': 'Native deliberately invalid/corrected fixtures and strict evidence classifier controls. These results are not synthetic vehicle runtime evidence.'}
    write(args.report, result)
    try:
        fixtures = args.output / 'fixtures'
        native_report = fixtures / 'fixtures.json'
        runner.command('native-fixtures', 'negative_fixtures.py',
                       ['--source', args.source, '--geometry', args.geometry, '--opening-contract', args.opening_contract,
                        '--output', fixtures], [native_report, fixtures / 'middle-collision.json.gz', fixtures / 'corrected.json.gz', fixtures / 'opening-contract.json'])
        fixture = json_read(native_report)
        assert fixture['status'] == 'passed' and fixture['source_sha256'] == result['source_sha256']
        for row in fixture['topology']:
            assert row['passed'] and row['actual_accept'] == row['expected_accept']
            passed('native-topology-' + row['case'], row)
        assert fixture['containment_negative']['status'].startswith('failed')
        assert fixture['containment_corrected']['status'].startswith('outside')
        passed('closed-containment-rejected', {'actual': fixture['containment_negative']})
        passed('closed-containment-corrected', {'actual': fixture['containment_corrected']})
        assert fixture['exact_interface_seat']['status'] == 'passed'
        assert fixture['interface_intrusion_negative']['status'] != 'passed'
        passed('exact-interface-seat', {'actual': fixture['exact_interface_seat']})
        passed('interface-intrusion-rejected', {'actual': fixture['interface_intrusion_negative']})
        samples = fixture['actual_native_opening_sampled_distances']
        assert [row['fraction'] for row in samples] == [0., .5, 1.]
        assert samples[0]['minimum']['distance_m'] > .001001 and samples[2]['minimum']['distance_m'] > .001001
        assert samples[1]['minimum']['distance_m'] == 0.
        passed('opening-endpoints-clear', {'actual_native_samples': samples})
        for case, exit_status in (('middle-collision', 1), ('corrected', 0)):
            path = args.output / (case + '-certificate.json')
            runner.command(case, 'openings.py', ['--input', fixtures / (case + '.json.gz'),
                '--drivers', fixtures / 'opening-contract.json', '--include-component', 'LOD0_QaNegativeFixedObstacle', '--output', path],
                [path], expected_exit=exit_status, positive=exit_status == 0)
            certificate = json_read(path)
            near = certificate['remaining_pairs']
            if exit_status:
                failures = [row for row in near if row['status'] != 'continuous-bound-certified']
                assert failures and any(set(row['pair']) == {'LOD0_QaNegativeFixedObstacle', 'LOD0_QaNegativeMovingCube'} for row in failures)
                assert certificate['status'] != 'passed'
                passed('middle-opening-rejected', {'certificate': str(path), 'sha256': sha(path), 'failures': failures})
            else:
                assert certificate['status'] == 'passed' and not any(row['status'] != 'continuous-bound-certified' for row in near)
                passed('corrected-opening-domain', {'certificate': str(path), 'sha256': sha(path)})
        for case in ('invalid', 'corrected'):
            path = args.output / ('driver-' + case + '.json')
            runner.command('driver-' + case, 'driver_fixture.py', ['--case', case, '--output', path], [path], positive=False)
            record = json_read(Path(runner.commands[-1]['path']))
            stdout = Path(runner.commands[-1]['path']).with_suffix('.stdout.log').read_text(encoding='utf8', errors='replace')
            stderr = Path(runner.commands[-1]['path']).with_suffix('.stderr.log').read_text(encoding='utf8', errors='replace')
            driver = json_read(path)
            try:
                positive_process(record['exit_status'], stdout + '\n' + stderr)
                accepted = True
            except ValueError:
                accepted = False
            assert accepted == (case == 'corrected')
            if case == 'corrected':
                assert driver['curve_valid'] and driver['driver_valid'] and abs(driver['native_location_x'] - .5) <= 1e-6
            passed('native-invalid-driver-rejected' if case == 'invalid' else 'native-corrected-driver',
                   {'native_exit': record['exit_status'], 'positive_command_classifier_accept': accepted,
                    'native_driver': driver, 'command': runner.commands[-1]})
        wiper = args.output / 'wiper-controls.json'
        runner.command('wiper-controls', 'wiper_negative_controls.py', ['--source', args.source, '--geometry', args.geometry,
                       '--motion-contract', args.motion_contract, '--output', wiper], [wiper])
        w = json_read(wiper)
        assert w['status'] == 'passed' and len(w['actual_geometry_cases']) == 4 and len(w['known_scalar_extrema']) == 4
        assert all(row['passed'] for row in w['actual_geometry_cases'] + w['known_scalar_extrema']) and w['triangle_projection_controls']['passed']
        passed('wiper-geometry-rejections', {'native_cases': w['actual_geometry_cases']})
        passed('wiper-scalar-extrema', {'cases': w['known_scalar_extrema']})
        passed('wiper-triangle-rejection', {'cases': w['triangle_projection_controls']})
        fixture_inventory = [{'name': name, 'status': 'passed'} for name in STAGES]
        completed_inventory(fixture_inventory)
        try:
            completed_inventory(fixture_inventory[:-1])
        except ValueError as failure:
            passed('missing-stage-rejected', {'fixture_type': 'Metadata inventory only, never runtime proof', 'rejection': str(failure)})
        else:
            raise AssertionError('Missing final stage incorrectly accepted')
        assert [row['name'] for row in controls] == expected
        result.update(status='passed', completed_controls=expected)
    except Exception as failure:
        result.update(status='failed', failure=str(failure), completed_controls=[row['name'] for row in controls])
    finally:
        result.update(end_utc=datetime.now(timezone.utc).isoformat(), controls=controls, commands=runner.commands,
                      source_unchanged=sha(args.source) == result['source_sha256'])
        if not result['source_unchanged']:
            result['status'] = 'failed'
        write(args.report, result)
    print(json.dumps({'status': result['status'], 'completed_controls': len(result['completed_controls']), 'expected_controls': len(expected)}), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
