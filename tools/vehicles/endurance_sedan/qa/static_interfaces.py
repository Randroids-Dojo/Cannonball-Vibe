"""Declared fixed packaging, cabin and aero interfaces against actual LOD0.

Every selected component is checked against every other LOD0 component. Named
seats use complete native intersection solids or full-surface separators. Other
pairs require one millimeter clearance and initial noncontainment. This is a
finite declared scope, not permission for unnamed construction intersections.
"""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import json_read, sha, stage_report
from finish_interfaces import inventory as finish_inventory
from fitted_interfaces import negative_controls as fitted_negative_controls, prove as prove_fitted, roof_return_controls
from geometry import bounds, box_distance2
from initial_containment import check_pair
from solid_interfaces import GUARD, prove_join
from surface_minimum import Distances
from restraint_interfaces import contract as restraint_contract, inspect as inspect_restraints


def contract(rows):
    path = Path(__file__).with_name('static-interface-rules.json')
    document = json_read(path)
    assert document['numerical_guard_m'] == GUARD
    rules = {tuple(sorted(row['pair'])): row for row in document['rules']}
    assert len(rules) == len(document['rules']) == 39
    selected = {name for name in rows if any(term in name for term in (
        'MainFuel', 'MainTankCrossover', 'AuxiliaryTank', 'AuxFill', 'AuxVent',
        'VentBulkheadUnion', 'VentRolloverValve', 'VentExternalCover', 'TransferPump',
        'PumpInletUnion', 'FuelBulkheadGland', 'FuelTransferLine', 'TankStrap',
        'DctBellhousing', 'FrontFinalDrive', 'HoodOffsetArm', 'TrunkOffsetArm', 'CabinUndertray_'))}
    def fitted(a, b, kind, **parameters):
        key = tuple(sorted((a, b)))
        assert key not in rules and a in rows and b in rows
        rules[key] = {'pair': list(key), 'fitted_kind': kind, **parameters}
    def seat(a, b, reason):
        key = tuple(sorted((a, b)))
        assert key not in rules and a in rows and b in rows
        rules[key] = {'pair': list(key), 'solid_policy': 'zero_solid_intrusion',
                      'allowed_contact_region': {'kind': 'actual_mesh_boundary', 'mesh': a,
                                                 'maximum_surface_distance_m': GUARD},
                      'rationale': reason}
    mounts = []
    for name, row in rows.items():
        if name.startswith(('LOD0_VisorMount_', 'LOD0_ConsoleMount_', 'LOD0_HandleMount_')):
            mounts.append(name)
            expected = ('LOD0_RoofConsole' if name.startswith('LOD0_ConsoleMount_') else
                        ('LOD0_Sunvisor_' if name.startswith('LOD0_VisorMount_') else 'LOD0_GrabHandle_')
                        + name.split('_')[-2])
            assert row['properties']['mounted_component'] == expected
            seat(name, 'LOD0_Headliner', 'Actual clipped pad upper surface seated on liner underside')
            seat(name, expected, 'Named pad lower surface seated on its roof component')
            selected.add(name)
        elif name.startswith('LOD0_CabinTrayMount_'):
            mounts.append(name)
            expected = 'LOD0_CabinUndertray_' + name.split('_')[-2]
            assert row['properties']['mounted_component'] == expected
            assert row['properties']['mounting_body'] == 'LOD0_StructuralBody'
            fitted(name, expected, 'cabin-pad', pad=name, other=expected, top=False)
            fitted(name, 'LOD0_StructuralBody', 'cabin-pad', pad=name, other='LOD0_StructuralBody', top=True)
            selected.add(name)
        elif name.startswith(('LOD0_FrontTrayMount_', 'LOD0_SplitterMount_')):
            mounts.append(name)
            index = int(name.split('_')[-1])
            expected = ('LOD0_FrontSplitter' if name.startswith('LOD0_SplitterMount_') else
                        'LOD0_FrontUndertray_' + name.split('_')[-2])
            body = 'LOD0_FrontBumper' if name.startswith('LOD0_SplitterMount_') or index >= 2 else 'LOD0_StructuralBody'
            assert row['properties']['mounted_component'] == expected and row['properties']['mounting_body'] == body
            seat(name, expected, 'Named flat support/panel seat')
            seat(name, body, 'Named flat support/body recess seat')
            selected.add(name)
    assert len(mounts) == 30, 'Exact10 cabin +8 front-tray +4 splitter +8 cabin-tray mounts required'
    for side in ('L', 'R'):
        fitted('LOD0_RoofSideRail_' + side, 'LOD0_Roof', 'roof', side=side)
        seat('LOD0_PillarA_' + side, 'LOD0_Roof', 'Fitted A upper-ribbon/roof butt')
        seat('LOD0_PillarA_' + side, 'LOD0_StructuralBody', 'Planar Z1.05 A-ribbon/formed-body upstand butt')
    for side in ('-1', '1'):
        seat('LOD0_ReadingLens_' + side, 'LOD0_RoofConsole', 'Reading lens upper face seated on console underside')
        fitted('LOD0_MainTankCrossoverBridge', 'LOD0_MainTankCrossover_' + side, 'crossover', side=int(side))
    seat('LOD0_RearMirrorMountPad', 'LOD0_Windshield', 'Finite adhesive button flush with the windshield inner face')
    seat('LOD0_RearMirrorStalk', 'LOD0_RearMirrorMountPad', 'Stalk cap seated on mounting button')
    seat('LOD0_RearMirrorStalk', 'LOD0_Mirror_RearHousing', 'Stalk terminal cap seated on rearview housing')
    selected.update(name for name in rows if name.startswith((
        'LOD0_Headliner', 'LOD0_RoofSideRail_', 'LOD0_Sunvisor_', 'LOD0_GrabHandle_',
        'LOD0_RoofConsole', 'LOD0_ReadingLens_', 'LOD0_PillarA_', 'LOD0_RearMirror',
        'LOD0_Mirror_RearHousing', 'LOD0_FrontUndertray_', 'LOD0_FrontSplitter')))
    assert all(name in rows for rule in rules.values() for name in rule['pair'])
    return selected, rules


