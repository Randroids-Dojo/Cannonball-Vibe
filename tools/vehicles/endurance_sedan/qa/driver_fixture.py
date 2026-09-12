"""Real native invalid/valid driver controls, isolated from the art source."""
import argparse
import json
from pathlib import Path
import sys

import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--case', choices=('invalid', 'corrected'), required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
assert not args.output.exists()
obj = bpy.data.objects.new('QaNativeDriverFixture', None)
bpy.context.scene.collection.objects.link(obj)
curve = obj.driver_add('location', 0)
curve.driver.expression = '1/0' if args.case == 'invalid' else '.5'
obj.update_tag(refresh={'OBJECT'})
bpy.context.scene.frame_set(2)
bpy.context.view_layer.update()
value = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).location.x
args.output.write_text(json.dumps({'case': args.case, 'expression': curve.driver.expression,
                                   'curve_valid': curve.is_valid, 'driver_valid': curve.driver.is_valid,
                                   'native_location_x': value, 'blender': bpy.app.version_string,
                                   'scope': 'Synthetic native driver rejection fixture only; not vehicle behavior'}, indent=2) + '\n',
                       encoding='utf8', newline='\n')
print('Native driver fixture completed with ' + args.case + ' expression.', flush=True)
