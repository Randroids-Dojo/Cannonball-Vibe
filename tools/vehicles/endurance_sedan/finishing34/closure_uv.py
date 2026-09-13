"""Build deterministic evaluated closure UVs; the caller owns adoption/saving.

Only the original seamless XY projection on Hood/Trunk is supported. A private
FLOAT_VECTOR carries the original corner UVs through native modifiers, avoiding
Bevel's unordered FLOAT2 consolidation. Exact rational averaging then rounds
once to binary32. Geometry, native normals and all other attributes must agree.
"""
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
import math
import struct

PROFILE = {'schema': 'closure-native-uv.v1', 'names': {'LOD0_Hood': 'Hood_Hinge', 'LOD0_Trunk': 'Trunk_Hinge'},
           'layer': 'SurfaceMeters', 'meters_per_repeat': .25, 'uv_limit': 1e-6,
           'normal_unit_limit': 1e-6, 'method': 'native-float3-interpolation-exact-continuous-vertex-average'}
ATTRIBUTE = '_cb_closure_uv_interpolant'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def average_binary32(values):
    """Correct nearest/even binary32 of the exact mean of finite binary32s."""
    if not values or any(not math.isfinite(v) or f32(v) != v for v in values):
        raise ValueError('Finite binary32 interpolation values required')
    exact = sum((Fraction(v) for v in values), Fraction()) / len(values)
    if exact == 0:
        return 0.0
    nearby = struct.unpack('<I', struct.pack('<f', float(exact)))[0]
    choices = []
    for bits in (nearby - 1, nearby, nearby + 1):
        if 0 <= bits <= 0xffffffff:
            value = struct.unpack('<f', struct.pack('<I', bits))[0]
            if math.isfinite(value):
                choices.append((abs(Fraction(value) - exact), bits & 1, value))
    return min(choices)[2]


def targets(loop_vertices, carrier, ordinary_uv, vertex_count):
    if not loop_vertices or len(carrier) != len(loop_vertices) or len(ordinary_uv) != len(loop_vertices):
        raise ValueError('Complete interpolation/UV corner inventory required')
    if any(len(v) != 3 or not all(math.isfinite(c) for c in v) or v[2] != 0 for v in carrier):
        raise ValueError('Invalid native UV interpolation carrier')
    buckets = defaultdict(list)
    for index, vertex in enumerate(loop_vertices):
        if type(vertex) is not int or not 0 <= vertex < vertex_count:
            raise ValueError('Invalid native corner vertex')
        buckets[vertex].append(index)
    if set(buckets) != set(range(vertex_count)):
        raise ValueError('Every native vertex requires a complete UV fan')
    for indices in buckets.values():
        if any(len(ordinary_uv[i]) != 2 or not all(math.isfinite(c) for c in ordinary_uv[i]) for i in indices):
            raise ValueError('Invalid evaluated UV field')
        if len({tuple(ordinary_uv[i]) for i in indices}) != 1:
            raise ValueError('Evaluated UV seams require a separate domain')
    mean = {vertex: [average_binary32([carrier[i][axis] for i in indices]) for axis in (0, 1)]
            for vertex, indices in sorted(buckets.items())}
    result = [mean[v] for v in loop_vertices]
    maximum = max(abs(a - b) for x, y in zip(result, ordinary_uv) for a, b in zip(x, y))
    if maximum > PROFILE['uv_limit']:
        raise ValueError('Deterministic UV exceeds unchanged field guard: ' + str(maximum))
    return result, {'vertices': vertex_count, 'corners': len(loop_vertices), 'maximum_UV_error': maximum,
                    'fan_sizes': {str(n): sum(len(v) == n for v in buckets.values()) for n in sorted({len(v) for v in buckets.values()})}}


def attribute_values(attribute):
    values = []
    for item in attribute.data:
        fields = [p.identifier for p in item.bl_rna.properties if p.identifier != 'rna_type']
        if len(fields) != 1:
            raise ValueError('Unsupported native attribute item schema')
        value = getattr(item, fields[0])
        values.append(list(value) if hasattr(value, '__len__') else value)
    return {'domain': attribute.domain, 'data_type': attribute.data_type, 'values': values}


def capture(mesh):
    return {'vertices': [list(v.co) for v in mesh.vertices], 'edges': [list(v.vertices) for v in mesh.edges],
            'sharp': [v.use_edge_sharp for v in mesh.edges], 'polygons': [list(p.vertices) for p in mesh.polygons],
            'polygon_materials': [p.material_index for p in mesh.polygons],
            'smooth': [p.use_smooth for p in mesh.polygons], 'normals': [list(n.vector) for n in mesh.corner_normals],
            'materials': [m.name if m else None for m in mesh.materials],
            'loop_vertices': [l.vertex_index for l in mesh.loops],
            'attributes': {a.name: attribute_values(a) for a in mesh.attributes if a.name not in (ATTRIBUTE, PROFILE['layer'])},
            'uv': {layer.name: [list(v.uv) for v in layer.data] for layer in mesh.uv_layers}}


