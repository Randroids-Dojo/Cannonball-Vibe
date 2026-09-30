"""Guarded original side-field restoration; no source save or geometry edits."""
import hashlib
import json
import math

import bpy
from mathutils import Vector,geometry

EXPECTED_PROFILE = {'schema': 'original-bumper-shoulder-field.v1', 'semantic': 'LOD0_FrontBumper', 'source_local_bounds_m': {'y': [1.87, 2.31], 'absolute_x_min': 0.6, 'z_min': 0.78}, 'minimum_face_normal_z': 0.1, 'retained_face_tag': 0, 'retained_face_strength': 16384, 'generated_side_strengths': [-16384, 0], 'whole_face_projection_guard_m': 1e-06, 'corner_lookup_guard_m': 2e-06, 'original_face_alignment_dot_min': 0.99985, 'normal_angle_guard_degrees': 0.025, 'raw_normal_unit_error_max': 1e-06, 'lookup_tie_distance_m': 1e-09, 'lookup_tie_alignment': 1e-09, 'boundary_fan_dihedral_degrees_max': 35, 'recess_axis_alignment_exclusion': 0.999, 'minimum_whole_owned_faces': 100, 'minimum_original_corners': 300}

def validate_profile(profile):
    """Only the reviewed finite geometry domain and unchanged guards are valid."""
    def same(actual, expected):
        if isinstance(expected, dict):
            return type(actual) is dict and set(actual)==set(expected) and all(same(actual[k],v) for k,v in expected.items())
        if isinstance(expected, list):
            return type(actual) is list and len(actual)==len(expected) and all(same(a,b) for a,b in zip(actual,expected))
        if type(expected) in (int,float):
            return type(actual) in (int,float) and math.isfinite(actual) and actual==expected
        return type(actual) is type(expected) and actual==expected
    if not same(profile,EXPECTED_PROFILE):raise ValueError('Unreviewed shoulder geometry scope or normal guard')
    return profile


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def pack_reference(body,field,profile):
    validate_profile(profile)
    return {'schema':'captured-original-shoulder-field.v1','scope_sha256':digest(profile),
            'coordinate_space':'native-source-local-meters','coordinate_frame':[list(r) for r in body.matrix_world],
            'capture_object':body.name,'capture_physical_sha256':fingerprint(body.data),
            'field':field,'field_sha256':digest(field)}


def reference_field(obj,reference,profile):
    validate_profile(profile)
    if type(reference) is not dict or set(reference)!={'schema','scope_sha256','coordinate_space','coordinate_frame','capture_object','capture_physical_sha256','field','field_sha256'}:
        raise ValueError('Incomplete original capture packet')
    if (reference['schema']!='captured-original-shoulder-field.v1' or reference['scope_sha256']!=digest(profile)
            or reference['coordinate_space']!='native-source-local-meters'
            or reference['coordinate_frame']!=[list(r) for r in obj.matrix_world]):
        raise ValueError('Original reference scope or coordinate frame differs')
    if type(reference['capture_object']) is not str or not reference['capture_object']:
        raise ValueError('Missing original capture object')
    capture_hash=reference['capture_physical_sha256']
    if type(capture_hash) is not str or len(capture_hash)!=64 or any(c not in '0123456789abcdef' for c in capture_hash):
        raise ValueError('Invalid original physical hash')
    field=reference['field']
    if type(field) is not dict or set(field)!={'vertices','triangles','normals'} or digest(field)!=reference['field_sha256']:
        raise ValueError('Original field packet hash or inventory differs')
    return field


def angle(a,b):
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross),sum(x*y for x,y in zip(a,b))))


def valid_normal(n):return len(n)==3 and all(math.isfinite(v) for v in n) and abs(math.hypot(*n)-1)<=1e-6


