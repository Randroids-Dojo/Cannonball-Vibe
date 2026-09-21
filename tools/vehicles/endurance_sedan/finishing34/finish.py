"""Compose current repairs from this build's own native references.

No retained report or prior mesh is read here. The caller owns the scene and
retains returned proof alongside the new editable source.
"""
import json
import bpy
from endurance_sedan import (
    model, exterior, surface_normals, triangle_projection, corner_encoding,
    roof_feature26, staged_normals, arch_finish26, arch_native26,
    front_target_transport28, front_bend27, front_lamp27,
    reserve_correspondence26, bevel_reserve26, geometry,
)
from . import door_fields, valance_fields, closure_uv, planar_glass, lamp_surface, lamp_apply
from .front_sheet import combined, sheet_reference, field_support
from .c_quarter.stage91 import stage as c_stage
from .c_quarter.fields46 import validate as receiver_fields


def normalized(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False))


def full_field(mesh, targets):
    mesh.calc_loop_triangles()
    normals = [tuple(n.vector) for n in mesh.corner_normals]
    rows = [dict(triangle=t.index, **field_support.complete_affine_angle(
        [targets[i] for i in t.loops], [normals[i] for i in t.loops])) for t in mesh.loop_triangles]
    return {'triangles':len(rows), 'maximum_degrees':max(r['maximum_degrees'] for r in rows), 'rows':rows}


