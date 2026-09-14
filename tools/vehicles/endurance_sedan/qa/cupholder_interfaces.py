"""Complete finite console/cupholder seats from evaluated source triangles.

The two named inserts require closed receiving wells, actual recessed console
walls and bottoms, and a supported planar lip. No other pair is excepted.
The report validator deliberately has no NumPy or Blender dependency.
"""
from __future__ import annotations

import argparse
from collections import deque
import copy
from datetime import datetime, timezone
from fractions import Fraction
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

GUARD = 1e-6
CONSOLE = 'LOD0_CenterConsole'
CUPS = ('LOD0_Cupholder_-1', 'LOD0_Cupholder_1')
CONTRACT = {
    'segments': 32, 'center_abs_x_m': .068, 'center_y_m': -.113,
    'receiving_inradius_m': .040, 'wall_thickness_m': .0015,
    'pocket_clearance_m': .0012, 'lip_outer_radius_m': .044,
    'lip_thickness_m': .002, 'lip_chamfer_m': .0005,
    'receiving_depth_m': .060, 'bottom_thickness_m': .003,
    'console_top_z_m': .586,
}
NEGATIVES = ('down200um', 'up200um', 'uncut_console', 'raised_pocket_corner', 'receiving_blocker')
NEGATIVE_FAILURES = {
    'down200um': 'Cup upper plane differs from locked height',
    'up200um': 'Cup upper plane differs from locked height',
    'uncut_console': 'Actual console cavity corner missing or moved',
    'raised_pocket_corner': 'Actual console cavity corner missing or moved',
    'receiving_blocker': 'Receiving depth or closed bottom thickness changed',
}
COVER_FIELDS = ('complete_cup_to_design', 'complete_design_to_cup',
                'complete_console_region_to_design', 'complete_design_to_console_region',
                'complete_flange_support_to_console')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: '+key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON: '+value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def positive_int(value):
    return type(value) is int and value > 0


