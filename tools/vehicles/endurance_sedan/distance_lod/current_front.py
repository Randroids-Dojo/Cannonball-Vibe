"""Actual finite front chain. Native read/independent numerical checks only."""
import sys
sys.dont_write_bytecode = True
from collections import defaultdict
import math
from .binding import digest, plain, sha

def require(value,message):
    if not value:raise ValueError(message)

def valid_normals(values):
    require(values and all(len(n)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in n)
        and abs(math.hypot(*n)-1)<=1e-6 for n in values),'Invalid complete native/target normal field')

def field_rows(triangles,targets,actual,support,selected=None,before=None):
    valid_normals(targets);valid_normals(actual)
    require(len(targets)==len(actual),'Incomplete complete-field normal inventory')
    all_rows=[];outside=[]
    if before is not None:valid_normals(before)
    for i,t in enumerate(triangles):
        loops=t['loops']
        all_rows.append({'triangle':i,**support.complete_affine_angle([targets[li] for li in loops],[actual[li] for li in loops])})
        if before is not None and t['face'] not in selected:
            outside.append({'triangle':i,**support.complete_affine_angle([before[li] for li in loops],[actual[li] for li in loops])})
    return {'all':all_rows,'outside':outside,'all_maximum_degrees':max(r['maximum_degrees'] for r in all_rows),
        'outside_maximum_degrees':max((r['maximum_degrees'] for r in outside),default=0.)}

def make_packet(source,construction,source_sha256,dependencies,material_capture):
    """Capture current native output and its actual source-generation chain."""
    current=construction['current_surface34']
    plans=[p for p in current['front_plans'] if p['object']=='LOD0_FrontBumper']
    require(len(plans)==1,'Missing or duplicate front field plan')
    core={'schema':'current-finite-front36.v1','current_source_sha256':source_sha256,
        'original_inlet_packet':construction['front_form27']['field_packet'],
        'original_sheet':current['original_sheet'],'original_body':current['original_body'],
        'front_prefix':construction['front_prefix29'],'front_plan':plans[0],
        'lamp_plan':current['lamp_plan'],'recorded_current_native':current['current_front_native'],
        'current_native':plain(dependencies['sheet'].native_state(source)),
        'current_physical':plain(dependencies['support'].fields(source)),
        'current_material_response':material_capture(source.data),
        'constructor_inputs':construction['construction_inputs']}
    return {'core':core,'sha256':digest(core)}

def check_inlet(packet,dependencies):
    require(set(packet)=={'core','sha256'} and digest(packet['core'])==packet['sha256'],'Original inlet packet hash mismatch')
    core=packet['core'];stages=core['stages']
    require(core['schema']=='front-form-field-construction.v2' and core['object']=='LOD0_FrontBumper'
        and core['capture_kind']=='actual-in-process-observation','Wrong actual inlet capture schema')
    require([s['stage'] for s in stages]==['bend','planar','lamp','rear_planar','inlet'],'Missing or reordered current inlet stage')
    require(core['normal_encoding_guard_degrees']==.025 and core['normal_unit_guard']==1e-6,'Changed inlet guards')
    previous=core['initial'];events=[]
    for stage in stages:
        require(stage['before']==previous,'Missing complete current intermediate state')
        if stage['stage']=='inlet':
            owners=stage['proof']['owners']
            require(len(owners)==len(stage['after']['triangles']) and [r['face'] for r in owners]==list(range(len(owners))),
                'Omitted/duplicate complete current Trim/carrier owner')
            require(not stage['proof']['generated_rear_fan']['repairs'],'Unhandled current inlet topology repair')
        require(len(stage['encodings'])==(2 if stage['stage']=='bend' else 1),'Unexpected original encoding partition')
        for index,event in enumerate(stage['encodings']):
            metrics=dependencies['recorder'].require_encoded(event['before'],event['targets'],event['after'])
            events.append({'stage':stage['stage'],'event':index,**metrics})
        require(stage['after']==stage['encodings'][-1]['after'],'Unobserved post-encoding intermediate state')
        previous=stage['after']
    require(previous==core['final'],'Missing current inlet final state')
    return events

def derive_sheet(core,dependencies):
    """Regenerate complete original ownership and geometric field transport."""
    d=dependencies;packet=core['original_inlet_packet'];plan=core['front_plan']
    d['sheet'].validate_reference(core['original_sheet'])
    patch=d['sheet'].original_patch(core['original_sheet'],d['ownership'],d['projection'])
    initial=d['sheet'].state_from_capture(packet['core']['initial'])
    owned=d['sheet'].prepare_sheet(initial,patch)
    transition=d['finite_bevel'].prepare(initial,owned,d['projection'],d['arch'].PROFILE)
    carrier=plain(d['carrier'].prepare(packet,transition,d['ownership'],d['projection'],d['transport'],d['bend'].field,d['optical'].field))
    require(plan['schema']=='complete-front-sheet-normal-only.v1' and plan['normal_guard_degrees']==.025,'Wrong current front field contract')
    require(carrier==plan['evidence'],'Original whole-face/finite-geometry carrier evidence differs from independent regeneration')
    final=packet['core']['final'];targets=list(final['normals']);selected=set()
    for ti in carrier['selected_triangles']:
        tri=final['triangles'][ti];selected.add(tri['face'])
        for li in tri['loops']:targets[li]=carrier['targets'][li]
    require(plan['before']==final['normals'],'Wrong current sheet pre-apply native field')
    require(plan['targets']==targets and plan['targets_sha256']==digest(targets),'Wrong independently regenerated complete sheet targets')
    require(plan['selected_faces']==sorted(selected),'Omitted or stale complete sheet face domain')
    require(plan['physical_sha256']==digest(plan['physical']),'Wrong current sheet physical checkpoint hash')
    faces=[{'face':fi,'loops':final['faces'][fi]['loops'],'targets':[targets[li] for li in final['faces'][fi]['loops']]} for fi in sorted(selected)]
    require(plan['authorship']==faces,'Incomplete complete-sheet corner authorship')
    return carrier,selected

