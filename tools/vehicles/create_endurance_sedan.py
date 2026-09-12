"""Build a fresh editable Meridian S8R source using pinned Blender 5.1.2.

Blender +Y is the nose, +Z is up, meters throughout. The existing Hero GT is
neither loaded nor altered. Preview controls are explicit source rig controls;
Godot uses the same semantic pivots driven by its authoritative runtime state.
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from endurance_sedan import geometry as geo, materials, model, finish_refinement  # noqa: E402


def arguments():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stage',choices=['blockout','production'],default='blockout')
    parser.add_argument('--surface-preview',action='store_true',help='Skip derived LODs during surface iteration; not a deliverable export')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def driver(obj, path, index, controls, prop, expression):
    curve=obj.driver_add(path,index)
    curve.driver.type='SCRIPTED'
    var=curve.driver.variables.new();var.name='value';var.type='SINGLE_PROP'
    var.targets[0].id=controls;var.targets[0].data_path='["'+prop+'"]'
    curve.driver.expression=expression


def control(controls,name,minimum=0,maximum=1,description='Source preview only'):
    controls[name]=0.0
    controls.id_properties_ui(name).update(min=minimum,max=maximum,description=description)


def build_semantics(collection,spec):
    root=geo.empty('AssetRoot',collection,asset_id='endurance-sedan',specification_version=spec.get('specification_revision',1))
    chassis=geo.empty('Chassis',collection,root)
    lods=[geo.empty('Visual_LOD'+str(i),collection,chassis,lod_index=i) for i in range(3)]
    pivots={}
    for name,position in spec['hardpoints_source_m'].items():
        if name.startswith('Wheel_'):
            continue
        pivots[name]=geo.empty(name,collection,root,position)
    for suffix in ('FL','FR','RL','RR'):
        suspension=pivots['Suspension_'+suffix]
        suspension['rest_length_m']=.16
        suspension['static_compression_m']=.075
        pivots['Wheel_'+suffix]=geo.empty('Wheel_'+suffix,collection,suspension,radius_m=.3433)
    for name in ('Body','Glass','Wheels','Interior','Lights'):
        geo.empty('MaterialGroup_'+name,collection,root)
    for name,position in [('Front',(0,2.2,.55)),('Rear',(0,-2.3,.55)),('Left',(-.94,0,.6)),('Right',(.94,0,.6)),('Roof',(0,-.4,1.44))]:
        geo.empty('Damage_'+name,collection,root,position)
    collision=geo.empty('CollisionProxy',collection,root,collision_policy='two setup-owned convex boxes')
    for box in spec['collision_boxes_godot_ground']:
        x,y,z=box['center'];sx,sy,sz=box['size']
        proxy=geo.box('CollisionProxy_'+box['name'],(x,-z,y),(sx,sz,sy),None,collection,collision,radius=0)
        proxy.hide_render=True;proxy.hide_set(True);proxy['collision_only']=True
    controls=geo.empty('RigControls',collection,root)
    controls['instructions']='Edit custom properties for source-only inspection; reset all to zero before export.'
    for name,m in spec['mechanisms'].items():
        pivot=pivots[name]
        pivot['mechanism']=json.dumps(m,sort_keys=True)
        if 'rest_rotation_x_deg' in m:pivot.rotation_euler.x=math.radians(m['rest_rotation_x_deg'])
        if name.startswith('Door_') or name in ('Hood_Hinge','Trunk_Hinge'):
            if name.startswith('Door_'):pivot['hardware_pin_heights_m']=m.get('hardware_pin_heights_m',[.42,.79])
            prop=name+'_open';control(controls,prop)
            driver(pivot,'rotation_euler',2 if name.startswith('Door_') else 0,controls,prop,'value*'+str(math.radians(m['open_deg'])))
    control(controls,'steering',-1,1,'Normalized source steering preview, +/-32 degrees')
    control(controls,'wheel_roll',-1000,1000,'Wheel roll radians')
    control(controls,'suspension',-.075,.085,'Travel from static in meters')
    for suffix in ('FL','FR','RL','RR'):
        suspension=pivots['Suspension_'+suffix]
        driver(suspension,'location',2,controls,'suspension','.3433+value')
        if suffix.startswith('F'):driver(suspension,'rotation_euler',2,controls,'steering','value*'+str(-math.radians(32)))
        driver(pivots['Wheel_'+suffix],'rotation_euler',0,controls,'wheel_roll','value')
    return root,lods,pivots,controls


def make_lods(collection,lods):
    from endurance_sedan.optimization import make_lods as build_distance_lods
    build_distance_lods(collection,lods)


def preview(collection):
    scene=bpy.context.scene
    floor=materials.principled('Preview_Floor',(.18,.18,.18),.82)
    geo.box('PreviewFloor',(0,0,-.035),(30,30,.06),floor,collection,radius=0)
    world=bpy.data.worlds.new('Neutral studio');world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.18,.18,.18,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.35
    scene.world=world
    for name,location,energy,size,scale in [
        ('Key',(-4,4,6),1500,5,(1,1,1)),('Fill',(5,1,4),1000,4,(1,1,1)),
        ('RearStrip',(-2,-5,4),1600,4,(1,1,1)),('TopStrip',(0,0,7),1200,5,(1,1,1))]:
        data=bpy.data.lights.new('Preview_'+name,'AREA');data.energy=energy;data.shape='RECTANGLE';data.size=size;data.size_y=2
        lamp=bpy.data.objects.new(data.name,data);collection.objects.link(lamp);lamp.location=location
        lamp.rotation_euler=(Vector((0,0,.65))-lamp.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('PreviewCamera');data.lens=55
    camera=bpy.data.objects.new('PreviewCamera',data);collection.objects.link(camera)
    camera.location=(-6,7,3.4);camera.rotation_euler=(Vector((0,0,.72))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera=camera
    scene.render.engine='BLENDER_EEVEE';scene.eevee.taa_render_samples=64
    scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    scene.view_settings.view_transform='AgX'
    scene.view_settings.look='AgX - Medium High Contrast'


def main():
    args=arguments();root=Path(__file__).resolve().parents[2]
    spec=json.loads((root/'docs/vehicles/endurance-sedan/specification.json').read_text())
    if bpy.app.version!=(5,1,2) or bpy.app.build_hash.decode()!='ec6e62d40fa9':raise RuntimeError('Pinned Blender identity mismatch')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    print('SEDAN_OWNED_SCENE '+json.dumps({'pid':os.getpid(),'file':bpy.data.filepath,'version':bpy.app.version_string,'stage':args.stage}))
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    scene['asset_id']='endurance-sedan';scene['production_stage']=args.stage;scene['specification']=json.dumps(spec,sort_keys=True)
    asset=bpy.data.collections.new('Asset');scene.collection.children.link(asset)
    studio=bpy.data.collections.new('Preview');scene.collection.children.link(studio)
    root_obj,lods,pivots,controls=build_semantics(asset,spec)
    mats=materials.build()
    if args.stage=='production':
        checkpoint=json.loads((root/'docs/vehicles/endurance-sedan/blockout-integration.json').read_text())
        if checkpoint['status']!='passed' or len(checkpoint['variants'])!=3:
            raise RuntimeError('Production surfaces require the recorded three-variant blockout proof')
        model.build_production(asset,lods[0],mats,pivots,controls,spec)
        finish_refinement.apply()
    else:
        model.build_blockout(asset,lods[0],mats,pivots,spec)
    bpy.context.view_layer.update()
    print('SEDAN_STAGE model complete',flush=True)
    try:
        for obj in list(asset.objects):
            if obj.type=='MESH':geo.repair_triangulation(obj)
    except ValueError:
        failed=args.output.resolve().with_suffix('.failed.blend')
        failed.parent.mkdir(parents=True,exist_ok=True)
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.wm.save_as_mainfile(filepath=str(failed))
        raise
    print('SEDAN_STAGE evaluated LOD0 repair complete',flush=True)
    scene['surface_preview_only']=args.surface_preview
    if not args.surface_preview:
        make_lods(asset,lods)
        for obj in list(asset.objects):
            if obj.type=='MESH':geo.repair_triangulation(obj)
    print('SEDAN_STAGE LOD construction complete',flush=True)
    preview(studio)
    scene.render.fps=60;scene.frame_end=600
    if args.stage=='production':
        from endurance_sedan.mechanisms import preview_illumination
        preview_illumination(studio,pivots,controls)
    bpy.context.preferences.filepaths.save_version=0
    args.output=args.output.resolve();args.output.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))
    print('CANNONBALL_SEDAN_SOURCE_OK '+json.dumps({'path':str(args.output),'objects':len(asset.objects),'stage':args.stage}))


if __name__=='__main__':
    try:
        main()
    except Exception as failure:
        if bpy.context.scene.get('asset_id')=='endurance-sedan':
            failed=arguments().output.resolve().with_suffix('.failed.blend')
            failed.parent.mkdir(parents=True,exist_ok=True)
            bpy.context.scene['construction_status']='failed'
            bpy.context.scene['construction_failure']=str(failure)
            bpy.context.preferences.filepaths.save_version=0
            bpy.ops.wm.save_as_mainfile(filepath=str(failed))
        raise
