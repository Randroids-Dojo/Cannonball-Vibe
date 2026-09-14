"""Typed source selection, caller file binding and numerical proof validation.

Native geometry/field/finite/motion construction is independently performed by
repeated_detail.py. This module has no Blender imports or constructor execution.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path


RIBS = tuple(sorted(f'LOD0_AirboxRib_{side}{index}'
                    for side in (-1, 1) for index in range(5)))
FINS = tuple(sorted(f'LOD0_CoolerFin_{index}' for index in range(36)))
NAMES = tuple(sorted(RIBS + FINS))
RECEIVERS = ('LOD0_Airbox_-1', 'LOD0_Airbox_1', 'LOD0_ChargeCoolingRadiator')
POLICY = {
    'schema': 'source-repeated-detail38.v1', 'members': list(NAMES),
    'rib_axis': 0, 'rib_section_points': 8,
    'rib_original_triangles': 44, 'rib_replacement_triangles': 28,
    'fin_keep': [0, 1, 3, 4, 5, 6],
    'fin_original_triangles': 28, 'fin_replacement_triangles': 20,
    'normal_angle_degrees': .025, 'raw_unit_error': 1e-6,
    'carrier_plane_match_m': 2e-7, 'retained_uv_absolute': 1e-5,
}
SELECTOR = 'repeated_detail_revision38'
COMPANION = 'repeated_detail38'
STAGE = 'repeated-detail'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def revision_requested(specification, construction, *, is_pipeline):
    """Top-level selection only; never run this on nested historical shoulder v1."""
    packaging = specification['original_packaging']
    require(type(packaging) is dict, 'Missing locked original packaging')
    if SELECTOR not in packaging:
        require(COMPANION not in construction, 'Undeclared repeated-detail companion')
        return False
    require(is_pipeline is True, 'Declared current detail revision requires binding v2')
    require(digest(packaging[SELECTOR]) == digest(POLICY), 'Unknown/null repeated-detail policy')
    require(COMPANION in construction, 'Missing declared repeated-detail companion')
    validate_witness_inventory(construction[COMPANION])
    return True


def validate_witness_inventory(proof):
    """Inventory only: native values/domains still require actual source replay."""
    require(type(proof) is dict and proof.get('schema') == 'source-repeated-detail-construction38.v1',
            'Wrong repeated-detail witness schema')
    require(digest(proof.get('policy')) == digest(POLICY), 'Wrong repeated-detail witness policy')
    require(proof.get('source_phase') == 'pre-lod', 'Current source requires an explicit pre-lod witness')
    for key, expected in (('before', NAMES + RECEIVERS), ('after_native', NAMES),
                          ('after_evaluated', NAMES), ('local', NAMES)):
        rows = proof.get(key)
        require(type(rows) is dict and set(rows) == set(expected)
                and all(type(row) is dict and row for row in rows.values()),
                'Incomplete native witness inventory: ' + key)
    require(proof.get('modifier_removals') == list(RIBS), 'Wrong exact rib modifier-removal inventory')
    for key, expected in (('triangles_before', 1448), ('triangles_after', 1000), ('lod0_saving', 448)):
        require(type(proof.get(key)) is int and proof[key] == expected,
                'Wrong declared actual count field: ' + key)
    # These values are assertions to be checked by native replay, never authority.
    require(type(proof.get('context_digest')) is str and len(proof['context_digest']) == 64
            and all(c in '0123456789abcdef' for c in proof['context_digest']),
            'Missing construction context digest')


@dataclass(frozen=True)
class RepeatedDetailLock:
    checkpoint: object
    constructor: object
    encoder: object
    policy_sha256: str


def lock_optional(specification, construction, *, is_pipeline, artifact,
                  generation_inputs, phase_outputs, source_artifacts, logical_files):
    """Use the existing strict artifact() on caller-resolved project-relative rows.

    logical_files maps constructor/encoder to actual locked Inputs at their
    required package paths. Other arguments are already verified Input objects
    from the source-binding loader, never fields copied from the QA report.
    """
    if not revision_requested(specification, construction, is_pipeline=is_pipeline):
        return None
    proof = construction[COMPANION]
    require(all(key in proof for key in ('checkpoint', 'constructor', 'encoder')),
            'Missing checkpoint or constructor file row')
    files = {key: artifact(proof[key]) for key in ('checkpoint', 'constructor', 'encoder')}
    require(len({row.path for row in files.values()}) == 3, 'Aliased repeated-detail inputs')
    checkpoint = files['checkpoint']
    require(checkpoint.path.suffix.lower() == '.blend' and checkpoint.bytes > 0,
            'A nonempty native pre-detail scene is required')
    require(checkpoint.path not in {row.path for row in source_artifacts},
            'Pre-detail checkpoint aliases another source phase or companion')
    require(checkpoint in phase_outputs, 'Pre-detail checkpoint missing from actual fresh phase outputs')
    require(set(logical_files) == {'constructor', 'encoder'}, 'Incomplete caller helper roles')
    for key in ('constructor', 'encoder'):
        require(files[key] == logical_files[key], 'Wrong logical helper path: ' + key)
        require(files[key] in generation_inputs, 'Helper absent from locked generation inputs: ' + key)
    return RepeatedDetailLock(checkpoint, files['constructor'], files['encoder'], digest(POLICY))


def expand_stages(base, *, detail):
    """base is the caller's existing fixed STAGES/STAGES_V2 tuple."""
    require(type(base) is tuple and base.count('motion-drivers') == 1
            and len(set(base)) == len(base) and STAGE not in base, 'Malformed base source-stage inventory')
    if detail is None:
        return base
    require('historical-extraction' in base and 'distance-fields' in base,
            'A repeated-detail stage requires the existing v2 chain')
    position = base.index('motion-drivers') + 1
    return (*base[:position], STAGE, *base[position:])


