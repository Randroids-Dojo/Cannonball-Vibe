"""Portable actual-source LOD construction hook; no source I/O, saves or exports.

The caller binds the current source/spec/helper bytes. Geometry always comes
from the native input objects, never from a report payload. Use before LOD0
export batching, once in a clean native scene with no existing lower LODs.
"""
import hashlib
import json
import math
import sys

import bpy


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load(name):
    from . import cabin_policy, lod_paint, selective_lod, front_feature_current
    from . import front_feature_base, front_builder, glass_field
    from .. import corner_encoding
    modules = {'cabin_policy': cabin_policy, 'lod_paint': lod_paint,
        'selective_lod': selective_lod, 'front_feature_mixed': front_feature_current,
        'front_feature': front_feature_base, 'front_builder_mixed': front_builder,
        'glass_field': glass_field, 'codec': corner_encoding}
    if name not in modules:
        raise ValueError('Unknown distance-LOD package dependency: ' + name)
    return modules[name]


def raw_fields(obj):
    mesh = obj.data
    return {'vertices': [list(v.co) for v in mesh.vertices],
        'edges': [list(e.vertices) for e in mesh.edges], 'sharp': [e.use_edge_sharp for e in mesh.edges],
        'polygons': [list(p.vertices) for p in mesh.polygons], 'polygon_materials': [p.material_index for p in mesh.polygons],
        'normals': [list(n.vector) for n in mesh.corner_normals],
        'uv': {u.name: [list(v.uv) for v in u.data] for u in mesh.uv_layers},
        'materials': [m.name if m else None for m in mesh.materials], 'smooth': [p.use_smooth for p in mesh.polygons],
        'matrix': [list(r) for r in obj.matrix_world], 'parent': obj.parent.name if obj.parent else None,
        'modifier_types': [m.type for m in obj.modifiers]}


def evaluated_row(obj, geometry):
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        mesh.calc_loop_triangles()
        normals = [list(n.vector) for n in mesh.corner_normals]
        if not normals or any(not all(math.isfinite(v) for v in n) or abs(math.hypot(*n) - 1.) > 1e-6 for n in normals):
            raise ValueError('Actual evaluated raw normal guard failed: ' + obj.name)
        if mesh.uv_layers.active is None:
            raise ValueError('Actual evaluated UV inventory missing: ' + obj.name)
        if any(not math.isfinite(value) for layer in mesh.uv_layers for v in layer.data for value in v.uv):
            raise ValueError('Actual evaluated UV nonfinite: ' + obj.name)
        return {'name': obj.name, 'vertices': [list(v.co) for v in mesh.vertices],
            'triangles': [list(t.vertices) for t in mesh.loop_triangles], 'triangle_loops': [list(t.loops) for t in mesh.loop_triangles],
            'normals': normals, 'uv': {u.name: [list(v.uv) for v in u.data] for u in mesh.uv_layers},
            'triangle_materials': [t.material_index for t in mesh.loop_triangles],
            'smooth': [p.use_smooth for p in mesh.polygons], 'matrix_world': [list(r) for r in obj.matrix_world],
            'materials': [m.name if m else None for m in mesh.materials], 'parent': obj.parent.name if obj.parent else None,
            'source_components': json.loads(obj.get('source_components', '[]')),
            'raw_maximum_normal_unit_error': max(abs(math.hypot(*n) - 1.) for n in normals),
            'counts': geometry.evaluated_counts(obj)}
    finally:
        evaluated.to_mesh_clear()


