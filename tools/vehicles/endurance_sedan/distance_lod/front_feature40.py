"""Preserve regenerated current front features through native lower LODs."""
from collections import defaultdict
from pathlib import Path
import json

import bpy

from . import affine_field, front_feature_base
from .front_feature_mixed import material_metadata
from .binding import digest, sha, plain
from ..front_finish40 import verification
from ..qa.front_finish_report import NAMES, RECEIVERS, LOWER_POLICY, require

FEATURES = {'trim_and_material_boundary_fans', 'arch_returns',
            'generated_bevel_returns', 'shoulder_lamp'}
_cache = {}


def bind(source, context):
    expected = context['expected']
    require(context.get('current_revision40') is True and source.name in NAMES,
            'Missing selected current three-panel front context')
    require(digest(expected) == context['expected_binding_digest'] and context['observed'] == expected,
            'Caller current three-panel front binding differs')
    require(expected['schema'] == 'current-guide-front-source-binding40.v1', 'Wrong current front binding schema')
    require(Path(bpy.data.filepath).resolve() == Path(expected['source_path']) and
            sha(expected['source_path']) == expected['source_sha256'], 'Wrong actual current front source')
    require(digest(context['input_files']) == expected['input_files_sha256'] and
            all(Path(row['path']).stat().st_size == row['bytes'] and sha(row['path']) == row['sha256']
                for row in context['input_files']), 'Current front recursive input bytes differ')
    require(digest(context['profile']) == expected['profile_sha256'] and
            context['profile'].get('current_front_revision40') == LOWER_POLICY and
            digest(json.loads(bpy.context.scene['specification'])) == expected['specification_sha256'],
            'Current front profile/specification differs')
    require(sha(context['construction_path']) == expected['construction_sha256'],
            'Current front construction companion differs')
    packet = context['packet']
    require(packet['sha256'] == digest(packet['core']) == expected['field_core_sha256'] and
            packet['core']['current_source_sha256'] == expected['source_sha256'],
            'Current front packet differs from caller-held field binding')
    # Include live mesh/material state in the key; source-file bytes alone cannot
    # authorize an edited in-memory native object.
    from ..front_finish40.native import capture
    from ..qa.shoulder_checkpoint import material_fields
    live = {name: capture(bpy.data.objects[name]) for name in (*NAMES, *RECEIVERS)}
    materials = {name: material_fields(bpy.data.objects[name].data) for name in (*NAMES, *RECEIVERS)}
    key = (context['expected_binding_digest'], digest(live), digest(materials))
    if key not in _cache:
        _cache[key] = verification.verify_packet(
            packet, expected_packet_digest=expected['field_core_sha256'])
    context['current_native_chain_proof'] = _cache[key]
    return expected, packet


def indices(values, count, label):
    require(type(values) is list and values == sorted(set(values)) and
            all(type(value) is int and 0 <= value < count for value in values),
            'Invalid/duplicate current front feature indices: ' + label)
    return set(values)


def capture(source, *, context):
    binding, packet = bind(source, context)
    domains = packet['core']['requested']['feature_domains']
    require(set(domains) == set(NAMES), 'Incomplete current front feature domain')
    return _capture_domain(source, domains[source.name], binding=binding,
        binding_digest=context['expected_binding_digest'],
        expected_materials=packet['core']['current_native'][source.name]['materials'])


