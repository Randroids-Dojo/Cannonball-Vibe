"""Complete finite roof-flange, crossover-cap and cabin-pad certificates.

The geometry is the supplied evaluated source. Revision14 defines these exact
interfaces; no source name alone excuses an intersection. Convex partitioning
retains uncovered pieces instead of accepting an overlapping sum of areas.
"""
import copy
import math

import numpy as np
from mathutils import Vector

from geometry import Mesh, bounds, box_distance2
from precision import point_triangle, split_halfspace
from solid_interfaces import GUARD, intersection


def area(poly):
    return math.fsum(float(np.linalg.norm(np.cross(poly[i] - poly[0], poly[i + 1] - poly[0]))) * .5
                     for i in range(1, len(poly) - 1)) if len(poly) > 2 else 0.


def partition(poly, planes):
    """One convex region removed from a polygon, with every remainder retained."""
    remaining, inside = [], poly
    for normal, constant in planes:
        inside, outside = split_halfspace(inside, normal, constant)
        if outside:
            remaining.append(outside)
        if not inside:
            break
    return inside, remaining


def polygon_planes(poly, normal):
    result = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        edge = np.cross(normal, b - a)
        length = float(np.linalg.norm(edge))
        if length:
            edge /= length
            result.append((edge, float(edge @ a)))
    return result


def roof_charts(row, upper):
    points = np.asarray(row['vertices'], dtype=float)
    charts = []
    for index, tri in enumerate(row['triangles']):
        poly = [points[i] for i in tri]
        normal = np.cross(poly[1] - poly[0], poly[2] - poly[0])
        if (normal[2] if upper else -normal[2]) / np.linalg.norm(normal) <= .5:
            continue
        if not upper:
            poly.reverse()
            normal = -normal
        charts.append({'triangle': index, 'normal': normal, 'constant': float(normal @ poly[0]),
                       'planes': polygon_planes(poly, np.array([0., 0., 1.])),
                       'low': np.min(poly, axis=0)[:2], 'high': np.max(poly, axis=0)[:2]})
    assert len(charts) == 448, 'Actual inner/outer roof facet inventory changed; inspect before updating contract'
    return charts


def relative_height(row, charts):
    minimum, maximum, pieces = math.inf, -math.inf, 0
    worst, uncovered = None, []
    vertices = np.asarray(row['vertices'], dtype=float)
    for index, triangle in enumerate(row['triangles']):
        poly = [vertices[i] for i in triangle]
        low, high = np.min(poly, axis=0)[:2], np.max(poly, axis=0)[:2]
        remaining = [poly]
        for chart in charts:
            if np.any(high < chart['low']) or np.any(low > chart['high']):
                continue
            todo = []
            for fragment in remaining:
                inside, outside = partition(fragment, chart['planes'])
                todo.extend(outside)
                if inside:
                    pieces += 1
                    normal = chart['normal']
                    for point in inside:
                        roof_z = (chart['constant'] - normal[0] * point[0] - normal[1] * point[1]) / normal[2]
                        delta = float(point[2] - roof_z)
                        if delta > maximum:
                            maximum = delta
                            worst = {'triangle': index, 'roof_triangle': chart['triangle'],
                                     'point_m': point.tolist(), 'roof_z_m': float(roof_z)}
                        minimum = min(minimum, delta)
            remaining = todo
            if not remaining:
                break
        # A boundary polygon can be numerically duplicated on a chart edge.
        # Even such degenerate pieces must be covered; none is dropped by area.
        for fragment in remaining:
            covered = False
            for chart in charts:
                if all(all(float(n @ point - d) >= -1e-12 for n, d in chart['planes']) for point in fragment):
                    normal = chart['normal']
                    deltas = [float(p[2] - (chart['constant'] - normal[0] * p[0] - normal[1] * p[1]) / normal[2]) for p in fragment]
                    minimum, maximum = min(minimum, *deltas), max(maximum, *deltas)
                    covered = True
                    break
            if not covered:
                uncovered.append({'triangle': index, 'area_m2': area(fragment), 'polygon_m': [p.tolist() for p in fragment]})
    return {'minimum_relative_z_m': minimum, 'maximum_relative_z_m': maximum,
            'worst_above_witness': worst, 'partition_pieces': pieces, 'uncovered': uncovered,
            'method': 'Every complete input triangle partitioned by actual roof XY facets; affine height extrema at all fragment vertices. Boundary arithmetic guard 1e-12 m; acceptance guard 1e-6 m.'}


