"""Guarded 13-part unsaved bevel trial. Never saves, exports or creates geometry.

Apply before the later portable charge-cooling port cuts. The native preimage
guard rejects changed/cut target geometry; the caller must rebind a new input
explicitly. No rotor or grille object is selected.
"""
import hashlib
import json
import math
from pathlib import Path

import bpy
from . import reserve_correspondence26 as correspondence

NAMES = (
    'LOD0_AuxiliaryTank', 'LOD0_ChargeCoolingRadiator',
    'LOD0_MainFuelLobe_-1', 'LOD0_MainFuelLobe_1',
    'LOD0_StampedPillar_BL', 'LOD0_StampedPillar_BR',
    'LOD0_Sump', 'LOD0_TransferPump', 'LOD0_V8Crankcase',
    'LOD0_V8CylinderBank_-1', 'LOD0_V8CylinderBank_1',
    'LOD0_Wiper_LRubber', 'LOD0_Wiper_RRubber',
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def physical(obj):
    mesh = obj.data
    return digest({'vertices': [list(p.co) for p in mesh.vertices],
        'edges': [(list(e.vertices), e.use_edge_sharp) for e in mesh.edges],
        'polygons': [(list(p.vertices), p.material_index, p.use_smooth) for p in mesh.polygons],
        'uvs': {layer.name: [list(d.uv) for d in layer.data] for layer in mesh.uv_layers},
        'normals': [list(n.vector) for n in mesh.corner_normals],
        'matrix': [list(r) for r in obj.matrix_world],
        'materials': [m.name if m else None for m in mesh.materials],
        'parent': obj.parent.name if obj.parent else None})


def modifier_state(obj):
    result = []
    for modifier in obj.modifiers:
        values = {'name': modifier.name, 'type': modifier.type}
        for prop in modifier.bl_rna.properties:
            if prop.is_readonly or prop.identifier in ('name', 'type', 'rna_type'):
                continue
            if prop.type in ('BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'):
                value = getattr(modifier, prop.identifier)
                values[prop.identifier] = list(value) if getattr(prop, 'is_array', False) else value
        result.append(values)
    return result


def evaluated(obj):
    graph = bpy.context.evaluated_depsgraph_get()
    value = obj.evaluated_get(graph)
    mesh = value.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    mesh.calc_loop_triangles()
    result = {'name': obj.name,
        'vertices': [list(value.matrix_world@p.co) for p in mesh.vertices],
        'triangles': [list(t.vertices) for t in mesh.loop_triangles],
        'normals': [list(n.vector) for n in mesh.corner_normals],
        'triangle_loops': [list(t.loops) for t in mesh.loop_triangles],
        'materials': [m.name if m else None for m in mesh.materials],
        'triangle_materials': [t.material_index for t in mesh.loop_triangles]}
    value.to_mesh_clear()
    return result


def shape_digest(row):
    return digest({k: v for k, v in row.items() if k != 'uvs'})


def apply(recipe=None, objects=None):
    """Preflight all 13 exact native inputs, then only assign BEVEL.segments=1."""
    if (bpy.app.version, bpy.app.build_hash.decode()) != ((5, 1, 2), 'ec6e62d40fa9'):
        raise ValueError('Expected pinned official Blender5.1.2 ec6e62d40fa9')
    if recipe is None:
        raise ValueError('An explicitly locked bevel construction recipe is required')
    if recipe.get('schema') != 'p1-018-detail-reserve13.v2' or tuple(recipe.get('names', [])) != NAMES:
        raise ValueError('Wrong declared13-part recipe')
    objects = {o.name: o for o in bpy.data.objects if o.type == 'MESH'} if objects is None else objects
    if any(name not in objects for name in NAMES):
        raise ValueError('Missing declared semantic target')
    actions = []; correspondence_proofs = {}
    for name in NAMES:
        obj = objects[name]
        expected = recipe['parts'][name]
        fields = expected.get('correspondence_fields')
        if fields is not None:
            if name not in ('LOD0_Sump', 'LOD0_V8Crankcase') or set(fields) != {'raw','evaluated_2','evaluated_1'}:
                raise ValueError('Undeclared native correspondence scope')
            if digest(fields['raw']) != expected['physical_sha256'] or shape_digest(fields['evaluated_2']) != expected['evaluated_before_sha256'] or shape_digest(fields['evaluated_1']) != expected['evaluated_after_sha256']:
                raise ValueError('Verification fixture no longer matches the original locked recipe')
            correspondence_proofs[name] = {}
        bevels = [m for m in obj.modifiers if m.type == 'BEVEL']
        if len(bevels) != 1 or bevels[0].segments != 2:
            raise ValueError('Expected one original2-segment bevel: '+name)
        if physical(obj) != expected['physical_sha256']:
            if fields is None: raise ValueError('Changed native input geometry/UV/normal/transform; apply before port cuts: '+name)
            correspondence_proofs[name]['raw'] = correspondence.compare_raw(fields['raw'], correspondence.raw(obj))
        if modifier_state(obj) != expected['modifier_state']:
            raise ValueError('Changed modifier preimage: '+name)
        actual = evaluated(obj)
        if shape_digest(actual) != expected['evaluated_before_sha256']:
            if fields is None: raise ValueError('Changed evaluated input: '+name)
            correspondence_proofs[name]['evaluated_before'] = correspondence.compare_evaluated(fields['evaluated_2'], correspondence.evaluated(obj))
        actions.append((obj, bevels[0], expected))
    # No mutation occurs before every expected target has passed preflight.
    raw_before = {name: physical(obj) for name, obj in objects.items()}
    modifier_before = {name: modifier_state(obj) for name, obj in objects.items()}
    for obj, bevel, expected in actions:
        bevel.segments = 1
    bpy.context.view_layer.update()
    results = []
    for obj, bevel, expected in actions:
        actual = evaluated(obj)
        if shape_digest(actual) != expected['evaluated_after_sha256']:
            fields = expected.get('correspondence_fields')
            if fields is None: raise ValueError('Unexpected actual candidate geometry/decoded normals: '+obj.name)
            correspondence_proofs[obj.name]['evaluated_after'] = correspondence.compare_evaluated(fields['evaluated_1'], correspondence.evaluated(obj))
        errors = []
        for normal in actual['normals']:
            if not all(math.isfinite(x) for x in normal):
                raise ValueError('Nonfinite native normal')
            length = math.sqrt(sum(x*x for x in normal))
            if not length or abs(length-1) > 1e-6:
                raise ValueError('Invalid raw native normal')
            errors.append(abs(length-1))
        results.append({'name': obj.name, 'triangles_before': expected['triangles_before'],
            'triangles_after': len(actual['triangles']), 'actual_shape_sha256': shape_digest(actual),
            'maximum_raw_normal_unit_error': max(errors)})
    for name, obj in objects.items():
        if physical(obj) != raw_before[name]:
            raise ValueError('Unexpected raw native field mutation: '+name)
        expected_modifiers = modifier_before[name]
        if name in NAMES:
            expected_modifiers = json.loads(json.dumps(expected_modifiers))
            for item in expected_modifiers:
                if item['type'] == 'BEVEL':
                    item['segments'] = 1
        if modifier_state(obj) != expected_modifiers:
            raise ValueError('Undeclared modifier mutation: '+name)
    saving = sum(r['triangles_before']-r['triangles_after'] for r in results)
    if saving != 1266:
        raise ValueError('Unexpected measured triangle delta')
    return {'status': 'passed', 'results': results, 'triangle_saving': saving, 'oriented_native_correspondence': correspondence_proofs,
        'raw_native_meshes_checked': len(objects), 'raw_geometry_uv_normals_transforms_unchanged': True,
        'only_modified_property': 'BEVEL.segments2ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢1 on13 exact targets',
        'uv_limit': 'Raw UVs exact; evaluated UV rounding is separately retained. No exact evaluated-UV or shipping-byte claim.',
        'source_saved': False, 'rotors_changed': False, 'human_approval_reference': None}
