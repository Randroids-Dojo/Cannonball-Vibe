"""Source-bound evaluated UV bake for the sedan's pinned GLB exporter.

Only small float variation in existing UV coordinates may be replaced. Every
other byte must match the reviewed reference. This never rounds coordinates,
changes topology, substitutes a mesh, or automatically updates a stale bake.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import struct

MAXIMUM_UV_ERROR = 0.00001


def digest(data):
    return hashlib.sha256(data).hexdigest()


def layout(raw):
    if len(raw) < 28 or struct.unpack_from('<4sII', raw) != (b'glTF', 2, len(raw)):
        raise ValueError('UV bake requires a valid GLB 2.0 header')
    chunks = {}; offset = 12
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError('Truncated GLB chunk header')
        size, kind = struct.unpack_from('<I4s', raw, offset); offset += 8
        if kind in chunks or size % 4 or offset + size > len(raw):
            raise ValueError('Invalid or repeated GLB chunk')
        chunks[kind] = (offset, raw[offset:offset+size]); offset += size
    if set(chunks) != {b'JSON', b'BIN\0'}:
        raise ValueError('UV bake requires one JSON and one embedded BIN chunk')
    document = json.loads(chunks[b'JSON'][1])
    buffers = document.get('buffers', [])
    if len(buffers) != 1 or 'uri' in buffers[0] or buffers[0]['byteLength'] > len(chunks[b'BIN\0'][1]):
        raise ValueError('UV bake requires one portable embedded buffer')
    accessors = document.get('accessors', [])
    views = document.get('bufferViews', [])
    uv_indices = set(); other_indices = set()
    for mesh in document.get('meshes', []):
        for primitive in mesh['primitives']:
            if 'indices' in primitive: other_indices.add(primitive['indices'])
            for name, index in primitive['attributes'].items():
                (uv_indices if name.startswith('TEXCOORD_') else other_indices).add(index)
    if not uv_indices or uv_indices & other_indices:
        raise ValueError('UV accessors are absent or also used by non-UV geometry')
    widths = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
    sizes = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}

    def span(index):
        item = accessors[index]
        if 'sparse' in item or 'bufferView' not in item:
            raise ValueError('Sparse or implicit accessors are outside the UV bake profile')
        view = views[item['bufferView']]
        width = widths[item['type']] * sizes[item['componentType']]
        stride = view.get('byteStride', width)
        start = view.get('byteOffset', 0) + item.get('byteOffset', 0)
        length = max(0, item['count'] - 1) * stride + width
        if view.get('buffer', 0) != 0 or item['count'] < 1 or stride < width or start < 0 or \
                start + length > view.get('byteOffset', 0) + view['byteLength'] or \
                start + length > buffers[0]['byteLength']:
            raise ValueError('Accessor exceeds its declared embedded buffer view')
        return chunks[b'BIN\0'][0] + start, length, stride

    spans = []
    for index in sorted(uv_indices):
        item = accessors[index]; start, length, stride = span(index)
        if item['componentType'] != 5126 or item['type'] != 'VEC2' or item.get('normalized', False) or stride != 8:
            raise ValueError('UV bake supports non-interleaved FLOAT VEC2 coordinates only')
        if any(not math.isfinite(value[0]) for value in struct.iter_unpack('<f', raw[start:start+length])):
            raise ValueError('UV bake rejects nonfinite coordinates')
        spans.append({'accessor': index, 'offset': start, 'bytes': length})
    non_uv_spans = [span(index)[:2] for index in range(len(accessors)) if index not in uv_indices]
    for image in document.get('images', []):
        if 'uri' in image: raise ValueError('UV bake rejects external images')
        view = views[image['bufferView']]
        if view.get('buffer', 0) != 0: raise ValueError('Image uses an external buffer')
        non_uv_spans.append((chunks[b'BIN\0'][0] + view.get('byteOffset', 0), view['byteLength']))
    previous_end = -1
    for row in sorted(spans, key=lambda value: value['offset']):
        start, end = row['offset'], row['offset'] + row['bytes']
        if start < previous_end or any(start < other + count and other < end for other, count in non_uv_spans):
            raise ValueError('UV payload overlaps another accessor or image')
        previous_end = end
    masked = bytearray(raw)
    for row in spans: masked[row['offset']:row['offset']+row['bytes']] = bytes(row['bytes'])
    return spans, digest(chunks[b'JSON'][1]), digest(masked)


def create(source, glb, destination):
    source, glb, destination = Path(source), Path(glb), Path(destination)
    if destination.exists(): raise ValueError('Use a new UV bake path; an existing bake is never overwritten')
    raw = glb.read_bytes(); spans, json_hash, other_hash = layout(raw)
    record = {'schema_version': 1, 'kind': 'cannonball-evaluated-uv-bake',
              'source_sha256': digest(source.read_bytes()), 'source_bytes': source.stat().st_size,
              'reference_glb_sha256': digest(raw), 'reference_glb_bytes': len(raw),
              'json_chunk_sha256': json_hash, 'all_non_uv_bytes_sha256': other_hash,
              'maximum_uv_error': MAXIMUM_UV_ERROR, 'accessors': []}
    for row in spans:
        payload = raw[row['offset']:row['offset']+row['bytes']]
        record['accessors'].append({**row, 'sha256': digest(payload), 'base64': base64.b64encode(payload).decode('ascii')})
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8', newline='\n')
    return record


def apply(source, glb, bake_path):
    source, glb, bake_path = Path(source), Path(glb), Path(bake_path)
    bake_bytes = bake_path.read_bytes(); bake = json.loads(bake_bytes)
    if bake.get('schema_version') != 1 or bake.get('kind') != 'cannonball-evaluated-uv-bake' or \
            bake.get('maximum_uv_error') != MAXIMUM_UV_ERROR:
        raise ValueError('Unsupported evaluated UV bake contract')
    if digest(source.read_bytes()) != bake['source_sha256'] or source.stat().st_size != bake['source_bytes']:
        raise ValueError('UV bake source is stale; explicitly prepare a new bake after source edits')
    raw = glb.read_bytes(); spans, json_hash, other_hash = layout(raw)
    if len(raw) != bake['reference_glb_bytes'] or json_hash != bake['json_chunk_sha256'] or other_hash != bake['all_non_uv_bytes_sha256']:
        raise ValueError('UV bake rejects changed GLB layout or any non-UV bytes')
    if spans != [{key: row[key] for key in ('accessor', 'offset', 'bytes')} for row in bake['accessors']]:
        raise ValueError('UV bake accessor layout mismatch')
    corrected = bytearray(raw); maximum = 0.0; changed = 0; components = 0
    for row in bake['accessors']:
        payload = base64.b64decode(row['base64'], validate=True)
        if len(payload) != row['bytes'] or digest(payload) != row['sha256']:
            raise ValueError('UV bake payload hash or length mismatch')
        original = raw[row['offset']:row['offset']+row['bytes']]
        for actual, expected in zip(struct.iter_unpack('<f', original), struct.iter_unpack('<f', payload)):
            if not math.isfinite(expected[0]): raise ValueError('UV bake contains nonfinite reference coordinates')
            error = abs(actual[0]-expected[0]); maximum = max(maximum, error); components += 1
            changed += actual[0] != expected[0]
            if error > MAXIMUM_UV_ERROR:
                raise ValueError('UV coordinate exceeds the locked 0.00001 bake tolerance')
        corrected[row['offset']:row['offset']+row['bytes']] = payload
    if digest(corrected) != bake['reference_glb_sha256']:
        raise ValueError('UV bake does not reconstruct the complete reviewed reference GLB')
    # All checks precede the write. An invalid export remains available intact.
    glb.write_bytes(corrected)
    return {'bake_sha256': digest(bake_bytes), 'source_sha256': bake['source_sha256'],
            'raw_glb_sha256': digest(raw), 'glb_sha256': digest(corrected),
            'all_non_uv_bytes_sha256': other_hash, 'uv_accessor_count': len(spans),
            'float_components_checked': components, 'changed_float_components': changed,
            'maximum_measured_uv_error': maximum, 'maximum_allowed_uv_error': MAXIMUM_UV_ERROR,
            'scope': 'Original reviewed UV float bytes only; all other GLB bytes must match exactly'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--glb', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_bytes())
    if inventory['status'] != 'passed' or inventory['source']['sha256'] != digest(args.source.read_bytes()) or \
            inventory['glb']['sha256'] != digest(args.glb.read_bytes()):
        raise ValueError('UV bake creation requires the matching successful source/export inventory')
    result = create(args.source, args.glb, args.output)
    print(json.dumps({'status': 'explicit_uv_bake_created', 'path': str(args.output),
                      'source_sha256': result['source_sha256'], 'reference_glb_sha256': result['reference_glb_sha256']}))


if __name__ == '__main__': main()
