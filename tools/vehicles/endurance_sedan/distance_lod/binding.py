"""Explicit caller-owned source and constructor context; never opens a scene."""
import gzip
import hashlib
import importlib
import json
from pathlib import Path


CURRENT_FRONT_PROTECTION = {
    'schema': 'current-finite-front-protection36.v1',
    'original_protected_faces': 1419, 'additional_complete_faces': 85,
    'protected_faces': 1504, 'finite_lamp_faces': 466, 'moved_vertices': 168,
    'selection': 'Mixed shoulder and Trim boundary seed vertices union actual finite-lamp vertices; one complete triangle closure, no recursive fan growth',
    'preserve': 'Complete original geometry, UV, normal and ordered material fields',
}
CURRENT_GLASS = {
    'schema': 'current-planar-glass37.v1',
    'members': ['LOD0_Windshield', 'LOD0_Backlight'],
    'source_domains': {'outer': 96, 'inner': 96, 'rim': 56},
    'solidify_thickness_m': .0045,
    'retained': 'All four manufactured rim domains unchanged; only the two verified pane interiors may be retessellated',
}
ROLES = frozenset({'source', 'construction', 'constructor', 'geometry', 'specification', 'profile'})


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


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def validate_domain_profiles(profile):
    from .tire import POLICY, HIGH_SOURCE_POLICY
    require(profile.get('current_front_protection') == CURRENT_FRONT_PROTECTION,
            'Changed finite lamp protection profile')
    require(profile.get('current_glass') == CURRENT_GLASS,
            'Changed authorized current glass domain profile')
    supported = dict(POLICY, high_source_revisions=[HIGH_SOURCE_POLICY])
    require(profile.get('distant_tire') in (POLICY, supported), 'Changed distant tire profile')


def check_file(row):
    require(isinstance(row, dict) and set(row) >= {'path', 'sha256', 'bytes'},
            'Incomplete caller file binding')
    path = Path(row['path'])
    require(path.is_absolute() and path.resolve() == path, 'Caller file path must be resolved absolute')
    require(path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
            'Caller file bytes differ: ' + str(path))
    return path


def validate_lock(lock, expected_lock_digest):
    """Expected digest comes from the invoking command, never a supplied report."""
    require(isinstance(lock, dict) and digest(lock) == expected_lock_digest,
            'Caller distance-LOD input lock mismatch')
    require(set(lock) == {'schema', 'roles', 'input_files', 'generation_inputs'}
            and lock['schema'] == 'distance-lod-source-input38.v1', 'Wrong distance-LOD input schema')
    require(set(lock['roles']) == ROLES, 'Missing or extra distance-LOD input roles')
    roles = {name: check_file(row) for name, row in lock['roles'].items()}
    rows = lock['input_files']
    require(isinstance(rows, list) and rows, 'Missing complete package input inventory')
    paths = [check_file(row) for row in rows]
    require(len(paths) == len(set(paths)), 'Duplicate current package input path')
    package_root = Path(__file__).resolve().parents[1]
    required = {p.resolve() for p in package_root.rglob('*') if p.is_file() and p.suffix in {'.py', '.json'}}
    require(required <= set(paths), 'Missing current constructor/package input file')
    from .. import geometry, wheels
    require(roles['geometry'] == Path(geometry.__file__).resolve()
            and roles['constructor'] == Path(wheels.__file__).resolve(),
            'Caller constructor module paths differ from current package')
    require(roles['profile'] == Path(__file__).with_name('profile.json').resolve(),
            'Caller profile path differs from current package')
    return roles


def check_generation_inputs(construction, rows):
    """Hash declared original constructor files; do not import or execute them."""
    expected = construction['construction_inputs']
    require(isinstance(rows, list) and len(rows) == len(expected),
            'Missing original source-generation input inventory')
    keys = [row.get('logical_path') for row in rows]
    require(len(keys) == len(set(keys)), 'Duplicate original source-generation path')
    by_name = {row['logical_path']: row for row in rows}
    require(set(by_name) == {row['path'] for row in expected},
            'Original source-generation path inventory differs')
    for record in expected:
        row = by_name[record['path']]
        require(row['sha256'] == record['sha256'] and row['bytes'] == record['bytes'],
                'Original constructor checkpoint bytes differ: ' + record['path'])
        check_file(row)


