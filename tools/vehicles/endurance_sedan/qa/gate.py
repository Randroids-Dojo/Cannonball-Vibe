"""Strict report and process acceptance shared by the source QA front door."""
from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

STAGES = ('extraction', 'shoulder-field', 'self-intersections', 'self-controls', 'lod-self-intersections', 'lod-self-controls', 'source-controls', 'source-lights', 'opening-drivers', 'motion-drivers',
          'optical-seats', 'finish-interfaces', 'cupholder-interfaces', 'static-interfaces', 'openings', 'opening-containment',
          'tires', 'wiper-glass', 'wiper-interassembly', 'wiper-containment',
          'negative-controls')
DIAGNOSTIC = re.compile(
    r'Traceback \(most recent call last\)|(?:Error in )?PyDriver|SyntaxError:|ERROR[^\r\n]*\bDriver\b|'
    r'(?:image|texture)[^\r\n]*(?:not available|not found|missing|unable to|cannot|failed)|'
    r'(?:not available|not found|missing|unable to|cannot|failed)[^\r\n]*(?:image|texture)|'
    r'EXCEPTION_ACCESS_VIOLATION|SIGSEGV|segmentation fault|fatal error', re.I)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def json_read(path):
    def invalid(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON property: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid, object_pairs_hook=unique)


def positive_process(exit_status, text):
    if exit_status != 0:
        raise ValueError('Native command exit status is not zero: ' + str(exit_status))
    findings = [line for line in text.splitlines() if DIAGNOSTIC.search(line)]
    if findings:
        raise ValueError('Positive Blender command reported forbidden diagnostics: ' + '\n'.join(findings[:12]))


def mesh_defects(rows):
    fields = ('degenerate_loop_triangles', 'nonmanifold_edges', 'duplicate_loop_triangles',
              'triangulated_nonmanifold_edges')
    return [{'name': row['name'], **{key: row[key] for key in fields}}
            for row in rows if any(row[key] != 0 for key in fields) or row['triangles'] <= 0
            or row['minimum_triangle_area_m2'] is None
            or not math.isfinite(row['minimum_triangle_area_m2'])
            or row['minimum_triangle_area_m2'] <= 1e-12]


def inventory(report, payload, source_sha):
    if report['source_sha256'] != source_sha or report['geometry_payload_sha256'] != sha(payload):
        raise ValueError('Native geometry inventory is not bound to the exact supplied source/payload')
    if (report['blender_version'], report['blender_build']) != ('5.1.2', 'ec6e62d40fa9'):
        raise ValueError('Geometry did not use pinned Blender5.1.2/ec6e62d40fa9')
    if report['surface_preview_only'] is not False or report['scene_stage'] != 'production':
        raise ValueError('Full source QA requires the production source with all declared LODs')
    rows = report['mesh_inventory']
    names = [row['name'] for row in rows]
    if not names or len(set(names)) != len(names):
        raise ValueError('Empty or duplicate evaluated mesh inventory')
    defects = mesh_defects(rows)
    if defects:
        raise ValueError('Actual evaluated source mesh defects, including editable preview meshes: ' + json.dumps(defects[:16]))
    normal_fields=('nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals')
    for row in rows:
        if (type(row.get('normal_corners')) is not int or row['normal_corners']<=0
                or any(type(row.get(key)) is not int or row[key]!=0 for key in normal_fields)
                or any(type(row.get(key)) not in (int,float) or not math.isfinite(row[key])
                       for key in ('normal_length_min','normal_length_max'))
                or not 1-1e-6<=row['normal_length_min']<=row['normal_length_max']<=1+1e-6):
            raise ValueError('Invalid raw native corner normals before exporter fallback: '+row['name'])
    shipping = [row for row in rows if row['source_preview_only'] is not True]
    counts = {str(lod): sum(row['triangles'] for row in shipping if row['name'].startswith(f'LOD{lod}_')) for lod in range(3)}
    if counts != report['shipping_lod_triangles'] or any(value <= 0 for value in counts.values()):
        raise ValueError('All three declared LOD inventories must be present and exact')
    total = sum(row['triangles'] for row in shipping)
    collision = sum(row['triangles'] for row in shipping if row['name'].startswith('Collision'))
    materials = sorted({name for row in shipping for name in row['material_names'] if name})
    if total != report['shipping_triangle_total'] or collision != report['shipping_collision_triangles'] or materials != report['shipping_materials']:
        raise ValueError('Source budget totals do not match actual evaluated rows')
    if counts['0'] > 150000 or total > 200000 or not 0 < collision <= 128 or len(materials) > 32:
        raise ValueError('Provisional Q044 content ceiling exceeded')
    if report['opening_sample_steps'] != 100 or report['pose_count'] != 645:
        raise ValueError('Native645-pose inventory incomplete')
    return {'status': 'passed', 'lod_triangles': counts, 'all_shipping_triangles': total,
            'collision_triangles': collision, 'materials': len(materials),
            'all_source_meshes': len(rows), 'native_sampled_poses': 645,
            'raw_native_normal_corners':sum(row['normal_corners'] for row in rows),
            'maximum_normal_length_error':max(max(abs(row['normal_length_min']-1),abs(row['normal_length_max']-1)) for row in rows),
            'limits': 'Content ceilings are provisional Q044; this is not an allocation ratification or motion proof.'}


