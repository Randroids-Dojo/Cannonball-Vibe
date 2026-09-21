"""Freeze only terminal viewer evidence and current source inputs for retention."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import platform
import subprocess

ROOT = Path.cwd().resolve(); HERE = Path(__file__).resolve().parent
assert ROOT == Path('C:/Dev/Cannonball-Vibe-sedan')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
entries = {}; omitted = []; snapshots = []
def measure(p):
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}
def add(p):
    p = p.resolve(strict=True)
    assert p.is_file() and p.is_relative_to(ROOT) and not p.is_symlink()
    row = measure(p)
    if row['path'] in entries: assert row == entries[row['path']]
    entries[row['path']] = row
def walk(folder):
    assert folder.is_dir()
    for dirname, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in {'.git', '.godot', '.venv', '__pycache__', '.tools', 'home', 'node_modules'})
        for name in sorted(files):
            p = Path(dirname) / name
            if p.suffix in {'.pyc', '.blend1', '.blend2'}:
                omitted.append({'path': p.relative_to(ROOT).as_posix(), 'reason': 'Regenerable bytecode or automatic backup'})
            else: add(p)
manifests = [
    ('reports/p1-018/runtime/showroom29-terminal-inventory18/manifest.json', '8cf3b0e10bc6e998e97e314b6437a6897328cc841d294afe0530e98ec4135f5b'),
    ('reports/p1-018/qa/showroom29-review01/retention16.json', '4a5b00367a4379c50e7065cc0aafa25f534ee3ad995a9189ab69bff66a91ef82'),
]
for relative, digest in manifests:
    p = ROOT / relative; assert sha(p) == digest
    add(p)
    for row in json.loads(p.read_text(encoding='utf-8'))['files']:
        q = ROOT / row['path']
        assert q.stat().st_size == row['bytes'] and sha(q) == row['sha256'], q
        add(q)
for relative in ('showroom29', 'showroom29-frontdoor01', 'showroom29-frontdoor02',
                 'runtime/showroom29-terminal-inventory18'):
    walk(ROOT / 'reports/p1-018' / relative)
for relative in ('reports/p1-018/user-showroom29-01/launch.py',
                 'reports/p1-018/user-showroom29-01/launch.json',
                 'reports/p1-018/user-showroom29-01/verified01.json'):
    add(ROOT / relative)
terminal_commands = []
for p in sorted((ROOT / 'reports/p1-018/commands').glob('*.json')):
    record = json.loads(p.read_text(encoding='utf-8'))
    if 'showroom29' not in p.name: continue
    assert all(k in record for k in ('exit_status', 'end_utc', 'log', 'log_sha256')), p
    q = ROOT / record['log']; assert sha(q) == record['log_sha256']
    add(p); add(q)
    terminal_commands.append({'record': p.relative_to(ROOT).as_posix(), 'exit_status': record['exit_status']})
current = [*sorted((ROOT / 'game/Vehicle/Showroom').glob('*')),
           *(ROOT / relative for relative in (
               'game/Main.cs', 'game/Vehicle/VehicleInspectionPanel.cs',
               'automation/playgodot/src/cannonball_playgodot/launcher.py',
               'automation/playgodot/tests/test_launcher.py', 'automation/playgodot/tests/test_vehicle_showroom.py',
               'docs/DELIVERY_LEDGER.json', 'docs/OPEN_QUESTIONS.md',
               'docs/vehicles/endurance-sedan/README.md', 'docs/vehicles/endurance-sedan/acceptance.json',
               'docs/vehicles/endurance-sedan/defects.json', 'docs/vehicles/endurance-sedan/showroom-plan.md',
               'docs/vehicles/endurance-sedan/showroom-checkpoint-v29.md',
               'tools/vehicles/endurance_sedan/retain_evidence.py',
               'project.godot', 'global.json', 'Cannonball.csproj'))]
for p in current:
    assert p.is_file()
    target = HERE / 'input-snapshot' / p.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream: stream.write(p.read_bytes())
    assert sha(target) == sha(p)
    add(target); snapshots.append({'original_path': p.relative_to(ROOT).as_posix(), 'retained': measure(target)})
for name in ('prepare.py', 'build.py'): add(HERE / name)
rows = [entries[k] for k in sorted(entries)]
assert len({row['path'].casefold() for row in rows}) == len(rows)
record = {
    'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
    'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'platform': platform.platform(), 'entries': rows, 'input_count': len(rows),
    'input_bytes': sum(row['bytes'] for row in rows), 'snapshots': snapshots,
    'terminal_commands': terminal_commands, 'omitted_derived_files': omitted,
    'explicit_agent_manifests': [{'path': path, 'sha256': digest} for path, digest in manifests],
    'scope': 'Interactive showroom source, actual Windows control/render/photo/cleanup evidence, exact final Windows front door, independent visual review and retained failures. Installed production34 is unchanged. No final sedan-art, reference-PC, remote platform or human acceptance.',
    'excluded_live_work': ['All current Blender construction/roof/front localization work and unretained later art trials.',
                           'Live user showroom/driving stdout and stderr; only immutable launch/verification receipts retained.',
                           'Original native08 residual disposable profile; its existing hash inventory is retained without altering it.'],
    'human_approval_reference': None,
}
inventory = HERE / 'inventory.json'
with inventory.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(record, stream, indent=2); stream.write('\n')
parts = []; part = []; size = 0
for row in rows:
    if part and size + row['bytes'] > 128 * 1024 * 1024:
        parts.append(part); part = []; size = 0
    part.append(row); size += row['bytes']
if part: parts.append(part)
for number, part in enumerate(parts, 1):
    value = {'task_id': 'P1-018', 'scope': record['scope'], 'inventory_path': inventory.relative_to(ROOT).as_posix(),
             'inventory_sha256': sha(inventory), 'part': number, 'parts': len(parts), 'entries': part}
    with (HERE / f'manifest-{number:02}.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
print(json.dumps({'files': len(rows), 'bytes': record['input_bytes'], 'parts': len(parts), 'inventory_sha256': sha(inventory)}))
