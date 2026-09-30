"""Add native fitted reinforcement to an uninstalled stage47 result.

No source assignment, file I/O, source save, export, or render. The original
body-field correction belongs before stage47. Every new member is built from
the actual current staged C and current fixed guide/glass/seal geometry.
"""
import bpy
from fractions import Fraction
from endurance_sedan import roof_feature26 as native, corner_encoding, geometry
from endurance_sedan.qa.self_geometry import scan
from .member_checks70 import fields
from . import reinforcement67

def serializable(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    return value

def add_reinforcement(staged):
    before_objects = set(bpy.data.objects)
    before_meshes = set(bpy.data.meshes)
    added = {}
    proofs = {}
    originals = {}
    try:
        for side, number in (('L', '-1'), ('R', '1')):
            name = 'LOD0_PillarC_' + side
            original = bpy.data.objects[name]
            if name in staged['staged_objects']:
                raise ValueError('Reinforcement was already staged')
            names = [name, 'LOD0_Backlight', 'LOD0_BacklightSeal', 'LOD0_RearBeltGuide_' + number, 'LOD0_DoorApertureSeal_R' + side]
            originals.update({n: native.physical(bpy.data.objects[n]) for n in names})
            rows = {n: native.row(bpy.data.objects[n]) for n in names}
            skin = native.row(staged['staged_objects']['LOD0_StampedPillar_C' + side])
            obj, proof = reinforcement67.make(original, rows[name], skin, rows['LOD0_Backlight'], rows['LOD0_RearBeltGuide_' + number], rows['LOD0_BacklightSeal'], rows['LOD0_DoorApertureSeal_R' + side], corner_encoding.encode)
            row = native.row(obj)
            counts = geometry.evaluated_counts(obj)
            self_check = scan(row)
            field_check = fields(row, proof)
            if self_check['status'] != 'passed':
                raise ValueError(('Actual staged reinforcement self check failed', side, self_check))
            keys = ('duplicate_faces', 'nonmanifold_edges', 'degenerate_faces', 'degenerate_triangles', 'triangulated_duplicate_faces', 'triangulated_nonmanifold_edges', 'nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals')
            if any((counts[k] for k in keys)):
                raise ValueError(('Actual staged reinforcement native validity failed', side, counts))
            proof['native_counts'] = counts
            proof['exact_self'] = self_check
            proof['direct_field_check'] = field_check
            proof['original_current_member_row'] = rows[name]
            proof['source_inputs'] = {n: rows[n] for n in names if n != name}
            added[name] = obj
            proofs[name] = serializable(proof)
        if any((native.physical(bpy.data.objects[n]) != v for n, v in originals.items())):
            raise ValueError('Reinforcement stage changed an original source object')
        staged['staged_objects'].update(added)
        staged['proof'].update(proofs)
        delta = sum((v['native_counts']['triangles'] - len(v['original_current_member_row']['triangles']) for v in proofs.values()))
        staged['scope_cost']['reinforcement_pair_delta'] = delta
        staged['scope_cost']['combined_with_reinforcement_delta'] = staged['scope_cost']['combined_delta'] + delta
        staged['status'] = 'Usable uninstalled C/receiver/reinforcement trial. Original base/body and upper interfaces, whole moving assembly and visual approval remain open.'
        return staged
    except BaseException:
        for obj in set(bpy.data.objects) - before_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in set(bpy.data.meshes) - before_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
