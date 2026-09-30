"""Retain incremental terminal evidence twice, then compare every archive byte."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess, sys

ROOT = Path.cwd(); HERE = Path(__file__).resolve().parent
OUT = ROOT / 'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v32'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
inventory = HERE / 'inventory.json'; lock = json.loads(inventory.read_text()); parts = []
assert not OUT.exists()
for manifest in sorted(HERE.glob('manifest-*.json')):
    number = int(manifest.stem.split('-')[1])
    target = OUT / f'art-checkpoint-v32-{number:02}.zip'
    repeat = HERE / f'art-checkpoint-v32-{number:02}-repeat.zip'
    index = OUT / f'index-{number:02}.json'
    command = [sys.executable, 'tools/vehicles/endurance_sedan/retain_evidence.py',
               '--manifest', str(manifest.relative_to(ROOT)), '--output', str(target.relative_to(ROOT)),
               '--repeat-output', str(repeat.relative_to(ROOT)), '--index', str(index.relative_to(ROOT))]
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, cwd=ROOT, check=False)
    command_record = {'part': number, 'command': command, 'started_utc': started,
                      'finished_utc': datetime.now(timezone.utc).isoformat(), 'exit_status': result.returncode}
    with (HERE / f'command-{number:02}.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(command_record, f, indent=2); f.write('\n')
    assert result.returncode == 0
    data = json.loads(index.read_text())
    assert data['status'] == 'passed' and data['byte_reproducible']
    with target.open('rb') as a, repeat.open('rb') as b:
        while block := a.read(1024 * 1024): assert block == b.read(1024 * 1024)
        assert not b.read(1)
    parts.append({**command_record, 'archive': data['archives'][0], 'repeat': data['archives'][1],
                  'index': {'path': index.relative_to(ROOT).as_posix(), 'sha256': sha(index)},
                  'entries': len(data['entries']), 'manifest_sha256': sha(manifest),
                  'every_archive_byte_compared': True})
    print('RETAINED_PART ' + str(number), flush=True)
for row in lock['entries']:
    p = ROOT / row['path']
    assert sha(p) == row['sha256'] and p.stat().st_size == row['bytes']
record = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
          'git_revision': lock['git_revision'], 'platform': lock['platform'],
          'inventory': {'path': inventory.relative_to(ROOT).as_posix(), 'sha256': sha(inventory)},
          'parts': parts, 'all_parts_directly_byte_compared': True,
          'all_members_sha256_and_crc_verified_twice': True,
          'entry_count': sum(p['entries'] for p in parts),
          'archive_bytes': sum(p['archive']['bytes'] for p in parts),
          'retention_retries': 0, 'scope': lock['scope'], 'human_approval_reference': None}
assert record['entry_count'] == lock['input_count']
with (OUT / 'index.json').open('x', encoding='utf-8', newline='\n') as f:
    json.dump(record, f, indent=2); f.write('\n')
for name in ('inventory.json', 'prepare.py', 'build.py'):
    with (OUT / name).open('xb') as f: f.write((HERE / name).read_bytes())
print(json.dumps({'parts': len(parts), 'entries': record['entry_count'], 'archive_bytes': record['archive_bytes']}), flush=True)