def stage_report(name, report, source_sha, *, context=None):
    if report.get('status') != 'passed' or report.get('source_sha256') != source_sha:
        raise ValueError(name + ' is failed, incomplete, or bound to a different source')
    if report.get('human_approval_reference') is not None:
        raise ValueError('Automated QA must not introduce a human approval reference')
    if name == 'self-intersections':
        rows=report['rows']
        if (report['components_filter'] or report['strict_crossing_pairs'] != 0
                or report['unresolved'] or not report['inputs_unchanged']
                or report['mesh_count'] != len(rows) or not rows
                or report['selected_meshes'] != [row['name'] for row in rows]
                or any(row['status']!='passed' or row['bad_pairs'] for row in rows)):
            raise ValueError('Every original LOD0 authored mesh must pass the unfiltered exact self scan')
    if name == 'self-controls':
        from self_controls import validate_report
        validate_report(report,source_sha)
    if name == 'lod-self-intersections':
        rows=report['rows']
        counts=report['lod_mesh_counts']
        if (not rows or not report['source_unchanged'] or not report['tools_unchanged']
                or set(counts)!={'1','2'}
                or any(type(value) is not int or value<=0 for value in counts.values())
                or sum(counts.values())!=len(rows) or report['mesh_count']!=len(rows)
                or len({row['name'] for row in rows})!=len(rows)
                or any(not row['name'].startswith(('LOD1_','LOD2_')) or row['status']!='passed' for row in rows)
                or any(counts[lod]!=sum(row['name'].startswith('LOD'+lod+'_') for row in rows) for lod in counts)
                or report['shell_count']!=sum(row['shell_count'] for row in rows)
                or report['triangle_count']!=sum(row['triangles'] for row in rows)
                or report['excluded_cross_shell_candidates']!=sum(row['excluded_cross_shell_candidates'] for row in rows)):
            raise ValueError('Complete source-bound final LOD1/2 shell inventory is required')
        for row in rows:
            shells=row['shells']
            if (not shells or row['shell_count']!=len(shells)
                    or sorted(index for shell in shells for index in shell['source_triangle_indices'])!=list(range(row['triangles']))
                    or any(shell['status']!='passed' or shell['bad_pairs'] for shell in shells)
                    or row['all_batch_aabb_candidates']!=row['tested_intrashell_candidates']+row['excluded_cross_shell_candidates']
                    or row['tested_intrashell_candidates']!=sum(shell['aabb_candidates'] for shell in shells)):
                raise ValueError('Actual indexed final-LOD shell coverage or exact crossing proof is incomplete')
    if name == 'lod-self-controls':
        from lod_self_controls import validate_report
        validate_report(report,source_sha)
    if name == 'source-controls' and len(report['states']) != 109:
        raise ValueError('Source display/threshold/control inventory must contain109 states')
    if name == 'source-lights' and (len(report['states']) != 12 or len(report['preview_beams']) != 4 or len(report['actual_emitter_bindings']) != 9):
        raise ValueError('Source light preview inventory incomplete')
    if name == 'opening-drivers' and len(report['opening_groups']) != 6:
        raise ValueError('Six actual opening driver groups are required')
    if name == 'shoulder-field':
        import shoulder_report
        require(context is not None, 'Caller-locked shoulder context required')
        metrics = check_shoulder_report(report, context['source_lock'], context['geometry'],
                                        context['shoulder_tools'], shoulder_report)
        return {'status': 'passed', **metrics}
    if name == 'finish-interfaces':
        import seat_finish_report
        require(context is not None, 'Caller-locked seat context required')
        metrics = check_seat_report(report, source_sha, context['geometry_sha256'],
                                    context['seat_inputs'], seat_finish_report)
        return {'status': 'passed', **metrics}
    if name == 'cupholder-interfaces':
        from cupholder_interfaces import validate_report
        validate_report(report, source_sha)
        return {'status': 'passed', 'finite_interfaces': report['interface_count'],
                'geometric_negative_controls': report['negative_control_count']}
    if name == 'static-interfaces' and (report['named_interface_count'] != 152
                                       or len(report['finite_interface_negative_controls']) != 3):
        raise ValueError('Revision17 requires152 finite named joints and3 original fitted interface controls')
    if name == 'static-interfaces':
        if (len(report['roof_return_negative_controls'])!=2
                or any(row['result']['status']!='failed' for row in report['roof_return_negative_controls'])):
            raise ValueError('Uncharted roof-return separation and region-escape controls are required')
        import seat_finish_report
        from static_interfaces import selected_scope
        require(context is not None, 'Caller-locked static context required')
        finish = context['finish_report']
        check_seat_report(finish, source_sha, context['geometry_sha256'],
                          context['seat_inputs'], seat_finish_report)
        data = strict_json(context['geometry'])
        require(data['source_sha256'] == source_sha, 'Wrong static source payload')
        rows = {n: r for n, r in data['meshes'].items()
                if not r['properties'].get('source_preview_only')}
        selected, rules, optical_pairs = selected_scope(rows, context['optical_report'])
        pairs = seat_finish_report.validated_binary_pairs(finish, source_sha)
        expected = expected_consumed_pairs(pairs, selected, rows, optical_pairs)
        require(report['selected_components'] == sorted(selected), 'Static semantic scope changed')
        require(report['named_interface_count'] == len(rules), 'Static named scope changed')
        require(report['finish_group_count'] == 68 and report['finish_binary_pair_count'] == 70
                and report['finish_interfaces_checked_separately'] == 68,
                'Complete finite group and binary domain counts required')
        check_consumed_pairs(report['finish_joint_certificates_used'], expected)
        restraint = report['restraint_checks']
        if (restraint['status'] != 'passed' or len(restraint['cloth_self_contact']) != 6
                or len(restraint['convex_guide_containment']) != 2 or len(restraint['negative_controls']) != 5
                or any(row['status'] != 'passed' for field in ('cloth_self_contact', 'convex_guide_containment', 'negative_controls') for row in restraint[field])):
            raise ValueError('Complete restraint self-contact, convex guides and rejection controls are required')
    if name == 'openings' and (report['mode'] != 'all' or report['groups_filter'] or report['components_filter']):
        raise ValueError('Final opening certificate cannot contain diagnostic filters')
    if name == 'negative-controls' and report.get('expected_controls') != report.get('completed_controls'):
        raise ValueError('Negative control inventory incomplete')
    return {'status': 'passed'}


