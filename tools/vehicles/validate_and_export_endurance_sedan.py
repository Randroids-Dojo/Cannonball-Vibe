"""Validate evaluated sedan geometry and export the pinned portable GLB."""

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from endurance_sedan.geometry import evaluated_counts  # noqa: E402
from glb_geometry import inspect as inspect_geometry  # noqa: E402
from validate_and_export_hero_gt import REQUIRED_NODES, export_glb, inspect_glb  # noqa: E402


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--inspect-only',action='store_true',help='Write evaluated diagnostics only; never export or claim optimized delivery')
    parser.add_argument('--unbatched-output',type=Path,help='Optional nonshipping GLB for independent component-to-batch correspondence QA')
    parser.add_argument('--prepare-uv-bake',type=Path,help='Explicitly create a NEW evaluated UV bake after source edits; never overwrites the current bake')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root=Path(__file__).resolve().parents[2]
    spec_path=root/'docs/vehicles/endurance-sedan/specification.json'
    contract_path=root/'tools/vehicles/vehicle_contract.json'
    spec=json.loads(spec_path.read_text());contract=json.loads(contract_path.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    if bpy.app.version!=(5,1,2) or bpy.app.build_hash.decode()!='ec6e62d40fa9':raise RuntimeError('Blender pin drift')
    scene=bpy.context.scene
    if scene.unit_settings.system!='METRIC' or scene.unit_settings.scale_length!=1:raise ValueError('Meter scale drift')
    asset=bpy.data.collections['Asset'];objects=list(asset.all_objects)
    source_only=[o for o in objects if o.get('source_preview_only',False)]
    for obj in source_only:bpy.data.objects.remove(obj,do_unlink=True)
    objects=list(asset.all_objects)
    names=[o.name for o in objects]
    required=REQUIRED_NODES|set(spec['hardpoints_source_m'])|{'RigControls'}
    if required-set(names):raise ValueError('Missing semantic nodes: '+str(sorted(required-set(names))))
    for name in required:
        if names.count(name)!=1:raise ValueError('Duplicate semantic '+name)
    controls=bpy.data.objects['RigControls']
    if any(isinstance(v,(float,int)) and v!=0 for k,v in controls.items() if k!='semantic_role' and not k.startswith('source_sim_')):
        raise ValueError('Source rig preview controls must be parked at zero for export')
    if bpy.data.libraries:raise ValueError('Linked libraries are not portable')
    for image in bpy.data.images:
        if image.source=='FILE' and image.packed_file is None:raise ValueError('Unpacked texture '+image.name)
    errors=[];counts={};materials={};bounds=[];meshes=[];graph=bpy.context.evaluated_depsgraph_get()
    if scene.get('surface_preview_only',False) and not args.inspect_only:errors.append('Surface preview contains no optimized shipping LODs')
    for obj in objects:
        if any(abs(v-1)>1e-6 for v in obj.scale):errors.append(obj.name+': nonunit scale')
        if obj.type!='MESH':continue
        info=evaluated_counts(obj);counts[obj.name]=info['triangles'];meshes.append({'name':obj.name,**info})
        if info['degenerate_faces']:errors.append(obj.name+': degenerate evaluated faces')
        if info['degenerate_triangles']:errors.append(obj.name+': degenerate evaluated loop triangles')
        if info['duplicate_faces']:errors.append(obj.name+': duplicate faces or collapsed closed component')
        if info['nonmanifold_edges']:errors.append(obj.name+': nonmanifold evaluated edges '+str(info['nonmanifold_edges']))
        if info['triangulated_duplicate_faces'] or info['triangulated_nonmanifold_edges']:
            errors.append(obj.name+': evaluated polygon tessellation is not a closed unique triangle mesh')
        if not info['uv_layers']:errors.append(obj.name+': missing UVs')
        for slot in obj.material_slots:
            if slot.material:materials[slot.material.name]=slot.material
        if obj.name.startswith('LOD0_'):
            ev=obj.evaluated_get(graph);data=ev.to_mesh()
            for vertex in data.vertices:
                p=obj.matrix_world@vertex.co
                if not all(math.isfinite(c) for c in p):errors.append(obj.name+': nonfinite vertex')
                bounds.append(tuple(p))
            ev.to_mesh_clear()
    actual_min=[min(p[i] for p in bounds) for i in range(3)];actual_max=[max(p[i] for p in bounds) for i in range(3)]
    lod_triangles={str(i):sum(c for n,c in counts.items() if n.startswith('LOD'+str(i)+'_')) for i in range(3)}
    if not args.inspect_only and not (lod_triangles['0']>lod_triangles['1']>lod_triangles['2']>0):errors.append('All three declared LODs must contain decreasing real geometry')
    collision=sum(c for n,c in counts.items() if n.startswith('CollisionProxy'))
    budgets=contract['budgets']
    for label,value,maximum in [('LOD0',lod_triangles['0'],budgets['triangles_lod0_max']),('all geometry',sum(counts.values()),budgets['triangles_total_max']),('materials',len(materials),budgets['materials_max']),('collision',collision,budgets['collision_triangles_max'])]:
        if value>maximum:errors.append(f'{label} budget {value} > {maximum}')
    hardpoints={}
    for name,expected in spec['hardpoints_source_m'].items():
        actual=bpy.data.objects[name].matrix_world.translation
        error=(actual-Vector(expected)).length
        hardpoints[name]={'source_m':list(actual),'error_m':error,'godot_m':[actual.x,actual.z,-actual.y]}
        if error>.0005:errors.append(name+': hardpoint drift '+str(error))
    textures={}
    for mat in materials.values():
        if not mat.node_tree:continue
        for node in mat.node_tree.nodes:
            if node.type=='TEX_IMAGE' and node.image:
                im=node.image;textures[im.name]={'width':im.size[0],'height':im.size[1],'color_space':im.colorspace_settings.name,'encoded_bytes':len(im.packed_file.data) if im.packed_file else 0,'rgba8_mip_residency_bytes':math.ceil(im.size[0]*im.size[1]*4*4/3)}
    texture_bytes=sum(x['encoded_bytes'] for x in textures.values())
    if len(textures)>budgets['textures_max'] or texture_bytes>budgets['texture_bytes_max']:errors.append('Texture budget exceeded')
    inventory={'schema_version':1,'asset_id':'endurance-sedan','stage':scene['production_stage'],'status':'failed' if errors else 'passed','errors':errors,'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),'required_nodes':sorted(required),'nodes':sorted(names),'meshes':meshes,'triangles':dict(sorted(counts.items())),'triangle_total':sum(counts.values()),'lod0_triangle_total':lod_triangles['0'],'lod_triangles':lod_triangles,'collision_triangle_total':collision,'materials':sorted(materials),'textures':textures,'texture_bytes_total':texture_bytes,'budgets':budgets,'bounds_source_m':{'minimum':actual_min,'maximum':actual_max,'size':[b-a for a,b in zip(actual_min,actual_max)]},'hardpoints':hardpoints,'source_axes':{'forward':'+Y','up':'+Z'},'godot_axes':{'forward':'-Z','up':'+Y'},'metric_scale':1,'identity_scales':True,'portable_paths':True,'source':{'path':str(args.source),'sha256':digest(args.source)},'specification_sha256':digest(spec_path),'budget_contract_sha256':digest(contract_path),'human_approval_reference':None}
    args.inventory.parent.mkdir(parents=True,exist_ok=True)
    inventory['status']='failed' if errors else ('passed' if args.inspect_only else 'export_pending')
    inventory['source_preview_only']=bool(scene.get('surface_preview_only',False))
    inventory['export_validator_sha256']=digest(Path(__file__))
    inventory['gltf_profile_sha256']=digest(root/'tools/assets/profiles/gltf2-endurance-sedan-v1.json')
    inventory['identity_transforms']=True
    inventory['validation_scope']='evaluated_source_only' if args.inspect_only else 'evaluated_and_exported_runtime_asset'
    args.inventory.write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n',newline='\n')
    if errors:raise ValueError('Evaluated asset failed: '+str(errors[:20]))
    if args.inspect_only:
        print('CANNONBALL_SEDAN_DIAGNOSTICS_ONLY '+json.dumps({'triangles':sum(counts.values()),'lods':lod_triangles,'source_preview_only':bool(scene.get('surface_preview_only',False))}))
        return
    inventory['bounds_meters']=[actual_max[0]-actual_min[0],actual_max[2]-actual_min[2],actual_max[1]-actual_min[1]]
    inventory['textures']=[{'name':name,**value} for name,value in sorted(textures.items())]
    profile=json.loads((root/'tools/assets/profiles/gltf2-endurance-sedan-v1.json').read_text())
    if args.unbatched_output:
        export_glb(args.unbatched_output.resolve(),profile)
        inventory['unbatched_qa_artifact']={'path':str(args.unbatched_output),'sha256':digest(args.unbatched_output),
                                          'scope':'Evaluated unbatched component comparison, not a shipping output'}
    from endurance_sedan.optimization import batch_export
    inventory['source_meshes']=inventory['meshes']
    inventory['source_triangles']=inventory['triangles']
    inventory['source_nodes']=inventory['nodes']
    inventory['export_batch_mapping']=batch_export(asset)
    batch_counts={obj.name:evaluated_counts(obj) for obj in asset.all_objects if obj.type=='MESH'}
    if sum(item['triangles'] for item in batch_counts.values())!=inventory['triangle_total']:
        inventory['status']='failed'
        inventory['errors'].append('Batching changed the evaluated triangle count')
        inventory['batch_counts_diagnostic']={name:info['triangles'] for name,info in sorted(batch_counts.items())}
        args.inventory.write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n',newline='\n')
        raise ValueError('Batching changed the evaluated triangle count')
    if any(info['nonmanifold_edges'] or info['degenerate_triangles'] or info['degenerate_faces'] or info['duplicate_faces'] or info['triangulated_duplicate_faces'] or info['triangulated_nonmanifold_edges'] for info in batch_counts.values()):
        inventory['status']='failed'
        inventory['errors'].append('Batching produced invalid evaluated geometry')
        inventory['invalid_batches']={name:info for name,info in batch_counts.items() if info['nonmanifold_edges'] or info['degenerate_triangles'] or info['degenerate_faces'] or info['duplicate_faces'] or info['triangulated_duplicate_faces'] or info['triangulated_nonmanifold_edges']}
        args.inventory.write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n',newline='\n')
        raise ValueError('Batching produced invalid evaluated geometry')
    inventory['meshes']=[{'name':name,**info} for name,info in sorted(batch_counts.items())]
    inventory['triangles']={name:info['triangles'] for name,info in sorted(batch_counts.items())}
    inventory['nodes']=sorted(obj.name for obj in asset.all_objects)
    inventory['runtime_mesh_count']=len(batch_counts)
    # Same pinned exporter options and axis conversion as the existing adapter.
    export_glb(args.output.resolve(),profile)
    # Blender's evaluated bevel UVs vary by a few float ULPs across processes.
    # Retain that raw export, then restore only the reviewed, source-bound UV
    # bytes. Every non-UV byte and the exact source must still match the bake.
    from endurance_sedan import uv_bake
    raw_export=args.output.with_name(args.output.stem+'.pre-uv-bake.glb')
    if raw_export.exists():raise ValueError('Use a fresh output directory; raw export evidence already exists')
    shutil.copyfile(args.output,raw_export)
    bake_path=args.prepare_uv_bake or root/profile['evaluated_uv_bake']['path']
    if profile['evaluated_uv_bake']['maximum_uv_error']!=uv_bake.MAXIMUM_UV_ERROR:
        raise ValueError('Evaluated UV bake tolerance differs from the pinned profile')
    if args.prepare_uv_bake:
        uv_bake.create(args.source,args.output,bake_path)
    inventory['evaluated_uv_bake']=uv_bake.apply(args.source,args.output,bake_path)
    inventory['evaluated_uv_bake']['path']=bake_path.relative_to(root).as_posix() if bake_path.is_absolute() and bake_path.is_relative_to(root) else bake_path.as_posix()
    inventory['evaluated_uv_bake']['raw_export_path']=raw_export.as_posix()
    inventory['glb']={'path':str(args.output),'sha256':digest(args.output),**inspect_glb(args.output)}
    inventory['glb_geometry']=inspect_geometry(args.output)
    if inventory['glb_geometry']['status']!='passed':
        inventory['status']='failed'
        inventory['errors'].append('Actual exported triangle bytes failed geometry validation')
    inventory['export_options']=profile
    inventory['status']='failed' if inventory['errors'] else 'passed'
    args.inventory.write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n',newline='\n')
    if inventory['errors']:raise ValueError(inventory['errors'])
    print('CANNONBALL_SEDAN_EXPORT_OK '+json.dumps({'triangles':sum(counts.values()),'lods':lod_triangles,'bounds':inventory['bounds_source_m'],'sha256':inventory['glb']['sha256']}))


if __name__=='__main__':main()
