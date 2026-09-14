"""Fixed-camera real Blender captures, with explicit source/config hashes."""

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


def lighting(scene, name):
    """Original physical light rigs; no external HDR or composited corrections."""
    factors={'neutral':1.,'daylight':.10,'overcast':.38,'dusk':.035,'night':.012}
    for obj in bpy.data.objects:
        if obj.type=='LIGHT' and obj.name.startswith('Preview_'):
            obj.data.energy*=factors[name]
            if name=='overcast':obj.data.size*=1.8;obj.data.size_y*=2
    background=scene.world.node_tree.nodes['Background']
    colors={'neutral':(.18,.18,.18,1),'daylight':(.52,.65,.85,1),'overcast':(.56,.59,.64,1),'dusk':(.10,.14,.27,1),'night':(.035,.05,.09,1)}
    strengths={'neutral':.35,'daylight':.55,'overcast':.75,'dusk':.14,'night':.035}
    background.inputs[0].default_value=colors[name]
    background.inputs[1].default_value=strengths[name]
    if name in ('daylight','dusk'):
        data=bpy.data.lights.new('QA_Sun','SUN');data.energy=2.5 if name=='daylight' else .45
        data.angle=math.radians(3 if name=='daylight' else 5)
        data.color=(1,.93,.82) if name=='daylight' else (1,.48,.22)
        lamp=bpy.data.objects.new(data.name,data);scene.collection.objects.link(lamp)
        lamp.rotation_euler=(math.radians(30 if name=='daylight' else 79),math.radians(-18),math.radians(-45))