def prepare(lock, *, expected_lock_digest, high_tire_observation=None,
            expected_high_tire_observation_digest=None):
    """Prepare from the already-open source and explicit immutable file lock.

    The owner opens the exact pre-LOD source first and retains the returned
    context digest outside the context before calling the public apply API.
    This function only reads/validates source fields and evaluates its graph.
    """
    import bpy
    from .. import geometry, optimization, surface_normals, reserve_correspondence26, bevel_reserve26
    from .. import lod_paint, selective_lod
    from ..qa import shoulder_checkpoint, lod_self_intersections
    from . import current_front, recipe, tire, tire_reference
    roles = validate_lock(lock, expected_lock_digest)
    require((bpy.app.version, bpy.app.build_hash.decode()) == ((5, 1, 2), 'ec6e62d40fa9'),
            'Pinned native Blender build mismatch')
    require(Path(bpy.data.filepath).resolve() == roles['source'], 'Already-open source path differs from caller lock')
    construction = read(roles['construction'])
    check_generation_inputs(construction, lock['generation_inputs'])
    profile = read(roles['profile'])
    recipe.validate_profile(profile, digest(profile))
    specification = read(roles['specification'])
    require(specification == json.loads(bpy.context.scene['specification']), 'Embedded/source specification differs')
    bpy.context.view_layer.update()
    bpy.context.evaluated_depsgraph_get().update()
    package_name = __package__.rsplit('.', 1)[0]
    package = importlib.import_module(package_name)
    require(package.lod_paint is lod_paint and package.selective_lod is selective_lod,
            'Ordinary optimizer dependencies are already overridden')
    dependencies = {name: importlib.import_module(package_name + '.' + relative) for name, relative in {
        'sheet': 'finishing34.front_sheet.sheet_reference', 'support': 'finishing34.front_sheet.field_support',
        'finite_bevel': 'finishing34.front_sheet.finite_bevel', 'carrier': 'finishing34.front_sheet.front_carrier',
        'normal_application': 'finishing34.front_sheet.normal_application', 'lamp': 'finishing34.lamp_surface',
        'ownership': 'surface_normals', 'projection': 'triangle_projection', 'transport': 'front_target_transport28',
        'bend': 'front_bend27', 'optical': 'front_lamp27', 'arch': 'arch_finish26',
        'recorder': 'front_field_capture27', 'snapshot_fields': 'shoulder_field02',
        'planar_glass': 'finishing34.planar_glass', 'native_fields': 'reserve_correspondence26',
    }.items()}
    packet = current_front.make_packet(bpy.data.objects['LOD0_FrontBumper'], construction,
        lock['roles']['source']['sha256'], dependencies, shoulder_checkpoint.material_fields)
    files = plain(lock['input_files'])
    expected = {'schema': 'current-finite-front-source-binding36.v1', 'source_path': str(roles['source']),
        'source_sha256': lock['roles']['source']['sha256'], 'construction_sha256': lock['roles']['construction']['sha256'],
        'field_core_sha256': packet['sha256'], 'input_files_sha256': digest(files),
        'profile_sha256': digest(profile), 'specification_sha256': digest(specification)}
    front_context = {'expected': expected, 'expected_binding_digest': digest(expected), 'observed': dict(expected),
        'input_files': files, 'profile': profile, 'packet': packet, 'dependencies': dependencies,
        'material_capture': shoulder_checkpoint.material_fields, 'construction_path': str(roles['construction'])}
    tire_inputs = {role: {'path': str(roles[name]), 'sha256': lock['roles'][name]['sha256']}
        for role, name in [('source', 'source'), ('construction', 'construction'), ('constructor', 'constructor'),
            ('geometry', 'geometry'), ('specification', 'specification'), ('base_profile', 'profile')]}
    if specification['original_packaging'].get('tire_groove_revision38') is not None:
        require(profile['distant_tire'].get('high_source_revisions') == [tire.HIGH_SOURCE_POLICY],
                'Profile does not authorize declared high-tire source revision')
    high_source = tire.prepare_high_source(tire_inputs, specification, construction,
        high_tire_observation, expected_high_tire_observation_digest)
    tire_binding = tire.capture_binding(tire_inputs, reference=tire_reference, hook=recipe,
        modifier_capture=bevel_reserve26.modifier_state, material_capture=shoulder_checkpoint.material_fields,
        high_source=high_source)
    captured = {'input_lock_digest': expected_lock_digest, 'front_binding_digest': digest(expected),
        'tire_binding_digest': digest(tire_binding), 'profile_digest': digest(profile)}
    return {'input_lock': plain(lock), 'expected_lock_digest': expected_lock_digest,
        'capture': captured, 'context_digest': digest(captured), 'source': roles['source'],
        'construction': construction, 'profile': profile, 'embedded_specification': specification,
        'packet': packet, 'front_context': front_context, 'tire_binding': tire_binding,
        'dependencies': dependencies, 'package': package, 'optimization': optimization,
        'geometry': geometry, 'surfaces': surface_normals, 'raw_capture': reserve_correspondence26.raw,
        'modifier_capture': bevel_reserve26.modifier_state, 'material_capture': shoulder_checkpoint.material_fields,
        'shell_certificate': lod_self_intersections.shell_certificate, 'reference': tire_reference}


def validate_context(context, expected_context_digest):
    require(isinstance(context, dict) and digest(context.get('capture')) == expected_context_digest
            == context.get('context_digest'), 'Caller distance-LOD context digest differs')
    validate_lock(context['input_lock'], context['expected_lock_digest'])
    expected = {'input_lock_digest': context['expected_lock_digest'],
        'front_binding_digest': context['front_context']['expected_binding_digest'],
        'tire_binding_digest': digest(context['tire_binding']), 'profile_digest': digest(context['profile'])}
    require(expected == context['capture'], 'Captured source/front/tire/profile context differs')