def _capture_domain(source, domain, *, binding, binding_digest, expected_materials):
    """Native feature measurement only; production callers bind provenance first."""
    require(source.name in NAMES, 'Unexpected current front native feature source')
    feature_rows = domain['feature_triangles']
    require(set(feature_rows) == FEATURES, 'Incomplete named current front feature families')
    mesh = source.data
    mesh.calc_loop_triangles()
    require(source.parent and source.parent.name == 'Visual_LOD0' and not source.modifiers and
            len(mesh.polygons) == len(mesh.loop_triangles) and all(len(p.vertices) == 3 for p in mesh.polygons),
            'Current front must be an explicit frozen three-panel source')
    require(mesh.uv_layers.active and mesh.uv_layers.active.name == 'SurfaceMeters' and len(mesh.uv_layers) == 1,
            'Current front surface chart changed')
    points = [tuple(vertex.co) for vertex in mesh.vertices]
    triangles = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
    materials = [material.name if material else None for material in mesh.materials]
    material_indices = [triangle.material_index for triangle in mesh.loop_triangles]
    require(materials == expected_materials,
            'Current front ordered material slots differ')
    require(len({front_feature_base._key([points[v] for v in tri]) for tri in triangles}) == len(triangles),
            'Ambiguous current front triangles')
    edges, incident = defaultdict(list), defaultdict(set)
    for index, triangle in enumerate(triangles):
        require(len(set(triangle)) == 3 and mesh.loop_triangles[index].area > 1e-12,
                'Invalid current front source triangle')
        for vertex in triangle:
            incident[vertex].add(index)
        for a, b in zip(triangle, triangle[1:] + triangle[:1]):
            edges[tuple(sorted((a, b)))].append(index)
    require(all(len(faces) == 2 for faces in edges.values()), 'Current front source is not closed')
    trim = {index for index, material in enumerate(material_indices) if materials[material] == 'Material_Trim'}
    boundary = {edge for edge, faces in edges.items() if len({material_indices[index] for index in faces}) > 1}
    boundary_vertices = {vertex for edge in boundary for vertex in edge}
    complete_boundary_fans = {face for vertex in boundary_vertices for face in incident[vertex]}
    features = {name: indices(values, len(triangles), name) for name, values in feature_rows.items()}
    require(trim | complete_boundary_fans <= features['trim_and_material_boundary_fans'],
            'Current front Trim or material-boundary incident fan was omitted')
    if source.name == NAMES[0]:
        require(trim and boundary and features['shoulder_lamp'], 'Missing current bumper aperture/shoulder features')
    else:
        require(features['arch_returns'] and features['shoulder_lamp'], 'Missing current fender arch/shoulder features')
    seeds = set().union(*features.values())
    vertices = {vertex for index in seeds for vertex in triangles[index]}
    protected = {index for index, triangle in enumerate(triangles) if set(triangle) <= vertices}
    require(vertices == indices(domain['protected_vertex_indices'], len(points), 'vertices') and
            protected == indices(domain['protected_triangle_indices'], len(triangles), 'triangles'),
            'Current front complete feature closure differs')
    rows = []
    for index in sorted(protected):
        triangle = mesh.loop_triangles[index]
        normals = [tuple(mesh.corner_normals[loop].vector) for loop in triangle.loops]
        positions = [points[vertex] for vertex in triangle.vertices]
        rows.append({'points': positions, 'key': front_feature_base._key(positions), 'normals': normals,
                     'uv': [tuple(mesh.uv_layers.active.data[loop].uv) for loop in triangle.loops],
                     'smooth': mesh.polygons[triangle.polygon_index].use_smooth,
                     'material_index': triangle.material_index, 'source_triangle': index,
                     'source_field_minimum': affine_field.preserve_field(normals, normals)})
    require(rows, 'Empty current front feature closure')
    return {'triangles': rows, 'points': {points[vertex] for vertex in vertices},
            'matrix': tuple(tuple(row) for row in source.matrix_world), 'seed_count': len(seeds),
            'initial': len(triangles), 'source_name': source.name, 'materials': materials,
            'trim_keys': sorted(front_feature_base._key([points[vertex] for vertex in triangles[index]]) for index in trim),
            'binding': binding, 'binding_digest': binding_digest,
            'domain': {'profile': LOWER_POLICY, 'source': source.name,
                       'complete_triangles': len(rows), 'protected_vertices': len(vertices),
                       'feature_triangles': plain(feature_rows), 'feature_domain_sha256': digest(domain),
                       'actual_Trim_triangles': len(trim), 'material_boundary_edges': len(boundary),
                       'complete_material_boundary_fan_triangles': len(complete_boundary_fans)}}


def verify(obj, reference):
    result = front_feature_base.verify(obj, reference)
    mesh = obj.data
    mesh.calc_loop_triangles()
    require([material.name if material else None for material in mesh.materials] == reference['materials'],
            'Current lower front material slots changed')
    found = {}
    trim = []
    for triangle in mesh.loop_triangles:
        points = [tuple(mesh.vertices[vertex].co) for vertex in triangle.vertices]
        key = front_feature_base._key(points)
        found.setdefault(key, []).append((triangle, points))
        require(0 <= triangle.material_index < len(reference['materials']), 'Invalid current lower front material')
        if reference['materials'][triangle.material_index] == 'Material_Trim':
            trim.append(key)
    require(sorted(trim) == reference['trim_keys'], 'Current lower front lost complete actual Trim geometry')
    fields = []
    for row in reference['triangles']:
        matches = found.get(row['key'], [])
        require(len(matches) == 1, 'Missing/ambiguous current lower feature triangle')
        triangle, points = matches[0]
        require(triangle.material_index == row['material_index'], 'Current lower feature material differs')
        order = [row['points'].index(point) for point in points]
        field = affine_field.preserve_field([row['normals'][index] for index in order],
                    [tuple(mesh.corner_normals[loop].vector) for loop in triangle.loops])
        fields.append({'source_triangle': row['source_triangle'], 'actual_triangle': triangle.index, **field})
    result.update(source=reference['source_name'], materials_exact=True,
                  complete_Trim_triangles=len(trim), complete_affine_field={
                      'triangles': len(fields), 'maximum_angle_upper_degrees': max(
                          row['angle_upper_degrees'] for row in fields), 'rows': fields},
                  actual_material_metadata=material_metadata(obj))
    return result


class Adapter(front_feature_base.Adapter):
    def __init__(self, source, existing, encoder, reference):
        require(source.name == reference['source_name'], 'Wrong current front source')
        self.reference, self.existing, self.encoder = reference, existing, encoder

    def prepare(self, obj):
        verify(obj, self.reference)
        return super().prepare(obj)

    def restore(self, obj, protection):
        result = super().restore(obj, protection)
        result['complete_current_feature_field'] = verify(obj, self.reference)
        return result