def validate_lamp_domain(core,dependencies):
    """Check every declared current finite position/normal/boundary item."""
    plan=core['lamp_plan'];native=core['current_native'];triangles=native['triangles']
    require(plan['schema']=='finite-lamp-surface-proposal.v1' and plan['object']=='LOD0_FrontBumper','Wrong current finite lamp schema')
    require(plan['normal_guard_degrees']==.025,'Changed finite lamp field guard')
    require(len(native['points'])==3305 and len(triangles)==6630 and len(native['normals'])==19890,'Current front inventory differs')
    selected=plan['domain']['selected_faces']
    require(selected==sorted(set(selected)) and len(selected)==466,'Omitted/duplicate finite lamp face')
    require(all(type(i)is int and 0<=i<len(native['face_loops']) for i in selected),'Invalid finite lamp face')
    selected=set(selected);incident=defaultdict(set);edge_faces=defaultdict(list)
    for t in triangles:
        for vi in t['vertices']:incident[vi].add(t['face'])
        for a,b in zip(t['vertices'],t['vertices'][1:]+t['vertices'][:1]):edge_faces[tuple(sorted((a,b)))].append(t['face'])
    require(all(len(fs)==2 for fs in edge_faces.values()),'Current finite front is not closed')
    vertices={vi for t in triangles if t['face'] in selected for vi in t['vertices']}
    free={v for v in vertices if incident[v] and incident[v]<=selected};fixed=vertices-free
    require(plan['domain']['free_vertices']==sorted(free) and plan['domain']['fixed_vertices']==sorted(fixed),
        'Omitted/ambiguous free or fixed finite vertices')
    boundary={edge:tuple(sorted(fs)) for edge,fs in edge_faces.items() if len(set(fs)&selected)==1}
    supplied={tuple(sorted(r['vertices'])):tuple(sorted(r['triangles'])) for r in plan['domain']['boundary']}
    require(boundary==supplied and len(supplied)==len(plan['domain']['boundary']),'Omitted/ambiguous complete finite boundary')
    require(len(plan['positions'])==len(plan['positions_before'])==len(native['points']),'Incomplete finite position field')
    changed=[i for i,(a,b) in enumerate(zip(plan['positions_before'],plan['positions'])) if a!=b]
    require(changed==plan['changed_vertices'] and len(changed)==168 and set(changed)<=free,'Unexpected moved finite vertex domain')
    require(all(a==b for i,(a,b) in enumerate(zip(plan['positions_before'],plan['positions'])) if i not in free),'Moved fixed/outside native position')
    owned={li for fi in selected for li in native['face_loops'][fi]}
    require(len(plan['targets'])==len(plan['normals_before'])==len(native['normals']),'Incomplete finite normal field')
    valid_normals(plan['targets']);valid_normals(plan['normals_before']);valid_normals(native['normals'])
    require(all(a==b for i,(a,b) in enumerate(zip(plan['targets'],plan['normals_before'])) if i not in owned),'Changed original outside finite target')
    for edge,fs in boundary.items():
        for vi in edge:
            for fi in fs:
                loops=[li for li in native['face_loops'][fi] if core['current_physical']['loops'][li][0]==vi]
                require(len(loops)==1 and plan['targets'][loops[0]]==plan['normals_before'][loops[0]],'Changed complete fixed boundary first jet')
    require(native['points']==plan['positions'],'Actual native geometry differs from finite plan')
    before=plan['physical_before'];after=core['current_physical']
    require({k:v for k,v in before.items() if k!='positions'}=={k:v for k,v in after.items() if k!='positions'},
        'Finite lamp changed topology/UV/material/rig/outside physical fields')
    require(before['positions']==plan['positions_before'],'Wrong finite before-position checkpoint')
    return selected

