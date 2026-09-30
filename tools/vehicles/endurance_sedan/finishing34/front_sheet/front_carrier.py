"""Transport original sheet authorship through the actual frozen front stages.

Input geometry is observed, never reconstructed or installed. Geometric fields
are supplied by the caller's current construction modules. Every new retained
fragment needs complete ownership; manufactured planes and walls are excluded.
"""

from . import field_support as support
from . import sheet_reference as sheet


def points(state, tri):
    return [tuple(state['physical']['vertices'][vi]) for vi in tri['vertices']]


def patch(state, targets, indices, ownership, projection):
    return sheet.Patch([points(state, state['triangles'][i]) for i in indices],
                       [[targets[li] for li in state['triangles'][i]['loops']] for i in indices],
                       ownership, projection, indices)


def same_layout(a, b):
    return (a['physical']['vertices'] == b['physical']['vertices']
            and a['triangles'] == b['triangles'] and a['loops'] == b['loops'])


def _plane_remap(before, after, targets, selected, components, axis, ownership, projection):
    if before['physical']['vertices'] != after['physical']['vertices']:
        raise ValueError('Actual plane stage moved geometry')
    old_faces = [i for c in components for i in c['old_faces']]
    if len(set(old_faces)) != len(old_faces):
        raise ValueError('Overlapping authored plane domains')
    removed = set(old_faces)
    retained = [i for i in range(len(before['triangles'])) if i not in removed]
    if any(t['face'] != i for i, t in enumerate(before['triangles'])):
        raise ValueError('Actual plane input must be explicit triangles')
    next_targets, next_selected, evidence = [], set(), []
    cursor = 0
    for old in retained:
        a, b = before['triangles'][old], after['triangles'][cursor]
        if a['vertices'] != b['vertices']:
            raise ValueError('Actual retained plane prefix correspondence failed')
        next_targets.extend(targets[li] for li in a['loops'])
        if old in selected:
            next_selected.add(cursor)
        cursor += 1
    for component in components:
        sign = component['normal_z' if axis == 2 else 'normal_y']
        if type(sign) is not int or sign not in (-1, 1):
            raise ValueError('Invalid actual manufactured plane direction')
        plane = component['plane_z_m' if axis == 2 else 'plane_y_m']
        original_ids = component['old_faces']
        carrier = patch(before, targets, original_ids, ownership, projection)
        new_indices = []
        for ids in component['new_triangles']:
            tri = after['triangles'][cursor]
            if ids != tri['vertices'] or any(p[axis] != plane for p in points(after, tri)):
                raise ValueError('Actual manufactured plane/partition differs from producer')
            owned = carrier.owner(points(after, tri), target=False)
            if owned is None:
                raise ValueError('New plane partition lacks complete original geometry')
            n = tuple(float(sign) if i == axis else 0. for i in range(3))
            if support.angle(n, sheet.normal(points(after, tri))) > .0001:
                raise ValueError('Manufactured plane orientation mismatch')
            next_targets.extend([n]*3)
            new_indices.append(cursor)
            cursor += 1
        reverse = patch(after, next_targets, new_indices, ownership, projection)
        for old in sorted(selected.intersection(original_ids)):
            if reverse.owner(points(before, before['triangles'][old]), target=False) is None:
                raise ValueError('Manufactured plane rewrite discarded original sheet remainder: '+str((axis, old, points(before, before['triangles'][old]))))
        evidence.append({'old_triangles': original_ids, 'new_triangles': new_indices,
                         'superseded_sheet_triangles': sorted(selected.intersection(original_ids)),
                         'axis': axis, 'plane_m': plane, 'normal_sign': sign,
                         'complete_new_to_old_geometry': True, 'complete_selected_original_sheet_to_new_geometry': True,
                         'other_protected_plane_remainders_outside_normal_scope': sorted(set(original_ids)-selected),
                         'authorship': 'protected-existing-manufactured-plane'})
    if cursor != len(after['triangles']) or len(next_targets) != len(after['loops']):
        raise ValueError('Incomplete actual planar partition')
    return next_targets, next_selected, evidence


