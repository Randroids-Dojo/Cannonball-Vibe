"""Native negative fixtures ported from retained current-front36 controls."""
import copy
import json
import bpy
from ..distance_lod import current_front as current, front_feature_current as feature
from ..distance_lod import api, recipe as hook, glass_field as glass
from ..distance_lod.binding import digest, require


def reject_control(controls, name, call, text):
    try:
        call()
    except ValueError as error:
        require(text in str(error), 'Wrong predicate for ' + name + ': ' + str(error))
        controls.append({'name': name, 'status': 'rejected', 'predicate': str(error), 'expected_substring': text})
    else:
        raise ValueError('Counterexample incorrectly accepted: ' + name)

ORIGINAL_IMPLEMENTATION_SHA256 = {'inventory.py': '59e2fa98e9c8c2ca428fae6337f052dcd13ac7daf81f06787fb0d00007b7f08f', 'native03.py': 'b0b00721efd66ed9f1ddfe2f8f1517a93516c402311c6b0d50d445e036e209ee', 'native04.py': 'e5a0942602150d1ef472fc277f81af3e71f84c039b134a5aed4792ab31ff1291', 'native07.py': 'a7c26d416a10d44ed85f36fe42afa6024378c806a00b5cf0fd8d82b5a6d2e33c', 'native08.py': '21bbfeb13fc6e4aa602310c55151853ba810134938e0df010ba7b8724c94863b', 'controls10.json': '0301f1564ffa61c593bb235d3bf19d3dba4c89a8d7e95b2b624c91ec9ed1df9c'}

