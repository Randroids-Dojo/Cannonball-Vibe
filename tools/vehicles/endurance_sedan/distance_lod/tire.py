"""Source-derived LOD1 tires, with a guarded final combined29 replacement.

No source opening, scene saving, exporting or rendering. Caller supplies and
locks native source/constructor bindings. Failures leave diagnostic private
geometry in memory; discard that scene rather than exporting a partial result.
"""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath

import bmesh
import bpy

NAMES = tuple('LOD0_Tire_' + s for s in ('FL', 'FR', 'RL', 'RR'))
IDENTITY = [[float(i == j) for j in range(4)] for i in range(4)]
POLICY = {'schema': 'distant-tire36.v1', 'levels': [1], 'members': list(NAMES),
    'radial_stations': 24, 'meridian_points': 12, 'high_meridian_points': 28,
    'source_radial_stations': 52, 'radius_m': .3433, 'width_m': .255, 'bead_radius_m': .2413,
    'material': 'Material_Rubber', 'uv': 'original dominant-axis quad chart',
    'uv_meters_per_repeat': .25, 'UV_error': 1e-6, 'raw_normal_unit_error': 1e-6,
    'native_normal_field_degrees': .025, 'LOD0_triangles': 150000,
    'all_triangles_including_collision': 200000, 'materials': 32}
PROFILE_AST = 'd4e2e7fec17d985c6ca8b586ec10da2918ed85c1bd43fdea16635c5332c47af4'
HIGH_SOURCE_POLICY = {
    'schema': 'source-tire-groove38.v1', 'members': list(NAMES),
    'original_radial_stations': 52, 'floor_radial_stations': 36,
    'original_floor_radius_m': .3393, 'floor_radius_m': .339625,
    'centers_x_m': [-.068, -.023, .023, .068],
    'top_half_width_m': .003, 'floor_half_width_m': .002,
    'tire_radius_m': .3433, 'tire_width_m': .255, 'uv_meters_per_repeat': .25,
    'original_triangles_per_tire': 4728, 'new_triangles_per_tire': 4472,
    'retained_triangles_per_tire': 3480, 'source_profile_ast_sha256': PROFILE_AST,
    'form_error_m': .001, 'native_normal_degrees': .025,
    'raw_normal_unit_error': 1e-6, 'uv_error': 1e-6,
    'identity': 'Original fictional tessellation refinement; outer tire silhouette, original shoulder reliefs, sidewall and bead remain exact.',
}
# Verified native results live only in this process. A serialized packet cannot
# create a cache entry or bypass its caller-held observation and complete replay.
_HIGH_SOURCE_CONTEXTS = {}

def require(value, message):
    if not value:
        raise ValueError(message)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def matrix(value):
    return [list(row) for row in value]

def angle(a, b):
    cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross), sum(x*y for x, y in zip(a, b))))

def native_unit(normals):
    require(bool(normals), 'Missing native raw normal inventory')
    require(all(len(n) == 3 and all(math.isfinite(v) for v in n) for n in normals), 'Nonfinite native raw normal')
    maximum = max(abs(math.hypot(*n)-1) for n in normals)
    require(maximum <= POLICY['raw_normal_unit_error'], 'Native raw unit normal guard')
    return maximum

def check_inputs(inputs):
    require(set(inputs) == {'source', 'construction', 'constructor', 'geometry', 'specification', 'base_profile'},
            'Incomplete tire input roles')
    for role, row in inputs.items():
        path = Path(row['path'])
        require(path.is_absolute() and path.resolve() == path, 'Require resolved absolute input path: ' + role)
        require(path.is_file() and sha(path) == row['sha256'], 'Bound tire input bytes changed: ' + role)
    require(Path(bpy.data.filepath).resolve() == Path(inputs['source']['path']), 'Loaded source differs from tire input')


def _relative_file(row, label):
    require(isinstance(row, dict) and set(row) == {'path', 'sha256', 'bytes'},
            'Incomplete high-tire ' + label + ' file row')
    name = row['path']
    require(isinstance(name, str) and '\\' not in name and ':' not in name,
            'High-tire file path must be project-relative: ' + label)
    path = PurePosixPath(name)
    require(not path.is_absolute() and bool(path.parts) and '..' not in path.parts
            and str(path) == name, 'High-tire file path must be project-relative: ' + label)
    return path


