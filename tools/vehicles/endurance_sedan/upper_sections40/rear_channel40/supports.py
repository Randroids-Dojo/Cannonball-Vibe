"""Integral finite rear rail/B seal supports from actual current cap and seal facets.

Pure arrays; no Blender, archived geometry assignment, file writes or exports.
The root is a finite opening inside the owned existing end cap. Two opposed
formed sheets return to the actual seal. Every original native vertex remains.
"""
import copy, math
from collections import defaultdict
from .vectors import f32,mix,sub,dot,cross,unit,normal,clip,zipper,orient
from .mesh import empty,old_face,new_face,ear_indices
from .channel import open_orientation
from .pressure_section import opposed_section
from .maths import closest_double


def interpolate(a,b,t):
    return unit(mix(a,b,t))


def bottom_height(old, records, y):
    sections={}
    for v in {v for q in records for v in q['indices']}:
        p=old['vertices'][v];sections.setdefault(p[1],[]).append(p)
    line=[(yy,min(ps,key=lambda p:abs(p[0]))[2]) for yy,ps in sorted(sections.items())]
    if y<=line[0][0]:return line[0][1]
    if y>=line[-1][0]:return line[-1][1]
    for (a,za),(b,zb) in zip(line,line[1:]):
        if a<=y<=b:return za+(zb-za)*(y-a)/(b-a)
    raise ValueError('Actual lower section missing')