def roof_joint(rows, side):
    name = 'LOD0_RoofSideRail_' + side
    roof, rail = rows['LOD0_Roof'], rows[name]
    outer, inner = roof_charts(roof, True), roof_charts(roof, False)
    solid = intersection(roof, rail)
    actual = relative_height(rail, outer)
    exterior = relative_height(solid, outer) if solid['triangles'] else None
    interior = relative_height(solid, inner) if solid['triangles'] else None
    finite = max((max(.592 - abs(p[0]), abs(p[0]) - .741, -1.230 - p[1], p[1] - .100)
                  for p in solid['vertices']), default=math.inf)
    quality = solid['quality']
    passed = (solid['triangles'] and quality['nonmanifold_edges'] == quality['duplicate_triangles'] == 0
              and abs(quality['signed_volume_m3']) > 0 and quality['minimum_area_m2'] > 0
              and not actual['uncovered'] and not exterior['uncovered'] and not interior['uncovered']
              and finite <= GUARD and actual['maximum_relative_z_m'] <= -.00055 + GUARD
              and exterior['maximum_relative_z_m'] <= -.00055 + GUARD
              and interior['minimum_relative_z_m'] >= -GUARD
              and interior['maximum_relative_z_m'] <= .00065 + GUARD)
    return {'pair': ['LOD0_Roof', name], 'status': 'passed' if passed else 'failed',
            'policy': 'Revision14 finite formed reinforcement flange, not a zero-volume seat',
            'guard_m': GUARD, 'maximum_inner_penetration_m': .00065, 'minimum_remaining_outer_skin_m': .00055,
            'complete_rail_relative_outer_roof': actual, 'intersection_relative_outer_roof': exterior,
            'intersection_relative_inner_roof': interior, 'finite_xy_residual_m': finite if math.isfinite(finite) else None,
            'intersection_quality': quality}, solid


def crossover_joint(rows, side):
    a, b = 'LOD0_MainTankCrossoverBridge', 'LOD0_MainTankCrossover_' + str(side)
    plane = side * .100
    first, second = rows[a], rows[b]
    violation = max(max(side * (p[0] - plane) for p in first['vertices']),
                    max(-side * (p[0] - plane) for p in second['vertices']))
    caps = []
    for row in (first, second):
        cap = sorted((np.asarray(p) for p in row['vertices'] if abs(p[0] - plane) <= GUARD),
                     key=lambda p: math.atan2(p[2] - .421, p[1] + .745))
        caps.append(cap)
    contact = []
    if len(caps[0]) == len(caps[1]) == 10:
        contact, _ = partition(caps[0], polygon_planes(caps[1], np.array([1., 0., 0.])))
    radius = max((math.hypot(p[1] + .745, p[2] - .421) for cap in caps for p in cap), default=math.inf)
    gap = max((p[0] for p in caps[0]), default=math.inf) - min((p[0] for p in caps[1]), default=-math.inf)
    passed = violation <= GUARD and radius <= .009 + GUARD and abs(gap) <= GUARD and area(contact) > 0
    return {'pair': [a, b], 'status': 'passed' if passed else 'failed', 'plane_x_m': plane,
            'guard_m': GUARD, 'complete_halfspace_violation_m': violation,
            'maximum_cap_radius_m': radius if math.isfinite(radius) else None,
            'cap_vertices': [len(cap) for cap in caps], 'plane_gap_m': gap if math.isfinite(gap) else None,
            'contact_area_m2': area(contact), 'contact_polygon_m': [p.tolist() for p in contact],
            'method': 'Whole opposite solid halfspaces and positive overlap of complete finite convex10-gon endcaps'}