def _module_row(module, row, expected_relative):
    from .binding import check_file
    require(str(_relative_file(row, 'helper')) == expected_relative,
            'Wrong high-tire constructor/encoder logical path')
    actual = {'path': str(Path(module.__file__).resolve()),
              'sha256': row['sha256'], 'bytes': row['bytes']}
    check_file(actual)
    return actual


def high_source_contract(inputs, spec, construction, observation, expected_observation_digest):
    """Validate the caller's actual pre-change observation, without scene I/O."""
    from .binding import check_file
    from .. import tire_grooves38, corner_encoding
    declared = spec['original_packaging'].get('tire_groove_revision38')
    proof = construction.get('tire_grooves38')
    if declared is None:
        require(proof is None and observation is None and expected_observation_digest is None,
                'Undeclared high-tire revision/checkpoint observation')
        return None
    require(declared == HIGH_SOURCE_POLICY == tire_grooves38.POLICY,
            'Unknown declared high-tire source policy')
    require(isinstance(proof, dict) and set(proof) == {
        'schema', 'policy', 'checkpoint', 'constructor', 'encoder', 'tires'}
        and proof['schema'] == 'source-tire-groove-construction38.v1'
        and proof['policy'] == HIGH_SOURCE_POLICY, 'Missing or wrong high-tire construction proof')
    require(isinstance(observation, dict) and expected_observation_digest is not None
            and digest(observation) == expected_observation_digest,
            'Caller-held high-tire checkpoint observation digest mismatch')
    require(set(observation) == {'schema', 'checkpoint', 'policy', 'native', 'tires'}
            and observation['schema'] == 'source-tire-groove-observation38.v1'
            and observation['policy'] == HIGH_SOURCE_POLICY,
            'Wrong high-tire checkpoint observation schema/policy')
    native = {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()}
    require(observation['native'] == native, 'High-tire checkpoint native build differs')
    relative = _relative_file(proof['checkpoint'], 'checkpoint')
    checkpoint = check_file(observation['checkpoint'])
    require(tuple(checkpoint.parts[-len(relative.parts):]) == relative.parts
            and all(observation['checkpoint'][key] == proof['checkpoint'][key]
                    for key in ('sha256', 'bytes')),
            'High-tire observed checkpoint differs from construction file')
    require(checkpoint != Path(inputs['source']['path']), 'High-tire checkpoint cannot be current source')
    files = {
        'checkpoint': copy.deepcopy(observation['checkpoint']),
        'constructor': _module_row(tire_grooves38, proof['constructor'],
            'tools/vehicles/endurance_sedan/tire_grooves38.py'),
        'encoder': _module_row(corner_encoding, proof['encoder'],
            'tools/vehicles/endurance_sedan/corner_encoding.py'),
    }
    require(set(proof['tires']) == set(observation['tires']) == set(NAMES),
            'Missing or extra high-tire source member')
    for name in NAMES:
        witness = proof['tires'][name]
        require(set(witness) == {'policy', 'before_native', 'after_native', 'construction'}
                and witness['policy'] == HIGH_SOURCE_POLICY, 'Wrong high-tire member witness')
        before, after = witness['before_native'], witness['after_native']
        require(observation['tires'][name] == before,
                'Actual observed pre-change tire differs from construction: ' + name)
        require(before['name'] == after['name'] == name, 'Wrong original/current high-tire semantic name')
        require(len(before['mesh']['faces']) == 4728 and len(after['mesh']['faces']) == 4472,
                'Wrong original/current declared high-tire triangle inventory')
        built = witness['construction']
        retained, old, new = (built[key] for key in (
            'retained_original_face_indices', 'old_modified_face_indices', 'new_modified_face_indices'))
        require(len(retained) == len(set(retained)) == 3480
                and len(old) == len(set(old)) == 1248
                and not set(retained) & set(old)
                and set(retained) | set(old) == set(range(4728))
                and len(new) == len(set(new)) == 992
                and set(new) == set(range(3480, 4472)),
                'Missing/overlapping complete high-tire original/generated domain')
        require(len(built['targets']) == 4472 * 3,
                'Missing complete high-tire target corner inventory')
    return {'proof': proof, 'observation': observation, 'files': files, 'native': native}