def build(rows, side, kind, scope, miter, ideal=None, observe=None):
    old=rows[scope['object']];seal=rows['LOD0_DoorApertureSeal_R'+side]
    cap=scope['free_lower_cap_faces' if kind=='rail' else 'aft_cap_faces']
    owned={q['face'] for q in cap};r=empty(old,ideal)
    reference={q['face']:q for q in cap}
    for fi,q in reference.items():
        if old['triangles'][fi]!=q['indices'] or [old['vertices'][v] for v in old['triangles'][fi]]!=q['positions_m']:
            raise ValueError(('Actual fixed cap changed',old['name'],fi))
    for fi in range(len(old['triangles'])):
        if fi not in owned:old_face(r,old,fi,ideal)
    root_ids=sorted({v for fi in owned for v in old['triangles'][fi]})
    if kind=='rail':
        # Actual concealed inboard receiving wall; the old lower cap remains
        # wholly present. The shared lower/upper root section is a finite
        # 1.501mm vertical band above the unchanged gasket top facet.
        ph0=6 if side=='R' else 5;v0=.75 if side=='R' else .25
        A=mix(seal['vertices'][15*8+ph0],seal['vertices'][15*8+(ph0+1)%8],v0)
        B=mix(seal['vertices'][16*8+ph0],seal['vertices'][16*8+(ph0+1)%8],v0)
        z0=mix(A,B,.18)[2]+.0015;z1=mix(A,B,.985)[2]+.0015
        qmap={v:[(old['vertices'][v][1]+1.16)/.505,
                 (old['vertices'][v][2]-max(z0+(z1-z0)*(old['vertices'][v][1]+1.16)/.505,bottom_height(old,scope['original_lower_cap_faces'],old['vertices'][v][1])+.0005))/.001501] for v in root_ids}
        ulo,uhi=0.,1.;branch=(15,16);seal_limits=(.180,.985)
    else:
        zlo=min(old['vertices'][v][2] for v in root_ids);zhi=max(old['vertices'][v][2] for v in root_ids)
        qmap={v:[0. if old['vertices'][v][2]<(zlo+zhi)/2 else 1.,
                 0. if old['vertices'][v][1]<-.636 else 1.] for v in root_ids}
        ulo,uhi=.04,.98;branch=(16,0);seal_limits=(.96,.02)
    vlo,vhi=(0.,1.) if kind=='rail' else (.15,.70)
    uv_source=ideal['uv_corner_targets'] if ideal else {n:[[uv[l] for l in ls] for ls in old['triangle_loops']] for n,uv in old['uvs'].items()}
    nn_source=ideal['normal_corner_targets'] if ideal else [[old['normals'][l] for l in ls] for ls in old['triangle_loops']]
    cache={tuple(round(x,13) for x in qmap[v]):v for v in root_ids};parameters={v:q[:] for v,q in qmap.items()};construction=[]
    def vertex(q):
        key=tuple(round(x,13) for x in q['q'])
        if key not in cache:
            cache[key]=len(r['vertices']);r['vertices'].append(f32(q['p']));parameters[cache[key]]=q['q'][:]
        elif math.dist(r['vertices'][cache[key]],q['p'])>2e-7:raise ValueError('Finite cap correspondence is ambiguous')
        return cache[key]
    for fi in sorted(owned):
        source=[{'p':old['vertices'][v],'q':qmap[v], 'w':[float(j==k) for k in range(3)]} for j,v in enumerate(old['triangles'][fi])]
        # Disjoint partition of the exact original cap outside one finite hole.
        left=clip(source,0,ulo,False);right=clip(source,0,uhi)
        middle=clip(clip(source,0,ulo),0,uhi,False)
        lower=clip(middle,1,vlo,False);upper=clip(middle,1,vhi)
        hole=clip(clip(middle,1,vlo),1,vhi,False)
        construction.append({'source_face':fi,'removed_polygon_m':[q['p'] for q in hole]})
        for poly in (left,right,lower,upper):
            if len(poly)<3:continue
            ids=[vertex(q) for q in poly]
            for ix in ear_indices([q['p'] for q in poly]):
                t=[ids[j] for j in ix]
                uv={n:[[sum(poly[j]['w'][k]*vs[fi][k][a] for k in range(3)) for a in (0,1)] for j in ix] for n,vs in uv_source.items()}
                ns=[unit([sum(poly[j]['w'][k]*nn_source[fi][k][a] for k in range(3)) for a in range(3)]) for j in ix]
                new_face(r,t,'retained_cap_fragment',old['triangle_materials'][fi],fi,uv,ns)
    def root_chain(v):
        return sorted(((q[0]-ulo)/(uhi-ulo),i) for i,q in parameters.items() if abs(q[1]-v)<1e-11 and ulo-1e-11<=q[0]<=uhi+1e-11)
    chains={0:root_chain(vlo),1:root_chain(vhi)}
    # Split each actual cut rim at the union of both longitudinal partitions.
    # This changes no original coordinate and avoids a hanging cap/return node.
    us=sorted({u for c in chains.values() for u,v in c})
    def split(a,b,v,t):
        faces=[fi for fi,tr in enumerate(r['triangles']) if a in tr and b in tr]
        if len(faces)!=1:raise ValueError(('Cap rim incidence',a,b,faces))
        fi=faces[0];tr=r['triangles'][fi]
        if r['domains'][fi]=='retained':r['domains'][fi]='retained_fragment'
        for j in range(3):
            if {tr[j],tr[(j+1)%3]}=={a,b}:break
        aa,bb,cc=tr[j],tr[(j+1)%3],tr[(j+2)%3];w=t if aa==a else 1-t
        n0,n1,n2=[r['normal_corner_targets'][fi][k] for k in (j,(j+1)%3,(j+2)%3)]
        nu=interpolate(n0,n1,w);uv0={n:[vs[fi][k] for k in (j,(j+1)%3,(j+2)%3)] for n,vs in r['uv_corner_targets'].items()}
        uvnew={n:[mix(vs[0],vs[1],w),vs[1],vs[2]] for n,vs in uv0.items()}
        new_face(r,[v,bb,cc],r['domains'][fi],r['triangle_materials'][fi],r['owners'][fi],uvnew,[nu,n1,n2])
        r['triangles'][fi]=[aa,v,cc];r['normal_corner_targets'][fi]=[n0,nu,n2]
        for n,vs in r['uv_corner_targets'].items():vs[fi]=[uv0[n][0],uvnew[n][0],uv0[n][2]]
    # Propagate every exact cap partition node along its real indexed edge.
    # This also subdivides a finite adjacent wall edge where a cap cut ends;
    # no old vertex or surface is moved and the original field is interpolated.
    cap_edge_subdivisions=[]
    while True:
        found=None
        for tr in r['triangles']:
            for a,b in zip(tr,tr[1:]+tr[:1]):
                if a not in parameters or b not in parameters:continue
                A,B=parameters[a],parameters[b];D=sub(B,A);den=dot(D,D)
                if den==0:continue
                choices=[]
                for v,Q in parameters.items():
                    if v in (a,b):continue
                    t=dot(sub(Q,A),D)/den
                    if not 1e-10<t<1-1e-10:continue
                    if math.dist(Q,mix(A,B,t))>1e-12:continue
                    if math.dist(r['vertices'][v],mix(r['vertices'][a],r['vertices'][b],t))>2e-7:continue
                    choices.append((t,v))
                if choices:found=(a,b,*min(choices));break
            if found:break
        if not found:break
        a,b,t,v=found
        # At a partition seam both retained polygons can share the same edge.
        faces=[fi for fi,tr in enumerate(r['triangles']) if a in tr and b in tr]
        for fi in faces:
            tr=r['triangles'][fi]
            if r['domains'][fi]=='retained':r['domains'][fi]='retained_fragment'
            for j in range(3):
                if {tr[j],tr[(j+1)%3]}=={a,b}:break
            aa,bb,cc=tr[j],tr[(j+1)%3],tr[(j+2)%3];w=t if aa==a else 1-t
            n0,n1,n2=[r['normal_corner_targets'][fi][k] for k in (j,(j+1)%3,(j+2)%3)]
            nu=interpolate(n0,n1,w);uv0={n:[vs[fi][k] for k in (j,(j+1)%3,(j+2)%3)] for n,vs in r['uv_corner_targets'].items()}
            uvnew={n:[mix(vs[0],vs[1],w),vs[1],vs[2]] for n,vs in uv0.items()}
            new_face(r,[v,bb,cc],r['domains'][fi],r['triangle_materials'][fi],r['owners'][fi],uvnew,[nu,n1,n2])
            r['triangles'][fi]=[aa,v,cc];r['normal_corner_targets'][fi]=[n0,nu,n2]
            for n,vs in r['uv_corner_targets'].items():vs[fi]=[uv0[n][0],uvnew[n][0],uv0[n][2]]
        cap_edge_subdivisions.append({'source_edge':[a,b],'new_vertex':v,'fraction':t,'incident_faces':faces})
        if len(cap_edge_subdivisions)>2000:raise ValueError('Nonterminating finite cap incidence')
    for which in (0,1):
        chain=chains[which]
        for u in us:
            if any(abs(u-v)<1e-12 for v,i in chain):continue
            for j,((a,va),(b,vb)) in enumerate(zip(chain,chain[1:])):
                if a<u<b:
                    t=(u-a)/(b-a);vi=len(r['vertices']);r['vertices'].append(f32(mix(r['vertices'][va],r['vertices'][vb],t)))
                    parameters[vi]=mix(parameters[va],parameters[vb],t)
                    split(va,vb,vi,t);chain.insert(j+1,(u,vi));break
            else:raise ValueError(('Missing finite cap parameter',u,chain))
    fixed=len(r['triangles']);material=old['triangle_materials'][min(owned)]
    def add(t,tag):new_face(r,t,tag,material)
    # The real counterpart is an inset finite upper/forward gasket face.
    ph=6 if side=='R' else 5;band=(.25,.75);a,b=branch
    ids={a*8+ph:(0.,0.),a*8+(ph+1)%8:(0.,1.),b*8+ph:(1.,0.),b*8+(ph+1)%8:(1.,1.)}
    footv=[];footq=[];foott=[];footparents=[];fc={}
    cut_to_u={seal_limits[0]+u*(seal_limits[1]-seal_limits[0]):u for u in us}
    for fi,t in enumerate(seal['triangles']):
        if not set(t)<=set(ids):continue
        poly=[{'p':seal['vertices'][v],'q':list(ids[v]),'w':[float(j==k) for k in range(3)]} for j,v in enumerate(t)]
        poly=clip(clip(clip(clip(poly,0,min(seal_limits)),0,max(seal_limits),False),1,band[0]),1,band[1],False)
        if len(poly)<3:continue
        partitions=[poly]
        for u in us[1:-1]:
            bound=seal_limits[0]+u*(seal_limits[1]-seal_limits[0]);pieces=[]
            for polygon in partitions:
                ds=[q['q'][0]-bound for q in polygon]
                pieces.extend([clip(polygon,0,bound),clip(polygon,0,bound,False)] if min(ds)<0<max(ds) else [polygon])
            partitions=pieces
        for poly in partitions:
            local=[]
            for q in poly:
                u=cut_to_u.get(q['q'][0],(q['q'][0]-seal_limits[0])/(seal_limits[1]-seal_limits[0]));v=(q['q'][1]-band[0])/(band[1]-band[0])
                if side=='L':v=1-v
                key=(round(u,13),round(v,13))
                if key not in fc:fc[key]=len(footv);footv.append(f32(q['p']));footq.append([u,v])
                local.append(fc[key])
            for ix in ear_indices([q['p'] for q in poly]):
                foott.append([local[j] for j in ix]);footparents.append({'object':seal['name'],'face':fi,'weights':[poly[j]['w'] for j in ix]})
    if not foott:raise ValueError('Missing complete actual fixed-seal foot')
    base=len(r['vertices']);r['vertices'].extend(footv)
    footroot=sorted((q[0],base+i) for i,q in enumerate(footq) if abs(q[1]-1.)<1e-10)
    # v=1 is the outboard pressure edge for phase6; approach it from the body.
    def foot_value(u):
        for (a,va),(b,vb) in zip(footroot,footroot[1:]):
            if a-1e-12<=u<=b+1e-12:return mix(r['vertices'][va],r['vertices'][vb],(u-a)/(b-a))
        raise ValueError(('No finite gasket arrival section',u))
    root=chains[0];oproot=dict(chains[1]);shared_arrival=None;inner=[]
    if kind=='rail':
        for t in zipper(root,footroot):add(t,'formed_fixed_return');inner.append(len(r['triangles'])-1)
    else:
        capn=unit([sum(normal(old['vertices'],old['triangles'][fi])[k] for fi in owned) for k in range(3)])
        bend=[]
        for u,vi in root:
            bend.append((u,len(r['vertices'])));r['vertices'].append(f32([r['vertices'][vi][k]+capn[k]*.0035 for k in range(3)]))
        for t in zipper(root,bend)+zipper(bend,footroot):add(t,'formed_fixed_return');inner.append(len(r['triangles'])-1)
    footfaces=[]
    for t in foott:add([base+v for v in t],'actual_fixed_seal_contact');footfaces.append(len(r['triangles'])-1)
    open_orientation(r['vertices'],r['triangles'],fixed)
    offsetfaces=inner+footfaces;vids=sorted({v for fi in offsetfaces for v in r['triangles'][fi]})
    rootmap={v:oproot[u] for u,v in root};opposed={};stock=[]
    for vi in vids:
        inc=[fi for fi in offsetfaces if vi in r['triangles'][fi]]
        ns=[normal(r['vertices'],r['triangles'][fi]) for fi in inc];anchors=[r['vertices'][r['triangles'][fi][0]] for fi in inc]
        if vi in rootmap:
            opposed[vi]=rootmap[vi];q=r['vertices'][rootmap[vi]]
            gs=[-dot(n,sub(q,a)) for n,a in zip(ns,anchors)]
            proof={'minimum_incident_stock_m':min(gs),'maximum_incident_stock_m':max(gs),'exact_original_cap':True}
        else:
            q,proof=miter(r['vertices'][vi],ns,anchors,depth=.001201)
            opposed[vi]=len(r['vertices']);r['vertices'].append(q)
        stock.append({'inner_vertex':vi,'opposed_vertex':opposed[vi],'incident_faces':inc,**proof})
    arrival_faces=[fi for fi in inner if any(v in {q for _,q in footroot} for v in r['triangles'][fi])]
    wall_reference=unit([sum(normal(r['vertices'],r['triangles'][fi])[k] for fi in arrival_faces) for k in range(3)])
    foot_opposed,pressure=opposed_section(seal,footv,[[u,1-v] for u,v in footq],foott,footparents,shared_arrival,wall_reference,miter,[normal(r['vertices'],r['triangles'][fi]) for fi in arrival_faces])
    transported=pressure['transport']
    for i,q in enumerate(foot_opposed):r['vertices'][opposed[base+i]]=q
    for q in stock:
        vi=q['inner_vertex'];other=r['vertices'][opposed[vi]]
        gauges=[-dot(normal(r['vertices'],r['triangles'][fi]),sub(other,r['vertices'][r['triangles'][fi][0]])) for fi in q['incident_faces']]
        q.update(minimum_incident_stock_m=min(gauges),maximum_incident_stock_m=max(gauges),diagonal_m=math.dist(r['vertices'][vi],other))
    for fi in offsetfaces:add([opposed[v] for v in reversed(r['triangles'][fi])],'opposed_'+r['domains'][fi])
    # Close each actual free stock section, rather than projecting a complete
    # nonplanar 3D end contour into an arbitrary drawing plane.
    uses=defaultdict(list)
    for fi in offsetfaces:
        t=r['triangles'][fi]
        for a,b in zip(t,t[1:]+t[:1]):uses[min(a,b),max(a,b)].append((a,b))
    caps=[]
    def subdivided_edge(a,b):
        result=[a]
        if a in parameters and b in parameters:
            A,B=parameters[a],parameters[b];D=sub(B,A);den=dot(D,D)
            candidates=[]
            if den:
                for v,Q in parameters.items():
                    if v in (a,b):continue
                    t=dot(sub(Q,A),D)/den
                    if 1e-10<t<1-1e-10 and math.dist(Q,mix(A,B,t))<1e-12:
                        candidates.append((t,v))
            result.extend(v for t,v in sorted(candidates))
        return result
    for e,es in uses.items():
        if len(es)!=1 or all(v in rootmap for v in e):continue
        a,b=es[0];corners=[a,opposed[a],opposed[b],b];poly=[]
        for c,d in zip(corners,corners[1:]+corners[:1]):poly.extend(subdivided_edge(c,d))
        for ix in ear_indices([r['vertices'][v] for v in poly]):add([poly[j] for j in ix],'finite_fixed_return_end_cap')
        caps.append(poly)
    if observe:observe(r,{'stock':stock,'fixed':fixed,'root_chains':chains,'footroot':footroot,'opposed':opposed})
    orient(r['triangles'],fixed)
    for fi in range(fixed,len(r['triangles'])):r['normal_corner_targets'][fi]=[normal(r['vertices'],r['triangles'][fi])]*3
    if r['vertices'][:len(old['vertices'])]!=old['vertices']:raise ValueError('Original fixed support vertex moved')
    return r,{'pressure_transport':transported,'pressure_section':pressure,'shared_arrival_m':shared_arrival,'cap_edge_subdivisions':cap_edge_subdivisions,'owned_source_faces':sorted(owned),'removed_finite_root':construction,'root_parameters':{'u':[ulo,uhi],'v':[vlo,vhi]},
              'source_cap_vertices_exact':True,'new_stock':stock,'footprints':footparents,'foot_face_indices':footfaces,
              'opposed_faces_start':fixed+len(offsetfaces),'finite_end_caps':caps,'source_faces_retained_or_fragmented':fixed,
              'net_triangles':len(r['triangles'])-len(old['triangles']),
              'stock_min_m':min(q['minimum_incident_stock_m'] for q in stock),
              'stock_max_m':max(q['maximum_incident_stock_m'] for q in stock),
              'whole_assembly_fit_and_native_encoding_pending':True}