def front_controls(e, packet, ctx, controls):
    reject = lambda name, call, text: reject_control(controls, name, call, text)
    source = bpy.data.objects['LOD0_FrontBumper']
    d, core = e['dependencies'], packet['core']
    changed = dict(ctx, expected_binding_digest='0' * 64)
    reject('caller-digest', lambda: feature.bind(source, changed), 'Caller current-front')
    changed = dict(ctx, observed={**ctx['observed'], 'source_sha256': '0' * 64})
    reject('observed-source', lambda: feature.bind(source, changed), 'Observed current source')
    for name, field, value, message in (
        ('source-bytes', 'source_sha256', '0' * 64, 'Loaded source file bytes'),
        ('construction-bytes', 'construction_sha256', '0' * 64, 'construction companion'),
        ('profile-digest', 'profile_sha256', '0' * 64, 'Changed current LOD profile')):
        expected = {**ctx['expected'], field: value}
        changed = dict(ctx, expected=expected, observed=dict(expected), expected_binding_digest=digest(expected))
        reject(name, lambda c=changed: feature.bind(source, c), message)
    files = [dict(r) for r in ctx['input_files']]
    files[-1]['sha256'] = '0' * 64
    expected = {**ctx['expected'], 'input_files_sha256': digest(files)}
    changed = dict(ctx, expected=expected, observed=dict(expected), expected_binding_digest=digest(expected), input_files=files)
    reject('current-helper-byte-hash', lambda: feature.bind(source, changed), 'Current constructor/helper input bytes')
    # Genuine prior packet schema cannot be made current by changing only its source hash.
    old = {'core': {**core, 'schema': 'composed-current-front-field.v1'}}
    old['sha256'] = digest(old['core'])
    reject('historical-normal-only-schema-with-current-source', lambda: current.verify_packet(source, old, d, e['material_capture']), 'Wrong current finite-front packet schema')
    altered = dict(core)
    altered['recorded_current_native'] = {**core['recorded_current_native'], 'normals': []}
    p = {'core': altered, 'sha256': digest(altered)}
    reject('missing-recorded-native-checkpoint', lambda: current.verify_packet(source, p, d, e['material_capture']), 'Actual saved front differs')
    inlet = core['original_inlet_packet']
    c = {**inlet['core'], 'stages': inlet['core']['stages'][:-1]}
    reject('missing-intermediate-stage', lambda: current.check_inlet({'core': c, 'sha256': digest(c)}, d), 'Missing or reordered')
    for name, duplicated in (('omitted-Trim-carrier-owner', False), ('duplicate-Trim-carrier-owner', True)):
        stages = list(inlet['core']['stages'])
        last = stages[-1]
        owners = list(last['proof']['owners'])
        if duplicated:
            owners[1] = owners[0]
        else:
            owners.pop()
        stages[-1] = {**last, 'proof': {**last['proof'], 'owners': owners}}
        c = {**inlet['core'], 'stages': stages}
        reject(name, lambda c=c: current.check_inlet({'core': c, 'sha256': digest(c)}, d), 'Omitted/duplicate complete current Trim/carrier owner')
    for name, mutate, message in (
        ('omitted-lamp-face', lambda p: p['domain']['selected_faces'].pop(), 'Omitted/duplicate finite lamp face'),
        ('ambiguous-lamp-face', lambda p: p['domain']['selected_faces'].__setitem__(1, p['domain']['selected_faces'][0]), 'Omitted/duplicate finite lamp face'),
        ('omitted-free-vertex', lambda p: p['domain']['free_vertices'].pop(), 'Omitted/ambiguous free or fixed'),
        ('omitted-boundary-edge', lambda p: p['domain']['boundary'].pop(), 'Omitted/ambiguous complete finite boundary'),
        ('moved-fixed-vertex', lambda p: p['positions'][p['domain']['fixed_vertices'][0]].__setitem__(0, p['positions'][p['domain']['fixed_vertices'][0]][0]+.001), 'Unexpected moved finite vertex domain'),
        ('zero-target-normal', lambda p: p['targets'].__setitem__(0, [0., 0., 0.]), 'Invalid complete native/target normal field')):
        lamp = copy.deepcopy(core['lamp_plan'])
        mutate(lamp)
        altered = {**core, 'lamp_plan': lamp}
        reject(name, lambda c=altered: current.validate_lamp_domain(c, d), message)
    lamp = copy.deepcopy(core['lamp_plan'])
    selected = set(lamp['domain']['selected_faces'])
    outside = next(t['loops'][0] for t in core['current_native']['triangles'] if t['face'] not in selected)
    lamp['targets'][outside] = [-x for x in lamp['targets'][outside]]
    reject('changed-unowned-normal-target', lambda: current.validate_lamp_domain({**core, 'lamp_plan': lamp}, d), 'Changed original outside finite target')
    for name, key, mutate in (
        ('changed-original-UV', 'uvs', lambda v: v[next(iter(v))][0].__setitem__(0, v[next(iter(v))][0][0] + 1e-4)),
        ('changed-original-material-slot', 'materials', lambda v: v.__setitem__(0, 'Material_Trim'))):
        physical = dict(core['current_physical'])
        physical[key] = copy.deepcopy(physical[key])
        mutate(physical[key])
        reject(name, lambda p=physical: current.validate_lamp_domain({**core, 'current_physical': p}, d), 'Finite lamp changed topology/UV/material/rig/outside physical fields')
    normals = copy.deepcopy(core['current_native']['normals'])
    normals[0] = [-x for x in normals[0]]
    reject('corrupted-actual-native-target', lambda: current.field_rows(core['current_native']['triangles'],
        core['lamp_plan']['targets'], normals, d['support']), 'affine')
    print(json.dumps({'phase': 'front-controls', 'count': len(controls), 'failed': [r for r in controls if r['status'] != 'rejected']}), flush=True)