def prepare_high_source(inputs, spec, construction, observation, expected_observation_digest):
    """Replay each declared tire once; subsequent uses require exact recapture."""
    check_inputs(inputs)
    contract = high_source_contract(inputs, spec, construction, observation, expected_observation_digest)
    if contract is None:
        return None
    from .. import tire_grooves38
    proof = contract['proof']
    captured = {
        'schema': 'distance-lod-high-tire-binding38.v1', 'policy': copy.deepcopy(HIGH_SOURCE_POLICY),
        'inputs_sha256': digest(inputs), 'observation_sha256': expected_observation_digest,
        'construction_proof_sha256': digest(proof), 'files': contract['files'],
        'native': contract['native'],
        'before_sha256': {name: digest(proof['tires'][name]['before_native']) for name in NAMES},
        'after_sha256': {name: digest(proof['tires'][name]['after_native']) for name in NAMES},
    }
    key = digest(captured)
    if key not in _HIGH_SOURCE_CONTEXTS:
        replay = {name: tire_grooves38.verify_current(bpy.data.objects[name], proof['tires'][name])
                  for name in NAMES}
        _HIGH_SOURCE_CONTEXTS[key] = {
            'binding': copy.deepcopy(captured), 'proof': copy.deepcopy(proof),
            'observation': copy.deepcopy(observation), 'replay': copy.deepcopy(replay),
        }
    validate_high_source(inputs, spec, captured)
    return captured


def validate_high_source(inputs, spec, captured):
    """Rehash real inputs and compare all native fields after any cached replay."""
    from .binding import check_file
    from .. import tire_grooves38, corner_encoding
    check_inputs(inputs)
    require(spec == json.loads(bpy.context.scene['specification']),
            'Embedded/source specification differs')
    require(spec['original_packaging'].get('tire_groove_revision38') == HIGH_SOURCE_POLICY,
            'Missing/changed current high-tire source declaration')
    require(isinstance(captured, dict), 'Missing independently prepared high-tire context')
    key = digest(captured)
    require(key in _HIGH_SOURCE_CONTEXTS, 'High-tire context has no complete replay in this process')
    cached = _HIGH_SOURCE_CONTEXTS[key]
    require(captured == cached['binding'] and captured['inputs_sha256'] == digest(inputs)
            and captured['construction_proof_sha256'] == digest(cached['proof'])
            and captured['observation_sha256'] == digest(cached['observation']),
            'Changed verified high-tire context/checkpoint digest')
    require(captured['policy'] == tire_grooves38.POLICY == HIGH_SOURCE_POLICY
            and captured['native'] == {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()},
            'Changed high-tire native/helper policy')
    for row in captured['files'].values():
        check_file(row)
    require(Path(tire_grooves38.__file__).resolve() == Path(captured['files']['constructor']['path'])
            and Path(corner_encoding.__file__).resolve() == Path(captured['files']['encoder']['path']),
            'Changed actual high-tire constructor/encoder module')
    require(bpy.context.scene.get('tire_groove_phase') == 'constructed',
            'Current source is not the constructed high-tire phase')
    for name in NAMES:
        obj = bpy.data.objects.get(name)
        require(obj is not None and obj.type == 'MESH', 'Missing current high-tire member: ' + name)
        tire_grooves38.current_matches(obj, cached['proof']['tires'][name])
    return cached


def high_source_evidence(binding, expected_binding_digest):
    """Expose the actual complete replay result for a caller's retained report."""
    require(digest(binding) == expected_binding_digest, 'Caller-locked tire binding digest mismatch')
    check_inputs(binding['inputs'])
    spec = json.loads(Path(binding['inputs']['specification']['path']).read_text(encoding='utf-8'))
    cached = validate_high_source(binding['inputs'], spec, binding.get('high_source'))
    return copy.deepcopy(cached['replay'])