def inspect(data, optical_report, finish_report):
    rows = {name: row for name, row in data['meshes'].items() if not row['properties'].get('source_preview_only')}
    selected, rules = contract(rows)
    stage_report('finish-interfaces',finish_report,data['source_sha256'])
    expected=[{'kind':kind,'pair':[a,b]} for kind,a,b in finish_inventory(rows)]
    if finish_report['exact_named_inventory']!=expected:
        raise ValueError('Finish certificate does not cover the actual required source interfaces')
    finish_pairs={tuple(sorted(row['pair'])):row for row in finish_report['results']}
    assert optical_report['status'] == 'passed' and optical_report['source_sha256'] == data['source_sha256']
    optical_pairs = {tuple(sorted(row['pair'])) for row in optical_report['pairs']}
    assert len(optical_pairs) == 231
    optical_names = {name for pair in optical_pairs for name in pair}
    selected.update(optical_names)
    restraint_names, restraint_rules = restraint_contract(rows)
    assert not set(rules).intersection(restraint_rules)
    selected.update(restraint_names)
    rules.update(restraint_rules)
    boxes = {name: bounds(row['vertices']) for name, row in rows.items()}
    distances = Distances(rows)
    solid_cache = {}
    broad, near, joints, failures = [], [], [], []
    intersections = {}
    seen = set()
    finish_used=[]
    for a in sorted(selected):
        for b in sorted(rows):
            if a == b:
                continue
            pair = tuple(sorted((a, b)))
            if pair in seen or pair in optical_pairs:
                continue
            seen.add(pair)
            if pair in finish_pairs:
                finish_used.append(finish_pairs[pair])
                continue
            if pair in rules:
                result, mesh = (prove_fitted(rows, rules[pair]) if 'fitted_kind' in rules[pair]
                                else prove_join(rows, rules[pair]))
                joints.append(result)
                if mesh is not None:
                    intersections['|'.join(pair)] = mesh
                if result['status'] != 'passed':
                    failures.append(result)
                print('QA_STATIC_JOINT ' + json.dumps({key: result[key] for key in ('pair', 'status')}), flush=True)
                continue
            gap = box_distance2(boxes[a], boxes[b]) ** .5
            if gap >= .001 + GUARD:
                broad.append({'pair': list(pair), 'lower_bound_m': gap - GUARD})
                continue
            minimum = distances.minimum(a, b)
            initial = check_pair(rows, pair, solid_cache) if minimum['distance_m'] >= .001 + GUARD else None
            passed = minimum['distance_m'] >= .001 + GUARD and not initial['status'].startswith(('failed', 'unresolved'))
            result = {'pair': list(pair), 'minimum': minimum, 'initial_containment': initial,
                      'status': 'passed' if passed else 'failed_clearance_or_containment'}
            near.append(result)
            if not passed:
                failures.append(result)
                print('QA_STATIC_FAILURE ' + json.dumps(result), flush=True)
    untested = sorted(set(rules) - seen)
    assert not untested, ('Declared interfaces omitted from selected scope', untested)
    controls = fitted_negative_controls(rows)
    restraint_checks = inspect_restraints(rows, intersections)
    if restraint_checks['status'] != 'passed':
        failures.append({'kind': 'restraint-extra-checks', **restraint_checks})
    return {'status': 'failed' if failures else 'passed', 'selected_components': sorted(selected),
            'named_interface_count': len(rules), 'named_interfaces': joints,
            'finite_interface_negative_controls': controls,
            'roof_return_negative_controls':roof_return_controls(rows),
            'restraint_checks': restraint_checks,
            'finish_interfaces_checked_separately':len(finish_pairs),
            'finish_joint_certificates_used':finish_used,
            'optical_internal_pairs_checked_separately': len(optical_pairs),
            'whole_aabb_certificates': broad, 'near_nonmating_pairs': near, 'failures': failures}, intersections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--optical-report', type=Path, required=True)
    parser.add_argument('--finish-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert not args.output.exists()
    start = time.perf_counter()
    data = json.loads(gzip.decompress(args.geometry.read_bytes()))
    optical = json_read(args.optical_report)
    finish=json_read(args.finish_report)
    assert any(row['sha256'] == sha(args.geometry) for row in optical['inputs']), 'Optics report used different geometry'
    if finish.get('geometry_payload_sha256')!=sha(args.geometry):
        raise ValueError('Finish report used different actual geometry')
    result, intersections = inspect(data, optical, finish)
    target = args.output.with_suffix('.intersection-solids.json.gz')
    assert not target.exists()
    target.write_bytes(gzip.compress(json.dumps(intersections, separators=(',', ':'), allow_nan=False).encode(), mtime=0))
    dependencies = [args.geometry, args.optical_report, args.finish_report, *sorted(Path(__file__).parent.glob('*.py')),
                    Path(__file__).with_name('static-interface-rules.json'),
                    Path(__file__).with_name('restraint-interface-rules.json')]
    result.update(task_id='P1-018', milestone='M5', utc=datetime.now(timezone.utc).isoformat(),
                  source_sha256=data['source_sha256'], elapsed_seconds=time.perf_counter() - start,
                  inputs=[{'path': str(path.resolve()), 'sha256': sha(path)} for path in dependencies],
                  intersection_geometry={'path': str(target.resolve()), 'sha256': sha(target)},
                  numerical_guard_m=GUARD, nonmating_required_m=.001,
                  limits='Actual fixed packaging, fitted cabin, A/body/roof, rear mirror, front/cabin undertrays and splitter, rear optics and all28 stowed restraint components versus every other LOD0 mesh. Internal wheel/brake and remaining upholstery construction are separate declared assemblies; full moving domains, runtime and human review remain separate. Revision14 roof layer, crossover caps and sixteen cabin pad seats retain complete finite certificates and three deliberately intruding controls. Revision17 adds40 finite restraint joints, six complete cloth self-contact checks, two actual convex-guide bounds and five specific negative controls. Named interfaces are not unconditional pair exemptions.',
                  human_approval_reference=None)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'status': result['status'], 'joints': result['named_interface_count'], 'failures': len(result['failures'])}), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
