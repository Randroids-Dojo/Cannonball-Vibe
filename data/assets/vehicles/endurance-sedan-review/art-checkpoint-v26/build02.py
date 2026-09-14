"""Resume verified evidence parts after excluding a live recorder from its freeze."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys,zipfile
ROOT=Path.cwd();HERE=Path(__file__).resolve().parent
OUT=ROOT/'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v26'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inventory=HERE/'inventory02.json';locked=json.loads(inventory.read_text())
current={r['path']:r for r in locked['entries']};parts=[]
def verify_previous(number):
    index=OUT/f'index-{number:02}.json';data=json.loads(index.read_text())
    manifest=HERE/f'manifest-{number:02}.json';raw=manifest.read_bytes()
    assert data['status']=='passed' and data['byte_reproducible']
    assert all(current[r['path']]==r for r in data['entries'])
    for item in data['archives']:
        path=ROOT/item['path'];assert sha(path)==item['sha256'] and path.stat().st_size==item['bytes']
        with zipfile.ZipFile(path) as archive:
            assert archive.read('manifest.json')==raw
            assert archive.namelist()==['manifest.json',*[r['path'] for r in data['entries']]]
            assert archive.testzip() is None
            for row in data['entries']:
                with archive.open(row['path']) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
    return {'part':number,'archive':data['archives'][0],'repeat':data['archives'][1],
            'index':{'path':index.relative_to(ROOT).as_posix(),'sha256':sha(index)},
            'entries':len(data['entries']),'manifest_sha256':sha(manifest),
            'original_success_preserved_and_fully_reverified':True}
for number in range(1,4):parts.append(verify_previous(number));print('REVERIFIED_PART '+str(number),flush=True)
for manifest in sorted(HERE.glob('manifest02-*.json')):
    number=int(manifest.stem.split('-')[1]);target=OUT/f'art-checkpoint-v26-{number:02}.zip'
    repeat=HERE/f'art-checkpoint-v26-{number:02}-repeat.zip';index=OUT/f'index-{number:02}.json'
    command=[sys.executable,'tools/vehicles/endurance_sedan/retain_evidence.py',
             '--manifest',str(manifest.relative_to(ROOT)),'--output',str(target.relative_to(ROOT)),
             '--repeat-output',str(repeat.relative_to(ROOT)),'--index',str(index.relative_to(ROOT))]
    started=datetime.now(timezone.utc).isoformat();result=subprocess.run(command,cwd=ROOT,check=False)
    row={'part':number,'command':command,'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),
         'exit_status':result.returncode}
    with (HERE/f'command02-{number:02}.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(row,f,indent=2);f.write('\n')
    if result.returncode:raise RuntimeError('Art retention part failed '+str(number))
    data=json.loads(index.read_text());assert data['status']=='passed' and data['byte_reproducible']
    row.update({'archive':data['archives'][0],'repeat':data['archives'][1],
                'index':{'path':index.relative_to(ROOT).as_posix(),'sha256':sha(index)},
                'entries':len(data['entries']),'manifest_sha256':sha(manifest)})
    parts.append(row);print('RETAINED_PART '+str(number),flush=True)
for part in parts:
    with (ROOT/part['archive']['path']).open('rb') as a,(ROOT/part['repeat']['path']).open('rb') as b:
        while block:=a.read(1024*1024):assert block==b.read(1024*1024)
        assert not b.read(1)
for row in current.values():
    path=ROOT/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
record={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
        'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'inventory':{'path':inventory.relative_to(ROOT).as_posix(),'sha256':sha(inventory)},
        'parts':parts,'all_parts_directly_byte_compared':True,'all_members_sha256_and_crc_verified_twice':True,
        'entry_count':sum(p['entries'] for p in parts),'archive_bytes':sum(p['archive']['bytes'] for p in parts),
        'retries':1,'failure_and_recovery':locked['retained_failure'],
        'scope':locked['scope'],'human_approval_reference':None}
assert record['entry_count']==locked['input_count']
with (OUT/'index.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
for name in ['inventory.json','inventory02.json','prepare.py','prepare02.py','build.py','build02.py']:
    with (OUT/name).open('xb') as f:f.write((HERE/name).read_bytes())
print(json.dumps({'parts':len(parts),'entries':record['entry_count'],'archive_bytes':record['archive_bytes']}),flush=True)
