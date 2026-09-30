"""Publish the verified retained checkpoint; leave final production gates open."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,platform,subprocess

root=Path.cwd().resolve();here=Path(__file__).resolve().parent
out=root/'data/assets/vehicles/endurance-sedan-review/art-checkpoint-v32'
base=root/'reports/p1-018';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def item(p):return {'path':p.relative_to(root).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
index=json.loads((out/'index.json').read_text())
assert index['all_parts_directly_byte_compared'] and index['all_members_sha256_and_crc_verified_twice']
assert index['entry_count']==3436 and len(index['parts'])==10
for row in index['parts']:
 p=root/row['archive']['path'];assert sha(p)==row['archive']['sha256'] and p.stat().st_size==row['archive']['bytes']
command=base/'commands/20260913T075542.657760Z-art32-two-archive-retention.json'
cmd=json.loads(command.read_text());assert cmd['exit_status']==0
with (out/'retention-command.json').open('xb') as f:f.write(command.read_bytes())
with (out/'update_record.py').open('xb') as f:f.write(Path(__file__).read_bytes())
utc=datetime.now(timezone.utc).isoformat();revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
composition=base/'combined-form29-pilot01/composed02/record.json';uv=base/'combined-form29-pilot01/uv04/record.json'
c=json.loads(composition.read_text());u=json.loads(uv.read_text());assert c['lod0_triangles']==148898
review=base/'combined-form29-pilot01/review06.json';r=json.loads(review.read_text())
record={'utc':utc,'git_base_revision':revision,'status':'retained-combined-editable-pilot-with-open-production-gates','platform':platform.platform(),
 'blender':{'version':'5.1.2','build':'ec6e62d40fa9'},'index':item(out/'index.json'),'inventory':item(out/'inventory.json'),'lead_command':{**item(out/'retention-command.json'),'exit_status':0},
 'source':u['pilot_source'],'composed_render_source':c['pilot_source'],'composition':item(composition),'reopen':item(base/'combined-form29-pilot01/render03/reopen.json'),
 'UV_adoption':item(uv),'actual_whole_form_review':item(review),'independent_valance_review':item(base/'qa/valance-field29-review01/observations02.json'),
 'metrics':{'archives':10,'input_files':3436,'input_bytes':1224896583,'archive_bytes':index['archive_bytes'],'byte_identical_archive_builds':2,'referenced_unchanged_v26_v27_payloads':10,
  'LOD0_triangles':148898,'LOD0_ceiling':150000,'LOD0_headroom':1102,'combined_changed_meshes':14,'combined_other_raw_meshes_modifiers_exact':1090,'reopened_changed_native_meshes_exact':14,
  'UV_changed_closures':2,'UV_other_raw_meshes_modifiers_exact':1102,'UV_maximum_change':9.5367431640625e-7,'UV_limit':1e-6,'combined_actual_stills':8,
  'body_complete_field_triangles':21926,'body_complete_max_degrees':.024995246980950823,'valance_complete_triangles':324,'valance_complete_max_degrees':.002277631891821923,
  'isolated_lower_policy_total':199442,'arithmetic_with_C_delta':200072,'final_composed_all_LOD_total':None,'all_LOD_limit':200000},
 'fresh_source_construction':'fresh02 was generated from an empty scene with188 locked inputs. The later composed02 andUV04 are explicit source-derived editable pilots, not a new empty-scene production-generation claim.',
 'failures_and_retries':['Rear cap original-field restoration rejected visually despite numerical field pass; side-only bumper restoration did not address the distinct valance semantic.',
  'Initial valance narrow-triangle finite ownership rejection corrected with independently scoped complete convex-distance proof; geometry and existing guards unchanged.',
  'Initial combined launch failed before mutation on missing declared QA import path; literal runner correction completed.',
  'Cabin LOD candidate remains historically failed strict UV preservation. Separate source-derived deterministic native UV carrier passes; final current-source lower LODs remain pending.',
  'First retention inventory treated lane-relative manifest paths as repository-relative and stopped before snapshots/archives. Explicit manifest domains fixed preparation02. All10 archive builds then passed first attempt.'],
 'retention_preparation_retry_count':1,'archive_retry_count':0,'canonical_source_or_exports_replaced':False,
 'documentation':'docs/vehicles/endurance-sedan/art-checkpoint-v32.md','windows_frontdoor':{'status':'pending_this_checkpoint'},
 'remaining':['Finite lamp-to-shoulder surface correction and upper roof/window/C assembly fit','Lower bumper/splitter/valance end construction finish','Actual combined LOD geometry/field/semantic/total budget and in-motion transitions','Fresh final reproducible constructor, final source reopen, two identical shipping GLBs and clean import','Full source opening/fit/motion, runtime footage, reference performance and required platform asset gates','Human visual/rights/driving/wheel-feel/usability approvals'],
 'human_approval_reference':None}
evidence=root/'evidence/M5/P1-018.json';e=json.loads(evidence.read_text(encoding='utf-8'));assert 'art_construction_checkpoint_v32' not in e
e['art_construction_checkpoint_v32']=record;e['utc']=utc
with evidence.open('w',encoding='utf-8',newline='\n') as f:json.dump(e,f,indent=2);f.write('\n')
defects=root/'docs/vehicles/endurance-sedan/defects.json';d=json.loads(defects.read_text(encoding='utf-8'))
known={v['id'] for v in d['defects']}
for finding in r['findings']:
 assert finding['id'] not in known
 d['defects'].append({'id':finding['id'],'severity':'major','status':finding['status'],'category':'combined-vehicle-form','assigned_owner':'lead-vehicle-art','observed_utc':utc,'summary':finding['observation'],
  'correction':'As recorded in the actual combined review and separately scoped current proposal; final production replacement remains pending.',
  'verification':'Eight actual fixed-camera Blender originals after save/reopen; exact relevant native fields and source bindings. Corrected-in-pilot is not final exported or motion acceptance.',
  'evidence':[item(review),item(out/'index.json')],'human_approval_reference':None})
d['artifact_reviews'].append({'id':'P1-018-ART32-COMBINED-PILOT','task_id':'P1-018','milestone':'M5','utc':utc,'git_revision':revision,'platform':platform.platform(),
 'kind':'actual-combined-source-and-render-review','status':record['status'],'evidence':[item(out/'index.json'),item(review)],'observations':[v['observation'] for v in r['findings']],
 'limits':'Production34 remains installed. New source has no lower LODs; final source/export/runtime/platform/human acceptance remains open.','human_approval_reference':None})
d['updated_utc']=utc
with defects.open('w',encoding='utf-8',newline='\n') as f:json.dump(d,f,indent=2);f.write('\n')
ledger=root/'docs/DELIVERY_LEDGER.json';l=json.loads(ledger.read_text(encoding='utf-8'));t=next(t for t in l['tasks'] if t['id']=='P1-018');assert t['status']=='in_progress'
doc='docs/vehicles/endurance-sedan/art-checkpoint-v32.md'
if doc not in t['evidence']:t['evidence'].append(doc)
t['notes']+=' '+utc+': v32 retains3436 completed source/proposal/native/render/failed-trial files in10 byte-verified archives, plus10 unchanged prior payload references. Actual composed source passes14 changed-field reopen checks and148898 LOD0; source-derived deterministic Hood/Trunk UVs are saved in a separate pilot. Canonical production34 and all final source/LOD/export/runtime/human gates remain unchanged and open.'
with ledger.open('w',encoding='utf-8',newline='\n') as f:json.dump(l,f,indent=2);f.write('\n')
text='''# P1-018 combined Blender checkpoint v32

The editable combined pilot is
`reports/p1-018/combined-form29-pilot01/uv04/source.blend`, SHA-256
`27e24adc70da451047181063a0fd29263e4f54a7452928da6ba5054f4710a73b`.
It contains the repaired body/door and front-arch fields, fitted C skins and
supports, corrected rear valance fields, and deterministic hood/trunk UVs.
Its148,898 LOD0 triangles fit the150,000 ceiling. Lower LODs and final
production installation are still pending.

The [retention index](../../../data/assets/vehicles/endurance-sedan-review/art-checkpoint-v32/index.json)
contains3,436 files in10 archives (1,045,828,721 bytes). Every archive was
built twice, directly compared and read back for every member's SHA-256 and
CRC. Ten unchanged payloads reference the retained v26/v27 inventories.
This verifies review-archive reproducibility; final shipping GLB identity
remains a separate gate. The failed preparation and all rejected modeling
trials remain available.

Blender5.1.2 `ec6e62d40fa9` generated the earlier fresh02 foundation from an
empty scene with188 locked inputs. Lead then derived composed02 andUV04
from that source. Fourteen changed meshes have identical evaluated fields
after the composed source reopens;1,090 other raw meshes/modifiers remain
exact. The C receiver field check uses the actual repaired body input.
The fitted supports meet the actual finite body surfaces and retain their
seats, belt guides and26 checked nearby clearances. These are modeled
assemblies and bounded fit evidence, with no strength or mechanical simulation.

Eight actual2560x1440 Cycles renders show the combined result from both
three-quarter views, both sides, top, rear and two front close-ups. The broad
door/body and front-arch reflections remain corrected. Independent QA confirms
the rear-valance shading correction in four separate matched pairs. The lamp
transition still has a forked reflection; upper roof/window/C joins and lower
bumper ends remain visibly unfinished. The
[actual review](../../../reports/p1-018/combined-form29-pilot01/review06.json)
records those limits. Its images use composed02 before the separate UV bake.

The hood/trunk UV correction carries the original authored coordinates through
the unchanged native modifiers, then computes a stable per-vertex mean. It
uses no quantization. Maximum change is9.536743e-7 under the unchanged1e-6
guard, with all non-UV evaluated fields exact. Root bakes exactly those two
modifier pairs and retains the original grids/modifier recipe in construction
witnesses. Source generation will integrate this step before LOD capture.
The old LOD trial's strict UV failure remains historical evidence; it is not
relabeled as passed. Actual current combined LOD totals are still being measured
against the unchanged200,000 ceiling.

To inspect locally, open the source above using the supplied Blender executable.
Select `RigControls` for opening, lighting and wiper properties. The base source,
complete native fields, staged construction scripts and actual images can be
restored from the10 archives into a clean worktree with relative paths preserved.
The bound construction sequence is `front-joined29-pilot01/run02.py`, then
`combined-form29-pilot01/compose02.py`, then `uv04.py`; their output directories
are guarded against overwriting an existing checkpoint. This is the current
reproducible pilot sequence, not the final production constructor.

The implemented game showroom remains available through **F2 → Explore in
showroom**, with orbit/pan/zoom, cabin/engine/luggage views, all six opening
controls, lighting, wipers and photos. It still uses the installed production34
asset. The new pilot will replace it after current-source LOD, export and runtime
checks. Hero GT and graybox behavior remain covered by the retained viewer
regressions.

P1-018 remains in progress. Full final construction, continuous opening/fit
checks, two identical GLBs, clean imports, footage, reference performance and
declared platform asset checks remain required. Human art/rights, driving,
physical-wheel and usability gates remain open.
'''
with (root/doc).open('x',encoding='utf-8',newline='\n') as f:f.write(text)
print(json.dumps({'status':record['status'],'index':record['index'],'source':record['source'],'new_defect_rows':len(r['findings'])}),flush=True)
