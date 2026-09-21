"""Current front-door LODs evaluated in their original frames before reduction.

The final batch still uses the existing rigid-parent transform. Avoiding the
extra initial coordinate roundtrip preserves the actual evaluated source shell
and corner field before the existing per-component simplifier examines it.
"""
from .. import source_generation as records

GROUPS = ((2, 'Door_FL', 'Material_Paint'), (2, 'Door_FR', 'Material_Paint'))
SELECTIVE_GROUPS = (*GROUPS, (2, 'Door_RL', 'Material_Rubber'))
MEMBERS = {
    (2, 'Door_' + side, 'Material_Paint'): tuple(sorted((
        'LOD0_DoorFrame_' + side, 'LOD0_DoorInnerHem_' + side,
        'LOD0_Door_' + side, 'LOD0_Handle_' + side,
        'LOD0_Mirror_' + mirror + 'Housing',
    ))) for side, mirror in (('FL', 'Left'), ('FR', 'Right'))
}


def validate_group(key, names):
    records.require(key in MEMBERS, 'Unknown current upper selective group')
    records.require(tuple(sorted(names)) == MEMBERS[key],
                    'Incomplete or duplicate current upper selective source members')


def adapter(key, members, parent, original_bake, capture):
    """Return a scoped bake callback and actual original-frame observations."""
    import bpy

    validate_group(key, [obj.name for obj in members])
    records.require(parent.name == key[1], 'Current upper selective parent differs')
    originals = {obj.name: obj for obj in members}
    seen = set()
    observations = []

    def bake(name, actual_members, target_parent, collection, material):
        if len(actual_members) != 1 or actual_members[0].name not in originals:
            return original_bake(name, actual_members, target_parent, collection, material)
        original = actual_members[0]
        records.require(original == originals[original.name] and original.name not in seen,
                        'Current upper original singleton changed or repeated')
        records.require(target_parent == parent and original.parent == parent
                        and material.name == key[2], 'Current upper original frame/material changed')
        before = capture(original)
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = original.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
        obj = original.copy()
        obj.name = name
        obj.data = mesh
        obj.modifiers.clear()
        collection.objects.link(obj)
        bpy.context.view_layer.update()
        after = capture(obj)
        after['name'] = original.name
        records.require(before == after, 'Current upper evaluated original-frame fields changed')
        records.require(all(getattr(obj, field) == getattr(original, field)
                            for field in ('parent', 'matrix_world', 'matrix_basis',
                                          'matrix_parent_inverse', 'rotation_mode')),
                        'Current upper evaluated original moving frame changed')
        seen.add(original.name)
        observations.append({'source': original.name, 'complete_fields_sha256': records.digest(before),
            'complete_fields_exact': True, 'world': [list(row) for row in obj.matrix_world],
            'basis': [list(row) for row in obj.matrix_basis],
            'parent_inverse': [list(row) for row in obj.matrix_parent_inverse]})
        return obj, {'method': 'Exact evaluated original-frame initial temporary component',
                     'source_component': original.name, 'parent': parent.name}

    return bake, observations