def capture(body,profile,*,authored_corner_targets=None):
    """Capture current pre-Boolean geometry with native or bounded authored targets."""
    validate_profile(profile)
    if body.type!='MESH' or body.modifiers:raise ValueError('Expected native original body without pending modifiers')
    bounds=profile['source_local_bounds_m'];y_min,y_max=bounds['y'];x_min=bounds['absolute_x_min'];z_min=bounds['z_min']
    mesh=body.data;mesh.calc_loop_triangles();points=[];triangles=[];normals=[]
    targets=authored_corner_targets
    if targets is not None:
        if len(targets)!=len(mesh.loops) or not all(valid_normal(n) for n in targets):raise ValueError("Incomplete authored prefix target")
        if max(angle(a,tuple(b.vector)) for a,b in zip(targets,mesh.corner_normals))>.025:raise ValueError("Authored prefix differs from actual native field")
    for tri in mesh.loop_triangles:
        face=mesh.polygons[tri.polygon_index];ps=[tuple(mesh.vertices[v].co) for v in tri.vertices]
        if mesh.attributes['cb_fascia_cap'].data[face.index].value!=0:continue
        if face.normal.z<profile['minimum_face_normal_z'] or max(p[1] for p in ps)<y_min or min(p[1] for p in ps)>y_max:continue
        if max(abs(p[0]) for p in ps)<x_min or max(p[2] for p in ps)<z_min:continue
        ns=[tuple(mesh.corner_normals[i].vector) if targets is None else tuple(targets[i]) for i in tri.loops]
        if not all(valid_normal(n) for n in ns):raise ValueError('Invalid original raw normal')
        start=len(points);points.extend(ps);triangles.append([start,start+1,start+2]);normals.append(ns)
    if not triangles:raise ValueError('Empty original side field')
    return pack_reference(body,{'vertices':points,'triangles':triangles,'normals':normals},profile)


def fields(mesh):
    result={'vertices':[tuple(v.co) for v in mesh.vertices],'edges':[(tuple(e.vertices),e.use_seam) for e in mesh.edges],
            'polygons':[(tuple(p.vertices),p.material_index,p.use_smooth) for p in mesh.polygons],
            'uv':{u.name:[tuple(v.uv) for v in u.data] for u in mesh.uv_layers},
            'materials':[m.name if m else None for m in mesh.materials],'attributes':{}}
    for attr in mesh.attributes:
        if attr.name in ('position','.edge_verts','.corner_vert','.corner_edge','custom_normal','sharp_edge'):continue
        data=[]
        for item in attr.data:
            key=next(k for k in ('value','vector','color') if hasattr(item,k));value=getattr(item,key)
            data.append(value if isinstance(value,(str,float,int,bool)) else tuple(value))
        result['attributes'][attr.name]=(attr.domain,attr.data_type,data)
    return result


def fingerprint(mesh):return hashlib.sha256(json.dumps(fields(mesh),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def barycentric(point,ps,ns):
    a,b,c=ps;u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)];w=[point[i]-a[i] for i in range(3)]
    dot=lambda a,b:sum(x*y for x,y in zip(a,b))
    uu,uv,vv,wu,wv=dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
    den=uu*vv-uv*uv
    if den<=0:raise ValueError('Degenerate original triangle')
    q=(vv*wu-uv*wv)/den;r=(uu*wv-uv*wu)/den
    value=[(1-q-r)*ns[0][i]+q*ns[1][i]+r*ns[2][i] for i in range(3)]
    length=math.hypot(*value)
    if length<.5:raise ValueError('Invalid interpolated original normal')
    return tuple(x/length for x in value)


