"""Complete finite header, fitted latch and sewn upholstery interfaces.

This read-only stage consumes evaluated source triangles. It does not excuse
other contacts, establish individual-mesh self validity, or approve appearance.
All uncovered fragments and incomplete route intervals fail the stage.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exact_triangles
import finish_report
import precision
import wiper_initial
from precision import point_triangle, split_halfspace, subtract_prism

GUARD = 1e-6
HEADER_Y = float(np.float32(.1051))
HEADER_BOX = ((.682, 1.342), (.697, 1.392))  # |X|, Z, finite section envelope.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unit(vector):
    vector = np.asarray(vector, dtype=float)
    length = float(np.linalg.norm(vector))
    require(np.isfinite(vector).all() and length > 0, 'Finite nonzero direction required')
    return vector / length


def triangles(row):
    return np.asarray(row['vertices'], dtype=float)[np.asarray(row['triangles'], dtype=int)]


def subset(row, ids, suffix):
    return {**row, 'name': row['name'] + suffix,
            'triangles': [row['triangles'][int(i)] for i in ids]}


def validate_row(name, row):
    require(isinstance(row, dict) and row.get('name') == name, 'Mesh name/key mismatch: ' + name)
    vertices, faces = row.get('vertices'), row.get('triangles')
    require(isinstance(vertices, list) and len(vertices) >= 4 and isinstance(faces, list) and faces,
            'Nonempty closed mesh required: ' + name)
    for point in vertices:
        require(isinstance(point, list) and len(point) == 3
                and all(type(v) in (int, float) and math.isfinite(v) for v in point),
                'Invalid finite vertex: ' + name)
    for face in faces:
        require(isinstance(face, list) and len(face) == 3
                and all(type(i) is int and 0 <= i < len(vertices) for i in face)
                and len(set(face)) == 3, 'Invalid triangle: ' + name)
    points = triangles(row)
    areas = np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1) / 2
    require(np.isfinite(areas).all() and np.min(areas) > 1e-12, 'Invalid triangle area: ' + name)
    edges = Counter((a, b) for face in faces for a, b in zip(face, face[1:] + face[:1]))
    require(all(count == 1 and edges[(b, a)] == 1 for (a, b), count in edges.items()),
            'Open, nonmanifold or inconsistently wound mesh: ' + name)
    require(len({tuple(sorted(face)) for face in faces}) == len(faces), 'Duplicate triangle: ' + name)
    require(isinstance(row.get('properties'), dict), 'Mesh properties required: ' + name)


def partition(poly, planes):
    """Shared precision.split_halfspace; keep every uncovered convex piece."""
    remaining = []
    for normal, constant in planes:
        poly, outside = split_halfspace(poly, normal, constant)
        if outside:
            remaining.append(outside)
        if not poly:
            break
    return poly, remaining


def polygon_planes(poly, normal):
    return [(unit(np.cross(normal, b - a)), float(unit(np.cross(normal, b - a)) @ a))
            for a, b in zip(poly, poly[1:] + poly[:1]) if np.linalg.norm(b - a) > 0]


def edge_neighborhoods(triangle, maximum):
    """Finite boxes wholly inside the Euclidean edge/vertex neighborhoods."""
    normal = unit(np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0]))
    edge_margin, vertex_margin = maximum/math.sqrt(2)-1e-9, maximum/math.sqrt(3)-1e-9
    regions = []
    for a, b in zip(triangle, np.roll(triangle, -1, axis=0)):
        tangent = unit(b-a)
        across = unit(np.cross(normal, tangent))
        planes = [(tangent, float(tangent @ a)), (-tangent, -float(tangent @ b))]
        for axis in (across, normal):
            planes.extend([(axis, float(axis @ a)-edge_margin), (-axis, -float(axis @ a)-edge_margin)])
        regions.append(planes)
    for point in triangle:
        regions.append([(sign*axis, float(sign*axis @ point)-vertex_margin)
                        for axis in np.eye(3) for sign in (-1, 1)])
    return regions


def surface_cover(mesh, target, maximum=GUARD):
    """Complete triangle-prism subtraction, as in solid_interfaces.boundary_shell.

    Kept pure NumPy here so the same entry point runs under pinned Blender or a
    CPU reader. Reuses precision's original full convex partition functions.
    A convex distance bound discharges tiny residual polygons, never their area.
    """
    other = triangles(target)
    low, high = other.min(1), other.max(1)
    cells, worst = 0, 0.
    for index, tri in enumerate(triangles(mesh)):
        selected = np.flatnonzero(np.all(low <= tri.max(0) + maximum, axis=1)
                                  & np.all(high >= tri.min(0) - maximum, axis=1))
        remaining = [list(tri)]
        for face in selected:
            todo = []
            for poly in remaining:
                cells += 1
                bound = max(float(np.linalg.norm(p - point_triangle(p, other[face]))) for p in poly)
                if bound <= maximum - 1e-9:
                    worst = max(worst, bound)
                    continue
                outside, covered = subtract_prism(poly, other[face], maximum - 1e-9)
                todo.extend(outside)
                if covered:
                    normal = unit(np.cross(other[face, 1] - other[face, 0], other[face, 2] - other[face, 0]))
                    worst = max(worst, *(abs(float((p - other[face, 0]) @ normal)) for p in covered))
            remaining = todo
            if not remaining:
                break
            if cells >= 100000 or len(remaining) > 5000:
                return {'status': 'unresolved', 'triangle': index, 'cells': cells}
        # Full edge and vertex neighborhoods resolve long boundary strips that
        # cross several target facets. A single nearest-triangle bound cannot
        # certify such strips, even when every point is only nanometers away.
        for face in selected:
            if not remaining:
                break
            for planes in edge_neighborhoods(other[face], maximum):
                todo = []
                for poly in remaining:
                    cells += 1
                    covered, outside = partition(poly, planes)
                    todo.extend(outside)
                    if covered:
                        worst = max(worst, maximum)
                remaining = todo
                if not remaining:
                    break
                if cells >= 100000 or len(remaining) > 5000:
                    return {'status': 'unresolved', 'triangle': index, 'cells': cells}
        uncovered = []
        for poly in remaining:
            bound = min((max(float(np.linalg.norm(p - point_triangle(p, other[face]))) for p in poly)
                         for face in selected), default=math.inf)
            if bound > maximum:
                uncovered.append([p.tolist() for p in poly])
            else:
                worst = max(worst, bound)
        if uncovered:
            return {'status': 'failed', 'triangle': index, 'cells': cells, 'uncovered': uncovered}
    return {'status': 'passed', 'full_triangles': len(mesh['triangles']), 'cells': cells,
            'maximum_certified_surface_distance_m': worst}


def hull2(points):
    values = sorted(set(tuple(map(float, point[:2])) for point in points))
    require(len(values) >= 3, 'Finite planar footprint required')
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    halves = []
    for ordered in (values, list(reversed(values))):
        half = []
        for point in ordered:
            while len(half) >= 2 and cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return [np.array([*point, 0.]) for point in halves[0] + halves[1]]


def prism_planes(poly, low, high):
    return polygon_planes(poly, np.array([0., 0., 1.])) + [
        (np.array([0., 0., 1.]), low), (np.array([0., 0., -1.]), -high)]


def rounded(width, height, radius, z=0.):
    result = []
    for x, y, start in ((width/2-radius, height/2-radius, 0),
                        (-width/2+radius, height/2-radius, 90),
                        (-width/2+radius, -height/2+radius, 180),
                        (width/2-radius, -height/2+radius, 270)):
        for i in range(3):
            angle = math.radians(start + 45*i)
            result.append(np.array([x+radius*math.cos(angle), y+radius*math.sin(angle), z]))
    return result


def polygon_mesh(polygons, name):
    vertices, faces = [], []
    for polygon in polygons:
        offset = len(vertices)
        vertices.extend([list(map(float, point)) for point in polygon])
        for i in range(1, len(polygon)-1):
            p = np.array([polygon[0], polygon[i], polygon[i+1]])
            if np.linalg.norm(np.cross(p[1]-p[0], p[2]-p[0])) > 0:
                faces.append([offset, offset+i, offset+i+1])
    require(faces, 'Positive-area finite surface required: ' + name)
    return {'name': name, 'vertices': vertices, 'triangles': faces}


def contract(row, key):
    value = row['properties'].get(key)
    require(isinstance(value, str), 'Missing finite interface contract: ' + row['name'] + '/' + key)
    result = strict_json(value)
    require(isinstance(result, dict), 'Object contract required')
    return result


def frame(normal):
    normal = unit(normal)
    x = np.array([1., 0., 0.])
    x = unit(x - normal*(x @ normal))
    return np.array([x, unit(np.cross(normal, x)), normal])


def local(row, origin, axes):
    return {**row, 'vertices': ((np.array(row['vertices']) - origin) @ axes.T).tolist()}


def cap(row, axis, plane):
    points = triangles(row)
    ids = np.flatnonzero(np.max(np.abs(points[:, :, axis] - plane), axis=1) <= GUARD)
    require(len(ids) > 0, 'Missing finite cap: ' + row['name'])
    return subset(row, ids, '_cap'), ids


def header_joint(rows, side):
    a, b = (rows[name] for name in ('LOD0_PillarA_' + side, 'LOD0_RoofSideRail_' + side))
    for row in (a, b):
        value = row['properties'].get('a_header_finite_butt_y_m')
        require(type(value) in (int, float) and math.isfinite(value) and abs(value - HEADER_Y) <= GUARD,
                'Missing or changed finite header plane: ' + row['name'])
    av, bv = np.array(a['vertices']), np.array(b['vertices'])
    ac, ai = cap(a, 1, HEADER_Y)
    bc, bi = cap(b, 1, HEADER_Y)
    normals = [np.cross(triangles(c)[:, 1]-triangles(c)[:, 0], triangles(c)[:, 2]-triangles(c)[:, 0]) for c in (ac, bc)]
    normals = [n/np.linalg.norm(n, axis=1)[:, None] for n in normals]
    points = np.concatenate([triangles(ac).reshape(-1, 3), triangles(bc).reshape(-1, 3)])
    outside = max(float(np.max(HEADER_BOX[0][0]-np.abs(points[:, 0]))),
                  float(np.max(np.abs(points[:, 0])-HEADER_BOX[1][0])),
                  float(np.max(HEADER_BOX[0][1]-points[:, 2])),
                  float(np.max(points[:, 2]-HEADER_BOX[1][1])))
    halves = bool(av[:, 1].min() >= HEADER_Y-GUARD and bv[:, 1].max() <= HEADER_Y+GUARD)
    opposite = bool(np.all(normals[0][:, 1] < -.999999) and np.all(normals[1][:, 1] > .999999))
    coverage = [surface_cover(ac, bc), surface_cover(bc, ac)]
    return {'kind': 'header_butt', 'pair': [a['name'], b['name']], 'plane_y_m': HEADER_Y,
            'finite_abs_x_z_box_m': HEADER_BOX, 'finite_region_residual_m': outside,
            'entire_opposite_halfspaces': halves, 'opposite_geometric_cap_normals': opposite,
            'cap_triangle_indices': [ai.tolist(), bi.tolist()], 'complete_cap_coverage': coverage,
            'status': 'passed' if halves and opposite and outside <= GUARD
                      and all(q['status'] == 'passed' for q in coverage) else 'failed'}


def housing_joint(rows, suffix):
    housing, panel = rows['LOD0_DoorLatch_' + suffix], rows['LOD0_Door_' + suffix]
    c = contract(housing, 'fitted_latch_seat')
    for key, expected in (('body_size_m', [.026, .050, .017]), ('flange_size_m', [.034, .060]),
                          ('socket_size_m', [.027, .051])):
        require(c.get(key) == expected, 'Changed latch dimensions: ' + key)
    require(c.get('flange_seat_overlap_m') == .0002, 'Changed latch flange overlap')
    axes, origin = frame(c['outward_normal']), np.array(c['center_m'])
    h, p = local(housing, origin, axes), local(panel, origin, axes)
    hv = np.array(h['vertices'])
    body = (hv[:, 2] < -.0002-GUARD) | ((hv[:, 2] <= -.0002+GUARD)
           & (np.abs(hv[:, 0]) <= .013+GUARD) & (np.abs(hv[:, 1]) <= .025+GUARD))
    require(body.sum() >= 24, 'Missing full housing body rings')
    require(np.max(np.abs(hv[:, 0])) <= .017+GUARD and np.max(np.abs(hv[:, 1])) <= .030+GUARD
            and hv[:, 2].min() >= -.017-GUARD and hv[:, 2].max() <= .0015+GUARD, 'Housing outside declared finite envelope')
    bodyplanes = prism_planes(hull2(hv[body]), float(hv[body, 2].min()), float(hv[body, 2].max()))
    flangeplanes = prism_planes(rounded(.034, .060, .003), -.0002, .0015)
    bodyfragments, flangefragments = [], []
    for i, tri in enumerate(triangles(p)):
        poly, _ = partition(list(tri), [(n, d-GUARD) for n, d in bodyplanes])
        if poly:
            bodyfragments.append({'panel_triangle': i, 'polygon_m': [v.tolist() for v in poly]})
        poly, _ = partition(list(tri), [(n, d-GUARD) for n, d in flangeplanes])
        if poly:
            flangefragments.append({'panel_triangle': i, 'depth_range_m': [min(float(q[2]) for q in poly), max(float(q[2]) for q in poly)]})
    _, ringpieces = partition(rounded(.034, .060, .003), polygon_planes(rounded(.027, .051, .002), np.array([0., 0., 1.])))
    ring = polygon_mesh(ringpieces, housing['name'] + '_finite_flange_ring')
    support = surface_cover(ring, p)
    parity = wiper_initial.parity(hv[body].mean(0), wiper_initial.components(p))
    maximum = max((q['depth_range_m'][1] for q in flangefragments), default=math.inf)
    return {'kind': 'latch_flange', 'pair': [housing['name'], panel['name']], 'contract': c,
            'complete_flange_ring_support': support, 'body_boundary_fragments': bodyfragments,
            'flange_boundary_fragments': flangefragments, 'maximum_panel_depth_m': maximum if math.isfinite(maximum) else None,
            'housing_body_interior': parity,
            'status': 'passed' if not bodyfragments and maximum <= GUARD and parity['status'] == 'outside'
                      and support['status'] == 'passed' else 'failed'}


def screw_joint(bolt, housing):
    c = contract(bolt, 'fitted_fastener_seat')
    require(c.get('depth_m') == .001 and c.get('head_radius_m') == .003 and c.get('socket_radius_m') == .00305,
            'Changed fitted fastener dimensions')
    axes, origin = frame(c['outward_normal']), np.array(c['bottom_center_m'])
    b, h = local(bolt, origin, axes), local(housing, origin, axes)
    bv, hp = np.array(b['vertices']), triangles(h)
    low, high = float(bv[:, 2].min()), float(bv[:, 2].max())
    require(abs(high-low-.001) <= GUARD, 'Fitted screw depth mismatch')
    bottom, ids = cap(b, 2, low)
    ring = hull2(triangles(bottom).reshape(-1, 3))
    require(len(ring) == 6 and max(abs(float(np.linalg.norm(p[:2]))-.003) for p in ring) <= GUARD,
            'Complete centered hex head required')
    support = surface_cover(bottom, h)
    planes = prism_planes(ring, low, high)
    fragments = []
    for i, tri in enumerate(hp):
        poly, _ = partition(list(tri), [(n, d-GUARD) for n, d in planes])
        if poly:
            fragments.append({'housing_triangle': i, 'relative_depth_range_m':
                              [min(float(p[2]-low) for p in poly), max(float(p[2]-low) for p in poly)]})
    maximum = max((q['relative_depth_range_m'][1] for q in fragments), default=math.inf)
    socket = [p*(.00305/.003) for p in ring]
    wallpolys = [np.array([[a[0], a[1], low], [b[0], b[1], low],
                          [b[0], b[1], high], [a[0], a[1], high]])
                 for a, b in zip(socket, socket[1:] + socket[:1])]
    walls = surface_cover(polygon_mesh(wallpolys, bolt['name'] + '_six_socket_walls'), h)
    radial = min(float(np.min(bv @ n - d)) for n, d in polygon_planes(socket, np.array([0., 0., 1.])))
    parity = wiper_initial.parity(bv.mean(0), wiper_initial.components(h))
    return {'kind': 'latch_screw', 'pair': [bolt['name'], housing['name']], 'contract': c,
            'complete_bottom_cap_support': support, 'complete_socket_wall_support': walls,
            'housing_inside_head_fragments': fragments, 'maximum_housing_intrusion_m': maximum if math.isfinite(maximum) else None,
            'whole_head_minimum_socket_plane_gap_m': radial, 'head_interior': parity,
            'status': 'passed' if support['status'] == walls['status'] == 'passed' and maximum <= GUARD
                      and radial > GUARD and parity['status'] == 'outside' else 'failed'}


def merged_intervals(intervals, guard):
    joined = []
    for low, high in sorted(intervals):
        if high < 0 or low > 1:
            continue
        low, high = max(0., low), min(1., high)
        if joined and low <= joined[-1][1]+guard:
            joined[-1][1] = max(high, joined[-1][1])
        else:
            joined.append([low, high])
    gaps, end = [], 0.
    for low, high in joined:
        if low > end+guard:
            gaps.append([end, low])
        end = max(end, high)
    if end < 1-guard:
        gaps.append([end, 1.])
    return joined, gaps


def cloth_joint(seam, pad, radius, axes):
    sv, sp, pp = np.array(seam['vertices']), triangles(seam), triangles(pad)
    require(len(sv) % 4 == 0 and len(sv) >= 8, 'Ordered four-sided sewn tube required')
    rings = sv.reshape(-1, 4, 3)
    centers = rings.mean(1)
    require(np.max(np.abs(np.linalg.norm(rings-centers[:, None, :], axis=2)-radius)) <= GUARD,
            'Thread radius differs from declared geometry')
    segments, contacts = [[] for _ in range(len(centers)-1)], []
    plo, phi = pp.min(1), pp.max(1)
    tested = 0
    for ai, tri in enumerate(sp):
        ringids = {int(i)//4 for i in seam['triangles'][ai]}
        if len(ringids) == 2 and max(ringids)-min(ringids) == 1:
            span = min(ringids)
        elif ringids == {0}:
            span = 0
        elif ringids == {len(centers)-1}:
            span = len(centers)-2
        else:
            raise ValueError('Unexpected sewn tube connectivity')
        delta = centers[span+1]-centers[span]
        length = float(np.linalg.norm(delta))
        require(length > 2*GUARD, 'Sewn tube zero/tiny route interval')
        selected = np.flatnonzero(np.all(plo <= tri.max(0), axis=1) & np.all(phi >= tri.min(0), axis=1))
        for bi in selected:
            tested += 1
            points = exact_triangles.intersection(tri.tolist(), pp[bi].tolist())
            if not points:
                continue
            actual = np.array(exact_triangles.jsonify(points))
            t = (actual-centers[span]) @ delta / (length*length)
            segments[span].append([float(t.min()), float(t.max())])
            contacts.append({'thread_triangle': ai, 'pad_triangle': int(bi), 'points_m': actual.tolist()})
    spans = []
    for i, intervals in enumerate(segments):
        length = float(np.linalg.norm(centers[i+1]-centers[i]))
        joined, gaps = merged_intervals(intervals, GUARD/length)
        spans.append({'segment': i, 'length_m': length, 'contact_projection_intervals': joined,
                      'uncovered_intervals': gaps})
    lsp, lpp = sp @ axes.T, pp @ axes.T
    normals = np.cross(lpp[:, 1]-lpp[:, 0], lpp[:, 2]-lpp[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    charts = []
    # Every outward-facing height chart participates. A second closed layer or
    # steep shoulder must not disappear behind the first chart owning XY.
    for i in np.flatnonzero(normals[:, 2] > 0):
        charts.append({'index': int(i), 'points': lpp[i], 'normal': normals[i],
                       'planes': polygon_planes(list(lpp[i]), np.array([0., 0., 1.])),
                       'low': lpp[i].min(0)[:2], 'high': lpp[i].max(0)[:2]})
    minimum, maximum, pieces, uncovered = math.inf, -math.inf, [], []
    for i, tri in enumerate(lsp):
        for chart in charts:
            if np.any(tri.min(0)[:2] > chart['high']) or np.any(tri.max(0)[:2] < chart['low']):
                continue
            inside, _ = partition(list(tri), chart['planes'])
            if inside:
                values = [float((p-chart['points'][0]) @ chart['normal']) for p in inside]
                minimum, maximum = min(minimum, *values), max(maximum, *values)
                pieces.append({'thread_triangle': i, 'pad_triangle': chart['index'],
                               'distance_range_m': [min(values), max(values)]})
        remaining = [list(tri)]
        for chart in charts:
            if np.any(tri.min(0)[:2] > chart['high']) or np.any(tri.max(0)[:2] < chart['low']):
                continue
            todo = []
            for poly in remaining:
                inside, outside = partition(poly, chart['planes'])
                todo.extend(outside)
            remaining = todo
            if not remaining:
                break
        for poly in remaining:
            owned = next((c for c in charts if all(all(float(n @ p-d) >= -1e-12 for n, d in c['planes']) for p in poly)), None)
            if owned is None:
                uncovered.append({'thread_triangle': i, 'polygon_m': [p.tolist() for p in poly]})
            else:
                values = [float((p-owned['points'][0]) @ owned['normal']) for p in poly]
                minimum, maximum = min(minimum, *values), max(maximum, *values)
    finite = math.isfinite(minimum) and math.isfinite(maximum)
    complete = all(not row['uncovered_intervals'] for row in spans)
    return {'kind': 'sewn_upholstery', 'pair': [seam['name'], pad['name']], 'radius_m': radius,
            'maximum_allowed_intrusion_m': .15*radius, 'tested_triangle_pairs': tested,
            'exact_boundary_contacts': contacts, 'complete_route_spans': spans,
            'complete_front_chart_fragments': pieces, 'uncovered_footprint': uncovered,
            'front_chart_policy': 'Every positive outward-axis facet checked independently; coverage subtraction is separate',
            'front_chart_count': len(charts), 'all_overlapping_front_charts_checked': True,
            'complete_surface_signed_distance_range_m': [minimum, maximum] if finite else None,
            'status': 'passed' if finite and minimum >= -.15*radius-GUARD and not uncovered and complete else 'failed'}


def inventory(rows):
    pairs = []
    for side in ('L', 'R'):
        pairs.append(('header_butt', 'LOD0_PillarA_'+side, 'LOD0_RoofSideRail_'+side))
    for suffix in ('FL', 'FR', 'RL', 'RR'):
        pairs.append(('latch_flange', 'LOD0_DoorLatch_'+suffix, 'LOD0_Door_'+suffix))
        names = sorted(name for name in rows if name.startswith('LOD0_LatchFastener_'+suffix))
        require(len(names) == 2, 'Exactly two fitted screw heads required per latch: ' + suffix)
        pairs.extend(('latch_screw', name, 'LOD0_DoorLatch_'+suffix) for name in names)
    for seat in ('FrontL', 'FrontR', 'RearL', 'RearR'):
        prefix = 'LOD0_'+seat
        pairs.extend(('sewn_upholstery', prefix+'CushionSeam'+str(i), prefix+'CushionInsert') for i in range(5))
        pairs.extend(('sewn_upholstery', prefix+'BackPiping'+str(side), prefix+'BackInsert') for side in (-1, 1))
    require(len(pairs) == 42 and len({a for _, a, _ in pairs}) == 42, 'Finite interface inventory mismatch')
    for _, a, b in pairs:
        require(a in rows and b in rows, 'Required interface mesh missing: ' + a + '/' + b)
    return pairs


def inspect_pair(rows, entry):
    kind, a, b = entry
    if kind == 'header_butt':
        return header_joint(rows, a[-1])
    if kind == 'latch_flange':
        return housing_joint(rows, a[-2:])
    if kind == 'latch_screw':
        return screw_joint(rows[a], rows[b])
    if 'CushionSeam' in a:
        radius, axis = .0006, np.array([0., 0., 1.])
    else:
        theta = math.radians(9 if 'Rear' in a else 18)
        radius, axis = .0008, np.array([0., math.cos(theta), math.sin(theta)])
    axes = np.array([[1., 0., 0.], np.cross(axis, [1., 0., 0.]), axis])
    return cloth_joint(rows[a], rows[b], radius, axes)


def negative_controls(rows, entries):
    controls = []
    targets = [entries[0], next(q for q in entries if q[0] == 'latch_flange'),
               next(q for q in entries if q[0] == 'latch_screw'),
               next(q for q in entries if 'BackPiping' in q[1])]
    for entry in targets:
        kind, a, b = entry
        if kind == 'header_butt':
            name, axis, distances = b, np.array([0., 1., 0.]), [-.0001, .0001]
        elif kind == 'latch_flange':
            name, axis, distances = a, unit(contract(rows[a], 'fitted_latch_seat')['outward_normal']), [-.0001, .0001]
        elif kind == 'latch_screw':
            name, axis, distances = a, unit(contract(rows[a], 'fitted_fastener_seat')['outward_normal']), [-.0001, .0001]
        else:
            theta = math.radians(18)
            name, axis, distances = a, np.array([0., math.cos(theta), math.sin(theta)]), [-.0002, .002]
        for distance in distances:
            changed = copy.deepcopy(rows[name])
            changed['vertices'] = (np.array(changed['vertices'])+axis*distance).tolist()
            try:
                result = inspect_pair(rows | {name: changed}, entry)
                rejected, reason = result['status'] != 'passed', result
            except ValueError as error:
                rejected, reason = True, {'failure': str(error)}
            controls.append({'name': kind+f'_{distance:+.7f}m', 'pair': [a, b], 'rejected': rejected, 'result': reason})
    controls.append(crossing_pad_control())
    return controls


def crossing_pad_control():
    """Actual closed two-layer counterexample to the former first-chart pass."""
    def box(name, low, high):
        vertices = [[x, y, z] for z in (low[2], high[2]) for y in (low[1], high[1]) for x in (low[0], high[0])]
        faces = [[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
                 [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]]
        return {'name': name, 'vertices': vertices, 'triangles': faces, 'properties': {}}
    ring = [(.0006, 0), (0, -.0006), (-.0006, 0), (0, .0006)]
    seam = {'name': 'SyntheticThread', 'vertices': [[x+.05, y, z+.00054] for y in (-.01, .01) for x, z in ring],
            'triangles': [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7]], 'properties': {}}
    for i in range(4):
        j = (i+1) % 4
        seam['triangles'].extend([[i, j, j+4], [i, j+4, i+4]])
    pad = box('SyntheticPad', [-.1, -.1, -.02], [.1, .1, 0.])
    upper = box('SyntheticSecondLayer', [.04, -.015, .0008], [.06, .015, .002])
    combined = copy.deepcopy(pad)
    offset = len(combined['vertices'])
    combined['vertices'] += upper['vertices']
    combined['triangles'] += [[i+offset for i in tri] for tri in upper['triangles']]
    for row in (seam, pad, upper, combined):
        validate_row(row['name'], row)
    baseline = cloth_joint(seam, pad, .0006, np.eye(3))
    negative = cloth_joint(seam, combined, .0006, np.eye(3))
    intersections = []
    for ai, a in enumerate(triangles(seam)):
        for bi, b in enumerate(triangles(upper)):
            points = exact_triangles.intersection(a.tolist(), b.tolist())
            if points:
                intersections.append({'thread_triangle': ai, 'extra_pad_triangle': bi,
                                      'points_m': exact_triangles.jsonify(points)})
    return {'name': 'sewn_upholstery_intersecting_second_pad_layer',
            'rejected': baseline['status'] == 'passed' and negative['status'] == 'failed' and bool(intersections),
            'baseline': baseline, 'result': negative, 'exact_extra_layer_intersections': intersections,
            'fixtures': {'thread': seam, 'pad': pad, 'second_layer': upper, 'combined': combined}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists(), 'Choose a fresh report path')
    require(args.output.resolve() != args.geometry.resolve(), 'Output must not replace input')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started, inputs = time.monotonic(), {}
    record = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.platform(), 'python': sys.version, 'numpy': np.__version__,
              'status': 'failed', 'source_sha256': None, 'human_approval_reference': None, 'guard_m': GUARD,
              'scope': '42 finite formed header, fitted latch and sewn upholstery interfaces only. '
                       'Individual self validity, all other contacts/motion, appearance and human approval remain separate.'}
    try:
        payload = strict_json(gzip.decompress(args.geometry.read_bytes()))
        require(isinstance(payload, dict) and isinstance(payload.get('meshes'), dict), 'Geometry object required')
        source_hash, source = payload.get('source_sha256'), Path(payload['source_path'])
        require(isinstance(source_hash, str) and re.fullmatch('[0-9a-f]{64}', source_hash)
                and source.is_file() and sha(source) == source_hash, 'Actual source hash mismatch')
        record['source_sha256'] = source_hash
        dependencies = [args.geometry, source, Path(__file__), Path(exact_triangles.__file__),
                        Path(precision.__file__), Path(wiper_initial.__file__), Path(finish_report.__file__),
                        Path(__file__).with_name('wiper_interassembly.py'), Path(__file__).with_name('wipers.py')]
        inputs = {str(p.resolve()): sha(p) for p in dependencies}
        record['geometry_payload_sha256'] = sha(args.geometry)
        try:
            record['git_revision'] = subprocess.check_output(['git', '-C', str(Path(__file__).parent), 'rev-parse', 'HEAD'], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            record['git_revision'] = None
        rows = payload['meshes']
        entries = inventory(rows)
        record['exact_named_inventory'] = [{'kind': kind, 'pair': [a, b]} for kind, a, b in entries]
        for name in sorted({name for _, a, b in entries for name in (a, b)}):
            validate_row(name, rows[name])
        results = []
        record['results'] = results
        for entry in entries:
            try:
                result = inspect_pair(rows, entry)
            except ValueError as error:
                result = {'kind': entry[0], 'pair': list(entry[1:]), 'status': 'failed', 'failure': str(error)}
            results.append(result)
            print(json.dumps({'pair': result['pair'], 'status': result['status']}), flush=True)
        controls = negative_controls(rows, entries)
        record.update(exact_named_inventory=[{'kind': kind, 'pair': [a, b]} for kind, a, b in entries],
                      interface_count=len(results), results=results, negative_controls=controls,
                      negative_control_count=len(controls),
                      status='passed' if all(q['status'] == 'passed' for q in results)
                             and all(q['rejected'] for q in controls) else 'failed')
    except Exception as error:
        record.update(status='failed', failure=type(error).__name__ + ': ' + str(error))
    finally:
        unchanged = all(Path(path).is_file() and sha(path) == digest for path, digest in inputs.items())
        record.update(inputs=[{'path': path, 'sha256': digest} for path, digest in inputs.items()],
                      inputs_unchanged=unchanged, elapsed_seconds=time.monotonic()-started)
        if not unchanged:
            record.update(status='failed', failure='Input changed during finite interface proof')
        if record['status'] == 'passed':
            try:
                finish_report.validate_report(record, record['source_sha256'])
            except ValueError as error:
                record.update(status='failed', failure='Report validation: '+str(error))
        args.output.write_text(json.dumps(record, indent=2, allow_nan=False)+'\n', encoding='utf8', newline='\n')
    print(json.dumps({'status': record['status'], 'interfaces': record.get('interface_count'), 'output': str(args.output)}), flush=True)
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