def capture_binding(inputs, *, reference, hook, modifier_capture, material_capture, high_source=None):
    """Read-only pre-LOD packet; caller locks its digest outside the result.

    Inputs must be independently source-generation/command bound. This packet
    proves current tire identity, not the rest of a construction witness.
    """
    check_inputs(inputs)
    require((bpy.app.version, bpy.app.build_hash.decode()) == ((5, 1, 2), 'ec6e62d40fa9'), 'Pinned native build required')
    spec = json.loads(Path(inputs['specification']['path']).read_text(encoding='utf-8'))
    require(spec == json.loads(bpy.context.scene['specification']), 'Embedded/source specification differs')
    declared = spec['original_packaging'].get('tire_groove_revision38')
    if declared is None:
        require(high_source is None, 'Undeclared high-tire context')
    else:
        validate_high_source(inputs, spec, high_source)
    profile, ast_sha = reference.profile_from_constructor(inputs['constructor']['path'], spec)
    require(ast_sha == PROFILE_AST and len(profile) == 28, 'Changed original meridian constructor')
    reduced = profile[:6] + profile[-6:]
    require(len(reduced) == 12 and max(p[1] for p in reduced) == .3433
        and min(p[1] for p in reduced) == .2413 and max(p[0] for p in reduced)-min(p[0] for p in reduced) == .255,
        'Changed declared tire profile dimensions')
    base_profile = json.loads(Path(inputs['base_profile']['path']).read_text(encoding='utf-8'))
    hook.validate_profile(base_profile, digest(base_profile))
    if declared is not None:
        require(base_profile['distant_tire'].get('high_source_revisions') == [HIGH_SOURCE_POLICY],
                'Profile does not authorize declared high-tire source revision')
    rows = {}
    bpy.context.view_layer.update()
    for name in NAMES:
        obj = bpy.data.objects.get(name)
        require(obj is not None and obj.type == 'MESH' and not obj.get('source_preview_only'), 'Missing shipping high tire: ' + name)
        require(obj.parent is not None and obj.parent.type == 'EMPTY' and obj.parent.name == name.replace('LOD0_Tire_', 'Wheel_'), 'Wrong tire rigid parent: ' + name)
        require(matrix(obj.matrix_basis) == IDENTITY and matrix(obj.matrix_parent_inverse) == IDENTITY, 'Changed tire local transform: ' + name)
        require(not obj.modifiers, 'Unexpected current high tire modifier: ' + name)
        obj.data.calc_loop_triangles()
        require(len(obj.data.loop_triangles) == (4728 if declared is None else 4472),
                'Changed current high tire triangle inventory: ' + name)
        used = {obj.data.materials[p.material_index].name if obj.data.materials[p.material_index] else None for p in obj.data.polygons}
        require(used == {'Material_Rubber'}, 'Wrong used tire material: ' + name)
        require(len(obj.data.uv_layers) == 1 and obj.data.uv_layers.active.name == 'SurfaceMeters', 'Changed high tire UV chart: ' + name)
        native_unit([list(n.vector) for n in obj.data.corner_normals])
        rows[name] = {'raw_sha256': digest(hook.raw_fields(obj)),
            'modifiers_sha256': digest(modifier_capture(obj)),
            'material_response_sha256': digest(material_capture(obj.data)),
            'matrix_basis': matrix(obj.matrix_basis), 'matrix_parent_inverse': matrix(obj.matrix_parent_inverse),
            'parent': obj.parent.name, 'parent_world': matrix(obj.parent.matrix_world),
            'triangles': len(obj.data.loop_triangles), 'materials': [m.name if m else None for m in obj.data.materials]}
    captured = {'schema': 'distant-tire-source36.v1', 'inputs': copy.deepcopy(inputs), 'policy': copy.deepcopy(POLICY),
        'profile': [list(p) for p in profile], 'carcass': [list(p) for p in reduced],
        'profile_ast_sha256': ast_sha, 'base_profile_sha256': digest(base_profile), 'tires': rows}
    if high_source is not None:
        captured['high_source'] = copy.deepcopy(high_source)
    return captured

def validate_binding(binding, expected_digest, **capture_args):
    require(digest(binding) == expected_digest, 'Caller-locked tire binding digest mismatch')
    require(binding.get('schema') == 'distant-tire-source36.v1' and binding.get('policy') == POLICY,
        'Wrong tire policy/schema')
    actual = capture_binding(binding['inputs'], high_source=binding.get('high_source'), **capture_args)
    require(actual == binding, 'Actual source/profile/material/parent tire fields differ from caller binding')

