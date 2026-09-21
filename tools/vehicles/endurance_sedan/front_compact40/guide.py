"""Extract the verified historical guide without an archived mesh dependency."""
import copy
from .primitives import derive

def extract_legacy_guide(construction):
 s=construction['current_surface34'];original=s['original_sheet'];front=construction['front_form27']['field_packet']['core'];domains={};guides={};records={}
 if original['schema']!='actual-original-front-sheet.v1' or original['source_kind']!='actual-pre-voids-native':raise ValueError('Wrong original guide provenance')
 if [v['stage']for v in front['stages']]!=['bend','planar','lamp','rear_planar','inlet']:raise ValueError('Incomplete front guide stage sequence')
 for plan in s['front_plans']:
  name=plan['object'];old=s['final_native_fields'][name];ev=plan['evidence']
  if name=='LOD0_FrontBumper':
   selected={r['triangle']for e in ev['initial_authored_domains']['complete_original_ownership']for r in e['complete_triangles']};state=front['initial'];history=[]
   for st in front['stages']:
    if st['before']!=state:raise ValueError('Unobserved historical guide boundary')
    if st['stage']in('planar','rear_planar'):
     removed={i for c in st['proof']['components']for i in c['old_faces']};retained=[i for i in range(len(state['triangles']))if i not in removed];selected={j for j,i in enumerate(retained)if i in selected}
    elif st['stage']=='inlet':
     if st['proof']['generated_rear_fan']['repairs']:raise ValueError('Unmapped final guide fan revision')
     selected={i for i,e in enumerate(st['proof']['owners'])if e['kind']in('retained_exact','retained_subdivided','subdivided_interpolated')and e['reference_face']in selected and not e.get('authored_rear_closure_field')}
    history.append({'stage':st['stage'],'sheet_triangles':len(selected)});state=st['after']
   if [t['vertices']for t in state['triangles']]!=old['triangles']:raise ValueError('Current guide topology differs from actual legacy final')
   # The old conservative complete-face map omitted real clipped fragments
   # of the same original retained skin. Use the actual construction class
   # across the entire current panel, distinct from axis walls/cap/perimeter.
   primitive_domains=derive(construction)
   complete_skin={i for i,d in enumerate(primitive_domains) if d.get('initial_marker')==0 and d.get('initial_strength')==16384 and d['kind']=='generated_finite_transition'}
   if not selected<=complete_skin:raise ValueError('Original complete-face map crosses native outer-skin class')
   history.append({'stage':'complete_current_original_skin_class','legacy_complete_faces':len(selected),'native_skin_faces':len(complete_skin),'additional_current_skin_fragments':sorted(complete_skin-selected)})
   selected=complete_skin
   points=copy.deepcopy(old['vertices']);tris=[old['triangles'][i][:]for i in sorted(selected)];provenance=[{'current_outer_triangle':i}for i in sorted(selected)];records[name]=history
  else:
   e=ev['original_sheet'];polys=plan['physical']['polygons'];owned=set(e['selected_faces']);selected={ti for ti,t in enumerate(old['triangles'])if any(set(t)<=set(polys[f][0])for f in owned)}
   ids=[i for i,t in enumerate(original['triangles'])if max(original['vertices'][v][1]for v in t)>=.60 and original['face_domains'][i]=={'marker':0,'strength':16384}]
   points=copy.deepcopy(original['vertices']);tris=[original['triangles'][i][:]for i in ids];provenance=[{'prevoid_triangle':i}for i in ids];records[name]={'complete_source_sheet_triangles':len(selected)}
  guides[name]={'vertices':points,'triangles':tris,'provenance':provenance,'kind':'actual uncut original geometry'if name!='LOD0_FrontBumper'else'actual current outer-sheet geometry after all historical front stages'}
  domains[name]={'outer_sheet_source_triangles':sorted(selected)}
 return {'schema':'front-compact40-legacy-guide.v1','guides':guides,'domains':domains,'records':records,'actual_before_panels':{n:copy.deepcopy(s['final_native_fields'][n])for n in guides},'source_normals_used':False,'primitive_domains':derive(construction)}
