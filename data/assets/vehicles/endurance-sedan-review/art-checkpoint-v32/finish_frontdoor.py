"""Retain completed Windows gate bytes and append its bounded result."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,subprocess,sys

root=Path.cwd().resolve();here=Path(__file__).resolve().parent
out=root/'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v32';report=root/'reports/p1-018/art32-frontdoor01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def item(p):return {'path':p.relative_to(root).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
summary=json.loads((report/'summary.json').read_text());bindings=json.loads((here/'frontdoor01-bindings.json').read_text())
assert summary['status']=='passed' and len(summary['steps'])==13 and all(r['exit_code']==0 for r in summary['steps'])
assert bindings['unchanged'] and bindings['check_exit_status']==0
cmd=root/'reports/p1-018/commands/20260913T080117.269728Z-art32-full-windows-frontdoor.json';command=json.loads(cmd.read_text());assert command['exit_status']==0
paths=sorted(p for p in report.rglob('*') if p.is_file())+[here/'frontdoor01.py',here/'frontdoor01-bindings.json',Path(__file__),cmd,root/command['log']]
manifest=here/'frontdoor-manifest.json'
with manifest.open('x',encoding='utf-8',newline='\n') as f:json.dump({'task_id':'P1-018','scope':'Completed full Windows scripts/check.sh on the retained checkpoint working inputs; no final source-asset acceptance.','entries':[item(p) for p in paths]},f,indent=2);f.write('\n')
argv=[sys.executable,'tools/vehicles/endurance_sedan/retain_evidence.py','--manifest',str(manifest.relative_to(root)),
      '--output',str((out/'frontdoor.zip').relative_to(root)),'--repeat-output',str((here/'frontdoor-repeat.zip').relative_to(root)),
      '--index',str((out/'frontdoor-index.json').relative_to(root))]
code=subprocess.call(argv,cwd=root);assert code==0
retention=json.loads((out/'frontdoor-index.json').read_text());assert retention['status']=='passed' and retention['byte_reproducible']
with (out/'frontdoor.zip').open('rb') as a,(here/'frontdoor-repeat.zip').open('rb') as b:
 while block:=a.read(1048576):assert block==b.read(1048576)
 assert not b.read(1)
for name,p in [('frontdoor-command.json',cmd),('finish_frontdoor.py',Path(__file__))]:
 with (out/name).open('xb') as f:f.write(p.read_bytes())
evidence=root/'evidence/M5/P1-018.json';data=json.loads(evidence.read_text(encoding='utf-8'))
record={'status':'passed','utc':datetime.now(timezone.utc).isoformat(),'git_base_revision':summary['commit'],'started_utc':summary['started_at'],'finished_utc':summary['finished_at'],
 'steps':summary['steps'],'inputs_unchanged_during_check':True,'input_count':len(bindings['inputs_before']),
 'tool_versions':json.loads((report/'doctor.json').read_text())['checks'],
 'retention_index':item(out/'frontdoor-index.json'),'archive':item(out/'frontdoor.zip'),'command':{**item(out/'frontdoor-command.json'),'exit_status':0},
 'every_archive_byte_compared':True,'all_members_sha256_and_crc_verified_twice':True,'retry_count':0,
 'scope':'Windows repository working-input gate. Installed production34 source asset failures, new pilot final asset/runtime/platform/performance evidence and human gates remain separate.','human_approval_reference':None}
assert data['art_construction_checkpoint_v32']['windows_frontdoor']['status']=='pending_this_checkpoint'
data['art_construction_checkpoint_v32']['windows_frontdoor']=record;data['utc']=record['utc']
with evidence.open('w',encoding='utf-8',newline='\n') as f:json.dump(data,f,indent=2);f.write('\n')
doc=root/'docs/vehicles/endurance-sedan/art-checkpoint-v32.md'
with doc.open('a',encoding='utf-8',newline='\n') as f:f.write('\nThe full Windows `scripts/check.sh` front door passes all13 steps for this\ncheckpoint, including doctor, build/unit suites and official Godot scenarios.\nIts checked inputs remain identical throughout. Logs, exact tool versions and\nstructured outputs are retained in [frontdoor-index.json](../../../data/assets/vehicles/endurance-sedan-review/art-checkpoint-v32/frontdoor-index.json).\nThis repository gate does not close the separate final sedan asset or human gates.\n')
print(json.dumps({'status':record['status'],'steps':len(record['steps']),'archive':record['archive'],'inputs':record['input_count']}),flush=True)
