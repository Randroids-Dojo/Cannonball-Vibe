"""Build and verify each frozen native art evidence part twice."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
ROOT=Path.cwd();HERE=Path(__file__).resolve().parent
OUT=ROOT/'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v26'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inventory=HERE/'inventory.json'
assert sha(inventory)=='4ddb6d5b9ef27a25a14af5fb3edb25f14b95e17d33acd0899a5a96349afc62e2'
OUT.mkdir(parents=True,exist_ok=False)
parts=[]
for manifest in sorted(HERE.glob('manifest-*.json')):
    number=int(manifest.stem.split('-')[1]);target=OUT/f'art-checkpoint-v26-{number:02}.zip'
    repeat=HERE/f'art-checkpoint-v26-{number:02}-repeat.zip';index=OUT/f'index-{number:02}.json'
    command=[sys.executable,'tools/vehicles/endurance_sedan/retain_evidence.py',
             '--manifest',str(manifest.relative_to(ROOT)),'--output',str(target.relative_to(ROOT)),
             '--repeat-output',str(repeat.relative_to(ROOT)),'--index',str(index.relative_to(ROOT))]
    started=datetime.now(timezone.utc).isoformat()
    result=subprocess.run(command,cwd=ROOT,check=False)
    row={'part':number,'command':command,'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),
         'exit_status':result.returncode}
    with (HERE/f'command-{number:02}.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(row,f,indent=2);f.write('\n')
    if result.returncode:raise RuntimeError('Art retention part failed '+str(number))
    data=json.loads(index.read_text());assert data['status']=='passed' and data['byte_reproducible']
    row.update({'archive':data['archives'][0],'repeat':data['archives'][1],
                'index':{'path':index.relative_to(ROOT).as_posix(),'sha256':sha(index)},
                'entries':len(data['entries']),'manifest_sha256':sha(manifest)})
    parts.append(row);print('RETAINED_PART '+str(number),flush=True)
record={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
        'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'inventory':{'path':inventory.relative_to(ROOT).as_posix(),'sha256':sha(inventory)},
        'parts':parts,'all_parts_byte_identical':True,'all_members_sha256_and_crc_verified_twice':True,
        'entry_count':sum(p['entries'] for p in parts),'archive_bytes':sum(p['archive']['bytes'] for p in parts),
        'scope':'Native art checkpoint retention only. Every original experiment and failure retains its own limited acceptance. Not final production/LOD/runtime or human acceptance.',
        'human_approval_reference':None}
with (OUT/'index.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
for source,name in [(inventory,'inventory.json'),(Path(__file__),'build.py'),(HERE/'prepare.py','prepare.py')]:
    with (OUT/name).open('xb') as f:f.write(source.read_bytes())
print(json.dumps({'parts':len(parts),'entries':record['entry_count'],'archive_bytes':record['archive_bytes']}),flush=True)
