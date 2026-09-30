"""Build the measured original structural finish, seats and stowed documents.

Pure native construction on the current scene. No saved source, historical
mesh payload, report path or export process supplies the geometry.
"""
import bpy

from . import rear_wheelhouse, assembly_structure, assembly_fields, door_sills
from . import seat_assemblies, seat_install, corner_encoding, document_storage
from . import rear_seat_field
from .qa.self_geometry import scan


def apply(collection, parent, mats):
    if bpy.context.scene.get('cb_assembly_finish_applied') or 'LOD0_RearWheelhouseTrim_L' in bpy.data.objects:
        raise ValueError('Structural and seat finish must be built once on the original component recipe')
    if 'LOD0_RearRCushionInsert' not in bpy.data.objects:
        raise ValueError('The complete original four-seat construction is required')
    assembly_fields.CAPTURED_VERTICES.clear()
    assembly_fields.CLEANUP.clear()
    assembly_structure.CUTS.clear()
    changed, wheelhouse = rear_wheelhouse.build(collection, parent, mats['leather'])
    parts, structural = assembly_structure.build(collection, parent, mats)
    changed.update(parts)
    replacements, sill = door_sills.build(collection, parent, mats['rubber'],
                                         bpy.data.objects['LOD0_SillTread_L'].data.materials[0])
    for obj in replacements:
        name = obj['candidate_replaces']
        changed[name] = assembly_structure.replace(bpy.data.objects[name], obj)
    seats = {}
    with rear_seat_field.installed(seat_assemblies, corner_encoding.encode) as rear_policy:
        for prefix in ('FrontL', 'FrontR', 'RearL', 'RearR'):
            staged, engineering = seat_assemblies.prepare_seat(prefix, exact_scan=scan, encode=corner_encoding.encode)
            created, installation = seat_install.apply_prepared(staged, engineering)
            changed.update(created)
            seats[prefix] = {'engineering': engineering, 'installation': installation}
    storage, documents = document_storage.build()
    changed.update({obj.name: obj for obj in storage})
    bpy.context.scene['cb_assembly_finish_applied'] = True
    return changed, {'wheelhouse': wheelhouse, 'structure': structural, 'sills': sill,
                     'seats': seats, 'documents': documents,
                     'rear_replay': rear_policy,
                     'scope': 'Native original modeled assemblies. Independent current-source fit, motion, export and runtime acceptance remain required.'}
