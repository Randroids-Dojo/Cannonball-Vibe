"""Bind continuous rigid-rotation analysis to the actual saved Blender drivers."""
import argparse
import ast
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);assert not a.output.exists()
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest();before=sha(a.source)
bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()),load_ui=False,use_scripts=True)
scene=bpy.context.scene;spec=json.loads(scene['specification']);controls=bpy.data.objects['RigControls']
keys=[k for k in controls.keys() if k.endswith('_open')];assert len(keys)==6
for k in keys:controls[k]=0.
controls.update_tag(refresh={'OBJECT'});scene.frame_set(1);bpy.context.view_layer.update()
rows=[]
for key in keys:
    name=key.removesuffix('_open');obj=bpy.data.objects[name];rest=obj.matrix_world.copy()
    assert len(obj.constraints)==0 and obj.rotation_mode=='XYZ'
    assert len(obj.animation_data.drivers)==1
    curve=obj.animation_data.drivers[0];driver=curve.driver
    assert curve.data_path=='rotation_euler' and curve.array_index==(2 if name.startswith('Door_') else 0)
    assert not curve.modifiers and not curve.mute and driver.is_valid and driver.type=='SCRIPTED'
    expression=ast.parse(driver.expression,mode='eval').body
    assert isinstance(expression,ast.BinOp) and isinstance(expression.op,ast.Mult)
    assert isinstance(expression.left,ast.Name) and expression.left.id=='value'
    factor=ast.literal_eval(expression.right);expected=math.radians(spec['mechanisms'][name]['open_deg'])
    assert abs(factor-expected)<1e-14
    assert len(driver.variables)==1
    variable=driver.variables[0];assert variable.name=='value' and variable.type=='SINGLE_PROP'
    assert len(variable.targets)==1 and variable.targets[0].id==controls and variable.targets[0].data_path=='["'+key+'"]'
    assert all(abs(rest[i][j]-(1. if i==j else 0.))<1e-12 for i in range(3) for j in range(3)), 'Opening rest axes must be source axes.'
    axis=Vector(spec['mechanisms'][name]['axis_source']).normalized();pivot=rest.translation
    descendants=[]
    for child in obj.children_recursive:
        assert not child.constraints,child.name
        assert not (child.animation_data and child.animation_data.drivers),child.name
        if child.type=='MESH':
            for modifier in child.modifiers:
                assert modifier.type in ('BEVEL','WEIGHTED_NORMAL','NORMAL_EDIT','SOLIDIFY','TRIANGULATE','DECIMATE','WELD'), (child.name,modifier.type)
        descendants.append(child.name)
    checks=[]
    for fraction in (0.,.001,.123456789,.5,.731,.999,1.):
        controls[key]=fraction;controls.update_tag(refresh={'OBJECT'});bpy.context.view_layer.update()
        native=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.copy()
        predicted=Matrix.Translation(pivot)@Matrix.Rotation(factor*fraction,4,axis)
        error=max(abs(native[i][j]-predicted[i][j]) for i in range(4) for j in range(4))
        assert error<5e-7,(name,fraction,error)
        checks.append({'fraction':fraction,'native_matrix':[list(r) for r in native],'max_component_error':error})
    controls[key]=0.;controls.update_tag(refresh={'OBJECT'});bpy.context.view_layer.update()
    rows.append({'name':name,'property':key,'expression':driver.expression,'factor_rad':factor,'pivot_source_m':list(pivot),
                 'axis_source':list(axis),'descendants':descendants,'checks':checks,'constraints':0,'driver_modifiers':0})
assert sha(a.source)==before
report={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),'source_sha256':before,
        'blender_version':bpy.app.version_string,'blender_build':bpy.app.build_hash.decode(),'script_sha256':sha(Path(__file__)),
        'opening_groups':rows,'status':'passed','source_unchanged':True,
        'limits':'Proves the six saved opening controllers are simple proportional rotations with rigid descendants. Geometry clearance is a separate computation. Other controls, physics deformation and tire/wiper motion are outside this driver contract.','human_approval_reference':None}
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'status':report['status'],'groups':len(rows),'maximum_native_matrix_error':max(c['max_component_error'] for r in rows for c in r['checks'])}),flush=True)