def check_stage_rows(rows, expected):
    """Small isolated control target; gate.check_stage_inventory owns final use."""
    require(type(rows) is list and [row.get('name') for row in rows] == list(expected),
            'Incomplete or reordered required stage inventory')
    require(all(row.get('status') == 'passed' for row in rows), 'Failed required source stage')


def receiver(name):
    require(name in NAMES, 'Unowned repeated-detail semantic')
    return ('LOD0_ChargeCoolingRadiator' if name in FINS else
            'LOD0_Airbox_' + ('-1' if name in RIBS[:5] else '1'))


def number(value, *, minimum=None, maximum=None):
    require(type(value) in (int, float) and math.isfinite(value), 'Finite numeric evidence required')
    require(minimum is None or value >= minimum, 'Numeric lower bound failed')
    require(maximum is None or value <= maximum, 'Numeric upper bound failed')
    return value


def vector(value):
    require(type(value) is list and len(value) == 3, 'Complete native vector required')
    return [number(v) for v in value]


def rest_pairs(rows):
    require(set(NAMES + RECEIVERS) <= set(rows), 'Missing current fixed members/receivers')
    return sorted({tuple(sorted((a, b))) for a in NAMES for b in rows if a != b})


def motion_inventory(rows, opening, motion):
    require(len(opening['opening_groups']) == 6, 'Six current opening groups required')
    source = [(r, r['descendants'], [0., 1.]) for r in opening['opening_groups']]
    source += [(r, r['rigid_descendants'], r.get('control_domain', [0., 1.]))
               for r in motion['wipers'] + motion['cabin_controls']]
    groups, members = {}, {}
    for record, declared, domain in source:
        name = record['name']
        require(name not in groups and len(set(declared)) == len(declared), 'Duplicate motion group/member')
        require(type(domain) is list and len(domain) == 2 and number(domain[0]) < number(domain[1]),
                'Complete motion domain required')
        axis = vector(record['axis_source'])
        require(abs(math.hypot(*axis)-1) <= 1e-6, 'Invalid actual rotation axis')
        vector(record['pivot_source_m']); number(record['factor_rad'])
        current = sorted(n for n, row in rows.items() if name in row['ancestors'])
        require(current and current == sorted(set(declared) & set(rows)), 'Actual moving descendant inventory differs: ' + name)
        groups[name] = {'name': name, 'members': current, 'domain': domain,
                        'axis_source': axis, 'pivot_source_m': record['pivot_source_m'],
                        'factor_rad': record['factor_rad']}
        for member in current:
            require(member not in members, 'Ambiguous compound moving member')
            members[member] = name
    require(not set(NAMES) & set(members), 'Repeated detail unexpectedly moves')
    tires = motion['tires']
    require(len(tires) == 4 and {r['wheel'] for r in tires} == {'FL', 'FR', 'RL', 'RR'}, 'Four current wheel domains required')
    wheels = {}
    for record in tires:
        name = record['wheel']
        current = sorted(n for n, row in rows.items() if 'Suspension_'+name in row['ancestors'])
        require(current and set(record['rigid_wheel_descendants']) & set(rows) <= set(current),
                'Incomplete current suspension inventory')
        require(record['travel_axis_source'] == [0, 0, 1] and
                record['continuous_travel_m'] == [-.075, .085], 'Changed declared suspension domain')
        wheels[name] = current
    return groups, members, wheels


