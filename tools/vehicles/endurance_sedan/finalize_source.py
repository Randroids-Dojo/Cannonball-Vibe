"""Native source owner's lower-LOD construction, save and independent reopen."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import traceback

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from endurance_sedan import distance_lod, source_generation as records
from endurance_sedan.qa import distance_lod as checker


def main():
    parser = argparse.ArgumentParser()
    for name in ('input-lock', 'output', 'bundle', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-lock-digest', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    for path in (args.output, args.bundle, args.report):
        records.require(not path.exists(), 'Retain prior source outputs; choose new paths')
    root = Path(__file__).resolve().parents[3]
    lock = records.read(args.input_lock)
    records.require(records.digest(lock) == args.expected_lock_digest, 'External lower input lock differs')
    result = {'schema': 'endurance-sedan-native-finalization38.v1', 'task_id': 'P1-018',
              'utc': datetime.now(timezone.utc).isoformat(), 'status': 'failed',
              'native_version': bpy.app.version_string, 'native_build': bpy.app.build_hash.decode(),
              'input_lock_sha256': records.sha(args.input_lock),
              'expected_lock_digest': args.expected_lock_digest, 'human_approval_reference': None,
              'completed_phases': []}
    previous = time.perf_counter()

    def phase(name):
        nonlocal previous
        current = time.perf_counter()
        row = {'name': name, 'utc': datetime.now(timezone.utc).isoformat(),
               'elapsed_seconds': current - previous}
        result['completed_phases'].append(row)
        previous = current
        print('SEDAN_FINAL_SOURCE_PHASE ' + str(row), flush=True)

    try:
        observations = records.observe_source_checkpoints(root, records.read(lock['roles']['construction']['path']))
        observation_args = records.source_observation_arguments(observations)
        bpy.ops.wm.open_mainfile(filepath=lock['roles']['source']['path'], load_ui=False, use_scripts=False)
        phase('checkpoint-observed-and-current-source-opened')
        context = distance_lod.prepare(lock, expected_lock_digest=args.expected_lock_digest, **observation_args)
        phase('current-source-inputs-verified')
        held = context['context_digest']
        before, materials = checker.capture_originals(context)
        front = distance_lod.verify_current_front(context=context, expected_context_digest=held)
        phase('originals-captured-and-front-fields-verified')
        lower, proof, payload = distance_lod.apply(bpy.data.collections['Asset'],
            {i: bpy.data.objects['Visual_LOD' + str(i)] for i in (0, 1, 2)},
            context=context, expected_context_digest=held)
        records.require(proof['status'] == 'passed-native-construction', 'Final lower budget or geometry failed')
        phase('lower-lods-constructed')
        verified = checker.verify_result(context, before, materials, lower, proof, payload)
        phase('lower-lods-independently-verified-before-save')
        bundle = {'schema': 'endurance-sedan-final-lower38.v1',
                  'original_source': lock['roles']['source'], 'before': before, 'material_before': materials,
                  'proof': proof, 'payload': payload, 'current_front': front,
                  'before_save_verification': verified}
        bpy.context.scene['surface_preview_only'] = False
        bpy.context.scene['source_generation_schema'] = 'endurance-sedan-source-generation-binding.v2'
        bpy.context.scene['prototype_scope'] = (
            'Original Meridian S8R production source with editable rig and verified native lower LODs. '
            'Export, runtime, performance, platform and human approvals have separate evidence.')
        bpy.context.preferences.filepaths.save_version = 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), check_existing=False, compress=True)
        saved = records.file_row(args.output)
        bpy.ops.wm.open_mainfile(filepath=saved['path'], load_ui=False, use_scripts=False)
        phase('final-source-saved-and-reopened')
        final_lock = {**lock, 'roles': {**lock['roles'], 'source': saved}}
        final_context = distance_lod.prepare(final_lock, expected_lock_digest=records.digest(final_lock), **observation_args)
        final_held = final_context['context_digest']
        final_front = distance_lod.verify_current_front(context=final_context, expected_context_digest=final_held)
        phase('reopened-source-inputs-and-front-fields-verified')
        final_lower = [bpy.data.objects[row['name']] for row in payload['meshes']]
        final_verification = checker.verify_result(final_context, before, materials, final_lower, proof, payload)
        phase('reopened-lower-lods-independently-verified')
        records.verify_rows([saved, *lock['roles'].values()])
        bundle.update(final_source=saved, final_front=final_front,
                      reopened_verification=final_verification,
                      final_input_lock=records.portable_lock(final_lock, root))
        records.write(args.bundle, bundle)
        result.update(status='passed', source=records.file_row(args.output, root),
                      bundle=records.file_row(args.bundle, root), budget=proof['live']['budget'],
                      source_correspondence=final_verification['source_correspondence'],
                      indexed_shell_count=proof['indexed_shell_count'],
                      source_reopened=True, source_saves=1, exports=0,
                      source_bytes_unchanged_after_reopen=records.sha(args.output) == saved['sha256'])
    except BaseException as failure:
        result.update(error=type(failure).__name__ + ': ' + str(failure), traceback=traceback.format_exc())
        print(result['traceback'], flush=True)
    finally:
        result['end_utc'] = datetime.now(timezone.utc).isoformat()
        records.write(args.report, result)
        print('SEDAN_FINAL_SOURCE ' + str({'status': result['status'], 'output': str(args.output)}), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