def _validate_base_profile(profile, expected_digest):
    if digest(profile) != expected_digest or profile.get('schema') != 'p1-018-distance-lod-mixed-front29-v1':
        raise ValueError('Caller-locked LOD profile mismatch')
    baseline = dict(profile)
    domain = baseline.pop('mixed_front', None)
    baseline['schema'] = 'p1-018-distance-lod-recipe91-v1'
    if digest(baseline) != '095b9b08d7dd8fe72e7f762b194f016eeaa824bfa48172ba529e8a519de864f2' or domain != load('front_feature_mixed').DOMAIN:
        raise ValueError('Ordinary frozen recipe or mixed-front domain changed')
    expected = {'LOD0_triangles': 150000, 'all_triangles_including_collision': 200000, 'materials': 32,
        'raw_normal_unit_error': 1e-6, 'native_normal_field_degrees': .025, 'whole_face_coverage_m': 1e-6, 'UV_error': 1e-6}
    if profile['limits'] != expected or profile['paint_requested_ratio'] != .065 or profile['ordinary_LOD1_ratio'] != .23 or profile['ordinary_LOD2_ratio'] != .065:
        raise ValueError('LOD recipe guards/ratios changed')
    additions = profile['maximum_LOD_zero_additions']
    if len(additions) != 88 or len(set(additions)) != 88 or not all(isinstance(n, str) and n.startswith('LOD0_') for n in additions):
        raise ValueError('Exact88 declared omission additions required')
    keys = {tuple(k) for k in profile['selective_additions']}
    if len(keys) != 7 or len(profile['selective_additions']) != 7:
        raise ValueError('Exact seven selective additions required')
    if profile['field_panes'] != ['LOD0_Windshield', 'LOD0_Backlight'] or profile['front_separate'] is not True:
        raise ValueError('Required independent native field components missing')
    if profile['component_ratio_overrides'] != {f'LOD0_{seat}JoinedUpholstery': .065 for seat in ('FrontL', 'FrontR', 'RearL', 'RearR')}:
        raise ValueError('Measured four-upholstery-body ratio inventory changed')


def _validate_repaired_profile(profile, expected_digest):
    if digest(profile) != expected_digest or profile.get('schema') != 'p1-018-distance-lod-mixed-front29-repaired-v1':
        raise ValueError('Caller-locked repaired LOD profile mismatch')
    baseline = dict(profile)
    repairs = baseline.pop('selective_shell_repair_additions', None)
    if repairs != [[2, 'Light_Head_FR', 'Material_Headlight']]:
        raise ValueError('Unreviewed shell repair inventory')
    baseline['schema'] = 'p1-018-distance-lod-mixed-front29-v1'
    _validate_base_profile(baseline, digest(baseline))


def validate_profile(profile, expected_digest):
    if digest(profile) != expected_digest or profile.get('schema') != 'p1-018-distance-lod-cabin29-v1':
        raise ValueError('Caller-locked cabin LOD profile mismatch')
    from .binding import validate_domain_profiles
    validate_domain_profiles(profile)
    baseline = dict(profile)
    for key in ('current_front_protection', 'current_glass', 'distant_tire'):
        baseline.pop(key)
    cabin = baseline.pop('cabin_lod1', None)
    load('cabin_policy').validate(cabin)
    baseline['schema'] = 'p1-018-distance-lod-mixed-front29-repaired-v1'
    _validate_repaired_profile(baseline, digest(baseline))


