"""Complete current native target, original owner and boundary field checks."""
from collections import defaultdict
import numpy as np
from .contracts import NAMES, RECEIVER, require
from . import surface


def weights(q,t):
    a,b,c=t;ab=b-a;ac=c-a;d=q-a
    u=np.linalg.solve([[ab@ab,ab@ac],[ab@ac,ac@ac]],[ab@d,ac@d])
    return np.array([1-u.sum(),u[0],u[1]])


def bounded_angle(a,b,field):
    try:return {'status':'passed',**field.complete_affine_angle(a,b,guard=.025)}
    except ValueError as error:return {'status':'failed','reason':str(error)}


def native_targets(actual,requested,field):
    reports={};failures=[]
    for name,plan in requested.items():
        row=actual[name]
        require(set(row['uvs'])==set(plan['triangle_uvs']),'Changed native UV channel inventory: '+name)
        out=[]
        for i,loops in enumerate(row['triangle_loops']):
            angle=bounded_angle(plan['requested_triangle_normals'][i],[row['normals'][li] for li in loops],field)
            uv=max(abs(a-b) for layer,values in plan['triangle_uvs'].items()
                   for target,li in zip(values[i],loops) for a,b in zip(target,row['uvs'][layer][li]))
            item={'triangle':i,'normal':angle,'whole_uv_component_error':uv,'status':'passed' if angle['status']=='passed' and uv<=1e-5 else 'failed'}
            out.append(item)
            if item['status']!='passed':failures.append([name,i])
        reports[name]=out
    return {'status':'passed' if not failures else 'failed','meshes':reports,'failures':failures}


def receiver(actual,before,field):
    require(set(actual['uvs'])==set(before['uvs']),'Changed receiver UV channels')
    records=[]
    for i,loops in enumerate(actual['triangle_loops']):
        oldloops=before['triangle_loops'][i]
        angle=bounded_angle([before['normals'][li] for li in oldloops],[actual['normals'][li] for li in loops],field)
        uv=max(abs(x-y) for layer in actual['uvs'] for a,b in zip(oldloops,loops)
               for x,y in zip(before['uvs'][layer][a],actual['uvs'][layer][b]))
        records.append({'triangle':i,'normal':angle,'whole_uv_component_error':uv,'status':'passed' if angle['status']=='passed' and uv<=1e-5 else 'failed'})
    return {'status':'passed' if all(r['status']=='passed' for r in records) else 'failed','triangles':records,
            'physical_material_fields_exact':True,'normal_guard_degrees':.025,'uv_guard':1e-5}


