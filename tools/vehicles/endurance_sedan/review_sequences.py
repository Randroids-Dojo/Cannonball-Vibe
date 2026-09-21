"""Supplemental inspection cameras and saved-control sequences, in source meters.

This module has no Blender dependency. Wheel views use actual opened-source
anchor positions. These are review cameras, never construction inputs.
"""

import math


OPENINGS = (('Door_FL_open', 'front_door'),
            ('Door_FR_open', 'front_door_right'),
            ('Door_RL_open', 'rear_door'),
            ('Door_RR_open', 'rear_door_right'),
            ('Hood_Hinge_open', 'hood_context'),
            ('Trunk_Hinge_open', 'trunk_context'))
GRAZING_VIEWS = ('graze_front_left', 'graze_front_right',
                 'graze_side_left', 'graze_side_right',
                 'graze_rear_left', 'graze_rear_right')


def extra_views(views, wheel_centers):
    result = {}
    for original in ('front_door', 'rear_door', 'glass_seal', 'wiper_overview'):
        location, target, ortho = views[original]
        result[original + '_right'] = ((-location[0], *location[1:]),
                                      (-target[0], *target[1:]), ortho)
    result['hood_context'] = ((-2.6, 4.2, 2.1), (0, 1.35, 1.15), False)
    result['trunk_context'] = ((2.6, -4.8, 2.6), (0, -1.85, 1.1), False)
    for side, sign in (('left', -1), ('right', 1)):
        result['rear_glass_' + side] = ((sign*1.85, -3.1, 2.10),
                                       (sign*.53, -1.20, 1.32), False)
        result['rear_glass_cabin_' + side] = ((-sign*.32, -.75, 1.16),
                                             (sign*.50, -1.44, 1.21), False)
        for region, location, target in (
                ('front', (2.5, 3.2, 1.4), (.68, 1.82, .77)),
                ('side', (2.8, -.20, 1.35), (.94, -.20, .82)),
                ('rear', (2.6, -3.4, 2.9), (.50, -1.0, 1.40))):
            result[f'graze_{region}_{side}'] = (
                (sign*location[0], *location[1:]),
                (sign*target[0], *target[1:]), False)
    if set(wheel_centers) != {'FL', 'FR', 'RL', 'RR'}:
        raise ValueError('All four actual source wheel centers are required')
    for suffix, center in wheel_centers.items():
        if len(center) != 3 or not all(math.isfinite(x) for x in center):
            raise ValueError('Invalid actual wheel center')
        sign = -1 if suffix.endswith('L') else 1
        x, y, z = center
        result['wheel_oblique_' + suffix] = ((x+sign*1.15, y+.70, z+.38),
                                             tuple(center), False)
        # Look outward from below the inner barrel. Ground is hidden for this
        # explicit underside camera; every vehicle mesh remains visible.
        inward = .45 if suffix.startswith('F') else .30
        result['wheel_inner_' + suffix] = ((x-sign*inward, y, -.15),
                                           tuple(center), False)
    return result


def shot_phase(index, frames, shot_count):
    if frames < 2*shot_count or not 0 <= index < frames:
        raise ValueError('Each inspection shot requires at least two frames')
    shot = min(shot_count-1, index*shot_count//frames)
    first = math.ceil(shot*frames/shot_count)
    last = math.ceil((shot+1)*frames/shot_count)-1
    return shot, (index-first)/(last-first)


def partial_return(phase):
    """Reverse below full opening, reopen, then return fully closed."""
    if not 0 <= phase <= 1:
        raise ValueError('Invalid opening phase')
    knots = ((0., 0.), (.28, .65), (.45, .20), (.75, .80), (1., 0.))
    for (a, va), (b, vb) in zip(knots, knots[1:]):
        if phase <= b:
            t = (phase-a)/(b-a)
            return va+(vb-va)*t*t*(3-2*t)
    raise AssertionError('Unreachable opening phase')


def supplemental_jobs(sequence, frames, fps, source_fps, timeline_rate, views):
    if sequence not in ('grazing', 'partial-openings'):
        raise ValueError('Unknown supplemental sequence')
    jobs = []
    for index in range(frames):
        shot, phase = shot_phase(index, frames, 6)
        if sequence == 'grazing':
            view = GRAZING_VIEWS[shot]
            controls = {}
        else:
            control, view = OPENINGS[shot]
            controls = {key: partial_return(phase) if key == control else 0.
                        for key, _ in OPENINGS}
        jobs.append((f'{index+1:06d}', *views[view],
                     1+index*source_fps/fps*timeline_rate, controls, view))
    return jobs
