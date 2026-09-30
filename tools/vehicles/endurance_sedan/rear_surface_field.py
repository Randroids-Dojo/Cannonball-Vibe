"""Finite original rear side field plus original fictional continuous cap finish.

Capture the actual native original skin before Boolean cuts. Apply after final
LOD0 mesh evaluation. The rear cap is an authored field on the actual retained
skin, not a claim that retessellated faces reproduce old triangle interpolation.
No report payload, source save, geometry edit, or export is used by this module.
"""
import math
from mathutils import Vector, geometry
from . import staged_normals as native

PROFILE={'schema':'original-rear-surface-field.v1','semantics':['LOD0_StructuralBody','LOD0_RearBumper'],
 'rear_domain_y_max_m':-.70,'cap_domain_y_max_m':-2.40,'cap_normal_y_max':-.80,
 'cap_half_width_m':.83,'cap_wrap_coefficient_m':.105,'cap_field_vertical_component':0.,
 'side_normal_x_min':.50,'side_absolute_x_min_m':.78,'side_normal_z_min':.50,'side_z_min_m':.80,
 'retained_face_strength':16384,'whole_original_face_guard_m':1e-6,'original_corner_guard_m':2e-6,
 'original_plane_alignment_min':.99985,'fan_original_continuity_degrees':.025,
 'fan_dihedral_degrees_max':35.,'generated_axis_plane_exclusion':.999,
 'native_normal_error_degrees_max':.025,'native_unit_error_max':1e-6,
 'cap_domain':'Complete XZ footprint within original cap and each actual corner within original2um lookup. Original FACE strength required. No3D whole-field preservation claim.'}

def validate(profile):
    if native.digest(profile)!=native.digest(PROFILE):raise ValueError('Unreviewed rear surface domain')
    return profile

def capture(obj,profile):
    validate(profile)
    if obj.name!='LOD0_StructuralBody' or obj.modifiers:raise ValueError('Expected native body immediately before first Boolean')
    mesh=obj.data;mesh.calc_loop_triangles()
    field={'vertices':[list(v.co) for v in mesh.vertices],'triangles':[],'normals':[],'cap':[]}
    for tri in mesh.loop_triangles:
        ps=[mesh.vertices[i].co for i in tri.vertices]
        if min(p.y for p in ps)>=profile['rear_domain_y_max_m']:continue
        normals=[list(mesh.corner_normals[i].vector) for i in tri.loops]
        if not all(native.valid_normal(n) for n in normals):raise ValueError('Invalid original native field')
        field['triangles'].append(list(tri.vertices));field['normals'].append(normals)
        field['cap'].append(max(p.y for p in ps)<profile['cap_domain_y_max_m'] and mesh.polygons[tri.polygon_index].normal.y<profile['cap_normal_y_max'])
    if sum(field['cap'])!=46 or len(field['triangles'])<1000:raise ValueError('Original rear skin construction differs')
    return {'schema':'captured-original-rear-skin.v1','profile_sha256':native.digest(profile),
      'coordinate_frame':[list(r) for r in obj.matrix_world],'coordinate_space':'native-source-local-meters',
      'physical_sha256':native.fingerprint(mesh),'field':field,'field_sha256':native.digest(field)}

def validate_reference(packet,profile):
    if type(packet) is not dict or set(packet)!={'schema','profile_sha256','coordinate_frame','coordinate_space','physical_sha256','field','field_sha256'}:
        raise ValueError('Incomplete original reference packet')
    field=packet['field']
    if type(field) is not dict or set(field)!={'vertices','triangles','normals','cap'}:
        raise ValueError('Incomplete original field arrays')
    for key in ('physical_sha256','field_sha256','profile_sha256'):
        value=packet[key]
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid reference hash: '+key)
    def vector(value,size):
        return type(value) in (list,tuple) and len(value)==size and all(type(v) in (int,float) and math.isfinite(v) for v in value)
    if type(packet['coordinate_frame']) is not list or len(packet['coordinate_frame'])!=4 or not all(vector(r,4) for r in packet['coordinate_frame']):
        raise ValueError('Invalid original reference coordinate frame')
    if type(field['vertices']) is not list or not field['vertices'] or not all(vector(p,3) for p in field['vertices']):
        raise ValueError('Invalid original reference vertices')
    if type(field['triangles']) is not list or len(field['triangles'])<1000:
        raise ValueError('Incomplete original reference triangle inventory')
    seen=set()
    for tri in field['triangles']:
        if type(tri) is not list or len(tri)!=3 or len(set(tri))!=3 or not all(type(i) is int and 0<=i<len(field['vertices']) for i in tri):
            raise ValueError('Invalid original reference triangle indices')
        key=tuple(sorted(tri))
        if key in seen:raise ValueError('Duplicate original reference triangle')
        seen.add(key)
        a,b,c=[Vector(field['vertices'][i]) for i in tri]
        if (b-a).cross(c-a).length_squared==0:raise ValueError('Degenerate original reference triangle')
    if type(field['normals']) is not list or len(field['normals'])!=len(field['triangles']) or not all(type(row) is list and len(row)==3 and all(vector(n,3) and native.valid_normal(n) for n in row) for row in field['normals']):
        raise ValueError('Invalid original reference corner normals')
    if type(field['cap']) is not list or len(field['cap'])!=len(field['triangles']) or not all(type(v) is bool for v in field['cap']) or sum(field['cap'])!=46:
        raise ValueError('Invalid original cap inventory')
    if packet['field_sha256']!=native.digest(field) or packet['profile_sha256']!=native.digest(profile):
        raise ValueError('Original reference content or scope hash differs')