def validate_report(report, source_sha):
    """Fail closed on missing proof fields, inventories or measured limits."""
    require(isinstance(report, dict) and report.get('status') == 'passed', 'Cup report not passed')
    require(isinstance(source_sha, str) and re.fullmatch('[0-9a-f]{64}', source_sha)
            and report.get('source_sha256') == source_sha, 'Cup report source mismatch')
    require(report.get('guard_m') == GUARD and 'human_approval_reference' in report
            and report['human_approval_reference'] is None,
            'Cup guard or human scope changed')
    require(report.get('blender_version') == '5.1.2' and report.get('blender_build_hash') == 'ec6e62d40fa9',
            'Cup proof requires the pinned native Blender build')
    require(type(report.get('interface_count')) is int and report['interface_count'] == 2,
            'Exactly two cup interfaces required')
    expected = [[cup, CONSOLE] for cup in CUPS]
    require(report.get('exact_named_inventory') == expected, 'Cup interface inventory mismatch')
    results = report.get('results')
    require(isinstance(results, list) and len(results) == 2
            and [r.get('pair') for r in results] == expected, 'Cup result inventory mismatch')
    for row in results:
        require(row.get('status') == 'passed', 'Cup pair not passed')
        require(row.get('contract') == CONTRACT, 'Cup dimensions differ from locked construction')
        for key in COVER_FIELDS:
            proof = row.get(key)
            require(isinstance(proof, dict) and proof.get('status') == 'passed'
                    and positive_int(proof.get('full_triangles'))
                    and type(proof.get('cells')) is int and proof['cells'] >= 0
                    and finite(proof.get('maximum_certified_surface_distance_m'))
                    and 0 <= proof['maximum_certified_surface_distance_m'] <= GUARD,
                    'Incomplete cup surface certificate: '+key)
            counters = [proof.get(name) for name in ('convex_single_triangle_certificates',
                        'convex_planar_patch_certificates', 'complete_partition_fallback_triangles')]
            require(all(type(value) is int and value >= 0 for value in counters)
                    and sum(counters) == proof['full_triangles']
                    and type(proof.get('convex_planar_patch_count')) is int
                    and proof['convex_planar_patch_count'] >= 0,
                    'Incomplete cup coverage partition inventory: '+key)
        for key in ('minimum_recess_side_clearance_m', 'minimum_recess_bottom_clearance_m'):
            value = row.get(key)
            require(finite(value) and value >= CONTRACT['pocket_clearance_m']-GUARD,
                    'Cup recessed clearance below contract: '+key)
        require(positive_int(row.get('complete_recess_triangle_count'))
                and positive_int(row.get('console_region_fragment_count')),
                'Missing complete cup/console domain inventory')
        require(finite(row.get('minimum_receiving_radius_m'))
                and row['minimum_receiving_radius_m'] >= CONTRACT['receiving_inradius_m']-GUARD,
                'Cup receiving void not clear')
        for key, expected_value in [('receiving_depth_m', .060), ('bottom_thickness_m', .003)]:
            require(finite(row.get(key)) and abs(row[key]-expected_value) <= GUARD,
                    'Wrong cup depth/thickness: '+key)
        require(finite(row.get('continuous_support_band_lower_bound_m'))
                and row['continuous_support_band_lower_bound_m'] > .0008,
                'Cup finite lip support is missing')
        require(finite(row.get('maximum_flange_plane_error_m'))
                and 0 <= row['maximum_flange_plane_error_m'] <= GUARD,
                'Cup flange outside finite seat plane')
        require(row.get('all_console_region_fragments_checked') is True,
                'Incomplete console region applicability')
        mount = row.get('finite_mount')
        require(isinstance(mount, dict) and finite(mount.get('plane_z_m'))
                and abs(mount['plane_z_m']-.586) <= GUARD, 'Missing finite cup seat plane')
        cx = -.068 if row['pair'][0] == CUPS[0] else .068
        for key, radius, z in [('outer_lip_vertices_m', .044, mount['plane_z_m']),
                               ('actual_pocket_upper_vertices_m', .0427/math.cos(math.pi/32), mount['plane_z_m']),
                               ('actual_pocket_lower_vertices_m', .0427/math.cos(math.pi/32), mount['plane_z_m']-.0622)]:
            ring = mount.get(key)
            require(isinstance(ring, list) and len(ring) == 32, 'Missing complete finite cup ring: '+key)
            for i, point in enumerate(ring):
                require(isinstance(point, list) and len(point) == 3 and all(finite(v) for v in point),
                        'Malformed finite cup ring vertex: '+key)
                expected_point = [cx+radius*math.cos(math.tau*i/32), -.113+radius*math.sin(math.tau*i/32), z]
                require(math.dist(point, expected_point) <= GUARD, 'Finite cup ring escaped contract: '+key)
        radii = mount.get('support_ring_vertex_radii_m')
        require(isinstance(radii, list) and len(radii) == 2 and all(finite(v) for v in radii)
                and radii[0] > .0427/math.cos(math.pi/32) and radii[1] > radii[0]
                and radii[1] < .044*math.cos(math.pi/32), 'Malformed finite cup support band')
    inputs = report.get('inputs')
    require(isinstance(inputs, list) and len(inputs) >= 4, 'Cup proof input hashes missing')
    paths = set()
    for item in inputs:
        require(isinstance(item, dict) and isinstance(item.get('path'), str) and item['path']
                and item['path'] not in paths and isinstance(item.get('sha256'), str)
                and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'Malformed cup input binding')
        paths.add(item['path'])
    require(any(item['sha256'] == source_sha for item in inputs)
            and report.get('inputs_unchanged') is True, 'Cup source/input binding missing')
    require(isinstance(report.get('geometry_payload_sha256'), str)
            and re.fullmatch('[0-9a-f]{64}', report['geometry_payload_sha256'])
            and any(item['sha256'] == report['geometry_payload_sha256'] for item in inputs),
            'Cup geometry hash binding missing')
    controls = report.get('negative_controls')
    expected_controls = [(cup, kind) for cup in CUPS for kind in NEGATIVES]
    require(type(report.get('negative_control_count')) is int
            and report['negative_control_count'] == len(expected_controls)
            and isinstance(controls, list) and len(controls) == len(expected_controls)
            and [(r.get('cup'), r.get('name')) for r in controls] == expected_controls,
            'Cup negative inventory mismatch')
    for control in controls:
        require(control.get('rejected') is True and isinstance(control.get('failure'), str)
                and control['failure'] and isinstance(control.get('mutated_mesh_sha256'), str)
                and re.fullmatch('[0-9a-f]{64}', control['mutated_mesh_sha256'])
                and control.get('mutated_schema_topology_valid') is True,
                'Cup negative did not establish rejection')
        require(control['failure'] == NEGATIVE_FAILURES[control['name']],
                'Cup negative failed at an unintended predicate')


