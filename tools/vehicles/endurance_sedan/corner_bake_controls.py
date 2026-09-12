"""Exercise actual platform-export acceptance and corruption rejection."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corner_bake


def parts(raw):
    count = struct.unpack_from('<I', raw, 12)[0]
    return json.loads(raw[20:20+count]), bytearray(raw[28+count:])


def encode(document, binary):
    encoded = json.dumps(document, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += bytes(-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28+len(encoded)+len(binary)) +
            struct.pack('<I4s', len(encoded), b'JSON') + encoded +
            struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def offset(document, index):
    accessor = document['accessors'][index]
    return document['bufferViews'][accessor['bufferView']].get('byteOffset', 0) + accessor.get('byteOffset', 0)


def update_bounds(document, binary, index):
    accessor = document['accessors'][index]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}[accessor['type']]
    code = {5126: 'f', 5123: 'H', 5125: 'I'}[accessor['componentType']]
    fmt = '<' + code * width
    start = offset(document, index)
    values = [struct.unpack_from(fmt, binary, start + i*struct.calcsize(fmt)) for i in range(accessor['count'])]
    for key, fn in [('min', min), ('max', max)]:
        if key in accessor:
            accessor[key] = [fn(row[i] for row in values) for i in range(width)]


def attribute_mutation(semantic, amount=None, flip=False, nonfinite=False, separate=False):
    def mutate(document, binary):
        primitive = next(p for m in document['meshes'] for p in m['primitives'] if semantic in p['attributes'])
        index = primitive['attributes'][semantic]
        other_channels = [key for mesh in document['meshes'] for item in mesh['primitives']
                          for key, value in item['attributes'].items() if value == index and key != semantic]
        if separate and other_channels:
            accessor = copy.deepcopy(document['accessors'][index])
            view = copy.deepcopy(document['bufferViews'][accessor['bufferView']])
            old = offset(document, index)
            payload = binary[old:old + view['byteLength']]
            binary.extend(bytes(-len(binary) % 4))
            view['byteOffset'] = len(binary)
            binary.extend(payload)
            document['buffers'][0]['byteLength'] = len(binary)
            accessor['bufferView'] = len(document['bufferViews'])
            document['bufferViews'].append(view)
            index = len(document['accessors'])
            document['accessors'].append(accessor)
            primitive['attributes'][semantic] = index
        start = offset(document, index)
        if flip:
            value = struct.unpack_from('<3f', binary, start)
            struct.pack_into('<3f', binary, start, *(-v for v in value))
        else:
            value = float('nan') if nonfinite else struct.unpack_from('<f', binary, start)[0] + amount
            struct.pack_into('<f', binary, start, value)
        if not nonfinite:
            update_bounds(document, binary, index)
    return mutate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'raw-glb', 'bake', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    args.output.mkdir(parents=True, exist_ok=False)
    lock = json.loads(args.bake.read_bytes())
    raw = args.raw_glb.read_bytes()
    reference_path = args.output / 'accepted-reference.glb'
    reference_path.write_bytes(raw)
    corner_bake.apply(args.source, reference_path, args.bake)
    reference = reference_path.read_bytes()
    report = {'task_id': 'P1-018', 'utc': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'inputs': {str(p): corner_bake.digest(p.read_bytes()) for p in [args.source, args.raw_glb, args.bake, Path(__file__)]},
              'cases': [], 'human_approval_reference': None}

    def check(name, expected=None, mutate=None, lock_change=None, source_change=False,
              candidate=reference, raw_change=None):
        folder = args.output / name
        folder.mkdir()
        if mutate:
            doc, binary = parts(candidate)
            mutate(doc, binary)
            candidate = encode(doc, binary)
        if raw_change:
            candidate = raw_change(candidate)
        target = folder / 'candidate.glb'
        target.write_bytes(candidate)
        changed_lock = copy.deepcopy(lock)
        if lock_change:
            lock_change(changed_lock)
        bake = folder / 'bake.json'
        bake.write_text(json.dumps(changed_lock)+'\n', encoding='utf8', newline='\n')
        source = args.source
        if source_change:
            source = folder / 'changed-source.blend'
            source.write_bytes(args.source.read_bytes() + b'changed')
        failure = None
        result = None
        try:
            result = corner_bake.apply(source, target, bake)
        except (ValueError, KeyError, struct.error) as error:
            failure = str(error)
        if expected is None:
            assert failure is None and target.read_bytes() == reference, (name, failure)
        else:
            assert failure and expected in failure, (name, failure, expected)
            assert target.read_bytes() == candidate, 'Rejected candidate was changed'
        report['cases'].append({'name': name, 'status': 'passed', 'expected_rejection': expected,
                                'observed_rejection': failure, 'result': result,
                                'input_sha256': corner_bake.digest(candidate),
                                'output_sha256': corner_bake.digest(target.read_bytes())})

    try:
        check('actual-platform-export', candidate=raw)
        check('canonical-encoding')
        check('bounded-uv-rounding', mutate=attribute_mutation('TEXCOORD_0', 0.000001))
        check('stale-source', 'source is stale', source_change=True)
        check('changed-limits', 'Unsupported corner bake contract',
              lock_change=lambda d: d['limits'].__setitem__('position_distance_m', 0.01))
        check('corrupt-reference-hash', 'Corrupt or oversized canonical',
              lock_change=lambda d: d.__setitem__('reference_glb_sha256', '0'*64))
        check('changed-position', 'Position exceeds', mutate=attribute_mutation('POSITION', 0.001))
        check('reversed-normal', 'Normal exceeds', mutate=attribute_mutation('NORMAL', flip=True))
        check('nonfinite-position', 'Nonfinite corner', mutate=attribute_mutation('POSITION', nonfinite=True))
        check('changed-uv0', 'UV exceeds', mutate=attribute_mutation('TEXCOORD_0', 0.001))
        check('changed-uv1-only', 'UV exceeds', mutate=attribute_mutation('TEXCOORD_1', 0.001, separate=True))
        check('changed-semantic', 'metadata changed', mutate=lambda d, b: d['nodes'][0].__setitem__('name', 'Wrong_Root'))
        def image_change(d, b):
            view = d['bufferViews'][d['images'][0]['bufferView']]
            start = view.get('byteOffset', 0)
            b[start+16] ^= 1
        check('changed-image', 'Embedded image bytes', mutate=image_change)
        def winding(d, b):
            index = d['meshes'][0]['primitives'][0]['indices']
            code = 'H' if d['accessors'][index]['componentType'] == 5123 else 'I'
            start = offset(d, index)
            a, c, e = struct.unpack_from('<'+code*3, b, start)
            struct.pack_into('<'+code*3, b, start, c, a, e)
        check('changed-winding', 'Position exceeds', mutate=winding)
        check('external-buffer', 'External or multiple', mutate=lambda d, b: d['buffers'][0].__setitem__('uri', 'foreign.bin'))
        check('sparse-accessor', 'Unsupported accessor', mutate=lambda d, b: d['accessors'][0].__setitem__('sparse', {}))
        check('interleaved-view', 'Unsupported buffer view', mutate=lambda d, b: d['bufferViews'][0].__setitem__('byteStride', 12))
        check('overlapping-view', 'Overlapping or unclaimed', mutate=lambda d, b: d['bufferViews'][1].__setitem__('byteOffset', 0))
        check('new-attribute', 'Unsupported or missing primitive attribute',
              mutate=lambda d, b: d['meshes'][0]['primitives'][0]['attributes'].__setitem__('COLOR_0', 0))
        check('morph-target', 'Only uncompressed rigid triangles', mutate=lambda d, b: d['meshes'][0]['primitives'][0].__setitem__('targets', []))
        check('new-extension', 'Unsupported GLB extension', mutate=lambda d, b: d.setdefault('extensionsUsed', []).append('KHR_draco_mesh_compression'))
        check('wrong-bounds', 'Accessor bounds', mutate=lambda d, b: next(a for a in d['accessors'] if 'min' in a).__setitem__('min', [999,999,999]))
        check('missing-position-bounds', 'POSITION requires min and max',
              mutate=lambda d, b: d['accessors'][d['meshes'][0]['primitives'][0]['attributes']['POSITION']].pop('min'))
        check('boolean-buffer-index', 'Unsupported buffer view', mutate=lambda d, b: d['bufferViews'][0].__setitem__('buffer', False))
        check('decimal-component-profile', 'Unsupported accessor format', mutate=lambda d, b: d['accessors'][0].__setitem__('componentType', float(d['accessors'][0]['componentType'])))
        check('boolean-scene-metadata', 'metadata changed', mutate=lambda d, b: d.__setitem__('scene', False))
        check('numeric-material-boolean', 'metadata changed', mutate=lambda d, b: d['materials'][0].__setitem__('doubleSided', 1))
        check('numeric-extra-boolean', 'metadata changed', mutate=lambda d, b: next(n for n in d['nodes'] if n.get('extras', {}).get('collision_only') is True)['extras'].__setitem__('collision_only', 1))
        def duplicate(raw_bytes):
            size = struct.unpack_from('<I', raw_bytes, 12)[0]
            encoded = raw_bytes[20:20+size].rstrip()[:-1] + b',"scene":0}'
            encoded += b' ' * (-len(encoded) % 4)
            tail = raw_bytes[20+size:]
            return (struct.pack('<4sII', b'glTF', 2, 20+len(encoded)+len(tail)) +
                    struct.pack('<I4s', len(encoded), b'JSON') + encoded + tail)
        check('duplicate-json-key', 'Duplicate JSON key', raw_change=duplicate)
        # A tiny edge makes winding/collapse changes fit inside position and UV
        # tolerances. Exercise those independently of the large-asset fixture.
        for name, collapse in [('thin-triangle-collapse', True), ('thin-triangle-winding', False)]:
            folder = args.output / name
            folder.mkdir()
            positions = [(0., 0., 0.), (1e-7, 0., 0.), (0., 1., 0.)]
            document = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
                        'nodes': [{'name': 'Synthetic', 'mesh': 0}], 'meshes': [{'name': 'Synthetic', 'primitives': [
                            {'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2}, 'indices': 3}]}],
                        'accessors': [], 'bufferViews': [], 'buffers': []}
            binary = bytearray()
            for values, shape, component, code, target in [(positions, 'VEC3', 5126, '3f', 34962),
                    ([(0., 0., 1.)]*3, 'VEC3', 5126, '3f', 34962),
                    ([(0., 0.), (1e-7, 0.), (0., 1.)], 'VEC2', 5126, '2f', 34962),
                    ([(0,), (1,), (2,)], 'SCALAR', 5123, 'H', 34963)]:
                binary.extend(bytes(-len(binary) % 4))
                payload = b''.join(struct.pack('<'+code, *v) for v in values)
                index = len(document['accessors'])
                document['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(payload), 'target': target})
                document['accessors'].append({'bufferView': index, 'componentType': component, 'count': 3, 'type': shape})
                binary.extend(payload)
            document['buffers'] = [{'byteLength': len(binary)}]
            document['accessors'][0].update(min=[0., 0., 0.], max=[struct.unpack('<f', struct.pack('<f', 1e-7))[0], 1., 0.])
            valid = folder / 'valid.glb'
            valid.write_bytes(encode(document, binary))
            bake = folder / 'bake.json'
            corner_bake.create(args.source, valid, bake)
            if collapse:
                struct.pack_into('<3f', binary, offset(document, 0)+12, 0., 0., 0.)
                update_bounds(document, binary, 0)
            else:
                struct.pack_into('<3H', binary, offset(document, 3), 1, 0, 2)
            candidate = encode(document, binary)
            target = folder / 'candidate.glb'
            target.write_bytes(candidate)
            expected = 'Degenerate triangle' if collapse else 'Triangle winding changed'
            try:
                corner_bake.apply(args.source, target, bake)
                raise AssertionError('Invalid thin triangle was accepted')
            except ValueError as error:
                assert expected in str(error), str(error)
                assert target.read_bytes() == candidate
                report['cases'].append({'name': name, 'status': 'passed', 'expected_rejection': expected,
                    'observed_rejection': str(error), 'input_sha256': corner_bake.digest(candidate),
                    'output_sha256': corner_bake.digest(target.read_bytes())})
        for path, value in report['inputs'].items():
            assert corner_bake.digest(Path(path).read_bytes()) == value
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', failure=str(error))
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8', newline='\n')
    print('CANNONBALL_CORNER_BAKE_CONTROLS_OK cases=' + str(len(report['cases'])))


if __name__ == '__main__':
    main()