def validate_source(obj, profile, expected_profile_digest):
    if digest(profile) != expected_profile_digest or profile != PROFILE:
        raise ValueError('Caller-locked closure UV profile mismatch')
    if obj.name not in profile['names'] or obj.parent is None or obj.parent.name != profile['names'][obj.name]:
        raise ValueError('Exact closure semantic identity/parent required')
    if [m.type for m in obj.modifiers] != ['SOLIDIFY', 'BEVEL']:
        raise ValueError('Exact closure modifier stack required')
    solid, bevel = obj.modifiers
    solid_expected = {'thickness': f32(.0012), 'offset': -1.0, 'use_even_offset': True, 'solidify_mode': 'EXTRUDE',
                      'use_rim': True, 'use_rim_only': False, 'material_offset': 0, 'material_offset_rim': 0}
    bevel_expected = {'width': f32(.00045 if obj.name == 'LOD0_Hood' else .0012), 'segments': 2,
                      'angle_limit': f32(.45), 'harden_normals': True, 'affect': 'EDGES', 'limit_method': 'ANGLE',
                      'offset_type': 'OFFSET', 'loop_slide': True, 'use_clamp_overlap': True,
                      'miter_inner': 'MITER_SHARP', 'miter_outer': 'MITER_SHARP', 'mark_seam': False,
                      'mark_sharp': False, 'material': -1, 'face_strength_mode': 'FSTR_NONE'}
    if any(getattr(modifier, k) != value for modifier, expected in ((solid, solid_expected), (bevel, bevel_expected)) for k, value in expected.items()):
        raise ValueError('Unreviewed closure modifier settings')
    mesh = obj.data
    if len(mesh.uv_layers) != 1 or mesh.uv_layers.active.name != profile['layer'] or ATTRIBUTE in mesh.attributes:
        raise ValueError('Exact source UV layer and absent private carrier required')
    values = [list(v.uv) for v in mesh.uv_layers.active.data]
    fans = defaultdict(set)
    for loop, uv in zip(mesh.loops, values):
        vertex = mesh.vertices[loop.vertex_index].co
        if uv != [f32(vertex.x / profile['meters_per_repeat']), f32(vertex.y / profile['meters_per_repeat'])]:
            raise ValueError('Original authored continuous XY mapping required')
        fans[loop.vertex_index].add(tuple(uv))
    if len(values) != len(mesh.loops) or set(fans) != set(range(len(mesh.vertices))) or any(len(v) != 1 for v in fans.values()):
        raise ValueError('Complete seamless original chart required')
    return values


def build(obj, *, profile, expected_profile_digest):
    """Return an owned detached evaluated mesh plus full witness. Never adopt it."""
    import bpy
    if (bpy.app.version, bpy.app.build_hash.decode()) != ((5, 1, 2), 'ec6e62d40fa9'):
        raise ValueError('Pinned official Blender5.1.2 required')
    source_uv = validate_source(obj, profile, expected_profile_digest)
    source = capture(obj.data)
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    data = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        original = capture(data)
    finally:
        evaluated.to_mesh_clear()
    duplicate = obj.copy()
    duplicate.data = obj.data.copy()
    duplicate.name = '_cb_uv_copy_' + obj.name
    bpy.context.scene.collection.objects.link(duplicate)
    private_data = duplicate.data
    result = None
    try:
        attr = private_data.attributes.new(ATTRIBUTE, 'FLOAT_VECTOR', 'CORNER')
        for item, uv in zip(attr.data, source_uv):
            item.vector = (uv[0], uv[1], 0.0)
        private_data.update()
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = duplicate.evaluated_get(graph)
        data = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        try:
            interpolated = capture(data)
            non_uv = {k: interpolated[k] == original[k] for k in original if k != 'uv'}
            if not all(non_uv.values()):
                raise ValueError('Interpolation carrier changed a non-UV native field')
            if any(not all(math.isfinite(v) for v in n) or abs(math.hypot(*n) - 1) > PROFILE['normal_unit_limit'] for n in original['normals']):
                raise ValueError('Original evaluated native normal guard failed')
            attr = data.attributes.get(ATTRIBUTE)
            if attr is None or attr.domain != 'CORNER' or attr.data_type != 'FLOAT_VECTOR':
                raise ValueError('Native interpolation carrier missing/wrong schema')
            carrier = [list(v.vector) for v in attr.data]
            uv, measures = targets(interpolated['loop_vertices'], carrier, interpolated['uv'][profile['layer']], len(data.vertices))
            original_error = max(abs(a - b) for x, y in zip(uv, original['uv'][profile['layer']]) for a, b in zip(x, y))
            if original_error > profile['uv_limit']:
                raise ValueError('Deterministic UV exceeds original evaluation guard')
            result = data.copy()
        finally:
            evaluated.to_mesh_clear()
        result.attributes.remove(result.attributes[ATTRIBUTE])
        result.uv_layers[profile['layer']].data.foreach_set('uv', [v for pair in uv for v in pair])
        result.update()
        final = capture(result)
        if any(final[k] != original[k] for k in original if k != 'uv') or final['uv'][profile['layer']] != uv:
            raise ValueError('Final UV write changed native fields or target bytes')
        if capture(obj.data) != source:
            raise ValueError('Original raw source changed')
        witness = {'schema': 'closure-native-uv-witness.v1', 'name': obj.name, 'profile_sha256': digest(profile),
                   'source_raw': source, 'original_evaluated': original, 'carrier': carrier, 'final': final,
                   'measures': {**measures, 'maximum_original_UV_error': original_error},
                   'target_sha256': digest(uv), 'non_UV_equal': non_uv,
                   'scope': 'Construction candidate only; source file, constructor and final save/export binding are caller responsibilities'}
        return result, witness
    except BaseException:
        if result is not None:
            bpy.data.meshes.remove(result)
        raise
    finally:
        bpy.data.objects.remove(duplicate, do_unlink=True)
        if private_data.users == 0:
            bpy.data.meshes.remove(private_data)
