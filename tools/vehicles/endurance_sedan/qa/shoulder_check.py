"""Read-only saved-source correspondence; native geometry plus historical normals."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy

from shoulder_checkpoint import digest,native_state,plain
from shoulder_report import validate_data,validate_report,read_json,artifact,require


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def binding(path):
    path=Path(path).resolve(strict=True)
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}


def write(path,value):
    path=Path(path)
    require(not path.exists(),'Retain old output: '+str(path))
    raw=(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw)


class HistoricalMesh:
    def __init__(self,mesh,normals):self.mesh=mesh;self.corner_normals=[type('Normal',(),{'vector':n})() for n in normals]
    def __getattr__(self,name):return getattr(self.mesh,name)


class HistoricalObject:
    def __init__(self,obj,normals):self.obj=obj;self.data=HistoricalMesh(obj.data,normals)
    def __getattr__(self,name):return getattr(self.obj,name)


def geometry_proof(obj,checkpoint,reference,profile,helper,ownership):
    # No codec write or scene mutation: the proxy substitutes only the bound
    # historical corner readback. Actual vertices/triangles/face normals are
    # read from the saved source. Host validator independently enumerates fans.
    before=checkpoint['core']['before']
    plan=helper.prepare(HistoricalObject(obj,before['normals']),reference,profile,ownership)
    return plain({key:plan[key] for key in ('candidate_faces','owned_faces','unowned_faces','excluded_generated_strength_faces','ambiguous_corners','details')})


def mesh_payload(obj,source_sha,helper,geometry):
    state=native_state(obj,helper)
    # Bind the independently extracted full-source payload and compare its
    # actual nominal bumper positions, triangles, material slots and frame.
    require(geometry['source_sha256']==source_sha,'Extracted geometry source differs')
    row=geometry['meshes'][obj.name]
    require(row['vertices']==[list(obj.matrix_world@v.co) for v in obj.data.vertices],'Extracted bumper vertices differ')
    require(row['triangles']==[list(t.vertices) for t in obj.data.loop_triangles],'Extracted bumper triangles differ')
    require(row['rest_world_matrix']==[list(r) for r in obj.matrix_world],'Extracted bumper frame differs')
    require(row['material_names']==state['physical']['materials'],'Extracted bumper materials differ')
    return {'schema':'shoulder-native-payload.v1','source_sha256':source_sha,'native':state,'evaluated_bumper':row}


def check(source,packet_path,profile_path,builder_path,geometry_path,output,helper_path,ownership_path,construction_root=None):
    require(bpy.app.version==(5,1,2) and bpy.app.build_hash.decode()=='ec6e62d40fa9','Wrong native Blender')
    source=Path(source);packet=read_json(Path(packet_path));profile=read_json(Path(profile_path))
    helper=load(helper_path,'_shoulder_field');helper.validate_profile(profile)
    ownership=load(ownership_path,'_shoulder_ownership')
    builder=load(builder_path,'_shoulder_builder')
    paths=[source,packet_path,profile_path,builder_path,geometry_path,helper_path,ownership_path,
           Path(__file__),Path(__file__).with_name('shoulder_checkpoint.py'),Path(__file__).with_name('shoulder_report.py')]
    initial=[binding(p) for p in paths]
    constructor=packet['core']['checkpoint']['core']['construction_inputs']
    resolved_constructor=[]
    for row in constructor:
        path=artifact({key:row[key] for key in ('path','sha256','bytes')},construction_root)
        resolved_constructor.append({**row,'path':str(path)})
    source_sha=initial[0]['sha256'];out=Path(output);out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=True)
    reference=builder.rebuild_reference(profile,helper,resolved_constructor)
    require(reference==packet['core']['checkpoint']['core']['reference'],'Fresh original construction field differs')
    write(out/'fresh-reference.json',reference)
    bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=True)
    obj=bpy.data.objects[profile['semantic']]
    geometry=read_json(Path(geometry_path))
    payload=mesh_payload(obj,source_sha,helper,geometry)
    write(out/'native-payload.json.gz',payload)
    proof=geometry_proof(obj,packet['core']['checkpoint'],reference,profile,helper,ownership)
    report={'schema':'shoulder-source-correspondence.v1','status':'passed','source_sha256':source_sha,
            'profile_sha256':digest(profile),'constructor_inputs_sha256':digest(constructor),
            'native':{'version':bpy.app.version_string,'build':bpy.app.build_hash.decode()},
            'bindings':{'source':binding(source),'payload':binding(out/'native-payload.json.gz'),
                        'packet':binding(packet_path),'fresh_reference':binding(out/'fresh-reference.json'),
                        'profile':binding(profile_path),'geometry':binding(geometry_path),
                        'tools':[binding(p) for p in paths[3:] if Path(p)!=Path(geometry_path)]},
            'geometry_proof':proof,'metrics':{},'source_saved':False,'human_approval_reference':None}
    report['metrics']=validate_data(report,packet,payload,reference,profile)
    validate_report(report,source_sha,expected_profile_sha256=binding(profile_path)['sha256'],expected_constructor_inputs_sha256=digest(constructor),construction_root=construction_root)
    for row in initial:artifact(row)
    for row in constructor:artifact({key:row[key] for key in ('path','sha256','bytes')},construction_root)
    write(out/'report.json',report)
    return report


def main():
    parser=argparse.ArgumentParser()
    for key in ('source','packet','profile','builder','geometry','output','helper','ownership'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--construction-root',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    try:
        report=check(args.source,args.packet,args.profile,args.builder,args.geometry,args.output,args.helper,args.ownership,args.construction_root)
        print(json.dumps({'status':'passed','metrics':report['metrics']}),flush=True)
    except Exception as error:
        path=args.output/'failure.json'
        if not path.exists():write(path,{'status':'failed','error':str(error),'traceback':traceback.format_exc(),'source_saved':False})
        raise


if __name__=='__main__':main()