def prepare(packet, initial_sheet, ownership, projection, transport, bend_field, optical_field):
    """Build final actual sheet carrier without reading/writing scene data."""
    from mathutils import Vector
    core = packet['core']
    if (support.digest(core) != packet['sha256'] or core['object'] != 'LOD0_FrontBumper'
            or core['capture_kind'] != 'actual-in-process-observation'):
        raise ValueError('Invalid current actual construction packet')
    stages = core['stages']
    if tuple(s['stage'] for s in stages) != ('bend', 'planar', 'lamp', 'rear_planar', 'inlet'):
        raise ValueError('Missing/reordered actual front stage')
    if initial_sheet['object'] != core['object']:
        raise ValueError('Original sheet semantic differs from actual construction')
    targets = list(initial_sheet['targets'])
    selected = set(initial_sheet['selected_triangles'])
    state = core['initial']
    if len(targets) != len(state['normals']):
        raise ValueError('Original sheet target inventory differs from current input')
    records = []
    for stage in stages:
        before, after = stage['before'], stage['after']
        if before != state:
            raise ValueError('Unobserved actual stage boundary')
        name = stage['stage']
        previous_selected = set(selected)
        if name == 'bend':
            first, second = stage['encodings']
            explicit = first['before']
            if before['physical']['vertices'] != explicit['physical']['vertices']:
                raise ValueError('Explicit original partition moved vertices')
            if [t['vertices'] for t in before['triangles']] != [t['vertices'] for t in explicit['triangles']]:
                raise ValueError('Explicit partition changed actual original triangles')
            targets = transport.explicit(targets, [t['loops'] for t in before['triangles']], len(before['loops']))
            predicted = [list(bend_field(Vector(p))[0]) for p in explicit['physical']['vertices']]
            if predicted != after['physical']['vertices']:
                raise ValueError('Actual bend geometry differs from independent producer')
            targets = transport.bend(targets, [ls[0] for ls in explicit['loops']], explicit['physical']['vertices'], bend_field)
            if explicit['triangles'] != after['triangles'] or explicit['loops'] != after['loops']:
                raise ValueError('Bend changed actual field partition')
            detail = {'exact_actual_vertex_transport': len(predicted), 'exact_partition': True}
        elif name in ('planar', 'rear_planar'):
            targets, selected, detail = _plane_remap(before, after, targets, selected, stage['proof']['components'],
                                                      2 if name == 'planar' else 1, ownership, projection)
        elif name == 'lamp':
            ps = [Vector(p) for p in before['physical']['vertices']]
            cx = (min(p.x for p in ps)+max(p.x for p in ps))/2
            predicted = [list(optical_field(p, 'body', cx)[0]) for p in ps]
            if predicted != after['physical']['vertices'] or before['triangles'] != after['triangles']:
                raise ValueError('Actual optical geometry differs from independent producer')
            targets = transport.optical(targets, [ls[0] for ls in before['loops']], before['physical']['vertices'], optical_field)
            detail = {'exact_actual_vertex_transport': len(predicted), 'exact_partition': True}
        else:
            if stage['proof']['generated_rear_fan']['repairs'] or len(stage['encodings']) != 1:
                raise ValueError('Current inlet has an unhandled postcut partition; capture and extend its complete mapping explicitly')
            # The actual complete sheet carrier owns only existing sheet. A
            # tagged cutter wall or protected plane cannot enter by nearest-hit.
            carrier = patch(before, targets, sorted(selected), ownership, projection)
            requests = [tuple(n) for n in after['normals']]
            next_selected, transfers, protected = set(), [], []
            claimed = stage['proof']['owners']
            if len(claimed) != len(after['triangles']) or [r['face'] for r in claimed] != list(range(len(claimed))):
                raise ValueError('Incomplete actual inlet ownership inventory')
            for ti, tri in enumerate(after['triangles']):
                ps = points(after, tri)
                owner = carrier.owner(ps)
                entry = claimed[ti]
                # Rear closures and newly made opening walls are independently
                # manufactured domains, even if a coincident corner touches skin.
                protected_domain = entry.get('authored_rear_closure_field', False) or entry['kind'] == 'new_return_wall'
                if protected_domain:
                    if owner is not None:
                        raise ValueError('Manufactured inlet wall also claims complete outer sheet')
                    protected.append({'triangle': ti, 'kind': entry['kind'], 'rear_closure': entry.get('authored_rear_closure_field', False)})
                    continue
                if owner is None:
                    protected.append({'triangle': ti, 'kind': 'not-complete-current-sheet'})
                    continue
                if entry['kind'] in ('retained_exact', 'retained_subdivided') and entry['reference_face'] not in selected:
                    raise ValueError('Inlet producer lineage conflicts with complete current sheet ownership')
                for li, target in zip(tri['loops'], owner['targets']):
                    requests[li] = target
                next_selected.add(ti)
                transfers.append({'triangle': ti, 'actual_points': ps, **owner})
            if not next_selected:
                raise ValueError('No current inlet sheet fragments survived')
            # Account for complete before-sheet remainder. Each piece not in
            # surviving skin must lie within the actual finite hexagonal cutter.
            reverse = patch(after, requests, sorted(next_selected), ownership, projection)
            outline = stage['proof']['outline_xz_m']
            expected_outline = [[-.38, .783], [.38, .783], [.345, .708], [.08, .695], [-.08, .695], [-.345, .708]]
            if outline != expected_outline:
                raise ValueError('Actual inlet footprint differs from the bound construction')
            orientation = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(outline, outline[1:]+outline[:1]))
            cutter = []
            for a, b in zip(outline, outline[1:]+outline[:1]):
                sign = 1 if orientation > 0 else -1
                n = sheet.unit((-sign*(b[1]-a[1]), 0., sign*(b[0]-a[0])))
                cutter.append((n, n[0]*a[0]+n[2]*a[1]-sheet.GUARD))
            cutter.extend([((0., 1., 0.), 2.17-sheet.GUARD), ((0., -1., 0.), -2.51-sheet.GUARD)])
            reverse_rows = []
            for old in sorted(selected):
                ps = points(before, before['triangles'][old])
                candidates = reverse.candidates(ps)
                remaining = [ps]
                for ri in candidates:
                    remaining = [part for poly in remaining for part in ownership._subtract(poly, reverse.patch[ri][2])]
                    if not remaining:
                        break
                for fragment in remaining:
                    if any(sum(n[i]*p[i] for i in range(3)) < offset for p in fragment for n, offset in cutter):
                        raise ValueError('Original sheet remainder escapes both actual surviving fragments and finite inlet cut: '+str(old))
                reverse_rows.append({'before_triangle': old, 'surviving_candidates': [reverse.ids[i] for i in candidates],
                                     'finite_cutter_remainder': remaining, 'unresolved': 0})
            targets, selected = requests, next_selected
            detail = {'complete_current_fragment_ownership': transfers, 'complete_original_remainder': reverse_rows,
                      'protected_current_domains': protected, 'cutter_planes': cutter,
                      'geometry_guard_m': sheet.GUARD, 'corner_guard_m': sheet.CORNER}
        if len(targets) != len(after['loops']):
            raise ValueError('Incomplete transported target inventory after '+name)
        records.append({'stage': name, 'before_sheet_triangles': len(previous_selected),
                        'after_sheet_triangles': len(selected), 'detail': detail})
        state = after
    if state != core['final']:
        raise ValueError('Final native capture differs from final stage')
    return {'schema': 'actual-current-front-sheet-carrier.v1', 'object': core['object'],
            'state': state, 'targets': targets, 'selected_triangles': sorted(selected),
            'actual_stage_proofs': records, 'original_reference_ownership': initial_sheet['complete_original_ownership'],
            'initial_authored_domains': {k: v for k, v in initial_sheet.items() if k != 'targets'},
            'source_packet_sha256': packet['sha256'], 'geometry_is_attribution_only': True}
