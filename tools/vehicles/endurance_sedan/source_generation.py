"""Portable source-generation records and explicit native input locks."""
from pathlib import Path
import gzip
import hashlib
import json


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def read_plain(value):
    """Copy JSON-compatible native values without accepting NaN or infinity."""
    return json.loads(json.dumps(value, allow_nan=False))


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON property: ' + key)
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('Nonfinite JSON number: ' + value)

    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw,
                      object_pairs_hook=unique, parse_constant=nonfinite)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        if path.suffix == '.gz':
            with gzip.GzipFile(fileobj=stream, mode='wb', mtime=0) as compressed:
                compressed.write(raw)
        else:
            stream.write(raw)
    return path


def file_row(path, root=None):
    path = Path(path).resolve(strict=True)
    if root is None:
        label = str(path)
    else:
        root = Path(root).resolve(strict=True)
        require(path.is_relative_to(root), 'Artifact outside the declared project root')
        label = path.relative_to(root).as_posix()
    return {'path': label, 'sha256': sha(path), 'bytes': path.stat().st_size}


def verify_rows(rows, root=None):
    seen = set()
    for row in rows:
        path = Path(row['path']) if root is None else Path(root) / row['path']
        path = path.resolve(strict=True)
        require(path not in seen, 'Duplicate locked artifact')
        seen.add(path)
        if root is not None:
            require(path.is_relative_to(Path(root).resolve()), 'Locked input escapes its project')
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Locked bytes changed: ' + str(path))


def lower_lock(root, source, construction):
    """The invoking owner holds digest(result) outside the native process."""
    root = Path(root).resolve(strict=True)
    package = root / 'tools/vehicles/endurance_sedan'
    paths = {'source': Path(source), 'construction': Path(construction),
             'constructor': package / 'wheels.py', 'geometry': package / 'geometry.py',
             'specification': root / 'docs/vehicles/endurance-sedan/specification.json',
             'profile': package / 'distance_lod/profile.json'}
    companion = read(construction)
    original = companion['construction_inputs']
    verify_rows(original, root)
    return {'schema': 'distance-lod-source-input38.v1',
            'roles': {role: file_row(path) for role, path in paths.items()},
            'input_files': [file_row(path) for path in sorted(package.rglob('*'))
                            if path.is_file() and path.suffix in ('.py', '.json')],
            'generation_inputs': [{'logical_path': row['path'], **file_row(root / row['path'])}
                                  for row in original]}


def portable_lock(lock, root):
    root = Path(root).resolve(strict=True)

    def portable(row):
        path = Path(row['path']).resolve(strict=True)
        require(path.is_relative_to(root), 'Native input lies outside the project')
        return {**row, 'path': path.relative_to(root).as_posix()}

    return {**lock, 'roles': {key: portable(row) for key, row in lock['roles'].items()},
            'input_files': [portable(row) for row in lock['input_files']],
            'generation_inputs': [portable(row) for row in lock['generation_inputs']]}


def absolute_lock(lock, root):
    root = Path(root).resolve(strict=True)

    def absolute(row):
        label = row['path']
        require(isinstance(label, str) and '\\' not in label and ':' not in label,
                'Portable project-relative input path required')
        relative = Path(label)
        require(not relative.is_absolute() and all(part not in ('.', '..') for part in label.split('/')),
                'Escaping portable source input')
        path = (root / relative).resolve(strict=True)
        require(path.is_relative_to(root), 'Portable source input resolves outside project')
        return {**row, 'path': str(path)}

    result = {**lock, 'roles': {key: absolute(row) for key, row in lock['roles'].items()},
              'input_files': [absolute(row) for row in lock['input_files']],
              'generation_inputs': [absolute(row) for row in lock['generation_inputs']]}
    for rows in (result['roles'].values(), result['input_files'], result['generation_inputs']):
        verify_rows(rows)
    return result


