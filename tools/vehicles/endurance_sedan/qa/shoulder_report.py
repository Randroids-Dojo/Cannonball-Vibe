"""Standard-library reader: rederive inventories, fan rules and numeric bounds."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

from shoulder_checkpoint import digest

ANGLE=.025
UNIT=1e-6


def require(condition,message):
    if not condition:raise ValueError(message)


def number(value):
    require(type(value) in (int,float) and math.isfinite(value),'Nonfinite or untyped number')
    return value


def integer(value,limit=None):
    require(type(value) is int and value>=0 and (limit is None or value<limit),'Invalid integer/index')
    return value


def hash_value(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None,'Invalid SHA256')
    return value


def keys(value,expected,label):
    require(type(value) is dict and set(value)==set(expected),'Incomplete/unknown '+label+' keys')


def normal(value):
    require(type(value) is list and len(value)==3,'Invalid normal vector')
    require(abs(math.hypot(*(number(v) for v in value))-1)<=UNIT,'Invalid raw unit normal')


def angle(a,b):
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross),sum(x*y for x,y in zip(a,b))))


def same_numbers(actual,expected,label):
    require(type(actual) is type(expected) or type(actual) in (int,float) and type(expected) in (int,float),label+' type differs')
    if type(expected) in (float,int):
        require(number(actual)==expected,label+' value differs')
    elif type(expected) is dict:
        keys(actual,expected,label)
        for k,v in expected.items():same_numbers(actual[k],v,label+'/'+k)
    elif type(expected) is list:
        require(len(actual)==len(expected),label+' length differs')
        for i,(a,b) in enumerate(zip(actual,expected)):same_numbers(a,b,label+'/'+str(i))
    else:require(actual==expected,label+' differs')


def validate_state(state):
    keys(state,('object','coordinate_frame','physical','material_response','normals','normal_codes','sharp','loops','faces','triangles'),'native state')
    require(state['object']=='LOD0_FrontBumper','Wrong subject semantic')
    require(len(state['coordinate_frame'])==4 and all(len(r)==4 for r in state['coordinate_frame']),'Wrong source frame')
    for row in state['coordinate_frame']:
        for v in row:number(v)
    physical=state['physical']
    keys(physical,('vertices','edges','polygons','uv','materials','attributes'),'physical fields')
    vertices=physical['vertices'];edges=physical['edges'];polys=physical['polygons'];loops=state['loops'];faces=state['faces']
    require(vertices and edges and polys and loops and len(faces)==len(polys),'Empty native mesh')
    for p in vertices:
        require(len(p)==3,'Bad vertex width')
        for v in p:number(v)
    for edge,seam in edges:
        require(len(edge)==2 and edge[0]!=edge[1] and type(seam) is bool,'Bad edge')
        for i in edge:integer(i,len(vertices))
    for row in loops:
        require(len(row)==2,'Bad loop row');integer(row[0],len(vertices));integer(row[1],len(edges))
    covered=[];triangles={}
    for fi,(face,poly) in enumerate(zip(faces,polys)):
        keys(face,('loops','normal'),'face');normal(face['normal'])
        require(len(poly)==3 and len(poly[0])>=3 and len(set(poly[0]))==len(poly[0]) and type(poly[2]) is bool,'Bad polygon')
        integer(poly[1],len(physical['materials']))
        require([loops[integer(i,len(loops))][0] for i in face['loops']]==poly[0],'Face/loop/vertex relation differs')
        for a,b in zip(face['loops'],face['loops'][1:]+face['loops'][:1]):
            require(set(edges[loops[a][1]][0])=={loops[a][0],loops[b][0]},'Loop edge relation differs')
        covered.extend(face['loops'])
    require(sorted(covered)==list(range(len(loops))),'Incomplete or duplicate corner coverage')
    for row in state['triangles']:
        keys(row,('face','vertices','loops'),'triangle')
        fi=integer(row['face'],len(faces))
        require(len(row['loops'])==3 and len(set(row['loops']))==3,'Invalid triangle loops')
        require(all(i in faces[fi]['loops'] for i in row['loops']),'Triangle escapes polygon')
        require([loops[i][0] for i in row['loops']]==row['vertices'],'Triangle vertex mapping differs')
        points=[vertices[i] for i in row['vertices']]
        u=[points[1][i]-points[0][i] for i in range(3)];v=[points[2][i]-points[0][i] for i in range(3)]
        require(math.hypot(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])>0,'Degenerate native triangle')
        triangles.setdefault(fi,[]).append(row)
    require(set(triangles)==set(range(len(faces))),'Missing polygon triangle coverage')
    require(all(len(triangles[i])==len(face['loops'])-2 for i,face in enumerate(faces)),'Wrong native triangle count')
    for name,uv in physical['uv'].items():
        require(type(name) is str and len(uv)==len(loops),'Incomplete UV layer')
        for p in uv:
            require(len(p)==2,'Bad UV');number(p[0]);number(p[1])
    for name in ('cb_fascia_cap','__mod_weightednormals_faceweight'):
        value=physical['attributes'].get(name)
        require(value is not None and value[:2]==['FACE','INT'] and len(value[2])==len(faces),'Missing FACE INT provenance')
        require(all(type(v) is int for v in value[2]),'Noninteger provenance')
    require(len(state['normals'])==len(state['normal_codes'])==len(loops),'Incomplete normal arrays')
    for n in state['normals']:normal(n)
    for n in state['normal_codes']:
        require(len(n)==2 and all(type(v) is int and -32768<=v<=32767 for v in n),'Invalid native normal code')
    require(len(state['sharp'])==len(edges) and all(type(v) is bool for v in state['sharp']),'Incomplete sharp inventory')
    require(len(state['material_response'])==len(physical['materials']),'Incomplete material response')


def derive_fans(before,seeds,profile):
    """Independent all-face enumeration using historical decoded before vectors."""
    field=before['physical'];loops=before['loops'];faces=before['faces'];old=before['normals']
    tags=field['attributes']['cb_fascia_cap'][2];strengths=field['attributes']['__mod_weightednormals_faceweight'][2]
    by_vertex={}
    for row in seeds:by_vertex.setdefault(row['vertex'],[]).append(row)
    fans=[];rejected=[];bounds=profile['source_local_bounds_m'];y0,y1=bounds['y']
    for fi,face in enumerate(faces):
        if tags[fi]!=profile['retained_face_tag'] or strengths[fi] not in profile['generated_side_strengths']:continue
        points=[field['vertices'][loops[i][0]] for i in face['loops']]
        if any(p[1]<y0 or p[1]>y1 or abs(p[0])<bounds['absolute_x_min'] or p[2]<bounds['z_min'] for p in points):continue
        if max(abs(v) for v in face['normal'])>profile['recess_axis_alignment_exclusion']:continue
        for li in face['loops']:
            vi=loops[li][0];choices=[]
            for seed in by_vertex.get(vi,[]):
                continuity=angle(old[li],old[seed['loop']])
                dot=sum(a*b for a,b in zip(face['normal'],faces[seed['face']]['normal']))
                if continuity<=ANGLE and dot>=math.cos(math.radians(profile['boundary_fan_dihedral_degrees_max'])):
                    choices.append((seed,continuity,dot))
            if not choices:continue
            target=choices[0][0]['target']
            if any(angle(target,s['target'])>ANGLE for s,_,_ in choices):
                rejected.append({'loop':li,'vertex':vi,'reason':'Distinct original normal groups'});continue
            fans.append({'loop':li,'vertex':vi,'face':fi,'tag':tags[fi],'strength':strengths[fi],
                         'seed_loops':[s['loop'] for s,_,_ in choices],
                         'before_continuity_max_degrees':max(c for _,c,_ in choices),
                         'geometric_dihedral_max_degrees':max(math.degrees(math.acos(max(-1.,min(1.,d)))) for _,_,d in choices),
                         'point':field['vertices'][vi],'before':old[li],'target':target})
    return fans,rejected


def derive_splits(before,targets):
    loops=before['loops'];edges=before['physical']['edges'];old=before['normals'];adjacency={}
    desired=[targets.get(i,n) for i,n in enumerate(old)]
    for fi,face in enumerate(before['faces']):
        mapping={loops[i][0]:i for i in face['loops']}
        for li in face['loops']:adjacency.setdefault(loops[li][1],[]).append((fi,mapping))
    result=[]
    for ei,(vertices,_) in enumerate(edges):
        if before['sharp'][ei]:continue
        pair=adjacency.get(ei,[]);require(len(pair)==2,'Nonmanifold source edge')
        reasons=[]
        for vi in vertices:
            a,b=pair[0][1][vi],pair[1][1][vi]
            if (a in targets or b in targets) and angle(desired[a],desired[b])>ANGLE:
                reasons.append({'vertex':vi,'loops':[a,b],'faces':[pair[0][0],pair[1][0]],
                                'desired_angle_degrees':angle(desired[a],desired[b]),
                                'before_angle_degrees':angle(old[a],old[b]),'selected':[a in targets,b in targets]})
        if reasons:result.append({'edge':ei,'vertices':vertices,'reasons':reasons})
    return result


def validate_data(report,packet,payload,fresh_reference,profile):
    """Pure data path used identically by native checker and host controls."""
    require(report['schema']=='shoulder-source-correspondence.v1' and report['status']=='passed','Not a passed shoulder source report')
    require(report['human_approval_reference'] is None and report['source_saved'] is False,'Wrong approval/source-save scope')
    require(report['native']=={'version':'5.1.2','build':'ec6e62d40fa9'},'Wrong native build')
    hash_value(report['source_sha256'])
    require(payload['schema']=='shoulder-native-payload.v1' and payload['source_sha256']==report['source_sha256'],'Wrong payload source')
    keys(payload,('schema','source_sha256','native','evaluated_bumper'),'source payload')
    keys(packet,('core','sha256'),'construction packet');require(digest(packet['core'])==packet['sha256'],'Construction packet digest differs')
    p=packet['core'];keys(p,('schema','checkpoint','witness','witness_sha256','selected_corners','unselected_corners'),'packet core')
    require(p['schema']=='shoulder-construction-packet.v1','Wrong packet schema')
    cp=p['checkpoint'];keys(cp,('core','sha256'),'before packet');require(digest(cp['core'])==cp['sha256'],'Before checkpoint digest differs')
    c=cp['core'];keys(c,('schema','phase','profile','profile_sha256','reference','reference_sha256','construction_inputs','constructor_inputs_sha256','before','before_sha256','provenance'),'before core')
    require(c['schema']=='shoulder-before-apply.v1' and c['phase']=='final-geometry-before-shoulder-apply','Wrong construction boundary')
    same_numbers(c['profile'],profile,'Locked profile')
    require(digest(profile)=='fc97126bec64c57d9264c6b8cd256222982acf6f00176d5c2df57f26bc1cb8fb','Unreviewed finite profile')
    require(c['profile_sha256']==digest(profile) and report['profile_sha256']==digest(profile),'Wrong profile hash')
    require(profile['normal_angle_guard_degrees']==ANGLE and profile['raw_normal_unit_error_max']==UNIT and profile['whole_face_projection_guard_m']==1e-6 and profile['corner_lookup_guard_m']==2e-6,'Changed numeric guard')
    require(c['reference_sha256']==digest(c['reference']) and c['reference']==fresh_reference,'Fresh original reference differs')
    require(c['reference']['field_sha256']==digest(c['reference']['field']),'Reference field hash differs')
    require(c['reference']['scope_sha256']==digest(profile),'Reference scope differs')
    inputs=c['construction_inputs'];require(type(inputs) is list and inputs,'Missing constructor input inventory')
    for row in inputs:
        keys(row,('role','path','sha256','bytes'),'constructor input');hash_value(row['sha256']);integer(row['bytes'])
        require(type(row['path']) is str and row['path'] and row['bytes']>0,'Empty constructor input')
    require(len({r['path'] for r in inputs})==len(inputs),'Duplicate constructor path')
    for role in ('specification','constructor','normal_module','ownership_module'):
        require(sum(r['role']==role for r in inputs)==1,'Missing/duplicate '+role)
    require(c['constructor_inputs_sha256']==digest(inputs)==report['constructor_inputs_sha256'],'Wrong constructor-input hash')
    before=c['before'];after=payload['native'];validate_state(before);validate_state(after)
    require(digest(before)==c['before_sha256'],'Before raw fields hash differs')
    for key in ('object','coordinate_frame','physical','material_response','loops','faces','triangles'):
        require(before[key]==after[key],'Changed physical/UV/material/native field: '+key)
    require(before['coordinate_frame']==fresh_reference['coordinate_frame'],'Reference frame differs')
    w=p['witness'];require(digest(w)==p['witness_sha256'],'Witness hash differs')
    require(w['status']=='applied-original-shoulder-field' and w['source_saved'] is False and w['human_approval_reference'] is None,'Wrong application scope')
    require(w['object']==before['object'] and w['geometry_sha256']==digest(before['physical']) and w['profile_sha256']==digest(profile) and w['reference_packet_sha256']==digest(fresh_reference),'Witness binding differs')
    proof=report['geometry_proof']
    for key in ('candidate_faces','owned_faces','unowned_faces','excluded_generated_strength_faces','ambiguous_corners','details'):
        same_numbers(w[key],proof[key],'Native geometry '+key)
    require(not w['ambiguous_corners'],'Ambiguous original corner')
    candidate=w['candidate_faces'];owned=w['owned_faces'];unowned=w['unowned_faces']
    expected_candidate=[];expected_excluded=[]
    tags=before['physical']['attributes']['cb_fascia_cap'][2]
    strengths=before['physical']['attributes']['__mod_weightednormals_faceweight'][2]
    bounds=profile['source_local_bounds_m'];y0,y1=bounds['y']
    for fi,face in enumerate(before['faces']):
        points=[before['physical']['vertices'][before['loops'][li][0]] for li in face['loops']]
        if tags[fi]!=profile['retained_face_tag'] or face['normal'][2]<profile['minimum_face_normal_z']:continue
        if any(p[1]<y0 or p[1]>y1 or abs(p[0])<bounds['absolute_x_min'] or p[2]<bounds['z_min'] for p in points):continue
        (expected_candidate if strengths[fi]==profile['retained_face_strength'] else expected_excluded).append(fi)
    require(candidate==expected_candidate and w['excluded_generated_strength_faces']==expected_excluded,'Incomplete finite-domain candidate inventory')
    require(len(owned)>=profile['minimum_whole_owned_faces'] and sorted(owned+unowned)==sorted(candidate) and len(set(candidate))==len(candidate),'Owned/unowned inventory incomplete')
    for rows in (candidate,owned,unowned,w['excluded_generated_strength_faces']):
        require(len(set(rows))==len(rows),'Duplicate face inventory')
        for i in rows:integer(i,len(before['faces']))
    details=w['details'];require(len(details)>=profile['minimum_original_corners'],'Too few original corners')
    expected_seeds=[i for fi in owned for i in before['faces'][fi]['loops']]
    require([r['loop'] for r in details]==expected_seeds,'Incomplete owned corner inventory')
    require({-1 if r['point'][0]<0 else 1 for r in details}=={-1,1},'Missing shoulder side')
    for row in details:
        li=row['loop'];normal(row['target'])
        require(row['face'] in owned and li in before['faces'][row['face']]['loops'] and row['vertex']==before['loops'][li][0] and row['point']==before['physical']['vertices'][row['vertex']],'Wrong original corner mapping')
        require(row['before']==before['normals'][li],'Wrong historical original corner')
        integer(row['reference_triangle'],len(fresh_reference['field']['triangles']))
        require(0<=number(row['distance_m'])<=2e-6,'Original corner misses reference')
        require(number(row['drift_binary64_degrees'])==angle(row['before'],row['target']),'Wrong original drift')
    fans,rejected=derive_fans(before,details,profile)
    same_numbers(w['propagated_boundary_fans'],fans,'Generated fan inventory')
    same_numbers(w['rejected_ambiguous_boundary_fans'],rejected,'Rejected fan inventory')
    targets={r['loop']:r['target'] for r in details+fans};selected=sorted(targets);unselected=[i for i in range(len(before['loops'])) if i not in targets]
    for values in (p['selected_corners'],p['unselected_corners']):
        require(type(values) is list,'Missing typed corner inventory')
        for i in values:integer(i,len(before['loops']))
    require(len(targets)==len(details)+len(fans) and p['selected_corners']==selected and p['unselected_corners']==unselected,'Incomplete selected/unselected partition')
    splits=derive_splits(before,targets)
    same_numbers(w['requested_normal_group_splits'],splits,'Requested sharp split inventory')
    delta=[{'edge':i,'vertices':before['physical']['edges'][i][0],'before':a,'after':b} for i,(a,b) in enumerate(zip(before['sharp'],after['sharp'])) if a!=b]
    require(all(r['before'] is False and r['after'] is True for r in delta),'Sharp flag removed')
    same_numbers(w['declared_sharp_additions'],delta,'Actual sharp delta inventory')
    # Fail closed if a setter adds another split: no incidental sharp change is
    # accepted merely because it touches a selected vertex.
    require([r['edge'] for r in delta]==[r['edge'] for r in splits],'Sharp change lacks exact original-group reason')
    target_errors=[angle(after['normals'][i],targets[i]) for i in selected]
    other_errors=[angle(before['normals'][i],after['normals'][i]) for i in unselected]
    require(target_errors and max(target_errors)<=ANGLE,'Saved selected native target differs')
    require(other_errors and max(other_errors)<=ANGLE,'Saved unrelated native corner differs')
    metrics={'owned_faces':len(owned),'unowned_faces':len(unowned),'original_corners':len(details),
             'generated_fans':len(fans),'rejected_ambiguous_fans':len(rejected),'selected_corners':len(selected),
             'unselected_corners':len(unselected),'sharp_additions':len(delta),
             'maximum_target_error_degrees':max(target_errors),'maximum_unrelated_delta_degrees':max(other_errors),
             'unrelated_vectors_exact':sum(before['normals'][i]==after['normals'][i] for i in unselected),
             'raw_normal_maximum_unit_error':max(abs(math.hypot(*n)-1) for n in after['normals'])}
    expected={'target_count':metrics['selected_corners'],'maximum_target_error_degrees':metrics['maximum_target_error_degrees'],
              'maximum_unrelated_delta_degrees':metrics['maximum_unrelated_delta_degrees'],'unrelated_count':metrics['unselected_corners'],
              'unrelated_vectors_exact':metrics['unrelated_vectors_exact'],'raw_normal_maximum_unit_error':metrics['raw_normal_maximum_unit_error']}
    for key,value in expected.items():same_numbers(w[key],value,'Witness measured '+key)
    require(w['projection_guard_m']==1e-6 and w['lookup_guard_m']==2e-6,'Changed witness geometric guard')
    return metrics


def read_json(path):
    def pairs(rows):
        result={}
        for key,value in rows:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    def reject(value):raise ValueError('Nonfinite JSON constant: '+value)
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt',encoding='utf8') as stream:return json.load(stream,object_pairs_hook=pairs,parse_constant=reject)


def artifact(row,base=None):
    keys(row,('path','sha256','bytes'),'artifact');hash_value(row['sha256']);integer(row['bytes'])
    path=Path(row['path'])
    if not path.is_absolute() and base is not None:
        root=Path(base).resolve(strict=True);path=(root/path).resolve(strict=True)
        require(path.is_relative_to(root),'Relative constructor input escapes root')
    require(path.is_file() and path.stat().st_size==row['bytes'],'Missing or wrong-size artifact')
    require(hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],'Artifact SHA differs')
    return path


def validate_report(report,source_sha256,*,expected_profile_sha256=None,expected_constructor_inputs_sha256=None,
                    expected_packet_sha256=None,expected_geometry_sha256=None,construction_root=None):
    keys(report,('schema','status','source_sha256','profile_sha256','constructor_inputs_sha256','native','bindings','geometry_proof','metrics','source_saved','human_approval_reference'),'source report')
    require(report['source_sha256']==hash_value(source_sha256),'Wrong expected source')
    bindings=report['bindings'];keys(bindings,('source','payload','packet','fresh_reference','profile','geometry','tools'),'report bindings')
    require(bindings['source']['sha256']==source_sha256,'Wrong source-file binding')
    artifact(bindings['source'])
    require(bindings['tools'] and len({r['path'] for r in bindings['tools']})==len(bindings['tools']),'Missing/duplicate checker tool binding')
    for row in bindings['tools']:artifact(row)
    data={key:read_json(artifact(bindings[key])) for key in ('payload','packet','fresh_reference','profile')}
    geometry=read_json(artifact(bindings['geometry']))
    require(geometry['source_sha256']==source_sha256 and geometry['meshes']['LOD0_FrontBumper']==data['payload']['evaluated_bumper'],'Extracted source payload differs')
    if expected_profile_sha256 is not None:require(bindings['profile']['sha256']==hash_value(expected_profile_sha256),'Wrong expected profile file')
    if expected_constructor_inputs_sha256 is not None:require(report['constructor_inputs_sha256']==hash_value(expected_constructor_inputs_sha256),'Wrong expected constructor lock')
    if expected_packet_sha256 is not None:require(bindings['packet']['sha256']==hash_value(expected_packet_sha256),'Wrong expected construction packet')
    if expected_geometry_sha256 is not None:require(bindings['geometry']['sha256']==hash_value(expected_geometry_sha256),'Wrong expected extracted geometry')
    for row in data['packet']['core']['checkpoint']['core']['construction_inputs']:
        artifact({k:row[k] for k in ('path','sha256','bytes')},construction_root)
    metrics=validate_data(report,data['packet'],data['payload'],data['fresh_reference'],data['profile'])
    same_numbers(report['metrics'],metrics,'Report numeric metrics')
    return metrics