def prepare(obj,packet,profile,ownership):
    validate(profile)
    validate_reference(packet,profile)
    if obj.name not in profile['semantics'] or obj.type!='MESH' or obj.modifiers:raise ValueError('Expected final native rear skin semantic')
    if (packet['schema']!='captured-original-rear-skin.v1' or packet['profile_sha256']!=native.digest(profile)
       or packet['field_sha256']!=native.digest(packet['field']) or packet['coordinate_frame']!=[list(r) for r in obj.matrix_world]
       or packet['coordinate_space']!='native-source-local-meters'):raise ValueError('Original reference identity differs')
    ref=packet['field'];mesh=obj.data;mesh.calc_loop_triangles()
    if len(ref['triangles'])!=len(ref['normals']) or len(ref['triangles'])!=len(ref['cap']):raise ValueError('Incomplete original field')
    if not all(native.valid_normal(n) for row in ref['normals'] for n in row):raise ValueError('Invalid original normals')
    patch=ownership._patch((None,[Vector(p) for p in ref['vertices']],ref['triangles'],[[Vector(n) for n in row] for row in ref['normals']]))
    facetris={}
    for tri in mesh.loop_triangles:facetris.setdefault(tri.polygon_index,[]).append([tuple(mesh.vertices[v].co) for v in tri.vertices])
    before=[tuple(n.vector) for n in mesh.corner_normals]
    if not all(native.valid_normal(n) for n in before):raise ValueError('Invalid final input normals')
    targets={};seeds={};domains={};original_witnesses=[];unowned=[]
    for face in mesh.polygons:
        ps=[tuple(mesh.vertices[i].co) for i in face.vertices]
        if max(p[1] for p in ps)>profile['rear_domain_y_max_m']:continue
        if face.normal.y<=profile['cap_normal_y_max'] and max(p[1] for p in ps)<=profile['cap_domain_y_max_m']:continue
        if not all(ownership._covers(tri,patch) for tri in facetris[face.index]):unowned.append(face.index);continue
        corners=[]
        for li in face.loop_indices:
            point=mesh.vertices[mesh.loops[li].vertex_index].co;choices=[]
            for ri,(vs,normal,_,ns) in enumerate(patch):
                if face.normal.dot(Vector(normal))<profile['original_plane_alignment_min']:continue
                vectors=[Vector(p) for p in vs];hit=geometry.closest_point_on_tri(point,*vectors);distance=(hit-point).length
                if distance>profile['original_corner_guard_m']:continue
                value=geometry.barycentric_transform(hit,*vectors,*ns)
                if value.length<.5:raise ValueError('Invalid interpolated original field')
                choices.append((distance,tuple(value.normalized()),ri))
            if not choices:raise ValueError('Owned corner lacks original surface')
            distance,normal,ri=min(choices,key=lambda r:(r[0],r[2]))
            corners.append({'loop':li,'vertex':mesh.loops[li].vertex_index,'target':normal,'reference_index':ri,
                            'cap':ref['cap'][ri],'distance_m':distance,'point':list(point)})
        iscap=all(c['cap'] for c in corners)
        side=(abs(face.normal.x)>profile['side_normal_x_min'] and min(abs(p[0]) for p in ps)>profile['side_absolute_x_min_m']) or (face.normal.z>profile['side_normal_z_min'] and min(p[2] for p in ps)>profile['side_z_min_m'])
        # Every authored cap face enters only through the complete provenance,
        # footprint and original-corner checks below. The whole3D side path
        # must never bypass these checks for a retained cap triangle.
        if iscap or not side:continue
        for c in corners:
            li,vi=c['loop'],c['vertex'];target=cap_normal(c['point'][0],profile) if iscap else c['target']
            targets[li]=target;seeds.setdefault(vi,[]).append({'loop':li,'target':target,'face':face.index})
        domains[face.index]='new-analytic-rear-cap' if iscap else 'original-precut-rear-side'
        original_witnesses.append({'face':face.index,'corners':corners,'new_cap_authorship':iscap})
    captri=[tri for tri,cap in zip(ref['triangles'],ref['cap']) if cap]
    projected=[Vector((v[0],0.,v[2])) for v in ref['vertices']]
    cappatch=ownership._patch((None,projected,captri,[[Vector((0,-1,0))]*3 for tri in captri]))
    capplanes=[[Vector(ref['vertices'][i]) for i in tri] for tri in captri]
    strength=mesh.attributes.get('__mod_weightednormals_faceweight')
    if strength is None or strength.domain!='FACE' or strength.data_type!='INT':raise ValueError('Original face provenance missing')
    cap_domain=[];rejected_cap=[];cap_candidate_faces=set()
    for face in mesh.polygons:
        ps=[mesh.vertices[v].co for v in face.vertices]
        if face.normal.y>profile['cap_normal_y_max'] or max(v.y for v in ps)>profile['cap_domain_y_max_m']:continue
        cap_candidate_faces.add(face.index)
        if strength.data[face.index].value!=profile['retained_face_strength']:
            rejected_cap.append({'face':face.index,'reason':'missing-retained-cap-provenance','strength':strength.data[face.index].value})
            continue
        projected_triangles=[[(v[0],0.,v[2]) for v in tri] for tri in facetris[face.index]]
        degenerate=[i for i,tri in enumerate(projected_triangles)
                    if (Vector(tri[1])-Vector(tri[0])).cross(Vector(tri[2])-Vector(tri[0])).length_squared==0]
        if degenerate:
            rejected_cap.append({'face':face.index,'reason':'zero-area-XZ-projection',
                                 'projected_triangle_indices':degenerate,
                                 'actual_native_triangles':facetris[face.index],
                                 'projected_triangles':projected_triangles})
            continue
        covered=all(ownership._covers(tri,cappatch) for tri in projected_triangles)
        distances=[min((geometry.closest_point_on_tri(point,*tri)-point).length for tri in capplanes) for point in ps]
        if not covered or max(distances)>profile['original_corner_guard_m']:
            rejected_cap.append({'face':face.index,'footprint':covered,'corner_distances_m':distances});continue
        for li in face.loop_indices:
            vi=mesh.loops[li].vertex_index;target=cap_normal(mesh.vertices[vi].co.x,profile);targets[li]=target
            seeds[vi]=[s for s in seeds.get(vi,[]) if s['loop']!=li]
            seeds[vi].append({'loop':li,'target':target,'face':face.index})
        domains[face.index]='new-analytic-rear-cap-retessellated-skin'
        cap_domain.append({'face':face.index,'whole_xz_footprint':True,'corner_distances_m':distances,'strength':16384})
    propagated=[];rejected_fans=[]
    for face in mesh.polygons:
        # Rejected cap faces cannot re-enter through neighboring corner fans.
        if face.index in domains or face.index in cap_candidate_faces:continue
        ps=[tuple(mesh.vertices[v].co) for v in face.vertices]
        if max(p[1] for p in ps)>profile['rear_domain_y_max_m'] or max(abs(v) for v in face.normal)>profile['generated_axis_plane_exclusion']:continue
        for li in face.loop_indices:
            vi=mesh.loops[li].vertex_index
            choices=[s for s in seeds.get(vi,[]) if native.angle(before[li],before[s['loop']])<=profile['fan_original_continuity_degrees'] and face.normal.dot(mesh.polygons[s['face']].normal)>=math.cos(math.radians(profile['fan_dihedral_degrees_max']))]
            if not choices:continue
            target=choices[0]['target']
            if any(native.angle(target,s['target'])>.025 for s in choices):rejected_fans.append(li);continue
            targets[li]=target;propagated.append({'loop':li,'face':face.index,'seeds':[s['loop'] for s in choices]})
    if len(targets)<500 or len(cap_domain)<10:raise ValueError('Incomplete actual rear field inventory')
    return {'before':before,'targets':targets,'ambiguous_corners':[],'object':obj.name,'domains':domains,
      'original_witnesses':original_witnesses,'unowned_original_faces':unowned,'new_cap_domain':cap_domain,
      'rejected_cap_faces':rejected_cap,'cap_candidate_faces':sorted(cap_candidate_faces),'propagated':propagated,'rejected_ambiguous_fans':rejected_fans,
      'reference_sha256':native.digest(packet),'profile_sha256':native.digest(profile),
      'scope':'Original whole-owned side field and explicitly authored continuous rear cap; no geometric changes or cap old-interpolation preservation claim.'}

def cap_normal(x,profile):
    return tuple(Vector((3*profile['cap_wrap_coefficient_m']*x*abs(x)/profile['cap_half_width_m']**3,-1.,profile['cap_field_vertical_component'])).normalized())

def apply(obj,packet,profile,ownership):
    plan=prepare(obj,packet,profile,ownership)
    result=native.apply_targets(obj,plan)
    result['corner_targets']={str(i):v for i,v in plan['targets'].items()}
    return result