def observe_high_tire_checkpoint(root, construction):
    """Source owner observes a real native checkpoint, before opening current source."""
    if 'tire_grooves38' not in construction:
        return None
    import bpy
    from . import tire_grooves38
    proof = construction['tire_grooves38']
    require(proof['schema'] == 'source-tire-groove-construction38.v1'
            and proof['policy'] == tire_grooves38.POLICY, 'Wrong source tire revision')
    verify_rows([proof['checkpoint'], proof['constructor'], proof['encoder']], root)
    path = (Path(root) / proof['checkpoint']['path']).resolve(strict=True)
    expected = file_row(path)
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    require(bpy.context.scene.get('tire_groove_phase') == 'pre-construction-checkpoint',
            'Source tire checkpoint has the wrong construction phase')
    require(set(proof['tires']) == set(tire_grooves38.NAMES), 'Incomplete current tire witnesses')
    observed = {name: tire_grooves38.capture(bpy.data.objects[name]) for name in tire_grooves38.NAMES}
    require(observed == {name: value['before_native'] for name, value in proof['tires'].items()},
            'Actual saved pre-groove native tire fields differ from current companion')
    verify_rows([expected])
    observed_legacy = {'schema': 'source-tire-groove-observation38.v1', 'checkpoint': expected,
            'policy': tire_grooves38.POLICY, 'tires': observed,
            'native': {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()}}
    from .tire_finish40 import observe
    return observe(root, construction, observed_legacy)


def observation_arguments(observation):
    return {} if observation is None else {
        'high_tire_observation': observation,
        'expected_high_tire_observation_digest': digest(observation)}


def observe_source_checkpoints(root, construction):
    """Return held observations; caller reopens the actual current source next."""
    from .front_finish40.observation import observe
    from .upper_finish40.observation import observe as observe_upper
    return {'high_tire': observe_high_tire_checkpoint(root, construction),
            'front_finish': observe(root, construction), 'upper_finish': observe_upper(root, construction)}


def source_observation_arguments(observations):
    result = observation_arguments(observations['high_tire'])
    front = observations['front_finish']
    if front is not None:
        result.update(front_observation=front, expected_front_observation_digest=digest(front))
    upper = observations.get('upper_finish')
    if upper is not None:
        result.update(upper_observation=upper, expected_upper_observation_digest=digest(upper))
    return result


def verify_saved_lower(source, binding_path, root, *, unused_output):
    """Re-extract the already-open saved source before any exporter mutation."""
    import bpy
    from . import distance_lod
    from .qa.gate import load_source_binding
    from .qa import distance_lod as checker
    lock = load_source_binding(binding_path, source, root, unused_output)
    require(lock.pipeline is not None, 'Current source export requires a v2 source binding')
    require(Path(bpy.data.filepath).resolve() == lock.source.path, 'Exporter scene differs from source binding')
    observations = observe_source_checkpoints(lock.root, read(lock.pipeline.construction.path))
    if any(value is not None for value in observations.values()):
        bpy.ops.wm.open_mainfile(filepath=str(lock.source.path), load_ui=False, use_scripts=False)
    native = absolute_lock(lock.pipeline.portable_input_lock, lock.root)
    context = distance_lod.prepare(native, expected_lock_digest=digest(native),
                                   **source_observation_arguments(observations))
    held = context['context_digest']
    front = distance_lod.verify_current_front(context=context, expected_context_digest=held)
    upper = distance_lod.verify_current_upper(context=context, expected_context_digest=held)
    bundle = read(lock.pipeline.lower_bundle.path)
    lower = [bpy.data.objects[row['name']] for row in bundle['payload']['meshes']]
    result = checker.verify_result(context, bundle['before'], bundle['material_before'],
                                  lower, bundle['proof'], bundle['payload'])
    lock.verify()
    return {'status': 'passed', 'source_sha256': lock.source.sha256,
            'binding_sha256': lock.binding.sha256, 'construction_sha256': lock.pipeline.construction.sha256,
            'lower_bundle_sha256': lock.pipeline.lower_bundle.sha256,
            'current_front_proof_sha256': digest(front), 'source_corners': front['proof']['source_corners'],
            'current_upper_proof_sha256': None if upper is None else digest(upper),
            'complete_lower_meshes': len(lower), 'indexed_shell_count': bundle['proof']['indexed_shell_count'],
            'budget': result['live']['budget'], 'raw_normal_maximum_unit_error': result['raw_normal_max'],
            'source_saved': False, 'all_locked_inputs_unchanged': True,
            'limits': 'Actual final source correspondence before export. Historical shoulder, full assembly/motion, runtime and human acceptance remain separate.',
            'human_approval_reference': None}
