"""Lead verifies every retained byte before promoting a bounded evidence archive."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import zipfile

root = Path.cwd()
here = Path(__file__).resolve().parent
packet = root / 'reports/p1-018/lifecycle26-retention01'
destination = root / 'data/assets/vehicles/endurance-sedan-review/lifecycle-checkpoint-v26'
assert not destination.exists()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
archive = packet / 'lifecycle-checkpoint-v26.zip'
repeat = packet / 'lifecycle-checkpoint-v26-repeat.zip'
expected = '8d59a307e58f5e988f2d476e73bec4f87c8e9448c5b2d1370dec1f2e8d527af3'
assert sha(archive) == sha(repeat) == expected
manifest_path = packet / 'manifest.json'
assert sha(manifest_path) == 'e198930cc6d78133af829cb0edbe49d6b62f007513f6b9ca4b4b85fd572977ef'
manifest = json.loads(manifest_path.read_text(encoding='utf8'))
members = json.loads((packet / 'members01.json').read_text(encoding='utf8'))['members']
checks = []
for path in (archive, repeat):
    with zipfile.ZipFile(path) as z:
        assert len(z.infolist()) == len({i.filename for i in z.infolist()}) == 894
        assert z.testzip() is None
        for entry in manifest['input_files']:
            value = z.read(entry['path'])
            assert len(value) == entry['bytes'] and hashlib.sha256(value).hexdigest() == entry['sha256'], entry['path']
        extra = set(z.namelist()) - {entry['path'] for entry in manifest['input_files']}
        assert len(extra) == 1
        assert z.read(next(iter(extra))) == manifest_path.read_bytes()
        checks.append({'path': str(path), 'sha256': sha(path), 'members_crc_sha_passed': 894})
m0 = json.loads((root / 'reports/p1-018/lifecycle26-frontdoor01/evidence.json').read_text(encoding='utf8'))
assert m0['exit_status'] == 0 and not m0['changed_inputs'] and len(m0['m0_summary']['steps']) == 13
runtime_paths = [entry for entry in m0['working_inputs'] if entry['path'].startswith(('addons/playgodot/', 'automation/playgodot/'))]
assert len(runtime_paths) == 5
assert all(sha(root / entry['path']) == entry['sha256'] for entry in runtime_paths)
destination.mkdir(parents=True)
files = ['lifecycle-checkpoint-v26.zip', 'manifest.json', 'index.json', 'verification01.json', 'HANDOFF02.md', 'AUDIT01.md']
for name in files:
    shutil.copyfile(packet / name, destination / name)
    assert sha(packet / name) == sha(destination / name)
result = {'task_id': 'P1-018', 'utc': datetime.now(timezone.utc).isoformat(),
    'status': 'lead_independent_retention_readback_passed', 'archives': checks,
    'promoted': [{'path': (destination / name).relative_to(root).as_posix(), 'sha256': sha(destination / name)} for name in files],
    'runtime_tested_inputs_unchanged': runtime_paths, 'm0_full_steps_passed': 13,
    'scope': 'Native Windows runtime corrections and retained prior platform diagnosis; not final sedan or current cross-platform acceptance.',
    'human_approval_reference': None}
for target in (here / 'verification.json', destination / 'lead-verification.json'):
    target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'status': result['status'], 'archive_sha256': expected, 'members_per_archive': 894}), flush=True)
