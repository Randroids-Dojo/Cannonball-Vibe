"""Retain the self-log freeze failure and lock completed receipts for recovery."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path.cwd();HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
measure=lambda p:{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
original=HERE/'inventory.json';old=json.loads(original.read_text());entries={r['path']:dict(r) for r in old['entries']}
changes=[]
for name,row in entries.items():
    actual=measure(ROOT/name)
    if actual!=row:changes.append({'before':row,'after':actual});entries[name]=actual
assert len(changes)==1
assert changes[0]['before']['path']=='reports/p1-018/commands/20260912T183934.576319Z-art26-checkpoint-freeze.log'
assert changes[0]['before']['bytes']==0
supplements=[original,HERE/'build.py',Path(__file__),*sorted(HERE.glob('command-*.json'))]
for stem in ['20260912T183934.576319Z-art26-checkpoint-freeze','20260912T184145.374628Z-art26-checkpoint-ten-parts-twice']:
    supplements += [ROOT/'reports/p1-018/commands'/(stem+suffix) for suffix in ('.json','.log')]
for path in supplements:
    row=measure(path);entries[row['path']]=row
record={**old,'utc':datetime.now(timezone.utc).isoformat(),'entries':[entries[k] for k in sorted(entries)],
        'original_inventory':measure(original),'retained_failure':{
            'cause':'Freeze captured its own still-open command log at zero bytes; the recorder completed the log after the freeze returned.',
            'changed_input':changes,'acceptance_change':False,
            'recovery':'Use the completed original log and receipt in a new inventory; preserve inventory01 and its three valid archive parts. Future own live receipts stay outside the frozen input list.'}}
record['input_count']=len(entries);record['input_bytes']=sum(r['bytes'] for r in entries.values())
out=HERE/'inventory02.json'
with out.open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
retained=[]
for number in range(1,4):
    part=json.loads((HERE/f'manifest-{number:02}.json').read_text())
    for row in part['entries']:assert entries.pop(row['path'])==row
    retained.append({'part':number,'manifest':measure(HERE/f'manifest-{number:02}.json')})
parts=[];part=[];size=0
for key in sorted(entries):
    row=entries[key]
    if part and size+row['bytes']>128*1024*1024:parts.append(part);part=[];size=0
    part.append(row);size+=row['bytes']
if part:parts.append(part)
for number,part in enumerate(parts,4):
    doc={'task_id':'P1-018','scope':record['scope'],'inventory_path':out.relative_to(ROOT).as_posix(),
         'inventory_sha256':sha(out),'part':number,'parts':len(parts)+3,'entries':part,
         'retained_first_three_parts':retained}
    with (HERE/f'manifest02-{number:02}.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(doc,f,indent=2);f.write('\n')
print(json.dumps({'entries':record['input_count'],'pending_parts':len(parts),'existing_valid_parts':3,
                  'inventory02_sha256':sha(out)}),flush=True)
