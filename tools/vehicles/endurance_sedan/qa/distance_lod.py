"""Independent actual-source/final distance-LOD verification; no source I/O."""
import copy
import bpy
from ..distance_lod import api, recipe
from ..distance_lod.tire import digest, matrix
from ..distance_lod.binding import require

def attr_values(attribute):
    result = []
    for item in attribute.data:
        row = {}
        for prop in item.bl_rna.properties:
            if prop.identifier == 'rna_type' or prop.type not in ('BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'):
                continue
            value = getattr(item, prop.identifier)
            if getattr(prop, 'is_array', False):
                value = list(value)
            elif isinstance(value, set):
                value = sorted(value)
            row[prop.identifier] = value
        result.append(row)
    return {'type': attribute.data_type, 'domain': attribute.domain, 'values': result}

def animation(obj):
    data = obj.animation_data
    if data is None:
        return None
    return {'action': data.action.name if data.action else None,
        'drivers': [{'path': c.data_path, 'index': c.array_index, 'type': c.driver.type,
            'expression': c.driver.expression, 'mute': c.mute,
            'variables': [{'name': v.name, 'type': v.type, 'targets': [
                {'id': t.id.name if t.id else None, 'path': t.data_path,
                 'bone': t.bone_target, 'transform_type': t.transform_type,
                 'transform_space': t.transform_space} for t in v.targets]} for v in c.driver.variables]}
            for c in data.drivers]}

def objects(api, hook, modifier_capture):
    rows = {}
    for obj in bpy.data.objects:
        row = {'type': obj.type, 'parent': obj.parent.name if obj.parent else None,
            'matrix_basis': matrix(obj.matrix_basis), 'matrix_parent_inverse': matrix(obj.matrix_parent_inverse),
            'matrix_world': matrix(obj.matrix_world), 'hide_render': obj.hide_render,
            'hide_viewport': obj.hide_viewport, 'hide_set': obj.hide_get(),
            'rotation_mode': obj.rotation_mode, 'animation': animation(obj),
            'properties': {k: api.json_property(v) for k, v in obj.items()},
            'collections': sorted(c.name for c in obj.users_collection)}
        if obj.type == 'MESH':
            row.update(raw_sha256=digest(hook.raw_fields(obj)),
                attributes_sha256=digest({a.name: attr_values(a) for a in obj.data.attributes}),
                modifier_state=modifier_capture(obj),
                mesh_properties={k: api.json_property(v) for k, v in obj.data.items()},
                material_links=[[s.name, s.link] for s in obj.material_slots],
                vertex_groups=[[g.name, g.lock_weight] for g in obj.vertex_groups],
                vertex_weights=[[[g.group, g.weight] for g in v.groups] for v in obj.data.vertices])
        rows[obj.name] = row
    return rows

def verify_originals(before, after):
    missing = sorted(set(before)-set(after))
    changed = sorted(n for n in before if n in after and before[n] != after[n])
    if missing or changed:
        raise ValueError('Original complete native inventory changed: ' + str({'missing': missing, 'changed': changed}))
    return {'original_objects': len(before), 'original_meshes': sum(r['type'] == 'MESH' for r in before.values()),
        'original_inventory_sha256': digest(before), 'current_original_inventory_sha256': digest({n: after[n] for n in before}),
        'additional_objects': sorted(set(after)-set(before)), 'changed': changed}

def capture_originals(context):
    before = objects(api, recipe, context['modifier_capture'])
    materials = {name: digest(context['material_capture'](bpy.data.objects[name].data))
        for name, row in before.items() if row['type'] == 'MESH'}
    return before, materials


def verify_result(context, before, material_before, lower, proof, payload):
    """Re-extract complete live native fields and shells, not report statuses."""
    from ..distance_lod import front_feature_current as feature, glass_field
    from ..distance_lod import selective_lod
    raw = {obj.name: recipe.raw_fields(obj) for obj in lower}
    require({name: digest(row) for name, row in raw.items()} == proof['final_after_repair_hashes'],
            'Final complete native payload hash differs')
    expected_members = proof['base_before_tire_replacement']['base_proof']['retained_source_members']
    live = api.verify_live(bpy.data.collections['Asset'], lower, payload['lod_construction'],
        original_names=set(material_before), expected_members=expected_members,
        geometry=context['geometry'], hook=recipe)
    require(live == proof['live'], 'Final live replay differs')
    expected_rows = {row['name']: row for row in payload['meshes']}
    require(set(expected_rows) == set(raw) and len(expected_rows) == len(payload['meshes']),
            'Complete payload mesh inventory differs')
    independent_shells = []
    maximum_unit_error = 0.
    for obj in sorted(lower, key=lambda item: item.name):
        actual = recipe.evaluated_row(obj, context['geometry'])
        require(actual == expected_rows[obj.name], 'Actual final evaluated geometry/UV/normal payload differs: ' + obj.name)
        maximum_unit_error = max(maximum_unit_error, actual['raw_maximum_normal_unit_error'])
        shell = context['shell_certificate'](selective_lod.native_row(obj))
        require(shell['status'] == 'passed', 'Independent final indexed shell failed: ' + obj.name)
        independent_shells.append(shell)
    reference = feature.capture(bpy.data.objects['LOD0_FrontBumper'], context=context['front_context'])
    front_fields = {obj.name: feature.verify(obj, reference) for obj in lower
        if obj.name in ('LOD1_MixedProtectedFront', 'LOD2_MixedProtectedFront')}
    require(len(front_fields) == 2, 'Missing complete current protected front outputs')
    glass_proofs = proof['base_before_tire_replacement']['base_proof']['glass_fields']
    glass_fields = {}
    for witness in glass_proofs:
        matches = [obj for obj in lower if obj.parent.name == witness['parent']
            and recipe.json.loads(obj['source_components']) == [witness['source']]]
        require(len(matches) == 1, 'Missing or duplicate current pane member')
        obj = matches[0]
        glass_fields[obj.name] = glass_field.verify_output(obj, witness, digest(witness))
    require(len(glass_fields) == 4, 'Missing complete current pane outputs')
    after = objects(api, recipe, context['modifier_capture'])
    metadata_changes = {}
    adjusted = copy.deepcopy(before)
    for name in before:
        for key in ('lod_index', 'maximum_lod'):
            old = before[name]['properties'].get(key)
            new = after[name]['properties'].get(key)
            if old != new:
                require(before[name]['type'] == 'MESH', 'Unexpected nonmesh metadata change')
                require((key == 'lod_index' and new == 0) or
                    (key == 'maximum_lod' and new == 0 and name in
                        proof['base_before_tire_replacement']['base_proof']['actual_maximum_lod_zero']),
                    'Unexpected original distance-eligibility metadata change')
                metadata_changes.setdefault(name, {})[key] = {'before': old, 'after': new}
                adjusted[name]['properties'][key] = new
    correspondence = verify_originals(adjusted, after)
    require(material_before == {name: digest(context['material_capture'](bpy.data.objects[name].data))
        for name in material_before}, 'Original material response changed')
    return {'live': live, 'source_correspondence': correspondence,
        'metadata_changes': metadata_changes, 'original_before_digest': digest(before),
        'original_after_digest': digest({name: after[name] for name in before}),
        'independent_shells': independent_shells, 'front_fields': front_fields, 'glass_fields': glass_fields,
        'raw_normal_max': maximum_unit_error, 'final_inventory': after,
        'scope': 'Complete original native fields and actual final members, indexed shells, materials, UVs, normals and budget; no assembly/visual/export acceptance.'}
