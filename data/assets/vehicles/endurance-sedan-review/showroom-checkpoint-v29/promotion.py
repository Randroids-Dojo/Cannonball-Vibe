"""Publish the retained viewer checkpoint without closing P1-018."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

root = Path.cwd().resolve(); here = Path(__file__).resolve().parent
out = root / 'data/assets/vehicles/endurance-sedan-review/showroom-checkpoint-v29'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def item(p):
    return {'path': p.relative_to(root).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}
index = json.loads((out / 'index.json').read_text())
assert index['entry_count'] == 979 and index['all_parts_directly_byte_compared']
assert index['all_members_sha256_and_crc_verified_twice']
commands = {
    'retention': root / 'reports/p1-018/commands/20260913T041225.689128Z-showroom29-retain-twice.json',
    'frontdoor': root / 'reports/p1-018/commands/20260913T035451.287935Z-showroom29-final-windows-frontdoor.json',
}
for name, path in commands.items():
    record = json.loads(path.read_text()); assert record['exit_status'] == 0
    assert sha(root / record['log']) == record['log_sha256']
    for source, target in ((path, out / (name + '-command.json')), (path.with_suffix('.log'), out / (name + '-command.log'))):
        with target.open('xb') as stream: stream.write(source.read_bytes())
utc = datetime.now(timezone.utc).isoformat()
runtime = root / 'reports/p1-018/runtime/showroom29-plan01'
checkpoint = {
    'utc': utc, 'git_base_revision': index['git_revision'], 'platform': index['platform'],
    'status': 'windows_viewer_verified_with_open_art_platform_and_human_gates',
    'index': item(out / 'index.json'),
    'documentation': 'docs/vehicles/endurance-sedan/showroom-checkpoint-v29.md',
    'source_scene': 'game/Vehicle/Showroom/VehicleShowroom.tscn',
    'tools': {'godot': '4.7.1.stable.mono.official.a13da4feb', 'dotnet_sdk': '10.0.102',
              'uv': '0.9.24', 'git_lfs': '3.7.1', 'renderer': 'forward_plus',
              'workstation_gpu': 'NVIDIA GeForce RTX 3080 Ti'},
    'input_output_retention': {'files': index['entry_count'], 'archive_bytes': index['archive_bytes'],
                               'archives': len(index['parts']), 'literal_identical_builds': 2,
                               'every_member_sha256_and_crc_verified_twice': True},
    'final_windows_frontdoor': {
        'command': item(out / 'frontdoor-command.json'), 'exit_status': 0, 'steps_passed': 13,
        'summary': item(root / 'reports/p1-018/showroom29-frontdoor02/summary.json'),
        'unchanged_source_hashes': item(root / 'reports/p1-018/showroom29/frontdoor02-bindings.json'),
    },
    'native_evidence': {
        'complete_sequence': item(runtime / 'handoff13/readback.json'),
        'final_focused_delta': item(runtime / 'lighting17-handoff/readback.json'),
        'complete_runtime_inventory': item(root / 'reports/p1-018/runtime/showroom29-terminal-inventory18/manifest.json'),
        'independent_visual_qa': item(root / 'reports/p1-018/qa/showroom29-review01/REVIEW16.md'),
        'independent_qa_inventory': item(root / 'reports/p1-018/qa/showroom29-review01/retention16.json'),
        'full_forward_plus_sequence_pass_seconds': 86.97,
        'unchanged_variant_regression_pass_seconds': 37.63,
        'final_focused_forward_plus_pass_seconds': 35.28,
        'full_sequence_unchanged_inputs': 55,
        'final_focused_unchanged_inputs': 55,
        'launcher_client_controls_passed': 129,
    },
    'failure_and_recovery': [
        'Native03 initialization/NOT_FOUND and cleanup diagnostics,04 stale immediate camera observation and05 unsupported test key remain retained; corrected06/07 complete.',
        'Native08 exact screenshot limit and separate Windows long-path cleanup failure remain retained. Native09 passes cleanup after the bounded path fix but fails camera-settling equality.',
        'Convergence10 reproduces1.728mm camera drift; capture11 waits for complete unchanged-pose convergence without changing the RPC limit or51 canonical assertions. Native11 then passes.',
        'Final1440 cockpit full-UI PNG still exceeds the unchanged limit; retain its actual UI-free Photo and separately verify full-UI cockpit at1280x720. No missing image is represented as a visual pass.',
    ],
    'metrics_scope': 'Fourteen short debug windows; monotonic frame intervals, private viewport render counters and sampled process memory with concurrent user apps. VSync1/fps_cap0. Not GPU timing or reference-PC acceptance.',
    'metrics': {'frame_p95_range_ms': [17.6175, 18.0232], 'sampled_working_set_high_range_mib': [921.512, 934.887],
                'render_video_high_range_mib': [590.569, 608.986], 'viewport_draw_calls_range': [83, 157]},
    'limitations': [
        'Installed production34 artwork is unchanged; newer Blender prototypes and their failures are not integrated by this viewer checkpoint.',
        'Night broad-panel readability and strong reflection glare remain open.',
        'Actual pointer/wheel/focus-loss/live-resize black-box checks were unavailable because the configured native Computer Use pipe could not connect.',
        'Current revision remote platform checks, Q-047 showroom budget, full final source/export/runtime/driving performance and all required human gates remain open.',
        'Archive repeatability is evidence retention, not a new shipping-GLB reproducibility claim.',
    ],
    'human_approval_reference': None,
}
p = root / 'evidence/M5/P1-018.json'; data = json.loads(p.read_text(encoding='utf-8'))
assert 'interactive_showroom_checkpoint_v29' not in data
data['interactive_showroom_checkpoint_v29'] = checkpoint
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
p = root / 'docs/DELIVERY_LEDGER.json'; data = json.loads(p.read_text(encoding='utf-8'))
task = next(t for t in data['tasks'] if t['id'] == 'P1-018'); assert task['status'] == 'in_progress'
task['notes'] += (' ' + utc + ': Interactive showroom checkpoint v29 retains979 files in a twice-built byte-identical archive. Final Windows13-step check.sh passes; full rendered keyboard/controller/opening/modal checks and sedan/Hero/graybox regression pass. Final targeted cockpit/notice corrections have actual evidence; night/reflection/source defects, remote revision/platform/performance and human gates stay open. See docs/vehicles/endurance-sedan/showroom-checkpoint-v29.md and M5 interactive_showroom_checkpoint_v29. DraftPR144 remains in progress with the installed production34 art unchanged.')
data['updated'] = utc[:10]
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
with (out / 'promotion.py').open('xb') as stream: stream.write(Path(__file__).read_bytes())
print(json.dumps({'status': task['status'], 'checkpoint': 'v29', 'archive_bytes': index['archive_bytes'], 'utc': utc}))
