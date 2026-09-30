"""Freeze terminal work through fresh05; never capture a live recorder log."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, platform, subprocess

ROOT = Path.cwd(); BASE = ROOT / 'reports/p1-018'; HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def measure(p):
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}

previous_path = ROOT / 'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v26/inventory02.json'
previous = {r['path']: r for r in json.loads(previous_path.read_text())['entries']}
folders = [
    'fresh-construction26-pilot05', 'fresh-controls26-01', 'fresh-controls26-02',
    'cooling-rotor26-composed01', 'rotor-reserve26-proposal01',
    'static-label26-atlas01', 'fascia-form26-pilot01',
    'research/main-radiator26-field01', 'research/source-display26-reopen01',
    'research/fresh26-sump-diagnostic01', 'research/roof-render26-review01/cooler01',
    'qa/rotor-reserve26-review01', 'qa/static-label26-review01',
    'qa/fascia-form26-review01', 'qa/roof-shoulder26-proposal01',
]
entries = {}; reused = {}; omitted = []; coverage = []
def add(path):
    assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT)
    row = measure(path)
    if previous.get(row['path']) == row:
        reused[row['path']] = row
    else:
        entries[row['path']] = row

skip = {'.git', '.godot', '.venv', 'node_modules', '__pycache__', 'home', '.tools'}
for relative in folders:
    folder = BASE / relative
    assert folder.is_dir(), folder
    count = 0
    for dirname, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(n for n in dirnames if n not in skip)
        for name in sorted(filenames):
            p = Path(dirname) / name
            if p.suffix in ('.pyc', '.blend1', '.blend2'):
                omitted.append({'path': p.relative_to(ROOT).as_posix(), 'reason': 'Derived bytecode or automatic backup, source revisions retained'})
                continue
            add(p); count += 1
    coverage.append({'folder': folder.relative_to(ROOT).as_posix(), 'files': count})

terminal = BASE / 'runtime/lod-normal26-diagnosis01/checkpoint56-inventory.json'
assert sha(terminal) == '3fb4e7b875e576427fdb0c8e28ea06497283b56ddfd3f6771bf634f22c2bf42f'
add(terminal)
snapshot_map = []
for record in json.loads(terminal.read_text())['files']:
    p = ROOT / record['path']
    assert sha(p) == record['sha256'] and p.stat().st_size == record['bytes'], p
    if p.is_relative_to(BASE):
        add(p)
    else:
        target = HERE / 'input-snapshot' / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f: f.write(p.read_bytes())
        add(target)
        snapshot_map.append({'original_path': p.relative_to(ROOT).as_posix(), 'retained': measure(target)})

# Retain only completed command envelopes and their verified closed log bytes.
terminal_commands = []
for p in sorted((BASE / 'commands').glob('*.json')):
    if p.name < '20260912T184652': continue
    record = json.loads(p.read_text())
    if not all(k in record for k in ('exit_status', 'end_utc', 'log', 'log_sha256')): continue
    log = ROOT / record['log']
    assert sha(log) == record['log_sha256'], log
    add(p); add(log)
    terminal_commands.append({'record': p.relative_to(ROOT).as_posix(), 'exit_status': record['exit_status']})

for relative in ['docs/DELIVERY_LEDGER.json', 'evidence/M5/P1-018.json',
                 'docs/vehicles/endurance-sedan/defects.json',
                 'docs/vehicles/endurance-sedan/refinement-review-v26.md',
                 'tools/vehicles/endurance_sedan/retain_evidence.py',
                 'tools/vehicles/endurance_sedan/qa/source_controls.py',
                 'tools/vehicles/endurance_sedan/qa/source_lights.py']:
    source = ROOT / relative
    target = HERE / 'input-snapshot' / relative
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f: f.write(source.read_bytes())
    assert sha(target) == sha(source)
    add(target)
    snapshot_map.append({'original_path': relative, 'retained': measure(target)})
for p in [Path(__file__), HERE / 'build.py']: add(p)
rows = [entries[k] for k in sorted(entries)]
assert len({r['path'].casefold() for r in rows}) == len(rows)
record = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
          'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
          'platform': platform.platform(), 'entries': rows,
          'input_count': len(rows), 'input_bytes': sum(r['bytes'] for r in rows),
          'previous_inventory': measure(previous_path), 'unchanged_previous_payloads': list(reused.values()),
          'snapshots': snapshot_map, 'terminal_commands': terminal_commands,
          'folders': coverage, 'omitted_derived_files': omitted,
          'excluded_live_work': ['qa/roof-joined26-proposal01', 'research/brake-edge26-proposal01',
                                 'runtime/lod-normal26-diagnosis01 beyond explicit terminal checkpoint56 inventory'],
          'scope': 'Incremental editable fresh05 construction, labels, cooling and component fit evidence; actual native stills; failed attempts and recovery; rejected roof/fascia/LOD prototypes. No final full-source, shipping GLB, runtime or human acceptance.',
          'human_approval_reference': None}
inventory = HERE / 'inventory.json'
with inventory.open('x', encoding='utf-8', newline='\n') as f:
    json.dump(record, f, indent=2); f.write('\n')
parts = []; part = []; size = 0
for row in rows:
    if part and size + row['bytes'] > 128 * 1024 * 1024:
        parts.append(part); part = []; size = 0
    part.append(row); size += row['bytes']
if part: parts.append(part)
for number, part in enumerate(parts, 1):
    item = {'task_id': 'P1-018', 'scope': record['scope'], 'inventory_path': inventory.relative_to(ROOT).as_posix(),
            'inventory_sha256': sha(inventory), 'part': number, 'parts': len(parts), 'entries': part}
    with (HERE / f'manifest-{number:02}.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(item, f, indent=2); f.write('\n')
print(json.dumps({'files': len(rows), 'bytes': record['input_bytes'], 'parts': len(parts),
                  'previous_files_referenced': len(reused), 'inventory_sha256': sha(inventory)}), flush=True)