def select_batches(lower, entries, binding):
    """Complete semantics, not historic batch ordinals or pre-Decimate ranges."""
    names = [obj.name for obj in lower]
    require(len(names) == len(set(names)), 'Duplicate lower object')
    require(len(entries) == len(names) and {e['batch'] for e in entries} == set(names), 'Missing or stale lower entry')
    require(json.loads(bpy.context.scene.get('lod_construction', 'null')) == entries, 'Stale live construction metadata')
    by_name = {e['batch']: e for e in entries}
    selected = {}
    for obj in lower:
        sources = json.loads(obj.get('source_components', 'null'))
        require(isinstance(sources, list) and sources and len(sources) == len(set(sources)), 'Invalid source membership')
        if obj.get('lod_index') != 1 or not set(sources) & set(NAMES):
            continue
        require(len(sources) == 1 and sources[0] in NAMES, 'Tire shares a batch with unowned members')
        source = sources[0]
        require(source not in selected, 'Duplicate LOD1 tire member')
        entry = by_name[obj.name]
        require(obj.name.startswith('LOD1_') and not obj.modifiers and entry['lod'] == 1, 'Wrong tire output level or live modifier')
        require(obj.parent and obj.parent.name == entry['parent'] == binding['tires'][source]['parent'], 'Wrong output tire parent')
        require(matrix(obj.matrix_basis) == IDENTITY and matrix(obj.matrix_parent_inverse) == IDENTITY, 'Wrong output tire transform')
        require(entry['material'] == 'Material_Rubber' and {obj.data.materials[p.material_index].name for p in obj.data.polygons} == {'Material_Rubber'}, 'Wrong output tire material')
        ranges = entry.get('components', entry.get('source_components_before_simplification'))
        require(isinstance(ranges, list) and len(ranges) == 1 and ranges[0]['source_component'] == source, 'Missing exact tire construction membership')
        obj.data.calc_loop_triangles()
        require(entry['triangles_after'] == len(obj.data.loop_triangles), 'Stale old tire triangle record')
        selected[source] = obj
    require(set(selected) == set(NAMES), 'Missing required four LOD1 tires')
    return selected

def build_tire(source, binding, collection, geometry, hook, shell_certificate):
    require(Path(geometry.__file__).resolve() == Path(binding['inputs']['geometry']['path'])
        and sha(geometry.__file__) == binding['inputs']['geometry']['sha256'], 'Wrong native geometry constructor module')
    name = source.name.replace('LOD0_Tire_', 'LOD1_DistantTire_')
    require(bpy.data.objects.get(name) is None, 'Distant tire output already exists')
    material = bpy.data.materials['Material_Rubber']
    obj = geometry.ring_x(name, binding['carcass'], (0, 0, 0), material, collection, source.parent, 24)
    mesh = obj.data
    require(len(mesh.vertices) == 288 and len(mesh.polygons) == 288, 'Incomplete source-derived quad ring')
    points = [list(v.co) for v in mesh.vertices]
    targets = {}
    quads = []
    for face in mesh.polygons:
        quads.append({'vertices': list(face.vertices),
            'uv': {str(mesh.loops[li].vertex_index): list(mesh.uv_layers.active.data[li].uv) for li in face.loop_indices}})
    for loop, normal in zip(mesh.loops, mesh.corner_normals):
        n = list(normal.vector)
        require(loop.vertex_index not in targets or targets[loop.vertex_index] == n, 'Ambiguous new smooth vertex fan')
        targets[loop.vertex_index] = n
    native_unit(list(targets.values()))
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.normals_split_custom_set([targets[loop.vertex_index] for loop in mesh.loops])
    obj['source_components'] = json.dumps([source.name])
    obj['lod_index'] = 1
    obj.hide_render = True
    obj.hide_set(True)
    witness = {'policy_sha256': digest(POLICY), 'source_binding_sha256': digest(binding),
        'source_component': source.name, 'points': points, 'quad_charts': quads,
        'target_by_vertex': {str(k): v for k, v in targets.items()},
        'target_domain': 'Native smooth quad-ring field before triangulation; complete new distant surface',
        'parent': source.parent.name, 'parent_world': matrix(source.parent.matrix_world)}
    verified = verify_tire(obj, witness, digest(witness), geometry, hook, shell_certificate)
    entry = {'batch': obj.name, 'lod': 1, 'parent': obj.parent.name, 'material': material.name,
        'method': 'Original12-point carcass revolved at24 stations; native smooth field retained through triangulation',
        'triangles': 576, 'triangles_after': 576,
        'components': [{'source_component': source.name, 'source_parent': source.parent.name,
            'vertex_start': 0, 'vertex_count': 288, 'triangle_start': 0, 'triangle_count': 576,
            'component_to_batch': IDENTITY}],
        'component_range_domain': 'Complete final native distant-carcass ranges',
        'distance_tire_policy_sha256': digest(POLICY), 'source_binding_sha256': digest(binding),
        'field_witness_sha256': digest(witness), 'native_field_encoding': verified['encoding']}
    obj['distant_tire_construction'] = json.dumps({'policy_sha256': digest(POLICY),
        'source_binding_sha256': digest(binding), 'field_witness_sha256': digest(witness)}, sort_keys=True)
    return obj, entry, witness, verified

