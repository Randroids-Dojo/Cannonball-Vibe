"""Native source lamp-emission bindings and four explicit preview spotlights."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def check_driver(owner, path, controls, property_name, factor):
    curves = [curve for curve in owner.animation_data.drivers if curve.data_path == path]
    assert len(curves) == 1
    curve = curves[0]
    assert curve.is_valid and curve.driver.is_valid and not curve.modifiers
    expression = ast.parse(curve.driver.expression, mode='eval').body
    assert isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Mult)
    assert isinstance(expression.left, ast.Name) and expression.left.id == 'value'
    assert isinstance(expression.right, ast.Constant) and expression.right.value == factor
    assert len(curve.driver.variables) == 1
    variable = curve.driver.variables[0]
    assert variable.name == 'value' and variable.type == 'SINGLE_PROP'
    assert variable.targets[0].id == controls and variable.targets[0].data_path == '["' + property_name + '"]'
    return {'data_path': path, 'expression': curve.driver.expression, 'property': property_name, 'factor': factor}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert not args.output.exists()
    source_sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()), load_ui=False, use_scripts=True)
    controls = bpy.data.objects['RigControls']
    numeric = {key: controls[key] for key in controls.keys() if isinstance(controls[key], (int, float))}
    materials = {'Material_Headlight': 'headlights', 'Material_Taillight': 'headlights',
                 'Material_BrakeLight': 'brake_lights', 'Material_ReverseLight': 'reverse_lights'}
    def update(values):
        for key, value in numeric.items():
            controls[key] = value if key.startswith('source_sim_') else 0.
        for key, value in values.items():
            controls[key] = value
        controls.update_tag(refresh={'OBJECT'})
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.update()
    update({})
    driver_rows = []
    for name, prop in materials.items():
        material = bpy.data.materials[name]
        socket = material.node_tree.nodes['Principled BSDF'].inputs['Emission Strength']
        driver_rows.append({'material': name, **check_driver(material.node_tree, socket.path_from_id('default_value'), controls, prop, 3)})
    bindings = []
    anchors = {'Light_Head_FL': 'Material_Headlight', 'Light_Head_FR': 'Material_Headlight',
               'Light_Tail_RL': 'Material_Taillight', 'Light_Tail_RR': 'Material_Taillight',
               'Light_Brake_L': 'Material_BrakeLight', 'Light_Brake_R': 'Material_BrakeLight',
               'Light_Brake_Center': 'Material_BrakeLight',
               'Light_Reverse_L': 'Material_ReverseLight', 'Light_Reverse_R': 'Material_ReverseLight'}
    for anchor, expected in anchors.items():
        node = bpy.data.objects[anchor]
        meshes = [obj for obj in node.children_recursive if obj.type == 'MESH' and obj.name.startswith('LOD0_')]
        assert meshes, 'No actual LOD0 emitter below ' + anchor
        for obj in meshes:
            assert expected in [slot.material.name for slot in obj.material_slots if slot.material], (anchor, obj.name)
        bindings.append({'anchor': anchor, 'expected_material': expected, 'actual_meshes': [obj.name for obj in meshes],
                         'matrix_source': [list(row) for row in node.matrix_world]})
    beams = []
    for anchor in ('Light_Head_FL', 'Light_Head_FR', 'Light_Reverse_L', 'Light_Reverse_R'):
        obj = bpy.data.objects['PreviewBeam_' + anchor]
        head = 'Head_' in anchor
        prop, power = ('headlights', 230) if head else ('reverse_lights', 24)
        assert obj.type == 'LIGHT' and obj.data.type == 'SPOT' and obj.parent == bpy.data.objects[anchor]
        assert obj.get('source_preview_only') is True and not obj.hide_render
        expected_location = Vector((0., .015 if head else -.015, 0.))
        assert (obj.location - expected_location).length <= 1e-6
        expected_direction = Vector((0., 20. if head else -5., -.63)).normalized()
        actual_direction = (obj.matrix_local.to_3x3() @ Vector((0., 0., -1.))).normalized()
        assert (actual_direction - expected_direction).length <= 1e-6
        assert abs(obj.data.spot_size - math.radians(58 if head else 95)) <= 1e-6
        driver = check_driver(obj.data, 'energy', controls, prop, power)
        beams.append({'name': obj.name, 'parent': anchor, 'preview_only': True,
                      'local_position_m': list(obj.location), 'local_direction': list(actual_direction),
                      'spot_size_rad': obj.data.spot_size, 'driver': driver})
    assert len([obj for obj in bpy.data.objects if obj.name.startswith('PreviewBeam_')]) == 4
    cases = [{prop: value} for prop in ('headlights', 'brake_lights', 'reverse_lights') for value in (0., .375, 1.)]
    cases += [{prop: value for prop in ('headlights', 'brake_lights', 'reverse_lights')} for value in (0., .375, 1.)]
    states = []
    for values in cases:
        update(values)
        emitted, powers = {}, {}
        for name, prop in materials.items():
            value = bpy.data.materials[name].node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value
            expected = values.get(prop, 0.) * 3
            assert abs(value - expected) <= 1e-6
            emitted[name] = {'actual': value, 'expected': expected}
        for beam in beams:
            value = bpy.data.objects[beam['name']].data.energy
            expected = values.get(beam['driver']['property'], 0.) * beam['driver']['factor']
            assert abs(value - expected) <= 1e-5
            powers[beam['name']] = {'actual_watts': value, 'expected_watts': expected}
        states.append({'controls': values, 'emission': emitted, 'beam_power': powers})
    assert hashlib.sha256(args.source.read_bytes()).hexdigest() == source_sha
    report = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': source_sha, 'source_unchanged': True, 'status': 'passed',
              'blender': bpy.app.version_string, 'build': bpy.app.build_hash.decode(),
              'material_drivers': driver_rows, 'actual_emitter_bindings': bindings,
              'preview_beams': beams, 'states': states, 'human_approval_reference': None,
              'limits': 'headlights, brake_lights and reverse_lights are independent editable source preview controls. They do not simulate pedal force, gearing, electrical load or engine state. Indicator/hazard timeline cases are in the separate109-state source-controls report. Runtime lamps have their own engine-state and native-light acceptance.'}
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'status': 'passed', 'preview_states': len(states), 'emitter_anchors': len(bindings), 'beam_count': len(beams)}), flush=True)


if __name__ == '__main__':
    main()
