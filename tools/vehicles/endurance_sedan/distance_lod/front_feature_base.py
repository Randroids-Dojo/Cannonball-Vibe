"""Protect actual original front shoulder triangles during native LOD generation.

The original object and existing LOD paint implementation are explicit inputs.
No file access, source saves, hardcoded face IDs or synthetic normal field.
"""
import math


def _key(points):
    return tuple(sorted(tuple(point) for point in points))


def _angle(a, b):
    a = tuple(float(value) for value in a)
    b = tuple(float(value) for value in b)
    if not all(math.isfinite(value) for value in a + b):
        raise ValueError('Nonfinite protected original normal')
    na, nb = math.hypot(*a), math.hypot(*b)
    if abs(na - 1.) > 1e-6 or abs(nb - 1.) > 1e-6:
        raise ValueError('Nonunit protected original normal')
    cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
             a[0] * b[1] - a[1] * b[0])
    return math.degrees(math.atan2(math.hypot(*cross), sum(x * y for x, y in zip(a, b))))


def capture(source):
    if source.name != 'LOD0_FrontBumper' or source.parent.name != 'Visual_LOD0' or source.modifiers:
        raise ValueError('Expected actual frozen original front bumper')
    data = source.data
    if [material.name for material in data.materials] != ['Material_Paint']:
        raise ValueError('Original front material changed')
    tag = data.attributes.get('cb_fascia_cap')
    strength = data.attributes.get('__mod_weightednormals_faceweight')
    if any(field is None or field.domain != 'FACE' or field.data_type != 'INT' for field in (tag, strength)):
        raise ValueError('Missing original front face provenance')
    if data.uv_layers.active is None:
        raise ValueError('Missing original front UV')
    data.calc_loop_triangles()
    world = {vertex.index: source.matrix_world @ vertex.co for vertex in data.vertices}
    seeds = []
    for triangle in data.loop_triangles:
        polygon = data.polygons[triangle.polygon_index]
        points = [world[index] for index in triangle.vertices]
        if (tag.data[polygon.index].value != 0 or strength.data[polygon.index].value != 16384
                or not polygon.use_smooth or min(point.z for point in points) < .80):
            continue
        if max(point.y for point in points) < 2.23 and not (
                max(abs(point.x) for point in points) >= .65 and max(point.y for point in points) >= 2.04):
            continue
        seeds.append(triangle)
    if not seeds:
        raise ValueError('Empty original front shoulder feature')
    protected = {index for triangle in seeds for index in triangle.vertices}
    rows = []
    for triangle in data.loop_triangles:
        if not all(index in protected for index in triangle.vertices):
            continue
        points = [data.vertices[index].co.copy() for index in triangle.vertices]
        if len(set(tuple(point) for point in points)) != 3 or triangle.area <= 1e-12:
            raise ValueError('Degenerate original protected triangle')
        normals = [data.corner_normals[index].vector.copy() for index in triangle.loops]
        for normal in normals:
            _angle(normal, normal)
        rows.append({'points': points, 'key': _key(points), 'normals': normals,
                     'uv': [data.uv_layers.active.data[index].uv.copy() for index in triangle.loops],
                     'smooth': data.polygons[triangle.polygon_index].use_smooth})
    if len({_key(row['points']) for row in rows}) != len(rows):
        raise ValueError('Ambiguous original protected triangle')
    return {'triangles': rows, 'points': {tuple(data.vertices[index].co) for index in protected},
            'matrix': tuple(tuple(row) for row in source.matrix_world),
            'seed_count': len(seeds), 'initial': len(data.loop_triangles),
            'source_name': source.name}


def verify(obj, reference):
    if tuple(tuple(row) for row in obj.matrix_world) != reference['matrix']:
        raise ValueError('Protected component frame changed')
    data = obj.data
    data.calc_loop_triangles()
    found = {}
    for triangle in data.loop_triangles:
        points = [data.vertices[index].co.copy() for index in triangle.vertices]
        found.setdefault(_key(points), []).append((triangle, points))
    maximum = 0.
    for original in reference['triangles']:
        matches = found.get(original['key'], [])
        if len(matches) != 1:
            raise ValueError('Lost, displaced or ambiguous protected front triangle')
        triangle, points = matches[0]
        order = [next(index for index, value in enumerate(original['points'])
                      if tuple(value) == tuple(point)) for point in points]
        if tuple(order) not in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
            raise ValueError('Protected front winding changed')
        if data.polygons[triangle.polygon_index].use_smooth != original['smooth']:
            raise ValueError('Protected front smooth policy changed')
        for loop, index in zip(triangle.loops, order):
            if tuple(data.uv_layers.active.data[loop].uv) != tuple(original['uv'][index]):
                raise ValueError('Protected front UV changed')
            angle = _angle(data.corner_normals[loop].vector, original['normals'][index])
            if angle > .025:
                raise ValueError('Protected original front field exceeds .025 degree native guard')
            maximum = max(maximum, angle)
    return {'complete_original_triangles': len(reference['triangles']),
            'position_and_UV_maximum_difference': 0., 'winding_preserved': True,
            'maximum_native_normal_angle_degrees': maximum,
            'maximum_native_normal_angle_limit_degrees': .025}