def geometry_dependencies():
    global np, fi
    if 'np' not in globals():
        import numpy as np
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import finish_interfaces as fi


def validate_mesh(row):
    fi.validate_row(row['name'], row)
    faces = row['triangles']
    neighbors = {}
    for face in faces:
        for a, b in zip(face, face[1:]+face[:1]):
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)
    remaining = set(neighbors); queue = deque([next(iter(remaining))])
    while queue:
        vertex = queue.popleft()
        if vertex not in remaining:
            continue
        remaining.remove(vertex); queue.extend(neighbors[vertex] & remaining)
    require(not remaining, 'One connected cup/console shell required: '+row['name'])
    tri = fi.triangles(row); local = tri-tri[0, 0]
    volume = float(np.einsum('ij,ij->i', local[:, 0], np.cross(local[:, 1], local[:, 2])).sum()/6)
    require(volume > 0 and math.isfinite(volume), 'Outward cup/console winding required: '+row['name'])


def circle(cx, radius, z):
    return [np.array([cx+radius*math.cos(math.tau*i/32), -.113+radius*math.sin(math.tau*i/32), z])
            for i in range(32)]


def strip(a, b):
    return [[a[i], a[(i+1) % 32], b[(i+1) % 32], b[i]] for i in range(32)]


def design(cx, top):
    factor = math.cos(math.pi/32)
    inner, wall, pocket = .040/factor, .0415/factor, .0427/factor
    upper, floor, bottom = top+.002, top+.002-.060, top+.002-.060-.003
    rings = [circle(cx, r, z) for r, z in [(inner, upper), (.0435, upper), (.044, upper-.0005),
                                         (.044, top), (wall, top), (wall, bottom), (inner, floor)]]
    pieces = []
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 0)]:
        pieces.extend(strip(rings[a], rings[b]))
    for index, z in ((5, bottom), (6, floor)):
        pieces.extend([[np.array([cx, -.113, z]), rings[index][i], rings[index][(i+1) % 32]]
                      for i in range(32)])
    cup = fi.polygon_mesh(pieces, 'DesignCup')
    outer = circle(cx, .045, top)
    cavity_top, cavity_bottom = circle(cx, pocket, top), circle(cx, pocket, bottom-.0012)
    console = fi.polygon_mesh(strip(outer, cavity_top)+strip(cavity_top, cavity_bottom)+[cavity_bottom],
                              'DesignConsolePocketAndTop')
    return {'cup': cup, 'console': console, 'outer_region': outer,
            'cavity_top': cavity_top, 'cavity_bottom': cavity_bottom,
            'floor_z': floor, 'bottom_z': bottom, 'cavity_bottom_z': bottom-.0012}


