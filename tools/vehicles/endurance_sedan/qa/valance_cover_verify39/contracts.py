"""Strict current-input contracts; no file or scene access."""
import hashlib
import json
import math
import re
from collections import Counter

NAMES = ('LOD0_RearLowerValance','LOD0_RearValanceMount_L1','LOD0_RearValanceMount_L2',
         'LOD0_RearValanceMount_R1','LOD0_RearValanceMount_R2')
RECEIVER = 'LOD0_RearBumper'
POLICY = {'schema':'source-valance-cover39.v1','members':list(NAMES),'receiver':RECEIVER,
    'original_triangles':324,'cover_triangles':1226,'mount_triangles':124,
    'sheet_stock_m':.0012,'stock_encoding_guard_m':.000001,'rest_clearance_m':.001001,
    'surface_correspondence_m':.0000002,'normal_angle_degrees':.025,'uv_absolute':.00001,
    'finite_normal_domains':5,'pocket_rays':91}


def require(value, message):
    if not value:
        raise ValueError(message)


def plain(value):
    return json.loads(json.dumps(value,allow_nan=False))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def geometry_binding(row):
    return {'name':row['name'],'vertices':len(row['vertices']),'triangles':len(row['triangles']),
            'sha256':digest({k:row[k] for k in ('name','vertices','triangles')})}


def vector(value, size, label):
    require(type(value) is list and len(value)==size and
            all(type(v) in (int,float) and math.isfinite(v) for v in value),'Invalid '+label)


def mesh(row, name, fields=False):
    require(type(row) is dict and row.get('name')==name,'Actual semantic identity mismatch: '+name)
    vertices=row.get('vertices');triangles=row.get('triangles')
    require(type(vertices) is list and len(vertices)>=3 and type(triangles) is list and triangles,'Missing actual mesh: '+name)
    for point in vertices:vector(point,3,'vertex')
    for tri in triangles:
        require(type(tri) is list and len(tri)==3 and len(set(tri))==3 and
                all(type(v) is int and 0<=v<len(vertices) for v in tri),'Invalid actual triangle: '+name)
    if not fields:return
    normals=row.get('normals');loops=row.get('triangle_loops');uvs=row.get('uvs')
    require(type(normals) is list and normals and type(loops) is list and len(loops)==len(triangles),'Incomplete native corners: '+name)
    for normal in normals:
        vector(normal,3,'normal');require(abs(math.hypot(*normal)-1)<=1e-6,'Invalid unit normal: '+name)
    used=set()
    for tri in loops:
        require(type(tri) is list and len(tri)==3 and len(set(tri))==3 and
                all(type(v) is int and 0<=v<len(normals) for v in tri),'Invalid native triangle loops: '+name)
        used.update(tri)
    require(used==set(range(len(normals))),'Unreferenced or missing native corner: '+name)
    require(type(uvs) is dict and uvs,'Missing complete native UV channels: '+name)
    for layer,values in uvs.items():
        require(type(layer) is str and layer and type(values) is list and len(values)==len(normals),'Incomplete UV channel: '+name)
        for uv in values:vector(uv,2,'UV')
    materials=row.get('materials');indices=row.get('triangle_materials')
    require(type(materials) is list and materials and all(type(v) is str and v for v in materials),'Missing native materials: '+name)
    require(type(indices) is list and len(indices)==len(triangles) and
            all(type(i) is int and 0<=i<len(materials) for i in indices),'Incomplete native material ownership: '+name)


def requested_row(row,name):
    mesh(row,name)
    count=len(row['triangles'])
    require(type(row.get('triangle_domains')) is list and len(row['triangle_domains'])==count and
            all(type(d) is str and d for d in row['triangle_domains']),'Incomplete requested finite domains: '+name)
    require(row.get('materials')==['Material_Trim'],'Unexpected requested manufactured material: '+name)
    values=row.get('requested_triangle_normals')
    require(type(values) is list and len(values)==count,'Incomplete requested field: '+name)
    for tri in values:
        require(type(tri) is list and len(tri)==3,'Invalid requested corner field')
        for n in tri:
            vector(n,3,'requested normal');require(abs(math.hypot(*n)-1)<=1e-6,'Invalid requested unit field')
    require(type(row.get('triangle_uvs')) is dict and row['triangle_uvs'],'Missing requested UV channels')
    for layer,values in row['triangle_uvs'].items():
        require(type(layer) is str and type(values) is list and len(values)==count,'Incomplete requested UV channel')
        for tri in values:
            require(type(tri) is list and len(tri)==3,'Invalid requested triangle UV')
            for uv in tri:vector(uv,2,'requested UV')


