"""Freeze completed form/UV/LOD investigations and the coherent editable pilot."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, platform, subprocess

ROOT=Path.cwd().resolve(); BASE=ROOT/'reports/p1-018'; HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def measure(p):return {'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
previous_paths=[ROOT/'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v26/inventory02.json',ROOT/'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v27/inventory.json']
previous={}
for p in previous_paths:
    for row in json.loads(p.read_text())['entries']:previous[row['path']]=row
folders=[
 'arch-field29-pilot01','body-c29-pilot01','c-form29-pilot01','combined-form29-pilot01',
 'door-field29-diagnosis01','door-field29-proposal01','door-field29-proposal02',
 'form29-review01','form29-review02','fresh-visible28-01','front-ideal28-pilot01',
 'front-joined29-pilot01','front-sheet29-pilot01','front-source28-inventory01',
 'geometry-review-29','geometry-scope28-01','rear-corner29-diagnosis01',
 'rear-field29-diagnosis01','rear-field29-proposal01','rear-field29-proposal02',
 'roof-field29-pilot01','source-economy28-pilot01','source28-inputs','tire29-view-pilot01','valance-field29-proposal01',
 'qa/c-pressing28-proposal01','qa/c-quarter28-planning01','qa/front-field29-trace01',
 'qa/front-joined29-localization01','qa/front-sheet29-proposal02','qa/front-transition29-proposal01',
 'qa/front-highlight29-diagnosis03','qa/body-c29-visual02','qa/tire29-visual01','qa/valance-field29-review01',
 'runtime/distance-lod29-callable01','runtime/front-lod29-contract01','runtime/lod-source29-plan01',
 'runtime/mixed-front-lod29-proposal01','runtime/distance-lod29-reserve01',
 'research/front-joined29-diagnosis01','research/front-shoulder28-artifact01',
 'research/tire-reserve29-proposal01','research/c-quarter29-patch-proposal01',
]
entries={};reused={};omitted=[];coverage=[]
def add(p):
    assert p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(ROOT),p
    row=measure(p)
    if previous.get(row['path'])==row:reused[row['path']]=row
    else:entries[row['path']]=row
skip={'.git','.godot','.venv','node_modules','__pycache__','home','.tools'}
for relative in folders:
    folder=BASE/relative;assert folder.is_dir(),folder;count=0
    for dirname,dirnames,filenames in os.walk(folder):
        dirnames[:]=sorted(n for n in dirnames if n not in skip)
        for name in sorted(filenames):
            p=Path(dirname)/name
            if p.suffix in ('.pyc','.blend1','.blend2'):
                omitted.append({'path':p.relative_to(ROOT).as_posix(),'reason':'Derived bytecode or automatic backup; actual source revisions retained'});continue
            add(p);count+=1
    coverage.append({'folder':folder.relative_to(ROOT).as_posix(),'files':count})

# Independent frozen manifests ensure that every lane's declared payload exists.
frozen=[]
for relative,expected in [
 ('runtime/distance-lod29-reserve01/manifest05.json','cfb7beac18e87a38da918aba2c1e1c548883632164f3ec79a5c45565d3b4bf77'),
 ('runtime/distance-lod29-reserve01/uv-proposal06/manifest03.json','32e38ab3621a3cc07e02552f938ab5b3749e03e76875f39cef67bf460cb05fa5'),
 ('research/c-quarter29-patch-proposal01/handoff94.json','dc283993e0599adf8a53f7fb23b4161d6cc774d9449217d55af01bf70bec343f'),
 ('qa/front-sheet29-proposal02/retention13.json','baaa5a5e967c8eefb9a32e3a4346a1c43e8661cc61badfda93718c51b8141a79'),
]:
    p=BASE/relative;assert sha(p)==expected,p;frozen.append(measure(p));add(p)
    data=json.loads(p.read_text());rows=data.get('files',data.get('required_files',[]))
    assert isinstance(rows,list),relative
    for row in rows:
        if 'path' not in row or 'sha256' not in row:raise ValueError(('Incomplete frozen manifest row',relative,row))
        target=ROOT/row['path'];assert sha(target)==row['sha256'],target
        if 'bytes' in row:assert target.stat().st_size==row['bytes'],target
        add(target)

terminal_commands=[]
for p in sorted((BASE/'commands').glob('*.json')):
    if p.name<'20260912T220000':continue
    record=json.loads(p.read_text())
    if not all(k in record for k in ('exit_status','end_utc','log','log_sha256')):continue
    log=ROOT/record['log'];assert sha(log)==record['log_sha256'],log
    add(p);add(log);terminal_commands.append({'record':p.relative_to(ROOT).as_posix(),'exit_status':record['exit_status']})
snapshots=[]
for relative in ['docs/DELIVERY_LEDGER.json','evidence/M5/P1-018.json','docs/vehicles/endurance-sedan/defects.json',
                 'docs/vehicles/endurance-sedan/specification.json','tools/vehicles/endurance_sedan/retain_evidence.py',
                 'tools/vehicles/endurance_sedan/render.py','tools/vehicles/run_recorded.py']:
    source=ROOT/relative;target=HERE/'input-snapshot'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f:f.write(source.read_bytes())
    assert sha(source)==sha(target);add(target);snapshots.append({'original_path':relative,'retained':measure(target)})
for p in (Path(__file__),HERE/'build.py'):add(p)
rows=[entries[k] for k in sorted(entries)]
assert len({r['path'].casefold() for r in rows})==len(rows)
record={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
 'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'platform':platform.platform(),
 'entries':rows,'input_count':len(rows),'input_bytes':sum(r['bytes'] for r in rows),
 'previous_inventories':[measure(p) for p in previous_paths],'unchanged_previous_payloads':list(reused.values()),
 'snapshots':snapshots,'terminal_commands':terminal_commands,'folders':coverage,'verified_lane_manifests':frozen,
 'omitted_derived_files':omitted,'excluded_live_work':['qa/front-transition30-proposal01','runtime/combined-lod29-pilot01','research/combined-roof29-diagnosis01','user-play28-01','user-showroom29-01'],
 'scope':'Completed actual fresh28/29 construction, rejected surface trials, native field/finite-contact/LOD/UV evidence, actual matched renders and lead/independent reviews. Includes separate editable composed02 and deterministic-UV04 pilots. Installed production34 source and GLB remain unchanged. No final all-LOD, two-GLB, runtime-performance, full-motion or human acceptance.',
 'human_approval_reference':None}
inventory=HERE/'inventory.json'
with inventory.open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
parts=[];part=[];size=0
for row in rows:
    if part and size+row['bytes']>128*1024*1024:parts.append(part);part=[];size=0
    part.append(row);size+=row['bytes']
if part:parts.append(part)
for number,part in enumerate(parts,1):
    item={'task_id':'P1-018','scope':record['scope'],'inventory_path':inventory.relative_to(ROOT).as_posix(),'inventory_sha256':sha(inventory),'part':number,'parts':len(parts),'entries':part}
    with (HERE/f'manifest-{number:02}.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(item,f,indent=2);f.write('\n')
print(json.dumps({'files':len(rows),'bytes':record['input_bytes'],'parts':len(parts),'previous_files_referenced':len(reused),'inventory_sha256':sha(inventory)}),flush=True)
