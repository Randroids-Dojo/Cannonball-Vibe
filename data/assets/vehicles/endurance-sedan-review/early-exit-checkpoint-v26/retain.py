"""Freeze completed early-exit evidence, archive twice, and verify every byte."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,platform,subprocess,sys,zipfile,zlib

root=Path.cwd();here=Path(__file__).resolve().parent
packet=root/'reports/p1-018/runtime/lifecycle26-platform02'
out=root/'data/assets/vehicles/endurance-sedan-review/early-exit-checkpoint-v26'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=here/'manifest.json'
if sys.argv[1]=='prepare':
    index=packet/'inventory13.json';assert sha(index)=='d86892deae743b05111ef143821c499dab197990becbaf527e702fc1a789d3b2'
    inventory=json.loads(index.read_text());paths=set()
    for row in inventory['payloads']:
        path=packet/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
        paths.add(path)
    # Include inventory bookkeeping only after the agent froze it. Do not use
    # ordinary rglob as a claim about the omitted long shader-cache paths.
    paths.update(packet.glob('inventory13*'))
    paths.update(p for p in (root/'reports/p1-018/early-exit26-frontdoor01').rglob('*') if p.is_file())
    paths.update(root/p for p in (
        'reports/p1-018/commands/20260912T190722.601365Z-early-exit26-full-working-frontdoor.json',
        'reports/p1-018/commands/20260912T190722.601365Z-early-exit26-full-working-frontdoor.log',
        'addons/playgodot/PROTOCOL.md',
        'docs/audits/2026-09-12-playgodot-early-exit-bookkeeping.md'))
    paths.add(Path(__file__))
    entries=[{'path':p.relative_to(root).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)]
    record={'schema_version':1,'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
            'git_base_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'platform':platform.platform(),'python':sys.version,'zlib':zlib.ZLIB_RUNTIME_VERSION,
            'scope':'Retained original CI failure, local bounded correction controls and working-input full M0; new-head platform and final asset gates remain open.',
            'agent_inventory':{'path':index.relative_to(root).as_posix(),'sha256':sha(index)},
            'explicit_cache_omissions':inventory['omissions'],'entries':entries,'input_count':len(entries),
            'input_bytes':sum(r['bytes'] for r in entries),'human_approval_reference':None}
    with manifest.open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps({'inputs':len(entries),'bytes':record['input_bytes']}),flush=True)
elif sys.argv[1]=='build':
    assert manifest.exists() and not out.exists()
    primary=out/'early-exit-checkpoint-v26.zip';repeat=here/'repeat.zip';index=out/'index.json'
    command=[sys.executable,'tools/vehicles/endurance_sedan/retain_evidence.py','--manifest',str(manifest),
             '--output',str(primary),'--repeat-output',str(repeat),'--index',str(index)]
    result=subprocess.run(command,cwd=root,check=False);assert result.returncode==0
    data=json.loads(index.read_text());assert data['status']=='passed' and data['byte_reproducible']
    with primary.open('rb') as a,repeat.open('rb') as b:
        while block:=a.read(1024*1024):assert block==b.read(1024*1024)
        assert not b.read(1)
    for path in (primary,repeat):
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            for row in data['entries']:
                with archive.open(row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
    for source,name in ((manifest,'manifest.json'),(Path(__file__),'retain.py'),(packet/'HANDOFF12.md','HANDOFF12.md')):
        with (out/name).open('xb') as f:f.write(source.read_bytes())
    proof={'task_id':'P1-018','utc':datetime.now(timezone.utc).isoformat(),'archive_sha256':sha(primary),
           'archive_bytes':primary.stat().st_size,'inputs':len(data['entries']),
           'directly_byte_compared':True,'lead_reread_all_member_sha256_and_crc_twice':True,
           'human_approval_reference':None}
    with (out/'lead-verification.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(proof,f,indent=2);f.write('\n')
    print(json.dumps(proof),flush=True)
else:raise ValueError('prepare or build required')