def verify_tire(obj, witness, expected_witness_digest, geometry, hook, shell_certificate):
    require(digest(witness) == expected_witness_digest, 'Changed new-field witness')
    mesh = obj.data
    mesh.calc_loop_triangles()
    require(not obj.modifiers and len(mesh.vertices) == 288 and len(mesh.polygons) == 576
        and len(mesh.loop_triangles) == 576 and all(len(p.vertices) == 3 for p in mesh.polygons), 'Incomplete final distant tire topology')
    require([list(v.co) for v in mesh.vertices] == witness['points'], 'New tire carrier position changed')
    require(obj.parent and obj.parent.name == witness['parent'] and matrix(obj.parent.matrix_world) == witness['parent_world'], 'New tire parent/pose changed')
    require(matrix(obj.matrix_basis) == IDENTITY and matrix(obj.matrix_parent_inverse) == IDENTITY, 'New tire transform changed')
    require([m.name if m else None for m in mesh.materials] == ['Material_Rubber']
        and all(p.material_index == 0 and p.use_smooth for p in mesh.polygons), 'New tire material/smooth field changed')
    require(len(mesh.uv_layers) == 1 and mesh.uv_layers.active.name == 'SurfaceMeters', 'New tire UV chart inventory changed')
    uv_error = 0.
    for face in mesh.polygons:
        owners = [q for q in witness['quad_charts'] if set(face.vertices) <= set(q['vertices'])]
        require(len(owners) == 1, 'Missing or ambiguous complete original quad chart owner')
        for li in face.loop_indices:
            actual = list(mesh.uv_layers.active.data[li].uv)
            expected = owners[0]['uv'][str(mesh.loops[li].vertex_index)]
            require(all(math.isfinite(v) for v in actual), 'Nonfinite new tire UV')
            uv_error = max(uv_error, *(abs(a-b) for a, b in zip(actual, expected)))
    require(uv_error <= POLICY['UV_error'], 'New tire UV target drift')
    actual = [list(n.vector) for n in mesh.corner_normals]
    unit_error = native_unit(actual)
    target = [witness['target_by_vertex'][str(loop.vertex_index)] for loop in mesh.loops]
    native_unit(target)
    angles = [angle(a, b) for a, b in zip(actual, target)]
    require(max(angles) <= POLICY['native_normal_field_degrees'], 'New tire decoded target-normal drift')
    raw = hook.raw_fields(obj)
    row = hook.evaluated_row(obj, geometry)
    require(row['vertices'] == witness['points'] and row['normals'] == actual
        and row['uv'] == raw['uv'], 'New tire evaluated/raw fields disagree')
    certificate = shell_certificate(row)
    require(certificate['status'] == 'passed', 'New tire exact shell/self certificate failed')
    count = geometry.evaluated_counts(obj)
    bad = ('nonmanifold_edges', 'degenerate_triangles', 'duplicate_faces',
        'triangulated_nonmanifold_edges', 'triangulated_duplicate_faces',
        'zero_corner_normals', 'nonfinite_corner_normals', 'nonunit_corner_normals')
    require(not any(count[k] for k in bad), 'New tire native geometry/normal guard')
    return {'encoding': {'passed': True, 'corners': len(actual), 'maximum_degrees': max(angles),
        'raw_maximum_unit_error': unit_error, 'UV_maximum_error': uv_error,
        'actual_normals_sha256': digest(actual), 'targets_sha256': digest(target)},
        'counts': count, 'shell': certificate, 'row': row, 'raw_sha256': digest(raw)}