def supplemental_front_controls(e, packet, historical_packet, controls):
    reject = lambda name, call, text: reject_control(controls, name, call, text)
    source = bpy.data.objects['LOD0_FrontBumper']
    old = copy.deepcopy(historical_packet)
    require(old['core']['schema'] == 'composed-current-front-field.v1', 'Wrong historical negative fixture')
    old['core']['current_source_sha256'] = e['front_context']['expected']['source_sha256']
    old['sha256'] = digest(old['core'])
    reject('actual-historical-packet-with-replaced-source-hash',
        lambda: current.verify_packet(source, old, e['dependencies'], e['material_capture']),
        'Wrong current finite-front packet schema')
    core = packet['core']
    for name, mutate, expected in (
        ('stale-current-triangle-connectivity', lambda c: c['current_native']['triangles'][0]['vertices'].__setitem__(0,
            c['current_native']['triangles'][0]['vertices'][1]), 'Actual saved front differs'),
        ('stale-current-material-connectivity', lambda c: c['current_physical']['polygons'][0].__setitem__(1, -1),
            'Actual saved front physical fields differ')):
        altered = dict(core)
        field = 'current_native' if 'triangle' in name else 'current_physical'
        altered[field] = copy.deepcopy(core[field]); mutate(altered)
        p = {'core': altered, 'sha256': digest(altered)}
        reject(name, lambda p=p: current.verify_packet(source, p, e['dependencies'], e['material_capture']), expected)
    lamp = copy.deepcopy(core['lamp_plan'])
    free = set(lamp['domain']['free_vertices'])
    outside = next(i for i in range(len(lamp['positions'])) if i not in set(lamp['domain']['vertices']))
    moved = lamp['changed_vertices'][0]
    lamp['positions'][moved] = list(lamp['positions_before'][moved])
    lamp['positions'][outside][2] += .001
    lamp['changed_vertices'] = sorted((set(lamp['changed_vertices']) - {moved}) | {outside})
    require(outside not in free, 'Counterexample selected a free position')
    reject('self-consistent-changed-list-moves-unowned-position',
        lambda: current.validate_lamp_domain({**core, 'lamp_plan': lamp}, e['dependencies']),
        'Unexpected moved finite vertex domain')


def glass_source_controls(e, controls):
    reject = lambda name, call, text: reject_control(controls, name, call, text)
    panes = e['construction']['current_surface34']['glass']
    natives = e['construction']['current_surface34']['final_native_fields']
    for name in ('LOD0_Windshield', 'LOD0_Backlight'):
        obj = bpy.data.objects[name]; witness = panes[name]; native = natives[name]
        glass.verify_current_witness(obj, witness, native, e['dependencies'])
        for case, mutate in (
            ('omitted-pane-triangle', lambda p: p['triangles'].pop(0)),
            ('extra-rim-triangle', lambda p: p['triangles'].append(copy.deepcopy(next(r for r in p['triangles'] if r['domain'] == 'rim')))),
            ('relabelled-rim-as-pane', lambda p: next(r for r in p['triangles'] if r['domain'] == 'rim').update(domain='outer'))):
            changed = copy.deepcopy(witness); mutate(changed)
            reject(name + '-' + case, lambda p=changed: glass.verify_current_witness(obj, p, native, e['dependencies']),
                'Missing/extra/changed current pane or rim domain witness')
        changed = copy.deepcopy(witness); changed['plan']['source_plane'][0] += .01
        reject(name + '-wrong-plane', lambda: glass.verify_current_witness(obj, changed, native, e['dependencies']),
            'Wrong independently derived current pane plane')
        changed_native = copy.deepcopy(native); changed_native['materials'][0] = 'Material_Paint'
        reject(name + '-wrong-native-material', lambda: glass.verify_current_witness(obj, witness, changed_native, e['dependencies']),
            'Current complete evaluated pane geometry/UV/normal/material differs')


