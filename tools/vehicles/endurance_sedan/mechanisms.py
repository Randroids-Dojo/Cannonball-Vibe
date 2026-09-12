"""Windshield-contact wipers and source inspection driver helpers."""

import math

from mathutils import Vector

from . import geometry as geo


def wipers(collection, lod, mats, pivots, spec):
    plane_point = Vector((0, spec['geometry']['cowl_y_m'], spec['geometry']['cowl_height_m']))
    for name, length, center in (('Wiper_L', .580, .360), ('Wiper_R', .480, .305)):
        pivot = pivots[name]
        normal = pivot.rotation_euler.to_matrix() @ Vector((0, 0, 1))
        plane_offset = (pivot.location - plane_point).dot(normal)
        # Rubber bottom is 0.5 mm off the ideal glass plane throughout sweep.
        blade_center_z = .0020 - plane_offset
        geo.box('LOD0_' + name + 'Rubber', (center, -.026, blade_center_z), (length, .010, .003), mats['rubber'], collection, pivot, radius=.0006)
        geo.box('LOD0_' + name + 'SpringRail', (center, -.026, blade_center_z + .0031), (length - .018, .014, .003), mats['trim'], collection, pivot, radius=.0007)
        geo.tube('LOD0_' + name + 'Arm', [(0, 0, .016), (.127, -.01, .025), (center, -.026, blade_center_z + .018)], [.008, .006, .004], mats['trim'], collection, pivot, sides=6)
        geo.box('LOD0_' + name + 'Clip', (center, -.026, blade_center_z + .011), (.036, .019, .017), mats['trim'], collection, pivot, radius=.003)
        geo.tube('LOD0_' + name + 'Boss', [(0, 0, .010), (0, 0, .021)], .009, mats['trim'], collection, pivot, sides=16)
        pivot['blade_bottom_offset_m'] = .0005
        pivot['blade_contact_plane_normal'] = list(normal)
        pivot['blade_span_m'] = length
        pivot['blade_center_local_x_m'] = center


def add_property(controls, name, minimum=0, maximum=1, description='Editable source inspection control'):
    controls[name] = 0.0
    controls.id_properties_ui(name).update(min=minimum, max=maximum, description=description)


def scalar_driver(owner, path, index, controls, prop, expression):
    if len(expression)>254:
        raise ValueError('Blender driver expression exceeds its 255-byte storage: '+expression)
    curve = owner.driver_add(path) if index is None else owner.driver_add(path, index)
    curve.driver.type = 'SCRIPTED'
    variable = curve.driver.variables.new()
    variable.name = 'value'
    variable.type = 'SINGLE_PROP'
    variable.targets[0].id = controls
    variable.targets[0].data_path = '["' + prop + '"]'
    curve.driver.expression = expression
    return curve


def variable(curve,name,controls,property_name):
    item=curve.driver.variables.new();item.name=name;item.type='SINGLE_PROP'
    item.targets[0].id=controls;item.targets[0].data_path='["'+property_name+'"]'


def quaternion_driver(obj, controls, prop, axis, maximum_angle):
    """Rotate about an authored local axis, preserving the sloped rest frame."""
    rest = obj.rotation_euler.to_quaternion()
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = rest
    # q_rest * q_axis(theta), expanded so saved drivers need no Python handler.
    w, x, y, z = rest
    ax, ay, az = axis
    sine = (-x * ax - y * ay - z * az,
            w * ax + y * az - z * ay,
            w * ay - x * az + z * ax,
            w * az + x * ay - y * ax)
    for i, (c, s) in enumerate(zip(rest, sine)):
        half_angle = maximum_angle / 2
        expression = f'{c:.16g}*cos(value*{half_angle:.16g})+{s:.16g}*sin(value*{half_angle:.16g})'
        scalar_driver(obj, 'rotation_quaternion', i, controls, prop, expression)


def source_controls(pivots, controls, mats, spec):
    for name in ('accelerator', 'brake', 'wiper_sweep', 'wipers_running', 'headlights', 'brake_lights', 'reverse_lights', 'left_indicators', 'right_indicators', 'hazards'):
        add_property(controls, name)
    for name, prop in (('Pedal_Accelerator', 'accelerator'), ('Pedal_Brake', 'brake')):
        quaternion_driver(pivots[name], controls, prop, (1, 0, 0), math.radians(spec['mechanisms'][name]['open_deg']))
    quaternion_driver(pivots['SteeringWheel_Pivot'], controls, 'steering', (0, 1, 0), math.radians(spec['geometry']['steering_lock_deg']) * spec['mechanisms']['SteeringWheel_Pivot']['ratio'])
    for name in ('Wiper_L', 'Wiper_R'):
        quaternion_driver(pivots[name], controls, 'wiper_sweep', (0, 0, 1), math.radians(spec['mechanisms'][name]['sweep_deg']))
        for curve in pivots[name].animation_data.drivers:
            variable(curve,'run',controls,'wipers_running')
            curve.driver.expression=curve.driver.expression.replace('value',f'max(value,run*(.5-.5*cos((frame-1)*{math.tau/(60*1.35):.16g})))')
    for key, prop in (('headlight', 'headlights'), ('taillight', 'headlights'), ('brake', 'brake_lights'), ('reverse', 'reverse_lights'), ('indicator_left', 'left_indicators'), ('indicator_right', 'right_indicators')):
        shader = mats[key].node_tree.nodes['Principled BSDF']
        curve=scalar_driver(shader.inputs['Emission Strength'], 'default_value', None, controls, prop, 'value*3')
        if key.startswith('indicator_'):
            variable(curve,'hazard',controls,'hazards')
            curve.driver.expression='max(value,hazard)*3*((frame-1)%60<30)'


def preview_illumination(collection,pivots,controls):
    import bpy
    for name in ('Light_Head_FL','Light_Head_FR','Light_Reverse_L','Light_Reverse_R'):
        if name not in pivots:continue
        head='Head_' in name
        data=bpy.data.lights.new('PreviewBeam_'+name,'SPOT');data.energy=0
        data.color=(.85,.91,1);data.spot_size=math.radians(58 if head else 95);data.spot_blend=.35
        data.shadow_soft_size=.025
        obj=bpy.data.objects.new(data.name,data);collection.objects.link(obj)
        obj.parent=pivots[name]
        obj.location=(0,.015 if head else -.015,0)
        aim=Vector((0,20 if head else -5,-.63))
        obj.rotation_euler=aim.to_track_quat('-Z','Y').to_euler()
        scalar_driver(data,'energy',None,controls,'headlights' if head else 'reverse_lights','value*'+str(230 if head else 24))
        obj['source_preview_only']=True