def outer_roles(cover,layout,ex):
    """Consume every native conforming fragment in its exact original facet."""
    sources=[]
    for t,role in zip(layout['added'],layout['authored_patch_domains']):
        require(type(t) is list and len(t)==3 and all(type(v) is int and 0<=v<len(layout['vertices']) for v in t),'Invalid authored layout facet')
        p=[ex.vector(layout['vertices'][v]) for v in t]
        n=ex.cross(ex.sub(p[1],p[0]),ex.sub(p[2],p[0]));require(ex.dot(n,n)>0,'Collapsed original stock facet')
        planes=[(ex.cross(n,ex.sub(b,a)),ex.dot(ex.cross(n,ex.sub(b,a)),a)) for a,b in zip(p,p[1:]+p[:1])]
        sources.append((p,n,planes,role))
    groups={};roles={}
    for i,(t,domain) in enumerate(zip(cover['triangles'],cover['triangle_domains'])):
        if domain!='terminal_outer':continue
        q=[ex.vector(cover['vertices'][v]) for v in t]
        candidates=[j for j,(p,n,planes,role) in enumerate(sources)
                    if all(ex.dot(n,ex.sub(v,p[0]))==0 and all(ex.dot(m,v)>=d for m,d in planes) for v in q)]
        require(len(candidates)==1,'Current outer fragment lacks one complete exact finite facet owner')
        j=candidates[0];p,n,planes,role=sources[j]
        require(ex.dot(n,ex.cross(ex.sub(q[1],q[0]),ex.sub(q[2],q[0])))>0,'Flipped current outer fragment')
        groups.setdefault(j,[]).append((i,q));roles[tuple(sorted(t))]=role
    require(set(groups)==set(range(len(sources))),'Unconsumed original outer sheet facet')
    records=[]
    for j,(p,n,planes,role) in enumerate(sources):
        remaining=[p]
        for i,q in groups[j]:
            cuts=[(ex.cross(n,ex.sub(b,a)),ex.dot(ex.cross(n,ex.sub(b,a)),a)) for a,b in zip(q,q[1:]+q[:1])]
            todo=[]
            for poly in remaining:
                inside,outside=ex.partition(poly,cuts)
                todo.extend(v for v in outside if ex.positive_area(v))
            remaining=todo
        require(not remaining,'Incomplete whole original stock facet coverage')
        original_area=ex.dot(n,ex.cross(ex.sub(p[1],p[0]),ex.sub(p[2],p[0])))
        current_area=sum(ex.dot(n,ex.cross(ex.sub(q[1],q[0]),ex.sub(q[2],q[0]))) for _,q in groups[j])
        require(original_area==current_area,'Repeated or overlapping current outer facet area')
        records.append({'layout_facet':j,'role':role,'current_triangles':[i for i,_ in groups[j]],
                        'complete_exact_coplanar_partition':True,'exact_oriented_area_sum':str(current_area)})
    return roles,records


