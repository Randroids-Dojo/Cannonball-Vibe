"""Exercise actual export UV-bake acceptance and corruption rejection."""
import argparse
import base64
import copy
import datetime
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uv_bake


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'raw-glb', 'bake', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.output.exists(): raise ValueError('Use a fresh UV control report directory')
    args.output.mkdir(parents=True)
    raw = args.raw_glb.read_bytes(); bake = json.loads(args.bake.read_bytes())
    spans, _, _ = uv_bake.layout(raw)
    json_length = struct.unpack_from('<I', raw, 12)[0]
    document = json.loads(raw[20:20+json_length]); bin_start = 28+json_length
    position_index = document['meshes'][0]['primitives'][0]['attributes']['POSITION']
    position = document['accessors'][position_index]
    position_offset = bin_start + document['bufferViews'][position['bufferView']].get('byteOffset', 0) + position.get('byteOffset', 0)
    first = spans[0]['offset']
    report = {'task_id': 'P1-018', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'running', 'inputs': {str(p): uv_bake.digest(p.read_bytes()) for p in (args.source,args.raw_glb,args.bake,Path(__file__))},
              'cases': [], 'human_approval_reference': None}
    def check(name, diagnostic=None, raw_mutation=None, bake_mutation=None, source_mutation=False):
        folder = args.output/name; folder.mkdir()
        value = bytearray(raw)
        if raw_mutation: raw_mutation(value)
        artifact = folder/'candidate.glb'; artifact.write_bytes(value)
        lock = copy.deepcopy(bake)
        if bake_mutation: bake_mutation(lock)
        lock_path = folder/'bake.json'; lock_path.write_text(json.dumps(lock)+'\n',encoding='utf-8',newline='\n')
        source = args.source
        if source_mutation:
            source = folder/'changed-source.blend'; source.write_bytes(args.source.read_bytes()+b'changed source')
        before = uv_bake.digest(artifact.read_bytes()); failure = None; result = None
        try: result = uv_bake.apply(source,artifact,lock_path)
        except ValueError as error: failure = str(error)
        if diagnostic is None:
            assert failure is None and uv_bake.digest(artifact.read_bytes()) == bake['reference_glb_sha256'],(name,failure)
        else:
            assert failure is not None and diagnostic in failure,(name,failure,diagnostic)
            assert uv_bake.digest(artifact.read_bytes()) == before,'Rejected artifact was modified'
        report['cases'].append({'name':name,'status':'passed','expected_rejection':diagnostic,'observed_rejection':failure,
                                'input_glb_sha256':before,'output_glb_sha256':uv_bake.digest(artifact.read_bytes()),'result':result})
    try:
        check('actual-export-accepted')
        check('source-mismatch','source is stale',source_mutation=True)
        check('position-byte-change','any non-UV bytes',raw_mutation=lambda data:data.__setitem__(position_offset,data[position_offset]^1))
        check('excessive-uv-change','exceeds the locked',raw_mutation=lambda data:struct.pack_into('<f',data,first,struct.unpack_from('<f',data,first)[0]+0.001))
        check('nonfinite-uv','nonfinite coordinates',raw_mutation=lambda data:struct.pack_into('<f',data,first,float('nan')))
        def corrupt_payload(lock):
            payload=bytearray(base64.b64decode(lock['accessors'][0]['base64']));payload[0]^=1
            lock['accessors'][0]['base64']=base64.b64encode(payload).decode('ascii')
        check('corrupt-payload','payload hash',bake_mutation=corrupt_payload)
        check('corrupt-reference-hash','complete reviewed reference',bake_mutation=lambda lock:lock.__setitem__('reference_glb_sha256','0'*64))
        check('changed-tolerance','Unsupported evaluated UV bake',bake_mutation=lambda lock:lock.__setitem__('maximum_uv_error',0.001))
        check('changed-layout','accessor layout mismatch',bake_mutation=lambda lock:lock['accessors'][0].__setitem__('offset',first+4))
        def nonfinite_reference(lock):
            row=lock['accessors'][0];payload=bytearray(base64.b64decode(row['base64']))
            struct.pack_into('<f',payload,0,float('inf'));row['base64']=base64.b64encode(payload).decode('ascii');row['sha256']=uv_bake.digest(payload)
        check('nonfinite-reference','nonfinite reference',bake_mutation=nonfinite_reference)
        # Exercise real accessor aliasing before the source/whole-file hash checks.
        overlap = copy.deepcopy(document)
        overlap['accessors'][spans[0]['accessor']]['bufferView'] = position['bufferView']
        overlap['accessors'][spans[0]['accessor']]['byteOffset'] = position.get('byteOffset',0)
        encoded=json.dumps(overlap,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
        binary=raw[bin_start:]
        aliased=struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(binary))+struct.pack('<I4s',len(encoded),b'JSON')+encoded+struct.pack('<I4s',len(binary),b'BIN\0')+binary
        try: uv_bake.layout(aliased)
        except ValueError as error:
            assert 'overlap' in str(error) or 'exceeds' in str(error),str(error)
            report['cases'].append({'name':'overlapping-payload','status':'passed','observed_rejection':str(error),'input_sha256':uv_bake.digest(aliased)})
        else: raise AssertionError('Overlapping UV/position bytes accepted')
        (args.output/'overlapping-payload.glb').write_bytes(aliased)
        for name,digest in report['inputs'].items(): assert uv_bake.digest(Path(name).read_bytes())==digest
        report['status']='passed'
    except BaseException as error:
        report.update(status='failed',failure=str(error));raise
    finally:
        report['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('CANNONBALL_UV_BAKE_CONTROLS_OK cases='+str(len(report['cases'])))


if __name__ == '__main__': main()