def verify_final_tires(final, entries, witnesses, expected_witness_digests, geometry, hook, shell_certificate):
    names = {n.replace('LOD0_Tire_', 'LOD1_DistantTire_') for n in NAMES}
    require(set(witnesses) == set(expected_witness_digests) == names, 'Incomplete final tire witnesses')
    selected = {o.name: o for o in final if o.name in names}
    require(set(selected) == names, 'Missing final live distant tire')
    by_name = {e['batch']: e for e in entries}
    checks = {}
    for name, obj in selected.items():
        witness = witnesses[name]
        check = verify_tire(obj, witness, expected_witness_digests[name], geometry, hook, shell_certificate)
        entry = by_name[name]
        require(entry['native_field_encoding'] == check['encoding'], 'Stale final native tire encoding record')
        require(entry['field_witness_sha256'] == expected_witness_digests[name]
            and entry['source_binding_sha256'] == witness['source_binding_sha256']
            and entry['distance_tire_policy_sha256'] == digest(POLICY), 'Stale final tire field/provenance record')
        require(json.loads(obj['distant_tire_construction']) == {
            'policy_sha256': digest(POLICY), 'source_binding_sha256': witness['source_binding_sha256'],
            'field_witness_sha256': expected_witness_digests[name]}, 'Live tire field metadata differs from final witness')
        checks[name] = check
    return checks

def replace(collection, lower, entries, *, binding, expected_binding_digest, reference,
            geometry, hook, api, shell_certificate, original_names, expected_members,
            modifier_capture, material_capture):
    """Final boundary, also usable after the caller's complete current build.

    The full caller must supply every live lower mesh/member, not just tires.
    This function always rechecks the complete actual live inventory supplied.
    """
    validate_binding(binding, expected_binding_digest, reference=reference, hook=hook,
        modifier_capture=modifier_capture, material_capture=material_capture)
    original_names = set(original_names)
    selected = select_batches(lower, entries, binding)
    require(not original_names & {obj.name for obj in selected.values()}, 'Cannot replace an original source object')
    live_before = api.verify_live(collection, lower, entries, original_names=original_names,
        expected_members=expected_members, geometry=geometry, hook=hook)
    selected_names = {obj.name for obj in selected.values()}
    retained = {obj.name: digest(hook.raw_fields(obj)) for obj in lower if obj.name not in selected_names}
    retained_entries = {e['batch']: copy.deepcopy(e) for e in entries if e['batch'] not in selected_names}
    old_entries = [copy.deepcopy(e) for e in entries if e['batch'] in selected_names]
    new_objects, new_entries, witnesses, checks = [], [], {}, {}
    for name in NAMES:
        obj, entry, witness, check = build_tire(bpy.data.objects[name], binding, collection, geometry, hook, shell_certificate)
        new_objects.append(obj)
        new_entries.append(entry)
        witnesses[obj.name] = witness
        checks[obj.name] = check
    # The new geometry must survive the same normal/diagonal post-repair phase.
    for obj in new_objects:
        geometry.repair_triangulation(obj)
        checks[obj.name] = verify_tire(obj, witnesses[obj.name], digest(witnesses[obj.name]), geometry, hook, shell_certificate)
    for entry in new_entries:
        entry['native_field_encoding'] = checks[entry['batch']]['encoding']
    retained_objects = [obj for obj in lower if obj.name not in selected_names]
    for obj in selected.values():
        require(obj.name in selected_names and obj.name not in original_names and obj.get('lod_index') == 1, 'Private deletion ownership mismatch')
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    final = retained_objects + new_objects
    final_entries = [copy.deepcopy(e) for e in entries if e['batch'] not in selected_names] + new_entries
    final.sort(key=lambda o: o.name)
    final_entries.sort(key=lambda e: e['batch'])
    bpy.context.scene['lod_construction'] = json.dumps(final_entries, sort_keys=True)
    bpy.context.view_layer.update()
    require({o.name: digest(hook.raw_fields(o)) for o in final if o.name in retained} == retained, 'Unselected lower field changed')
    require({e['batch']: e for e in final_entries if e['batch'] in retained_entries} == retained_entries, 'Unselected lower construction changed')
    live = api.verify_live(collection, final, final_entries, original_names=original_names,
        expected_members=expected_members, geometry=geometry, hook=hook)
    checks = verify_final_tires(final, final_entries, witnesses, {n: digest(w) for n,w in witnesses.items()},
        geometry, hook, shell_certificate)
    old_count = sum(e['triangles_after'] for e in old_entries)
    return final, {'schema': 'distant-tire-replacement36.v1', 'live': live,
        'source_binding_sha256': expected_binding_digest, 'policy': copy.deepcopy(POLICY),
        'before_live': live_before, 'superseded_entries': old_entries,
        'superseded_private_batches_removed': sorted(selected_names),
        'retained_lower_hashes': retained, 'retained_entries_sha256': digest(retained_entries),
        'new_tire_triangles': 2304, 'previous_tire_triangles': old_count,
        'measured_LOD1_saving': old_count-2304, 'witnesses': witnesses,
        'new_checks': checks, 'lod_construction': final_entries,
        'GPU': False, 'source_saves': 0, 'exports': 0}, final_entries

