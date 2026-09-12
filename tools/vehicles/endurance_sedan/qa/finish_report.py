"""Standard-library-only acceptance of the finite finish certificate schema.

This checks complete inventories, quantitative proof fields and controls. The
source runner separately binds command exits and hashes actual output bytes.
"""
import math
import re

GUARD = 1e-6
CONTROL_NAMES = tuple(kind+f'_{distance:+.7f}m' for kind, distances in (
    ('header_butt', (-.0001, .0001)), ('latch_flange', (-.0001, .0001)),
    ('latch_screw', (-.0001, .0001)), ('sewn_upholstery', (-.0002, .002))) for distance in distances
) + ('sewn_upholstery_intersecting_second_pad_layer',)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Finite numeric proof value required')
    return value


def count(value, minimum=0):
    require(type(value) is int and value >= minimum, 'Integer proof count required')
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Invalid SHA256 binding')
    return value


def nonempty(value):
    require(isinstance(value, list) and bool(value), 'Nonempty proof inventory required')
    return value


def bounds(value):
    require(isinstance(value, (list, tuple)) and len(value) == 2, 'Complete numeric range required')
    low, high = map(number, value)
    require(low <= high, 'Reversed numeric proof range')
    return low, high


def cover(row):
    require(isinstance(row, dict) and row.get('status') == 'passed', 'Incomplete finite surface coverage')
    count(row.get('full_triangles'), 1)
    count(row.get('cells'), 1)
    require(0 <= number(row.get('maximum_certified_surface_distance_m')) <= GUARD,
            'Surface coverage exceeds guard')
    require(not row.get('uncovered'), 'Uncovered surface fragments')


def outside(row):
    require(isinstance(row, dict) and row.get('status') == 'outside', 'Solid containment unresolved')
    rays = nonempty(row.get('rays'))
    require(len(rays) == 3, 'Three independent unambiguous parities required')
    directions = []
    for ray in rays:
        require(ray.get('inside_odd_parity') is False, 'Inside solid parity')
        direction = ray.get('direction')
        require(isinstance(direction, list) and len(direction) == 3, '3D parity direction required')
        values = [number(x) for x in direction]
        require(abs(math.hypot(*values)-1) < 1e-8, 'Unit parity direction required')
        directions.append(tuple(values))
        distances = ray.get('positive_distances_m')
        require(isinstance(distances, list) and all(number(d) > 0 for d in distances)
                and distances == sorted(set(distances)) and len(distances) % 2 == 0, 'Invalid outside ray distances')
    require(len(set(directions)) == 3, 'Duplicated parity directions')


def expected_inventory(names):
    entries = [('header_butt', 'LOD0_PillarA_'+side, 'LOD0_RoofSideRail_'+side) for side in ('L', 'R')]
    for suffix in ('FL', 'FR', 'RL', 'RR'):
        entries.append(('latch_flange', 'LOD0_DoorLatch_'+suffix, 'LOD0_Door_'+suffix))
        screws = sorted(name for name in names if re.fullmatch('LOD0_LatchFastener_'+suffix+r'[-+.0-9]+', name))
        require(len(screws) == 2, 'Exactly two named screws required per latch')
        entries.extend(('latch_screw', name, 'LOD0_DoorLatch_'+suffix) for name in screws)
    for seat in ('FrontL', 'FrontR', 'RearL', 'RearR'):
        base = 'LOD0_'+seat
        entries.extend(('sewn_upholstery', base+'CushionSeam'+str(i), base+'CushionInsert') for i in range(5))
        entries.extend(('sewn_upholstery', base+'BackPiping'+str(side), base+'BackInsert') for side in (-1, 1))
    return [{'kind': kind, 'pair': [a, b]} for kind, a, b in entries]