def validate(actual_rows,actual_fields,requested,companion,references,providers):
    require(type(actual_rows) is dict and actual_rows,'Missing global current source rows')
    require(type(actual_fields) is dict and set(actual_fields)==set(NAMES)|{RECEIVER},'Exactly six current field rows required')
    require(type(requested) is dict and set(requested)==set(NAMES),'Exactly five requested meshes required')
    require(type(companion) is dict and companion.get('schema')=='source-valance-cover-construction39.v1','Wrong construction companion')
    require(companion.get('policy')==POLICY and companion.get('source_phase')=='pre-lod','Changed policy or phase')
    require(type(references) is dict and set(references)=={'original_valance','valance_plan','prelate_rear34'},'Incomplete actual original references')
    before=companion.get('before')
    require(type(before) is dict and set(before)=={NAMES[0],RECEIVER},'Incomplete pre-cover boundary')
    for name,row in before.items():mesh(row,name,True)
    for name,row in actual_rows.items():
        require(type(name) is str and type(row) is dict and type(row.get('properties')) is dict,'Malformed current global metadata')
        if 'source_preview_only' in row['properties']:
            require(type(row['properties']['source_preview_only']) is bool,'Invalid native preview identity')
    rows={name:row for name,row in actual_rows.items() if name.startswith('LOD0_') and row['properties'].get('source_preview_only') is not True}
    require(set(actual_fields)<=set(rows),'Current five parts or receiver omitted from global source domain')
    for name,row in rows.items():mesh(row,name)
    for name,row in actual_fields.items():
        mesh(row,name,True)
        require(all(row[k]==rows[name][k] for k in ('name','vertices','triangles')),'Field/global geometry disagreement: '+name)
        require(row['materials']==rows[name].get('material_names'),'Missing or different global/native materials: '+name)
        matrix=rows[name].get('rest_world_matrix')
        require(type(matrix) is list and len(matrix)==4,'Missing complete fixed assembly frame: '+name)
        for values in matrix:vector(values,4,'fixed assembly matrix')
        require(matrix==[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],'Changed fixed assembly frame: '+name)
    for name,row in requested.items():
        requested_row(row,name)
        require(all(row[k]==actual_fields[name][k] for k in ('name','vertices','triangles','materials')),'Actual mesh differs from requested construction: '+name)
        require(all(i==0 for i in actual_fields[name]['triangle_materials']),'Changed requested material assignment: '+name)
    require(len(requested[NAMES[0]]['triangles'])==1226 and sum(len(requested[n]['triangles']) for n in NAMES[1:])==124,'Changed finite construction topology budget')
    require(all(actual_fields[RECEIVER][k]==before[RECEIVER][k] for k in ('vertices','triangles','materials','triangle_materials')),'Protected receiver physical/material fields changed')
    plan=references['valance_plan'];roles=companion.get('triangle_domains')
    require(type(plan) is dict and plan.get('schema')=='new-original-ribbon-corner-field.v1' and plan.get('object')==NAMES[0],'Wrong original finite-role plan')
    require(plan.get('reference_sha256')==digest(references['original_valance']) and plan.get('targets_sha256')==digest(plan.get('targets')),'Original role/reference/target digest mismatch')
    require(type(roles) is list and len(roles)==len(before[NAMES[0]]['triangles'])==324,'Incomplete pre-cover roles')
    derived=[None]*324;seen=set();all_loops=set()
    for entry in plan.get('domains',[]):
        face=entry.get('face');ids=entry.get('complete_triangles');domain=entry.get('domain')
        require(type(face) is int and face>=0 and face not in seen,'Invalid original face owner')
        require(type(domain) is str and (domain in ('front','back','top','bottom','left','right') or re.fullmatch(r'passage_(-1|1)_[0-7]',domain)),'Unknown original manufactured domain')
        require(type(ids) is list and ids and len(ids)==len(set(ids)) and all(type(i) is int and 0<=i<324 and derived[i] is None for i in ids),'Invalid complete original triangle ownership')
        loops=entry.get('loops')
        require(type(loops) is list and len(loops)>=3 and len(set(loops))==len(loops)
                and all(type(i) is int and 0<=i<len(before[NAMES[0]]['normals']) and i not in all_loops for i in loops),'Invalid complete original face loops')
        used=Counter((a,b) for i in ids for t in [before[NAMES[0]]['triangle_loops'][i]] for a,b in zip(t,t[1:]+t[:1]))
        require(all(c==1 for c in used.values()),'Repeated original face cell edge')
        rim={edge for edge in used if (edge[1],edge[0]) not in used}
        require(rim==set(zip(loops,loops[1:]+loops[:1])),'Original role loops differ from complete actual native face boundary')
        require({v for i in ids for v in before[NAMES[0]]['triangle_loops'][i]}==set(loops),'Original face has missing or extraneous native loops')
        all_loops.update(loops)
        seen.add(face)
        for i in ids:derived[i]=domain
    require(derived==roles and all(d is not None for d in derived),'Changed or missing original role inventory')
    require(seen==set(range(len(plan['domains']))) and all_loops==set(range(len(before[NAMES[0]]['normals']))),'Incomplete original face/loop inventory')
    declaration=companion.get('finite_field_domains')
    require(type(declaration) is list and len(declaration)==5,'Incomplete bounded original normal release')
    for entry in declaration:
        require(type(entry) is dict and type(entry.get('oriented_base_points')) is list and len(entry['oriented_base_points'])==3,'Invalid original finite field selector')
        for point in entry['oriented_base_points']:vector(point,3,'finite field selector')
    # Recompute the original intermediate sheet from current inputs. Its output
    # is a reference only; all final source predicates below remain independent.
    rebuilt=plain(providers.prepare_base(before[NAMES[0]],references['prelate_rear34'],roles,providers.exact,providers.fi.point_triangle))
    require(rebuilt[NAMES[0]]==companion.get('base'),'Companion original sheet does not follow actual pre-cover inputs')
    base=companion['base'];requested_row(base,NAMES[0])
    for name in NAMES[1:]:require(rebuilt[name]==requested[name],'Changed actual finite attachment construction: '+name)
    cover=requested[NAMES[0]];domains=cover['triangle_domains'];authored=cover.get('triangle_authored_roles')
    require(type(authored) is list and len(authored)==1226 and all(type(v) is str for v in authored),'Incomplete actual authored face roles')
    require(set(domains)=={'outer','rim','terminal_outer','terminal_inner','terminal_rim','inner_preserved_fragment','authored_inner_front','formed_side_inner','finite_upper_stock_cap'},'Unknown or missing stock domains')
    layout=companion.get('layout')
    require(type(layout) is dict and layout.get('body_changed') is False,'Invalid shared current terminal layout')
    require(type(layout.get('added')) is list and len(layout['added'])==len(layout.get('authored_patch_domains',[])),'Incomplete outer facet role layout')
    roles_by_tri,partition=outer_roles(cover,layout,providers.exact)
    return rows,base,roles_by_tri,partition
