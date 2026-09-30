"""Explicit cover revision selection and source-phase file binding.

These checks select required native verification. Constructor witnesses never
substitute for independent inspection of the final saved source.
"""
from dataclasses import dataclass
import hashlib
import json
import gzip
import math
from pathlib import Path
from fractions import Fraction

NAMES = ('LOD0_RearLowerValance', 'LOD0_RearValanceMount_L1',
         'LOD0_RearValanceMount_L2', 'LOD0_RearValanceMount_R1',
         'LOD0_RearValanceMount_R2')
RECEIVER = 'LOD0_RearBumper'
OPENING_GROUPS = {'Door_FL', 'Door_FR', 'Door_RL', 'Door_RR', 'Hood_Hinge', 'Trunk_Hinge'}
SELECTOR = 'valance_cover_revision39'
COMPANION = 'valance_cover39'
STAGE = 'valance-cover'
POLICY = {
    'schema': 'source-valance-cover39.v1', 'members': list(NAMES),
    'receiver': RECEIVER, 'original_triangles': 324,
    'cover_triangles': 1226, 'mount_triangles': 124,
    'sheet_stock_m': .0012, 'stock_encoding_guard_m': .000001,
    'rest_clearance_m': .001001, 'surface_correspondence_m': .0000002,
    'normal_angle_degrees': .025, 'uv_absolute': .00001,
    'finite_normal_domains': 5, 'pocket_rays': 91,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def revision_requested(specification, construction, *, is_pipeline):
    packaging = specification['original_packaging']
    require(type(packaging) is dict, 'Missing locked original packaging')
    if SELECTOR not in packaging:
        require(COMPANION not in construction, 'Undeclared cover companion')
        return False
    require(is_pipeline is True, 'Current cover requires source binding v2')
    require(digest(packaging[SELECTOR]) == digest(POLICY), 'Unknown/null cover revision')
    require(COMPANION in construction, 'Missing declared cover companion')
    proof = construction[COMPANION]
    require(type(proof) is dict and proof.get('schema') == 'source-valance-cover-construction39.v1',
            'Wrong cover construction witness')
    require(digest(proof.get('policy')) == digest(POLICY), 'Cover witness policy differs')
    require(proof.get('source_phase') == 'pre-lod', 'Wrong cover construction phase')
    require(type(proof.get('before')) is dict and
            set(proof['before']) == {NAMES[0], RECEIVER}, 'Incomplete actual pre-cover rows')
    require(type(proof.get('triangle_domains')) is list and
            len(proof['triangle_domains']) == POLICY['original_triangles'], 'Incomplete original face roles')
    require(type(proof.get('finite_field_domains')) is list and
            len(proof['finite_field_domains']) == POLICY['finite_normal_domains'], 'Incomplete finite field release')
    require(type(proof.get('native')) is dict and set(proof['native'].get('after', {})) == set(NAMES),
            'Incomplete actual five-part native witness')
    require(proof.get('unowned_raw_unchanged') is True and
            type(proof.get('unowned_raw_before')) is dict and proof['unowned_raw_before'],
            'Missing actual protected-context witness')
    return True


@dataclass(frozen=True)
class ValanceCoverLock:
    checkpoint: object
    requested: object
    constructor: object
    encoder: object
    policy_sha256: str


def lock_optional(specification, construction, *, is_pipeline, artifact,
                  generation_inputs, phase_outputs, source_artifacts, logical_files):
    if not revision_requested(specification, construction, is_pipeline=is_pipeline):
        return None
    proof = construction[COMPANION]
    roles = ('checkpoint', 'requested', 'constructor', 'encoder')
    require(all(key in proof for key in roles), 'Missing cover checkpoint/request/helper file')
    files = {key: artifact(proof[key]) for key in roles}
    require(len({r.path for r in files.values()}) == len(roles), 'Aliased cover files')
    require(files['checkpoint'].path.suffix.lower() == '.blend' and files['checkpoint'].bytes > 0,
            'Actual pre-cover Blender source is required')
    require(files['requested'].path.name == 'requested.json.gz' and files['requested'].bytes > 0,
            'Complete pre-encoding requested packet is required')
    for key in ('checkpoint', 'requested'):
        require(files[key] in phase_outputs, 'Cover phase artifact missing from actual fresh outputs: ' + key)
        require(files[key].path not in {r.path for r in source_artifacts}, 'Cover phase aliases another source artifact')
    require(set(logical_files) == {'constructor', 'encoder'}, 'Incomplete cover logical helper roles')
    for key in ('constructor', 'encoder'):
        require(files[key] == logical_files[key] and files[key] in generation_inputs,
                'Wrong or unlocked actual cover helper: ' + key)
    return ValanceCoverLock(*(files[key] for key in roles), digest(POLICY))


def expand_stages(base, *, cover):
    require(type(base) is tuple and STAGE not in base and base.count('static-interfaces') == 1,
            'Invalid base cover-stage inventory')
    if cover is None:
        return base
    require('historical-extraction' in base and 'distance-fields' in base, 'Cover requires source v2 chain')
    position = base.index('static-interfaces')
    return (*base[:position], STAGE, *base[position:])


SECTIONS = ('native_requested_fields', 'protected_receiver_fields', 'complete_outside_fields',
            'stock', 'pocket_rays', 'mounting', 'rest')
SHEETS = {'bottom_return', 'closing_back', 'deep_side', 'formed_front',
          'inboard_closing_return', 'inward_side_bend', 'outer_side'}
RAY_POLICY_SHA256 = '3858a2fd695a46936663de4b23c44dc0bffba94df6427890342f267935bbc104'


def file_row(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def read_document(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate proof property: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite proof number: ' + value)
    path = Path(path)
    data = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def tool_files(directory):
    return sorted(p for p in Path(directory).rglob('*') if p.is_file()
                  and p.suffix in ('.py', '.json') and '__pycache__' not in p.parts)


def capture_run_binding(args, lock, *, tool_directory):
    require(lock.pipeline is not None and lock.pipeline.valance_cover is not None,
            'Caller must select the current cover revision')
    cover = lock.pipeline.valance_cover
    roles = {'source': lock.source.path, 'source_binding': lock.binding.path,
             'construction': lock.pipeline.construction.path, 'checkpoint': cover.checkpoint.path,
             'requested': cover.requested.path, 'geometry': args.geometry}
    directory = Path(tool_directory).resolve(strict=True)
    package = directory / 'valance_cover_verify39'
    require((directory / 'valance_cover.py').is_file() and
            (directory / 'valance_cover_report.py').is_file() and
            (package / 'verify.py').is_file() and (package / 'contracts.py').is_file(),
            'Missing independent staged cover checker')
    return {'schema': 'source-valance-cover-inputs39.v1',
            'source_binding_sha256': lock.binding.sha256,
            'roles': {key: file_row(path) for key, path in roles.items()},
            'source_inputs': [file_row(item.path) for item in lock.inputs],
            'tools': [file_row(path) for path in tool_files(directory)]}


def number(value, *, minimum=0, maximum=math.inf):
    require(type(value) in (int, float) and math.isfinite(value)
            and minimum <= value <= maximum, 'Invalid or out-of-bound proof number')
    return value


def geometry_binding(row):
    return {'name': row['name'], 'vertices': len(row['vertices']),
            'triangles': len(row['triangles']),
            'sha256': digest({k: row[k] for k in ('name', 'vertices', 'triangles')})}


def source_rows(extraction):
    rows = {n: r for n, r in extraction['meshes'].items()
            if n.startswith('LOD0_') and r['properties'].get('source_preview_only') is not True}
    require(set(NAMES) | {RECEIVER} <= set(rows), 'Missing current cover assembly')
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for name in (*NAMES, RECEIVER):
        matrix = rows[name].get('rest_world_matrix')
        require(type(matrix) is list and len(matrix) == 4 and
                all(type(r) is list and len(r) == 4 and
                    all(type(v) in (int, float) and math.isfinite(v) for v in r) for r in matrix)
                and matrix == identity, 'Missing or changed fixed cover transform: ' + name)
        materials = rows[name].get('material_names')
        require(type(materials) is list and materials and
                all(type(v) is str and v for v in materials), 'Missing actual global materials: ' + name)
    return rows


def normal(value):
    require(value['status'] == 'passed' and value['unresolved'] == 0,
            'Unresolved complete normal field')
    number(value['maximum_degrees'], maximum=POLICY['normal_angle_degrees'])


def coverage(value, maximum):
    require(value['status'] == 'passed' and not value['failures']
            and type(value['full_triangles']) is int and value['full_triangles'] > 0,
            'Incomplete finite surface coverage')
    number(value['maximum_certified_surface_distance_m'], maximum=maximum)


def field_rows(records, count):
    require(type(records) is list and [r['triangle'] for r in records] == list(range(count)),
            'Missing, duplicated or reordered actual triangle fields')
    for record in records:
        require(record['status'] == 'passed', 'Failed current triangle field')
        normal(record['normal'])
        number(record['whole_uv_component_error'], maximum=POLICY['uv_absolute'])


def finite_pairs(proof, rows, requested):
    expected = {tuple(sorted((mount, other))) for mount in NAMES[1:]
                for other in (NAMES[0], RECEIVER)}
    joints = proof['finite_joints']
    require(type(joints) is list and len(joints) == 8 and
            {tuple(r['pair']) for r in joints} == expected and
            proof['mounting']['finite_joints'] == joints, 'Incomplete exact finite joint inventory')
    result = {}
    for joint in joints:
        pair = tuple(joint['pair']); mount = joint['mount']
        require(list(pair) == sorted(pair) and mount in NAMES[1:] and mount in pair,
                'Wrong sorted mount/receiver pair')
        receiving = 'body' if RECEIVER in pair else 'cover'
        require(joint['schema'] == 'source-valance-cover39.finite-joint.v1' and
                joint['status'] == 'passed' and joint['receiving_domain'] == receiving
                and joint['guard_m'] == POLICY['stock_encoding_guard_m'], 'Invalid finite joint contract')
        require(joint['certificate_sha256'] == digest({k: v for k, v in joint.items()
                    if k != 'certificate_sha256'}), 'Changed finite certificate content')
        require(joint['geometry_bindings'] == {name: geometry_binding(rows[name]) for name in pair},
                'Finite joint is bound to stale or incomplete geometry')
        caps = joint['actual_finite_cap_footprints']
        expected_caps = {'body_land'} if receiving == 'body' else {'cover_left', 'cover_right'}
        require(set(caps) == expected_caps, 'Incomplete current support footprint')
        for name, cap in caps.items():
            interface = requested[mount]['finite_interfaces']
            indices = interface['body_land_triangles'] if name == 'body_land' else interface[name]['triangles']
            require(cap['triangles'] == indices,
                    'Finite footprint does not use complete requested cap')
            coverage(cap['coverage'], POLICY['stock_encoding_guard_m'])
            require(cap['coverage']['full_triangles'] == len(indices),
                    'Finite footprint coverage omitted an actual cap triangle')
        contact = joint['complete_contact']
        require(contact['status'] == 'passed' and contact['failures'] == []
                and contact['guard_m'] == 1e-6, 'Failed complete finite contact')
        require(contact['finite_cap_triangles'] == [i for cap in caps.values() for i in cap['triangles']],
                'Complete contact used different finite caps')
        for key in ('complete_native_to_cell_union', 'complete_cell_union_to_native'):
            coverage(contact[key], 1e-6)
        require(contact['complete_native_to_cell_union']['full_triangles'] == len(rows[mount]['triangles']),
                'Contact omitted native support triangles')
        witnesses = contact['interior_witnesses']
        require(type(contact['cell_count']) is int and contact['cell_count'] > 0 and
                [r['cell'] for r in witnesses] == list(range(contact['cell_count'])) and
                all(r['all_three_even'] is True and r['parity'] is not None and
                    len(r['parity']['ray_hit_counts']) == 3 and
                    all(type(n) is int and n >= 0 and n % 2 == 0 for n in r['parity']['ray_hit_counts'])
                    for r in witnesses), 'Finite support containment remains unresolved')
        fragments = contact['target_fragments']
        require(type(fragments) is list and contact['current_target_facet_cell_tests'] >= len(fragments),
                'Incomplete target/cell clipping inventory')
        receiver = next(n for n in pair if n != mount)
        for fragment in fragments:
            require(type(fragment['cell']) is int and 0 <= fragment['cell'] < contact['cell_count'] and
                    type(fragment['target_triangle']) is int and
                    0 <= fragment['target_triangle'] < len(rows[receiver]['triangles']), 'Wrong finite fragment owner')
            coverage(fragment['finite_cap_coverage'], 1e-6)
        result[pair] = joint
    return result


def validate_rest(proof, rows, pairs):
    rest = proof['rest']
    expected = sorted({tuple(sorted((n, other))) for n in NAMES for other in rows if n != other})
    require(rest['status'] == 'passed' and rest['failures'] == [] and rest['clearance_m'] == .001001,
            'Failed current changed-parts rest domain')
    require(rest['complete_global_geometry_bindings'] == {n: geometry_binding(r) for n, r in rows.items()},
            'Global current geometry omitted or changed')
    require(rest['pair_count'] == len(expected) == 5 * len(rows) - 15 and
            [tuple(r['pair']) for r in rest['pairs']] == expected and
            rest['finite_joint_pairs'] == [list(p) for p in sorted(pairs)], 'Incomplete actual rest pair domain')
    for record in rest['pairs']:
        pair = tuple(record['pair'])
        if pair in pairs:
            require(record['status'] == 'passed_finite_boundary_caps' and
                    record['certificate_sha256'] == pairs[pair]['certificate_sha256'], 'Wrong finite joint consumption')
        elif record['status'] == 'passed_complete_aabb':
            number(record['lower_bound_m'], minimum=.001001)
        else:
            require(record['status'] == 'passed_complete_nonmate', 'Unknown or failed nonmate result')
            number(record['measurement']['distance_m'], minimum=.001001)


def validate_outside(proof, requested):
    outside = proof['complete_outside_fields']; cover = requested[NAMES[0]]
    require(outside['status'] == 'passed' and not outside['failures'], 'Failed protected outside fields')
    expected = [i for i, d in enumerate(cover['triangle_domains'])
                if d in ('outer', 'rim', 'inner_preserved_fragment')]
    records = outside['field_records']
    require([r['triangle'] for r in records] == expected and
            outside['protected_triangle_count'] == len(expected), 'Incomplete protected native fields')
    released = outside['released_fragments']
    require(type(released) is list and len(released) == len(set(released)) == 7 and set(released) <= set(expected),
            'Incomplete finite normal release')
    for record in records:
        require(record['status'] == 'passed', 'Failed complete outside field')
        number(record['whole_affine_position_bound_m'], maximum=2e-7)
        number(record['whole_uv_error'], maximum=1e-5)
        if record['triangle'] not in released:
            normal(record['complete_normal'])
    owners = outside['surface_owners']
    require(outside['original_owner_count'] == len(owners) == len({r['original_triangle'] for r in owners}) and
            sorted(i for r in owners for i in r['current_triangles']) == sorted(expected), 'Incomplete original finite owners')
    for owner in owners:
        for key in ('original_to_current', 'current_to_original'):
            value = owner[key]
            require(value['status'] == 'passed' and value['guard_m'] == 2e-7 and not value['uncovered']
                    and value['records'], 'Incomplete bidirectional protected surface')
            for record in value['records']:
                cells = record.get('complete_cells')
                if cells is None:
                    require(record['cells'] == 1, 'Missing finite cell subdivision proof')
                    cells = [record]
                else:
                    require(type(cells) is list and cells and len(cells) == record['cells'] and
                            [c['cell'] for c in cells] == list(range(len(cells))), 'Incomplete finite cell subdivision')
                require(all(0 <= Fraction(c['bound_squared']) <= Fraction('0.0000002') ** 2 for c in cells),
                        'Outside surface residual exceeds guard')
    boundaries = outside['boundaries']
    require(len(boundaries) == 11 and len({tuple(r['edge']) for r in boundaries}) == 11 and
            sum(r['kind'] == 'protected' for r in boundaries) == 6 and
            len(outside['actual_lower_fans']) == len(set(outside['actual_lower_fans'])) == 15,
            'Incomplete finite boundary/fan inventory')
    for boundary in boundaries:
        normal(boundary['complete_native_edge'])


def validate_stock(proof, requested):
    stock = proof['stock']; plan = requested[NAMES[0]]
    require(stock['sheet_stock_m'] == .0012 and stock['native_guard_m'] == 1e-6 and
            set(stock['seven_sheet_domains']) == SHEETS, 'Incomplete or changed sheet-stock contract')
    for sheet in stock['seven_sheet_domains'].values():
        require(sheet['status'] == 'passed' and sheet['outer_triangles'] and sheet['inner_triangles'],
                'Missing or failed complete sheet pair')
        number(sheet['minimum']['distance_m'], minimum=.001199)
    outer = [i for i, d in enumerate(plan['triangle_domains']) if d in ('outer', 'terminal_outer')]
    inner = [i for i, d in enumerate(plan['triangle_domains'])
             if d in ('inner_preserved_fragment', 'terminal_inner', 'formed_side_inner', 'authored_inner_front')]
    opposed = stock['all_opposed']; records = opposed['records']
    require(opposed['outer_faces'] == outer and opposed['inner_faces'] == inner and
            opposed['pairs'] == len(outer) * len(inner) and opposed['exact_pairs'] == len(records) and
            opposed['aabb_at_least_1p25mm'] + len(records) == opposed['pairs'], 'Incomplete Cartesian opposed domain')
    actual_pairs = {(r['outer_face'], r['inner_face']) for r in records}
    require(len(actual_pairs) == len(records) and
            all(a in outer and b in inner for a, b in actual_pairs), 'Duplicate or invalid opposed pair')
    boxes = {i: ([min(plan['vertices'][v][k] for v in plan['triangles'][i]) for k in range(3)],
                 [max(plan['vertices'][v][k] for v in plan['triangles'][i]) for k in range(3)])
             for i in set(outer + inner)}
    for a in outer:
        for b in inner:
            if (a, b) not in actual_pairs:
                lo, hi = boxes[a]; other_lo, other_hi = boxes[b]
                require(sum(max(0, lo[k] - other_hi[k], other_lo[k] - hi[k]) ** 2 for k in range(3)) >= .00125 ** 2,
                        'Uncertified omitted opposed near pair')
    short = {(r['outer_face'], r['inner_face']) for r in records
             if Fraction(r['exact_distance_squared_m2']) < Fraction('.001199') ** 2}
    caps = stock['finite_end_caps']
    require(caps['status'] == 'passed_finite_stock_end_classification' and caps['guard_m'] == .001199 and
            caps['whole_mesh_closed_oriented'] is True and
            caps['whole_vertex_link_cycles'] == len({i for t in plan['triangles'] for i in t}),
            'Missing finite stock-end classification')
    number(caps['positive_signed_volume_m3'], minimum=1e-15)
    require(len(caps['pairs']) == 10 and {(r['outer_face'], r['inner_face']) for r in caps['pairs']} == short,
            'Finite caps do not cover the exact complete short-pair set')
    require(len(caps['side_caps']) == 2 and len(caps['return_caps']) == 2, 'Incomplete finite end caps')


def validate_proof(proof, extraction, requested):
    rows = source_rows(extraction)
    require(proof['schema'] == 'source-valance-cover39.verification.v1' and proof['status'] == 'passed' and
            proof['policy'] == POLICY and proof['policy_sha256'] == digest(POLICY) and
            proof['requested_sha256'] == digest(requested), 'Wrong current cover proof policy or request')
    require(set(requested) == set(NAMES) and proof['source_triangle_delta'] == 1026 and
            proof['source_saved'] is False and proof['exported'] is False and proof['rendered'] is False and
            proof['human_approval_reference'] is None, 'Wrong native read-only proof contract')
    require(all(type(proof.get(key)) is dict and proof[key].get('status') == 'passed' for key in SECTIONS),
            'Missing or failed current cover section')
    fields = proof['native_requested_fields']
    require(set(fields['meshes']) == set(NAMES) and fields['failures'] == [], 'Incomplete native field domain')
    require(len(rows[NAMES[0]]['triangles']) == 1226 and
            sum(len(rows[n]['triangles']) for n in NAMES[1:]) == 124, 'Changed current native cover budget')
    for name in NAMES:
        require({k: rows[name][k] for k in ('name', 'vertices', 'triangles')} ==
                {k: requested[name][k] for k in ('name', 'vertices', 'triangles')} and
                rows[name]['material_names'] == requested[name]['materials'], 'Current geometry differs from requested part')
        field_rows(fields['meshes'][name], len(rows[name]['triangles']))
    receiver = proof['protected_receiver_fields']
    require(receiver['physical_material_fields_exact'] is True and receiver['normal_guard_degrees'] == .025
            and receiver['uv_guard'] == 1e-5, 'Changed protected receiver contract')
    field_rows(receiver['triangles'], len(rows[RECEIVER]['triangles']))
    validate_outside(proof, requested)
    validate_stock(proof, requested)
    rays = proof['pocket_rays']
    require(rays['count'] == rays['blocked'] == len(rays['rays']) == 91 and
            [r['policy_index'] for r in rays['rays']] == list(range(91)) and
            rays['fixed_policy_sha256'] == RAY_POLICY_SHA256 and
            rays['geometry_bindings'] == {n: geometry_binding(rows[n]) for n in (NAMES[0], RECEIVER)},
            'Incomplete source-bound pocket rays')
    fixed = [{k: r[k] for k in ('origin', 'direction', 'pixel', 'region', 'view')} for r in rays['rays']]
    require(digest(fixed) == RAY_POLICY_SHA256, 'Changed known counterexample rays')
    for ray in rays['rays']:
        require(ray['status'] == 'passed' and 0 <= ray['cover_triangle'] < len(rows[NAMES[0]]['triangles']) and
                0 <= ray['receiver_triangle'] < len(rows[RECEIVER]['triangles']), 'Pocket backstop or cover hit missing')
        require(0 < number(ray['cover_distance_m']) < number(ray['receiver_distance_m']),
                'Cover is not before the actual receiver')
    mounting = proof['mounting']; controls = mounting['displaced_cap_controls']
    expected_controls = {(n, cap, delta) for n in NAMES[1:] for cap in ('body_land', 'cover_left', 'cover_right')
                         for delta in (-.0002, .0002)}
    require(mounting['complete_cap_count'] == 12 and len(controls) == 24 and
            {(r['name'], r['cap'], r['translation_y_m']) for r in controls} == expected_controls and
            all(r['rejected'] is True and r['coverage']['status'] != 'passed' for r in controls),
            'Missing or accepted displaced complete cap control')
    pairs = finite_pairs(proof, rows, requested)
    validate_rest(proof, rows, pairs)
    return {'members': 5, 'finite_joints': 8, 'complete_rest_pairs': len(proof['rest']['pairs']),
            'sheet_pairs': 7, 'pocket_rays': 91, 'complete_cap_controls': 24, 'source_triangle_delta': 1026}


def validate_observations(payload, held, extraction):
    companion = read_document(held['roles']['construction']['path'])[COMPANION]
    require(payload['actual_pre_cover_verified'] is True and
            digest(payload['actual_pre_cover']) == digest(companion['before']),
            'Native checkpoint observation differs from the held construction boundary')
    count = payload['pre_cover_protected_raw_meshes']
    require(type(count) is int and count == len(companion['unowned_raw_before']),
            'Native checkpoint observation omitted protected source meshes')
    require(payload['current_field_names'] == sorted((*NAMES, RECEIVER)) and
            payload['actual_global_meshes_observed'] == sorted(source_rows(extraction)),
            'Incomplete actual current-source observation inventory')
    observed = payload['actual_imports']
    require(type(observed) is list and observed and
            all(type(r) is dict and set(r) == {'path', 'bytes', 'sha256'} for r in observed),
            'Missing actual native import observations')
    allowed = {r['path']: r for r in held['source_inputs'] + held['tools']}
    paths = [r['path'] for r in observed]
    require(len(paths) == len(set(paths)), 'Repeated native import observation')
    require(all(Path(r['path']).suffix == '.py' and allowed.get(r['path']) == r and
                file_row(r['path']) == r for r in observed), 'Stale or unbound actual native import')
    package = {r['path'] for r in held['tools']
               if Path(r['path']).parent.name == 'valance_cover_verify39' and Path(r['path']).suffix == '.py'}
    entry_names = {'valance_cover.py', 'valance_cover_report.py', 'gate.py'}
    entries = {r['path'] for r in held['tools'] if Path(r['path']).name in entry_names}
    require(len(package) == 13 and len(entries) == 3 and package | entries <= set(paths),
            'Native import observations omitted a required entrypoint or verifier module')


def validate_report(result, payload, *, lock, held, invocation_path, payload_path, extraction):
    require(result['status'] == 'passed' and result['source_sha256'] == lock.source.sha256 and
            result['source_binding_sha256'] == lock.binding.sha256 and
            result['source_saved'] is False and result['exported'] is False and
            result['all_locked_inputs_unchanged'] is True and result['human_approval_reference'] is None,
            'Failed, stale or incomplete native source report')
    require(result['native'] == {'version': '5.1.2', 'build': 'ec6e62d40fa9'} and
            result['run_binding'] == file_row(invocation_path) and result['payload'] == file_row(payload_path),
            'Wrong source-stage engine, invocation or output bytes')
    require(held['source_binding_sha256'] == lock.binding.sha256 and
            held['roles']['source'] == file_row(lock.source.path) and
            payload['input_binding'] == held, 'Native payload differs from caller-held inputs')
    require(all(file_row(r['path']) == r for r in
                list(held['roles'].values()) + held['source_inputs'] + held['tools']),
            'Actual source-stage input or recursive checker changed')
    require(extraction['source_sha256'] == lock.source.sha256 and
            held['roles']['geometry']['sha256'] == result['geometry_sha256'], 'Wrong current global extraction')
    requested = read_document(lock.pipeline.valance_cover.requested.path)
    validate_observations(payload, held, extraction)
    return validate_proof(payload['proof'], extraction, requested)


def validated_binary_pairs(result, payload, extraction):
    """Consume only the prior independently executed and current-source-bound stage."""
    require(result['status'] == 'passed' and result['source_sha256'] == extraction['source_sha256'] and
            result['all_locked_inputs_unchanged'] is True and result['source_saved'] is False and
            result['exported'] is False and result['human_approval_reference'] is None,
            'Missing passed current-source finite certificate stage')
    held = payload['input_binding']
    require(held['roles']['source']['sha256'] == extraction['source_sha256'] and
            all(file_row(r['path']) == r for r in list(held['roles'].values()) + held['source_inputs'] + held['tools']),
            'Stale finite-certificate input or checker')
    requested = read_document(held['roles']['requested']['path'])
    validate_observations(payload, held, extraction)
    validate_proof(payload['proof'], extraction, requested)
    return finite_pairs(payload['proof'], source_rows(extraction), requested)


def certificate_reference(joint):
    return {key: joint[key] for key in ('pair', 'certificate_sha256', 'geometry_bindings')}


def validate_opening_coverage(result, extraction, opening):
    rows = source_rows(extraction)
    require(result['status'] == 'passed' and result['source_sha256'] == extraction['source_sha256'] and
            opening['status'] == 'passed' and opening['source_sha256'] == extraction['source_sha256'],
            'Failed or stale opening proof')
    require(result['mode'] == 'all' and not result['groups_filter'] and not result['components_filter'],
            'Cover requires the complete global continuous opening check')
    require(result['target_m'] == .001 and result['numeric_guard_m'] == 1e-6,
            'Changed continuous opening clearance contract')
    groups = {r['name'] for r in opening['opening_groups']}
    require(len(opening['opening_groups']) == 6 and groups == OPENING_GROUPS,
            'All six actual sedan opening groups required')
    for group in opening['opening_groups']:
        actual_members = {n for n, r in rows.items() if group['name'] in r['ancestors']}
        require(actual_members and actual_members == set(group['descendants']).intersection(rows),
                'Opening group differs from actual current source ancestry: ' + group['name'])
    moving = {n for n, r in rows.items() if groups.intersection(r['ancestors'])}
    require(moving and not moving.intersection(NAMES), 'Invalid moving/current cover membership')
    expected = {tuple(sorted((n, m))) for n in NAMES for m in moving}
    observed = []
    for item in result['entire_domain_aabb_certificates']:
        if set(item['pair']).intersection(NAMES):
            number(item['lower_bound_m'], minimum=.001001)
            observed.append(tuple(sorted(item['pair'])))
    for item in result['remaining_pairs']:
        if set(item['pair']).intersection(NAMES):
            require(item['status'] == 'continuous-bound-certified' and item['witness'] is None and
                    item['unresolved'] is None, 'Unresolved cover/moving-component interval')
            number(item['lower_bound_m'], minimum=.001)
            observed.append(tuple(sorted(item['pair'])))
    require(len(observed) == len(set(observed)) == len(expected) and set(observed) == expected,
            'Cover opening proof omitted or duplicated a current pair')
    return {'members': list(NAMES), 'opening_groups': sorted(groups),
            'moving_meshes': sorted(moving), 'pair_count': len(expected),
            'pair_inventory_sha256': digest([list(p) for p in sorted(expected)])}
