"""Freeze completed native art work and failures; exclude live agent outputs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,platform,subprocess

ROOT=Path.cwd();BASE=ROOT/'reports/p1-018';HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
excluded_roots={'art-checkpoint26-retention01','camera26-frontdoor01','camera26-retention01',
 'lifecycle26-frontdoor01','lifecycle26-promotion01','lifecycle26-retention01',
 'save-clock26-retention01','qa26-frontdoor01'}
folders=[p for p in BASE.iterdir() if p.is_dir() and '26' in p.name and p.name not in excluded_roots]
folders += [p for p in (BASE/'qa').iterdir() if p.is_dir() and '26' in p.name and p.name!='composition26-current01']
folders += [p for p in (BASE/'research').iterdir() if p.is_dir() and '26' in p.name]
runtime_names=['detail-reserve26-next01','brake-field26-visual01','rear-lip26-surface01',
               'trunk-rib26-fit01','source-qa26-integration-proposal01']
folders += [BASE/'runtime'/name for name in runtime_names]
live=BASE/'research/roof-render26-review01/cooler01'
entries={};omissions=[];coverage=[]
def measure(path):
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size}
for folder in sorted(folders):
    assert folder.is_dir() and folder.resolve().is_relative_to(BASE)
    count=0
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.is_relative_to(live):continue
        assert not path.is_symlink() and path.resolve().is_relative_to(BASE)
        row=measure(path)
        if '__pycache__' in path.parts or path.suffix=='.pyc':
            omissions.append({**row,'reason':'Generated Python bytecode cache; source retained'})
            continue
        assert not any(part in ('.git','.venv','.godot','node_modules') for part in path.parts),str(path)
        entries[row['path']]=row;count+=1
    coverage.append({'folder':folder.relative_to(ROOT).as_posix(),'files':count})
for path in sorted((BASE/'commands').iterdir()):
    if path.is_file() and path.name>='20260912T101100' and path.suffix in ('.json','.log'):
        row=measure(path);entries[row['path']]=row
snap=HERE/'input-snapshot'
for relative in ['docs/DELIVERY_LEDGER.json','evidence/M5/P1-018.json',
                 'docs/vehicles/endurance-sedan/defects.json','docs/vehicles/endurance-sedan/refinement-review-v26.md',
                 'docs/vehicles/endurance-sedan/specification.json','tools/vehicles/endurance_sedan/render.py']:
    source=ROOT/relative;target=snap/relative;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(source.read_bytes())
    row=measure(target);entries[row['path']]=row
for path in sorted((ROOT/'tools/vehicles/endurance_sedan/qa').rglob('*')):
    if path.is_file() and path.suffix in ('.py','.json'):
        target=snap/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(path.read_bytes())
        row=measure(target);entries[row['path']]=row
row=measure(Path(__file__));entries[row['path']]=row
rows=[entries[k] for k in sorted(entries)]
assert len({r['path'].casefold() for r in rows})==len(rows)
record={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
        'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'platform':platform.platform(),'entries':rows,'input_count':len(rows),
        'input_bytes':sum(r['bytes'] for r in rows),'folders':coverage,'omitted_caches':omissions,
        'excluded_live_directories':[live.relative_to(ROOT).as_posix(),'reports/p1-018/qa/composition26-current01',
                                     'reports/p1-018/runtime/lifecycle26-platform02'],
        'scope':'Completed art experiments, failed attempts, component proofs, actual renders, native source files and construction recipes through composed148948-triangle checkpoint. Retention only; not final shipping/whole-asset or human acceptance.',
        'human_approval_reference':None}
with (HERE/'inventory.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
# Bound each part by uncompressed payload so individual retained artifacts stay manageable.
parts=[];part=[];size=0
for row in rows:
    if part and size+row['bytes']>128*1024*1024:parts.append(part);part=[];size=0
    part.append(row);size+=row['bytes']
if part:parts.append(part)
for i,part in enumerate(parts,1):
    doc={'task_id':'P1-018','scope':record['scope'],'inventory_path':(HERE/'inventory.json').relative_to(ROOT).as_posix(),
         'inventory_sha256':sha(HERE/'inventory.json'),'part':i,'parts':len(parts),'entries':part}
    with (HERE/f'manifest-{i:02}.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(doc,f,indent=2);f.write('\n')
print(json.dumps({'input_count':len(rows),'input_bytes':record['input_bytes'],'parts':len(parts),
                  'cache_omissions':len(omissions),'inventory_sha256':sha(HERE/'inventory.json')}),flush=True)
