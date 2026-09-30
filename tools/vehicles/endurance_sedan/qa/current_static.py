"""Current finite cargo supports for the explicitly bound production source.

Legacy revision17 remains a separate profile. Complete cap support, native
intersection bounds and nonmating clearances are independently exercised.
The rubber-gland certificate bounds contact fragments; it is not a pressure
seal,360degree bearing or mechanical fuel simulation.
"""
import copy
import math

PROFILE = 'production38'
GUARD = 1e-6



def expected_mounts():
    rows = {}
    for side in (-1, 1):
        for suffix, y in ((-2.1, -2.1), (-1.7, -1.718)):
            name = 'LOD0_AuxTankFoot_' + str(side) + '_' + str(suffix)
            rows[name] = {'center_xy': (side * .25, y), 'width_xy': (.04, .04),
                          'low_z': .3885, 'high_z': .420,
                          'bottom': 'LOD0_TrunkCarpet', 'top': 'LOD0_AuxiliaryTank'}
        for y, low, body in ((-2.1, .295, 'LOD0_RearBumper'), (-1.7, .240, 'LOD0_StructuralBody')):
            name = 'LOD0_CargoDeckPedestal_' + str(side) + '_' + str(y)
            rows[name] = {'center_xy': (side * .25, y), 'width_xy': (.04, .04),
                          'low_z': low, 'high_z': .3845,
                          'bottom': body, 'top': 'LOD0_TrunkCarpet'}
    for y in (-1.98, -1.942):
        rows['LOD0_TransferPumpFoot_' + str(y)] = {
            'center_xy': (.537, y), 'width_xy': (.016, .018),
            'low_z': .3885, 'high_z': .415,
            'bottom': 'LOD0_TrunkCarpet', 'top': 'LOD0_TransferPump'}
    return rows