def completed_inventory(rows):
    check_stage_inventory(rows)


SINGLE_ROLES = ('specification', 'constructor', 'normal_module', 'ownership_module')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def strict_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result

    def invalid(value):
        raise ValueError('Nonfinite JSON: ' + value)

    path = Path(path)
    raw = path.read_bytes()
    if path.suffix == '.gz':
        raw = gzip.decompress(raw)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def keys(value, expected, context):
    require(type(value) is dict and set(value) == set(expected),
            'Unexpected or missing ' + context + ' fields')


def hash_value(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'Invalid SHA256')
    return value


def relative_path(value):
    require(type(value) is str and value and '\\' not in value and ':' not in value,
            'Project-relative POSIX path required')
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value
            and all(p not in ('', '.', '..') and not p.endswith((' ', '.')) for p in value.split('/')),
            'Noncanonical or escaping relative path')
    return path


@dataclass(frozen=True)
class Input:
    path: Path
    sha256: str
    bytes: int

    def verify(self):
        require(self.path.is_file() and self.path.stat().st_size == self.bytes,
                'Missing or wrong-size input: ' + str(self.path))
        require(sha(self.path) == self.sha256, 'Changed input: ' + str(self.path))


def artifact(row, root):
    keys(row, ('path', 'sha256', 'bytes'), 'artifact')
    rel = relative_path(row['path'])
    hash_value(row['sha256'])
    require(type(row['bytes']) is int and row['bytes'] >= 0, 'Nonnegative integral byte count required')
    resolved = (root / Path(*rel.parts)).resolve(strict=True)
    require(resolved.is_relative_to(root), 'Artifact resolves outside construction root')
    result = Input(resolved, row['sha256'], row['bytes'])
    result.verify()
    return result