def receiving_wall_scope(rows, side, source_cap):
    old=rows['LOD0_RoofSideRail_'+side];seal=rows['LOD0_DoorApertureSeal_R'+side]
    ph=6 if side=='R' else 5;v=.75 if side=='R' else .25;sgn=1 if side=='R' else -1
    A=mix(seal['vertices'][15*8+ph],seal['vertices'][15*8+(ph+1)%8],v)
    B=mix(seal['vertices'][16*8+ph],seal['vertices'][16*8+(ph+1)%8],v)
    z0=mix(A,B,.18)[2]+.0015;z1=mix(A,B,.985)[2]+.0015
    faces=[]
    for fi,t in enumerate(old['triangles']):
        n=normal(old['vertices'],t)
        if -sgn*n[0]<.75:continue
        poly=[{'p':old['vertices'][i], 'q':[(old['vertices'][i][1]+1.16)/.505,
              (old['vertices'][i][2]-max(z0+(z1-z0)*(old['vertices'][i][1]+1.16)/.505,bottom_height(old,source_cap,old['vertices'][i][1])+.0005))/.001501], 'w':[float(j==k) for k in range(3)]} for j,i in enumerate(t)]
        for ax,b,up in ((0,0.,True),(0,1.,False),(1,0.,True),(1,1.,False)):poly=clip(poly,ax,b,up)
        if len(poly)<3:continue
        faces.append({'face':fi,'indices':t,'positions_m':[old['vertices'][v] for v in t],
                      'finite_removed_polygon_m':[q['p'] for q in poly],'material':old['materials'][old['triangle_materials'][fi]]})
    if not faces:raise ValueError('No actual concealed receiving wall')
    return {'object':old['name'],'free_lower_cap_faces':faces,'original_lower_cap_faces':source_cap}