def inventory(row, spec):
    from solid_interfaces import shape_quality
    low = [spec['center_xy'][i] - spec['width_xy'][i] / 2 for i in range(2)] + [spec['low_z']]
    high = [spec['center_xy'][i] + spec['width_xy'][i] / 2 for i in range(2)] + [spec['high_z']]
    points = row['vertices']
    quality = shape_quality(points, row['triangles'])
    expected = [(x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
    matched = [min((math.dist(v, q) for v in points), default=math.inf) for q in expected]
    passed = (len(points) == 8 and len(row['triangles']) == 12
              and max(matched) <= GUARD and quality['signed_volume_m3'] > 0
              and not any(quality[k] for k in ('nonmanifold_edges', 'duplicate_triangles', 'degenerate_triangles')))
    return {'status': 'passed' if passed else 'failed', 'expected_bounds_m': [low, high],
            'maximum_corner_displacement_m': max(matched), 'quality': quality}


def seat(rows, name, spec, top):
    from geometry import bounds
    from solid_interfaces import boundary_shell, intersection
    foot = rows[name]
    shape = inventory(foot, spec)
    other_name = spec['top' if top else 'bottom']
    other = rows[other_name]
    target_z = spec['high_z' if top else 'low_z']
    indices = [t for t in foot['triangles'] if all(abs(foot['vertices'][i][2] - target_z) <= GUARD for i in t)]
    cap = {'name': name + ('_TopCap' if top else '_BottomCap'), 'vertices': foot['vertices'], 'triangles': indices}
    coverage = boundary_shell(cap, other, maximum=GUARD) if len(indices) == 2 else {'status': 'failed_cap_inventory'}
    solid = intersection(foot, other)
    shells = [boundary_shell(solid, r, maximum=GUARD) for r in (foot, other)] if solid['triangles'] else []
    lo, hi = bounds(foot['vertices'])
    residual = max((max(lo[0]-p[0], p[0]-hi[0], lo[1]-p[1], p[1]-hi[1], abs(p[2]-target_z))
                    for p in solid['vertices']), default=0.)
    passed = (shape['status'] == 'passed' and len(indices) == 2 and coverage['status'] == 'passed'
              and residual <= GUARD and all(r['status'] == 'passed' for r in shells))
    return {'pair': [name, other_name], 'top': top, 'status': 'passed' if passed else 'failed',
            'mount_inventory': shape, 'finite_plane_z_m': target_z,
            'cap_triangles': len(indices), 'complete_cap_coverage': coverage,
            'intersection_triangles': len(solid['triangles']), 'intersection_quality': solid['quality'],
            'maximum_intersection_outside_finite_cap_m': residual,
            'complete_intersection_boundary_certificates': shells,
            'guard_m': GUARD, 'scope': 'Complete support plus bounded zero intrusion; no source geometry mutation.'}


def probe(rows):
    from geometry import bounds, box_distance2
    from initial_containment import check_pair
    from surface_minimum import Distances
    specs = expected_mounts()
    actual = {name for name in rows if name.startswith(('LOD0_AuxTankFoot_', 'LOD0_CargoDeckPedestal_', 'LOD0_TransferPumpFoot_'))}
    if actual != set(specs):
        raise ValueError('Missing or unexpected cargo support inventory: ' + str(sorted(actual ^ set(specs))))
    seats = [seat(rows, name, spec, top) for name, spec in specs.items() for top in (False, True)]
    pairs = {tuple(sorted(r['pair'])) for r in seats}
    distance = Distances(rows)
    boxes = {name: bounds(row['vertices']) for name, row in rows.items()}
    broad, near, seen, solids = [], [], set(), {}
    for name in sorted(specs):
        for other in sorted(rows):
            pair = tuple(sorted((name, other)))
            if name == other or pair in seen or pair in pairs:
                continue
            seen.add(pair)
            gap = box_distance2(boxes[name], boxes[other]) ** .5
            if gap >= .001 + GUARD:
                broad.append({'pair': list(pair), 'lower_bound_m': gap-GUARD})
                continue
            minimum = distance.minimum(name, other)
            initial = check_pair(rows, pair, solids) if minimum['distance_m'] >= .001 + GUARD else None
            passed = minimum['distance_m'] >= .001 + GUARD and not initial['status'].startswith(('failed', 'unresolved'))
            near.append({'pair': list(pair), 'minimum': minimum, 'initial_containment': initial,
                         'status': 'passed' if passed else 'failed'})
    return {'status': 'passed' if all(r['status'] == 'passed' for r in seats+near) else 'failed',
            'selected_mounts': sorted(specs), 'native_caps': seats,
            'whole_aabb_certificates': broad, 'near_nonmating': near}


def controls(rows):
    specs = expected_mounts()
    pump = 'LOD0_TransferPumpFoot_-1.98'
    result = []
    for label, shift in (('10um_support_gap', .00001), ('10um_solid_intrusion', -.00001)):
        changed = copy.deepcopy(rows[pump])
        changed['vertices'] = [[x, y, z+shift] for x, y, z in changed['vertices']]
        value = seat({**rows, pump: changed}, pump, specs[pump], False)
        result.append({'name': label, 'status': 'passed' if value['status'] == 'failed' else 'failed', 'observed': value})
    changed = copy.deepcopy(rows[pump])
    changed['triangles'] = [t for t in changed['triangles'] if not all(abs(changed['vertices'][i][2]-.3885) <= GUARD for i in t)]
    value = seat({**rows, pump: changed}, pump, specs[pump], False)
    result.append({'name': 'removed_complete_bottom_cap', 'status': 'passed' if value['status'] == 'failed' else 'failed', 'observed': value})
    foot = 'LOD0_AuxTankFoot_-1_-1.7'
    changed = copy.deepcopy(rows[foot])
    changed['vertices'] = [[x, y+.018, z] for x, y, z in changed['vertices']]
    value = seat({**rows, foot: changed}, foot, specs[foot], True)
    result.append({'name': 'old16mm_unsupported_tank_overhang', 'status': 'passed' if value['status'] == 'failed' else 'failed', 'observed': value})
    for label, selected in (('missing_mount', {n:r for n,r in rows.items() if n != pump}),
                            ('unexpected_mount', {**rows, 'LOD0_TransferPumpFoot_unexpected': rows[pump]})):
        try:
            probe(selected)
        except ValueError as error:
            result.append({'name': label, 'status': 'passed', 'observed_rejection': str(error)})
        else:
            result.append({'name': label, 'status': 'failed'})
    return result


def gland_inventory(row):
    from solid_interfaces import shape_quality
    expected = [(.378 + r*math.cos(i*math.tau/16), -1.99+r*math.sin(i*math.tau/16), z)
                for r in (.009, .019) for z in (.3695, .4035) for i in range(16)]
    actual = row['vertices']
    displacement = max((min((math.dist(a, b) for b in actual), default=math.inf) for a in expected))
    quality = shape_quality(actual, row['triangles'])
    passed = (len(actual) == 64 and len(row['triangles']) == 128 and displacement <= GUARD
              and quality['signed_volume_m3'] > 0
              and not any(quality[k] for k in ('nonmanifold_edges', 'duplicate_triangles', 'degenerate_triangles')))
    return {'status': 'passed' if passed else 'failed', 'expected_vertices': 64,
            'expected_triangles': 128, 'maximum_expected_ring_displacement_m': displacement,
            'quality': quality, 'center_source_m': [.378, -1.99, .3865],
            'outer_radius_m': .019, 'inner_radius_m': .009, 'wall_thickness_m': .010, 'length_m': .034}


def gland(rows):
    from initial_containment import check_pair
    from solid_interfaces import prove_join
    from surface_minimum import Distances
    name = 'LOD0_FuelBulkheadGland'
    rule = {'pair': [name, 'LOD0_TrunkCarpet'], 'solid_policy': 'bounded_compressible_radial_shell',
            'allowed_contact_region': {'kind': 'finite_cylinder', 'start_m': [.378, -1.99, .3845],
                                       'end_m': [.378, -1.99, .3885],
                                       'outer_radius_m': .019, 'inner_radius_m': .018*math.cos(math.pi/24)},
            'rationale': 'Existing 19mm rubber gland at raised4mm cargo deck through its original18mm24-sided bore; same radial-shell allowance, relocated finite geometry.'}
    shape = gland_inventory(rows[name])
    join, solid = prove_join(rows, rule)
    distance = Distances(rows).minimum(name, 'LOD0_StructuralBody')
    initial = check_pair(rows, (name, 'LOD0_StructuralBody'), {}) if distance['distance_m'] >= .001+GUARD else None
    separated = distance['distance_m'] >= .001+GUARD and not initial['status'].startswith(('failed', 'unresolved'))
    return {'status': 'passed' if shape['status'] == join['status'] == 'passed' and separated else 'failed',
            'actual_gland_inventory': shape, 'deck_annular_join': join, 'body_minimum': distance, 'body_initial_containment': initial,
            'body_status': 'passed' if separated else 'failed', 'intersection': solid}


def receiving_controls(rows):
    foot_name = 'LOD0_TransferPumpFoot_-1.98'
    foot_spec = expected_mounts()[foot_name]
    positive = seat(rows, foot_name, foot_spec, False)
    assert positive['status'] == 'passed'
    controls = []
    for name, displacement in (('exact_mount_10um_receiver_gap', -.00001),
                                ('exact_mount_10um_receiver_intrusion', .00001)):
        receiver = copy.deepcopy(rows['LOD0_TrunkCarpet'])
        receiver['vertices'] = [[x, y, z+displacement] for x, y, z in receiver['vertices']]
        result = seat({**rows, 'LOD0_TrunkCarpet': receiver}, foot_name, foot_spec, False)
        passed = result['mount_inventory']['status'] == 'passed' and result['status'] == 'failed'
        controls.append({'name': name, 'status': 'passed' if passed else 'failed',
                         'target_translation_m': [0, 0, displacement], 'result': result})
    receiver = copy.deepcopy(rows['LOD0_TransferPump'])
    floor = min(p[2] for p in receiver['vertices'])
    old = len(receiver['triangles'])
    receiver['triangles'] = [t for t in receiver['triangles']
                             if not all(abs(receiver['vertices'][i][2]-floor) <= GUARD for i in t)]
    assert len(receiver['triangles']) < old
    result = seat({**rows, 'LOD0_TransferPump': receiver}, foot_name, foot_spec, True)
    controls.append({'name': 'exact_mount_missing_receiver_bearing_surface',
                     'removed_receiver_triangles': old-len(receiver['triangles']),
                     'status': 'passed' if result['mount_inventory']['status'] == 'passed'
                              and result['complete_cap_coverage']['status'] != 'passed'
                              and result['status'] == 'failed' else 'failed', 'result': result})
    block = copy.deepcopy(rows[foot_name])
    block['name'] = 'LOD0_UnlistedCargoCollisionControl'
    result = probe({**rows, block['name']: block})
    failures = [r for r in result['near_nonmating'] if r['status'] != 'passed']
    controls.append({'name': 'unlisted_part_overlaps_valid_mount',
                     'status': 'passed' if result['status'] == 'failed'
                              and any(block['name'] in r['pair'] for r in failures) else 'failed',
                     'failed_pairs': failures,
                     'caps_still_pass': all(r['status'] == 'passed' for r in result['native_caps'])})
    gland_name = 'LOD0_FuelBulkheadGland'
    positive_gland = gland_inventory(rows[gland_name])
    assert positive_gland['status'] == 'passed'
    expanded = copy.deepcopy(rows[gland_name])
    expanded['vertices'] = [[.378+(x-.378)*(20/19), -1.99+(y+1.99)*(20/19), z]
                            if math.hypot(x-.378, y+1.99) > .015 else [x, y, z]
                            for x, y, z in expanded['vertices']]
    value = gland_inventory(expanded)
    controls.append({'name': 'gland_outer_radius_19_to20mm',
                     'status': 'passed' if value['status'] == 'failed' else 'failed', 'result': value})
    shifted = copy.deepcopy(rows[gland_name])
    shifted['vertices'] = [[x+.003, y, z] for x,y,z in shifted['vertices']]
    value = gland({**rows, gland_name: shifted})
    controls.append({'name': '3mm_gland_shift_escapes_finite_deck_annulus',
                     'status': 'passed' if value['deck_annular_join']['status'] != 'passed' else 'failed',
                     'result': value})
    return controls



def apply_contract(rows, selected, rules):
    """Replace only the two historical gland roles; add20 exact cargo seats."""
    specs = expected_mounts()
    actual = {name for name in rows if name.startswith((
        'LOD0_AuxTankFoot_', 'LOD0_CargoDeckPedestal_', 'LOD0_TransferPumpFoot_'))}
    if actual != set(specs):
        raise ValueError('Current cargo mount inventory differs: ' + str(sorted(actual ^ set(specs))))
    gland_body = tuple(sorted(('LOD0_FuelBulkheadGland', 'LOD0_StructuralBody')))
    gland_deck = tuple(sorted(('LOD0_FuelBulkheadGland', 'LOD0_TrunkCarpet')))
    if gland_body not in rules or gland_deck not in rules:
        raise ValueError('Expected two explicit legacy gland roles before current migration')
    del rules[gland_body]
    rules[gland_deck] = {'pair': list(gland_deck), 'interface_profile': PROFILE,
                         'current_kind': 'raised-deck-gland'}
    for name, spec in specs.items():
        for top in (False, True):
            other = spec['top' if top else 'bottom']
            key = tuple(sorted((name, other)))
            if key in rules or other not in rows:
                raise ValueError('Duplicate or missing current cargo interface: ' + str(key))
            rules[key] = {'pair': list(key), 'interface_profile': PROFILE,
                          'current_kind': 'cargo-seat', 'mount': name, 'top': top}
        selected.add(name)


def prove(rows, rule):
    if rule.get('interface_profile') != PROFILE:
        raise ValueError('Explicit current interface profile required')
    kind = rule['current_kind']
    if kind == 'cargo-seat':
        name = rule['mount']
        return seat(rows, name, expected_mounts()[name], rule['top']), None
    if kind == 'raised-deck-gland':
        result = gland(rows)
        solid = result.pop('intersection')
        result['pair'] = list(rule['pair'])
        return result, solid
    raise ValueError('Unknown current interface role: ' + str(kind))


def extra_checks(rows):
    positive = probe(rows)
    shape = gland_inventory(rows['LOD0_FuelBulkheadGland'])
    rejected = controls(rows) + receiving_controls(rows)
    passed = (positive['status'] == shape['status'] == 'passed'
              and len(rejected) == 12 and all(row['status'] == 'passed' for row in rejected))
    return {'status': 'passed' if passed else 'failed', 'profile': PROFILE,
            'actual_gland_inventory': shape, 'mounts': positive,
            'negative_controls': rejected, 'guard_m': GUARD,
            'scope': 'Complete20 actual cargo caps and all mount-versus-rest pairs;12 independent native negative controls. Ring geometry is checked on every positive gland role. Annular contact-fragment bounds do not claim a complete pressure seal.'}


def validate_report(report, rows):
    """Host-side scope validation; importing this module must not require bpy."""
    specs = expected_mounts()
    controls_expected = {
        '10um_support_gap', '10um_solid_intrusion', 'removed_complete_bottom_cap',
        'old16mm_unsupported_tank_overhang', 'missing_mount', 'unexpected_mount',
        'exact_mount_10um_receiver_gap', 'exact_mount_10um_receiver_intrusion',
        'exact_mount_missing_receiver_bearing_surface', 'unlisted_part_overlaps_valid_mount',
        'gland_outer_radius_19_to20mm', '3mm_gland_shift_escapes_finite_deck_annulus'}
    negative = report['negative_controls']
    positive = report['mounts']
    if (report['status'] != 'passed' or report['profile'] != PROFILE or report['guard_m'] != GUARD
            or report['actual_gland_inventory']['status'] != 'passed'
            or positive['status'] != 'passed' or positive['selected_mounts'] != sorted(specs)
            or len(negative) != 12 or {r['name'] for r in negative} != controls_expected
            or any(r['status'] != 'passed' for r in negative)):
        raise ValueError('Current cargo profile, positive geometry or12 rejection controls incomplete')
    expected = {tuple(sorted((name, other))) for name in specs for other in rows if name != other}
    records = positive['native_caps'] + positive['whole_aabb_certificates'] + positive['near_nonmating']
    pairs = [tuple(sorted(r['pair'])) for r in records]
    if len(pairs) != len(set(pairs)) or set(pairs) != expected:
        raise ValueError('Complete exact mount-versus-rest pair inventory required')
    caps = positive['native_caps']
    expected_caps = {tuple(sorted((name, spec['top' if top else 'bottom'])))
                     for name, spec in specs.items() for top in (False, True)}
    if (len(caps) != 20 or {tuple(sorted(r['pair'])) for r in caps} != expected_caps
            or any(r['status'] != 'passed' or r['mount_inventory']['status'] != 'passed'
                   or r['cap_triangles'] != 2 or r['complete_cap_coverage']['status'] != 'passed'
                   or r['maximum_intersection_outside_finite_cap_m'] > GUARD
                   or any(c['status'] != 'passed' for c in r['complete_intersection_boundary_certificates'])
                   for r in caps)):
        raise ValueError('Complete finite20 mounting-cap certificates required')
    if (any(not math.isfinite(r['lower_bound_m']) or r['lower_bound_m'] < .001
            for r in positive['whole_aabb_certificates'])
            or any(r['status'] != 'passed' or r['minimum']['distance_m'] < .001 + GUARD
                   or r['initial_containment']['status'].startswith(('failed', 'unresolved'))
                   for r in positive['near_nonmating'])):
        raise ValueError('Current cargo nonmating clearance or containment failed')