def pad_joint(rows, name, other_name, top):
    pad, other = rows[name], rows[other_name]
    low, high = bounds(pad['vertices'])
    assert len(pad['vertices']) == 8 and len(pad['triangles']) == 12
    assert all(abs((high[i] - low[i]) - .012) <= GUARD for i in (0, 1))
    assert abs(low[2] - .1399) <= .0002 and abs(high[2] - .1424) <= .0002
    plane = high[2] if top else low[2]
    prism_low = [low[0], low[1], low[2] - GUARD]
    prism_high = [high[0], high[1], high[2] + GUARD]
    planes = []
    for axis in range(3):
        n = np.eye(3)[axis]
        planes.extend(((n, prism_low[axis]), (-n, -prism_high[axis])))
    footprint = [np.array([x, y, plane]) for x, y in
                 ((low[0], low[1]), (high[0], low[1]), (high[0], high[1]), (low[0], high[1]))]
    remaining = [footprint]
    maximum, pieces, originals = 0., [], []
    for index, tri in enumerate(other['triangles']):
        poly = [np.asarray(other['vertices'][i]) for i in tri]
        if box_distance2(bounds(poly), (prism_low, prism_high)) > 0:
            continue
        clipped, _ = partition(poly, planes)
        if not clipped:
            continue
        residual = max(abs(float(p[2] - plane)) for p in clipped)
        maximum = max(maximum, residual)
        projected = [np.array([p[0], p[1], plane]) for p in clipped]
        signed = sum(float(np.cross(projected[i] - projected[0], projected[i + 1] - projected[0])[2]) for i in range(1, len(projected) - 1))
        if signed < 0:
            projected.reverse()
        if area(projected) > 0 and residual <= GUARD:
            originals.append((index, np.asarray(poly)))
            next_remaining = []
            for fragment in remaining:
                _, outside = partition(fragment, polygon_planes(projected, np.array([0., 0., 1.])))
                next_remaining.extend(outside)
            remaining = next_remaining
        pieces.append({'triangle': index, 'maximum_plane_residual_m': residual, 'polygon_m': [p.tolist() for p in clipped]})
    # Set subtraction can duplicate roundoff slivers at shared triangle edges.
    # Bound every entire residual convex polygon to ONE original triangle via
    # all its vertices. Distance to a convex triangle is convex, so this covers
    # every point. The1pm arithmetic threshold is much smaller than the existing
    #1um geometry guard; area magnitude alone never accepts an uncovered region.
    uncovered = math.fsum(area(p) for p in remaining)
    residual_bounds = []
    for fragment in remaining:
        best = min(({'triangle': index,
                     'maximum_distance_m': max(float(np.linalg.norm(point - point_triangle(point, triangle)))
                                               for point in fragment)} for index, triangle in originals),
                   key=lambda row: row['maximum_distance_m'], default=None)
        residual_bounds.append(best)
    covered = all(row is not None and row['maximum_distance_m'] <= 1e-12 for row in residual_bounds)
    center = [(x + y) * .5 for x, y in zip(low, high)]
    inside = Mesh(other).inside(Vector(center))
    separated = top or max(p[2] for p in other['vertices']) <= plane + GUARD
    passed = (maximum <= GUARD and covered and inside is not None
              and all(count % 2 == 0 for count in inside['ray_hit_counts']) and separated and bool(pieces))
    return {'pair': [name, other_name], 'status': 'passed' if passed else 'failed',
            'policy': 'Revision14 exact12 mm square complete upper/body or lower/tray mounting face',
            'plane_z_m': plane, 'pad_bounds_m': [low, high], 'guard_m': GUARD,
            'maximum_plane_residual_m': maximum, 'uncovered_footprint_area_m2': uncovered,
            'residual_full_polygon_bounds': residual_bounds, 'residual_arithmetic_bound_m': 1e-12,
            'complete_footprint_area_m2': (high[0] - low[0]) * (high[1] - low[1]),
            'pad_interior': inside, 'entire_tray_opposite_halfspace': separated,
            'clipped_original_triangles': pieces}


def prove(rows, rule):
    kind = rule['fitted_kind']
    if kind == 'roof':
        return roof_joint(rows, rule['side'])
    if kind == 'crossover':
        return crossover_joint(rows, rule['side']), None
    if kind == 'cabin-pad':
        return pad_joint(rows, rule['pad'], rule['other'], rule['top']), None
    raise ValueError(kind)


def negative_controls(rows):
    shifted = copy.deepcopy(rows['LOD0_CabinTrayMount_1_2'])
    shifted['vertices'] = [[x, y, z + .0001] for x, y, z in shifted['vertices']]
    pad = pad_joint(rows | {shifted['name']: shifted}, shifted['name'], 'LOD0_StructuralBody', True)
    shifted = copy.deepcopy(rows['LOD0_MainTankCrossoverBridge'])
    shifted['vertices'] = [[x + .0001, y, z] for x, y, z in shifted['vertices']]
    crossover = crossover_joint(rows | {shifted['name']: shifted}, 1)
    shifted = copy.deepcopy(rows['LOD0_RoofSideRail_L'])
    shifted['vertices'] = [[x, y, z + .002] for x, y, z in shifted['vertices']]
    roof, _ = roof_joint(rows | {shifted['name']: shifted}, 'L')
    controls = [{'name': 'pad100um-body-intrusion', 'result': pad},
                {'name': 'crossover100um-overlap', 'result': crossover},
                {'name': 'roof2mm-outward-intrusion', 'result': roof}]
    assert all(row['result']['status'] == 'failed' for row in controls)
    return controls