def horizontal_convex_patches(row):
    """Join only exactly planar, oriented triangulated convex disks.

    Opposite internal edges cancel, leaving one simple convex boundary. All
    triangles have the same exact orientation, so their winding sum covers
    that disk once, with no hole or overlapped area. This is a coverage proof
    from the actual target faces; a convex hull alone would not establish it.
    """
    groups = {}
    for index, tri in enumerate(fi.triangles(row)):
        if tri[0, 2] == tri[1, 2] == tri[2, 2]:
            groups.setdefault(float(tri[0, 2]), []).append((index, [tuple(p[:2]) for p in tri]))
    patches = []
    for z, rows in groups.items():
        coordinates = {p: tuple(Fraction(float(v)) for v in p) for _, tri in rows for p in tri}
        def cross(a, b, c):
            a, b, c = coordinates[a], coordinates[b], coordinates[c]
            return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        edges, adjacency = {}, [set() for _ in rows]
        for i, (_, tri) in enumerate(rows):
            for a, b in zip(tri, tri[1:]+tri[:1]):
                edges.setdefault(tuple(sorted((a, b))), []).append((i, a, b))
        for uses in edges.values():
            for i, _, _ in uses:
                adjacency[i].update(j for j, _, _ in uses if j != i)
        remaining = set(range(len(rows)))
        while remaining:
            todo, component = [min(remaining)], set()
            while todo:
                i = todo.pop()
                if i in component:
                    continue
                component.add(i); todo.extend(adjacency[i]-component)
            remaining -= component
            signs = [cross(*rows[i][1]) for i in component]
            if not (all(v > 0 for v in signs) or all(v < 0 for v in signs)):
                continue
            boundary, valid = {}, True
            for uses in edges.values():
                selected = [(a, b) for i, a, b in uses if i in component]
                if len(selected) == 2:
                    if selected[0] != tuple(reversed(selected[1])):
                        valid = False; break
                elif len(selected) == 1:
                    a, b = selected[0]
                    if a in boundary:
                        valid = False; break
                    boundary[a] = b
                elif selected:
                    valid = False; break
            if not valid or len(boundary) < 3 or len(set(boundary.values())) != len(boundary):
                continue
            start = min(boundary); polygon, current = [], start
            while current not in polygon and current in boundary:
                polygon.append(current); current = boundary[current]
            if current != start or len(polygon) != len(boundary):
                continue  # multiple loops include a hole; never replace by a hull
            sign = 1 if signs[0] > 0 else -1
            if any(sign*cross(a, b, p) < 0 for a, b in zip(polygon, polygon[1:]+polygon[:1])
                   for p in polygon):
                continue
            patches.append({'polygon': [np.array([*p, z]) for p in polygon],
                            'triangle_indices': sorted(rows[i][0] for i in component), 'orientation': sign})
    return patches


def patch_distance(point, patch):
    polygon, sign = patch['polygon'], patch['orientation']
    inside = all(sign*((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])) >= 0
                 for a, b in zip(polygon, polygon[1:]+polygon[:1]))
    if inside:
        return abs(float(point[2]-polygon[0][2]))
    distance = math.inf
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        edge = b-a
        t = min(1., max(0., float((point-a) @ edge)/float(edge @ edge)))
        distance = min(distance, float(np.linalg.norm(point-a-t*edge)))
    return distance