def require_front_context(context, binding, hook):
    require(isinstance(context, dict) and context.get('expected') is not None,
        'Current whole-front binding required before combined LOD construction')
    expected = context['expected']
    require(expected.get('source_sha256') == binding['inputs']['source']['sha256']
        and Path(expected.get('source_path', '')).resolve() == Path(binding['inputs']['source']['path']),
        'Current front context belongs to another source; no stale packet/hash substitution')
    # Existing whole-face and geometric provenance guards remain authoritative.
    if context.get('current_revision40') is True:
        from . import front_feature40
        from ..qa.front_finish_report import NAMES
        return {name: front_feature40.capture(bpy.data.objects[name], context=context) for name in NAMES}
    return hook.load('front_feature_mixed').capture(bpy.data.objects['LOD0_FrontBumper'], context=context)

def apply(collection, lods, *, binding, expected_binding_digest, reference, api, material_capture, **base_args):
    """Production wrapper. Complete front preflight precedes all construction."""
    hook = api.load('distant_tire_capture', 'recipe')
    validate_binding(binding, expected_binding_digest, reference=reference, hook=hook,
        modifier_capture=base_args['modifier_capture'], material_capture=material_capture)
    require_front_context(base_args.get('front_context'), binding, hook)
    before = api.source_snapshot(base_args['raw_capture'], base_args['modifier_capture'])
    empties = api.empty_fields()
    lower, base, payload = api.apply(collection, lods, **base_args)
    require(base['status'] in ('passed-native-construction', 'failed-budget'), 'Base geometry/field construction did not pass')
    expected_members = base['base_proof']['retained_source_members']
    final, replacement, entries = replace(collection, lower, payload['lod_construction'],
        binding=binding, expected_binding_digest=expected_binding_digest, reference=reference,
        geometry=base_args['geometry'], hook=hook, api=api, shell_certificate=base_args['shell_certificate'],
        original_names=set(before), expected_members=expected_members,
        modifier_capture=base_args['modifier_capture'], material_capture=material_capture)
    api.verify_originals(before, empties, base_args['raw_capture'], base_args['modifier_capture'])
    rows, certificates = [], []
    for obj in final:
        row = hook.evaluated_row(obj, base_args['geometry'])
        rows.append(row)
        certificates.append(base_args['shell_certificate'](row))
    require(all(c['status'] == 'passed' for c in certificates), 'Final complete indexed-shell failure')
    hashes = {obj.name: digest(hook.raw_fields(obj)) for obj in final}
    live = replacement['live']
    report = {'status': 'passed-native-construction' if live['budget']['passed'] else 'failed-budget',
        'profile_digest': base['profile_digest'], 'live': live,
        'distance_tire_replacement': replacement,
        'base_before_tire_replacement': base,
        'final_after_repair_hashes': hashes, 'complete_indexed_shell_proofs': certificates,
        'indexed_shell_count': sum(c['shell_count'] for c in certificates),
        'original_raw_mesh_modifier_hashes': {n: digest(v) for n, v in before.items()},
        'source_meshes_preserved': len(before), 'original_empty_field_digest': digest(empties),
        'source_saves': 0, 'exports': 0, 'GPU': False, 'human_approval_reference': None}
    return final, report, {'meshes': rows, 'lod_construction': entries}