def protected(actual,plan,base,declaration,providers):
    ex=providers.exact;fi=providers.fi;field=providers.field
    oldvv=np.asarray(base['vertices']);oldtri=oldvv[np.asarray(base['triangles'])]
    vv=np.asarray(actual['vertices']);nt=vv[np.asarray(actual['triangles'])]
    old_retained={old for old,new in plan['shared_terminal_sections']['preserved_old_triangles']}
    pieces=defaultdict(list)
    for i,(t,domain) in enumerate(zip(oldtri,base['triangle_domains'])):
        poly=[ex.vector(q) for q in t]
        if domain!='inner':
            if i in old_retained:pieces[i].append(poly)
            continue
        sign=1 if sum(q[0] for q in poly)>=0 else -1
        hit,out=ex.partition(poly,[((ex.F(sign),ex.F(0),ex.F(0)),ex.F(float(np.float32(.755)))),
                                     ((ex.F(0),ex.F(0),ex.F(-1)),ex.F(-float(np.float32(.275))))])
        for q in (out if hit else [poly]):
            if ex.positive_area(q):pieces[i].append(q)
    declared=set()
    for entry in declaration:
        points=entry.get('oriented_base_points')
        ids=[i for i,t in enumerate(oldtri) if base['triangle_domains'][i]=='inner' and t.tolist()==points]
        require(len(ids)==1 and ids[0] not in declared,'Nonunique actual finite inner-field owner')
        declared.add(ids[0])
    selected=[i for i,d in enumerate(plan['triangle_domains']) if d in ('outer','rim','inner_preserved_fragment')]
    require(set(actual['uvs'])==set(base['triangle_uvs']),'Changed original UV channel inventory')
    records=[];failures=[];targets=defaultdict(list);target_ids=defaultdict(list);released=[]
    lows=oldtri.min(1);highs=oldtri.max(1)
    for i in selected:
        t=nt[i];domain=plan['triangle_domains'][i];expected='inner' if domain=='inner_preserved_fragment' else domain
        candidates=[]
        for old in np.flatnonzero(np.all(lows<=t.max(0)+2e-7,axis=1)&np.all(highs>=t.min(0)-2e-7,axis=1)):
            if base['triangle_domains'][old]!=expected:continue
            q=np.asarray([fi.point_triangle(p,oldtri[old]) for p in t]);bound=float(np.max(np.linalg.norm(q-t,axis=1)))
            if bound<=2e-7:candidates.append((bound,int(old),q))
        if not candidates:
            failures.append({'triangle':i,'reason':'No complete finite original owner'});continue
        bound,old,q=min(candidates,key=lambda r:(r[0],r[1]));w=np.asarray([weights(p,oldtri[old]) for p in q])
        loops=actual['triangle_loops'][i]
        uv=max(float(np.max(np.abs(w@np.asarray(values[old])-np.asarray([actual['uvs'][layer][li] for li in loops])))) for layer,values in base['triangle_uvs'].items())
        release=old in declared and domain=='inner_preserved_fragment'
        normal={'status':'authored_finite_release'} if release else bounded_angle((w@np.asarray(base['requested_triangle_normals'][old])).tolist(),[actual['normals'][li] for li in loops],field)
        item={'triangle':i,'old_triangle':old,'domain':domain,'whole_affine_position_bound_m':bound,
              'original_barycentric':w.tolist(),'original_surface_points':q.tolist(),'whole_uv_error':uv,'complete_normal':normal,
              'status':'passed' if uv<=1e-5 and normal['status'] in ('passed','authored_finite_release') else 'failed'}
        records.append(item)
        if release:released.append(i)
        if item['status']!='passed':failures.append(item)
        targets[old].append([ex.vector(p) for p in t]);target_ids[old].append(i)
    ownership=plan.get('normal_authorship422',{})
    require(set(ownership.get('current_fragments',[]))==set(released) and len(released)==7,'Released normal fragments do not match finite current owners')
    require(set(targets)==set(pieces),'Current and original protected owner sets differ')
    surfaces=[]
    for owner,polys in sorted(pieces.items()):
        first=surface.cover(polys,targets[owner],ex)
        source_tris=[[p[0],p[i],p[i+1]] for p in polys for i in range(1,len(p)-1) if ex.positive_area([p[0],p[i],p[i+1]])]
        reverse=surface.cover(targets[owner],source_tris,ex)
        item={'original_triangle':owner,'current_triangles':target_ids[owner],'original_to_current':first,'current_to_original':reverse}
        surfaces.append(item)
        if first['status']!='passed' or reverse['status']!='passed':failures.append({'surface_owner':owner})
    # Recompute all edge incidences; neither reported edge IDs nor fan counts
    # may remove part of the current authored/protected boundary.
    edges=defaultdict(list)
    for i,t in enumerate(plan['triangles']):
        for a,b in zip(t,t[1:]+t[:1]):edges[tuple(sorted((a,b)))].append(i)
    require(all(len(v)==2 for v in edges.values()),'Current cover lacks closed edge incidence')
    boundaries=[];lower=set();release_set=set(released)
    for edge,uses in edges.items():
        if len(set(uses)&release_set)!=1:continue
        inside=next(i for i in uses if i in release_set);outside=next(i for i in uses if i not in release_set)
        domain=plan['triangle_domains'][outside]
        require(domain in ('authored_inner_front','inner_preserved_fragment'),'Unexpected finite release boundary')
        kind='coplanar_lower' if domain=='authored_inner_front' else 'protected'
        if kind=='coplanar_lower':
            require(all(vv[v,2]==float(np.float32(.275)) for v in edge),'Lower field fan left fixed upper level');lower.update(edge)
        normals=[]
        for i in (inside,outside):normals.append([actual['normals'][actual['triangle_loops'][i][actual['triangles'][i].index(v)]] for v in edge])
        a,b=normals;proof=bounded_angle([a[0],a[1],a[0]],[b[0],b[1],b[0]],field)
        boundaries.append({'edge':list(edge),'inside':inside,'outside':outside,'kind':kind,'complete_native_edge':proof})
        if proof['status']!='passed':failures.append({'boundary':edge,'proof':proof})
    require(len(boundaries)==11 and sum(r['kind']=='protected' for r in boundaries)==6 and len(lower)==7,'Complete current boundary inventory changed')
    fans=[i for i,t in enumerate(plan['triangles']) if plan['triangle_domains'][i]=='authored_inner_front' and set(t)&lower]
    require(len(fans)==15,'Complete current lower incident-fan inventory changed')
    require(ownership.get('authored_inner_front_fans')==fans and set(ownership.get('lower_boundary_vertices',[]))==lower,'Captured lower-fan domain differs from actual incidence')
    allowed={(i,k) for i in released for k in range(3)} | {(i,k) for i in fans for k,v in enumerate(plan['triangles'][i]) if v in lower}
    require({tuple(v) for v in ownership.get('allowed_corners',[])}==allowed,'Captured allowed normal corners differ from complete finite domains')
    original_rows=ownership.get('original_finite_owners',[])
    require(len(original_rows)==5 and {r.get('owner') for r in original_rows}==declared,'Captured original field owner inventory differs')
    for entry in original_rows:
        i=entry['owner']
        require(entry['points']==oldtri[i].tolist() and entry['requested_normals']==base['requested_triangle_normals'][i],'Captured original owner field differs from current base')
    actual_owners={str(r['triangle']):r['old_triangle'] for r in records if r['triangle'] in release_set}
    require(ownership.get('current_fragment_owners')==actual_owners,'Captured field fragment owners differ from actual correspondence')
    declared_edges={(tuple(sorted(q['edge'])),q['inside'],q['outside'],q['kind']) for q in ownership.get('complete_boundary_fields',[])}
    actual_edges={(tuple(q['edge']),q['inside'],q['outside'],q['kind']) for q in boundaries}
    require(declared_edges==actual_edges,'Captured boundary list differs from complete incidence')
    return {'status':'passed' if not failures else 'failed','field_records':records,'surface_owners':surfaces,'boundaries':boundaries,
            'released_fragments':released,'actual_lower_fans':fans,'failures':failures,'protected_triangle_count':len(selected),
            'original_owner_count':len(pieces),'old_normal_triangle_count':len(selected)-len(released)}