def require_cover(source, target, label):
    # Distance to a closed convex triangle is convex. Bounding its value at all
    # three source vertices bounds the complete source triangle. Try this full
    # face certificate before partitioning, so early non-owning target facets
    # do not create thousands of needless slivers on an otherwise owned face.
    other = fi.triangles(target); low, high = other.min(1), other.max(1)
    centers = other.mean(1); unresolved = []; cells, worst = 0, 0.
    patches = horizontal_convex_patches(target); patch_count = 0
    original = fi.triangles(source)
    for index, triangle in enumerate(original):
        ids = np.flatnonzero(np.all(low <= triangle.max(0)+GUARD, axis=1)
                            & np.all(high >= triangle.min(0)-GUARD, axis=1))
        ids = sorted(ids, key=lambda i: float(np.linalg.norm(centers[i]-triangle.mean(0))))
        covered = False
        for patch in patches:
            cells += 1
            bound = max(patch_distance(p, patch) for p in triangle)
            if bound <= GUARD-1e-9:
                worst = max(worst, bound); covered = True; patch_count += 1; break
        if covered:
            continue
        for other_index in ids:
            cells += 1
            bound = max(float(np.linalg.norm(p-fi.point_triangle(p, other[other_index]))) for p in triangle)
            if bound <= GUARD-1e-9:
                worst = max(worst, bound); covered = True; break
        if not covered:
            unresolved.append(index)
    if unresolved:
        result = fi.surface_cover(fi.subset(source, unresolved, '_unresolved'), target, GUARD)
        require(result['status'] == 'passed', label+': '+json.dumps(result))
        cells += result['cells']; worst = max(worst, result['maximum_certified_surface_distance_m'])
    result = {'status': 'passed', 'full_triangles': len(original), 'cells': cells,
              'maximum_certified_surface_distance_m': worst,
              'convex_single_triangle_certificates': len(original)-len(unresolved)-patch_count,
              'convex_planar_patch_certificates': patch_count, 'convex_planar_patch_count': len(patches),
              'complete_partition_fallback_triangles': len(unresolved)}
    require(result['status'] == 'passed', label+': '+json.dumps(result))
    return result


def nearest_ring(console, expected):
    used = sorted({i for face in console['triangles'] for i in face})
    points = np.asarray(console['vertices'], dtype=float)[used]
    ring = []
    for point in expected:
        distances = np.linalg.norm(points-point, axis=1)
        index = int(np.argmin(distances))
        require(float(distances[index]) <= GUARD, 'Actual console cavity corner missing or moved')
        ring.append(points[index])
    require(len({tuple(point) for point in ring}) == 32, 'Repeated console cavity corners')
    return ring


def radial_minimum(poly, center):
    values = [point[:2]-center for point in poly]
    cross_values = [float(a[0]*b[1]-a[1]*b[0]) for a, b in zip(values, values[1:]+values[:1])]
    area = sum(cross_values)/2
    if abs(area) > 1e-20 and (all(v >= 0 for v in cross_values) or all(v <= 0 for v in cross_values)):
        return 0.
    minimum = math.inf
    for a, b in zip(values, values[1:]+values[:1]):
        edge = b-a; length2 = float(edge @ edge)
        t = min(1., max(0., -float(a @ edge)/length2)) if length2 else 0.
        minimum = min(minimum, float(np.linalg.norm(a+t*edge)))
    return minimum


