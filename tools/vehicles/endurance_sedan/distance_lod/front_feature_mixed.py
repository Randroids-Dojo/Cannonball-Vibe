"""Current-source mixed-material front preservation; no file/scene mutation.

References come from the actual native input after caller-locked packet/field
binding. Old cap tags and historical object summaries have no authority here.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import bpy





from . import front_feature_base as original
from . import affine_field as affine
_key=original._key
_angle=original._angle
digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
DOMAIN={'schema':'current-native-mixed-front-feature.v1','object':'LOD0_FrontBumper',
    'materials':['Material_Paint','Material_Trim'],'levels':[1,2],
    'shoulder':{'minimum_all_vertex_z_m':.80,'maximum_y_minimum_m':2.23,
                'side_maximum_absolute_x_minimum_m':.65,'side_maximum_y_minimum_m':2.04},
    'trim':'all actual new_return_wall triangles plus boundary-vertex one-ring',
    'closure':'complete source triangles enclosed by union seed vertices; no recursive fan growth',
    'field_bound':'affine-residual-over-exact-closed-normal-triangle-minimum'}


def require(value,message):
    if not value:raise ValueError(message)





def capture(source,*,context,binding_check):
    require(source.name=='LOD0_FrontBumper' and source.parent and source.parent.name=='Visual_LOD0' and not source.modifiers,
            'Expected complete original native front bumper')
    binding,packet=binding_check(source,context)
    mesh=source.data;mesh.calc_loop_triangles()
    require([m.name if m else None for m in mesh.materials]==DOMAIN['materials'],'Mixed front ordered material slots changed')
    require(mesh.uv_layers.active and mesh.uv_layers.active.name=='SurfaceMeters' and len(mesh.uv_layers)==1,'Mixed front chart changed')
    require(len(mesh.polygons)==len(mesh.loop_triangles) and all(len(p.vertices)==3 for p in mesh.polygons),'Expected current explicit front triangles')
    points=[tuple(v.co) for v in mesh.vertices]
    triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
    materials=[t.material_index for t in mesh.loop_triangles]
    require(set(materials)=={0,1},'Both actual front materials are required')
    require(len({_key([points[v] for v in t]) for t in triangles})==len(triangles),'Ambiguous original native triangles')
    edge_faces=defaultdict(list);vertex_faces=defaultdict(set)
    for i,tri in enumerate(triangles):
        require(len(set(tri))==3 and mesh.loop_triangles[i].area>1e-12,'Invalid original triangle')
        for v in tri:vertex_faces[v].add(i)
        for a,b in zip(tri,tri[1:]+tri[:1]):edge_faces[tuple(sorted((a,b)))].append(i)
    require(all(len(faces)==2 for faces in edge_faces.values()),'Original mixed front is not closed')
    trim={i for i,value in enumerate(materials) if value==1}
    proof=packet['core']['stages'][-1]['proof'];owners=proof['owners']
    require(len(owners)==proof['before_fan_bumper_triangles'] and {r['face'] for r in owners}==set(range(len(owners))),
            'Incomplete current inlet owner inventory')
    old_trim={row['face'] for row in owners if row['kind']=='new_return_wall'}
    fan=proof['generated_rear_fan']
    if fan['repairs']:
        mapping={row['old_face']:row['new_face'] for row in fan['outside_faces']}
        require(len(mapping)==len(fan['outside_faces']),'Ambiguous current fan correspondence')
        owned_trim={mapping[i] for i in old_trim if i in mapping}
    else:owned_trim=old_trim
    require(owned_trim==trim and bool(trim),'Current Trim walls differ from actual inlet provenance')
    boundary=[edge for edge,faces in edge_faces.items() if len({materials[i] for i in faces})==2]
    require(bool(boundary),'Missing actual mixed-material boundary')
    boundary_vertices={v for edge in boundary for v in edge}
    trim_fan=set().union(*(vertex_faces[v] for v in boundary_vertices))
    shoulder={i for i,t in enumerate(triangles) if materials[i]==0 and mesh.polygons[i].use_smooth
        and min(points[v][2] for v in t)>=.80
        and (max(points[v][1] for v in t)>=2.23 or
             (max(abs(points[v][0]) for v in t)>=.65 and max(points[v][1] for v in t)>=2.04))}
    require(bool(shoulder),'Empty current shoulder domain')
    seeds=trim|trim_fan|shoulder
    vertices={v for i in seeds for v in triangles[i]}
    rows=[]
    for i,t in enumerate(mesh.loop_triangles):
        if not set(t.vertices)<=vertices:continue
        normals=[tuple(mesh.corner_normals[li].vector) for li in t.loops]
        field=affine.preserve_field(normals,normals)
        ps=[points[v] for v in t.vertices]
        rows.append({'points':ps,'key':_key(ps),'normals':normals,
            'uv':[tuple(mesh.uv_layers.active.data[li].uv) for li in t.loops],
            'smooth':mesh.polygons[t.polygon_index].use_smooth,'material_index':t.material_index,
            'source_triangle':i,'source_field_minimum':field})
    require(rows and set(trim)<={r['source_triangle'] for r in rows},'Incomplete protected current material domain')
    return {'triangles':rows,'points':{points[v] for v in vertices},
        'matrix':tuple(tuple(row) for row in source.matrix_world),'seed_count':len(seeds),
        'initial':len(triangles),'source_name':source.name,'materials':DOMAIN['materials'],
        'trim_keys':sorted(_key([points[v] for v in triangles[i]]) for i in trim),
        'binding':binding,'binding_digest':context['expected_binding_digest'],
        'domain':{'profile':DOMAIN,'Trim_triangles':len(trim),'boundary_edges':len(boundary),
            'Trim_boundary_fan_triangles':len(trim_fan),'shoulder_seed_triangles':len(shoulder),
            'union_seed_triangles':len(seeds),'protected_vertices':len(vertices),'complete_triangles':len(rows),
            'minimum_original_affine_length_lower':min(r['source_field_minimum']['minimum_original_length_lower'] for r in rows)}}


def material_metadata(obj):
    obj.data.calc_loop_triangles()
    values=[t.material_index for t in obj.data.loop_triangles]
    return {'materials':[m.name if m else None for m in obj.data.materials],
            'triangle_materials_sha256':digest(values),
            'triangle_material_counts':dict(sorted(Counter(str(v) for v in values).items()))}


def verify(obj,reference):
    result=original.verify(obj,reference)
    mesh=obj.data;mesh.calc_loop_triangles()
    require([m.name if m else None for m in mesh.materials]==reference['materials'],'Mixed front ordered materials changed')
    found={}
    for triangle in mesh.loop_triangles:
        ps=[tuple(mesh.vertices[v].co) for v in triangle.vertices]
        found.setdefault(_key(ps),[]).append((triangle,ps))
    trim_keys=sorted(_key([tuple(mesh.vertices[v].co) for v in t.vertices]) for t in mesh.loop_triangles if t.material_index==1)
    require(trim_keys==reference['trim_keys'],'Complete actual Trim wall triangles changed')
    require({t.material_index for t in mesh.loop_triangles}=={0,1},'Unexpected actual front material index')
    fields=[]
    for row in reference['triangles']:
        matches=found.get(row['key'],[])
        require(len(matches)==1,'Lost or ambiguous mixed protected triangle')
        triangle,ps=matches[0]
        require(triangle.material_index==row['material_index'],'Protected front material changed')
        order=[row['points'].index(p) for p in ps]
        expected=[list(row['normals'][i]) for i in order]
        actual=[list(mesh.corner_normals[li].vector) for li in triangle.loops]
        proof=affine.preserve_field(expected,actual)
        fields.append({'source_triangle':row['source_triangle'],'actual_triangle':triangle.index,**proof})
    result.update(materials_exact=True,complete_Trim_triangles=len(reference['trim_keys']),
        complete_affine_field={'triangles':len(fields),'maximum_angle_upper_degrees':max(r['angle_upper_degrees'] for r in fields),
            'minimum_original_length_lower':min(r['minimum_original_length_lower'] for r in fields),'rows':fields},
        actual_material_metadata=material_metadata(obj))
    return result


class Adapter(original.Adapter):
    def __init__(self,source,existing,encoder,reference):
        self.reference,self.existing,self.encoder=reference,existing,encoder
        require(source.name==reference['source_name'],'Wrong original native object')

    def prepare(self,obj):
        verify(obj,self.reference)
        return super().prepare(obj)

    def restore(self,obj,protection):
        result=super().restore(obj,protection)
        result['complete_current_mixed_field']=verify(obj,self.reference)
        return result