def apply(construction):
    proof = {'schema':'current-surface-construction34.v1', 'archived_geometry_input':None,
             'remaining_visual_work':['upper roof return','lamp residual reflections','lower bumper ends'],
             'original_body':model.BODY_PREVOIDS_ROW34, 'original_sheet':model.BODY_PREVOIDS_SHEET34,
             'original_valance':exterior.ORIGINAL_VALANCE34}
    names = set(door_fields.SEMANTICS) | set(sheet_reference.SEMANTICS) | {
        'LOD0_Roof','LOD0_StampedPillar_CL','LOD0_StampedPillar_CR',
        'LOD0_PillarC_L','LOD0_PillarC_R',valance_fields.SEMANTIC,
        *closure_uv.PROFILE['names'],*planar_glass.NAMES}
    def other_meshes():
        return {o.name:staged_normals.digest({'raw':reserve_correspondence26.raw(o),
            'modifiers':bevel_reserve26.modifier_state(o)}) for o in bpy.data.objects
            if o.type=='MESH' and o.name not in names}
    bpy.context.view_layer.update()
    before_other = other_meshes();before_objects = set(bpy.data.objects)
    body_plans = {n:door_fields.prepare(bpy.data.objects[n],model.BODY_PREVOIDS_ROW34,surface_normals)
                  for n in door_fields.SEMANTICS}
    proof['body_plans'] = body_plans;proof['body_native'] = {}
    for n,plan in body_plans.items():
        door_fields.apply(bpy.data.objects[n],plan,corner_encoding.encode)
        proof['body_native'][n] = full_field(bpy.data.objects[n].data,plan['targets'])
    print('PORTABLE34 complete body/door fields',flush=True)

    objects = {n:bpy.data.objects[n] for n in sheet_reference.SEMANTICS}
    plans = combined.prepare(objects,model.BODY_PREVOIDS_SHEET34,
        construction['front_form27']['field_packet'], ownership=surface_normals,
        projection=triangle_projection,transport=front_target_transport28,
        bend_field=front_bend27.field,optical_field=front_lamp27.field,
        return_references={n:arch_finish26.prepare(objects[n],arch_native26)
                           for n in sheet_reference.SEMANTICS[:2]},return_profile=arch_finish26.PROFILE)
    proof['front_plans'] = plans
    proof['front_native'] = combined.apply(objects,plans,corner_encoding.encode)
    print('PORTABLE34 complete actual front fields',flush=True)

    current_body = roof_feature26.row(bpy.data.objects['LOD0_StructuralBody'])
    staged = c_stage()
    assert staged['proof']['LOD0_StructuralBody']['original_body_row'] == current_body
    rows = {n:roof_feature26.row(o) for n,o in staged['staged_objects'].items()}
    proof['C_receiver_fields'] = receiver_fields({'original':current_body,
        'candidate':rows['LOD0_StructuralBody'],'proof':staged['proof']['LOD0_StructuralBody']},
        staged['actual_boundary'])
    proof['C_structure'] = {'rows':rows,'proof':staged['proof'],
        'actual_boundary':staged['actual_boundary'],'scope_cost':staged['scope_cost']}
    for n,o in staged['staged_objects'].items():
        bpy.data.objects[n].data=o.data;bpy.data.objects.remove(o,do_unlink=True)
    bpy.context.view_layer.update()
    print('PORTABLE34 paired C skins, receiver and fitted members',flush=True)

    obj=bpy.data.objects[valance_fields.SEMANTIC]
    plan=valance_fields.prepare(obj,exterior.ORIGINAL_VALANCE34,surface_normals,staged_normals,triangle_projection)
    proof['valance_plan']=plan
    proof['valance_native']=valance_fields.apply(obj,plan,corner_encoding.encode,staged_normals)
    proof['valance_complete_fields']=full_field(obj.data,plan['targets'])

    obj=bpy.data.objects['LOD0_FrontBumper']
    sheet_plan=next(p for p in plans if p['object']==obj.name)
    plan=lamp_surface.prepare(normalized(sheet_reference.native_state(obj)),
        normalized(model.BODY_PREVOIDS_ROW34),normalized(construction['front_prefix29']),
        normalized(construction['front_form27']['field_packet']),normalized(sheet_plan))
    plan['physical_before']=field_support.fields(obj)
    proof['lamp_plan']=plan
    proof['lamp_native']=lamp_apply.apply(obj,plan,encode=corner_encoding.encode,
        capture_fields=field_support.fields,complete_affine_angle=field_support.complete_affine_angle,
        angle=field_support.angle)
    proof['current_front_native']=sheet_reference.native_state(obj)
    print('PORTABLE34 finite lamp surface; residual visual gate remains open',flush=True)

    proof['glass']={}
    for name in planar_glass.NAMES:
        obj=bpy.data.objects[name];plan=planar_glass.prepare(obj)
        planar_glass.apply(obj,plan);proof['glass'][name]=planar_glass.verify(obj,plan)
    proof['closures']={};stable={}
    for name in sorted(closure_uv.PROFILE['names']):
        obj=bpy.data.objects[name];original_modifiers=bevel_reserve26.modifier_state(obj)
        mesh,witness=closure_uv.build(obj,profile=closure_uv.PROFILE,
                                    expected_profile_digest=closure_uv.digest(closure_uv.PROFILE))
        obj.data=mesh;obj.modifiers.clear();mesh.name=name+'_DeterministicClosureMesh'
        bpy.context.view_layer.update();assert closure_uv.capture(obj.data)==witness['final']
        proof['closures'][name]={'construction':witness,'original_modifiers':original_modifiers}
        stable[name]={'profile_sha256':closure_uv.digest(closure_uv.PROFILE),
            'target_sha256':witness['target_sha256'],'final_sha256':closure_uv.digest(witness['final'])}
    bpy.context.scene['closure_uv_construction']=json.dumps(stable,sort_keys=True,separators=(',',':'))
    bpy.context.scene['planar_glazing_domains']=json.dumps({'schema':'native-planar-glass-domains.v1',
        'names':list(planar_glass.NAMES),'source_modifier':'live4.5mmSolidify'},sort_keys=True)
    assert other_meshes()==before_other and set(bpy.data.objects)==before_objects
    shipping=[o for o in bpy.data.collections['Asset'].all_objects if o.type=='MESH'
              and o.name.startswith('LOD0_') and not o.get('source_preview_only')]
    count=sum(geometry.evaluated_counts(o)['triangles'] for o in shipping)
    assert count==148898 and count<=150000,count
    proof.update(lod0_triangles=count,unrelated_raw_modifiers_exact=len(before_other),
        persistent_object_inventory_exact=True,source_saved_by_caller=False)
    proof['final_native_fields']={n:reserve_correspondence26.evaluated(bpy.data.objects[n]) for n in sorted(names)}
    print('PORTABLE34 current fields complete: '+str(count)+'LOD0 triangles',flush=True)
    return proof