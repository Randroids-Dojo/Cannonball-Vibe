"""Measure the rear optical frame's exact named mating faces and other gaps."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_minimum import Distances

GUARD = 1e-6


def clip_x(polygon, low, high):
    result = [np.asarray(point, dtype=float) for point in polygon]
    for value, sign in ((low, 1), (high, -1)):
        old, result = result, []
        if not old:
            break
        for a, b in zip(old, old[1:] + old[:1]):
            da, db = sign * (a[0] - value), sign * (b[0] - value)
            if da >= 0:
                result.append(a)
            if (da < 0) != (db < 0):
                result.append(a + (b - a) * da / (da - db))
    return result


def profile_separator(wall, other):
    """Each actual X slab uses the upper wall's actual lower-face plane.

    All wall triangles must lie above it and all other triangles below it.
    Clipping triangles at every slab boundary makes this a complete surface
    proof, rather than a vertex-only test across different tessellations.
    """
    wv = np.asarray(wall['vertices'], dtype=float)
    ov = np.asarray(other['vertices'], dtype=float)
    wt, ot = wv[np.asarray(wall['triangles'])], ov[np.asarray(other['triangles'])]
    stations = sorted(set(float(x) for x in wv[:, 0]))
    # The declared 4 mm wall's lower rear/front edges are at .916/.926 m.
    mask = np.minimum(abs(wv[:, 2] - .916), abs(wv[:, 2] - .926)) < GUARD
    lower_triangles = [tri for indices, tri in zip(wall['triangles'], wt) if all(mask[i] for i in indices)]
    assert len(lower_triangles) == 2 * (len(stations) - 1), 'Upper wall lower-face inventory mismatch'
    records = []
    for low, high in zip(stations, stations[1:]):
        candidates = [tri for tri in lower_triangles if tri[:, 0].min() >= low - 1e-10
                      and tri[:, 0].max() <= high + 1e-10]
        assert len(candidates) == 2
        tri = candidates[0]
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        normal /= np.linalg.norm(normal)
        if normal[2] < 0:
            normal = -normal
        assert normal[2] > .8, 'Expected a mostly horizontal formed wall seating plane'
        constant = float(normal @ tri[0])
        lows, highs, contact_area = [], [], 0.
        worst_above = worst_below = None
        for triangles, is_wall in ((wt, True), (ot, False)):
            for triangle in triangles:
                if triangle[:, 0].max() < low or triangle[:, 0].min() > high:
                    continue
                polygon = clip_x(triangle, low, high)
                if not polygon:
                    continue
                values = [float(normal @ point - constant) for point in polygon]
                if is_wall:
                    lows.extend(values)
                    if worst_below is None or min(values) < worst_below['signed_distance_m']:
                        i = int(np.argmin(values))
                        worst_below = {'point_m': polygon[i].tolist(), 'signed_distance_m': values[i]}
                else:
                    highs.extend(values)
                    if worst_above is None or max(values) > worst_above['signed_distance_m']:
                        i = int(np.argmax(values))
                        worst_above = {'point_m': polygon[i].tolist(), 'signed_distance_m': values[i]}
                    if len(polygon) >= 3 and max(abs(value) for value in values) <= GUARD:
                        contact_area += sum(float(np.linalg.norm(np.cross(polygon[i] - polygon[0], polygon[i + 1] - polygon[0]))) / 2
                                            for i in range(1, len(polygon) - 1))
        records.append({'x_interval_m': [low, high], 'normal': normal.tolist(), 'plane_constant': constant,
                        'wall_min_signed_m': min(lows), 'other_max_signed_m': max(highs) if highs else None,
                        'wall_worst': worst_below, 'other_worst': worst_above,
                        'other_coplanar_face_area_m2': contact_area})
    failure = any(row['wall_min_signed_m'] < -GUARD or (row['other_max_signed_m'] is not None and row['other_max_signed_m'] > GUARD) for row in records)
    return {'method': 'Actual lower-wall plane per X slab; all actual triangles clipped at every slab boundary',
            'status': 'failed' if failure else 'passed', 'slabs': records,
            'maximum_other_intrusion_m': max(0., max(row['other_max_signed_m'] for row in records if row['other_max_signed_m'] is not None)),
            'maximum_wall_below_plane_m': max(0., -min(row['wall_min_signed_m'] for row in records)),
            'coplanar_other_area_m2': sum(row['other_coplanar_face_area_m2'] for row in records)}


def axis_separator(first, second, axis, plane, first_sign):
    a = np.asarray(first['vertices'], dtype=float)[:, axis]
    b = np.asarray(second['vertices'], dtype=float)[:, axis]
    agap, bgap = first_sign * (a - plane), -first_sign * (b - plane)
    return {'method': 'Whole closed solids lie in opposite axis-aligned half-spaces',
            'axis': axis, 'plane_m': plane, 'first_half_space_sign': first_sign,
            'first_min_signed_m': float(agap.min()), 'second_min_signed_m': float(bgap.min()),
            'status': 'passed' if min(agap.min(), bgap.min()) >= -GUARD else 'failed'}


def inspect(rows):
    names = []
    rules = {}
    def register(a, b, method):
        key = tuple(sorted((a, b)))
        assert key not in rules
        rules[key] = (a, b, method)
    for side, cx in (('L', -.650), ('R', .650)):
        housing, cover = f'LOD0_TaillightHousing_{side}', f'LOD0_TaillightCover_{side}'
        bottom, top = f'LOD0_TaillightWall_{side}0.808', f'LOD0_TaillightWall_{side}0.928'
        returns = [f'LOD0_TaillightSideReturn_{side}{sign}' for sign in (-1, 1)]
        names += [housing, cover, bottom, top, *returns,
                  f'LOD0_TailGuide_{side}-0.036', f'LOD0_TailGuide_{side}0.036',
                  f'LOD0_BrakeEmitter_{side}', f'LOD0_ReverseEmitter_{side}', f'LOD0_RearIndicator_{side}']
        for other in (housing, cover, *returns):
            register(bottom, other, ('axis', 2, .810, -1))
            register(top, other, ('profile',))
        for sign, return_name in zip((-1, 1), returns):
            for other in (housing, cover):
                register(return_name, other, ('axis', 0, cx + sign * .207, sign))
    assert all(name in rows for name in names), 'Required rear optical mesh absent'
    distances = Distances(rows)
    results = []
    for a, b in itertools.combinations(names, 2):
        minimum = distances.minimum(a, b)
        key = tuple(sorted((a, b)))
        if key in rules:
            first, second, method = rules[key]
            bound = (profile_separator(rows[first], rows[second]) if method[0] == 'profile'
                     else axis_separator(rows[first], rows[second], *method[1:]))
            status = bound['status']
            if minimum['distance_m'] > GUARD:
                status = 'failed_missing_declared_seat'
            results.append({'pair': [a, b], 'rule': 'Named rear optical frame seated interface',
                            'status': status, 'minimum': minimum, 'separating_bound': bound})
        else:
            results.append({'pair': [a, b], 'rule': 'Unrelated optical parts: 1 mm plus 1 um numeric guard',
                            'status': 'passed' if minimum['distance_m'] >= .001 + GUARD else 'failed_clearance',
                            'minimum': minimum})
    return {'status': 'passed' if all(row['status'] == 'passed' for row in results) else 'failed',
            'pair_count': len(results), 'named_interface_count': len(rules), 'pairs': results,
            'failure_count': sum(row['status'] != 'passed' for row in results)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--geometry', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert not args.output.exists()
    data = json.loads(gzip.decompress(args.geometry.read_bytes()))
    result = inspect(data['meshes'])
    result.update(task_id='P1-018', milestone='M5', utc=datetime.now(timezone.utc).isoformat(),
                  source_sha256=data['source_sha256'], numeric_plane_guard_m=GUARD,
                  inputs=[{'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                          for path in (args.geometry, Path(__file__), Path(__file__).with_name('surface_minimum.py'),
                                       Path(__file__).with_name('geometry.py'))],
                  limits='Actual rear optical internal geometry only. Source revision and candidate scope follow exact input bytes. Body, openings, export, runtime lights and human review require separate evidence.',
                  human_approval_reference=None)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({key: result[key] for key in ('status', 'pair_count', 'named_interface_count', 'failure_count')}), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
