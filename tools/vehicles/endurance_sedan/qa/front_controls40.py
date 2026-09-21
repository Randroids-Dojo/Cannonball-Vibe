"""Adversarial controls against an already-open, caller-bound current40 source.

No file writes, source opening, native launch, save, export or render occurs here.
The caller owns phase observations, source-byte verification and report emission.
This module must not be run against fabricated context/provenance dictionaries.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path


GROUPS = (
    'held-digests', 'legacy-provenance', 'current-panels', 'feature-domains',
    'complete-Trim', 'lower-fields', 'lower-members', 'profile-budget',
)
PANELS = ('LOD0_FrontBumper', 'LOD0_FrontFender_L', 'LOD0_FrontFender_R')
EXPECTED_NAMES = (
    'packet-coherent-rehash-held-digest', 'context-coherent-rehash-held-digest',
    'absent-actual-legacy-observation', 'coherent-stale-checkpoint-observation',
    'legacy-status-without-strict-proof', 'stale-regenerated-request', 'old-guide-contract',
    'legacy-schema-with-current-source',
    'missing-current-native-left-fender', 'missing-requested-right-fender',
    'actual-current-left-fender-corner', 'actual-current-right-fender-corner',
    'actual-current-left-fender-cache', 'actual-current-right-fender-cache',
    'missing-named-feature-family', 'omitted-actual-Trim-source-triangle',
    'missing-current-fender-arch-domain', 'omitted-protected-vertex', 'duplicate-feature-triangle',
    'actual-lower1-Trim-omission', 'actual-lower2-Trim-omission',
    *(f'actual-lower{level}-{name}-corner' for level in (1, 2) for name in PANELS),
    'actual-lower1-left-fender-UV', 'actual-lower2-right-fender-position',
    'missing-lower1-left-fender', 'missing-lower2-right-fender', 'duplicate-lower2-bumper',
    'profile-omitted-level', 'profile-raised-LOD0-ceiling', 'profile-raised-total-ceiling',
    'forged-LOD0-budget-claim', 'forged-total-budget-claim',
)


def _require(value, message):
    if not value:
        raise ValueError(message)


class ControlFailure(ValueError):
    """Carries the completed inventory if any rejection hits the wrong predicate."""
    def __init__(self, message, inventory):
        super().__init__(message)
        self.inventory = inventory


def _reject(rows, group, name, callback, expected, witness):
    _require(group in GROUPS and name in EXPECTED_NAMES, 'Unknown private control')
    try:
        callback()
    except ValueError as error:
        observed = str(error)
        right = any(text in observed for text in expected)
        rows.append({'group': group, 'name': name,
                     'status': 'rejected' if right else 'wrong-predicate',
                     'observed_exception': type(error).__name__, 'observed_predicate': observed,
                     'required_predicates': list(expected), 'witness': witness})
    else:
        rows.append({'group': group, 'name': name, 'status': 'unexpectedly-accepted',
                     'required_predicates': list(expected), 'witness': witness})


def _packet(core, digest):
    return {'core': core, 'sha256': digest(core)}


def _front_copy(context):
    result = dict(context)
    for key in ('expected', 'observed', 'profile', 'packet', 'input_files'):
        result[key] = deepcopy(context[key])
    result.pop('current_native_chain_proof', None)
    return result


@contextmanager
def _private_mesh(obj):
    """Keep the actual object identity, replace only its disposable mesh pointer."""
    import bpy
    original = obj.data
    private = original.copy()
    try:
        obj.data = private
        bpy.context.view_layer.update()
        yield private
    finally:
        obj.data = original
        bpy.context.view_layer.update()
        _require(private.users == 0, 'Private control mesh unexpectedly acquired another owner')
        bpy.data.meshes.remove(private)
        _require(obj.data == original, 'Control did not restore original mesh pointer')


def _flip_corner(mesh, loop):
    normals = [tuple(value.vector) for value in mesh.corner_normals]
    old = normals[loop]
    normals[loop] = tuple(-value for value in old)
    mesh.normals_split_custom_set(normals)
    mesh.update()
    actual = tuple(mesh.corner_normals[loop].vector)
    _require(sum(a * b for a, b in zip(old, actual)) < -.9,
             'Native counterexample did not actually reverse its selected corner')
    return {'loop': loop, 'before': list(old), 'after': list(actual)}


def _find_protected_triangle(mesh, reference, key_function):
    mesh.calc_loop_triangles()
    held = reference['triangles'][0]
    matches = [triangle for triangle in mesh.loop_triangles
               if key_function([tuple(mesh.vertices[index].co) for index in triangle.vertices]) == held['key']]
    _require(len(matches) == 1, 'Cannot locate actual protected lower triangle for control')
    return matches[0], held


def run(context, observations, bundle):
    """Return eight named negative groups derived from real current/final inputs.

    Invoke only after successful distance-fields on the same open source. No
    previous report payload is installed as geometry. All mutations are local
    dictionary copies or temporary actual-object mesh copies restored in finally.
    An exception is a failure, never an accepted control, unless _reject records
    its required ValueError predicate. The caller must retain lock.verify() and
    source-byte equality before and after this callable.
    """
    import bpy
    from endurance_sedan import distance_lod, source_generation as records
    from endurance_sedan.distance_lod import api, binding, recipe, front_feature40 as feature
    from endurance_sedan.distance_lod.front_feature_base import _key
    from endurance_sedan.front_finish40 import native, verification
    from endurance_sedan.qa import distance_lod as checker
    from endurance_sedan.qa.front_finish_report import COMPANION, NAMES

    _require(tuple(NAMES) == PANELS, 'Current panel API changed; explicitly rebind controls')
    _require((bpy.app.version, bpy.app.build_hash.decode()) == ((5, 1, 2), 'ec6e62d40fa9'),
             'Pinned actual native Blender required')
    front = context['front_context']
    _require(front.get('current_revision40') is True, 'Current40-only controls cannot run on legacy source')
    observation = observations.get('front_finish')
    _require(type(observation) is dict, 'Real completed legacy observation required')
    held_context = context['context_digest']
    held_observation = records.digest(observation)
    held_packet = front['expected']['field_core_sha256']
    packet = front['packet']
    root = Path(verification.__file__).resolve().parents[4]
    proof_present = 'current_native_chain_proof' in front
    proof_before = front.get('current_native_chain_proof')
    front_values = ('expected', 'observed', 'input_files', 'profile', 'packet',
                    'expected_binding_digest', 'construction_path', 'current_revision40')
    before_inputs = {
        'observations': records.digest(observations), 'bundle': records.digest(bundle),
        'construction': records.digest(context['construction']), 'packet': records.digest(packet),
        'profile': records.digest(context['profile']), 'capture': records.digest(context['capture']),
        'front_values': records.digest({key: front[key] for key in front_values}),
    }
    scene_before = checker.objects(api, recipe, context['modifier_capture'])
    material_before = {name: records.digest(context['material_capture'](bpy.data.objects[name].data))
                       for name, value in scene_before.items() if value['type'] == 'MESH'}
    mesh_ids_before = {mesh.as_pointer() for mesh in bpy.data.meshes}
    cache_before = dict(feature._cache)
    rows = []
    result = None
    try:
        feature._cache.clear()
        current = distance_lod.verify_current_front(context=context, expected_context_digest=held_context)
        _require(current['proof']['members'] == list(NAMES), 'Baseline did not prove all current panels')
        rebuilt = verification.make_packet(context['construction'], front['expected']['source_sha256'],
                                            root, observation, held_observation)
        _require(rebuilt == packet, 'Actual held observation does not reproduce the current packet')
        references = {name: feature.capture(bpy.data.objects[name], context=front) for name in NAMES}
        lower = [bpy.data.objects[value['name']] for value in bundle['payload']['meshes']]
        by_pair = {}
        for level in (1, 2):
            for name in NAMES:
                matches = [obj for obj in lower if obj.parent is not None and
                           obj.parent.name == 'Visual_LOD' + str(level) and
                           json.loads(obj['source_components']) == [name]]
                _require(len(matches) == 1, 'Real current lower panel absent or duplicate')
                by_pair[level, name] = matches[0]
        lower_positive = {obj.name: feature.verify(obj, references[name])
                          for (level, name), obj in by_pair.items()}
        proof, payload = bundle['proof'], bundle['payload']
        expected_members = proof['base_before_tire_replacement']['base_proof']['retained_source_members']
        def live(objects=lower):
            return api.verify_live(bpy.data.collections['Asset'], objects, payload['lod_construction'],
                                   original_names=set(bundle['material_before']), expected_members=expected_members,
                                   geometry=context['geometry'], hook=recipe)
        baseline_live = live()
        _require(baseline_live == proof['live'] and baseline_live['budget']['passed'] is True,
                 'Successful actual final native budget required before adversarial controls')

        # A coherent internal rehash is insufficient when the caller holds the old digest.
        altered = deepcopy(packet['core'])
        altered['current_source_sha256'] = '0' * 64
        bad = _packet(altered, records.digest)
        _require(bad['sha256'] != held_packet, 'Counterexample did not change packet content')
        _reject(rows, 'held-digests', 'packet-coherent-rehash-held-digest',
                lambda: verification.verify_packet(bad, expected_packet_digest=held_packet),
                ('caller-held digest',), {'held': held_packet, 'internally_rehashed': bad['sha256']})
        altered_context = dict(context)
        altered_front = _front_copy(front)
        altered_front['expected']['field_core_sha256'] = bad['sha256']
        altered_front['observed'] = deepcopy(altered_front['expected'])
        altered_front['expected_binding_digest'] = records.digest(altered_front['expected'])
        altered_front['packet'] = bad
        altered_context['front_context'] = altered_front
        altered_context['packet'] = bad
        altered_context['capture'] = {**context['capture'], 'front_binding_digest': altered_front['expected_binding_digest']}
        altered_context['context_digest'] = records.digest(altered_context['capture'])
        _reject(rows, 'held-digests', 'context-coherent-rehash-held-digest',
                lambda: binding.validate_context(altered_context, held_context),
                ('Caller distance-LOD context digest differs',),
                {'held': held_context, 'internally_rehashed': altered_context['context_digest']})

        def make(obs, construction=context['construction'], expected=None):
            return verification.make_packet(construction, front['expected']['source_sha256'], root,
                                            obs, held_observation if expected is None else expected)
        _reject(rows, 'legacy-provenance', 'absent-actual-legacy-observation', lambda: make(None),
                ('caller-held actual legacy observation',), {'held_observation': held_observation})
        obs = deepcopy(observation)
        obs['checkpoint']['sha256'] = '0' * 64
        _reject(rows, 'legacy-provenance', 'coherent-stale-checkpoint-observation',
                lambda: make(obs, expected=records.digest(obs)), ('another checkpoint/request',),
                {'mutation': 'checkpoint SHA changed; observation digest coherently recomputed; actual held files unchanged'})
        obs = deepcopy(observation)
        obs['legacy_proof']['status'] = 'passed'
        _reject(rows, 'legacy-provenance', 'legacy-status-without-strict-proof',
                lambda: make(obs, expected=records.digest(obs)), ('strict completed legacy proof',),
                {'mutation': 'generic passed status replaces strict actual legacy proof'})
        obs = deepcopy(observation)
        obs['regenerated_request_sha256'] = '0' * 64
        _reject(rows, 'legacy-provenance', 'stale-regenerated-request',
                lambda: make(obs, expected=records.digest(obs)), ('not independently regenerated',),
                {'mutation': 'regeneration digest replaced, all actual source/request bytes unchanged'})
        construction = deepcopy(context['construction'])
        construction[COMPANION]['contract']['legacy_guide'] = {'schema': 'qa-rejected-old-guide'}
        _reject(rows, 'legacy-provenance', 'old-guide-contract',
                lambda: make(observation, construction=construction), ('actual-input observation differs',),
                {'held_guide_digest': records.digest(observation['contract']['legacy_guide'])})
        altered = deepcopy(packet['core'])
        altered['schema'] = 'current-finite-front-source-binding36.v1'
        bad = _packet(altered, records.digest)
        _reject(rows, 'legacy-provenance', 'legacy-schema-with-current-source',
                lambda: verification.verify_packet(bad, expected_packet_digest=bad['sha256']),
                ('Wrong current guide front policy',),
                {'mutation': 'old schema with current source and coherent hash; structural validation, not new provenance'})

        actual = {name: native.capture(bpy.data.objects[name]) for name in NAMES}
        requested = packet['core']['requested']['parts']
        absent = dict(actual)
        absent.pop(NAMES[1])
        _reject(rows, 'current-panels', 'missing-current-native-left-fender',
                lambda: native.verify_fields(absent, requested), ('Incomplete current front native field domain',),
                {'missing': NAMES[1], 'actual_triangle_count': len(actual[NAMES[1]]['triangles'])})
        absent_request = dict(requested)
        absent_request.pop(NAMES[2])
        _reject(rows, 'current-panels', 'missing-requested-right-fender',
                lambda: native.verify_fields(actual, absent_request), ('Incomplete current front native field domain',),
                {'missing': NAMES[2], 'actual_triangle_count': len(actual[NAMES[2]]['triangles'])})
        for name, side in zip(NAMES[1:], ('left', 'right'), strict=True):
            obj = bpy.data.objects[name]
            with _private_mesh(obj) as mesh:
                witness = _flip_corner(mesh, actual[name]['triangle_loops'][0][0])
                changed = dict(actual)
                changed[name] = native.capture(obj)
                _reject(rows, 'current-panels', f'actual-current-{side}-fender-corner',
                        lambda: native.verify_fields(changed, requested), ('Complete affine field guard failed',),
                        {'source': name, **witness})
                _reject(rows, 'current-panels', f'actual-current-{side}-fender-cache',
                        lambda: feature.bind(obj, _front_copy(front)), ('Actual current front native fields differ',),
                        {'source': name, 'baseline_cache_warmed': True, **witness})

        domains = packet['core']['requested']['feature_domains']
        def measure(name, domain):
            return feature._capture_domain(bpy.data.objects[name], domain,
                binding=front['expected'], binding_digest=front['expected_binding_digest'],
                expected_materials=actual[name]['materials'])
        for name in NAMES:
            _require(measure(name, domains[name]) == references[name],
                     'Unbound feature measurement differs from bind-first real baseline')
        domain = deepcopy(domains[NAMES[0]])
        domain['feature_triangles'].pop('shoulder_lamp')
        _reject(rows, 'feature-domains', 'missing-named-feature-family', lambda: measure(NAMES[0], domain),
                ('Incomplete named current front feature families',), {'missing': 'shoulder_lamp'})
        trim_index = next(index for index, material in enumerate(actual[NAMES[0]]['triangle_materials'])
                          if actual[NAMES[0]]['materials'][material] == 'Material_Trim')
        domain = deepcopy(domains[NAMES[0]])
        domain['feature_triangles']['trim_and_material_boundary_fans'].remove(trim_index)
        _reject(rows, 'feature-domains', 'omitted-actual-Trim-source-triangle', lambda: measure(NAMES[0], domain),
                ('Trim or material-boundary incident fan was omitted',),
                {'source_triangle': trim_index, 'actual_material': 'Material_Trim'})
        domain = deepcopy(domains[NAMES[1]])
        domain['feature_triangles']['arch_returns'] = []
        _reject(rows, 'feature-domains', 'missing-current-fender-arch-domain', lambda: measure(NAMES[1], domain),
                ('Missing current fender arch/shoulder features',), {'source': NAMES[1]})
        domain = deepcopy(domains[NAMES[2]])
        omitted_vertex = domain['protected_vertex_indices'].pop()
        _reject(rows, 'feature-domains', 'omitted-protected-vertex', lambda: measure(NAMES[2], domain),
                ('complete feature closure differs',), {'source': NAMES[2], 'omitted_vertex': omitted_vertex})
        domain = deepcopy(domains[NAMES[2]])
        family = next(key for key, values in domain['feature_triangles'].items() if values)
        domain['feature_triangles'][family].append(domain['feature_triangles'][family][0])
        _reject(rows, 'feature-domains', 'duplicate-feature-triangle', lambda: measure(NAMES[2], domain),
                ('Invalid/duplicate current front feature indices',), {'source': NAMES[2], 'family': family})

        for level in (1, 2):
            obj = by_pair[level, NAMES[0]]
            with _private_mesh(obj) as mesh:
                polygon = next(p for p in mesh.polygons if mesh.materials[p.material_index].name == 'Material_Trim')
                previous = polygon.material_index
                paint = next(i for i, material in enumerate(mesh.materials) if material.name == 'Material_Paint')
                polygon.material_index = paint
                _reject(rows, 'complete-Trim', f'actual-lower{level}-Trim-omission',
                        lambda: feature.verify(obj, references[NAMES[0]]),
                        ('lost complete actual Trim geometry',),
                        {'object': obj.name, 'polygon': polygon.index, 'old_slot': previous, 'new_slot': paint})

        for level in (1, 2):
            for name in NAMES:
                obj = by_pair[level, name]
                with _private_mesh(obj) as mesh:
                    triangle, held = _find_protected_triangle(mesh, references[name], _key)
                    witness = _flip_corner(mesh, triangle.loops[0])
                    _reject(rows, 'lower-fields', f'actual-lower{level}-{name}-corner',
                            lambda: feature.verify(obj, references[name]),
                            ('Protected original front field exceeds .025 degree native guard',),
                            {'object': obj.name, 'source_triangle': held['source_triangle'], **witness})
        obj = by_pair[1, NAMES[1]]
        with _private_mesh(obj) as mesh:
            triangle, held = _find_protected_triangle(mesh, references[NAMES[1]], _key)
            loop = triangle.loops[0]
            old_uv = list(mesh.uv_layers.active.data[loop].uv)
            mesh.uv_layers.active.data[loop].uv[0] += .0001
            _reject(rows, 'lower-fields', 'actual-lower1-left-fender-UV',
                    lambda: feature.verify(obj, references[NAMES[1]]), ('Protected front UV changed',),
                    {'object': obj.name, 'loop': loop, 'before': old_uv,
                     'after': list(mesh.uv_layers.active.data[loop].uv)})
        obj = by_pair[2, NAMES[2]]
        with _private_mesh(obj) as mesh:
            triangle, held = _find_protected_triangle(mesh, references[NAMES[2]], _key)
            vertex = triangle.vertices[0]
            old_position = list(mesh.vertices[vertex].co)
            mesh.vertices[vertex].co.x += .001
            mesh.update()
            _reject(rows, 'lower-fields', 'actual-lower2-right-fender-position',
                    lambda: feature.verify(obj, references[NAMES[2]]),
                    ('Lost, displaced or ambiguous protected front triangle',),
                    {'object': obj.name, 'vertex': vertex, 'before': old_position,
                     'after': list(mesh.vertices[vertex].co)})

        for level, name, control in ((1, NAMES[1], 'missing-lower1-left-fender'),
                                     (2, NAMES[2], 'missing-lower2-right-fender')):
            missing = by_pair[level, name]
            candidates = [obj for obj in lower if obj != missing]
            _reject(rows, 'lower-members', control, lambda: live(candidates),
                    ('Unexpected or missing live mesh',),
                    {'omitted_return_member': missing.name, 'original_native_object_still_present': True})
        duplicate = by_pair[2, NAMES[0]]
        _reject(rows, 'lower-members', 'duplicate-lower2-bumper', lambda: live(lower + [duplicate]),
                ('Ambiguous final lower-LOD object inventory',), {'duplicated_actual_member': duplicate.name})

        profile = deepcopy(context['profile'])
        profile['current_front_revision40']['levels'] = [1]
        _reject(rows, 'profile-budget', 'profile-omitted-level',
                lambda: recipe.validate_profile(profile, records.digest(profile)),
                ('current three-panel LOD profile mismatch',), {'levels': [1], 'coherent_profile_digest': True})
        for key, value, name in (('LOD0_triangles', 150001, 'profile-raised-LOD0-ceiling'),
                                  ('all_triangles_including_collision', 200001, 'profile-raised-total-ceiling')):
            profile = deepcopy(context['profile'])
            profile['limits'][key] = value
            _reject(rows, 'profile-budget', name,
                    lambda: recipe.validate_profile(profile, records.digest(profile)),
                    ('Ordinary frozen recipe or mixed-front domain changed', 'LOD recipe guards/ratios changed'),
                    {'limit': key, 'raised_to': value, 'coherent_profile_digest': True})
        for which, name in (('LOD0', 'forged-LOD0-budget-claim'), ('total', 'forged-total-budget-claim')):
            bad_proof = dict(proof, live=deepcopy(proof['live']))
            budget = bad_proof['live']['budget']
            if which == 'LOD0':
                budget['total'] += 150001 - budget['counts']['0']
                budget['counts']['0'] = 150001
            else:
                budget['counts']['2'] += 200001 - budget['total']
                budget['total'] = 200001
            budget['passed'] = True
            _reject(rows, 'profile-budget', name,
                    lambda: checker.verify_result(context, bundle['before'], bundle['material_before'],
                                                  lower, bad_proof, payload),
                    ('Final live replay differs',),
                    {'forged_budget': budget, 'actual_budget': baseline_live['budget'],
                     'scope': 'Corrupted claims over actual generated objects; not a fabricated native over-budget run'})

        _require(len(rows) == len(EXPECTED_NAMES) and {row['name'] for row in rows} == set(EXPECTED_NAMES),
                 'Missing or duplicate private counterexample inventory')
        result = {
            'schema': 'current-front-controls40.v1', 'status': 'passed' if all(r['status'] == 'rejected' for r in rows) else 'failed',
            'selected_current_front': True, 'context_digest': held_context, 'packet_digest': held_packet,
            'observation_digest': held_observation, 'source_sha256': front['expected']['source_sha256'],
            'groups': {group: [r['name'] for r in rows if r['group'] == group] for group in GROUPS},
            'expected_names': list(EXPECTED_NAMES), 'controls': rows, 'negative_count': len(rows),
            'positive_current': current, 'positive_lower_fields': lower_positive,
            'actual_budget': baseline_live['budget'], 'source_saved': False, 'exported': False, 'GPU': False,
            'scope': 'Adversarial source/packet/feature/lower/report controls on actual caller-held generated inputs. Pure feature measurement is tested separately from provenance; production capture remains bind-first. No geometry acceptance or final human approval.',
        }
    finally:
        feature._cache.clear()
        feature._cache.update(cache_before)
        if proof_present:
            front['current_native_chain_proof'] = proof_before
        else:
            front.pop('current_native_chain_proof', None)
        _require(('current_native_chain_proof' in front) == proof_present and
                 (not proof_present or front['current_native_chain_proof'] is proof_before),
                 'Private controls did not restore the caller chain-proof object')
        _require(feature._cache == cache_before,
                 'Private controls did not restore the feature cache')
        after = checker.objects(api, recipe, context['modifier_capture'])
        after_materials = {name: records.digest(context['material_capture'](bpy.data.objects[name].data))
                           for name, value in after.items() if value['type'] == 'MESH'}
        after_inputs = {
            'observations': records.digest(observations), 'bundle': records.digest(bundle),
            'construction': records.digest(context['construction']), 'packet': records.digest(packet),
            'profile': records.digest(context['profile']), 'capture': records.digest(context['capture']),
            'front_values': records.digest({key: front[key] for key in front_values}),
        }
        _require(scene_before == after and material_before == after_materials,
                 'Private controls did not restore every actual native object/field/material')
        _require(mesh_ids_before == {mesh.as_pointer() for mesh in bpy.data.meshes},
                 'Private controls leaked or removed a native mesh datablock')
        _require(before_inputs == after_inputs, 'Private controls changed caller-held input values')
        if result is not None:
            result['restoration'] = {'all_actual_object_fields_and_materials_exact': True,
                'all_mesh_datablock_identities_exact': True, 'held_inputs_exact': True,
                'caller_chain_proof_presence_and_identity_restored': True,
                'feature_cache_restored': True,
                'object_count': len(scene_before), 'mesh_count': len(mesh_ids_before),
                'before_native_digest': records.digest(scene_before), 'after_native_digest': records.digest(after),
                'before_inputs': before_inputs, 'after_inputs': after_inputs}
    if result['status'] != 'passed':
        raise ControlFailure('Current front counterexample was accepted or failed at another predicate', result)
    return result
