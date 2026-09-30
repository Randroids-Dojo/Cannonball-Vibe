"""Original formed fascia surface with bounded native corner-field authorship."""
import json
import math
from mathutils import Vector
from . import fascia_side_field


def validate(profile):
    expected_cap={'front_y_m':2.4,'half_width_m':.825,'vertical_radius_m':3.457,'vertical_center_z_m':.550,'plan_wrap_coefficient_m':.150,'radial_fractions':[.25,.5,.75,1.0],'longitudinal_fade_y_m':[2.230,2.4]}
    for key,value in expected_cap.items():
        if profile['front_cap'][key]!=value:raise ValueError('Changed original fascia cap: '+key)
    if (profile['perimeter']['offset_m']!=.018 or profile['perimeter']['segments']!=3
            or profile['perimeter']['weight_ramp_z_m']!=[.670,.770]
            or profile['perimeter']['native_face_strength_mode']!='FSTR_ALL'
            or profile['shoulder']['parameter_span']!=[5.65,6.35]
            or profile['shoulder']['coefficient_m']!=-.034
            or profile['shoulder']['longitudinal_fade_y_m']!=[1.90,2.20]
            or profile['cap_field']['normal_angle_guard_degrees']!=.025
            or profile['outer_side_endpoints']['optical_floor_z_m']!=.673
            or profile['fender_field']['whole_face_projection_guard_m']!=1e-6
            or profile['fender_field']['corner_lookup_guard_m']!=2e-6
            or profile['fender_field']['normal_angle_guard_degrees']!=.025):
        raise ValueError('Changed original fascia construction or native field boundary')


def apply(obj, front_width):
    mesh=obj.data
    marker=mesh.attributes.get('cb_fascia_cap');strength=mesh.attributes.get('__mod_weightednormals_faceweight')
    if marker is None or strength is None:raise ValueError('Authored cap provenance was lost')
    cap_faces={p.index for p in mesh.polygons if marker.data[p.index].value==1 and strength.data[p.index].value==16384}
    if len(cap_faces)<200:raise ValueError('Missing retained cap faces')
    cap_vertices={v for i in cap_faces for v in mesh.polygons[i].vertices}
    before=[tuple(n.vector) for n in mesh.corner_normals]
    old_codes=[tuple(n.value) for n in mesh.attributes['custom_normal'].data]
    updated=list(before);changed=set();bevel_loops=0
    for face in mesh.polygons:
        retained=face.index in cap_faces
        edge=marker.data[face.index].value==1 and strength.data[face.index].value in (-16384,0)
        for index in face.loop_indices:
            vertex=mesh.loops[index].vertex_index
            if not retained and not (edge and vertex in cap_vertices):continue
            x,y,z=mesh.vertices[vertex].co
            dx=.45*x*abs(x)/front_width**3
            dz=(z-.550)/math.sqrt(3.457**2-(z-.550)**2)
            updated[index]=Vector((dx,1.,dz)).normalized();changed.add(index)
            if not retained:bevel_loops+=1
    mesh.normals_split_custom_set(updated)
    encoded_after_set=[tuple(n.value) for n in mesh.attributes['custom_normal'].data]
    vectors_after_set=[tuple(n.vector) for n in mesh.corner_normals]
    for i,code in enumerate(old_codes):
        if i not in changed:mesh.attributes['custom_normal'].data[i].value=code
    mesh.update()
    vectors_after_restore=[tuple(n.vector) for n in mesh.corner_normals]
    def angle(a,b):
        cosine=sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
        return math.degrees(math.acos(max(-1.,min(1.,cosine))))
    cases=[]
    for i,target in enumerate(before):
        if i in changed:continue
        set_angle=angle(target,vectors_after_set[i]);restore_angle=angle(target,vectors_after_restore[i])
        if target!=vectors_after_restore[i] or target!=vectors_after_set[i]:
            cases.append({'loop':i,'set_angle_degrees':set_angle,'restored_code_angle_degrees':restore_angle,
                'target':target,'after_set':vectors_after_set[i],'after_old_code':vectors_after_restore[i]})
        if set_angle<restore_angle:
            mesh.attributes['custom_normal'].data[i].value=encoded_after_set[i]
    mesh.update()
    after=[tuple(n.vector) for n in mesh.corner_normals]
    diagnostic={'case_count':len(cases),'cases':cases,'changed_loops':sorted(changed),
        'maximum_unmodified_target_roundtrip_angle_degrees':max((angle(a,b) for i,(a,b) in enumerate(zip(before,after)) if i not in changed),default=0),
        'maximum_after_set_angle_degrees':max((c['set_angle_degrees'] for c in cases),default=0),
        'maximum_after_old_code_angle_degrees':max((c['restored_code_angle_degrees'] for c in cases),default=0)}
    if diagnostic['maximum_unmodified_target_roundtrip_angle_degrees']>.025:raise ValueError('Unbounded unrelated native corner-normal reencoding')
    groups={}
    for face_index in cap_faces:
        for i in mesh.polygons[face_index].loop_indices:
            groups.setdefault(mesh.loops[i].vertex_index,[]).append(after[i])
    maximum=0.
    for values in groups.values():
        for a in values:
            for b in values:
                cosine=sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
                maximum=max(maximum,math.degrees(math.acos(max(-1.,min(1.,cosine)))))
    if maximum>.025:raise ValueError('Discontinuous native cap shading')
    result={'authored_retained_cap_faces':len(cap_faces),'authored_corner_count':len(changed),
            'matching_generated_bevel_corner_count':bevel_loops,'maximum_shared_cap_normal_angle_degrees':maximum,
            'unrelated_native_corner_maximum_reencoding_degrees':diagnostic['maximum_unmodified_target_roundtrip_angle_degrees'],'shape_changes_by_this_field':False,
            'cap_original_face_tag':1,'native_original_face_strength':16384,
            'scope':'New continuous normal field on the actual retained post-bevel original cap and its shared generated bevel corners. This does not relax pre-cut preservation, self/contact or export correspondence guards.'}
    obj['authored_fascia_field']=json.dumps(result,sort_keys=True)
    symmetric=fascia_side_field.apply(obj,optical_floor_z=.673)
    obj['authored_fascia_side_field']=json.dumps(symmetric,sort_keys=True)
    return {'cap':result,'outer_side_endpoints':symmetric}