def constructor_inventory(rows, root):
    require(type(rows) is list and rows, 'Missing constructor input inventory')
    result = []
    for row in rows:
        keys(row, ('role', 'path', 'sha256', 'bytes'), 'constructor input')
        require(row['role'] in (*SINGLE_ROLES, 'constructor_component'), 'Unknown constructor role')
        require(type(row['bytes']) is int and row['bytes'] > 0, 'Empty constructor input')
        result.append(artifact({k: row[k] for k in ('path', 'sha256', 'bytes')}, root))
    require(len({r['path'].casefold() for r in rows}) == len(rows), 'Duplicate constructor path')
    require(len({str(r.path).casefold() for r in result}) == len(rows), 'Aliased constructor input')
    for role in SINGLE_ROLES:
        require(sum(row['role'] == role for row in rows) == 1, 'Missing/duplicate role: ' + role)
    return result


@dataclass(frozen=True)
class SourceLock:
    root: Path
    binding: Input
    source: Input
    packet: Input
    profile: Input
    builder: Input
    helper: Input
    ownership: Input
    constructor_inputs_sha256: str
    inputs: tuple[Input, ...]

    def verify(self):
        for row in self.inputs:
            row.verify()

    def shoulder_expected(self, geometry):
        self.verify()
        return {'source_sha256': self.source.sha256,
                'expected_profile_sha256': self.profile.sha256,
                'expected_constructor_inputs_sha256': self.constructor_inputs_sha256,
                'expected_packet_sha256': self.packet.sha256,
                'expected_geometry_sha256': sha(geometry),
                'construction_root': self.root}


def load_source_binding(path, source, construction_root, output):
    """Resolve the caller's binding BEFORE any subprocess; no report is an input."""
    root = Path(construction_root).resolve(strict=True)
    require(root.is_dir(), 'Construction root must be a directory')
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to(root), 'Binding must be under construction root')
    source = Path(source).resolve(strict=True)
    binding = Input(path, sha(path), path.stat().st_size)
    document = strict_json(path)
    keys(document, ('schema', 'source', 'construction_packet', 'shoulder_profile',
                    'reference_builder', 'builder_inputs', 'construction_inputs',
                    'constructor_inputs_sha256', 'generation_record'), 'source binding')
    require(document['schema'] == 'endurance-sedan-source-generation-binding.v1', 'Wrong binding schema')
    files = {key: artifact(document[key], root) for key in (
        'source', 'construction_packet', 'shoulder_profile', 'reference_builder', 'generation_record')}
    require(all(row.bytes > 0 for row in files.values()), 'Empty source-generation artifact')
    require(files['source'].path == source and source.suffix.lower() == '.blend', 'Wrong actual source argument')
    require(len({str(value.path).casefold() for value in files.values()}) == len(files),
            'Source/packet/profile/builder/record must be distinct artifacts')
    rows = document['construction_inputs']
    constructors = constructor_inventory(rows, root)
    hash_value(document['constructor_inputs_sha256'])
    require(document['constructor_inputs_sha256'] == digest(rows), 'Wrong constructor inventory digest')
    builder_rows = document['builder_inputs']
    require(type(builder_rows) is list and builder_rows, 'Missing fresh-builder closure')
    builders = [artifact(row, root) for row in builder_rows]
    require(len({str(row.path).casefold() for row in builders}) == len(builders), 'Duplicate builder closure input')
    require(files['reference_builder'] in builders, 'Builder absent from its closure')
    packet = strict_json(files['construction_packet'].path)
    core = packet['core']['checkpoint']['core']  # Direct packet, not an aggregate envelope.
    require(core['construction_inputs'] == rows and core['constructor_inputs_sha256'] == digest(rows),
            'Checkpoint constructor inputs differ from caller binding')
    profile = strict_json(files['shoulder_profile'].path)
    require(core['profile'] == profile and core['profile_sha256'] == digest(profile),
            'Checkpoint profile differs from caller binding')
    # Full packet schema/raw fields/witness validation remains the native stage.
    record = strict_json(files['generation_record'].path)
    require(record['schema'] == 'endurance-sedan-source-generation-record.v1', 'Wrong generation record schema')
    require(type(record['exit_status']) is int and record['exit_status'] == 0, 'Generation did not exit zero')
    require(record['constructor_inputs_sha256'] == digest(rows), 'Generation constructor inputs differ')
    expected_outputs = [{**document[key], 'role': key} for key in
                        ('source', 'construction_packet', 'shoulder_profile')]
    require(record['source_outputs'] == expected_outputs, 'Generation output inventory differs')
    require(type(record['argv']) is list and record['argv']
            and all(type(arg) is str and arg for arg in record['argv']), 'Exact generation argv required')
    require(record['checkpoint_phase'] == 'final-geometry-before-shoulder-apply', 'Wrong generation boundary')
    # Logs are exact process outputs, not authority to skip independent checks.
    logs = record['logs']
    require(type(logs) is list and len(logs) == 2, 'Both generation logs must be retained')
    log_files = [artifact(row, root) for row in logs]
    require(len({str(row.path).casefold() for row in log_files}) == 2, 'Duplicate generation logs')
    all_inputs = (binding, *files.values(), *constructors, *builders, *log_files)
    output = Path(output).resolve()
    require(not output.exists(), 'Choose a fresh output directory')
    require(all(not row.path.is_relative_to(output) for row in all_inputs), 'Output contains a locked input')
    by_role = {row['role']: item for row, item in zip(rows, constructors) if row['role'] != 'constructor_component'}
    lock = SourceLock(root, binding, files['source'], files['construction_packet'],
                      files['shoulder_profile'], files['reference_builder'], by_role['normal_module'],
                      by_role['ownership_module'], digest(rows), tuple(all_inputs))
    lock.verify()
    return lock