def configure_engine(scene, args):
    devices=[]
    if args.engine=='cycles':
        scene.render.engine='CYCLES';scene.cycles.samples=args.samples
        scene.cycles.use_denoising=True
        scene.cycles.denoising_use_gpu=bool(getattr(args,'gpu_denoising',False))
        scene.cycles.use_adaptive_sampling=True
        scene.cycles.adaptive_threshold=.015
        scene.cycles.max_bounces=10;scene.cycles.transmission_bounces=8
        scene.cycles.transparent_max_bounces=8
        scene.render.use_persistent_data=True
        scene.cycles.device=args.device
        if args.device=='GPU':
            prefs=bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type='OPTIX';prefs.get_devices()
            for device in prefs.devices:
                device.use=device.type=='OPTIX'
                devices.append({'name':device.name,'type':device.type,'enabled':bool(device.use)})
            if not any(d['enabled'] for d in devices):raise RuntimeError('Requested OptiX GPU is unavailable')
    else:
        scene.render.engine='BLENDER_EEVEE';scene.eevee.taa_render_samples=args.samples
    return devices


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--views',default='front3q,rear3q,left,front,rear,top')
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--height',type=int,default=720)
    parser.add_argument('--clay',action='store_true')
    parser.add_argument('--technical-overlays',action='store_true',help='Explicit temporary x-ray geometry, actual anchors/proxies and meter rulers')
    parser.add_argument('--control',action='append',default=[],help='Source RigControls property=value')
    parser.add_argument('--samples',type=int,default=64)
    parser.add_argument('--engine',choices=('cycles','eevee'),default='cycles')
    parser.add_argument('--device',choices=('GPU','CPU'),default='GPU')
    parser.add_argument('--gpu-denoising',action='store_true',help='Use the same OpenImageDenoise algorithm on the configured GPU')
    parser.add_argument('--lighting',choices=('neutral','daylight','overcast','dusk','night'),default='neutral')
    parser.add_argument('--inspection-fill-watts',type=float,default=0,help='Explicit camera-mounted area work light for enclosed cabin inspection')
    parser.add_argument('--sequence',choices=('none','hold','turntable','interior','openings','all-openings'),default='none')
    parser.add_argument('--frames',type=int,default=360)
    parser.add_argument('--fps',type=int,default=30)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.technical_overlays and (args.clay or args.sequence!='none'):
        raise ValueError('Technical overlays require a separate non-clay still set')
    if args.gpu_denoising and (args.engine!='cycles' or args.device!='GPU'):
        raise ValueError('GPU denoising requires Cycles GPU rendering')
    args.output.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene;camera=scene.camera
    if args.width<64 or args.height<64 or args.samples<1 or args.frames<2 or args.fps<1 or not 0<=args.inspection_fill_watts<=1000:raise ValueError('Invalid capture configuration')
    devices=configure_engine(scene,args);lighting(scene,args.lighting)
    pose={}
    controls=bpy.data.objects['RigControls']
    for item in args.control:
        key,value=item.split('=',1)
        if key not in controls:raise ValueError('Unknown source control '+key)
        controls[key]=float(value);pose[key]=float(value)
    controls.update_tag();scene.frame_set(1);bpy.context.view_layer.update()
    scene.render.resolution_x=args.width;scene.render.resolution_y=args.height
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    under_data=bpy.data.lights.new('QA_UndersideFill','AREA');under_data.energy=450;under_data.shape='DISK';under_data.size=5
    under_lamp=bpy.data.objects.new(under_data.name,under_data);scene.collection.objects.link(under_lamp)
    under_lamp.location=(0,0,-4);under_lamp.rotation_euler=(0,math.pi,0)
    fill_data=None
    if args.inspection_fill_watts:
        fill_data=bpy.data.lights.new('QA_CabinInspectionWorkLight','AREA')
        fill_data.energy=args.inspection_fill_watts;fill_data.shape='DISK';fill_data.size=.35
        fill=bpy.data.objects.new(fill_data.name,fill_data);scene.collection.objects.link(fill)
        fill.parent=camera;fill.location=(0,0,.025)
    for obj in list(bpy.data.collections['Asset'].all_objects):
        if obj.type=='MESH':obj.hide_render=obj.name.startswith(('LOD1_','LOD2_','CollisionProxy'))
    if args.clay:
        mat=bpy.data.materials.new('QA_NeutralClay');mat.diffuse_color=(.42,.42,.42,1);mat.use_nodes=True
        mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.42
        scene.view_layers[0].material_override=mat
    views={'front3q':((-6,7,3.4),(0,0,.75),False),'rear3q':((6,-7,3.2),(0,0,.75),False),
           'left':((-8,0,.78),(0,0,.78),True),'right':((8,0,.78),(0,0,.78),True),
           'front':((0,8,.77),(0,0,.77),True),'rear':((0,-8,.77),(0,0,.77),True),
           'top':((0,0,9),(0,0,0),True),'under':((0,0,-8),(0,0,0),True),
           'cockpit':((-.43,-.39,1.21),(-.32,.70,.95),False),
           'rear_cabin':((.0,-1.2,1.22),(0,.38,.72),False),
           'rear_seats':((0,-.52,1.24),(0,-1.22,.674),False),
           'rear_door':((-2.8,-1.32,.90),(-1.15,-1.12,.82),False),
           'front_door':((-3.4,-.25,.90),(-1.15,.10,.82),False),
           'roof_front':((.15,-.40,1.03),(0,.005,1.34),False),
           'roof_rear':((0,-.75,1.04),(-.45,-.72,1.35),False),
           'engine':((-.95,2.55,2.75),(0,1.38,.58),False),
           'trunk':((.90,-3.6,2.55),(0,-1.97,.58),False),
           'front_lamps':((-2.05,4.4,1.35),(-.34,2.25,.69),False),
           'rear_lamps':((2.0,-4.4,1.35),(.3,-2.42,.65),False),
           'wheel':((-2.4,1.5,.65),(-.84,1.46,.40),False),
           'pedals':((-.56,.20,.52),(-.375,.6635,.349),False),
           'paint':((-2.5,3.2,1.9),(-.48,1.73,.84),False),
           'panel_gap':((-1.52,.05,1.18),(-.89,-.62,.94),False),
           'glass_seal':((-1.3,.3,1.64),(-.63,.02,1.28),False),
           'upholstery':((.02,.30,1.12),(-.40,-.28,.62),False),
           'hood_hinge':((-1.3,1.60,1.69),(-.437,.8,.99),False),
           'trunk_hinge':((-.95,-2.90,1.68),(-.455,-2.0,.99),False),
           'wiper_oblique':((1.10,1.50,1.95),(0,.47,1.16),False),
           'wiper_overview':((-1.04,2.052,1.91),(-.20,.54,1.13),False),
           'front_belt_left':((.10,-1.07,1.03),(-.715,-.622,.80),False),
           'wipers':((-.9,1.8,1.78),(-.20,.54,1.13),False)}
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from endurance_sedan import review_overlays
    swatch_objects={}
    swatch_views=[name for name in args.views.split(',') if name.startswith('swatch_')]
    if swatch_views:
        if len(swatch_views)!=len(args.views.split(',')) or args.sequence!='none' or args.clay or args.technical_overlays:
            raise ValueError('Material swatches require a separate normal-material still set')
        swatch_objects=review_overlays.swatches()
        bpy.data.collections['Asset'].hide_render=True
        for name in review_overlays.SWATCHES:
            views['swatch_'+name]=((1.8,2.6,1.3),(0,0,.45),False)
        views['swatch_board']=((0,8,1.52),(0,0,1.52),True)
    overlay=review_overlays.technical(scene) if args.technical_overlays else None
    config={'source_sha256':hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),'renderer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'blender':bpy.app.version_string,'build_hash':bpy.app.build_hash.decode(),'engine':scene.render.engine,'device':args.device,'devices':devices,'size':[args.width,args.height],'samples':args.samples,'denoising':bool(scene.cycles.use_denoising) if args.engine=='cycles' else False,'view_transform':scene.view_settings.view_transform,'look':scene.view_settings.look,'exposure':scene.view_settings.exposure,'clay':args.clay,'source_controls':pose,'lighting':args.lighting,'sequence':args.sequence,'frame_count':args.frames if args.sequence!='none' else len(args.views.split(',')),'fps':args.fps,'views':args.views,'ray_bounces':10 if args.engine=='cycles' else None,'source_timeline_fps':scene.render.fps}
    config['inspection_fill_watts']=args.inspection_fill_watts
    config['inspection_fill_disk_diameter_m']={'default':.35,'pedals':.14,'rear_seats':.20,'front_belt_left':.20}
    config['inspection_fill_camera_local_m']=[0,0,.025]
    config['denoiser']=scene.cycles.denoiser if args.engine=='cycles' else None
    config['denoising_use_gpu']=bool(scene.cycles.denoising_use_gpu) if args.engine=='cycles' else None
    config['denoising_prefilter']=scene.cycles.denoising_prefilter if args.engine=='cycles' else None
    config['technical_overlay']=overlay
    config['review_overlay_tool_sha256']=hashlib.sha256(Path(review_overlays.__file__).read_bytes()).hexdigest()
    config['review_geometry_tool_sha256']=hashlib.sha256(Path(review_overlays.geo.__file__).read_bytes()).hexdigest()
    config['material_swatches']={name:{'source_material':obj.data.materials[0].name,'sphere_diameter_m':.86,'uv_meters_per_repeat':.25} for name,obj in swatch_objects.items()}
    if swatch_objects:
        config['swatch_board_source_centers_m']={name:[(i%3-1)*1.05,0,.46+(2-i//3)*1.05] for i,name in enumerate(swatch_objects)}
    config_hash=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    manifest_path=args.output/'manifest.json'
    manifest={'source':bpy.data.filepath,'configuration':config,'configuration_sha256':config_hash,'status':'running','frames':[]}
    existing={}
    if manifest_path.exists():
        old=json.loads(manifest_path.read_text())
        if old.get('configuration_sha256')!=config_hash:raise ValueError('Output folder contains a different capture configuration')
        existing={f['view']:f for f in old['frames']}
    jobs=[]
    if args.sequence=='none':
        jobs=[(name,*views[name],1,{},name) for name in args.views.split(',')]
    elif args.sequence=='hold':
        if ',' in args.views:raise ValueError('A continuous hold requires exactly one named view')
        location,target,ortho=views[args.views]
        for i in range(args.frames):
            jobs.append((f'{i+1:06d}',location,target,ortho,1+i*scene.render.fps/args.fps,{},args.views))
    elif args.sequence=='turntable':
        for i in range(args.frames):
            angle=math.atan2(7,-6)-math.tau*i/args.frames
            jobs.append((f'{i+1:06d}',(8.6*math.cos(angle),8.6*math.sin(angle),3.0),(0,0,.76),False,1+i*scene.render.fps/args.fps,{},'front3q'))
    elif args.sequence=='interior':
        shots=('cockpit','pedals','upholstery','rear_seats','rear_cabin')
        for i in range(args.frames):
            index=min(len(shots)-1,i*len(shots)//args.frames)
            location,target,ortho=views[shots[index]]
            phase=(i*len(shots)/args.frames)%1
            location=(location[0]+.035*math.sin((phase-.5)*math.pi),location[1],location[2])
            jobs.append((f'{i+1:06d}',location,target,ortho,1+i*scene.render.fps/args.fps,{},shots[index]))
    else:
        actions=(('Door_FL_open','front_door'),('Door_FR_open','front_door'),('Door_RL_open','rear_door'),('Door_RR_open','rear_door'),('Hood_Hinge_open','engine'),('Trunk_Hinge_open','trunk'))
        for i in range(args.frames):
            index=min(5,i*6//args.frames);control,view=actions[index]
            first=math.ceil(index*args.frames/6);last=math.ceil((index+1)*args.frames/6)-1
            phase=(i-first)/max(1,last-first)
            if args.sequence=='all-openings':
                view='front3q';phase=i/(args.frames-1)
            value=math.sin(phase*math.pi)**2
            location,target,ortho=views[view]
            if args.sequence=='openings' and control in ('Door_FR_open','Door_RR_open'):
                location=(-location[0],location[1],location[2]);target=(-target[0],target[1],target[2])
            jobs.append((f'{i+1:06d}',location,target,ortho,1+i*scene.render.fps/args.fps,{a[0]:value if args.sequence=='all-openings' or a[0]==control else 0. for a in actions},view))
    def save_manifest():
        temporary=manifest_path.with_suffix('.partial.json');temporary.write_text(json.dumps(manifest,indent=2)+'\n',newline='\n');temporary.replace(manifest_path)
    for name,location,target,ortho,source_frame,animated,capture_view in jobs:
        if (args.output/'STOP').exists():manifest['status']='stopped';save_manifest();raise RuntimeError('Capture STOP requested')
        for key,value in animated.items():
            if key not in controls:raise ValueError('Unknown animated source control '+key)
            controls[key]=value
        controls.update_tag();scene.frame_set(int(source_frame),subframe=source_frame%1);bpy.context.view_layer.update()
        for index,(swatch,obj) in enumerate(swatch_objects.items()):
            obj.hide_render=capture_view not in ('swatch_'+swatch,'swatch_board')
            obj.location=((index%3-1)*1.05,0,(2-index//3)*1.05) if capture_view=='swatch_board' else (0,0,0)
        camera.location=location;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.type='ORTHO' if ortho else 'PERSP'
        # Technical rulers span +/-3 m; include their ends and ticks with a
        # margin in the shorter dimension of the 16:9 top/underside frames.
        camera.data.ortho_scale=(11.6 if args.technical_overlays else 9.8) if capture_view in ('top','under') else 6.6
        camera.data.lens=22 if capture_view=='front_belt_left' else 35 if capture_view=='wiper_overview' else 18 if capture_view=='rear_seats' else 24 if capture_view in ('cockpit','rear_cabin','rear_seats','pedals','upholstery','front_door','rear_door','roof_front','roof_rear') else 55
        bpy.data.objects['PreviewFloor'].hide_render=capture_view in ('under','swatch_board') or args.technical_overlays
        under_lamp.hide_render=capture_view!='under'
        if fill_data is not None:
            fill_data.size=.14 if capture_view=='pedals' else .20 if capture_view in ('rear_seats','front_belt_left') else .35
        path=(args.output/(name+'.png')).resolve()
        previous=existing.get(name)
        if previous and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==previous['sha256']:
            manifest['frames'].append({**previous,'existing':True});save_manifest();continue
        temporary=path.with_name(path.stem+'.partial.png');scene.render.filepath=str(temporary)
        before=time.perf_counter();bpy.ops.render.render(write_still=True);elapsed=time.perf_counter()-before
        temporary.replace(path)
        manifest['frames'].append({'view':name,'capture_view':capture_view,'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'seconds':elapsed,'cold':len(manifest['frames'])==0,'camera_location':list(location),'camera_target':list(target),'orthographic':ortho,'lens_mm':camera.data.lens,'ortho_scale_m':camera.data.ortho_scale,'source_frame':source_frame,'time_seconds':(source_frame-1)/scene.render.fps,'animated_controls':animated,'inspection_fill_watts':args.inspection_fill_watts,'inspection_fill_disk_diameter_m':float(fill_data.size) if fill_data is not None else None})
        save_manifest()
        print('SEDAN_RENDER_FRAME '+json.dumps(manifest['frames'][-1]))
    manifest['status']='completed';save_manifest()


if __name__=='__main__':main()
