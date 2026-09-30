"""Unaccepted C-skin form preview, derived only from the loaded actual scene.

No I/O, source save, export, rendering, archived geometry assignment or original
object mutation. The caller owns installation/removal of returned private objects.
Receiver, reinforcement, all finite joints and clearances remain open.
"""
import bpy
from endurance_sedan import roof_feature26 as native, corner_encoding
from .boundary02 import plan
from . import roof_fields12
from . import c_surface21
NAMES = ('LOD0_Roof', 'LOD0_StructuralBody', 'LOD0_BacklightSeal', 'LOD0_StampedPillar_CL', 'LOD0_StampedPillar_CR', 'LOD0_RoofSideRail_L', 'LOD0_RoofSideRail_R', 'LOD0_DoorFrame_RL', 'LOD0_DoorFrame_RR')

def stage():
    originals = {name: bpy.data.objects[name] for name in NAMES}
    before = {name: native.physical(obj) for name, obj in originals.items()}
    rows = {name: native.row(obj) for name, obj in originals.items()}
    staged = {}
    proof = {}
    try:
        roof, roof_proof = roof_fields12.make(originals['LOD0_Roof'])
        staged['LOD0_Roof'] = roof
        proof['LOD0_Roof'] = roof_proof
        roof_row = native.row(roof)
        for key in ('vertices', 'triangles', 'uvs', 'materials', 'triangle_materials'):
            if roof_row[key] != rows['LOD0_Roof'][key]:
                raise ValueError(('Roof changed a fixed evaluated field', key))
        rows['LOD0_Roof'] = roof_row
        planning = plan(rows)
        for side in ('L', 'R'):
            name = 'LOD0_StampedPillar_C' + side
            if len(originals[name].modifiers):
                raise ValueError('Preview replacement requires explicitly unmodified original C mesh')
            obj, p, surface = c_surface21.make(originals[name], rows, planning[side], side, corner_encoding.encode)
            staged[name] = obj
            proof[name] = p
        if any((native.physical(obj) != before[name] for name, obj in originals.items())):
            raise ValueError('Preview changed an original source object')
        return {'staged_objects': staged, 'proof': proof, 'actual_boundary': planning, 'status': 'Unaccepted form preview only; existing reinforcement and body are unchanged and intersect the private C skins.', 'originals_unchanged': True, 'source_saved': False, 'exported': False, 'gpu_used': False}
    except BaseException:
        for obj in reversed(list(staged.values())):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
