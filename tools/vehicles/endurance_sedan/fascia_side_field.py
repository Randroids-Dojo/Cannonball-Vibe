"""Bounded semantic/geometric correction for the measured outer-side endpoint fix."""
import math

def angle(a,b):
    return math.degrees(math.acos(max(-1.,min(1.,sum(x*y for x,y in zip(a,b))/(math.hypot(*a)*math.hypot(*b))))))
def unit(a):return tuple(x/math.hypot(*a) for x in a)
def physical(mesh):
    return {'vertices':[tuple(v.co) for v in mesh.vertices],
            'faces':[(tuple(p.vertices),p.material_index,p.use_smooth) for p in mesh.polygons],
            'uv':{u.name:[tuple(v.uv) for v in u.data] for u in mesh.uv_layers},
            'materials':[m.as_pointer() if m else None for m in mesh.materials],
            'tags':{n:[v.value for v in mesh.attributes[n].data] for n in ('cb_fascia_cap','__mod_weightednormals_faceweight')}}

def select(obj,*,optical_floor_z=.673):
    if obj.name!='LOD0_FrontBumper':raise ValueError('Wrong semantic mesh')
    if not math.isfinite(optical_floor_z):raise ValueError('Nonfinite optical plane')
    mesh=obj.data;tag=mesh.attributes.get('cb_fascia_cap');strength=mesh.attributes.get('__mod_weightednormals_faceweight')
    if any(a is None or a.domain!='FACE' or a.data_type!='INT' for a in (tag,strength)):
        raise ValueError('Missing retained-face provenance')
    cap={};side={}
    for p in mesh.polygons:
        if strength.data[p.index].value!=16384 or tag.data[p.index].value not in (0,1):continue
        for li in p.loop_indices:
            (side if tag.data[p.index].value==0 else cap).setdefault(mesh.loops[li].vertex_index,[]).append((p.index,li))
    result=[]
    for vi in sorted(set(side)&set(cap)):
        point=tuple(mesh.vertices[vi].co)
        if not all(math.isfinite(x) for x in point):raise ValueError('Nonfinite shared endpoint')
        x,y,z=point
        # This is the declared finite original optical-corner neighborhood,
        # tied to the existing opening's lower plane. It is not all tag0 faces.
        if not (.80<=abs(x)<=.87 and 2.20<=y<=2.28 and optical_floor_z-.006<=z<optical_floor_z):continue
        faces=sorted(set(pi for pi,li in side[vi]))
        if len(faces)!=1:raise ValueError('Ambiguous original-side endpoint incidence')
        face=mesh.polygons[faces[0]]
        if len(face.vertices)!=3 or abs(face.normal.z)>.10:raise ValueError('Endpoint is not the observed original outer side patch')
        target=unit(tuple(face.normal))
        result.append({'vertex':vi,'point':point,'side_face':face.index,
                       'selected_loops':[li for pi,li in side[vi]],'target':target,
                       'cap_faces':sorted(set(pi for pi,li in cap[vi]))})
    if len(result)!=2:raise ValueError('Expected exactly two symmetric outer-side endpoints')
    result.sort(key=lambda r:r['point'][0]);a,b=result
    if not a['point'][0]<0<b['point'][0] or math.dist((-a['point'][0],a['point'][1],a['point'][2]),b['point'])>2e-6:
        raise ValueError('Outer-side endpoint symmetry mismatch')
    if any(len(r['selected_loops'])!=1 for r in result):raise ValueError('Unexpected endpoint corner inventory')
    return result

def apply(obj,*,optical_floor_z=.673):
    selected=select(obj,optical_floor_z=optical_floor_z);mesh=obj.data
    before_fields=physical(mesh);old_sharp=[e.use_edge_sharp for e in mesh.edges]
    before=[tuple(n.vector) for n in mesh.corner_normals]
    if not all(all(math.isfinite(v) for v in n) and abs(math.hypot(*n)-1)<1e-5 for n in before):
        raise ValueError('Invalid native input normals')
    targets={li:r['target'] for r in selected for li in r['selected_loops']}
    old_codes=[tuple(v.value) for v in mesh.attributes['custom_normal'].data]
    values=list(before)
    for li,target in targets.items():values[li]=target
    mesh.normals_split_custom_set(values)
    fresh_codes=[tuple(v.value) for v in mesh.attributes['custom_normal'].data]
    fresh=[tuple(n.vector) for n in mesh.corner_normals]
    for li,code in enumerate(old_codes):
        if li not in targets:mesh.attributes['custom_normal'].data[li].value=code
    mesh.update();restored=[tuple(n.vector) for n in mesh.corner_normals]
    for li in range(len(before)):
        if li not in targets and angle(before[li],fresh[li])<angle(before[li],restored[li]):
            mesh.attributes['custom_normal'].data[li].value=fresh_codes[li]
    mesh.update();after=[tuple(n.vector) for n in mesh.corner_normals]
    if physical(mesh)!=before_fields:raise ValueError('Geometry/UV/material/retained provenance changed')
    changes=[];vertices={r['vertex'] for r in selected}
    for i,e in enumerate(mesh.edges):
        if e.use_edge_sharp==old_sharp[i]:continue
        if old_sharp[i] or not e.use_edge_sharp or not vertices&set(e.vertices):raise ValueError('Normal split escaped selected endpoint fans')
        changes.append({'edge':i,'vertices':tuple(e.vertices),'before_sharp':old_sharp[i],'after_sharp':e.use_edge_sharp})
    maximum=max(angle(a,b) for i,(a,b) in enumerate(zip(before,after)) if i not in targets)
    target_error=max(angle(after[i],t) for i,t in targets.items())
    if maximum>.025 or target_error>.025:raise ValueError('Unbounded native normal encoding delta')
    recess=[]
    for p in mesh.polygons:
        zs=[mesh.vertices[v].co.z for v in p.vertices]
        if abs(p.normal.z)>.999 and max(abs(z-optical_floor_z) for z in zs)<1e-5:
            if any(before[i]!=after[i] for i in p.loop_indices):raise ValueError('Actual optical recess plane normals changed')
            recess.append(p.index)
    if not recess:raise ValueError('No actual optical-recess plane witness')
    return {'status':'applied-two-symmetric-original-side-endpoint-corners','selected':selected,
            'selected_corner_count':len(targets),'declared_sharp_edge_changes':changes,
            'maximum_unselected_corner_delta_degrees':maximum,'maximum_target_error_degrees':target_error,
            'unselected_vectors_exact':sum(a==b for i,(a,b) in enumerate(zip(before,after)) if i not in targets),
            'unselected_corner_count':len(before)-len(targets),'optical_recess_exact_normal_faces':recess,
            'geometry_uv_material_provenance_exact':True,'original_sharp_policy_exact':False,
            'optical_floor_z_m':optical_floor_z,'finite_neighborhood_m':{'abs_x':[.80,.87],'y':[2.20,2.28],'below_optical_floor':[0,.006]},
            'source_saved':False,'human_approval_reference':None}
