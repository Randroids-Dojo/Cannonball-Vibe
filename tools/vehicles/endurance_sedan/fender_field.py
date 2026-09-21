"""Original upper-fender cut-edge field, with complete face ownership."""
import math
import bpy
from mathutils import Vector, geometry

def angle(a,b):
    return math.degrees(math.acos(max(-1.,min(1.,sum(x*y for x,y in zip(a,b))/(math.hypot(*a)*math.hypot(*b))))))

def capture(body):
    """Read the original body immediately before its first Boolean cut."""
    mesh=body.data;mesh.calc_loop_triangles();points=[];triangles=[];normals=[]
    for tri in mesh.loop_triangles:
        face=mesh.polygons[tri.polygon_index]
        p=[tuple(mesh.vertices[v].co) for v in tri.vertices]
        if face.normal.z<.5 or max(v[1] for v in p)<1.81 or min(v[1] for v in p)>1.90:continue
        if max(abs(v[0]) for v in p)<.75 or max(v[2] for v in p)<.84:continue
        n=[tuple(mesh.corner_normals[i].vector) for i in tri.loops]
        if not all(all(math.isfinite(x) for x in v) and abs(math.hypot(*v)-1)<=1e-6 for v in n):
            raise ValueError('Invalid native original field')
        offset=len(points);points.extend(p);triangles.append([offset,offset+1,offset+2]);normals.append(n)
    if not triangles:raise ValueError('Missing original upper-fender reference')
    return {'vertices':points,'triangles':triangles,'normals':normals,
            'scope':'Actual native original body field before any Boolean, limited to triangles overlapping the upper front-fender seam neighborhood.'}

def physical(mesh):
    return {'vertices':[tuple(v.co) for v in mesh.vertices],
            'polygons':[(tuple(p.vertices),p.material_index,p.use_smooth) for p in mesh.polygons],
            'edges':[tuple(e.vertices) for e in mesh.edges],
            'uv':{layer.name:[tuple(v.uv) for v in layer.data] for layer in mesh.uv_layers},
            'materials':[m.as_pointer() if m else None for m in mesh.materials],
            'provenance':{n:[v.value for v in mesh.attributes[n].data] for n in ('cb_fascia_cap','__mod_weightednormals_faceweight')}}

def prepare(obj,reference,ownership):
    if obj.name not in ('LOD0_FrontFender_L','LOD0_FrontFender_R'):raise ValueError('Wrong original fender semantic')
    if obj.modifiers:raise ValueError('Expected final native fender without pending modifiers')
    mesh=obj.data
    tag=mesh.attributes.get('cb_fascia_cap');strength=mesh.attributes.get('__mod_weightednormals_faceweight')
    if any(a is None or a.domain!='FACE' or a.data_type!='INT' for a in (tag,strength)):
        raise ValueError('Missing retained surface provenance')
    front=max(v.co.y for v in mesh.vertices)
    if abs(front-1.8665)>2e-6:raise ValueError('Original front panel boundary changed')
    points=reference['vertices'];triangles=reference['triangles'];normal_rows=reference['normals']
    if not points or not triangles or len(triangles)!=len(normal_rows):raise ValueError('Incomplete original field reference')
    if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in points):raise ValueError('Nonfinite original field geometry')
    if any(len(t)!=3 or any(type(v) is not int or not 0<=v<len(points) for v in t) for t in triangles):
        raise ValueError('Invalid original field triangle index')
    if any(len(row)!=3 or any(len(n)!=3 or not all(math.isfinite(v) for v in n) or abs(math.hypot(*n)-1)>1e-6 for n in row) for row in normal_rows):
        raise ValueError('Invalid original reference corner normal')
    patch=ownership._patch((None,[Vector(p) for p in reference['vertices']],reference['triangles'],
                            [[Vector(n) for n in values] for values in reference['normals']]))
    before=[tuple(n.vector) for n in mesh.corner_normals]
    if not all(all(math.isfinite(x) for x in n) and abs(math.hypot(*n)-1)<=1e-6 for n in before):
        raise ValueError('Invalid saved native corner normals')
    mesh.calc_loop_triangles();face_triangles={}
    for t in mesh.loop_triangles:
        face_triangles.setdefault(t.polygon_index,[]).append([tuple(mesh.vertices[v].co) for v in t.vertices])
    targets={};owned=[];unowned=[];candidates=[];vertices={}
    for face in mesh.polygons:
        points=[tuple(mesh.vertices[v].co) for v in face.vertices]
        if tag.data[face.index].value!=0 or strength.data[face.index].value!=16384:continue
        if face.normal.z<.5 or min(p[1] for p in points)<1.81 or max(p[1] for p in points)<front-.002:continue
        if min(p[2] for p in points)<.84 or min(abs(p[0]) for p in points)<.75:continue
        candidates.append(face.index)
        if not all(ownership._covers(t,patch) for t in face_triangles[face.index]):
            unowned.append(face.index);continue
        owned.append(face.index)
        for li in face.loop_indices:
            vi=mesh.loops[li].vertex_index;point=mesh.vertices[vi].co
            if point.y<front-.002:continue
            choices=[]
            for ps,normal,_,ns in patch:
                if face.normal.dot(Vector(normal))<.8:continue
                ps=[Vector(p) for p in ps];hit=geometry.closest_point_on_tri(point,*ps);distance=(hit-point).length
                if distance>2e-6:continue
                value=geometry.barycentric_transform(hit,*ps,*ns)
                if value.length<.5:raise ValueError('Invalid interpolated original field')
                choices.append((distance,tuple(value.normalized())))
            if not choices:raise ValueError('Owned corner lacks its original field')
            distance,value=min(choices,key=lambda item:item[0])
            vertices.setdefault(vi,[]).append((distance,value,li))
    if len(owned)<10 or len(vertices)<10:raise ValueError('Incomplete upper cut-edge ownership inventory')
    retained=set()
    for vi,choices in vertices.items():
        distance,value,_=min(choices,key=lambda item:item[0])
        if any(angle(value,target)>.025 for _,target,_ in choices):raise ValueError('Inconsistent owning reference fields')
        original_loops=[li for _,_,li in choices];retained.update(original_loops)
        for li,loop in enumerate(mesh.loops):
            if loop.vertex_index==vi and any(angle(before[li],before[original])<=.025 for original in original_loops):
                targets[li]=value
    return {'object':obj.name,'front_cut_plane_y_m':front,'candidate_faces':candidates,'owned_faces':owned,
            'unowned_candidate_faces_not_reauthored':unowned,
            'selected_vertices':sorted(vertices),'retained_original_corner_count':len(retained),
            'targets':targets,'before':before,
            'maximum_reference_distance_m':max(distance for values in vertices.values() for distance,_,_ in values),
            'scope':'Wholly owned original upward fender faces at the front cut; only new cut-edge vertices and their previously continuous same-vertex corner fans. Existing discrete corner groups remain separate.'}

