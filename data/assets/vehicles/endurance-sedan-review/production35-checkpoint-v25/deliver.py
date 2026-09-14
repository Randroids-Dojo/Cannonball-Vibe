"""Bind the completed retained checkpoint into the existing delivery evidence."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path.cwd()
OUT = ROOT / 'data/assets/vehicles/endurance-sedan-review/production35-checkpoint-v25'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
index = json.loads((OUT / 'index.json').read_text())
assert index['status'] == 'passed' and index['byte_reproducible'] is True
records = sorted((ROOT / 'reports/p1-018/commands').glob('*source35-v25-checkpoint-retention.json'))
assert len(records) == 1
command = json.loads(records[0].read_text())
assert command['exit_status'] == 0
for source in (records[0], records[0].with_suffix('.log'), Path(__file__)):
    target = OUT / source.name
    assert not target.exists()
    shutil.copyfile(source, target)

def artifact(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}

p = ROOT / 'evidence/M5/P1-018.json'
evidence = json.loads(p.read_text())
assert evidence['status'] == 'in_progress'
assert 'construction_checkpoint_v25' not in evidence
evidence['construction_checkpoint_v25'] = {
    'utc': datetime.now(timezone.utc).isoformat(),
    'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'git_state': 'V25 working construction inputs before checkpoint commit; archive contains their exact bytes and the corresponding full10 source.',
    'platform': index['platform'], 'status': 'scoped-construction-checkpoint-passed',
    'source_path_in_archive': 'reports/p1-018/source35-full10/source.blend',
    'source_sha256': '26b7fc239a3d88854f00ddfc71dde9bfe25e80e1432255e8ea0236e4348de53e',
    'blender_version': '5.1.2', 'blender_build': 'ec6e62d40fa9',
    'source_qa': {'stages_passed': 20, 'evidence_path_in_archive': 'reports/p1-018/source35-full10/qa20/evidence.json'},
    'windows_front_door': {'steps_passed': 13, 'evidence_path_in_archive': 'reports/p1-018/source35-v25-frontdoor01/m0/summary.json'},
    'metrics': {'lod_triangles': [142828, 30272, 17576], 'collision_triangles': 24,
                'all_shipping_triangles': 190700, 'materials': 24,
                'lod0_limit': 150000, 'all_shipping_limit': 200000, 'material_limit': 32},
    'retained_inputs': len(index['entries']),
    'archive_reproduced_byte_for_byte': True,
    'artifacts': [artifact(OUT / name) for name in ('source-checkpoint-v25.zip', 'manifest.json', 'index.json', records[0].name)],
    'failures_retained': ['Full09 four distant brake-hat meshes each had three self-crossing pairs; repaired by exact selective fallback, then full10 passed all 20 stages.',
                          'Simplified turbo contour visibly degraded; original detailed housings retained.'],
    'remaining': 'Complete assembly repairs, final source35 native/LOD/export/import/runtime/media/performance/platform checks and required human gates remain open. The installed source34 Blender and GLB remain unchanged; their remote asset failure is not declared repaired by this checkpoint.',
    'human_approval_reference': None,
}
p.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({'status': 'checkpoint-bound', 'archive_sha256': index['archives'][0]['sha256'],
                  'evidence_sha256': sha(p), 'entries': len(index['entries'])}))
