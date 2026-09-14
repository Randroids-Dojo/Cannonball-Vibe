"""Finite foot diagonals; winding derives from the actual complete owner face.

A submicrometre native sliver can itself have an inverted geometric normal.
It cannot define the intended hemisphere for the replacement diagonal."""
import copy, math
from collections import Counter, defaultdict
from .boundary02 import sub, cross, dot
from endurance_sedan.boolean_surface import _candidates, _crossing_keys
from endurance_sedan.qa.self_geometry import scan

def area(row, face):
    a, b, c = [row['vertices'][v] for v in face]
    return math.hypot(*cross(sub(b, a), sub(c, a))) / 2

def defects(row):
    return [i for i, t in enumerate(row['triangles']) if area(row, t) <= 1e-12]

def repair(row, origins, original_member, actual_body):
    current = copy.deepcopy(row)
    initial = scan(current)
    bad = initial
    attempts = []
    accepted = []
    start_degenerate = defects(current)
    for _ in range(8):
        degenerate = defects(current)
        if not bad['bad_pairs'] and (not degenerate):
            return (current, {'status': 'passed', 'initial_exact_self': initial, 'initial_degenerate_triangles': start_degenerate, 'attempts': attempts, 'accepted': accepted, 'vertices_exact': current['vertices'] == row['vertices'], 'triangle_count_exact': len(current['triangles']) == len(row['triangles']), 'final_exact_self': bad, 'final_degenerate_triangles': []})
        work = {**current, 'polygons': current['triangles'], 'polygon_indices': list(range(len(current['triangles'])))}
        by_edge = defaultdict(list)
        for i, t in enumerate(current['triangles']):
            for a, b in zip(t, t[1:] + t[:1]):
                by_edge[tuple(sorted((a, b)))].append(i)
        changed = False
        for proposal in _candidates(work):
            a, b = proposal['edge']
            ids = by_edge[a, b]
            if len(ids) != 2 or origins[ids[0]] != origins[ids[1]]:
                continue
            if min((current['vertices'][v][2] for i in ids for v in current['triangles'][i])) > 1.011:
                continue
            t = current['triangles'][ids[0]]
            q = current['triangles'][ids[1]]
            if not any((t[k] == a and t[(k + 1) % 3] == b for k in range(3))):
                a, b = (b, a)
            if not any((q[k] == b and q[(k + 1) % 3] == a for k in range(3))):
                raise ValueError('Unexpected source edge winding')
            c = next((v for v in t if v not in (a, b)))
            d = next((v for v in q if v not in (a, b)))
            replacement = [[c, d, b], [d, c, a]]
            owner = origins[ids[0]]
            reference = original_member if owner > 0 else actual_body
            rp = [reference['vertices'][v] for v in reference['triangles'][abs(owner) - 1]]
            old_normal = cross(sub(rp[1], rp[0]), sub(rp[2], rp[0]))
            if owner < 0:
                old_normal = [-v for v in old_normal]
            if any((dot(old_normal, cross(sub(current['vertices'][u[1]], current['vertices'][u[0]]), sub(current['vertices'][u[2]], current['vertices'][u[0]]))) <= 0 for u in replacement)):
                continue
            trial = copy.deepcopy(current)
            for i, u in zip(ids, replacement):
                trial['triangles'][i] = u
            trial_degenerate = defects(trial)
            if len(trial_degenerate) > len(degenerate):
                continue
            check = scan(trial)
            previous_keys = _crossing_keys(current, bad)
            new_keys = _crossing_keys(trial, check)
            passed = new_keys <= previous_keys and (len(trial_degenerate) < len(degenerate) or new_keys < previous_keys)
            record = {**proposal, 'source_origin': origins[ids[0]], 'faces': ids, 'old_triangles': [t, q], 'new_triangles': replacement, 'degenerate_before': len(degenerate), 'degenerate_after': len(trial_degenerate), 'crossings_before': len(bad['bad_pairs']), 'crossings_after': len(check['bad_pairs']), 'accepted': passed}
            attempts.append(record)
            if passed:
                current = trial
                bad = check
                accepted.append(record)
                changed = True
                break
        if not changed:
            raise ValueError(('No strictly improving same-owner fixed-vertex foot diagonal', degenerate, bad, attempts))
    raise ValueError('Foot diagonal correction exceeded eight local operations')
