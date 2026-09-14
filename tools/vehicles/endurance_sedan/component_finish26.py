"""Current native final components; no archived scene or mesh-table inputs."""
from pathlib import Path
import json
import bpy
from . import geometry as geo, corner_encoding as codec, boolean_surface as repair
from . import surface_normals, triangle_projection, roof_feature26 as native
from . import detail_six26, detail_thirteen26, brake_finish26, cylinder_finish26
from . import arch_finish26, arch_native26, lip_finish26, roof_finish26
from . import climate_carrier26, front_housing26, trunk_ribs26, front_liner26
from . import main_coolant26, main_sockets26, tank_repair26, tank_chamfer26, bevel_reserve26
from . import cooling_finish26
from .qa.self_geometry import scan
from .qa.solid_interfaces import boundary_shell


def finish_native(obj):
    result = codec.encode(obj.data, [tuple(n.vector) for n in obj.data.corner_normals])
    assert result['passed']
    topology = repair.repair(obj, scan, geo.evaluated_counts)
    assert topology.get('maximum_common_normal_angle_degrees', 0) <= .025
    return {'native_requested_target_encoding': result, 'bounded_boolean_topology_repair': topology}


def apply(actual_preboolean_rear_reference, actual_preboolean_body_surface):
    proof = {}
    print('COMPONENT26 radial detail', flush=True)
    _, proof['six'] = detail_six26.apply(geo, native.row)
    _, proof['thirteen'] = detail_thirteen26.apply(geo, native.row)
    _, proof['brakes'] = brake_finish26.apply(geo, native.row, codec.encode)
    _, proof['cylinders'] = cylinder_finish26.apply(geo, native.row, codec.encode)
    proof['arches'] = [arch_finish26.apply(bpy.data.objects[name], arch_native26)
                       for name in ('LOD0_StructuralBody', 'LOD0_FrontBumper',
                                    'LOD0_FrontFender_L', 'LOD0_FrontFender_R')]
    proof['rear_lip'] = lip_finish26.apply(bpy.data.objects['LOD0_StructuralBody'],
        actual_preboolean_rear_reference, surface_normals, arch_native26)
    print('COMPONENT26 formed roof', flush=True)
    proof['roof'] = roof_finish26.apply()
    _, proof['trunk_ribs'] = trunk_ribs26.build()
    _, proof['climate_carrier'] = climate_carrier26.apply(geo, native.row)
    print('COMPONENT26 front wheelhouse', flush=True)
    _, proof['front_liner']=front_liner26.apply(geo, native.row, actual_preboolean_body_surface)
    made, proof['front_housing'] = front_housing26.build_candidates(geo, native.row, finish_native)
    for name, candidate in made.items():
        obj = bpy.data.objects[name]
        assert obj.matrix_world == candidate.matrix_world and obj.parent == candidate.parent
        roof_finish26.install(obj, candidate)
        if 'LinerRetainer_' in name:
            obj['fitted_retainer_seat'] = json.dumps(next(r for r in proof['front_housing']['retainers'] if r['object'] == name), sort_keys=True)
            obj['manufacturing_form'] = '8-sided seated molded retainer head; no modeled threaded shaft'
        elif 'WheelArchLiner_' in name:
            obj['manufacturing_form'] = 'Molded2.5mm liner,444/446.5mm section,55 stations spanning-26.8..206.8deg; actual tower and24mm damper service apertures'
            obj['fitted_housing_revision26'] = json.dumps(next(r for r in proof['front_housing']['liners'] if r['object'] == name), sort_keys=True)
        else:
            obj['manufacturing_form'] = '3.75mm formed inboard wall atabsX461.25..465mm;47mm axle and21mm lower-arm service apertures'
            obj['fitted_housing_revision26'] = json.dumps(next(r for r in proof['front_housing']['walls'] if r['object'] == name), sort_keys=True)
    print('COMPONENT26 main cooling', flush=True)
    proof['main_coolant'] = main_coolant26.apply(geo, native.row)
    original = native.row(bpy.data.objects['LOD0_ExpansionTank'])
    _, proof['main_sockets'] = main_sockets26.apply(geo, native.row, after_cut=cooling_finish26.main_stack)
    stack=bpy.data.objects['LOD0_RadiatorStack']
    assert not stack.modifiers
    before=native.row(stack);moved=[]
    for vertex in stack.data.vertices:
        if vertex.co.y>2.035:
            moved.append(vertex.index);vertex.co.y-=.004
    stack.data.update();after=native.row(stack)
    assert moved and all(after['vertices'][i]==p for i,p in enumerate(before['vertices']) if i not in moved)
    proof['stack_retreat']={'forward_retreat_m':.004,'moved_vertices':moved,'unchanged_rear_vertices_exact':True}
    tank = bpy.data.objects['LOD0_ExpansionTank']
    hose = native.row(bpy.data.objects['LOD0_CoolantHose'])
    proof['tank_repair'] = tank_repair26.repair_tank(tank, original, hose,
        row=native.row, boolean_surface=repair, encode=codec.encode,
        closest=triangle_projection.closest, boundary_shell=boundary_shell,
        exact_scan=scan, evaluated_counts=geo.evaluated_counts)
    proof['tank_chamfer'] = tank_chamfer26.apply(tank, original, hose,
        row=native.row, encode=codec.encode, boundary_shell=boundary_shell,
        exact_scan=scan, evaluated_counts=geo.evaluated_counts)
    recipe = json.loads(Path(__file__).with_name('bevel_reserve26.json').read_text())
    proof['bevel_reserve'] = bevel_reserve26.apply(recipe=recipe)
    proof['charge_cooling'] = cooling_finish26.charge_cooling()
    material = bpy.data.materials['Material_Screen']
    shader = material.node_tree.nodes.get('Principled BSDF')
    assert shader is not None
    shader.inputs['Specular IOR Level'].default_value = .06
    shader.inputs['Roughness'].default_value = .32
    proof['display_ar'] = {'specular_ior_level': .06, 'roughness': .32}
    print('COMPONENT26 complete', flush=True)
    return proof
