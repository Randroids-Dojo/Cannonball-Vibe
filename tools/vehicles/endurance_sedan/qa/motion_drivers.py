"""Bind tire and wiper continuous domains to the actual saved rigid drivers."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


def number(node):
    value = ast.literal_eval(node)
    assert isinstance(value, (float, int)) and math.isfinite(value)
    return value


def driver(curve, controls, bindings):
    assert curve.driver.type == "SCRIPTED" and curve.driver.is_valid and curve.is_valid
    assert not curve.mute and not curve.modifiers
    actual = {}
    for variable in curve.driver.variables:
        assert variable.type == "SINGLE_PROP" and len(variable.targets) == 1
        target = variable.targets[0]
        assert target.id == controls
        actual[variable.name] = target.data_path
    assert actual == {key: '["' + value + '"]' for key, value in bindings.items()}
    return ast.parse(curve.driver.expression, mode="eval").body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    assert not args.output.exists()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = sha(args.source)
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()), load_ui=False, use_scripts=True)
    scene = bpy.context.scene
    spec = json.loads(scene["specification"])
    controls = bpy.data.objects["RigControls"]
    baseline = {key: float(controls[key]) for key in controls.keys()
                if isinstance(controls[key], (float, int))}

    def pose(values, frame=1):
        for key, value in baseline.items():
            controls[key] = value if key.startswith("source_sim_") else 0.
        for key, value in values.items():
            controls[key] = value
        controls.update_tag(refresh={"OBJECT"})
        scene.frame_set(frame)
        bpy.context.view_layer.update()

    def descendants(obj):
        names = []
        for child in obj.children_recursive:
            assert not child.constraints
            assert not (child.animation_data and child.animation_data.drivers), child.name
            assert all(mod.type in ("BEVEL", "WEIGHTED_NORMAL", "NORMAL_EDIT", "SOLIDIFY", "TRIANGULATE", "DECIMATE", "WELD")
                       for mod in child.modifiers), child.name
            names.append(child.name)
        return names

    def error(actual, expected):
        return max(abs(actual[i][j] - expected[i][j]) for i in range(4) for j in range(4))

    pose({})
    tires = []
    maximum = 0.
    for suffix in ("FL", "FR", "RL", "RR"):
        suspension = bpy.data.objects["Suspension_" + suffix]
        wheel = bpy.data.objects["Wheel_" + suffix]
        rest = suspension.matrix_world.copy()
        wheel_rest = wheel.matrix_world.copy()
        assert wheel.parent == suspension and not wheel.constraints and not suspension.constraints
        assert wheel.rotation_mode == suspension.rotation_mode == "XYZ"
        curves = {(c.data_path, c.array_index): c for c in suspension.animation_data.drivers}
        expected_channels = {("location", 2)} | ({("rotation_euler", 2)} if suffix.startswith("F") else set())
        assert curves.keys() == expected_channels
        node = driver(curves[("location", 2)], controls, {"value": "suspension"})
        assert isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
        assert abs(number(node.left) - spec["geometry"]["wheel_radius_m"]) < 1e-12
        assert isinstance(node.right, ast.Name) and node.right.id == "value"
        yaw_factor = 0.
        if suffix.startswith("F"):
            node = driver(curves[("rotation_euler", 2)], controls, {"value": "steering"})
            assert isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)
            assert isinstance(node.left, ast.Name) and node.left.id == "value"
            yaw_factor = number(node.right)
            assert abs(yaw_factor + math.radians(spec["geometry"]["steering_lock_deg"])) < 1e-12
        assert len(wheel.animation_data.drivers) == 1
        curve = wheel.animation_data.drivers[0]
        assert curve.data_path == "rotation_euler" and curve.array_index == 0
        node = driver(curve, controls, {"value": "wheel_roll"})
        assert isinstance(node, ast.Name) and node.id == "value"
        names = descendants(wheel)
        checks = []
        for steering, travel, roll in ((-1, -.075, .731), (1, .085, 4.29), (.193, -.031, 1.92),
                                       (-.617, .013, 5.7), (0, 0, 0)):
            pose({"steering": steering, "suspension": travel, "wheel_roll": roll})
            center = rest.translation + Vector((0, 0, travel))
            predicted = Matrix.Translation(center) @ Matrix.Rotation(yaw_factor * steering, 4, "Z") @ Matrix.Rotation(roll, 4, "X")
            actual = wheel.matrix_world.copy()
            delta = error(actual, predicted)
            assert delta < 1e-6, (suffix, steering, travel, roll, delta)
            maximum = max(maximum, delta)
            checks.append({"steering": steering, "travel_m": travel, "roll_rad": roll,
                           "native_world_matrix": [list(r) for r in actual], "max_error": delta})
        tires.append({"wheel": suffix, "center_source_m": list(rest.translation), "yaw_factor_rad": yaw_factor,
                      "wheel_rest_matrix": [list(r) for r in wheel_rest], "roll_axis_local": [1, 0, 0],
                      "travel_axis_source": [0, 0, 1], "continuous_steering": [-1, 1],
                      "continuous_travel_m": [-.075, .085], "continuous_roll_rad": [0, math.tau],
                      "rigid_wheel_descendants": names, "native_checks": checks})
        pose({})
    wipers = []
    for name in ("Wiper_L", "Wiper_R"):
        obj = bpy.data.objects[name]
        assert not obj.constraints and obj.rotation_mode == "QUATERNION"
        rest = obj.matrix_world.copy()
        quaternion = obj.rotation_quaternion.copy()
        w, x, y, z = quaternion
        sine = (-z, y, -x, w)
        half_angle = math.radians(spec["mechanisms"][name]["sweep_deg"]) / 2
        assert len(obj.animation_data.drivers) == 4
        expressions = []
        for curve in obj.animation_data.drivers:
            assert curve.data_path == "rotation_quaternion" and 0 <= curve.array_index < 4
            node = driver(curve, controls, {"value": "wiper_sweep", "run": "wipers_running"})
            assert isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
            for term, fn, coefficient in ((node.left, "cos", quaternion[curve.array_index]),
                                          (node.right, "sin", sine[curve.array_index])):
                assert isinstance(term, ast.BinOp) and isinstance(term.op, ast.Mult)
                assert abs(number(term.left) - coefficient) < 1e-7
                trig = term.right
                assert isinstance(trig, ast.Call) and isinstance(trig.func, ast.Name) and trig.func.id == fn and len(trig.args) == 1 and not trig.keywords
                phase = trig.args[0]
                assert isinstance(phase, ast.BinOp) and isinstance(phase.op, ast.Mult)
                assert abs(number(phase.right) - half_angle) < 1e-12
                expected_wave = ast.parse(f"max(value,run*(.5-.5*cos((frame-1)*{math.tau/(60*1.35):.16g})))", mode="eval").body
                assert ast.dump(phase.left) == ast.dump(expected_wave)
            expressions.append({"index": curve.array_index, "expression": curve.driver.expression})
        axis = (rest.to_3x3() @ Vector((0, 0, 1))).normalized()
        expected_axis = Vector(spec["mechanisms"][name]["axis_source"]).normalized()
        # The dimension sheet axis is rounded; the actual saved35.31deg frame
        # drives the certificate. Use its declared angular modeling tolerance.
        axis_delta_deg = math.degrees(math.atan2(axis.cross(expected_axis).length,
                                                axis.dot(expected_axis)))
        assert axis_delta_deg <= spec["tolerances"]["hinge_axis_deg"]
        names = descendants(obj)
        checks = []
        for fraction in (0., .001, .123456789, .5, .731, .999, 1.):
            pose({"wiper_sweep": fraction})
            predicted = Matrix.Translation(rest.translation) @ Matrix.Rotation(half_angle * 2 * fraction, 4, axis) @ Matrix.Translation(-rest.translation) @ rest
            actual = obj.matrix_world.copy()
            delta = error(actual, predicted)
            assert delta < 1e-6, (name, fraction, delta)
            maximum = max(maximum, delta)
            checks.append({"fraction": fraction, "native_world_matrix": [list(r) for r in actual], "max_error": delta})
        wipers.append({"name": name, "pivot_source_m": list(rest.translation), "axis_source": list(axis),
                       "dimension_sheet_axis_delta_deg": axis_delta_deg,
                       "dimension_sheet_axis_tolerance_deg": spec["tolerances"]["hinge_axis_deg"],
                       "factor_rad": half_angle * 2, "rest_world_matrix": [list(r) for r in rest],
                       "rigid_descendants": names, "expressions": expressions, "native_checks": checks,
                       "running_formula": "max(manual, run*(.5-.5*cos((frame-1)*2pi/81))) stays in[0,1] for each declared control in[0,1] at every frame."})
        pose({})
    cabin_controls = []
    for name, prop, local_axis in (("SteeringWheel_Pivot","steering",(0,1,0)),
                                   ("Pedal_Accelerator","accelerator",(1,0,0)),
                                   ("Pedal_Brake","brake",(1,0,0))):
        obj=bpy.data.objects[name];rest=obj.matrix_world.copy();q=obj.rotation_quaternion.copy()
        assert obj.rotation_mode=='QUATERNION' and not obj.constraints
        factor=(math.radians(spec['geometry']['steering_lock_deg'])*spec['mechanisms'][name]['ratio']
                if name=='SteeringWheel_Pivot' else math.radians(spec['mechanisms'][name]['open_deg']))
        w,x,y,z=q;ax,ay,az=local_axis
        sine=(-x*ax-y*ay-z*az,w*ax+y*az-z*ay,w*ay-x*az+z*ax,w*az+x*ay-y*ax)
        assert len(obj.animation_data.drivers)==4
        expressions=[]
        for curve in obj.animation_data.drivers:
            node=driver(curve,controls,{'value':prop})
            assert curve.data_path=='rotation_quaternion' and isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add)
            for term,fn,coefficient in ((node.left,'cos',q[curve.array_index]),(node.right,'sin',sine[curve.array_index])):
                assert isinstance(term,ast.BinOp) and isinstance(term.op,ast.Mult)
                assert abs(number(term.left)-coefficient)<1e-7
                trig=term.right
                assert isinstance(trig,ast.Call) and isinstance(trig.func,ast.Name) and trig.func.id==fn and len(trig.args)==1
                phase=trig.args[0]
                assert isinstance(phase,ast.BinOp) and isinstance(phase.op,ast.Mult)
                assert isinstance(phase.left,ast.Name) and phase.left.id=='value' and abs(number(phase.right)-factor/2)<1e-12
            expressions.append({'index':curve.array_index,'expression':curve.driver.expression})
        axis=(rest.to_3x3()@Vector(local_axis)).normalized();checks=[]
        domain=[-1.,1.] if name=='SteeringWheel_Pivot' else [0.,1.]
        for fraction in sorted(set([domain[0],.001,.02,.317,.731,.999,domain[1]])):
            pose({prop:fraction})
            expected=Matrix.Translation(rest.translation)@Matrix.Rotation(factor*fraction,4,axis)@Matrix.Translation(-rest.translation)@rest
            delta=error(obj.matrix_world,expected);assert delta<1e-6,(name,fraction,delta)
            maximum=max(maximum,delta);checks.append({'fraction':fraction,'native_world_matrix':[list(r) for r in obj.matrix_world],'max_error':delta})
        cabin_controls.append({'name':name,'property':prop,'axis_source':list(axis),'pivot_source_m':list(rest.translation),
                               'factor_rad':factor,'control_domain':domain,'rest_world_matrix':[list(r) for r in rest],
                               'rigid_descendants':descendants(obj),'expressions':expressions,'native_checks':checks})
        pose({})
    assert sha(args.source) == before
    report = {"task_id": "P1-018", "milestone": "M5", "utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": before, "source_unchanged": True, "blender_version": bpy.app.version_string,
              "blender_build": bpy.app.build_hash.decode(), "script_sha256": sha(Path(__file__)),
              "tires": tires, "wipers": wipers, "cabin_controls":cabin_controls, "maximum_native_matrix_error": maximum,
              "status": "passed", "human_approval_reference": None,
              "limits": "Saved rigid driver formula contract, not geometry clearance. Wheel co-assemblies and fixed mechanical contacts require separate interface review."}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "passed", "maximum_native_matrix_error": maximum}), flush=True)


if __name__ == "__main__":
    main()