def apply(objects,reference,ownership):
    if sorted(obj.name for obj in objects)!=['LOD0_FrontFender_L','LOD0_FrontFender_R']:
        raise ValueError('Both original front fenders are required')
    prepared=[prepare(obj,reference,ownership) for obj in objects]
    stages=[];proofs=[]
    try:
        for obj,plan in zip(objects,prepared):
            mesh=obj.data.copy();stages.append(mesh);fields=physical(obj.data)
            old_sharp=[e.use_edge_sharp for e in obj.data.edges]
            before=plan['before'];targets=plan['targets'];old_codes=[tuple(v.value) for v in mesh.attributes['custom_normal'].data]
            values=list(before)
            for li,target in targets.items():values[li]=target
            mesh.normals_split_custom_set(values);fresh_codes=[tuple(v.value) for v in mesh.attributes['custom_normal'].data]
            fresh=[tuple(v.vector) for v in mesh.corner_normals]
            for li,code in enumerate(old_codes):
                if li not in targets:mesh.attributes['custom_normal'].data[li].value=code
            mesh.update();restored=[tuple(v.vector) for v in mesh.corner_normals]
            for li in range(len(before)):
                if li not in targets and angle(before[li],fresh[li])<angle(before[li],restored[li]):
                    mesh.attributes['custom_normal'].data[li].value=fresh_codes[li]
            mesh.update();after=[tuple(n.vector) for n in mesh.corner_normals]
            if physical(mesh)!=fields:raise ValueError('Geometry/UV/material/provenance changed')
            maximum=max(angle(a,b) for li,(a,b) in enumerate(zip(before,after)) if li not in targets)
            error=max(angle(after[li],target) for li,target in targets.items())
            if maximum>.025 or error>.025:raise ValueError('Native normal encoding exceeded0.025 degree bound')
            changes=[]
            for edge,was in zip(mesh.edges,old_sharp):
                if edge.use_edge_sharp==was:continue
                if was or not edge.use_edge_sharp or not set(edge.vertices)&set(plan['selected_vertices']):
                    raise ValueError('Sharp policy changed outside selected corner fans')
                changes.append({'edge':edge.index,'vertices':list(edge.vertices),'before':was,'after':edge.use_edge_sharp})
            proofs.append({k:v for k,v in plan.items() if k not in ('before','targets')} | {
                'target_count':len(targets),'targets':[{'loop':li,'vertex':mesh.loops[li].vertex_index,'target':v,'before':before[li],'after':after[li]} for li,v in sorted(targets.items())],
                'maximum_unrelated_corner_delta_degrees':maximum,'maximum_target_error_degrees':error,
                'unrelated_vectors_exact':sum(a==b for li,(a,b) in enumerate(zip(before,after)) if li not in targets),
                'unrelated_corner_count':len(before)-len(targets),'declared_sharp_edge_changes':changes,'geometry_uv_material_provenance_exact':True})
        for obj,mesh in zip(objects,stages):obj.data=mesh
        stages=[]
        return {'status':'applied-original-two-sided-fender-cut-edge-field','objects':proofs,
                'whole_face_projection_guard_m':1e-6,'corner_lookup_guard_m':2e-6,
                'unrelated_normal_angle_limit_degrees':.025,'source_saved':False,'human_approval_reference':None}
    finally:
        for mesh in stages:
            if mesh.users==0:bpy.data.meshes.remove(mesh)