def prepare(obj,reference,profile,ownership):
    validate_profile(profile)
    if obj.name!=profile['semantic'] or obj.type!='MESH' or obj.modifiers:raise ValueError('Expected final FrontBumper mesh')
    packet=reference;reference=reference_field(obj,packet,profile)
    bounds=profile['source_local_bounds_m'];y_min,y_max=bounds['y'];x_min=bounds['absolute_x_min'];z_min=bounds['z_min']
    ps,ts,ns=reference['vertices'],reference['triangles'],reference['normals']
    if not ps or not ts or len(ts)!=len(ns):raise ValueError('Empty or incomplete original reference')
    if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in ps):raise ValueError('Nonfinite original geometry')
    if any(len(t)!=3 or any(type(i) is not int or not 0<=i<len(ps) for i in t) for t in ts):raise ValueError('Bad original index')
    if any(len(row)!=3 or not all(valid_normal(n) for n in row) for row in ns):raise ValueError('Invalid original normal')
    mesh=obj.data;mesh.calc_loop_triangles()
    tag=mesh.attributes.get('cb_fascia_cap');strength=mesh.attributes.get('__mod_weightednormals_faceweight')
    if any(a is None or a.domain!='FACE' or a.data_type!='INT' for a in (tag,strength)):raise ValueError('Missing FACE INT provenance')
    before=[tuple(n.vector) for n in mesh.corner_normals]
    if not all(valid_normal(n) for n in before):raise ValueError('Invalid source raw normal')
    patch=ownership._patch((None,[Vector(p) for p in ps],ts,[[Vector(n) for n in row] for row in ns]))
    face_tris={};loop_faces={}
    for t in mesh.loop_triangles:face_tris.setdefault(t.polygon_index,[]).append([tuple(mesh.vertices[v].co) for v in t.vertices])
    for p in mesh.polygons:
        for li in p.loop_indices:loop_faces[li]=p.index
    targets={};owned=[];unowned=[];candidate=[];excluded_strength=[];ambiguities=[];details=[]
    for face in mesh.polygons:
        points=[tuple(mesh.vertices[v].co) for v in face.vertices]
        if tag.data[face.index].value!=0:continue
        if face.normal.z<profile['minimum_face_normal_z'] or min(p[1] for p in points)<y_min or max(p[1] for p in points)>y_max:continue
        if min(abs(p[0]) for p in points)<x_min or min(p[2] for p in points)<z_min:continue
        if strength.data[face.index].value!=16384:excluded_strength.append(face.index);continue
        candidate.append(face.index)
        if not all(ownership._covers(t,patch) for t in face_tris[face.index]):unowned.append(face.index);continue
        owned.append(face.index)
        # Restrict corner queries to the exact aligned original planes used by
        # whole-face ownership, preserving a physical side/cap or crease split.
        eligible=[]
        for ri,(rps,rn,_,rns) in enumerate(patch):
            alignment=sum(float(face.normal[i])*rn[i] for i in range(3))
            if alignment<.99985:continue
            if max(abs(sum((p[i]-rps[0][i])*rn[i] for i in range(3))) for p in points)>1e-6:continue
            eligible.append((ri,rps,rns,alignment))
        for li in face.loop_indices:
            point=mesh.vertices[mesh.loops[li].vertex_index].co;choices=[]
            for ri,rps,rns,alignment in eligible:
                hit=geometry.closest_point_on_tri(point,*[Vector(p) for p in rps]);distance=math.dist(tuple(point),tuple(hit))
                if distance>2e-6:continue
                target=barycentric(tuple(hit),rps,rns)
                choices.append((distance,-alignment,ri,target))
            if not choices:raise ValueError('Owned corner lacks an aligned original reference')
            best=min(choices,key=lambda r:r[:3])
            tied=[q for q in choices if q[0]<=best[0]+1e-9 and abs(q[1]-best[1])<=1e-9]
            if any(angle(q[3],best[3])>.025 for q in tied):
                ambiguities.append({'face':face.index,'loop':li,'choices':tied})
            targets[li]=best[3]
            details.append({'face':face.index,'loop':li,'vertex':mesh.loops[li].vertex_index,'point':tuple(point),
                            'reference_triangle':best[2],'distance_m':best[0],'before':before[li],'target':best[3],
                            'drift_binary64_degrees':angle(before[li],best[3])})
    side=lambda x:-1 if x<0 else 1
    if (len(owned)<profile['minimum_whole_owned_faces'] or len(targets)<profile['minimum_original_corners']
            or {side(d['point'][0]) for d in details}!={-1,1}):
        raise ValueError('Missing original owned shoulder field on one or both sides')
    seed_by_vertex={}
    for detail in details:seed_by_vertex.setdefault(detail['vertex'],[]).append(detail)
    propagated=[];rejected_boundary=[]
    for face in mesh.polygons:
        if tag.data[face.index].value!=0 or strength.data[face.index].value not in (-16384,0):continue
        points=[tuple(mesh.vertices[v].co) for v in face.vertices]
        if min(p[1] for p in points)<y_min or max(p[1] for p in points)>y_max or min(abs(p[0]) for p in points)<x_min or min(p[2] for p in points)<z_min:continue
        if max(abs(float(v)) for v in face.normal)>.999:continue
        for li in face.loop_indices:
            vi=mesh.loops[li].vertex_index
            choices=[]
            for seed in seed_by_vertex.get(vi,[]):
                before_angle=angle(before[li],before[seed['loop']])
                geometric=sum(float(face.normal[i])*float(mesh.polygons[seed['face']].normal[i]) for i in range(3))
                if before_angle<=.025 and geometric>=math.cos(math.radians(35)):
                    choices.append((seed,before_angle,geometric))
            if not choices:continue
            value=choices[0][0]['target']
            if any(angle(value,seed['target'])>.025 for seed,_,_ in choices):
                rejected_boundary.append({'loop':li,'vertex':vi,'reason':'Distinct original normal groups'});continue
            targets[li]=value
            propagated.append({'loop':li,'vertex':vi,'face':face.index,'tag':0,'strength':strength.data[face.index].value,
                               'seed_loops':[seed['loop'] for seed,_,_ in choices],'before_continuity_max_degrees':max(v for _,v,_ in choices),
                               'geometric_dihedral_max_degrees':max(math.degrees(math.acos(max(-1.,min(1.,v)))) for _,_,v in choices),
                               'point':tuple(mesh.vertices[vi].co),'before':before[li],'target':value})
    return {'object':obj.name,'geometry_sha256':fingerprint(mesh),'reference_packet_sha256':digest(packet),'profile_sha256':digest(profile),'before':before,'targets':targets,'details':details,
            'candidate_faces':candidate,'owned_faces':owned,'unowned_faces':unowned,'excluded_generated_strength_faces':excluded_strength,
            'ambiguous_corners':ambiguities,'propagated_boundary_fans':propagated,'rejected_ambiguous_boundary_fans':rejected_boundary,'projection_guard_m':1e-6,'lookup_guard_m':2e-6,
            'scope':'Wholly owned retained tag0 shoulder faces only. Cap and unowned retained triangles are excluded. Generated faces are never claimed wholly owned; only explicitly reported previously-continuous same-side boundary corners may inherit a proven side value. Each corner comes from an aligned original reference plane; native reference discontinuities are not averaged.'}


