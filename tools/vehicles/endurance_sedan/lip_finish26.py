"""Explicit new field at the finite rear-lip midline; not old face ownership.

The two mirrored outer triangles may be retessellated across original facets.
The old complete-whole-face test remains unchanged and is recorded. A separate
complete clipped-piece certificate establishes the intended upper surface.
Only its common outer-midline corner is authored. Cap, cavity and transition
face corners remain unselected, with any new sharp splits reported by the codec.
"""
import math
from mathutils import Vector, geometry

PROFILE={
 'schema':'authored-rear-lip-midline-field.v1','semantic':'LOD0_StructuralBody',
 'midline_absolute_x_max_m':1e-7,'pole_y_bounds_m':[-2.541,-2.530],
 'pole_z_bounds_m':[.863,.870],'outer_y_bounds_m':[-2.541,-2.430],
 'outer_z_bounds_m':[.860,.920],'outer_absolute_x_max_m':.300,
 'outer_normal_z_min':.90,'outer_normal_y_bounds':[-.43,-.36],
 'marker':0,'strength':16384,'outer_face_count':2,'pole_incident_face_count':5,
 'original_piece_plane_guard_m':1e-6,'original_corner_guard_m':2e-6,
 'original_plane_alignment_min':.99985,'reference_normal_agreement_degrees':.025,
 'native_normal_error_degrees_max':.025,'raw_normal_unit_error_max':1e-6,
 'authorship':'Two upper-lip corners only; no old whole-face preservation or cap authorship claim.',
}

def _inside(x,bounds):return bounds[0]<=x<=bounds[1]

def _piece_certificate(triangle,patch,own):
    n=own._unit(own._cross(own._sub(triangle[1],triangle[0]),own._sub(triangle[2],triangle[0])))
    remaining=[triangle];pieces=[]
    for ri,(points,normal,planes,_) in enumerate(patch):
        if own._dot(n,normal)<PROFILE['original_plane_alignment_min']:continue
        following=[]
        for polygon in remaining:
            intersection=polygon
            for pn,po in planes:
                if intersection:intersection=own._clip(intersection,pn,po,True)
            error=max((abs(own._dot(own._sub(p,points[0]),normal)) for p in intersection),default=0.)
            if intersection and error<=PROFILE['original_piece_plane_guard_m']:
                following.extend(own._subtract(polygon,planes))
                pieces.append({'reference':ri,'points':intersection,'maximum_plane_error_m':error})
            else:following.append(polygon)
        remaining=following
        if not remaining:break
    if remaining:raise ValueError('Upper-lip intended-surface footprint is incomplete')
    return pieces

