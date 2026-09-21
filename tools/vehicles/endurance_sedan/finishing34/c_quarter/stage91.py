"""Atomic uninstalled paired C/receiver/member flush-foot composition.

Apply the lead's body-field stage first. This module reads the actual current
scene through stage47/72 and performs no file I/O, source save or export.
"""
import bpy
from endurance_sedan import roof_feature26 as native, corner_encoding
from .stage47 import stage as c_receiver_stage
from .stage72 import add_reinforcement
from .base_fields86 import check as field_check
from . import base84

def finish_bases(staged):
    before_objects = set(bpy.data.objects)
    before_meshes = set(bpy.data.meshes)
    previous = {}
    new = {}
    proofs = {}
    fixed = {name: native.physical(obj) for name, obj in staged['staged_objects'].items() if not name.startswith('LOD0_PillarC_')}
    try:
        for side in ('L', 'R'):
            name = 'LOD0_PillarC_' + side
            old = staged['staged_objects'][name]
            old_proof = staged['proof'][name]
            if old is bpy.data.objects.get(name):
                raise ValueError('A source member was supplied instead of an owned staged member')
            if 'input_member_ideal_targets' in old_proof:
                raise ValueError('Finite foot was already applied')
            old_count = len(native.row(old)['triangles'])
            obj, proof = base84.make(old, staged['staged_objects']['LOD0_StructuralBody'], old_proof, corner_encoding.encode)
            proof['input_member_ideal_targets'] = old_proof['ideal_targets']
            proof['independent_complete_field_check'] = field_check(native.row(obj), proof, proof['input_member_ideal_targets'])
            proof['original_source_member_row'] = old_proof['original_current_member_row']
            proof['foot_triangle_increment'] = proof['native_counts']['triangles'] - old_count
            previous[name] = old
            new[name] = obj
            proofs[name] = proof
        if any((native.physical(staged['staged_objects'][name]) != value for name, value in fixed.items())):
            raise ValueError('Foot operation changed fixed staged body/C/Roof fields')
        prior = staged['scope_cost']['reinforcement_pair_delta']
        pair = sum((proof['native_counts']['triangles'] - len(proof['original_source_member_row']['triangles']) for proof in proofs.values()))
        staged['scope_cost'].update({'pre_foot_reinforcement_pair_delta': prior, 'foot_pair_increment': sum((p['foot_triangle_increment'] for p in proofs.values())), 'reinforcement_pair_delta': pair, 'combined_with_reinforcement_delta': staged['scope_cost']['combined_delta'] + pair})
        staged['staged_objects'].update(new)
        staged['proof'].update(proofs)
        for obj in previous.values():
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        staged['status'] = 'Uninstalled C/receiver/reinforcement with scoped finite feet. Current paired finite/rest proof is separate; remaining roof interfaces, complete motion, native LOD budgets and visual acceptance stay open.'
        return staged
    except BaseException:
        for obj in set(bpy.data.objects) - before_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in set(bpy.data.meshes) - before_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise

def stage():
    before_objects = set(bpy.data.objects)
    before_meshes = set(bpy.data.meshes)
    try:
        return finish_bases(add_reinforcement(c_receiver_stage()))
    except BaseException:
        for obj in set(bpy.data.objects) - before_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in set(bpy.data.meshes) - before_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
