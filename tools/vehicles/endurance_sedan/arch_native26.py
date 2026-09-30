"""Bounded native corner-field encoding; no construction, file IO or source save."""
import bpy
import hashlib,json,math

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def angle(a,b):
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross),sum(x*y for x,y in zip(a,b))))

def valid_normal(n):return len(n)==3 and all(math.isfinite(v) for v in n) and abs(math.hypot(*n)-1)<=1e-6

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

def refine_selected_codes(mesh, targets):
    import itertools
    before = {li:angle(tuple(mesh.corner_normals[li].vector),v) for li,v in targets.items()}
    selected = [li for li,error in before.items() if error>.004]
    codes = {li:tuple(mesh.attributes['custom_normal'].data[li].value) for li in selected}
    best = {li:(before[li],codes[li]) for li in selected}
    offsets = (-128,-64,-32,-16,-8,-4,-2,-1,0,1,2,4,8,16,32,64,128)
    for dx,dy in itertools.product(offsets,repeat=2):
        for li,(a,b) in codes.items():
            mesh.attributes['custom_normal'].data[li].value=(max(-32767,min(32767,a+dx)),max(-32767,min(32767,b+dy)))
        mesh.update()
        for li in selected:
            error=angle(targets[li],tuple(mesh.corner_normals[li].vector))
            if error<best[li][0]:best[li]=(error,tuple(mesh.attributes['custom_normal'].data[li].value))
    centers={li:item[1] for li,item in best.items()}
    for dx,dy in itertools.product(range(-2,3),repeat=2):
        for li,(a,b) in centers.items():
            mesh.attributes['custom_normal'].data[li].value=(max(-32767,min(32767,a+dx)),max(-32767,min(32767,b+dy)))
        mesh.update()
        for li in selected:
            error=angle(targets[li],tuple(mesh.corner_normals[li].vector))
            if error<best[li][0]:best[li]=(error,tuple(mesh.attributes['custom_normal'].data[li].value))
    for li,item in best.items():mesh.attributes['custom_normal'].data[li].value=item[1]
    mesh.update()
    return {'before_max_degrees':max(before.values()),'selected_corners':len(selected),
            'after_max_degrees':max(angle(tuple(mesh.corner_normals[li].vector),v) for li,v in targets.items()),
            'offsets':list(offsets),'best':best}

def apply_targets(obj,plan):
    """Encode an explicit independently prepared native corner-field plan."""
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
                if (a in targets or b in targets) and angle(values[a],values[b])>.000001:
                    reasons.append({'vertex':vi,'loops':[a,b],'faces':[adjacent[0][0],adjacent[1][0]],'desired_angle_degrees':angle(values[a],values[b]),'before_angle_degrees':angle(before[a],before[b]),'selected':[a in targets,b in targets]})
            if reasons:
                edge.use_edge_sharp=True;requested_splits.append({'edge':edge.index,'vertices':list(edge.vertices),'reasons':reasons})
        staged.normals_split_custom_set(values)
        code_refinement=refine_selected_codes(staged,targets)
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
        proof.update(status='applied-explicit-native-corner-field',code_refinement=code_refinement,target_count=len(targets),maximum_target_error_degrees=max_target,
                     maximum_unrelated_delta_degrees=max_other,unrelated_count=len(before)-len(targets),
                     unrelated_vectors_exact=sum(before[i]==after[i] for i in range(len(before)) if i not in targets),
                     declared_sharp_additions=sharp,requested_normal_group_splits=requested_splits,geometry_uv_material_provenance_exact=True,
                     raw_normal_maximum_unit_error=max(abs(math.hypot(*n)-1) for n in after),
                     source_saved=False,human_approval_reference=None)
        obj.data=staged;staged=None
        return proof
    finally:
        if staged is not None and staged.users==0:bpy.data.meshes.remove(staged)