def inspect_pair(cup, console):
    geometry_dependencies()
    require(cup['name'] in CUPS and console['name'] == CONSOLE, 'Unexpected finite cup pair')
    for row in (cup, console):
        validate_mesh(row)
    require(cup.get('ancestors') == console.get('ancestors'), 'Cup and console must share the same fixed assembly')
    require('Chassis' in cup.get('ancestors', []) or cup.get('ancestors') == ['Visual_LOD0'],
            'Cup fixed authored parent missing')
    cx = -.068 if cup['name'].endswith('_-1') else .068
    center = np.array([cx, -.113])
    top = max(point[2] for point in console['vertices'])
    require(abs(top-.586) <= GUARD, 'Actual console top differs from locked seat height')
    require(abs(max(point[2] for point in cup['vertices'])-(top+.002)) <= GUARD,
            'Cup upper plane differs from locked height')
    levels = sorted({float(p[2]) for p in cup['vertices'] if np.linalg.norm(np.array(p[:2])-center) <= GUARD})
    require(len(levels) == 2, 'Distinct closed inner/outer cup floors required')
    depth = max(p[2] for p in cup['vertices'])-levels[1]
    thickness = levels[1]-levels[0]
    require(abs(depth-.060) <= GUARD and abs(thickness-.003) <= GUARD,
            'Receiving depth or closed bottom thickness changed')
    reference = design(cx, top)
    result = {'pair': [cup['name'], console['name']], 'status': 'failed', 'contract': dict(CONTRACT)}
    result['complete_cup_to_design'] = require_cover(cup, reference['cup'], 'Cup boundary outside complete design')
    result['complete_design_to_cup'] = require_cover(reference['cup'], cup, 'Cup design boundary missing')
    cavity_top = nearest_ring(console, reference['cavity_top'])
    cavity_bottom = nearest_ring(console, reference['cavity_bottom'])
    require(max(abs(float(a[2])-top) for a in cavity_top) <= GUARD, 'Nonplanar cup pocket upper rim')
    bottom_z = min(float(a[2]) for a in cavity_bottom)
    require(max(float(a[2]) for a in cavity_bottom)-bottom_z <= GUARD, 'Nonplanar cup pocket floor')
    planes = fi.polygon_planes(cavity_top, np.array([0., 0., 1.]))
    require(all(float(n @ np.array([cx, -.113, top])) > d for n, d in planes), 'Cavity winding is not convex inward')
    require(all(float(n @ p) >= d-GUARD for p in cavity_top for n, d in planes), 'Actual cavity rim not convex')
    minimum_side, minimum_bottom = math.inf, math.inf
    receiving_radius, recess_count = math.inf, 0
    cup_triangles = fi.triangles(cup)
    for tri in cup_triangles:
        if min(float(p[2]) for p in tri) < top-GUARD:
            polygon, _ = fi.partition(list(tri), [(np.array([0., 0., -1.]), -top)])
            if polygon:
                recess_count += 1
                minimum_side = min(minimum_side, *(float(n @ p)-d for p in polygon for n, d in planes))
                minimum_bottom = min(minimum_bottom, *(float(p[2])-bottom_z for p in polygon))
        polygon, _ = fi.partition(list(tri), [(np.array([0., 0., 1.]), reference['floor_z']+2*GUARD),
                                            (np.array([0., 0., -1.]), -(top+.002-2*GUARD))])
        if polygon:
            receiving_radius = min(receiving_radius, radial_minimum(polygon, center))
    require(recess_count > 0 and minimum_side >= .0012-GUARD and minimum_bottom >= .0012-GUARD,
            'Recessed cup wall/bottom lacks actual 1.2 mm pocket clearance')
    require(receiving_radius >= .040-GUARD, 'Solid cup boundary blocks the full receiving radius')
    # Every console triangle that enters the whole cup neighborhood is checked,
    # including additional layers. Finding the nominal 32 corners is not enough.
    region_planes = fi.prism_planes(reference['outer_region'], reference['cavity_bottom_z']-4*GUARD, top+4*GUARD)
    fragments = []
    for tri in fi.triangles(console):
        polygon, _ = fi.partition(list(tri), region_planes)
        if len(polygon) >= 3:
            fragments.append(polygon)
    region = fi.polygon_mesh(fragments, 'CompleteActualConsoleCupRegion')
    result['complete_console_region_to_design'] = require_cover(region, reference['console'], 'Unexpected console surface in cup neighborhood')
    result['complete_design_to_console_region'] = require_cover(reference['console'], region, 'Missing complete pocket/top boundary')
    # This finite outer ring lies inside both actual polygons: its inner radius
    # is outside every pocket vertex, its outer radius is below every lip edge.
    lip_expected = circle(cx, .044, top)
    lip_actual = nearest_ring(cup, lip_expected)
    lip_planes = fi.polygon_planes(lip_actual, np.array([0., 0., 1.]))
    apothem = min(float(n @ np.array([cx, -.113, top]))-d for n, d in lip_planes)
    cavity_radius = max(float(np.linalg.norm(p[:2]-center)) for p in cavity_top)
    band = apothem-cavity_radius
    require(band > .0008, 'No continuous finite flange seat band')
    support_inner = (cavity_radius+8*GUARD)/math.cos(math.pi/32)
    support_outer = apothem-8*GUARD
    require(support_outer > support_inner, 'Finite support construction collapsed')
    support = fi.polygon_mesh(strip(circle(cx, support_outer, top), circle(cx, support_inner, top)), 'FiniteCupSupportRing')
    result['complete_flange_support_to_console'] = require_cover(support, console, 'Cup lip has an unsupported finite seat region')
    # Full cup boundary matching already binds the entire underside plane.
    flange_error = max(abs(float(p[2])-top) for p in lip_actual)
    result.update(status='passed', complete_recess_triangle_count=recess_count,
                  minimum_recess_side_clearance_m=minimum_side, minimum_recess_bottom_clearance_m=minimum_bottom,
                  minimum_receiving_radius_m=receiving_radius, receiving_depth_m=depth, bottom_thickness_m=thickness,
                  continuous_support_band_lower_bound_m=band, maximum_flange_plane_error_m=flange_error,
                  console_region_fragment_count=len(fragments), all_console_region_fragments_checked=True,
                  finite_mount={'plane_z_m': top, 'outer_lip_vertices_m': [p.tolist() for p in lip_actual],
                                'actual_pocket_upper_vertices_m': [p.tolist() for p in cavity_top],
                                'actual_pocket_lower_vertices_m': [p.tolist() for p in cavity_bottom],
                                'support_ring_vertex_radii_m': [support_inner, support_outer]},
                  proof_scope='Every complete cup boundary and local console boundary checked. Only the finite planar lip seat is a mating interface; recessed sides/bottom stay clear. Other geometry and human acceptance remain separate.')
    return result


