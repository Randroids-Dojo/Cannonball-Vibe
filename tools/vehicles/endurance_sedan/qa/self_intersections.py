"""Check every original LOD0 authored mesh for strict self intersections."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sys
import time

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import self_geometry


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def strict_json(raw):
    def constant(value):raise ValueError('Nonfinite JSON value: '+value)
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    return json.loads(raw,parse_constant=constant,object_pairs_hook=pairs)


def validate_row(name,row):
    if not isinstance(row,dict) or row.get('name')!=name:
        raise ValueError('Mesh name/key mismatch: '+name)
    vertices,triangles=row.get('vertices'),row.get('triangles')
    if not isinstance(vertices,list) or len(vertices)<3:
        raise ValueError('Nonempty vertex array required: '+name)
    if not isinstance(triangles,list) or not triangles:
        raise ValueError('Nonempty triangle array required: '+name)
    for point in vertices:
        if (not isinstance(point,list) or len(point)!=3
                or any(type(value) not in (int,float) or not math.isfinite(value) for value in point)):
            raise ValueError('Invalid finite3D vertex: '+name)
    for face in triangles:
        if (not isinstance(face,list) or len(face)!=3 or len(set(face))!=3
                or any(type(index) is not int or not 0<=index<len(vertices) for index in face)):
            raise ValueError('Invalid triangle indices: '+name)
        a,b,c=[vertices[index] for index in face]
        normal=self_geometry.cross(self_geometry.sub(b,a),self_geometry.sub(c,a))
        area=math.hypot(*normal)/2
        if not math.isfinite(area) or area<=1e-12:
            raise ValueError('Degenerate or below-threshold triangle: '+name)


def inspect(payload,source_hash,includes):
    if not re.fullmatch('[0-9a-f]{64}',source_hash):
        raise ValueError('Actual source SHA256 is invalid')
    if not isinstance(payload,dict) or payload.get('source_sha256')!=source_hash:
        raise ValueError('Extracted geometry is not bound to the actual supplied source')
    meshes=payload.get('meshes')
    if not isinstance(meshes,dict) or not meshes:
        raise ValueError('Nonempty mesh inventory required')
    selected=[];excluded=[]
    for name,row in sorted(meshes.items()):
        if not isinstance(name,str) or not isinstance(row,dict):
            raise ValueError('Invalid named mesh entry')
        properties=row.get('properties',{})
        if not isinstance(properties,dict):raise ValueError('Invalid mesh properties')
        if not name.startswith('LOD0_') or properties.get('source_preview_only') is True:
            excluded.append(name);continue
        if includes and not any(name.startswith(prefix) for prefix in includes):continue
        validate_row(name,row)
        selected.append((name,row))
    if not selected:raise ValueError('No eligible original LOD0 meshes selected')
    for prefix in includes:
        if not prefix or not any(name.startswith(prefix) for name,_ in selected):
            raise ValueError('Requested mesh prefix did not match: '+prefix)
    results=[]
    for name,row in selected:
        result=self_geometry.scan(row);results.append(result)
        if result['status']!='passed' or len(results)%100==0:
            print(json.dumps({'mesh':name,'checked':len(results),'status':result['status'],
                              'crossings':len(result['bad_pairs'])}),flush=True)
    return {'status':'passed' if all(row['status']=='passed' for row in results) else 'failed',
            'rows':results,'selected_meshes':[name for name,_ in selected],
            'excluded_preview_or_other_lod':excluded,
            'mesh_count':len(results),'triangle_count':sum(row['triangles'] for row in results),
            'aabb_candidates':sum(row['aabb_candidates'] for row in results),
            'strict_crossing_pairs':sum(len(row['bad_pairs']) for row in results),
            'unresolved':[]}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--geometry',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--include',action='append',default=[])
    args=parser.parse_args(argv)
    if args.output.exists():parser.error('Choose a fresh output path')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    record={'task_id':'P1-018','utc':datetime.now(timezone.utc).isoformat(),
            'platform':platform.platform(),'blender_version':bpy.app.version_string,
            'blender_build':bpy.app.build_hash.decode(),'numpy':np.__version__,
            'status':'failed','source_sha256':None,'components_filter':args.include,
            'human_approval_reference':None,'scope':'Strict self-contact of each original LOD0 authored mesh. '
            'Indexed shared edges/vertices retain the1um guard; no nonindexed intersection exemption. '
            'Interassembly contacts, merged lower LODs, motion, export and human reviews are separate.'}
    inputs={}
    try:
        if (bpy.app.version_string,bpy.app.build_hash.decode())!=('5.1.2','ec6e62d40fa9'):
            raise ValueError('Pinned Blender identity required')
        if args.source.suffix.lower()!='.blend':raise ValueError('Editable .blend source required')
        paths=[args.source,args.geometry,Path(__file__),Path(self_geometry.__file__),
               Path(self_geometry.exact.__file__)]
        inputs={str(path.resolve()):sha(path) for path in paths}
        record['source_sha256']=sha(args.source)
        record['geometry_payload_sha256']=sha(args.geometry)
        with gzip.open(args.geometry,'rb') as stream:payload=strict_json(stream.read())
        record.update(inspect(payload,record['source_sha256'],args.include))
    except Exception as error:
        record.update(status='failed',failure=type(error).__name__+': '+str(error))
    finally:
        unchanged=all(Path(path).is_file() and sha(path)==digest for path,digest in inputs.items())
        record.update(inputs=[{'path':path,'sha256':digest} for path,digest in inputs.items()],
                      inputs_unchanged=unchanged,elapsed_seconds=time.monotonic()-started)
        if not unchanged:record.update(status='failed',failure='Locked input changed during self scan')
        args.output.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'status':record['status'],'meshes':record.get('mesh_count'),
                      'crossings':record.get('strict_crossing_pairs'),'output':str(args.output)}),flush=True)
    return 0 if record['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