def prepare(obj,reference,ownership,native):
    if obj.name!=PROFILE['semantic'] or obj.type!='MESH' or obj.modifiers:
        raise ValueError('Expected final native structural body')
    mesh=obj.data;mesh.calc_loop_triangles()
    if reference['coordinate_frame']!=[list(r) for r in obj.matrix_world]:
        raise ValueError('Reference coordinate frame differs')
    field=reference['field']
    if native.digest(field)!=reference['field_sha256']:raise ValueError('Reference content hash differs')
    if len(field['triangles'])!=len(field['normals']) or len(field['cap'])!=len(field['triangles']):
        raise ValueError('Missing reference corner inventory')
    if not all(native.valid_normal(n) for ns in field['normals'] for n in ns):
        raise ValueError('Invalid raw reference normal')
    before=[tuple(n.vector) for n in mesh.corner_normals]
    if not all(native.valid_normal(n) for n in before):raise ValueError('Invalid raw native normal')
    attrs={}
    for key in ('cb_fascia_cap','__mod_weightednormals_faceweight'):
        attr=mesh.attributes.get(key)
        if attr is None or attr.domain!='FACE' or attr.data_type!='INT':raise ValueError('Missing native face provenance')
        attrs[key]=attr
    incident={}
    for face in mesh.polygons:
        if len(face.vertices)!=3:raise ValueError('Final triangle partition required')
        for vi in face.vertices:incident.setdefault(vi,[]).append(face)
    def outer(face):
        if attrs['cb_fascia_cap'].data[face.index].value!=0 or attrs['__mod_weightednormals_faceweight'].data[face.index].value!=16384:return False
        if face.normal.z<PROFILE['outer_normal_z_min'] or not _inside(face.normal.y,PROFILE['outer_normal_y_bounds']):return False
        return all(abs(mesh.vertices[i].co.x)<=PROFILE['outer_absolute_x_max_m']
                   and _inside(mesh.vertices[i].co.y,PROFILE['outer_y_bounds_m'])
                   and _inside(mesh.vertices[i].co.z,PROFILE['outer_z_bounds_m']) for i in face.vertices)
    poles=[]
    for v in mesh.vertices:
        if abs(v.co.x)>PROFILE['midline_absolute_x_max_m'] or not _inside(v.co.y,PROFILE['pole_y_bounds_m']) or not _inside(v.co.z,PROFILE['pole_z_bounds_m']):continue
        faces=[f for f in incident.get(v.index,[]) if outer(f)]
        if len(faces)==2:poles.append((v,faces))
    if len(poles)!=1:raise ValueError('Missing or ambiguous mirrored outer-lip topology')
    pole,faces=poles[0]
    if len(incident[pole.index])!=5:raise ValueError('Unexpected outer-lip incident topology')
    common=set(faces[0].vertices)&set(faces[1].vertices)
    if len(common)!=2 or pole.index not in common:raise ValueError('Outer faces must share one edge')
    other=mesh.vertices[next(iter(common-{pole.index}))]
    if abs(other.co.x)>1e-7 or other.co.y<=pole.co.y+.05:raise ValueError('Outer midline edge orientation differs')
    branches=[mesh.vertices[next(iter(set(f.vertices)-common))].co.copy() for f in faces]
    if branches[0].x*branches[1].x>=0 or (branches[0]-Vector((-branches[1].x,branches[1].y,branches[1].z))).length>2e-6:
        raise ValueError('Mirrored upper-lip branch geometry differs')
    edge_faces={}
    for f in mesh.polygons:
        for li in f.loop_indices:edge_faces.setdefault(mesh.loops[li].edge_index,[]).append(f.index)
    for f in incident[pole.index]:
        if any(len(edge_faces[mesh.loops[li].edge_index])!=2 for li in f.loop_indices):raise ValueError('Open/nonmanifold lip neighborhood')
    patch=ownership._patch((None,[Vector(v) for v in field['vertices']],field['triangles'],
                            [[Vector(n) for n in ns] for ns in field['normals']]))
    # Only original upper faces may supply a field. The cap is never a source.
    upper=[];indices=[]
    for ri,item in enumerate(patch):
        ps,n,_,_=item
        if not field['cap'][ri] and n[2]>.85 and max(p[1] for p in ps)<-2.4 and min(p[2] for p in ps)>.84:
            upper.append(item);indices.append(ri)
    if len(upper)<4:raise ValueError('Missing original upper-lip carrier')
    targets={};proof=[]
    for face in faces:
        ps=[tuple(mesh.vertices[i].co) for i in face.vertices]
        pieces=_piece_certificate(ps,upper,ownership)
        li=next(i for i in face.loop_indices if mesh.loops[i].vertex_index==pole.index)
        choices=[]
        for ri,(vs,n,_,ns) in enumerate(upper):
            if face.normal.dot(Vector(n))<.99985:continue
            hit=geometry.closest_point_on_tri(pole.co,*[Vector(v) for v in vs]);distance=(hit-pole.co).length
            if distance>2e-6:continue
            value=geometry.barycentric_transform(hit,*[Vector(v) for v in vs],*ns).normalized()
            if face.normal.dot(value)<.5:raise ValueError('Reference target faces away from upper surface')
            choices.append({'reference':indices[ri],'distance_m':distance,'normal':tuple(value)})
        if not choices:raise ValueError('Authored pole lacks original upper-field target')
        target=min(choices,key=lambda c:(c['distance_m'],c['reference']))['normal']
        if any(native.angle(target,c['normal'])>.025 for c in choices):raise ValueError('Ambiguous original upper-field target')
        targets[li]=target
        proof.append({'face':face.index,'loop':li,'vertex':pole.index,'point':list(pole.co),
                      'whole_original_face_owned':ownership._covers(ps,patch),
                      'complete_authored_piece_certificate':pieces,'reference_choices':choices,
                      'target':target,'input_angle_degrees':native.angle(before[li],target)})
    if len(targets)!=2 or native.angle(*targets.values())>.025:raise ValueError('Two-sided target continuity differs')
    shared=tuple(sum(n[i] for n in targets.values())/2 for i in range(3))
    length=math.hypot(*shared);shared=tuple(v/length for v in shared)
    for li in targets:targets[li]=shared
    for row in proof:
        row['reference_target']=row['target'];row['target']=shared
        row['input_angle_degrees']=native.angle(before[row['loop']],shared)
    excluded=[{'face':f.index,'normal':tuple(f.normal),'loop_at_pole':next(li for li in f.loop_indices if mesh.loops[li].vertex_index==pole.index),
               'vertices':list(f.vertices),'marker':attrs['cb_fascia_cap'].data[f.index].value,
               'reason':'Unselected generated transition; genuine surface boundary retained'} for f in incident[pole.index] if f not in faces]
    return {'object':obj.name,'before':before,'targets':targets,'ambiguous_corners':[],
            'profile':PROFILE,'profile_sha256':native.digest(PROFILE),'reference_sha256':native.digest(reference),
            'authored_corners':proof,'excluded_incident_faces':excluded,
            'scope':'Explicit new two-corner upper-lip field, with complete intended-surface certificate; original whole-face/cap ownership tests unchanged.'}

def apply(obj,reference,ownership,native):
    plan=prepare(obj,reference,ownership,native)
    result=native.apply_targets(obj,plan)
    result['corner_targets']={str(i):n for i,n in plan['targets'].items()}
    return result