def final_controls(e, lower, proof, payload, reference, controls):
    reject = lambda name, call, text: reject_control(controls, name, call, text)
    glass_proofs = proof['base_before_tire_replacement']['base_proof']['glass_fields']
    witness = glass_proofs[0]
    matches = [obj for obj in lower if obj.parent.name == witness['parent']
        and json.loads(obj['source_components']) == [witness['source']]]
    require(len(matches) == 1, 'Missing or duplicate current pane member')
    obj = matches[0]
    changed = copy.deepcopy(witness); changed['current_rim_indices'].pop()
    reject('omitted-retained-rim-witness', lambda: glass.verify_output(obj, changed, digest(changed)),
        'Extra/duplicate current retained rim triangle')
    reject('caller-output-witness-digest', lambda: glass.verify_output(obj, witness, '0' * 64),
        'Caller current pane witness digest')
    clone = obj.copy(); clone.data = obj.data.copy(); bpy.data.collections['Asset'].objects.link(clone)
    try:
        old = list(clone.data.uv_layers.active.data[0].uv)
        clone.data.uv_layers.active.data[0].uv[0] += 1e-4
        reject('actual-corrupt-lower-UV', lambda: glass.verify_output(clone, witness, digest(witness)),
            'Current lower pane physical/UV/material field changed')
        clone.data.uv_layers.active.data[0].uv = old
        normals = [list(n.vector) for n in clone.data.corner_normals]; normals[0] = [-v for v in normals[0]]
        clone.data.normals_split_custom_set(normals)
        reject('actual-corrupt-lower-normal', lambda: glass.verify_output(clone, witness, digest(witness)),
            'Current lower pane target-normal guard failed')
    finally:
        mesh = clone.data; bpy.data.objects.remove(clone, do_unlink=True); bpy.data.meshes.remove(mesh)
    glass.verify_output(obj, witness, digest(witness))
    expected_members = proof['base_before_tire_replacement']['base_proof']['retained_source_members']
    original_mesh_names = set(proof['original_raw_mesh_modifier_hashes'])
    def live(entries=payload['lod_construction'], objects=lower):
        return api.verify_live(bpy.data.collections['Asset'], objects, entries, original_names=original_mesh_names,
            expected_members=expected_members, geometry=e['geometry'], hook=hook)
    scene_entry = bpy.context.scene['lod_construction']
    changed = copy.deepcopy(payload['lod_construction'])
    index = next(i for i, row in enumerate(changed) if row['batch'] == 'LOD1_DistantTire_FL')
    changed[index]['components'][0]['vertex_count'] -= 1
    try:
        bpy.context.scene['lod_construction'] = json.dumps(changed, sort_keys=True)
        reject('incomplete-final-component-range', lambda: live(changed), 'vertex domain')
    finally:
        bpy.context.scene['lod_construction'] = scene_entry
    reject('forgotten-live-return-member', lambda: live(objects=lower[1:]), 'Unexpected or missing live mesh')
    ghost = lower[0].copy(); bpy.data.collections['Asset'].objects.link(ghost)
    try:
        reject('forgotten-baseline-comparison-batch', live, 'Unexpected or missing live mesh')
    finally:
        bpy.data.objects.remove(ghost, do_unlink=True)
    front = next(obj for obj in lower if obj.name == 'LOD1_MixedProtectedFront')
    clone = front.copy(); clone.data = front.data.copy(); bpy.data.collections['Asset'].objects.link(clone)
    try:
        clone.data.calc_loop_triangles(); protected_key = reference['triangles'][0]['key']
        tri = next(t for t in clone.data.loop_triangles if feature._base._key(
            [tuple(clone.data.vertices[v].co) for v in t.vertices]) == protected_key)
        normals = [list(n.vector) for n in clone.data.corner_normals]; li = tri.loops[0]
        normals[li] = [-x for x in normals[li]]; clone.data.normals_split_custom_set(normals)
        reject('actual-corrupt-retained-lower-front-corner', lambda: feature.verify(clone, reference),
            'Protected original front field exceeds .025 degree')
    finally:
        mesh = clone.data; bpy.data.objects.remove(clone, do_unlink=True); bpy.data.meshes.remove(mesh)
    feature.verify(front, reference)
    changed = copy.deepcopy(payload['lod_construction']); changed[index]['triangles_after'] += 1
    reject('stale-live-construction-inventory', lambda: live(changed), 'Live construction metadata')
    require(live() == proof['live'], 'Final live state changed after controls')


