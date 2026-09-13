"""Install already validated staged seat meshes into an unsaved Blender scene.

No file reads, saves, rendering or export. Original semantic carriers retain
their object identity/parent/properties. New foam and switch mount inherit the
seat's authored semantic donor. The caller owns subsequent whole-source gates.
"""
import bpy
from mathutils import Matrix


def apply_prepared(replacements, engineering):
    if engineering.get('status') != 'prepared_native_valid_requires_assembly_fit':
        raise ValueError('A validated prepared seat is required')
    prefix = engineering['seat']
    if prefix not in ('FrontL','FrontR','RearL','RearR'):
        raise ValueError('Unknown authored seat')
    removed = engineering['removed_originals']
    replaced = engineering['replaced_originals']
    added = engineering['new_semantic_objects']
    if len(set(removed+replaced+added)) != len(removed+replaced+added):
        raise ValueError('Ambiguous seat mutation inventory')
    if set(replacements) != set(replaced+added):
        raise ValueError('Prepared seat inventory differs from declared replacement')
    if any(name in bpy.data.objects for name in added):
        raise ValueError('Seat has already been installed')
    originals = {name:bpy.data.objects[name] for name in removed+replaced}
    donor = bpy.data.objects['LOD0_'+prefix+'BackInsert']
    parent = donor.parent
    collections = list(donor.users_collection)
    properties = {key:donor[key] for key in donor.keys()}
    for name,obj in replacements.items():
        if obj not in list(bpy.data.objects) or obj.type!='MESH' or obj.modifiers:
            raise ValueError('Missing or unevaluated staged seat object')
        obj.data.calc_loop_triangles()
        if len(obj.data.loop_triangles)!=engineering['after_triangles'][name] or len(obj.data.materials)!=1:
            raise ValueError('Staged seat geometry/material count changed')
    created = {}
    for name,stage in replacements.items():
        if name in originals:
            obj = originals[name]
            obj.modifiers.clear()
            obj.data = stage.data
            obj.matrix_world = Matrix.Identity(4)
            bpy.data.objects.remove(stage,do_unlink=True)
        else:
            obj = stage
            for collection in list(obj.users_collection):
                collection.objects.unlink(obj)
            for collection in collections:
                collection.objects.link(obj)
            obj.parent = parent
            obj.matrix_world = Matrix.Identity(4)
            for key,value in properties.items():
                obj[key] = value
            obj.name = name
        obj['coherent_seat_prefix'] = prefix
        obj['coherent_seat_role'] = name.removeprefix('LOD0_'+prefix)
        created[name] = obj
    for name in removed:
        bpy.data.objects.remove(originals[name],do_unlink=True)
    return created, {'seat':prefix,'removed':removed,'replaced':replaced,'added':added,
                     'triangle_delta':engineering['triangle_delta'],
                     'normal_codes_reencoded_during_install':False}