def verify_packet(source,packet,dependencies,material_capture,*,regenerate=True):
    require(set(packet)=={'core','sha256'} and packet['sha256']==digest(packet['core']),'Current front packet hash mismatch')
    core=packet['core'];d=dependencies
    require(core['schema']=='current-finite-front36.v1','Wrong current finite-front packet schema')
    actual=plain(d['sheet'].native_state(source));physical=plain(d['support'].fields(source))
    require(actual==core['current_native']==core['recorded_current_native'],'Actual saved front differs from current native construction snapshot')
    require(physical==core['current_physical'],'Actual saved front physical fields differ')
    require(material_capture(source.data)==core['current_material_response'],'Actual current material response differs')
    events=check_inlet(core['original_inlet_packet'],d)
    initial=core['original_inlet_packet']['core']['final'];plan=core['front_plan'];lamp=core['lamp_plan']
    require(core['current_material_response']==initial['material_response'],'Current original material response changed')
    require(plan['physical']==lamp['physical_before'],'Missing complete sheet-to-finite physical checkpoint')
    require(initial['physical']['vertices']==lamp['positions_before'] and initial['triangles']==actual['triangles']
        and [f['loops'] for f in initial['faces']]==actual['face_loops'],'Finite stage changed original carrier connectivity')
    selected_lamp=validate_lamp_domain(core,d)
    if regenerate:
        carrier,selected_sheet=derive_sheet(core,d)
    else:
        raise ValueError('Independent current carrier regeneration cannot be skipped')
    # Actual pre-finite native normals are the output checkpoint of the
    # preceding sheet authorship. Recheck complete target and outside fields.
    pre_fields=field_rows(actual['triangles'],plan['targets'],lamp['normals_before'],d['support'],selected_sheet,plan['before'])
    pre_state=plain(d['sheet'].state_from_capture(initial));pre_state['normals']=lamp['normals_before']
    regenerated=plain(d['lamp'].prepare(pre_state,core['original_body'],core['front_prefix'],core['original_inlet_packet'],plan))
    expected={k:v for k,v in lamp.items() if k!='physical_before'}
    require(regenerated==expected,'Current finite lamp differs from independent parameter/geometry/target regeneration')
    final_fields=field_rows(actual['triangles'],lamp['targets'],actual['normals'],d['support'],selected_lamp,lamp['normals_before'])
    return {'status':'passed-current-native-chain','source_vertices':len(actual['points']),'source_triangles':len(actual['triangles']),
        'source_corners':len(actual['normals']),'moved_vertices':len(lamp['changed_vertices']),'finite_faces':len(selected_lamp),
        'inlet_encodings':events,'independent_carrier_sha256':digest(carrier),
        'independent_finite_plan_sha256':digest(regenerated),'sheet_target_and_outside':pre_fields,
        'finite_target_and_outside':final_fields,'raw_maximum_unit_error':max(abs(math.hypot(*n)-1) for n in actual['normals']),
        'geometry_UV_material_rig_exact':True,'source_saves':0,'exports':0,'GPU':False}

def protection_inventory(source,selected_lamp_faces):
    """Literal frozen mixed-front domain, before any decimation or expansion."""
    mesh=source.data;mesh.calc_loop_triangles()
    require(len(mesh.polygons)==len(mesh.loop_triangles) and all(len(p.vertices)==3 for p in mesh.polygons),
        'Current front must have explicit triangles')
    points=[list(v.co) for v in mesh.vertices]
    edges=defaultdict(list);incident=defaultdict(set)
    for ti,t in enumerate(mesh.loop_triangles):
        for v in t.vertices:incident[v].add(ti)
        for a,b in zip(t.vertices,tuple(t.vertices[1:])+tuple(t.vertices[:1])):edges[tuple(sorted((a,b)))].append(ti)
    require(all(len(fs)==2 for fs in edges.values()),'Current front is not closed')
    trim={i for i,t in enumerate(mesh.loop_triangles) if t.material_index==1}
    boundary=[edge for edge,fs in edges.items() if len({mesh.loop_triangles[i].material_index for i in fs})==2]
    vertices={v for edge in boundary for v in edge}
    fan=set().union(*(incident[v] for v in vertices))
    shoulder={i for i,t in enumerate(mesh.loop_triangles) if t.material_index==0 and mesh.polygons[t.polygon_index].use_smooth
        and min(points[v][2] for v in t.vertices)>=.80
        and (max(points[v][1] for v in t.vertices)>=2.23
            or (max(abs(points[v][0]) for v in t.vertices)>=.65 and max(points[v][1] for v in t.vertices)>=2.04))}
    seeds=trim|fan|shoulder
    seed_vertices={v for i in seeds for v in mesh.loop_triangles[i].vertices}
    protected={i for i,t in enumerate(mesh.loop_triangles) if set(t.vertices)<=seed_vertices}
    missing=sorted(set(selected_lamp_faces)-protected)
    missing_vertices=sorted({v for i in missing for v in mesh.loop_triangles[i].vertices}-seed_vertices)
    return {'Trim_triangles':len(trim),'Trim_boundary_one_ring':len(fan),'shoulder_seed_faces':len(shoulder),
        'protected_triangles':sorted(protected),'protected_vertices':sorted(seed_vertices),
        'lamp_faces':sorted(selected_lamp_faces),'missing_lamp_faces':missing,
        'missing_lamp_vertices':missing_vertices,
        'additional_original_triangles_if_individually_retained':len(missing),
        'actual_lower_cost_of_expansion':None,
        'domain_was_expanded':False}