def apply(collection, lods, *, package, optimization, geometry, surfaces, shell_certificate,
          profile, expected_profile_digest, inherited_distance_only_names, front_context):
    """Generate, verify and return (objects, report, actual_payload) once.

    A failed attempt leaves its actual native scene for diagnosis. Use a fresh
    process rather than publishing partial geometry or reusing this scene.
    Patched module functions are restored on both success and failure.
    """
    validate_profile(profile, expected_profile_digest)
    if (bpy.app.version, bpy.app.build_hash.decode()) != ((5, 1, 2), 'ec6e62d40fa9'):
        raise ValueError('Pinned official Blender5.1.2 build required')
    if set(lods) != {0, 1, 2} or any(lods[i].name != 'Visual_LOD' + str(i) for i in lods):
        raise ValueError('Exact native three-LOD parent inventory required')
    if any(o.type == 'MESH' and o.name.startswith(('LOD1_', 'LOD2_', 'LOD0_Batch_')) for o in collection.objects):
        raise ValueError('Call once before any existing lower LODs or LOD0 export batches')
    originals = sorted((o for o in collection.objects if o.type == 'MESH' and o.name.startswith('LOD0_') and not o.get('source_preview_only')), key=lambda o: o.name)
    names = {o.name for o in originals}
    if not originals or len(names) != len(originals):
        raise ValueError('Empty/ambiguous current source inventory')
    omitted = set(inherited_distance_only_names) | set(profile['maximum_LOD_zero_additions'])
    if omitted - names:
        raise ValueError('Missing declared current source omission: ' + ', '.join(sorted(omitted - names)))
    required = {'LOD0_FrontBumper', *profile['field_panes'], *profile['component_ratio_overrides']}
    if not required <= names or required & omitted:
        raise ValueError('Missing or omitted protected current source member')
    # Predict the unchanged make_lods eligibility before it writes metadata.
    # This includes preexisting construction-only members and new small parts.
    expected_eligibility = {}
    for obj in originals:
        maximum = obj.get('maximum_lod', 2)
        if obj.name in omitted or max(obj.dimensions) < .080 or any(word in obj.name for word in ('Stitch', 'Piping', 'CushionSeam', 'RotorVane', 'BrakeVane', 'LugBolt', 'ValveStem')):
            maximum = 0
        expected_eligibility[obj.name] = maximum
    cabin = load('cabin_policy')
    cabin.validate_source(originals, profile['cabin_lod1'], expected_eligibility)
    cabin_seen = set()
    before = {o.name: digest(raw_fields(o)) for o in originals}
    before_counts = {o.name: geometry.evaluated_counts(o) for o in originals}
    bad_keys = ('nonmanifold_edges', 'degenerate_triangles', 'duplicate_faces', 'triangulated_nonmanifold_edges',
        'triangulated_duplicate_faces', 'zero_corner_normals', 'nonfinite_corner_normals', 'nonunit_corner_normals')
    if any(any(c[k] for k in bad_keys) for c in before_counts.values()):
        raise ValueError('Actual current source topology/raw normals invalid before LOD construction')
    empties = {o.name: {'parent': o.parent.name if o.parent else None, 'matrix': [list(r) for r in o.matrix_world],
        'properties': {k: v for k, v in o.items() if isinstance(v, (str, int, float, bool))}} for o in collection.objects if o.type == 'EMPTY'}
    paint, selective = load('lod_paint'), load('selective_lod')
    feature, encoder, front_builder, glass = load('front_feature_mixed'), load('codec'), load('front_builder_mixed'), load('glass_field')
    front_reference = feature.capture(bpy.data.objects['LOD0_FrontBumper'], context=front_context)
    ordinary_groups, original_keys = optimization.groups, optimization.SELECTIVE_LOD_GROUPS
    saved_package = {name: getattr(package, name, None) for name in ('lod_paint', 'selective_lod')}
    saved_modules = {package.__name__ + '.' + name: sys.modules.get(package.__name__ + '.' + name) for name in saved_package}
    ordinary_simplify = selective.simplify_group
    additions = {tuple(k) for k in profile['selective_additions']}
    paint_key = (1, 'Visual_LOD0', 'Material_Paint')
    if len(original_keys) != 24 or additions & original_keys or paint_key in original_keys:
        raise ValueError('Unexpected original selective policy; explicit source-policy rebind required')
    expected_paint = sorted(o.name for o in originals if o.parent == lods[0] and expected_eligibility[o.name] >= 1
        and {o.material_slots[i].material.name if o.material_slots[i].material else None
             for i in {p.material_index for p in o.data.polygons}} == {'Material_Paint'})
    if 'LOD0_FrontBumper' in expected_paint or expected_eligibility['LOD0_FrontBumper'] != 2:
        raise ValueError('Mixed current front must remain separate and eligible at both levels')

    def groups(objects, lod_index, target_parent=None):
        result, found = [], 0
        private_inputs = [o for o in objects if o.name != 'LOD0_FrontBumper']
        if len(private_inputs) != len(objects) - 1 or lod_index not in (1, 2):
            raise ValueError('Missing/ambiguous current front exclusion before grouping')
        for key, members in ordinary_groups(private_inputs, lod_index, target_parent):
            if key == ('Visual_LOD' + str(lod_index), 'Material_Paint'):
                if sorted(o.name for o in members) != expected_paint:
                    raise ValueError('Current native paint group changed after input inventory')
                if not members:
                    raise ValueError('Empty remaining fixed paint group')
                found += 1
            result.append((key, members))
        if found != 1:
            raise ValueError('Missing/ambiguous lower-LOD front paint group')
        return result

    def simplify(name, members, parent, target_collection, material, ratio, **kwargs):
        key = (int(name[3]), kwargs['expected_source_parent'], material.name)
        if key == (1, 'Visual_LOD0', 'Material_Leather'):
            kwargs['component_requested_ratios'] = dict(profile['component_ratio_overrides'])
        if key[0] == 1:
            overrides = cabin.component_overrides(key, members, profile['cabin_lod1'], cabin_seen)
            if overrides:
                kwargs['component_requested_ratios'] = dict(kwargs.get('component_requested_ratios', {})) | overrides
        if key == paint_key:
            ratio = profile['paint_requested_ratio']
        return ordinary_simplify(name, members, parent, target_collection, material, ratio, **kwargs)

    try:
        for name, module in (('lod_paint', paint), ('selective_lod', selective)):
            setattr(package, name, module)
            sys.modules[package.__name__ + '.' + name] = module
        optimization.groups = groups
        optimization.SELECTIVE_LOD_GROUPS = original_keys | additions | {paint_key} | {tuple(k) for k in profile['selective_shell_repair_additions']} | {tuple(profile['cabin_lod1']['selective_addition'])}
        selective.simplify_group = simplify
        cabin.make_lods(optimization, package, shell_certificate, collection, lods, omitted, policy=profile['cabin_lod1'], seen=cabin_seen)
        cabin.verify_seen(cabin_seen, profile['cabin_lod1'])
        lower = sorted((o for o in collection.objects if o.type == 'MESH' and o.name.startswith(('LOD1_', 'LOD2_'))), key=lambda o: o.name)
        for obj in lower:
            geometry.repair_triangulation(obj)
        entries = json.loads(bpy.context.scene['lod_construction'])
        fronts, front_proofs = [], []
        for level in (1, 2):
            front, front_proof = front_builder.build(bpy.data.objects['LOD0_FrontBumper'], lods[level], collection,
                feature=feature, encoder=encoder.encode, paint=paint, selective=selective, geometry=geometry, shell_certificate=shell_certificate, reference=front_reference)
            front['source_components'], front['lod_index'] = json.dumps(['LOD0_FrontBumper']), level
            front.hide_render = True
            front.hide_set(True)
            entries.append({'batch': front.name, 'lod': level, 'parent': front.parent.name,
                **feature.material_metadata(front), 'triangles_after': len(front.data.loop_triangles), 'source_component': 'LOD0_FrontBumper',
                'method': 'Separate complete current mixed front; no subsequent rebatch', 'field_proof': json.loads(json.dumps(front_proof, allow_nan=False))})
            lower.append(front)
            fronts.append(front)
            front_proofs.append(front_proof)
        old_panes = [o for o in lower if json.loads(o.get('source_components', '[]')) in [[n] for n in profile['field_panes']]]
        if len(old_panes) != 4 or {(o.parent.name, json.loads(o['source_components'])[0]) for o in old_panes} != {(p.name, n) for p in (lods[1], lods[2]) for n in profile['field_panes']}:
            raise ValueError('Exactly four single-source lower-LOD pane replacements required')
        pane_proofs = []
        for old in old_panes:
            source_name = json.loads(old['source_components'])[0]
            obj, proof = glass.build(bpy.data.objects[source_name], old.parent, collection,
                bake_batch=optimization.bake_batch, surfaces=surfaces, encoder=encoder.encode, certificate=shell_certificate, context=front_context)
            lod = int(old.parent.name[-1])
            obj['lod_index'] = lod
            obj.hide_render = True
            obj.hide_set(True)
            entries = [e for e in entries if e['batch'] != old.name]
            entries.append({'batch': obj.name, 'lod': lod, 'parent': obj.parent.name, 'material': obj.data.materials[0].name,
                'triangles_after': len(obj.data.loop_triangles), 'source_component': source_name,
                'method': 'Retain complete original variable pane field, retessellate only proven constant interiors',
                'components': [{'source_component': source_name, 'vertex_start': 0, 'vertex_count': len(obj.data.vertices),
                    'triangle_start': 0, 'triangle_count': len(obj.data.loop_triangles), 'range_domain': 'Complete final single-source pane'}]})
            lower.remove(old)
            lower.append(obj)
            data = old.data
            bpy.data.objects.remove(old, do_unlink=True)
            if data.users == 0:
                bpy.data.meshes.remove(data)
            pane_proofs.append(proof)
        rows, shells = {}, []
        for obj in sorted(lower, key=lambda o: o.name):
            row = evaluated_row(obj, geometry)
            if any(row['counts'][k] for k in bad_keys):
                raise ValueError('Actual generated topology/normal invalid: ' + obj.name)
            proof = shell_certificate(selective.native_row(obj))
            if proof['status'] != 'passed':
                raise ValueError('Actual generated indexed-shell self invalid: ' + obj.name)
            rows[obj.name] = row
            shells.append(proof)
            print(json.dumps({'stage': 'recipe91-complete-lower-LOD-check', 'name': obj.name, 'status': 'passed'}), flush=True)
        if {e['batch'] for e in entries} != set(rows) or len(entries) != len(rows):
            raise ValueError('Final native LOD construction manifest mismatch')
        actual_members = {str(i): {n for o in lower if int(o['lod_index']) == i for n in json.loads(o['source_components'])} for i in (1, 2)}
        expected_members = {str(i): {o.name for o in originals if i <= expected_eligibility[o.name]} for i in (1, 2)}
        if any(o.get('maximum_lod', 2) != expected_eligibility[o.name] for o in originals):
            raise ValueError('Actual distance metadata disagrees with original input eligibility')
        if actual_members != expected_members:
            raise ValueError('Complete current retained source member inventory failed')
        if any(digest(raw_fields(o)) != before[o.name] for o in originals):
            raise ValueError('Original LOD0 physical/UV/normal/material/transform field changed')
        empty_after = {o.name: {'parent': o.parent.name if o.parent else None, 'matrix': [list(r) for r in o.matrix_world],
            'properties': {k: v for k, v in o.items() if isinstance(v, (str, int, float, bool))}} for o in collection.objects if o.type == 'EMPTY'}
        if empty_after != empties:
            raise ValueError('Semantic anchors/pivots changed')
        collision = {o.name: geometry.evaluated_counts(o)['triangles'] for o in collection.objects if o.type == 'MESH' and o.name.startswith('CollisionProxy_')}
        if set(collision) != {'CollisionProxy_Body', 'CollisionProxy_Cabin'}:
            raise ValueError('Actual collision triangle inventory missing/ambiguous')
        counts = {str(i): sum(len(r['triangles']) for n, r in rows.items() if n.startswith('LOD' + str(i) + '_')) for i in (1, 2)}
        counts['0'] = sum(c['triangles'] for c in before_counts.values())
        total = sum(counts.values()) + sum(collision.values())
        materials = sorted({m.name for o in originals + lower for m in o.data.materials if m})
        budget = {'passed': counts['0'] <= 150000 and total <= 200000 and len(materials) <= 32,
            'counts': counts, 'actual_collision_triangles': collision, 'total': total, 'material_count': len(materials), 'materials': materials}
        final_front = {obj.name: feature.verify(obj, front_reference) for obj in fronts}
        bpy.context.scene['lod_construction'] = json.dumps(entries, sort_keys=True)
        report = {'status': 'passed-native-construction' if budget['passed'] else 'failed-budget',
            'profile_digest': expected_profile_digest, 'original_LOD0_raw_field_hashes': before,
            'original_LOD0_counts': before_counts, 'complete_current_source_paint_members': expected_paint,
            'original_predicted_eligibility': expected_eligibility, 'declared_omissions': sorted(omitted), 'retained_source_members': {k: sorted(v) for k, v in actual_members.items()},
            'actual_maximum_lod_zero': sorted(o.name for o in originals if o.get('maximum_lod', 2) == 0),
            'complete_indexed_shell_proofs': shells, 'mesh_count': len(rows), 'shell_count': sum(p['shell_count'] for p in shells),
            'budget': budget, 'front_field': final_front, 'front_attempts': front_proofs, 'glass_fields': pane_proofs,
            'unmodified_original_mesh_count': len(originals), 'semantic_empty_fields_unchanged': True,
            'limits': profile['limits'], 'source_saves': 0, 'exports': 0, 'human_approval_reference': None,
            'scope': 'Actual current native LOD construction, raw fields, complete indexed-shell validity and literal composed budget. Cross-shell contacts, final exports, runtime transitions and human acceptance remain separate. Scene lod_index/maximum_lod metadata are intentionally set by the existing distance-eligibility policy; source mesh fields are preserved.'}
        return lower, report, {'meshes': rows, 'lod_construction': entries}
    finally:
        optimization.groups, optimization.SELECTIVE_LOD_GROUPS = ordinary_groups, original_keys
        for name, old in saved_package.items():
            if old is None:
                if hasattr(package, name):
                    delattr(package, name)
            else:
                setattr(package, name, old)
        for name, old in saved_modules.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
