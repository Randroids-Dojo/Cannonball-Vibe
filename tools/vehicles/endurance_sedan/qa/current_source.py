"""Read-only native current-front and saved lower-source correspondence stages."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import load_source_binding, sha


def load_independent_checker():
    path = Path(__file__).resolve().with_name('distance_lod.py')
    if not path.is_file():
        raise ValueError('Missing staged distance-LOD checker')
    expected_sha = sha(path)
    name = 'endurance_sedan.qa._source_qa_distance_lod'
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load staged distance-LOD checker')
    checker = importlib.util.module_from_spec(spec)
    sys.modules[name] = checker
    try:
        spec.loader.exec_module(checker)
        if not callable(getattr(checker, 'verify_result', None)):
            raise ValueError('Staged distance-LOD checker has no verifier')
        if Path(checker.__file__).resolve() != path or sha(path) != expected_sha:
            raise ValueError('Staged distance-LOD checker changed while loading')
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return checker, {'path': str(path), 'sha256': expected_sha,
                     'bytes': path.stat().st_size, 'module': name}


def main():
    parser = argparse.ArgumentParser()
    for name in ('source', 'source-binding', 'construction-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-binding-sha256', required=True)
    parser.add_argument('--mode', choices=('front', 'lower'), required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert not args.output.exists() and sha(args.source_binding) == args.expected_binding_sha256
    lock = load_source_binding(args.source_binding, args.source, args.construction_root,
                               args.output.parent / ('unused-preflight-' + args.mode))
    assert lock.pipeline is not None
    sys.path.insert(1, str(lock.root / 'tools/vehicles'))
    from endurance_sedan import distance_lod, source_generation as records, shoulder_field02
    from endurance_sedan.qa import shoulder_checkpoint
    checker, checker_input = load_independent_checker()
    native_lock = records.absolute_lock(lock.pipeline.portable_input_lock, lock.root)
    expected = records.digest(native_lock)
    construction = records.read(lock.pipeline.construction.path)
    result = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
              'mode': args.mode, 'source_sha256': lock.source.sha256,
              'source_binding_sha256': lock.binding.sha256, 'source_saved': False,
              'blender_version': bpy.app.version_string, 'blender_build': bpy.app.build_hash.decode(),
              'independent_checker': checker_input,
              'human_approval_reference': None}
    if args.mode == 'front':
        pre_front = lock.pipeline.pre_front
        bpy.ops.wm.open_mainfile(filepath=str(pre_front.path), load_ui=False, use_scripts=False)
        actual = shoulder_checkpoint.native_state(bpy.data.objects['LOD0_FrontBumper'], shoulder_field02)
        records.require(actual == construction['front_before_native'],
                        'Actual pre-front source differs from the current-chain starting checkpoint')
        result.update(pre_front_source_sha256=pre_front.sha256,
                      actual_pre_front_checkpoint_exact=True)
    observation = records.observe_high_tire_checkpoint(lock.root, construction)
    bpy.ops.wm.open_mainfile(filepath=str(lock.source.path), load_ui=False, use_scripts=False)
    context = distance_lod.prepare(native_lock, expected_lock_digest=expected,
                                   **records.observation_arguments(observation))
    result['native_high_tire_checkpoint_observed'] = observation is not None
    held = context['context_digest']
    if args.mode == 'front':
        payload = distance_lod.verify_current_front(context=context, expected_context_digest=held)
        result['source_corners'] = payload['proof']['source_corners']
    else:
        bundle = records.read(lock.pipeline.lower_bundle.path)
        lower = [bpy.data.objects[row['name']] for row in bundle['payload']['meshes']]
        payload = checker.verify_result(context, bundle['before'], bundle['material_before'],
                                        lower, bundle['proof'], bundle['payload'])
        result.update(complete_final_lower_count=len(lower),
                      indexed_shell_count=bundle['proof']['indexed_shell_count'],
                      budget=payload['live']['budget'])
    records.require(sha(Path(checker_input['path'])) == checker_input['sha256'],
                    'Staged distance-LOD checker changed during verification')
    lock.verify()
    payload_path = args.output.with_suffix('.payload.json.gz')
    records.write(payload_path, payload)
    result.update(status='passed', all_locked_inputs_unchanged=True, payload=records.file_row(payload_path))
    records.write(args.output, result)
    print('SEDAN_CURRENT_SOURCE ' + str({'mode': args.mode, 'status': 'passed'}), flush=True)


if __name__ == '__main__':
    main()