def box_row(name, low, high, ancestors):
    vertices = [[float(x), float(y), float(z)] for z in (low[2], high[2])
                for y in (low[1], high[1]) for x in (low[0], high[0])]
    faces = [[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
             [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]]
    return {'name': name, 'vertices': vertices, 'triangles': faces, 'properties': {}, 'ancestors': ancestors}


def negative_controls(rows):
    results = []
    for name in CUPS:
        cx = -.068 if name.endswith('_-1') else .068
        for kind in NEGATIVES:
            cup, console = copy.deepcopy(rows[name]), copy.deepcopy(rows[CONSOLE])
            if kind in ('down200um', 'up200um'):
                for point in cup['vertices']:
                    point[2] += -.0002 if kind == 'down200um' else .0002
                mutated = cup
            elif kind == 'uncut_console':
                points = np.asarray(console['vertices'])
                console = box_row(CONSOLE, points.min(0), points.max(0), console['ancestors']); mutated = console
            elif kind == 'raised_pocket_corner':
                top = max(p[2] for p in console['vertices']); floor = top+.002-.060-.003-.0012
                eligible = [i for i, p in enumerate(console['vertices'])
                            if abs(p[2]-floor) <= GUARD and math.hypot(p[0]-cx, p[1]+.113) < .0435]
                require(eligible, 'Pocket-corner negative lacks an actual vertex')
                console['vertices'][eligible[0]][2] += .002
                mutated = console
            else:
                top = max(p[2] for p in console['vertices'])
                centers = [i for i, p in enumerate(cup['vertices'])
                           if math.hypot(p[0]-cx, p[1]+.113) <= GUARD and abs(p[2]-(top-.058)) <= GUARD]
                require(len(centers) == 1, 'Receiving-blocker control lacks the actual inner floor center')
                cup['vertices'][centers[0]][2] += .030
                mutated = cup
            # A malformed scalar or mesh must fail this control preparation,
            # not masquerade as the intended geometric rejection.
            fi.validate_row(mutated['name'], mutated)
            rejected, failure = False, ''
            try:
                inspect_pair(cup, console)
            except ValueError as error:
                rejected, failure = True, str(error)
            results.append({'cup': name, 'name': kind, 'rejected': rejected, 'failure': failure,
                            'mutated_schema_topology_valid': True,
                            'mutated_mesh_sha256': hashlib.sha256(json.dumps(mutated, sort_keys=True, allow_nan=False).encode()).hexdigest()})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists() and args.output.resolve() != args.geometry.resolve(), 'Choose a fresh report path')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started, inputs = time.monotonic(), {}
    record = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.platform(), 'python': sys.version, 'status': 'failed',
              'source_sha256': None, 'guard_m': GUARD, 'human_approval_reference': None,
              'scope': 'Two finite cupholder/console interfaces only. Other contacts, motion, individual mesh self validity, LOD, art and human gates remain separate.'}
    try:
        geometry_dependencies(); record['numpy'] = np.__version__
        import bpy
        record['blender_version'] = bpy.app.version_string
        record['blender_build_hash'] = bpy.app.build_hash.decode()
        payload = strict_json(gzip.decompress(args.geometry.read_bytes()))
        require(isinstance(payload, dict) and isinstance(payload.get('meshes'), dict), 'Evaluated geometry object required')
        source_hash, source = payload.get('source_sha256'), Path(payload['source_path'])
        require(isinstance(source_hash, str) and re.fullmatch('[0-9a-f]{64}', source_hash)
                and source.is_file() and sha(source) == source_hash, 'Actual source hash mismatch')
        record['source_sha256'] = source_hash
        specification = payload.get('embedded_specification')
        require(isinstance(specification, dict), 'Embedded source specification required')
        contract = specification.get('original_packaging', {}).get('cabin_revision20', {}).get('cupholders')
        require(isinstance(contract, dict), 'Source has no locked cup construction')
        for key, value in CONTRACT.items():
            require(type(contract.get(key)) is type(value) and contract[key] == value, 'Changed locked cup parameter: '+key)
        dependencies = [args.geometry, source, Path(__file__), Path(fi.__file__), Path(fi.precision.__file__),
                        Path(fi.exact_triangles.__file__), Path(fi.wiper_initial.__file__), Path(fi.finish_report.__file__),
                        Path(__file__).with_name('wiper_interassembly.py'), Path(__file__).with_name('wipers.py'),
                        Path(bpy.app.binary_path)]
        inputs = {str(p.resolve()): sha(p) for p in dependencies}
        record['geometry_payload_sha256'] = sha(args.geometry)
        record['git_revision'] = subprocess.check_output(['git', '-C', str(Path(__file__).parent), 'rev-parse', 'HEAD'], text=True).strip()
        rows = payload['meshes']
        require(all(name in rows for name in (*CUPS, CONSOLE)), 'Required cup/console mesh missing')
        require(sorted(name for name in rows if name.startswith('LOD0_Cupholder_')) == list(CUPS), 'Unexpected cup inventory')
        results = []; record['results'] = results
        for name in CUPS:
            result = inspect_pair(rows[name], rows[CONSOLE]); results.append(result)
            print(json.dumps({'pair': result['pair'], 'status': result['status']}), flush=True)
        controls = negative_controls(rows)
        record.update(exact_named_inventory=[[name, CONSOLE] for name in CUPS], interface_count=2,
                      results=results, negative_controls=controls, negative_control_count=len(controls),
                      status='passed' if all(row['rejected'] for row in controls) else 'failed')
    except Exception as error:
        record.update(status='failed', failure=type(error).__name__+': '+str(error))
    finally:
        unchanged = bool(inputs) and all(Path(path).is_file() and sha(path) == digest for path, digest in inputs.items())
        record.update(inputs=[{'path': path, 'sha256': digest} for path, digest in inputs.items()],
                      inputs_unchanged=unchanged, elapsed_seconds=time.monotonic()-started)
        if not unchanged:
            record.update(status='failed', input_failure='Missing or changed cup proof input binding')
        if record['status'] == 'passed':
            try:
                validate_report(record, record['source_sha256'])
            except ValueError as error:
                record.update(status='failed', failure='Report validation: '+str(error))
        args.output.write_text(json.dumps(record, indent=2, allow_nan=False)+'\n', encoding='utf8', newline='\n')
    print(json.dumps({'status': record['status'], 'output': str(args.output)}), flush=True)
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
