"""Restore a source-bound GLB encoding only after validating every triangle corner.

The editable source stays authoritative. This explicit evaluated export bake
handles platform-dependent split-normal/UV rounding and resulting vertex
deduplication; it does not bypass source, geometry, material or image checks.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

LIMITS = {
    'position_distance_m': 0.0000002,
    'normal_angle_degrees': 0.025,
    'normal_length_error': 0.000001,
    'uv_component_error': 0.00001,
}
MAX_BYTES = 64 * 1024 * 1024
MINIMUM_TRIANGLE_AREA_M2 = 1e-12
ATTRIBUTES = {'POSITION': 'VEC3', 'NORMAL': 'VEC3', 'TEXCOORD_0': 'VEC2', 'TEXCOORD_1': 'VEC2'}
ROOT_KEYS = {'asset', 'scene', 'scenes', 'nodes', 'meshes', 'materials', 'textures', 'images',
             'samplers', 'accessors', 'bufferViews', 'buffers', 'extensionsUsed', 'extensionsRequired'}
EXTENSIONS = {'KHR_materials_clearcoat', 'KHR_materials_transmission', 'KHR_materials_ior'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, minimum=0):
    # This pinned Blender profile uses integer storage tokens. glTF itself also
    # permits integral decimal numbers; rejecting those here is a profile rule.
    return type(value) is int and value >= minimum


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key rejected: ' + key)
        result[key] = value
    return result


def semantic_equal(a, b):
    # Python's ordinary equality considers True == 1; glTF metadata does not.
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(semantic_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(semantic_equal(x, y) for x, y in zip(a, b))
    if type(a) in (int, float) and type(b) in (int, float):
        return a == b
    return type(a) is type(b) and a == b


def oriented_triangle(a, b, c):
    u, v = [y-x for x, y in zip(a, b)], [y-x for x, y in zip(a, c)]
    return (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])


def finite_tree(value):
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_tree(item) for item in value)
    return not isinstance(value, float) or math.isfinite(value)


def parse(raw):
    require(28 <= len(raw) <= MAX_BYTES, 'Unsupported GLB size')
    magic, version, length = struct.unpack_from('<4sII', raw)
    require((magic, version, length) == (b'glTF', 2, len(raw)), 'Invalid GLB header')
    size, kind = struct.unpack_from('<I4s', raw, 12)
    require(kind == b'JSON' and size % 4 == 0 and 28 + size <= len(raw), 'Invalid JSON chunk')
    document = json.loads(raw[20:20 + size], object_pairs_hook=unique_object)
    binary_size, kind = struct.unpack_from('<I4s', raw, 20 + size)
    require(kind == b'BIN\0' and binary_size % 4 == 0 and 28 + size + binary_size == len(raw),
            'Only one JSON and one BIN chunk are supported')
    binary = raw[28 + size:]
    require(isinstance(document, dict) and set(document) <= ROOT_KEYS and finite_tree(document),
            'Unsupported or nonfinite GLB metadata')
    require(set(document.get('extensionsUsed', [])) <= EXTENSIONS and
            set(document.get('extensionsRequired', [])) <= EXTENSIONS, 'Unsupported GLB extension')
    buffers = document['buffers']
    require(len(buffers) == 1 and set(buffers[0]) == {'byteLength'}, 'External or multiple buffers rejected')
    logical_size = buffers[0]['byteLength']
    require(integer(logical_size, 1) and 0 <= len(binary) - logical_size <= 3 and
            not any(binary[logical_size:]), 'Invalid BIN length or padding')
    views, accessors = document['bufferViews'], document['accessors']
    intervals = []
    for view in views:
        require(set(view) <= {'buffer', 'byteOffset', 'byteLength', 'target'} and
                integer(view.get('buffer')) and view['buffer'] == 0,
                'Unsupported buffer view, interleaving or external buffer')
        start, count = view.get('byteOffset', 0), view['byteLength']
        require(integer(start) and integer(count, 1) and start % 4 == 0 and start + count <= logical_size,
                'Buffer view range is invalid')
        require('target' not in view or (integer(view['target']) and view['target'] in (34962, 34963)),
                'Unsupported buffer view target')
        intervals.append((start, start + count))
    end = 0
    for start, stop in sorted(intervals):
        require(start >= end and start - end <= 3 and not any(binary[end:start]),
                'Overlapping or unclaimed BIN bytes rejected')
        end = stop
    require(0 <= logical_size - end <= 3 and not any(binary[end:logical_size]), 'Unclaimed trailing BIN bytes')
    arrays, formats = [], []
    used_views = set()
    for accessor in accessors:
        require(set(accessor) <= {'bufferView', 'byteOffset', 'componentType', 'count', 'type', 'min', 'max'},
                'Unsupported accessor, sparse data or normalization')
        index, count = accessor['bufferView'], accessor['count']
        require(integer(index) and index < len(views) and index not in used_views and integer(count, 1),
                'Accessor view alias or count is invalid')
        used_views.add(index)
        view = views[index]
        component, shape = accessor['componentType'], accessor['type']
        require(integer(component) and ((component == 5126 and shape in ('VEC2', 'VEC3')) or
                (component in (5123, 5125) and shape == 'SCALAR')), 'Unsupported accessor format')
        code = {5126: 'f', 5123: 'H', 5125: 'I'}[component]
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}[shape]
        fmt = '<' + code * width
        require(integer(accessor.get('byteOffset', 0)) and accessor.get('byteOffset', 0) == 0 and
                view['byteLength'] == count * struct.calcsize(fmt),
                'Accessor must exactly cover its unstrided view')
        start = view.get('byteOffset', 0)
        values = list(struct.iter_unpack(fmt, binary[start:start + view['byteLength']]))
        require(all(math.isfinite(v) for row in values for v in row), 'Nonfinite corner attribute')
        for bound, fn in [('min', min), ('max', max)]:
            if bound in accessor:
                require(semantic_equal(accessor[bound], [fn(row[i] for row in values) for i in range(width)]),
                        'Accessor bounds do not describe actual values')
        arrays.append(values)
        formats.append((component, shape, view.get('target')))
    images = []
    for image in document.get('images', []):
        require(set(image) <= {'name', 'mimeType', 'bufferView'} and image.get('mimeType') == 'image/png',
                'Only embedded PNG images are supported')
        index = image['bufferView']
        require(integer(index) and index < len(views) and index not in used_views and
                'target' not in views[index], 'Image view alias or target is invalid')
        used_views.add(index)
        view = views[index]
        start = view.get('byteOffset', 0)
        images.append(binary[start:start + view['byteLength']])
    require(used_views == set(range(len(views))), 'Unreferenced buffer views rejected')
    primitives, used_accessors = [], set()
    for mesh in document['meshes']:
        require(set(mesh) <= {'name', 'primitives', 'extras'} and mesh['primitives'], 'Unsupported mesh payload')
        for primitive in mesh['primitives']:
            require(set(primitive) <= {'attributes', 'indices', 'material', 'mode'} and
                    integer(primitive.get('mode', 4)) and primitive.get('mode', 4) == 4,
                    'Only uncompressed rigid triangles are supported')
            attrs = primitive['attributes']
            require({'POSITION', 'NORMAL', 'TEXCOORD_0'} <= set(attrs) <= set(ATTRIBUTES),
                    'Unsupported or missing primitive attribute')
            references = [primitive['indices'], *attrs.values()]
            # glTF may reuse the same read-only accessor, including identical
            # UV0/UV1 arrays. Every use still receives its semantic/type/count
            # and ordered-corner checks. Different accessor/view overlaps were
            # already rejected above.
            require(all(integer(i) and i < len(arrays) for i in references), 'Invalid primitive accessor')
            used_accessors.update(references)
            indices = arrays[primitive['indices']]
            require(formats[primitive['indices']][0] in (5123, 5125) and
                    formats[primitive['indices']][1:] == ('SCALAR', 34963) and len(indices) % 3 == 0,
                    'Invalid triangle index accessor')
            count = len(arrays[attrs['POSITION']])
            require({'min', 'max'} <= set(accessors[attrs['POSITION']]), 'POSITION requires min and max bounds')
            restart = 65535 if formats[primitive['indices']][0] == 5123 else 4294967295
            require(all(i < restart for (i,) in indices), 'Primitive restart index is forbidden in glTF')
            require({i for (i,) in indices} == set(range(count)), 'Invalid indices or unreferenced vertices')
            for semantic, index in attrs.items():
                require(formats[index] == (5126, ATTRIBUTES[semantic], 34962) and len(arrays[index]) == count,
                        'Primitive attribute format or count differs')
            require(all(abs(math.sqrt(sum(v*v for v in normal)) - 1) <= LIMITS['normal_length_error']
                        for normal in arrays[attrs['NORMAL']]), 'Non-unit corner normal')
            primitives.append((mesh['name'], indices, {key: arrays[index] for key, index in attrs.items()}))
    require(used_accessors == set(range(len(arrays))), 'Unreferenced accessors rejected')
    metadata = copy.deepcopy(document)
    for key in ('accessors', 'bufferViews', 'buffers'):
        metadata.pop(key)
    for mesh in metadata['meshes']:
        for primitive in mesh['primitives']:
            primitive['attributes'] = sorted(primitive['attributes'])
            primitive.pop('indices')
    for image in metadata.get('images', []):
        image.pop('bufferView')
    return metadata, primitives, images


def compare(actual, reference):
    am, ap, ai = parse(actual)
    rm, rp, ri = parse(reference)
    require(semantic_equal(am, rm), 'Scene, material, semantic or primitive metadata changed')
    require(ai == ri, 'Embedded image bytes changed')
    result = {'primitives': len(ap), 'triangles': 0, 'corners': 0, 'attributes_checked': 0,
              'changed_position_corners': 0, 'changed_normal_corners': 0, 'changed_uv_corners': 0,
              'maximum_position_distance_m': 0.0, 'maximum_normal_angle_degrees': 0.0,
              'maximum_uv_component_error': 0.0, 'embedded_images': len(ai),
              'minimum_raw_triangle_area_m2': math.inf, 'minimum_reference_triangle_area_m2': math.inf,
              'triangle_area_threshold_m2': MINIMUM_TRIANGLE_AREA_M2, 'oriented_triangles_checked': 0}
    for (an, aidx, attrs), (rn, ridx, refs) in zip(ap, rp):
        require(an == rn and len(aidx) == len(ridx) and attrs.keys() == refs.keys(), 'Ordered triangle topology changed')
        result['triangles'] += len(aidx) // 3
        result['corners'] += len(aidx)
        for (a,), (r,) in zip(aidx, ridx):
            for semantic in attrs:
                x, y = attrs[semantic][a], refs[semantic][r]
                result['attributes_checked'] += 1
                if semantic == 'POSITION':
                    error = math.dist(x, y)
                    require(error <= LIMITS['position_distance_m'], 'Position exceeds corner bake tolerance')
                    result['maximum_position_distance_m'] = max(result['maximum_position_distance_m'], error)
                    result['changed_position_corners'] += x != y
                elif semantic == 'NORMAL':
                    length_product = math.sqrt(sum(v*v for v in x) * sum(v*v for v in y))
                    angle = math.degrees(math.acos(max(-1, min(1, sum(u*v for u, v in zip(x, y)) / length_product)))) if x != y else 0.0
                    require(angle <= LIMITS['normal_angle_degrees'], 'Normal exceeds corner bake tolerance')
                    result['maximum_normal_angle_degrees'] = max(result['maximum_normal_angle_degrees'], angle)
                    result['changed_normal_corners'] += x != y
                else:
                    error = max(abs(u-v) for u, v in zip(x, y))
                    require(error <= LIMITS['uv_component_error'], 'UV exceeds corner bake tolerance')
                    result['maximum_uv_component_error'] = max(result['maximum_uv_component_error'], error)
                    result['changed_uv_corners'] += x != y
        for offset in range(0, len(aidx), 3):
            ac = oriented_triangle(*(attrs['POSITION'][i] for (i,) in aidx[offset:offset+3]))
            rc = oriented_triangle(*(refs['POSITION'][i] for (i,) in ridx[offset:offset+3]))
            aa, ra = (math.sqrt(sum(v*v for v in cross)) * 0.5 for cross in (ac, rc))
            require(min(aa, ra) > MINIMUM_TRIANGLE_AREA_M2, 'Degenerate triangle before corner bake')
            require(sum(x*y for x, y in zip(ac, rc)) > 0, 'Triangle winding changed before corner bake')
            result['minimum_raw_triangle_area_m2'] = min(result['minimum_raw_triangle_area_m2'], aa)
            result['minimum_reference_triangle_area_m2'] = min(result['minimum_reference_triangle_area_m2'], ra)
            result['oriented_triangles_checked'] += 1
    return result


def create(source, glb, destination):
    source, glb, destination = map(Path, (source, glb, destination))
    require(not destination.exists(), 'Preserve existing corner bake; use a new path')
    raw = glb.read_bytes()
    compare(raw, raw)
    record = {'schema_version': 1, 'kind': 'cannonball-evaluated-corner-bake', 'limits': LIMITS,
              'source_sha256': digest(source.read_bytes()), 'source_bytes': source.stat().st_size,
              'reference_glb_sha256': digest(raw), 'reference_glb_bytes': len(raw),
              'reference_encoding': 'zlib-base64',
              'reference_payload': base64.b64encode(zlib.compress(raw, level=9)).decode('ascii')}
    destination.write_text(json.dumps(record, indent=2) + '\n', encoding='utf8', newline='\n')
    return record


def apply(source, glb, bake_path):
    source, glb, bake_path = map(Path, (source, glb, bake_path))
    lock_bytes = bake_path.read_bytes()
    require(len(lock_bytes) <= MAX_BYTES * 2, 'Unsupported corner bake file size')
    bake = json.loads(lock_bytes, object_pairs_hook=unique_object)
    require(set(bake) == {'schema_version', 'kind', 'limits', 'source_sha256', 'source_bytes',
                         'reference_glb_sha256', 'reference_glb_bytes', 'reference_encoding', 'reference_payload'} and
            type(bake['schema_version']) is int and bake['schema_version'] == 1 and
            bake['kind'] == 'cannonball-evaluated-corner-bake' and semantic_equal(bake['limits'], LIMITS) and
            bake['reference_encoding'] == 'zlib-base64' and integer(bake['source_bytes'], 1),
            'Unsupported corner bake contract')
    require(digest(source.read_bytes()) == bake['source_sha256'] and source.stat().st_size == bake['source_bytes'],
            'Corner bake source is stale; explicitly prepare a new bake after source edits')
    require(integer(bake['reference_glb_bytes'], 28) and bake['reference_glb_bytes'] <= MAX_BYTES,
            'Unsupported reference payload size')
    packed = base64.b64decode(bake['reference_payload'], validate=True)
    require(len(packed) <= MAX_BYTES, 'Unsupported compressed payload size')
    decompressor = zlib.decompressobj()
    reference = decompressor.decompress(packed, MAX_BYTES + 1)
    require(decompressor.eof and not decompressor.unused_data and not decompressor.unconsumed_tail and
            len(reference) == bake['reference_glb_bytes'] and digest(reference) == bake['reference_glb_sha256'],
            'Corrupt or oversized canonical reference payload')
    raw = glb.read_bytes()
    measurements = compare(raw, reference)
    # Every validation precedes the write; rejected candidates remain unchanged.
    glb.write_bytes(reference)
    return {'bake_sha256': digest(lock_bytes), 'source_sha256': bake['source_sha256'],
            'raw_glb_sha256': digest(raw), 'glb_sha256': digest(reference), 'limits': LIMITS,
            'measurements': measurements,
            'scope': 'Ordered rigid triangle corners, every UV channel, scene/material metadata and exact embedded images; canonical encoding only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'glb', 'inventory', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_bytes(), object_pairs_hook=unique_object)
    require(inventory['status'] == 'passed' and inventory['source']['sha256'] == digest(args.source.read_bytes()) and
            inventory['glb']['sha256'] == digest(args.glb.read_bytes()),
            'Corner bake creation requires the matching successful source/export inventory')
    record = create(args.source, args.glb, args.output)
    print(json.dumps({'status': 'explicit_corner_bake_created', 'path': str(args.output),
                      'source_sha256': record['source_sha256'], 'reference_glb_sha256': record['reference_glb_sha256']}))


if __name__ == '__main__':
    main()
