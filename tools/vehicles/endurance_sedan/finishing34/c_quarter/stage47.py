"""Actual-scene C/Roof fields plus paired quarter receiver. No I/O or install.

The returned receiver proof identifies every newly authored face, and exact
original barycentric provenance for the retained faces. A later original-body
normal restoration must preserve the new authored receiver targets.
"""
import bpy
from endurance_sedan import roof_feature26 as native, corner_encoding
from . import stage24
from . import receiver40

def stage():
    for side in ('L', 'R'):
        obj = bpy.data.objects['LOD0_StampedPillar_C' + side]
        if len(obj.data.vertices) != 272:
            raise ValueError('C receiver stage requires the original272-vertex C source; do not reapply')
    body = bpy.data.objects['LOD0_StructuralBody']
    before = native.physical(body)
    original = native.row(body)
    made = stage24.stage()
    try:
        skins = {s: {'row': native.row(made['staged_objects']['LOD0_StampedPillar_C' + s]), 'proof': made['proof']['LOD0_StampedPillar_C' + s]} for s in ('L', 'R')}
        obj, proof = receiver40.build(body, original, skins, made['actual_boundary'], corner_encoding.encode)
        made['staged_objects']['LOD0_StructuralBody'] = obj
        proof['new_authored_face_indices'] = [i for i, owner in enumerate(proof['original_triangle_owners']) if owner is None]
        proof['original_body_row'] = original
        proof['later_body_field_stage_contract'] = 'Only restore original-body owned domains through exact mapped correspondence. Preserve new_authored_face_indices and their ideal_targets; this stage captures the actual current input field, never an archived old field.'
        made['proof']['LOD0_StructuralBody'] = proof
        if native.physical(body) != before:
            raise ValueError('Receiver changed the original loaded body')
        made['status'] = 'Usable paired C/receiver candidate. Reinforcement, other upper joints, rest/motion and visual review remain open.'
        made['scope_cost'] = {'C_pair_delta': -256, 'receiver_delta': proof['cost']['delta'], 'combined_delta': proof['cost']['delta'] - 256, 'Roof_geometry_delta': 0}
        return made
    except BaseException:
        for obj in reversed(list(made['staged_objects'].values())):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