def apply(obj,reference,profile,ownership):
    plan=prepare(obj,reference,profile,ownership)
    if plan['ambiguous_corners']:raise ValueError('Ambiguous original shoulder corner field')
    staged=obj.data.copy()
    try:
        before=plan['before'];targets=plan['targets'];old_fields=fields(obj.data)
        old_sharp=[e.use_edge_sharp for e in staged.edges]
        old_codes=[tuple(n.value) for n in staged.attributes['custom_normal'].data]
        values=list(before)
        for li,n in targets.items():values[li]=n
        edge_faces={}
        for face in staged.polygons:
            at_vertex={staged.loops[li].vertex_index:li for li in face.loop_indices}
            for li in face.loop_indices:edge_faces.setdefault(staged.loops[li].edge_index,[]).append((face.index,at_vertex))
        requested_splits=[]
        for edge in staged.edges:
            if edge.use_edge_sharp:continue
            adjacent=edge_faces[edge.index]
            if len(adjacent)!=2:raise ValueError('Nonmanifold selected surface')
            reasons=[]
            for vi in edge.vertices:
                a,b=adjacent[0][1][vi],adjacent[1][1][vi]
                if (a in targets or b in targets) and angle(values[a],values[b])>.025:
                    reasons.append({'vertex':vi,'loops':[a,b],'faces':[adjacent[0][0],adjacent[1][0]],'desired_angle_degrees':angle(values[a],values[b]),'before_angle_degrees':angle(before[a],before[b]),'selected':[a in targets,b in targets]})
            if reasons:
                edge.use_edge_sharp=True;requested_splits.append({'edge':edge.index,'vertices':list(edge.vertices),'reasons':reasons})
        staged.normals_split_custom_set(values)
        fresh_codes=[tuple(n.value) for n in staged.attributes['custom_normal'].data];fresh=[tuple(n.vector) for n in staged.corner_normals]
        for li,code in enumerate(old_codes):
            if li not in targets:staged.attributes['custom_normal'].data[li].value=code
        staged.update();restored=[tuple(n.vector) for n in staged.corner_normals]
        for li in range(len(before)):
            if li not in targets and angle(before[li],fresh[li])<angle(before[li],restored[li]):
                staged.attributes['custom_normal'].data[li].value=fresh_codes[li]
        staged.update();after=[tuple(n.vector) for n in staged.corner_normals]
        if fields(staged)!=old_fields or list(staged.materials)!=list(obj.data.materials):raise ValueError('Geometry/UV/material/provenance changed')
        if not all(valid_normal(n) for n in after):raise ValueError('Invalid final raw native normal')
        max_other=max(angle(before[i],after[i]) for i in range(len(before)) if i not in targets)
        max_target=max(angle(after[i],n) for i,n in targets.items())
        if max_other>.025 or max_target>.025:raise ValueError(f'Native encoding bound exceeded: unrelated={max_other}; target={max_target}')
        selected_vertices={staged.loops[li].vertex_index for li in targets};sharp=[]
        for edge,was in zip(staged.edges,old_sharp):
            if edge.use_edge_sharp==was:continue
            if was or not edge.use_edge_sharp or not set(edge.vertices)&selected_vertices:raise ValueError('Sharp change escaped selected fan')
            sharp.append({'edge':edge.index,'vertices':list(edge.vertices),'before':was,'after':edge.use_edge_sharp})
        proof={k:v for k,v in plan.items() if k not in ('targets','before')}
        proof.update(status='applied-original-shoulder-field',target_count=len(targets),maximum_target_error_degrees=max_target,
                     maximum_unrelated_delta_degrees=max_other,unrelated_count=len(before)-len(targets),
                     unrelated_vectors_exact=sum(before[i]==after[i] for i in range(len(before)) if i not in targets),
                     declared_sharp_additions=sharp,requested_normal_group_splits=requested_splits,geometry_uv_material_provenance_exact=True,
                     raw_normal_maximum_unit_error=max(abs(math.hypot(*n)-1) for n in after),
                     source_saved=False,human_approval_reference=None)
        obj.data=staged;staged=None
        return proof
    finally:
        if staged is not None and staged.users==0:bpy.data.meshes.remove(staged)


def verify_owned(obj,reference,profile,ownership):
    """Read-only saved-corner criterion using a freshly regenerated original field.

    This proves retained owned corners, not the historical pre-application fan
    continuity or preservation of unrelated corners; those require the bound
    construction witness described in the integration proposal.
    """
    plan=prepare(obj,reference,profile,ownership)
    errors=[angle(tuple(obj.data.corner_normals[r['loop']].vector),r['target']) for r in plan['details']]
    maximum=max(errors)
    if maximum>.025:raise ValueError('Saved original owned shoulder normals differ')
    return {'status':'passed-original-owned-shoulder-correspondence','object':obj.name,
            'owned_face_count':len(plan['owned_faces']),'owned_corner_count':len(errors),
            'unowned_retained_faces':plan['unowned_faces'],'maximum_error_degrees':maximum,
            'geometry_sha256':plan['geometry_sha256'],'reference_packet_sha256':digest(reference),
            'profile_sha256':digest(profile),'generated_fans_and_before_state_require_construction_witness':True}