def validate_result(row):
    require(isinstance(row, dict) and row.get('status') == 'passed', 'Failed finite interface')
    kind = row.get('kind')
    if kind == 'header_butt':
        require(number(row.get('plane_y_m')) == .10509999841451645, 'Changed header split plane')
        require([list(bounds(q)) for q in row.get('finite_abs_x_z_box_m', [])] == [[.682, 1.342], [.697, 1.392]],
                'Changed finite header section envelope')
        require(number(row.get('finite_region_residual_m')) <= GUARD, 'Header cap outside finite envelope')
        require(row.get('entire_opposite_halfspaces') is True and row.get('opposite_geometric_cap_normals') is True,
                'Header solid separation or orientation failed')
        caps, indices = nonempty(row.get('complete_cap_coverage')), nonempty(row.get('cap_triangle_indices'))
        require(len(caps) == len(indices) == 2, 'Both complete header caps required')
        for proof, ids in zip(caps, indices):
            cover(proof)
            nonempty(ids)
            require(all(type(i) is int and i >= 0 for i in ids) and len(set(ids)) == len(ids)
                    and len(ids) == proof['full_triangles'], 'Header cap triangle inventory differs')
    elif kind == 'latch_flange':
        cover(row.get('complete_flange_ring_support'))
        require(row.get('body_boundary_fragments') == [], 'Panel intrudes fitted housing body')
        pieces = nonempty(row.get('flange_boundary_fragments'))
        ranges = [bounds(q.get('depth_range_m')) for q in pieces]
        require(all(low >= -.0002-GUARD-1e-12 and high <= GUARD for low, high in ranges),
                'Panel/housing contact outside finite flange seat')
        maximum = max(high for _, high in ranges)
        require(abs(number(row.get('maximum_panel_depth_m'))-maximum) <= 1e-12, 'Flange maximum contradicts fragments')
        outside(row.get('housing_body_interior'))
    elif kind == 'latch_screw':
        cover(row.get('complete_bottom_cap_support'))
        cover(row.get('complete_socket_wall_support'))
        require(number(row.get('whole_head_minimum_socket_plane_gap_m')) > GUARD, 'No guarded radial socket clearance')
        pieces = nonempty(row.get('housing_inside_head_fragments'))
        maximum = max(bounds(q.get('relative_depth_range_m'))[1] for q in pieces)
        require(maximum <= GUARD and abs(number(row.get('maximum_housing_intrusion_m'))-maximum) <= 1e-12,
                'Screw-cap intrusion differs from complete housing fragments')
        outside(row.get('head_interior'))
    elif kind == 'sewn_upholstery':
        radius = number(row.get('radius_m'))
        require(radius in (.0006, .0008) and number(row.get('maximum_allowed_intrusion_m')) == .15*radius,
                'Changed declared thread intrusion')
        count(row.get('front_chart_count'), 1)
        require(row.get('all_overlapping_front_charts_checked') is True
                and row.get('front_chart_policy') == 'Every positive outward-axis facet checked independently; coverage subtraction is separate',
                'All pad height layers must be checked independently')
        require(row.get('uncovered_footprint') == [], 'Unsupported thread footprint')
        contacts = nonempty(row.get('exact_boundary_contacts'))
        require(count(row.get('tested_triangle_pairs'), 1) >= len(contacts), 'Contact pair counts disagree')
        for contact in contacts:
            count(contact.get('thread_triangle'))
            count(contact.get('pad_triangle'))
            for point in nonempty(contact.get('points_m')):
                require(isinstance(point, list) and len(point) == 3, 'Complete contact coordinates required')
                for value in point:
                    number(value)
        spans = nonempty(row.get('complete_route_spans'))
        for index, span in enumerate(spans):
            require(type(span.get('segment')) is int and span['segment'] == index, 'Route span omitted or reordered')
            length = number(span.get('length_m'))
            require(length > 2*GUARD and span.get('uncovered_intervals') == [], 'Unsupported route interval')
            intervals, end = nonempty(span.get('contact_projection_intervals')), 0.
            previous = -1.
            for interval in intervals:
                low, high = bounds(interval)
                require(0 <= low <= high <= 1 and low >= previous and low <= end+GUARD/length,
                        'Declared contact intervals do not cover route')
                previous, end = low, max(end, high)
            require(end >= 1-GUARD/length, 'Route endpoint unsupported')
        pieces = nonempty(row.get('complete_front_chart_fragments'))
        ranges = [bounds(q.get('distance_range_m')) for q in pieces]
        low, high = bounds(row.get('complete_surface_signed_distance_range_m'))
        require(low >= -.15*radius-GUARD and low <= min(a for a, _ in ranges)+1e-12
                and high >= max(b for _, b in ranges)-1e-12, 'Complete pad surface bound contradicts fragments')
        for piece in pieces:
            count(piece.get('thread_triangle'))
            count(piece.get('pad_triangle'))
    else:
        raise ValueError('Unknown finite interface kind')


