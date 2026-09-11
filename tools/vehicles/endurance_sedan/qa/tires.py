"""Conservative tire/body certificates over roll, steer, travel and openings.

The rotational support envelope contains actual tread and sipe triangles. Target
triangles and independent opening intervals are subdivided until a positive
lower bound succeeds. A sample, an AABB overlap or an exhausted budget never
counts as a clearance pass.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np


def box_gap(a, b):
    return float(np.linalg.norm(np.maximum(np.maximum(a[0] - b[1], b[0] - a[1]), 0)))


def triangle_inner_radius(points):
    """Exact double-precision distance from the axle to a projected triangle."""
    a, b, c = points
    cross = lambda u, v: float(u[0]*v[1]-u[1]*v[0])
    area = cross(b-a,c-a)
    if abs(area) > 1e-18:
        signs = [cross(b-a,-a),cross(c-b,-b),cross(a-c,-c)]
        if all(s >= 0 for s in signs) or all(s <= 0 for s in signs):
            return 0.
    minimum = math.inf
    for p, q in ((a,b),(b,c),(c,a)):
        edge = q-p; length = float(edge@edge)
        t = min(1.,max(0.,-float(p@edge)/length)) if length else 0.
        minimum = min(minimum,float(np.linalg.norm(p+t*edge)))
    return minimum


def scalar_range(c, x, y, low, high):
    values = [c + x * math.cos(t) + y * math.sin(t) for t in (low, high)]
    phase = math.atan2(y, x)
    for k in range(math.floor((low - phase) / math.pi) - 1,
                   math.ceil((high - phase) / math.pi) + 2):
        t = phase + k * math.pi
        if low <= t <= high:
            values.append(c + x * math.cos(t) + y * math.sin(t))
    return min(values), max(values)


def coefficients(points, group):
    if group is None:
        return None
    axis = np.asarray(group['axis_source']); pivot = np.asarray(group['pivot_source_m'])
    u = points - pivot
    parallel = (u @ axis)[:, None] * axis
    return pivot + parallel, u - parallel, np.cross(axis, u)


def swept_box(points, group):
    if group is None:
        return points.min(axis=0), points.max(axis=0)
    c, x, y = coefficients(points, group)
    low, high = sorted((0, group['factor_rad']))
    ranges = np.asarray([[scalar_range(c[i, j], x[i, j], y[i, j], low, high)
                          for j in range(3)] for i in range(len(points))])
    return ranges[:, :, 0].min(axis=0), ranges[:, :, 1].max(axis=0)


def outside_solid(vertices, triangles, candidates, guard):
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    for index, point in enumerate(candidates):
        if np.any(point < low - guard) or np.any(point > high + guard):
            return {'tire_vertex': index, 'source_m': point.tolist(), 'method': 'outside-target-aabb'}
    surface = vertices[triangles]; edge1 = surface[:, 1] - surface[:, 0]; edge2 = surface[:, 2] - surface[:, 0]
    for index in range(min(len(candidates), 64)):
        point = candidates[index]; counts = []; ambiguous = False
        for raw in ((1, .371, .173), (-.219, 1, .413), (.337, -.183, 1)):
            direction = np.asarray(raw) / np.linalg.norm(raw)
            h = np.cross(direction, edge2); determinant = np.einsum('ij,ij->i', edge1, h)
            usable = np.abs(determinant) > 1e-12
            inv = np.divide(1., determinant, out=np.zeros_like(determinant), where=usable)
            s = point - surface[:, 0]; u = inv * np.einsum('ij,ij->i', s, h)
            q = np.cross(s, edge1); v = inv * (q @ direction); t = inv * np.einsum('ij,ij->i', edge2, q)
            hits = usable & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-8)
            if np.any(hits & ((u < 1e-8) | (v < 1e-8) | (u + v > 1 - 1e-8))):
                ambiguous = True; break
            counts.append(int(hits.sum()))
        if not ambiguous and len(counts) == 3 and all(c % 2 == 0 for c in counts):
            return {'tire_vertex': index, 'source_m': point.tolist(), 'method': 'three-ray-parity', 'counts': counts}
    return None


def certify(vertices, triangles, group, wheel, max_cells):
    # Each cell has its own triangle and independent target-opening interval.
    pending = [(vertices[t], 0., 1. if group else 0., 0) for t in triangles]
    support = wheel['support']; center = wheel['center']; yaw = wheel['angles']
    cos = np.cos(yaw); sin = np.sin(yaw); droop, bump = wheel['travel']
    guard = wheel['guard']; required = wheel['required']; cells = leaves = 0
    minimum = math.inf; maximum_depth = 0
    while pending:
        batch = pending[-256:]; del pending[-len(batch):]
        cells += len(batch)
        if cells > max_cells:
            return {'status': 'unresolved', 'reason': 'bounded-work-limit', 'cells': cells, 'remaining': len(pending) + len(batch)}
        raw = np.stack([r[0] for r in batch]); middle = raw.mean(axis=1)
        triangle_radius = np.linalg.norm(raw - middle[:, None, :], axis=2).max(axis=1)
        target_error = np.zeros(len(batch))
        if group:
            axis = np.asarray(group['axis_source']); pivot = np.asarray(group['pivot_source_m'])
            u = middle - pivot; parallel = (u @ axis)[:, None] * axis
            angles = np.asarray([(r[1] + r[2]) / 2 * group['factor_rad'] for r in batch])
            middle = pivot + parallel + (u - parallel) * np.cos(angles)[:, None] + np.cross(axis, u) * np.sin(angles)[:, None]
            radii = np.linalg.norm(np.cross(axis, raw - pivot), axis=2).max(axis=1)
            target_error = 2 * radii * np.sin(np.asarray([abs(group['factor_rad']) * (r[2] - r[1]) / 4 for r in batch]))
        rel = middle - center
        axial = rel[:, 0, None] * cos + rel[:, 1, None] * sin
        tangent = -rel[:, 0, None] * sin + rel[:, 1, None] * cos
        vertical = np.maximum(np.maximum(droop - rel[:, 2], rel[:, 2] - bump), 0)
        radial = np.sqrt(tangent ** 2 + vertical[:, None] ** 2)
        distance = np.full_like(radial, -np.inf)
        for a, b, c in support:
            np.maximum(distance, (a * np.abs(axial) + b * radial - c) / math.hypot(a, b), out=distance)
        # Axles can lie inside the real tire's empty central bore. This is an
        # independently measured inner surface bound, not an exclusion. Use the
        # furthest suspension endpoint for a lower bound valid over all travel.
        maximum_vertical = np.maximum(np.abs(droop-rel[:,2]),np.abs(bump-rel[:,2]))
        bore_gap = wheel['inner_radius'] - np.sqrt(tangent**2+maximum_vertical[:,None]**2)
        np.maximum(distance,bore_gap,out=distance)
        distance = distance.min(axis=1)
        bound = distance - triangle_radius - wheel['angular_error'] - target_error - guard
        accepted = bound >= required
        if np.any(accepted):
            leaves += int(accepted.sum()); minimum = min(minimum, float(bound[accepted].min()))
        for i in np.flatnonzero(~accepted):
            tri, lo, hi, depth = batch[i]; maximum_depth = max(maximum_depth, depth)
            if depth >= 28 or (triangle_radius[i] < .000025 and target_error[i] < .000025):
                return {'status': 'unresolved', 'reason': 'support-envelope-or-numeric-limit', 'cells': cells,
                        'target_point_source_m': middle[i].tolist(), 'opening_interval': [lo, hi],
                        'lower_bound_m': float(bound[i]), 'center_support_distance_m': float(distance[i]),
                        'triangle_radius_m': float(triangle_radius[i]), 'opening_displacement_m': float(target_error[i]),
                        'yaw_displacement_m': wheel['angular_error'], 'depth': depth}
            if group and target_error[i] > triangle_radius[i] * .6:
                mid = (lo + hi) / 2
                pending.extend(((tri, lo, mid, depth + 1), (tri, mid, hi, depth + 1)))
            else:
                a, b, c = tri; ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
                pending.extend((np.asarray(v), lo, hi, depth + 1) for v in
                               ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
    outside = outside_solid(vertices, triangles, wheel['actual_points'], guard)
    if outside is None:
        return {'status': 'unresolved', 'reason': 'whole-containment-not-excluded', 'lower_bound_m': minimum}
    return {'status': 'continuous-bound-certified', 'lower_bound_m': minimum,
            'cells': cells, 'leaves': leaves, 'maximum_depth': maximum_depth, 'outside_target_witness': outside}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--input', type=Path, required=True)
    p.add_argument('--drivers', type=Path, required=True); p.add_argument('--openings', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--max-cells-per-pair', type=int, default=300000)
    p.add_argument('--yaw-step-deg', type=float, default=.25)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert not args.output.exists() and 0 < args.yaw_step_deg <= .25
    start = time.perf_counter(); utc = datetime.now(timezone.utc).isoformat()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    data = json.loads(gzip.decompress(args.input.read_bytes()))
    drivers = json.loads(args.drivers.read_text()); openings = json.loads(args.openings.read_text())
    assert drivers['status'] == openings['status'] == 'passed'
    assert drivers['source_sha256'] == openings['source_sha256'] == data['source_sha256']
    rows = {n:r for n,r in data['meshes'].items() if r['properties'].get('source_preview_only') is not True}
    groups = {r['name']: r for r in openings['opening_groups']}
    membership = {n:next((g for g in r['ancestors'] if g in groups), None) for n,r in rows.items()}
    boxes = {n:swept_box(np.asarray(r['vertices']), groups.get(membership[n])) for n,r in rows.items()}
    output = []; required = .005; guard = .000001
    for contract in drivers['tires']:
        suffix = contract['wheel']; center = np.asarray(contract['center_source_m'])
        assert contract['roll_axis_local'] == [1,0,0] and contract['travel_axis_source'] == [0,0,1]
        included = [n for n in rows if n == 'LOD0_Tire_' + suffix or n.startswith('LOD0_ShoulderSipe_' + suffix + '_')]
        assert 'LOD0_Tire_' + suffix in included
        points = np.concatenate([np.asarray(rows[n]['vertices']) for n in included])
        local = points - center; axial = np.abs(local[:,0]); radial = np.linalg.norm(local[:,1:], axis=1)
        half, radius = float(axial.max()), float(radial.max())
        assert radius <= .3438 and half <= .128
        inner = math.inf
        for n in included:
            projected = (np.asarray(rows[n]['vertices'])-center)[np.asarray(rows[n]['triangles'])][:,:,1:]
            inner = min(inner,min(triangle_inner_radius(t) for t in projected))
        assert inner > .1, 'Actual tire triangle enters its expected empty hub bore.'
        # Dense support directions contain every vertex and every edge/face by convexity.
        slopes = [(math.cos(t), math.sin(t)) for t in np.linspace(0, math.pi/2, 33)]
        support = [(a,b,float((a*axial+b*radial).max())) for a,b in slopes]
        limit = abs(contract['yaw_factor_rad'])
        intervals = max(1, math.ceil(math.degrees(2*limit) / args.yaw_step_deg))
        angles = np.linspace(-limit,limit,intervals+1) if limit else np.asarray([0.])
        yaw_gap = (2*limit / intervals) if limit else 0.
        angular_error = 2 * math.hypot(half,radius) * math.sin(yaw_gap/4)
        travel = contract['continuous_travel_m']; sphere = math.hypot(half,radius)
        wheel_box = (center + np.asarray([-sphere,-sphere,-radius+travel[0]]),
                     center + np.asarray([sphere,sphere,radius+travel[1]]))
        omitted = [n for n,r in rows.items() if 'Suspension_' + suffix in r['ancestors']]
        assert all(n in omitted for n in included)
        context = {'support':support,'center':center,'angles':angles,'travel':travel,
                   'angular_error':angular_error,'guard':guard,'required':required,'actual_points':points,
                   'inner_radius':inner}
        checks = []; broad = []
        for n,r in rows.items():
            if n in omitted: continue
            gap = box_gap(wheel_box, boxes[n])
            if gap >= required + guard:
                broad.append({'part':n,'lower_bound_m':gap-guard}); continue
            result = certify(np.asarray(r['vertices']), np.asarray(r['triangles']),
                             groups.get(membership[n]), context, args.max_cells_per_pair)
            result.update({'part':n,'independent_opening':membership[n]}); checks.append(result)
            print('QA_TIRE_PAIR '+json.dumps({'wheel':suffix,**result}),flush=True)
        output.append({'wheel':suffix,'center_source_m':center.tolist(),'outer_radius_m':radius,'half_width_m':half,
                       'inner_surface_radius_lower_bound_m':inner,
                       'support_envelope':support,'included_tread_sipe_meshes':included,'yaw_range_rad':[-limit,limit],
                       'yaw_sample_count':len(angles),'inter_sample_displacement_m':angular_error,
                       'continuous_travel_m':travel,'continuous_roll_rad':[0,2*math.pi],
                       'coassembly_meshes_outside_body_clearance_scope':omitted,
                       'entire_domain_aabb_certificates':broad,'refined_pairs':checks})
    failures = [{'wheel':r['wheel'],**c} for r in output for c in r['refined_pairs'] if c['status']!='continuous-bound-certified']
    report = {'task_id':'P1-018','milestone':'M5','start_utc':utc,'end_utc':datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds':time.perf_counter()-start,'source_sha256':data['source_sha256'],
              'inputs':[{'path':str(p),'sha256':sha(p)} for p in (args.input,args.drivers,args.openings,Path(__file__))],
              'required_m':required,'guard_m':guard,'numpy':np.__version__,'results':output,'failures':failures,
              'status':'passed' if not failures else 'unresolved','human_approval_reference':None,
              'method':'Actual tread/sipe convex outer supports and exact projected-triangle inner-radius bounds contain the full rolling annular geometry, including its measured empty axle bore. Suspension is eliminated analytically, using the closest endpoint for outer supports and furthest endpoint for inner-radius clearance. Steering samples include a conservative inter-sample Hausdorff bound. Every independently moving target has its own full opening interval; triangle-radius and rigid-point displacement bounds cover all intermediate positions. Three-ray exterior classification excludes whole containment.',
              'limits':'Tread/sipe versus all other vehicle assemblies including independent six-opening motion. Each exact same-wheel suspension/brake/rim coassembly is individually listed outside this body-clearance domain and needs internal assembly QA. Wipers are at rest; disjoint swept boxes or the separate wiper certificate must cover their motion. An unresolved sufficient bound is not proof of a collision and is never a pass.'}
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('QA_TIRES_COMPLETE '+json.dumps({'status':report['status'],'unresolved':len(failures)}),flush=True)
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
