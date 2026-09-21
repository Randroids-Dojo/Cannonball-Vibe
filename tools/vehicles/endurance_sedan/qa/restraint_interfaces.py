"""Finite restraint attachments, full cloth self-contact and rejection controls."""
import copy
from pathlib import Path

import numpy as np

from gate import json_read
from ribbon_self import inspect as inspect_ribbon
from solid_interfaces import GUARD, prove_join


def contract(rows):
    data = json_read(Path(__file__).with_name('restraint-interface-rules.json'))
    assert data['numerical_guard_m'] == GUARD and data['nonmating_gap_m'] == .001
    selected = set(data['selected_components'])
    rules = {tuple(sorted(row['pair'])): row for row in data['rules']}
    assert len(selected) == 28 and selected <= set(rows)
    assert len(rules) == len(data['rules']) == 40
    assert all(name in rows for pair in rules for name in pair)
    return selected, rules


def convex_guide(guide, mesh):
    v = np.asarray(guide['vertices'], dtype=float)
    triangles = np.asarray(guide['triangles'], dtype=int)
    center = v.mean(axis=0)
    planes = []
    own = -float('inf')
    for a, b, c in v[triangles]:
        normal = np.cross(b-a, c-a)
        normal /= np.linalg.norm(normal)
        if np.dot(normal, center-a) > 0:
            normal = -normal
        own = max(own, float(np.max((v-a) @ normal)))
        planes.append((normal, a))
    points = np.asarray(mesh['vertices'], dtype=float)
    assert len(mesh['triangles']) and len(points), 'Actual cloth/pillar intersection is required'
    residual = max(float(np.max((points-a) @ normal)) for normal, a in planes)
    return {'guide': guide['name'], 'guide_planes': len(planes),
            'full_intersection_triangles': len(mesh['triangles']),
            'convexity_maximum_residual_m': own, 'maximum_outside_residual_m': residual,
            'status': 'passed' if own <= GUARD and residual <= GUARD else 'failed'}


def inspect(rows, intersections):
    selected, rules = contract(rows)
    cloth = sorted(n for n in selected if 'Web' in n or n == 'LOD0_RearCenterBelt')
    assert len(cloth) == 6
    self_checks = [inspect_ribbon(rows[n]) for n in cloth]
    guides = []
    for side, letter in [(-1, 'L'), (1, 'R')]:
        pair = sorted([f'LOD0_PillarC_{letter}', f'LOD0_RearBeltWeb_{side}'])
        mesh = intersections['|'.join(pair)]
        guides.append(dict(convex_guide(rows[f'LOD0_RearBeltGuide_{side}'], mesh), pair=pair))

    controls = []
    pair = tuple(sorted(['LOD0_FrontBeltTongue_-1', 'LOD0_FrontBeltWeb_-1']))
    rule = rules[pair]
    for name, offset in [('tongue-intrusion', .0001), ('tongue-gap', -.008)]:
        changed = dict(rows)
        tongue = copy.deepcopy(rows['LOD0_FrontBeltTongue_-1'])
        for point in tongue['vertices']:
            point[1] += offset
        changed[tongue['name']] = tongue
        actual, _ = prove_join(changed, rule)
        controls.append({'name': name, 'kind': 'Actual source copied tongue translated in Y',
                         'offset_m': offset, 'observed': actual,
                         'status': 'passed' if actual['status'] != 'passed' else 'failed'})
    # Both controls intersect away from any indexed seam; one is coplanar.
    first = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
    for name, second in [
        ('cloth-coplanar-crossing', [[.1, .1, 0.], [.8, .1, 0.], [.1, .8, 0.]]),
        ('cloth-nonplanar-crossing', [[.2, .2, -.1], [.2, .2, .1], [.8, .2, 0.]]),
    ]:
        fixture = {'name': name, 'vertices': first+second, 'triangles': [[0, 1, 2], [3, 4, 5]]}
        actual = inspect_ribbon(fixture)
        controls.append({'name': name, 'kind': 'Declared two-triangle synthetic intersection',
                         'fixture': fixture, 'observed': actual,
                         'status': 'passed' if actual['status'] == 'failed' else 'failed'})
    pair = sorted(['LOD0_PillarC_L', 'LOD0_RearBeltWeb_-1'])
    escaped = copy.deepcopy(intersections['|'.join(pair)])
    for point in escaped['vertices']:
        point[0] -= .060
    actual = convex_guide(rows['LOD0_RearBeltGuide_-1'], escaped)
    controls.append({'name': 'cloth-outside-convex-guide', 'kind': 'Actual complete intersection translated60mm in X',
                     'observed': actual, 'status': 'passed' if actual['status'] == 'failed' else 'failed'})
    return {'cloth_self_contact': self_checks, 'convex_guide_containment': guides,
            'negative_controls': controls,
            'status': 'passed' if all(row['status'] == 'passed' for row in self_checks+guides+controls) else 'failed'}