def _validate_report(report, source_sha):
    digest(source_sha)
    require(isinstance(report, dict) and report.get('status') == 'passed' and report.get('source_sha256') == source_sha,
            'Failed or differently bound finish certificate')
    require(report.get('human_approval_reference') is None and report.get('inputs_unchanged') is True,
            'Input mutation or invalid human approval')
    require(number(report.get('guard_m')) == GUARD, 'Changed finite interface guard')
    payload_hash = digest(report.get('geometry_payload_sha256'))
    require(count(report.get('interface_count')) == 42, 'Complete42 interface inventory required')
    declarations, results = nonempty(report.get('exact_named_inventory')), nonempty(report.get('results'))
    names = []
    for entry in declarations:
        require(isinstance(entry, dict) and isinstance(entry.get('pair'), list) and len(entry['pair']) == 2
                and all(isinstance(v, str) and v for v in entry['pair']), 'Named interface pair required')
        names.append(entry['pair'][0])
    require(len(set(names)) == 42 and declarations == expected_inventory(names), 'Incomplete or duplicate named interface inventory')
    require(len(results) == 42 and [{'kind': q.get('kind'), 'pair': q.get('pair')} for q in results] == declarations,
            'Proof rows differ from named inventory')
    for row in results:
        validate_result(row)
    controls = nonempty(report.get('negative_controls'))
    require(count(report.get('negative_control_count')) == len(CONTROL_NAMES)
            and [q.get('name') for q in controls] == list(CONTROL_NAMES), 'Missing or duplicate finite controls')
    for row in controls:
        require(row.get('rejected') is True and isinstance(row.get('result'), dict), 'Ineffective negative control')
        require(row['result'].get('status') == 'failed'
                or isinstance(row['result'].get('failure'), str) and bool(row['result']['failure']), 'Negative control did not fail')
    crossing = controls[-1]
    validate_result(crossing.get('baseline'))
    nonempty(crossing.get('exact_extra_layer_intersections'))
    require(crossing['result'].get('all_overlapping_front_charts_checked') is True
            and bounds(crossing['result'].get('complete_surface_signed_distance_range_m'))[0] < -.15*.0006-GUARD,
            'Second-layer control failed for the wrong reason')
    inputs = nonempty(report.get('inputs'))
    require(all(isinstance(q, dict) and isinstance(q.get('path'), str) and q['path'] for q in inputs), 'Invalid file inventory')
    for entry in inputs:
        digest(entry.get('sha256'))
    require(len({q['path'] for q in inputs}) == len(inputs), 'Duplicate file binding')
    require(any(q['sha256'] == source_sha and q['path'].lower().endswith('.blend') for q in inputs)
            and any(q['sha256'] == payload_hash and q['path'].endswith('.json.gz') for q in inputs),
            'Source and evaluated payload byte bindings required')
    filenames = {q['path'].replace('\\', '/').rsplit('/', 1)[-1] for q in inputs}
    require({'finish_interfaces.py', 'finish_report.py', 'precision.py', 'exact_triangles.py',
             'wiper_initial.py', 'wiper_interassembly.py', 'wipers.py'} <= filenames, 'Missing reader dependency binding')
    return {'interfaces': 42, 'negative_controls': len(CONTROL_NAMES), 'unresolved': 0}


def validate_report(report, source_sha):
    """Malformed nested schemas and failed numeric proofs always raise ValueError."""
    try:
        return _validate_report(report, source_sha)
    except (TypeError, KeyError, AttributeError, IndexError) as error:
        raise ValueError('Malformed finite interface report: '+str(error)) from error