def high_tire_controls(e, observation, expected_observation_digest, controls):
    """Optional revision controls; the original44 cases remain unchanged.

    Uses the current caller-bound witness and actual native tires. Temporary
    corruptions are restored in memory; this function never opens or saves.
    """
    from ..distance_lod import tire
    from .. import tire_grooves38, tire_finish40, corner_encoding
    inputs = e['tire_binding']['inputs']
    spec, construction = e['embedded_specification'], e['construction']
    captured = e['tire_binding']['high_source']
    reject = lambda name, call, text: reject_control(controls, name, call, text)
    radial = tire_finish40.prepare(inputs, spec, construction, observation, expected_observation_digest)
    if radial is not None:
        # Historical contract cases still exercise the actual historical
        # observation. The complete current wrapper has its own caller-held
        # digest and independently replayed source binding above.
        observation = observation['legacy']
        expected_observation_digest = digest(observation)
    live_difference = ('Actual high tire differs' if radial is None else
                       'Actual current44 native tire differs')

    def contract(s=spec, c=construction, o=observation, held=expected_observation_digest):
        return tire.high_source_contract(inputs, s, c, o, held)

    reject('high-tire-missing-observation', lambda: contract(o=None), 'observation digest')
    reject('high-tire-wrong-held-observation-digest', lambda: contract(held='0' * 64), 'observation digest')
    changed = dict(construction); changed.pop('tire_grooves38')
    reject('high-tire-missing-construction', lambda: contract(c=changed), 'Missing or wrong high-tire construction')
    changed_spec = copy.deepcopy(spec); changed_spec['original_packaging'].pop('tire_groove_revision38')
    reject('high-tire-undeclared-revision', lambda: contract(s=changed_spec), 'Undeclared high-tire revision')
    changed_spec = copy.deepcopy(spec); changed_spec['original_packaging']['tire_groove_revision38']['floor_radial_stations'] -= 1
    reject('high-tire-unknown-specification-policy', lambda: contract(s=changed_spec), 'Unknown declared high-tire')
    changed_observation = copy.deepcopy(observation); changed_observation['native']['build'] = 'unknown'
    reject('high-tire-wrong-checkpoint-native-build',
        lambda: contract(o=changed_observation, held=digest(changed_observation)), 'native build differs')
    changed_observation = copy.deepcopy(observation); changed_observation['tires'].pop(tire.NAMES[-1])
    reject('high-tire-missing-observed-wheel',
        lambda: contract(o=changed_observation, held=digest(changed_observation)), 'Missing or extra high-tire')
    changed_observation = copy.deepcopy(observation)
    changed_observation['tires'][tire.NAMES[0]]['mesh']['normals'][0][0][0] += .01
    reject('high-tire-corrupt-observed-old-corner',
        lambda: contract(o=changed_observation, held=digest(changed_observation)), 'observed pre-change tire differs')
    for name, mutate, predicate in (
        ('missing-wheel', lambda p: p['tires'].pop(tire.NAMES[-1]), 'Missing or extra high-tire'),
        ('extra-wheel', lambda p: p['tires'].update(LOD0_Tire_Extra=p['tires'][tire.NAMES[0]]), 'Missing or extra high-tire'),
        ('wrong-constructor-hash', lambda p: p['constructor'].update(sha256='0' * 64), 'Caller file bytes differ'),
        ('wrong-encoder-hash', lambda p: p['encoder'].update(sha256='0' * 64), 'Caller file bytes differ'),
        ('wrong-constructor-path', lambda p: p['constructor'].update(path='tools/vehicles/endurance_sedan/wheels.py'), 'constructor/encoder logical path'),
        ('escaping-checkpoint-path', lambda p: p['checkpoint'].update(path='../source.blend'), 'project-relative'),
        ('wrong-checkpoint-bytes', lambda p: p['checkpoint'].update(bytes=p['checkpoint']['bytes'] + 1), 'observed checkpoint differs'),
        ('omitted-original-domain', lambda p: p['tires'][tire.NAMES[0]]['construction']['retained_original_face_indices'].pop(), 'Missing/overlapping complete high-tire'),
        ('overlapping-original-domain', lambda p: p['tires'][tire.NAMES[0]]['construction']['old_modified_face_indices'].__setitem__(0,
            p['tires'][tire.NAMES[0]]['construction']['retained_original_face_indices'][0]), 'Missing/overlapping complete high-tire'),
        ('omitted-target-corner', lambda p: p['tires'][tire.NAMES[0]]['construction']['targets'].pop(), 'Missing complete high-tire target'),
    ):
        changed = dict(construction); changed['tire_grooves38'] = copy.deepcopy(construction['tire_grooves38'])
        mutate(changed['tire_grooves38'])
        reject('high-tire-' + name, lambda c=changed: contract(c=c), predicate)
    changed_capture = copy.deepcopy(captured); changed_capture['observation_sha256'] = '0' * 64
    reject('high-tire-serialized-context-without-replay',
        lambda: tire.validate_high_source(inputs, spec, changed_capture), 'no complete replay in this process')
    changed_profile = copy.deepcopy(e['profile'])
    changed_profile['distant_tire']['high_source_revisions'][0]['floor_radius_m'] += .0001
    reject('high-tire-changed-profile-policy',
        lambda: hook.validate_profile(changed_profile, digest(changed_profile)), 'Changed distant tire profile')
    changed_inputs = copy.deepcopy(inputs); changed_inputs['source']['sha256'] = '0' * 64
    reject('high-tire-changed-source-bytes', lambda: tire.check_inputs(changed_inputs), 'Bound tire input bytes changed')
    previous_phase = bpy.context.scene['tire_groove_phase']
    try:
        bpy.context.scene['tire_groove_phase'] = 'pre-construction-checkpoint'
        reject('high-tire-wrong-live-phase', lambda: tire.validate_high_source(inputs, spec, captured),
               'not the constructed high-tire phase')
    finally:
        bpy.context.scene['tire_groove_phase'] = previous_phase
    obj = bpy.data.objects[tire.NAMES[0]]
    original_mesh = obj.data
    modified = original_mesh.copy()
    obj.data = modified
    try:
        uv = list(modified.uv_layers.active.data[0].uv)
        modified.uv_layers.active.data[0].uv[0] += 1e-4
        reject('high-tire-corrupted-native-UV-after-replay',
            lambda: tire.validate_high_source(inputs, spec, captured), live_difference)
        modified.uv_layers.active.data[0].uv = uv
        codes = modified.attributes['custom_normal']
        original_code = list(codes.data[0].value)
        codes.data[0].value = [original_code[0] + (-1 if original_code[0] == 32767 else 1), original_code[1]]
        reject('high-tire-corrupted-native-code-after-replay',
            lambda: tire.validate_high_source(inputs, spec, captured), live_difference)
        codes.data[0].value = original_code
        modified.vertices[0].co.x += .001
        reject('high-tire-corrupted-native-position-after-replay',
            lambda: tire.validate_high_source(inputs, spec, captured), live_difference)
    finally:
        obj.data = original_mesh
        bpy.data.meshes.remove(modified)
    material = original_mesh.materials[0]
    try:
        original_mesh.materials[0] = bpy.data.materials['Material_Trim']
        reject('high-tire-corrupted-native-material-after-replay',
            lambda: tire.validate_high_source(inputs, spec, captured), live_difference)
    finally:
        original_mesh.materials[0] = material
    parent = obj.parent
    try:
        obj.parent = bpy.data.objects['Wheel_FR']
        bpy.context.view_layer.update()
        reject('high-tire-corrupted-native-parent-after-replay',
            lambda: tire.validate_high_source(inputs, spec, captured), live_difference)
    finally:
        obj.parent = parent
        bpy.context.view_layer.update()
    # Changed targets must fail actual regeneration, even when current fields
    # still match. This rejects before the expensive complete surface bound.
    changed_witness = copy.deepcopy(construction['tire_grooves38']['tires'][obj.name])
    changed_witness['construction']['targets'][0] = [0., 0., 0.]
    legacy_mesh = None
    try:
        if radial is not None:
            # Restore only a temporary exact historical mesh generated from
            # the independently observed original checkpoint. Do not pretend
            # the current44 mesh is the historical52 construction result.
            witness = construction['tire_grooves38']['tires'][obj.name]
            legacy_mesh, replay = tire_grooves38.build_mesh(witness['before_native']['mesh'],
                list(original_mesh.materials), '_HistoricalTireQA', corner_encoding)
            require(tire_grooves38.plain(replay) == witness['construction'],
                    'Historical tire QA regeneration differs')
            obj.data = legacy_mesh
            tire_grooves38.current_matches(obj, witness)
        reject('high-tire-corrupted-replay-target', lambda: tire_grooves38.verify_current(obj, changed_witness),
            'constructor/domain/target replay differs')
    finally:
        obj.data = original_mesh
        if legacy_mesh is not None:
            bpy.data.meshes.remove(legacy_mesh)
    tire.validate_high_source(inputs, spec, captured)