def check_stage_inventory(rows):
    require(type(rows) is list and tuple(row.get('name') for row in rows) == STAGES,
            'Complete ordered 21-stage inventory required')
    require(all(row.get('status') == 'passed' for row in rows), 'Every stage must pass')


def check_report_inputs(report_rows, expected):
    """Expected path/hash map is computed from the locked invocation, never report."""
    require(type(report_rows) is list and report_rows, 'Report input inventory missing')
    observed = {}
    for row in report_rows:
        keys(row, ('path', 'sha256'), 'report input')
        require(type(row['path']) is str and row['path'] not in observed, 'Duplicate report input')
        observed[row['path']] = hash_value(row['sha256'])
    require(observed == expected, 'Report input paths/hashes differ from locked invocation')


def check_seat_report(report, source_sha, geometry_sha, expected_inputs, reader):
    require(report.get('geometry_payload_sha256') == hash_value(geometry_sha), 'Wrong locked seat payload')
    check_report_inputs(report.get('inputs'), expected_inputs)
    return reader.validate_report(report, source_sha)


def check_shoulder_report(report, lock, geometry, expected_tools, reader):
    """Forward every required expectation from the caller lock, not the report."""
    values = lock.shoulder_expected(geometry)
    expected = {'source': lock.source, 'packet': lock.packet, 'profile': lock.profile,
                'geometry': Input(Path(geometry).resolve(strict=True), sha(geometry),
                                  Path(geometry).stat().st_size)}
    for key, row in expected.items():
        require(report['bindings'][key] == {'path': str(row.path), 'sha256': row.sha256, 'bytes': row.bytes},
                'Shoulder artifact differs from caller invocation: ' + key)
    tools = report['bindings']['tools']
    require(type(tools) is list and len({row['path'] for row in tools}) == len(tools),
            'Missing/duplicate shoulder tool inventory')
    require({row['path']: row for row in tools} == expected_tools, 'Shoulder tools differ from locked invocation')
    return reader.validate_report(report, **values)


def expected_consumed_pairs(validated_pairs, selected, current_names, optical_pairs):
    """Exact subset visited by current selected-vs-all loop, with optics first."""
    selected, current_names, optical_pairs = set(selected), set(current_names), set(optical_pairs)
    require(selected <= current_names, 'Static selected object absent from actual payload')
    return [validated_pairs[pair] for pair in sorted(validated_pairs)
            if set(pair) <= current_names and set(pair) & selected and pair not in optical_pairs]


def check_consumed_pairs(actual, expected):
    require(type(actual) is list and actual == expected, 'Missing/extra/duplicate static finite consumption')
