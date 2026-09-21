"""Current-source lower LODs with a complete live-scene inventory.

The caller binds source/constructor/helper bytes independently. This module
does not open/save sources, export files, render, or author missing provenance.
"""
import collections
import copy
import json

import bpy

TARGETS = frozenset({'LOD0_WindshieldSeal', 'LOD0_PillarA_L', 'LOD0_PillarA_R'})
BAD = ('nonmanifold_edges', 'degenerate_triangles', 'duplicate_faces',
       'triangulated_nonmanifold_edges', 'triangulated_duplicate_faces',
       'zero_corner_normals', 'nonfinite_corner_normals', 'nonunit_corner_normals')


def load(name, relative):
    from . import recipe, boundary_field, boundary_subset
    modules = {'recipe': recipe, 'boundary_field': boundary_field, 'boundary_subset': boundary_subset}
    if relative not in modules:
        raise ValueError('Unknown distance-LOD package dependency: ' + relative)
    return modules[relative]


def json_property(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {k: json_property(v) for k, v in value.items()}
    if hasattr(value, 'to_dict'):
        return {k: json_property(v) for k, v in value.to_dict().items()}
    if hasattr(value, 'to_list'):
        return [json_property(v) for v in value.to_list()]
    if isinstance(value, (list, tuple)):
        return [json_property(v) for v in value]
    if isinstance(value, bpy.types.ID):
        return {'id_type': value.bl_rna.identifier, 'name': value.name}
    raise ValueError('Unsupported source property type: ' + type(value).__name__)


def empty_fields():
    result = {}
    for obj in bpy.data.objects:
        if obj.type != 'EMPTY':
            continue
        drivers = []
        if obj.animation_data:
            for curve in obj.animation_data.drivers:
                drivers.append({'path': curve.data_path, 'array_index': curve.array_index,
                    'expression': curve.driver.expression, 'type': curve.driver.type,
                    'variables': [{'name': v.name, 'type': v.type,
                        'targets': [{'id': t.id.name if t.id else None, 'path': t.data_path,
                            'bone': t.bone_target, 'transform_type': t.transform_type,
                            'transform_space': t.transform_space} for t in v.targets]} for v in curve.driver.variables]})
        result[obj.name] = {'parent': obj.parent.name if obj.parent else None,
            'matrix': [list(row) for row in obj.matrix_world],
            'properties': {k: json_property(v) for k, v in obj.items()}, 'drivers': drivers}
    return result


def source_snapshot(raw_capture, modifier_capture):
    return {obj.name: {'raw': raw_capture(obj), 'modifiers': modifier_capture(obj)}
            for obj in bpy.data.objects if obj.type == 'MESH'}


def verify_originals(before, empties, raw_capture, modifier_capture):
    for name, expected in before.items():
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != 'MESH':
            raise ValueError('Original source mesh lost: ' + name)
        actual = {'raw': raw_capture(obj), 'modifiers': modifier_capture(obj)}
        if actual != expected:
            raise ValueError('Original source raw fields/modifiers changed: ' + name)
    if empty_fields() != empties:
        raise ValueError('Original semantic empty/driver fields changed')


def verify_live(collection, lower, entries, *, original_names, expected_members, geometry, hook):
    """Reject ghost comparison objects, stale metadata and incomplete membership."""
    names = [obj.name for obj in lower]
    if len(names) != len(set(names)) or any(obj.type != 'MESH' for obj in lower):
        raise ValueError('Ambiguous final lower-LOD object inventory')
    actual_all = {obj.name for obj in bpy.data.objects if obj.type == 'MESH'}
    if actual_all != set(original_names) | set(names):
        raise ValueError('Unexpected or missing live mesh; possible retained baseline batch')
    asset_meshes = {obj.name for obj in collection.all_objects if obj.type == 'MESH'}
    if not set(names) <= asset_meshes:
        raise ValueError('Final lower component is outside the actual Asset collection')
    actual_lower = {obj.name for obj in collection.all_objects
                    if obj.type == 'MESH' and obj.name.startswith(('LOD1_', 'LOD2_'))}
    if actual_lower != set(names):
        raise ValueError('Live lower-LOD inventory disagrees with returned objects')
    if json.loads(bpy.context.scene.get('lod_construction', 'null')) != entries:
        raise ValueError('Live construction metadata differs from final entries')
    if len(entries) != len(names) or {e.get('batch') for e in entries} != set(names):
        raise ValueError('Final entry/object inventory mismatch')
    by_name = {entry['batch']: entry for entry in entries}
    members = {'1': collections.Counter(), '2': collections.Counter()}
    actual_counts = {}
    for obj in lower:
        level = str(obj.get('lod_index'))
        if level not in members or not obj.name.startswith('LOD' + level + '_'):
            raise ValueError('Final component LOD metadata/name mismatch')
        entry = by_name[obj.name]
        sources = json.loads(obj.get('source_components', 'null'))
        if not isinstance(sources, list) or not sources or any(not isinstance(v, str) for v in sources) or len(sources) != len(set(sources)):
            raise ValueError('Missing or duplicate final source member inventory')
        components = entry.get('components')
        original_components = entry.get('source_components_before_simplification')
        if components is not None:
            if not isinstance(components, list) or not components or len(components) != len(sources) or {c.get('source_component') for c in components} != set(sources):
                raise ValueError('Final component-range semantic inventory mismatch')
            obj.data.calc_loop_triangles()
            occupied_v, occupied_t = set(), set()
            for component in components:
                if any(type(component.get(k)) is not int or component[k] < 0 for k in ('vertex_start', 'triangle_start')) or any(type(component.get(k)) is not int or component[k] <= 0 for k in ('vertex_count', 'triangle_count')):
                    raise ValueError('Invalid final typed component ranges')
                vertices = set(range(component['vertex_start'], component['vertex_start'] + component['vertex_count']))
                triangles = set(range(component['triangle_start'], component['triangle_start'] + component['triangle_count']))
                if occupied_v & vertices or occupied_t & triangles or max(vertices) >= len(obj.data.vertices) or max(triangles) >= len(obj.data.loop_triangles):
                    raise ValueError('Overlapping or out-of-bounds final component ranges')
                if any(not set(obj.data.loop_triangles[i].vertices) <= vertices for i in triangles):
                    raise ValueError('Final component triangle crosses its vertex domain')
                occupied_v |= vertices
                occupied_t |= triangles
            if occupied_v != set(range(len(obj.data.vertices))) or occupied_t != set(range(len(obj.data.loop_triangles))):
                raise ValueError('Incomplete final native component ranges')
        elif original_components is not None:
            if not isinstance(original_components, list) or len(original_components) != len(sources) or {c.get('source_component') for c in original_components} != set(sources) or entry.get('component_range_domain') != 'Original input only; no final component ranges are claimed after batch Decimate':
                raise ValueError('Original-only component provenance mismatch')
        elif sources != [entry.get('source_component')]:
            raise ValueError('Missing final single-source component provenance')
        members[level].update(sources)
        count = geometry.evaluated_counts(obj)
        actual_counts[obj.name] = count
        if any(count[k] for k in BAD):
            raise ValueError('Final live topology/raw-normal failure: ' + obj.name)
        if entry.get('triangles_after') != count['triangles'] or entry.get('lod') != int(level):
            raise ValueError('Stale final triangle or LOD construction metadata')
        if obj.parent is None or entry.get('parent') != obj.parent.name:
            raise ValueError('Final rigid parent differs from construction metadata')
        used = {obj.data.materials[p.material_index].name for p in obj.data.polygons}
        protected_fronts = {
            'LOD' + level + '_MixedProtectedFront': 'LOD0_FrontBumper',
            'LOD' + level + '_ProtectedFrontFender_L': 'LOD0_FrontFender_L',
            'LOD' + level + '_ProtectedFrontFender_R': 'LOD0_FrontFender_R',
        }
        if sources == ['LOD0_FrontBumper'] or obj.name in protected_fronts:
            if obj.name not in protected_fronts or sources != [protected_fronts[obj.name]]:
                raise ValueError('Unexpected current protected-front identity')
            actual_material = hook.load('front_feature_mixed').material_metadata(obj)
            expected_materials = ['Material_Paint', 'Material_Trim'] if sources == ['LOD0_FrontBumper'] else ['Material_Paint']
            if actual_material['materials'] != expected_materials or any(entry.get(k) != v for k, v in actual_material.items()):
                raise ValueError('Final protected front material metadata differs from actual native triangles')
        elif used != {entry.get('material')}:
            raise ValueError('Final material differs from construction metadata')
    expected = {str(level): collections.Counter(names) for level, names in expected_members.items()}
    if members != expected:
        raise ValueError('Complete retained source-member multiplicity failed')
    counts = {'0': 0, '1': 0, '2': 0}
    collision = {}
    material_names = set()
    inventory = []
    for obj in sorted((o for o in collection.all_objects if o.type == 'MESH'), key=lambda o: o.name):
        if obj.get('source_preview_only'):
            inventory.append({'name': obj.name, 'role': 'excluded-source-preview'})
            continue
        value = actual_counts.get(obj.name) or geometry.evaluated_counts(obj)
        if obj.name.startswith('CollisionProxy_'):
            collision[obj.name] = value['triangles']
            role = 'collision'
        elif obj.name.startswith(('LOD0_', 'LOD1_', 'LOD2_')):
            role = obj.name[:4]
            counts[obj.name[3]] += value['triangles']
            material_names.update(material.name for material in obj.data.materials if material)
        else:
            raise ValueError('Unclassified actual Asset mesh: ' + obj.name)
        inventory.append({'name': obj.name, 'role': role, 'triangles': value['triangles']})
    if set(collision) != {'CollisionProxy_Body', 'CollisionProxy_Cabin'}:
        raise ValueError('Missing or ambiguous actual collision inventory')
    total = sum(counts.values()) + sum(collision.values())
    budget = {'counts': counts, 'collision': collision, 'total': total,
              'materials': sorted(material_names), 'material_count': len(material_names),
              'passed': counts['0'] <= 150000 and total <= 200000 and len(material_names) <= 32}
    return {'budget': budget, 'all_actual_asset_meshes': inventory,
            'actual_global_mesh_count': len(actual_all), 'final_lower_mesh_count': len(names),
            'retained_members': {k: sorted(v.elements()) for k, v in members.items()},
            'live_construction_digest': hook.digest(entries)}


def apply(collection, lods, *, package, optimization, geometry, surfaces, shell_certificate,
          profile, expected_profile_digest, inherited_distance_only_names,
          raw_capture, modifier_capture, front_context):
    """Return final native objects/proof/payload with the caller-bound mixed front."""
    hook = load('recipe', 'recipe')
    hook.validate_profile(profile, expected_profile_digest)
    if (bpy.app.version, bpy.app.build_hash.decode()) != ((5, 1, 2), 'ec6e62d40fa9'):
        raise ValueError('Pinned Blender identity required')
    feature, encoder = hook.load('front_feature_mixed'), hook.load('codec')
    front_names = ('LOD0_FrontBumper',)
    if front_context.get('current_revision40') is True:
        from . import front_feature40 as feature
        from ..qa.front_finish_report import NAMES as front_names
    boundary_feature = hook.load('front_feature')
    boundary, subset = load('boundary', 'boundary_field'), load('subset', 'boundary_subset')
    # Bind the reviewed current mixed-front domain before any ordinary LOD mutation.
    for name in front_names:
        feature.capture(bpy.data.objects[name], context=front_context)
    before = source_snapshot(raw_capture, modifier_capture)
    empties = empty_fields()
    lower, base, payload = hook.apply(collection, lods, package=package, optimization=optimization,
        geometry=geometry, surfaces=surfaces, shell_certificate=shell_certificate, profile=profile,
        expected_profile_digest=expected_profile_digest, inherited_distance_only_names=inherited_distance_only_names, front_context=front_context)
    if base['status'] not in {'passed-native-construction', 'failed-budget'}:
        raise ValueError('Base native geometry construction failed')
    # Preserve failed budgets as results while completing actual final counts.
    paint, selective = hook.load('lod_paint'), hook.load('selective_lod')
    entry_by_name = {entry['batch']: entry for entry in payload['lod_construction']}
    superseded = [obj for obj in lower if set(json.loads(obj['source_components'])) & TARGETS]
    if len(superseded) != 4:
        raise ValueError('Expected four mixed private boundary batches; current source policy requires rebind')
    base_hashes = {obj.name: hook.digest(hook.raw_fields(obj)) for obj in lower}
    replacements, new_entries, subset_proofs, boundary_proofs = [], [], [], []
    for old in superseded:
        entry = entry_by_name[old.name]
        obj, new_entry, proof = subset.trim_native_components(old, entry, collection, targets=TARGETS, hook=hook,
            expected_entry_digest=hook.digest(entry), expected_original_digest=base_hashes[old.name])
        replacements.append(obj)
        new_entries.append(new_entry)
        subset_proofs.append(proof)
    for lod in (1, 2):
        for name in sorted(TARGETS):
            source = bpy.data.objects[name]
            if name == 'LOD0_WindshieldSeal':
                obj, proof = boundary.build_seal(source, lods[lod], collection, raw_fields=hook.raw_fields,
                    shell_certificate=shell_certificate, native_row=selective.native_row)
            else:
                obj, proof = boundary.build_pillar(source, lods[lod], collection, feature=boundary_feature, encoder=encoder.encode,
                    paint=paint, selective=selective, geometry=geometry, shell_certificate=shell_certificate)
                reference = proof.pop('original_reference')
                proof['final_source_reference_check'] = boundary_feature.verify(obj, reference)
            obj.hide_render = True
            obj.hide_set(True)
            obj.data.calc_loop_triangles()
            proof.update(lod=lod, batch=obj.name)
            replacements.append(obj)
            boundary_proofs.append(proof)
            new_entries.append({'lod': lod, 'parent': obj.parent.name, 'material': obj.data.materials[0].name,
                'batch': obj.name, 'triangles_after': len(obj.data.loop_triangles),
                'source_component': name, 'method': 'Complete original boundary component; no later rebake',
                'components': [{'source_component': name, 'vertex_start': 0, 'vertex_count': len(obj.data.vertices),
                    'triangle_start': 0, 'triangle_count': len(obj.data.loop_triangles), 'range_domain': 'Complete final single-source component'}]})
    if any(hook.digest(hook.raw_fields(obj)) != base_hashes[obj.name] for obj in lower):
        raise ValueError('Native baseline changed before verified replacement')
    removed_names = sorted(obj.name for obj in superseded)
    unchanged = [obj for obj in lower if obj not in superseded]
    final = unchanged + replacements
    entries = [entry for entry in payload['lod_construction'] if entry['batch'] not in removed_names] + new_entries
    entries.sort(key=lambda entry: entry['batch'])
    for old in superseded:
        if old.name in before or old not in lower:
            raise ValueError('Refusing to remove an original source object')
        data = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
    bpy.context.scene['lod_construction'] = json.dumps(entries, sort_keys=True)
    final_hashes = {obj.name: hook.digest(hook.raw_fields(obj)) for obj in final}
    for obj in list(collection.all_objects):
        if obj.type == 'MESH':
            geometry.repair_triangulation(obj)
    verify_originals(before, empties, raw_capture, modifier_capture)
    if any(hook.digest(hook.raw_fields(obj)) != final_hashes[obj.name] for obj in final):
        raise ValueError('Post-LOD repair changed a certified final component')
    live = verify_live(collection, final, entries, original_names=set(before),
        expected_members=base['retained_source_members'], geometry=geometry, hook=hook)
    old_proofs = {proof['name']: proof for proof in base['complete_indexed_shell_proofs']}
    proofs, rows, reused = [], {}, []
    for obj in sorted(final, key=lambda obj: obj.name):
        rows[obj.name] = hook.evaluated_row(obj, geometry)
        if obj in unchanged and hook.digest(hook.raw_fields(obj)) == base_hashes[obj.name]:
            proof = old_proofs[obj.name]
            reused.append(obj.name)
        else:
            proof = shell_certificate(selective.native_row(obj))
        if proof['status'] != 'passed':
            raise ValueError('Final actual indexed-shell self failed: ' + obj.name)
        proofs.append(proof)
    front_field = {}
    for name in front_names:
        fronts = [obj for obj in final if json.loads(obj['source_components']) == [name]]
        if len(fronts) != 2 or {obj['lod_index'] for obj in fronts} != {1, 2}:
            raise ValueError('Missing current protected front at either level: ' + name)
        front_reference = feature.capture(bpy.data.objects[name], context=front_context)
        front_field.update({obj.name: feature.verify(obj, front_reference) for obj in fronts})
    report = {'status': 'passed-native-construction' if live['budget']['passed'] else 'failed-budget',
        'profile_digest': expected_profile_digest, 'live': live, 'superseded_private_batches_removed': removed_names,
        'original_raw_mesh_modifier_hashes': {name: hook.digest(row) for name, row in before.items()},
        'original_empty_field_digest': hook.digest(empties), 'source_meshes_preserved': len(before),
        'base_proof': base, 'subset_proofs': subset_proofs, 'boundary_proofs': boundary_proofs,
        'final_front_field': front_field, 'final_after_repair_hashes': final_hashes,
        'complete_indexed_shell_proofs': proofs, 'same_process_unchanged_certificates_reused': reused,
        'indexed_shell_count': sum(proof['shell_count'] for proof in proofs),
        'source_saves': 0, 'exports': 0, 'GPU': False, 'human_approval_reference': None,
        'scope': 'Actual unsaved geometry and live inventory; source appearance/physical assembly/export/runtime acceptance separate.'}
    return final, report, {'meshes': rows, 'lod_construction': entries}