class Adapter:
    def __init__(self, source, existing, encoder):
        self.reference = capture(source)
        self.existing = existing
        self.encoder = encoder

    def prepare(self, obj):
        reference = self.reference
        if tuple(tuple(row) for row in obj.matrix_world) != reference['matrix']:
            raise ValueError('Original to private component frame changed')
        data = obj.data
        data.calc_loop_triangles()
        if len(data.loop_triangles) != reference['initial']:
            raise ValueError('Expected complete original component before simplification')
        # Verify complete original field after the first bake, before protection.
        verify(obj, reference)
        protected = {vertex.index for vertex in data.vertices if tuple(vertex.co) in reference['points']}
        if len(protected) != len(reference['points']):
            raise ValueError('Missing original protected positions')
        return {'vertices': protected, 'triangles': reference['triangles'],
                'boundary': sum(any(index in protected for index in triangle.vertices)
                                for triangle in data.loop_triangles),
                'initial': len(data.loop_triangles), 'full': False, 'parent': obj.parent.name}

    def configure(self, obj, modifier, protection, ratio):
        return self.existing.configure(obj, modifier, protection, ratio)

    def restore(self, obj, protection):
        mesh = obj.data
        mesh.calc_loop_triangles()
        physical_before = ([tuple(v.co) for v in mesh.vertices],
            [(tuple(p.vertices), p.material_index, p.use_smooth) for p in mesh.polygons],
            [tuple(e.vertices) for e in mesh.edges], [m.name for m in mesh.materials])
        uv_before = [tuple(v.uv) for v in mesh.uv_layers.active.data]
        sharp_before = [edge.use_edge_sharp for edge in mesh.edges]
        before = [tuple(normal.vector) for normal in mesh.corner_normals]
        targets = list(before)
        selected = set()
        found = {}
        for triangle in mesh.loop_triangles:
            points = [mesh.vertices[index].co for index in triangle.vertices]
            found.setdefault(_key(points), []).append((triangle, points))
        for original in self.reference['triangles']:
            matches = found.get(original['key'], [])
            if len(matches) != 1:
                raise ValueError('Lost, displaced or ambiguous protected front triangle')
            triangle, points = matches[0]
            order = [next(i for i, value in enumerate(original['points']) if tuple(value) == tuple(point)) for point in points]
            if tuple(order) not in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
                raise ValueError('Protected front winding changed')
            if mesh.polygons[triangle.polygon_index].use_smooth != original['smooth']:
                raise ValueError('Protected front smooth policy changed')
            for loop, index in zip(triangle.loops, order):
                selected.add(loop)
                targets[loop] = tuple(original['normals'][index])
                mesh.uv_layers.active.data[loop].uv = original['uv'][index]
        codec = self.encoder(mesh, targets)
        if not codec['passed']:
            raise ValueError('Native original-field encoding failed')
        after = [tuple(normal.vector) for normal in mesh.corner_normals]
        maximum_all = max(_angle(a, b) for a, b in zip(after, targets))
        maximum_unselected = max((_angle(a, b) for i, (a, b) in enumerate(zip(after, before)) if i not in selected), default=0.)
        if maximum_all > .025 or maximum_unselected > .025:
            raise ValueError('Native field targets or unrelated corners exceed .025 degrees')
        physical_after = ([tuple(v.co) for v in mesh.vertices],
            [(tuple(p.vertices), p.material_index, p.use_smooth) for p in mesh.polygons],
            [tuple(e.vertices) for e in mesh.edges], [m.name for m in mesh.materials])
        if physical_after != physical_before:
            raise ValueError('Original-field encoding changed physical geometry or material')
        if any(tuple(value.uv) != uv_before[index] for index, value in enumerate(mesh.uv_layers.active.data) if index not in selected):
            raise ValueError('Original-field restoration changed unrelated UV')
        result = verify(obj, self.reference)
        result.update(native_codec=codec, selected_corner_count=len(selected),
            all_target_maximum_degrees=maximum_all, unselected_maximum_degrees=maximum_unselected,
            physical_fields_exact_through_encoding=True, unselected_UV_exact=True,
            sharp_edge_changes=[{'edge': edge.index, 'vertices': list(edge.vertices), 'before': old, 'after': edge.use_edge_sharp}
                                for edge, old in zip(mesh.edges, sharp_before) if edge.use_edge_sharp != old],
            scope='Original protected triangle targets; every unselected target is the actual generated field before encoding. Sharp encoding domains are explicitly split; physical geometry is unchanged.')
        return result
