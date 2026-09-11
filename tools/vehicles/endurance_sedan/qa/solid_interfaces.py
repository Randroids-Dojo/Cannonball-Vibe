"""Native closed-solid construction joints inside individually named finite zones.

Only isolated copies of retained evaluated world triangles are created. These
copies are diagnostic geometry; this module never opens or saves an art source.
"""
from collections import Counter, defaultdict
import math
import numpy as np

import bpy
from mathutils import Vector, geometry

from geometry import Mesh, contact
from surface_minimum import Distances
from precision import point_triangle, subtract_prism

GUARD = 1e-6


def components(triangles):
    neighbors = defaultdict(set)
    for tri in triangles:
        for i in tri:
            neighbors[i].update(tri)
    pending = set(neighbors)
    result = []
    while pending:
        component = {pending.pop()}
        todo = list(component)
        while todo:
            for other in neighbors[todo.pop()] - component:
                component.add(other)
                pending.discard(other)
                todo.append(other)
        result.append(component)
    return result


def shape_quality(vertices, triangles):
    edges = Counter(tuple(sorted((tri[i], tri[(i + 1) % 3])))
                    for tri in triangles for i in range(3))
    duplicates = sum(value - 1 for value in Counter(tuple(sorted(tri)) for tri in triangles).values())
    points = [Vector(v) for v in vertices]
    areas = [((points[b] - points[a]).cross(points[c] - points[a])).length * .5 for a, b, c in triangles]
    origin = vertices[0] if vertices else (0., 0., 0.)
    local = [[v[i] - origin[i] for i in range(3)] for v in vertices]
    def triple(tri):
        a, b, c = (local[i] for i in tri)
        return (a[0] * (b[1] * c[2] - b[2] * c[1])
                + a[1] * (b[2] * c[0] - b[0] * c[2])
                + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return {'nonmanifold_edges': sum(value != 2 for value in edges.values()),
            'duplicate_triangles': duplicates,
            'degenerate_triangles': sum(area <= 1e-12 for area in areas),
            'minimum_area_m2': min(areas, default=None),
            'signed_volume_m3': math.fsum(triple(tri) for tri in triangles) / 6}


def intersection(a, b):
    objects = []
    datablocks = []
    try:
        for row in (a, b):
            data = bpy.data.meshes.new('QA_IntersectionInput')
            data.from_pydata(row['vertices'], [], row['triangles'])
            data.update()
            obj = bpy.data.objects.new('QA_IntersectionInput', data)
            bpy.context.scene.collection.objects.link(obj)
            objects.append(obj)
            datablocks.append(data)
        first, second = objects
        bpy.context.view_layer.objects.active = first
        modifier = first.modifiers.new('QA full solid intersection', 'BOOLEAN')
        modifier.operation = 'INTERSECT'
        modifier.solver = 'EXACT'
        modifier.object = second
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        data = first.data
        if data not in datablocks:
            datablocks.append(data)
        data.calc_loop_triangles()
        vertices = [list(v.co) for v in data.vertices]
        triangles = [list(tri.vertices) for tri in data.loop_triangles]
        return {'vertices': vertices, 'triangles': triangles,
                'quality': shape_quality(vertices, triangles)}
    finally:
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for data in datablocks:
            if data.users == 0:
                bpy.data.meshes.remove(data)


def point_residual(zone, point):
    kind = zone['kind']
    if kind == 'box':
        return max(max(a - value, value - b) for a, value, b in
                   zip(zone['low_m'], point, zone['high_m']))
    if kind == 'sphere':
        return math.dist(point, zone['center_m']) - zone['radius_m']
    if kind == 'finite_cylinder':
        start, end = Vector(zone['start_m']), Vector(zone['end_m'])
        length = (end - start).length
        axis = (end - start) / length if length else Vector(zone['axis_source']).normalized()
        delta = Vector(point) - start
        axial = delta.dot(axis)
        radial = (delta - axial * axis).length
        return max(-axial, axial - length, radial - zone['outer_radius_m'], zone['inner_radius_m'] - radial)
    raise ValueError('Unsupported finite joint region: ' + kind)


def component_region(mesh, indices, zone):
    """Convex outer bounds, plus full triangle minimum for an annular hole."""
    maximum = max(point_residual(zone, mesh['vertices'][i]) for i in indices)
    result = {'maximum_vertex_residual_m': maximum, 'guard_m': GUARD}
    if zone['kind'] == 'finite_cylinder' and zone['inner_radius_m'] > 0:
        start, end = Vector(zone['start_m']), Vector(zone['end_m'])
        axis = (end - start).normalized()
        def project(point):
            delta = Vector(point) - start
            return delta - axis * delta.dot(axis)
        points = {i: project(mesh['vertices'][i]) for i in indices}
        minimum = math.inf
        witness = None
        for index, tri in enumerate(mesh['triangles']):
            if tri[0] not in indices:
                continue
            vertices = [points[i] for i in tri]
            if (vertices[1] - vertices[0]).cross(vertices[2] - vertices[0]).length_squared > 1e-24:
                radial = geometry.closest_point_on_tri(Vector(), *vertices).length
            else:
                radial = min(v.length for v in vertices)
                for i in range(3):
                    p, q = vertices[i], vertices[(i + 1) % 3]
                    delta = q - p
                    t = max(0., min(1., -p.dot(delta) / delta.length_squared)) if delta.length_squared else 0.
                    radial = min(radial, (p + t * delta).length)
            if radial < minimum:
                minimum, witness = radial, index
        result.update(minimum_full_triangle_radius_m=minimum, radial_triangle=witness)
        maximum = max(maximum, zone['inner_radius_m'] - minimum)
    result.update(maximum_outside_m=maximum, status='passed' if maximum <= GUARD else 'failed')
    return result


def plane_joint(rows, rule):
    zone = rule['allowed_contact_region']
    point = Vector(zone['start_m'])
    axis = Vector(zone['axis_source']).normalized()
    a, b = (rows[name] for name in rule['pair'])
    ranges = []
    for row in (a, b):
        values = [(Vector(v) - point).dot(axis) for v in row['vertices']]
        ranges.append([min(values), max(values)])
    separated = ((ranges[0][0] >= -GUARD and ranges[1][1] <= GUARD)
                 or (ranges[1][0] >= -GUARD and ranges[0][1] <= GUARD))
    # A larger component can have unrelated vertices on the same global plane.
    # Only the smaller full cap is the intended contact footprint.
    footprints = []
    for row in (a, b):
        vertices = [v for v in row['vertices'] if abs((Vector(v) - point).dot(axis)) <= GUARD]
        if len(vertices) >= 3:
            footprints.append(max(point_residual(zone, v) for v in vertices))
    footprint = min(footprints, default=math.inf)
    observed = contact(Mesh(a), Mesh(b))
    minimum = Distances(rows).minimum(a['name'], b['name'])
    return {'pair': rule['pair'], 'method': 'Entire solids in opposite closed halfspaces; smaller cap contained in the named finite disk',
            'projection_ranges_m': ranges, 'finite_disk_residual_m': footprint,
            'contact_witness': observed, 'minimum': minimum,
            'status': 'passed' if separated and footprint <= GUARD and minimum['distance_m'] <= GUARD else 'failed'}


def boundary_shell(mesh, target, maximum=GUARD, maximum_cells=100000):
    """Cover every full diagnostic triangle by actual source-triangle prisms.

    A closed orthogonal prism of half-height<1um above one original triangle is
    wholly inside its1um Euclidean neighborhood. Exact convex clipping removes
    only certified regions and retains every remaining polygon, including
    zero-area Boolean boundary sheets. This avoids nearest-face discontinuities
    and cannot pass by area sums that double-count overlapping patches.
    """
    vertices = np.asarray(mesh['vertices'], dtype=float)
    target_triangles = np.asarray(target['vertices'], dtype=float)[np.asarray(target['triangles'])]
    low, high = target_triangles.min(axis=1), target_triangles.max(axis=1)
    cells, worst = 0, 0.
    for index, indices in enumerate(mesh['triangles']):
        triangle = vertices[indices]
        candidates = np.flatnonzero(np.all(low <= triangle.max(axis=0) + maximum, axis=1)
                                    & np.all(high >= triangle.min(axis=0) - maximum, axis=1))
        remaining = [list(triangle)]
        for face in candidates:
            retained = []
            surface = target_triangles[face]
            for polygon in remaining:
                cells += 1
                bound = max(float(np.linalg.norm(point - point_triangle(point, surface))) for point in polygon)
                if bound <= maximum - 1e-9:
                    worst = max(worst, bound)
                    continue
                outside, covered = subtract_prism(polygon, surface, maximum - 1e-9)
                retained.extend(outside)
                if covered:
                    normal = np.cross(surface[1] - surface[0], surface[2] - surface[0])
                    normal /= np.linalg.norm(normal)
                    worst = max(worst, max(abs(float((point - surface[0]) @ normal)) for point in covered))
            remaining = retained
            if not remaining:
                break
            if cells >= maximum_cells or len(remaining) > 5000:
                return {'status': 'unresolved', 'target': target['name'], 'triangle': index, 'cells': cells}
        if remaining:
            unresolved = []
            for polygon in remaining:
                accepted = False
                for face in candidates:
                    bound = max(float(np.linalg.norm(point - point_triangle(point, target_triangles[face]))) for point in polygon)
                    if bound <= maximum:
                        worst = max(worst, bound)
                        accepted = True
                        break
                if not accepted:
                    unresolved.append([[float(v) for v in point] for point in polygon])
            if unresolved:
                return {'status': 'unresolved_uncovered_fragment', 'target': target['name'], 'triangle': index,
                        'cells': cells, 'uncovered_polygons': unresolved[:8]}
    return {'status': 'passed', 'target': target['name'], 'full_triangles': len(mesh['triangles']),
            'cells': cells, 'maximum_certified_surface_distance_m': worst,
            'method': 'Complete polygon partition by orthogonal prisms of actual source triangles; no uncovered regions and no area-sum coverage shortcut'}


def prove_join(rows, rule):
    zone = rule['allowed_contact_region']
    if rule['solid_policy'] == 'zero_solid_intrusion' and zone['kind'] == 'finite_cylinder' and zone['start_m'] == zone['end_m']:
        return plane_joint(rows, rule), None
    a, b = (rows[name] for name in rule['pair'])
    mesh = intersection(a, b)
    quality = mesh['quality']
    observed = contact(Mesh(a), Mesh(b))
    result = {'pair': rule['pair'], 'purpose': rule.get('purpose', rule.get('rationale')),
              'solid_policy': rule['solid_policy'], 'region': zone,
              'intersection_vertices': len(mesh['vertices']), 'intersection_triangles': len(mesh['triangles']),
              'quality': quality, 'contact_witness': observed}
    if rule['solid_policy'] == 'zero_solid_intrusion':
        minimum = Distances(rows).minimum(a['name'], b['name'])
        shells = [boundary_shell(mesh, row) for row in (a, b)] if mesh['triangles'] else []
        result.update(minimum=minimum, full_surface_bounds=shells,
                      status='passed' if minimum['distance_m'] <= GUARD and all(row['status'] == 'passed' for row in shells) else 'failed_or_unresolved_boundary_seat')
        result['method'] = ('Native EXACT intersection empty or its complete triangle point set lies within1um of BOTH original boundaries; '
                            'actual contact/gap within the same numeric guard is required. Signed volume cancellation does not decide acceptance.')
        return result, mesh
    # Boolean intersection fragments are evidence, never shipping geometry.
    # Tiny positive faces and exact collinear redundant boundary segments are
    # still included in the complete-region proof. Original source triangles
    # separately retain the1e-12m² gate. Indexed closedness remains required.
    valid = bool(mesh['triangles']) and quality['signed_volume_m3'] > 0 and not any(
        quality[key] for key in ('nonmanifold_edges', 'duplicate_triangles'))
    zones = zone['regions'] if zone['kind'] == 'union' else [zone]
    checks = []
    for ids in components(mesh['triangles']):
        choices = [component_region(mesh, ids, candidate) for candidate in zones]
        choice = min(range(len(choices)), key=lambda i: choices[i]['maximum_outside_m'])
        checks.append({'vertices': len(ids), 'region_index': choice, **choices[choice]})
    result.update(method='Native EXACT complete intersection solids; each full connected component inside one declared finite region',
                  components=checks, status='passed' if valid and checks and all(r['status'] == 'passed' for r in checks) else 'failed_or_unresolved')
    return result, mesh