def check_intervals(intervals, domain):
    require(type(intervals) is list and intervals, 'Missing complete motion interval partition')
    cursor = domain[0]
    for row in intervals:
        require(type(row) is list and len(row) == 2 and number(row[0]) == cursor and number(row[1]) > cursor,
                'Motion partition is missing, overlapping or reordered')
        cursor = row[1]
    require(cursor == domain[1], 'Motion partition does not cover the complete declared domain')


def file_row(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': value}


def capture_run_binding(args, lock, detail, specification, *, tool_directory):
    """Caller captures arguments and its immutable staged tools before launch."""
    expected = {'source': lock.source.path, 'checkpoint': detail.checkpoint.path,
                'pre_lod': lock.pipeline.pre_lod.path, 'construction': lock.pipeline.construction.path,
                'specification': specification.path, 'constructor': detail.constructor.path,
                'encoder': detail.encoder.path, 'geometry': args.geometry,
                'opening': args.opening_contract, 'motion': args.motion_contract,
                'lower_report': args.lower_report, 'lower_payload': args.lower_payload}
    directory = Path(tool_directory).resolve(strict=True)
    actual_tools = [file_row(path) for path in sorted(directory.iterdir())
                    if path.is_file() and path.suffix in ('.py', '.json')]
    require(actual_tools and (directory/'repeated_detail.py').is_file()
            and (directory/'repeated_detail_report.py').is_file(), 'Missing staged native/report checker')
    return {'schema': 'repeated-detail-inputs38.v1', 'source_binding_sha256': lock.binding.sha256,
            'roles': {key: file_row(path) for key, path in expected.items()}, 'tools': actual_tools}


def validate_run_binding(held, args, lock, detail, specification):
    expected = capture_run_binding(args, lock, detail, specification, tool_directory=Path(__file__).resolve().parent)
    require(held == expected, 'Actual stage arguments or staged tools differ from caller-held invocation')


def validate_lower_prerequisite(report, payload, lock, path, before_digest):
    require(report['status'] == 'passed' and report['mode'] == 'lower'
            and report['source_sha256'] == lock.source.sha256
            and report['source_binding_sha256'] == lock.binding.sha256
            and report['source_saved'] is False and report['human_approval_reference'] is None,
            'Independent current lower prerequisite failed or stale')
    require(report['payload'] == file_row(path), 'Wrong actual lower payload bytes')
    require(payload['original_before_digest'] == before_digest, 'Actual pre-LOD observation differs from lower stage')
    require(payload['live']['budget']['passed'] is True, 'Current lower budget is not passing')


def _shell(row, maximum):
    require(row['status'] == 'passed' and row['maximum_allowed_m'] == maximum, 'Failed finite coverage')
    require(type(row['positive_target_triangles']) is int and row['positive_target_triangles'] > 0,
            'Missing positive finite target')
    require(type(row['full_triangles']) is int and row['full_triangles'] > 0 and
            row['full_triangles'] == row['complete_input_triangles_including_boundary_sheets'],
            'Incomplete finite input triangle coverage')
    number(row['maximum_certified_surface_distance_m'], minimum=0, maximum=maximum)


def validate_finite(rows):
    require(type(rows) is list and [r['name'] for r in rows] == list(NAMES), 'Incomplete 46 finite joints')
    for row in rows:
        name = row['name']
        require(row['pair'] == [name, receiver(name)], 'Wrong finite receiver identity')
        if name in FINS:
            require(row['kind'] == 'fin_landing' and len(row['landing_vertices']) == 4
                    and len({tuple(vector(v)) for v in row['landing_vertices']}) == 4,
                    'Missing complete finite landing vertices')
            require(row['original_y'] == row['candidate_y'], 'Original landing plane changed')
            require(len(row['positive_cap_area_m2']) == 2 and min(row['positive_cap_area_m2']) > 1e-12,
                    'Missing positive fin area')
            half = row['halfspaces']; plane = number(half['plane_y'])
            require(number(half['receiver_maximum_y']) <= plane+1e-6 and
                    number(half['fin_minimum_y']) >= plane-1e-6, 'Wrong complete fin stock halfspaces')
            require(len(row['full_cap_coverage']) == 3, 'Incomplete finite cap directions')
            for coverage, maximum in zip(row['full_cap_coverage'], (2e-7, 2e-7, 1e-6)):
                _shell(coverage, maximum)
        else:
            require(row['kind'] == 'embedded_rib' and len(row['quality']) == 2
                    and len(row['positive_surface_area_m2']) == 2
                    and min(row['positive_surface_area_m2']) > 1e-12, 'Missing embedded finite stock')
            for quality in row['quality']:
                require(number(quality['signed_volume_m3']) > 0 and quality['nonmanifold_edges'] == 0
                        and quality['duplicate_triangles'] == 0, 'Invalid finite intersection shell')
            require(len(row['complete_boundary']) == 2, 'Incomplete embedded shell directions')
            for coverage in row['complete_boundary']:
                _shell(coverage, 2e-7)


def validate_rest(value, rows):
    expected = rest_pairs(rows)
    joints = sorted({tuple(sorted((name, receiver(name)))) for name in NAMES})
    require(value['all_pairs'] == [list(p) for p in expected] and value['named_pairs'] == [list(p) for p in joints],
            'Current rest pair coverage is incomplete or stale')
    nonmates = [pair for pair in expected if pair not in set(joints)]
    require([r['pair'] for r in value['nonmates']] == [list(p) for p in nonmates], 'Missing or duplicate current nonmate pair')
    for row in value['nonmates']:
        if row['method'] == 'whole_aabb':
            number(row['lower_bound_m'], minimum=.001001)
        else:
            require(row['method'] == 'complete_triangles_and_containment', 'Unknown current rest proof')
            number(row['minimum']['distance_m'], minimum=.001001)
            contain = row['containment']
            require(contain['pair'] == row['pair'] and contain['status'] in
                    ('outside_by_disjoint_rest_aabbs', 'outside_by_components_and_parity'), 'Unresolved initial containment')
            for check in contain['checks']:
                require(check['status'] in ('outside', 'outside_target_aabb'), 'Initial inside/ambiguous component')


def validate_motion(value, rows, opening, motion):
    groups, members, wheels = motion_inventory(rows, opening, motion)
    require(value['groups'] == groups and value['member_groups'] == members, 'Current motion group coverage changed')
    expected = [[fixed, moving] for fixed in NAMES for moving in sorted(members)]
    require([r['pair'] for r in value['rotations']] == expected, 'Missing or duplicate current swept pair')
    for row in value['rotations']:
        moving = row['pair'][1]
        group = members[moving]
        domain = groups[group]['domain']
        require(row['group'] == group and row['domain'] == domain, 'Wrong actual swept domain')
        check_intervals([leaf['domain'] for leaf in row['leaves']], domain)
        for leaf in row['leaves']:
            number(leaf['lower_bound_m'], minimum=.001001)
            if leaf['method'] == 'triangle_features_plus_displacement':
                number(leaf['displacement_m'], minimum=0)
                require(leaf['midpoint'] == sum(leaf['domain'])/2 and
                        leaf['tested_threshold_m'] == .001001+leaf['displacement_m'], 'Incomplete displacement certificate')
            else:
                require(leaf['method'] == 'whole_aabb', 'Unknown continuous proof method')
    expected_wheels = [[fixed, driver['wheel']] for driver in motion['tires'] for fixed in NAMES]
    require([[r['fixed'], r['wheel']] for r in value['wheels']] == expected_wheels, 'Missing full wheel/suspension pair')
    drivers = {r['wheel']: r for r in motion['tires']}
    for row in value['wheels']:
        driver = drivers[row['wheel']]
        require(row['complete_moving_members'] == wheels[row['wheel']] and
                row['center_source_m'] == driver['center_source_m'] and
                row['travel_m'] == driver['continuous_travel_m'], 'Incomplete suspension sphere or travel')
        number(row['sphere_radius_m'], minimum=0); number(row['lower_bound_m'], minimum=.001001)


def subtract(a, b):
    return [a[i]-b[i] for i in range(3)]


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def unit(value):
    length = math.hypot(*value)
    require(math.isfinite(length) and length > 0, 'Singular field/triangle')
    return [v/length for v in value]


def corner_targets(before, after):
    """Check every corner against the source carrier or the actual new plane.

    An extended flat rib end shares its original plane and affine field; it
    need not invent another normal domain. New fin planes use their geometric
    normal and the declared source-metre chart. No report carrier IDs are used.
    """
    old = before['evaluated']; raw = after['raw']
    corner_count = sum(len(p[0]) for p in raw['polygons'])
    require(old['triangles'] and len(old['triangle_loops']) == len(old['triangles'])
            and raw['polygons'] and corner_count == len(raw['normals'])
            and all(len(v) == corner_count for v in raw['uvs'].values()),
            'Incomplete original or current corner inventory')
    planes, source_faces, areas = [], [], []
    for triangle in old['triangles']:
        a, b, c = [old['vertices'][i] for i in triangle]
        cross_value = cross(subtract(b, a), subtract(c, a))
        normal = unit(cross_value)
        planes.append((normal, dot(normal, a)))
        source_faces.append((a, b, c)); areas.append(math.hypot(*cross_value)/2)
    require(set(raw['uvs']) == set(old['uvs']) == {'SurfaceMeters'}, 'Changed authored UV layers')
    count = 0; domains = []; errors = []; uv_errors = []
    for index, (vertices, _material, _smooth) in enumerate(raw['polygons']):
        points = [raw['vertices'][i] for i in vertices]
        normal = unit(cross(subtract(points[1], points[0]), subtract(points[2], points[0])))
        carriers = [i for i, (n, d) in enumerate(planes) if dot(n, normal) > .99985
                    and max(abs(dot(n, point)-d) for point in points) <= 2e-7]
        carrier = max(carriers, key=lambda i: areas[i], default=None)
        domains.append({'polygon': index, 'source_triangles': carriers, 'source_carrier': carrier,
                        'domain': 'original_source_field' if carrier is not None else 'new_physical_facet',
                        'corner_range': [count, count+len(vertices)]})
        axis = max(range(3), key=lambda i: abs(normal[i]))
        for offset, point in enumerate(points):
            if carrier is None:
                target_normal = normal
                target_uv = {name: [point[i]/.25 for i in range(3) if i != axis] for name in old['uvs']}
            else:
                a, b, c = source_faces[carrier]
                e, f, g = subtract(b, a), subtract(c, a), subtract(point, a)
                ee, ef, ff = dot(e, e), dot(e, f), dot(f, f)
                determinant = ee*ff-ef*ef
                require(determinant > 0, 'Degenerate original affine carrier')
                v = (ff*dot(e, g)-ef*dot(f, g))/determinant
                w = (ee*dot(f, g)-ef*dot(e, g))/determinant
                weights = (1-v-w, v, w); loops = old['triangle_loops'][carrier]
                target_normal = unit([sum(weights[j]*old['normals'][loops[j]][i] for j in range(3))
                                      for i in range(3)])
                target_uv = {name: [sum(weights[j]*values[loops[j]][i] for j in range(3)) for i in range(2)]
                             for name, values in old['uvs'].items()}
            actual = vector(raw['normals'][count+offset])
            require(abs(math.hypot(*actual)-1) <= 1e-6, 'Invalid raw corner normal')
            error = math.degrees(math.atan2(math.hypot(*cross(target_normal, actual)), dot(target_normal, actual)))
            number(error, minimum=0, maximum=.025); errors.append(error)
            for name, values in raw['uvs'].items():
                error_uv = max(abs(a-b) for a, b in zip(target_uv[name], values[count+offset]))
                number(error_uv, minimum=0, maximum=1e-5); uv_errors.append(error_uv)
        count += len(vertices)
    require(count == len(raw['normals']) and all(len(v) == count for v in raw['uvs'].values()),
            'Incomplete physical-facet corner inventory')
    require(domains and errors and uv_errors, 'Missing complete physical facet domain')
    return {'domains': domains, 'corner_count': count,
            'maximum_normal_degrees': max(errors), 'maximum_uv_absolute': max(uv_errors)}


def lower_metadata_preimage(before, after, changes):
    """Reconstruct only already-verified lower-policy property assignments.

    Values come from the separately caller-bound, successful distance-fields
    result and must agree with both actual captures. This never mutates Blender.
    """
    require(type(changes) is dict and set(changes) <= {'lod_index', 'maximum_lod'},
            'Unowned lower metadata change')
    old, new = before['raw']['properties'], after['raw']['properties']
    adjusted = json.loads(json.dumps(before, allow_nan=False))
    for key, delta in changes.items():
        require(type(delta) is dict and set(delta) == {'before', 'after'}
                and delta['before'] == old.get(key), 'Wrong actual lower metadata preimage')
        require(type(delta['after']) is int and delta['after'] == 0
                and type(new.get(key)) is int and new[key] == 0, 'Wrong actual lower metadata result')
        if key == 'lod_index':
            require(key not in old, 'Repeated-detail pre-lod metadata was already assigned')
        else:
            require(key in old and old[key] != 0, 'Unnecessary or unknown maximum-lod assignment')
        adjusted['raw']['properties'][key] = 0
    return adjusted


def validate_context_preimage(observed, proof):
    require(observed.get('source_phase') == proof.get('source_phase') == 'pre-lod',
            'Wrong native writer preimage phase')
    recorded = {**observed, 'before': proof['before']}
    require(digest(recorded) == proof['context_digest'], 'Stored writer context digest does not bind its preimage')


def validate_local(rows, extraction):
    require([r['name'] for r in rows] == list(NAMES), 'Incomplete native member field inventory')
    for row in rows:
        name = row['name']; after = row['after_native']; before = row['before_native']
        expected = extraction['meshes'][name]
        require(after['evaluated']['world_vertices'] == expected['vertices'] and
                after['evaluated']['triangles'] == expected['triangles'], 'Local actual native mesh differs from current extraction')
        require(row['triangles_before'] == (44 if name in RIBS else 28) and
                row['triangles_after'] == (28 if name in RIBS else 20), 'Unexpected native detail cost')
        number(row['raw_normal_unit_error'], minimum=0, maximum=1e-6)
        for value in after['evaluated']['normals']:
            require(abs(math.hypot(*vector(value))-1) <= 1e-6, 'Invalid actual native normal')
        self_test = row['self']
        require(self_test['status'] == 'passed' and not self_test['bad_pairs'] and
                self_test['triangles'] == row['triangles_after'], 'Incomplete actual self check')
        shape = row['shape']
        require(shape['nonmanifold_edges'] == 0 and shape['duplicate_triangles'] == 0
                and number(shape['signed_volume_m3']) > 0, 'Invalid complete actual shell')
        fields = row['fields']; ids = row['retained_triangle_indices']
        require(ids and len(set(ids)) == len(ids) and fields['candidate_triangles_checked'] == len(ids)
                and fields['status'] == 'passed' and not fields['unresolved'], 'Incomplete complete-field domain')
        require(set(c['candidate_triangle'] for c in fields['complete_polygons']) == set(ids), 'Omitted retained triangle field')
        for cell in fields['complete_polygons']:
            require(cell['complete_polygon'] and len(cell['complete_polygon']) >= 3, 'Empty complete field polygon')
            for point in cell['complete_polygon']:
                vector(point)
            number(cell['affine_normal_difference_max'], minimum=0)
            require(number(cell['both_interpolant_length_lower_bound']) > 0, 'Singular original affine field')
            number(cell['whole_polygon_normal_angle_upper_degrees'], minimum=0, maximum=.025)
            require(set(cell['whole_polygon_uv_max_abs']) == set(before['evaluated']['uvs']), 'UV coverage layer missing')
            for value in cell['whole_polygon_uv_max_abs'].values():
                number(value, minimum=0, maximum=1e-5)
        require(row['corner_targets'] == corner_targets(before, after), 'Incomplete actual all-corner target evidence')


def validate_payload(payload, held, extraction, opening, motion):
    require(payload['input_roles'] == held['roles'] and payload['tools'] == held['tools'],
            'Payload file/tool binding differs from caller')
    rows = {name: row for name, row in extraction['meshes'].items() if not row['properties'].get('source_preview_only')}
    require(payload['current_geometry_names'] == sorted(rows), 'Incomplete current assembly inventory')
    require(set(payload['before_native']) == set(NAMES + RECEIVERS)
            and set(payload['original_correspondence']) == set(NAMES + RECEIVERS), 'Missing checkpoint/current rows')
    require(payload['counts'] == {'before': 1448, 'after': 1000, 'members': 46}, 'Wrong actual native detail counts')
    validate_local(payload['local'], extraction)
    validate_finite(payload['finite'])
    validate_rest(payload['rest'], rows)
    validate_motion(payload['motion'], rows, opening, motion)
    for key in ('replay_outside', 'actual_pre_lod_correspondence'):
        value = payload[key]
        require(value['object_names'] and value['mesh_names'] and
                set(value['evaluated_uv']) == set(value['mesh_names']), 'Incomplete native preserved inventory')
        for layers in value['evaluated_uv'].values():
            for layer in layers:
                number(layer['maximum_absolute'], minimum=0, maximum=1e-5)
                require(layer['exact'] == (layer['maximum_absolute'] == 0), 'Incorrect exact UV claim')
    return {'members': 46, 'finite_joints': len(payload['finite']),
            'rest_pairs': len(payload['rest']['all_pairs']), 'rotating_pairs': len(payload['motion']['rotations']),
            'wheel_pairs': len(payload['motion']['wheels']), 'lod0_saving': 448}


def validate_report(result, payload, *, lock, held, invocation_path, payload_path,
                    extraction, opening, motion):
    """Root passes every expectation from its held invocation, never the report."""
    require(result['status'] == 'passed' and result['source_sha256'] == lock.source.sha256
            and result['source_binding_sha256'] == lock.binding.sha256,
            'Repeated-detail report is failed or from another current source')
    require(result['run_binding'] == file_row(invocation_path)
            and result['payload'] == file_row(payload_path), 'Wrong actual invocation or numerical payload bytes')
    require(result['source_saved'] is False and result['exported'] is False
            and result['all_locked_inputs_unchanged'] is True
            and result['human_approval_reference'] is None, 'Wrong native diagnostic contract')
    require(result['native'] == {'version': '5.1.2', 'build': 'ec6e62d40fa9'}, 'Wrong native proof engine')
    require(held['source_binding_sha256'] == lock.binding.sha256
            and held['roles']['source'] == file_row(lock.source.path), 'Wrong caller-held current source')
    require(all(file_row(row['path']) == row for row in list(held['roles'].values()) + held['tools']),
            'Invocation inputs changed before independent validation')
    return validate_payload(payload, held, extraction, opening, motion)
