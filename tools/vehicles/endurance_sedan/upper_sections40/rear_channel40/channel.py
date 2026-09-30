"""Complete paired sash section: fitted groove, shared arrival and Door floor.

The old inward chord and old five-sixths root are absent. The groove follows
the real rubber facets, including its lower turn. Its lower floor has distinct
inner and outer receiving edges. All points are private construction arrays.
"""
import copy, math
from .sections import zipper as section_zipper
from collections import defaultdict, deque
from .mesh import empty, initial, old_face, new_face, set_geometric_new_fields, ear_indices
from .pressure import layout
from .maths import closest_double
from .vectors import f32, mix, sub, dot, cross, unit, area, normal, clip, zipper, orient


def open_orientation(vertices, triangles, fixed):
    edges=defaultdict(list)
    for fi,t in enumerate(triangles):
        for a,b in zip(t,t[1:]+t[:1]):edges[min(a,b),max(a,b)].append((fi,a<b))
    states={i:False for i in range(fixed)};queue=deque(states)
    while queue:
        fi=queue.popleft()
        for a,b in zip(triangles[fi],triangles[fi][1:]+triangles[fi][:1]):
            uses=edges[min(a,b),max(a,b)]
            if len(uses)==1:continue
            if len(uses)!=2:raise ValueError(('Nonmanifold open sheet',a,b,uses))
            oi,sg=next(p for p in uses if p[0]!=fi);flip=states[fi]^((a<b)==sg)
            if oi in states:
                if states[oi]!=flip:raise ValueError(('Inconsistent open sheet',fi,oi))
            else:states[oi]=flip;queue.append(oi)
    if len(states)!=len(triangles):raise ValueError(('Disconnected new inner sheet',len(states),len(triangles)))
    for fi,flip in states.items():
        if flip:triangles[fi].reverse()
    return states


def lower_floor(door, side, y0, y1):
    """Whole actual finite Door footprint, with its real diagonal subdivisions."""
    sgn=1 if side=='R'else-1;xs=tuple(f32([.8215,.856]));verts=[];params=[];triangles=[];parents=[];cache={}
    def vertex(v):
        key=tuple(f32(v['p']))
        if key not in cache:
            cache[key]=len(verts);verts.append(list(key));params.append(v['q'][:])
        return cache[key]
    for fi,t in enumerate(door['triangles']):
        if normal(door['vertices'],t)[2]<.97:continue
        ps=[door['vertices'][v]for v in t]
        if min(p[2]for p in ps)<1.011:continue
        poly=[{'p':p,'q':[(p[1]-y0)/(y1-y0),(sgn*p[0]-xs[0])/(xs[1]-xs[0])],
               'w':[float(j==k)for k in range(3)]}for j,p in enumerate(ps)]
        for ax,b,up in ((0,0.,True),(0,1.,False),(1,0.,True),(1,1.,False)):
            poly=clip(poly,ax,b,up)
        if len(poly)<3:continue
        ids=[vertex(v)for v in poly]
        for ix in ear_indices([v['p']for v in poly]):
            triangles.append([ids[i]for i in ix]);parents.append({'object':door['name'],'face':fi,'weights':[poly[i]['w']for i in ix]})
    coverage=sum(abs(cross([params[t[1]][k]-params[t[0]][k]for k in (0,1)]+[0.],
                          [params[t[2]][k]-params[t[0]][k]for k in (0,1)]+[0.])[2])/2 for t in triangles)
    if abs(coverage-1.)>1e-7:raise ValueError(('Incomplete actual Door floor',side,coverage))
    return {'vertices':verts,'parameters':params,'triangles':triangles,'parents':parents,'normalized_complete_area':coverage,
            'absX_m':xs,'Y_m':[y0,y1]}


def build(rows, side, scoped, miter, ideal=None, observe=None):
    name='LOD0_DoorFrame_R'+side;old=rows[name];rubber=rows['LOD0_DoorGlassSeal_R'+side]
    gasket=rows['LOD0_DoorApertureSeal_R'+side];door=rows['LOD0_Door_R'+side]
    r=empty(old,ideal);owned={q['face']for q in scoped['sash']['complete_inward_parent_faces']}
    for fi in range(len(old['triangles'])):
        if fi not in owned:old_face(r,old,fi,ideal)
    fixed=len(r['triangles']);phase=lambda j:j if side=='R'else(4-j)%8
    rings={};rubmap={}
    for j in (7,6,5,4,3):
        rings[j]=[]
        for i in range(25):
            vi=len(r['vertices']);r['vertices'].append(rubber['vertices'][8*i+phase(j)][:]);rings[j].append(vi);rubmap[8*i+phase(j)]=vi
    def add(t,kind,material=0):new_face(r,t,kind,material)
    root0=[i*6 for i in range(25)];root5=[i*6+5 for i in range(25)]
    for i in range(25):
        j=(i+1)%25;add([root0[i],rings[7][i],rings[7][j]],'finite_outer_bead_edge_cap');add([root0[i],rings[7][j],root0[j]],'finite_outer_bead_edge_cap')
    groove_faces=[];stock_groove=[]
    for fi,t in enumerate(rubber['triangles']):
        if all(v in rubmap for v in t):
            newt=[rubmap[v]for v in t];add(newt,'actual_gasket_seat');groove_faces.append(len(r['triangles'])-1)
            if all((v%8 if side=='R'else(4-v%8)%8)<=5 for v in t):stock_groove.append(len(r['triangles'])-1)
    # A single monotone physical correspondence is used on each real gasket
    # branch. No per-diagonal averaged offset or old one-sixth bead fragment.
    pp=[];pq=[];pt=[];pm=[];cache={};root_indices={};polys=[];knots_all=[]
    ph = 0 if side == 'R' else 3; band=(.25,.95)if side=='R'else(.05,.75)
    def add_p(q,p):
        u=q[0]%25;key=(round(u,12),round(q[1],12))
        if key not in cache:cache[key]=len(pp);pp.append(f32(p));pq.append([u,q[1]])
        return cache[key]
    def turn_station(ring, candidates):
        center = mix(gasket['vertices'][ring*8+ph], gasket['vertices'][ring*8+(ph+1)%8], .5)
        return float(min(candidates, key=lambda u: sum((r['vertices'][rings[3][u]][k]-center[k])**2 for k in (1,2))))
    rear_turn = turn_station(15, range(10,15))
    fore_turn = turn_station(16, range(20,25))
    for a,b,ua,ub in ((14,15,7.,rear_turn),(15,16,rear_turn,fore_turn),(16,0,fore_turn,28.)):
        ids={a*8+ph:(0.,0.),a*8+(ph+1)%8:(0.,1.),b*8+ph:(1.,0.),b*8+(ph+1)%8:(1.,1.)}
        fs=[fi for fi,t in enumerate(gasket['triangles'])if set(t)<=set(ids)]
        c0=mix(gasket['vertices'][a*8+ph],gasket['vertices'][a*8+(ph+1)%8],.5)
        c1=mix(gasket['vertices'][b*8+ph],gasket['vertices'][b*8+(ph+1)%8],.5)
        direction=sub(c1,c0);direction[0]=0.;den=dot(direction,direction)
        knots=[]
        for u in range(int(ua),int(ub)+1):
            p=r['vertices'][rings[3][u%25]];w=max(0.,min(1.,dot(sub(p,c0),direction)/den))
            if u==ua:w=0.
            if u==ub:w=1.
            knots.append((w,float(u)))
        if any(y[0]<=x[0]for x,y in zip(knots,knots[1:])):raise ValueError(('Nonmonotone actual branch correspondence',a,b,knots))
        knots_all.append({'branch':[a,b],'knots':knots})
        # The root is the band edge nearest the actual shared arrival571.
        root_fraction=band[1] if side == 'R' else band[0]
        for fi in fs:
            native=[{'q':list(ids[v]),'p':gasket['vertices'][v],'w':[float(j==k)for k in range(3)]}for j,v in enumerate(gasket['triangles'][fi])]
            for (sa,ra),(sb,rb)in zip(knots,knots[1:]):
                poly=clip(clip(clip(clip(native,0,sa),0,sb,False),1,band[0]),1,band[1],False)
                if len(poly)<3:continue
                for v in poly:
                    vv=(v['q'][1]-root_fraction)/(band[1]-band[0])*(-1 if side == 'R' else 1)
                    v['q']=[ra+(rb-ra)*(v['q'][0]-sa)/(sb-sa),vv]
                ids2=[add_p(v['q'],v['p'])for v in poly]
                for ix in ear_indices([v['p']for v in poly]):
                    pt.append([ids2[k]for k in ix]);pm.append({'kind':'fixed_gasket_pressure','object':gasket['name'],'face':fi,'weights':[poly[k]['w']for k in ix]})
    # Actual full lower floor lies inside the proven receiving-envelope band.
    y0=rubber['vertices'][4*8+phase(3)][1];y1=rubber['vertices'][5*8+phase(3)][1]
    floor=lower_floor(door,side,y0,y1); floor_map={};floor_contact={}
    for i,(p,q)in enumerate(zip(floor['vertices'],floor['parameters'])):
        # v=0 is the outer edge adjacent to the sash; v=1 is the inboard edge.
        u=4.+q[0];v=1.-q[1];top=f32([p[0],p[1],p[2]+.00135]);j=add_p([u,v],top);floor_map[i]=j;floor_contact[j]=p
    native_collapsed_floor_faces = []
    for fi, (t, p) in enumerate(zip(floor['triangles'], floor['parents'])):
        nt = [floor_map[v] for v in t]
        if len(set(nt)) < 3:
            native_collapsed_floor_faces.append({'analysis_face': fi, 'source': p, 'exact_native_indices': nt})
            continue
        pt.append(nt); pm.append({'kind':'Door_floor', **p})
    base=len(r['vertices']);r['vertices'].extend(pp)
    p0=sorted((q[0],i)for i,q in enumerate(pq)if abs(q[1])<1e-10)
    arrival={};arr=[.004 if side=='R'else-.004,-.0022513266988647743,-.0052703639486432596]
    for u,i in p0:
        if i in floor_contact:arrival[i]=base+i
        else:
            arrival[i]=len(r['vertices']);r['vertices'].append(f32([pp[i][k]+arr[k]for k in range(3)]))
    # True free lower-end boundaries bridge the two separate receiving lands.
    # Intermediate frame station6 is inserted on the single common rear chord.
    ac={round(u,12):arrival[i]for u,i in p0}
    for a,b in ((3.,4.),(5.,7.)):
        for u in range(int(a)+1,int(b)):
            ac[float(u)]=len(r['vertices']);r['vertices'].append(f32(mix(r['vertices'][ac[a]],r['vertices'][ac[b]],(u-a)/(b-a))))
    aloop=sorted(ac.items());aloop.append((25.,aloop[0][1]))
    # Make the complete inner wall first; source edge positions are exact and
    # only authored groove edges receive additional diagonal subdivisions.
    # The complete lower wall uses the same longitudinal stations as the
    # actual curved Door receiver. Split the shared rubber-seat edge too;
    # no long corner fan is allowed across those finite section changes.
    extra=[]
    for u,_ in aloop:
        if 4.+1e-10<u<5.-1e-10:
            vi=len(r['vertices']);r['vertices'].append(f32(mix(r['vertices'][rings[3][4]],r['vertices'][rings[3][5]],u-4.)))
            extra.append((u,vi))
    lower_chain=[rings[3][4]]+[v for _,v in extra]+[rings[3][5]]
    old_stock=set(stock_groove)
    for fi in list(groove_faces):
        tri=r['triangles'][fi]
        if not {rings[3][4],rings[3][5]}<=set(tri):continue
        a,b=rings[3][4],rings[3][5]
        forward=any(x==a and y==b for x,y in zip(tri,tri[1:]+tri[:1]))
        chain=lower_chain if forward else list(reversed(lower_chain))
        c=next(v for v in tri if v not in (a,b));pieces=[[x,y,c] for x,y in zip(chain,chain[1:])]
        r['triangles'][fi]=pieces[0]
        for t in pieces[1:]:
            add(t,'actual_gasket_seat');groove_faces.append(len(r['triangles'])-1)
            if fi in old_stock:stock_groove.append(len(r['triangles'])-1)
    gloop=sorted([(float(i),rings[3][i])for i in range(25)]+extra)+[(25.,rings[3][0])]
    inner=[]
    for t in section_zipper(r['vertices'],gloop,aloop):add(t,'formed_inner_sash');inner.append(len(r['triangles'])-1)
    arrival_faces=[]
    pe=defaultdict(list)
    for t in pt:
        for a,b in zip(t,t[1:]+t[:1]):pe[min(a,b),max(a,b)].append((a,b))
    for (u,a),(v,b)in zip(p0,p0[1:]+[(p0[0][0]+25,p0[0][1])]):
        if (min(a,b),max(a,b))not in pe:continue
        if a in floor_contact and b in floor_contact:continue
        for t in ([base+a,arrival[a],arrival[b]],[base+a,arrival[b],base+b]):add(t,'shared_weather_arrival');arrival_faces.append(len(r['triangles'])-1)
    footfaces=[]
    for t,m in zip(pt,pm):add([base+i for i in t],m['kind']);footfaces.append(len(r['triangles'])-1)
    states=open_orientation(r['vertices'],r['triangles'],fixed)
    set_geometric_new_fields(r,fixed)
    if observe:observe('inner',r,{'gasket':groove_faces,'inner':inner,'arrival':arrival_faces,'feet':footfaces})
    # The actual complete incident planes determine one common opposed point.
    # This includes the rubber-seat turn, unlike the old flat inward chord.
    offsetfaces=stock_groove+inner+arrival_faces+footfaces
    vids=sorted({v for fi in offsetfaces for v in r['triangles'][fi]});opposed={};stock=[]
    for vi in vids:
        inc=[fi for fi in offsetfaces if vi in r['triangles'][fi]]
        ns=[normal(r['vertices'],r['triangles'][fi])for fi in inc]
        anchors=[r['vertices'][r['triangles'][fi][0]]for fi in inc]
        local=vi-base
        if local in floor_contact:
            q=f32([floor_contact[local][0],floor_contact[local][1],floor_contact[local][2]+.0000003]);gauges=[-dot(n,sub(q,a))for n,a in zip(ns,anchors)]
            proof={'minimum_incident_stock_m':min(gauges),'maximum_incident_stock_m':max(gauges),'diagonal_m':math.dist(q,r['vertices'][vi]),'actual_Door_seating_target_m':.0000003,'finite_Door_contact_guard_m':.000001}
        else:q,proof=miter(r['vertices'][vi],ns,anchors,depth=.001201)
        opposed[vi]=len(r['vertices']);r['vertices'].append(q)
        stock.append({'inner_vertex':vi,'incident_faces':inc,**proof})
    # One extrusion vector across the complete straight lower groove edge.
    # All lower-wall section normals constrain it together; independent
    # offsets at closely spaced receiver diagonals would fold the old groove.
    lowerids=[rings[3][4]]+[v for _,v in extra]+[rings[3][5]]
    lowerfaces=sorted({fi for vi in lowerids for fi in offsetfaces if vi in r['triangles'][fi]})
    lowernormals=[normal(r['vertices'],r['triangles'][fi]) for fi in lowerfaces]
    shift,lowerproof=miter([0.,0.,0.],lowernormals,[[0.,0.,0.]]*len(lowernormals),depth=.001201)
    for vi in lowerids:r['vertices'][opposed[vi]]=f32([r['vertices'][vi][k]+shift[k] for k in range(3)])
    # Transport the complete actual pressure-foot section from source facets.
    # Interior source diagonals never receive independent offset constructions.
    pressure=layout(rows,side,ph,band,arr)
    cells=[q for q in pressure['complete_cells'] if q['kind']=='complete_pressure_stock']
    transported=[]
    def bary(p,a,b,c):
        u,v,w=sub(b,a),sub(c,a),sub(p,a);uu,uv,vv,wu,wv=dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
        den=uu*vv-uv*uv;y=(wu*vv-wv*uv)/den;z=(wv*uu-wu*uv)/den
        return [1-y-z,y,z]
    for i,p in enumerate(pp):
        if i in floor_contact:continue
        choices=[]
        for cell in cells:
            ids=cell['vertices'];poly=[pressure['pressure_vertices_m'][v] for v in ids]
            for tri in ear_indices(poly):
                ps=[poly[v] for v in tri];q=closest_double(p,*ps)
                choices.append((math.dist(p,q),[ids[v] for v in tri],bary(q,*ps),cell['source_face']))
        d,ids,w,parent=min(choices,key=lambda x:x[0])
        if d>2e-7:raise ValueError(('Actual pressure stock source correspondence',side,i,d))
        q=f32([sum(w[j]*pressure['stock_vertices_m'][ids[j]][k] for j in range(3)) for k in range(3)])
        r['vertices'][opposed[base+i]]=q
        transported.append({'inner_vertex':base+i,'source_face':parent,'source_indices':ids,'weights':w,'source_distance_m':d})
    for q in stock:
        vi=q['inner_vertex'];other=r['vertices'][opposed[vi]]
        gauges=[-dot(normal(r['vertices'],r['triangles'][fi]),sub(other,r['vertices'][r['triangles'][fi][0]])) for fi in q['incident_faces']]
        q.update(minimum_incident_stock_m=min(gauges),maximum_incident_stock_m=max(gauges),diagonal_m=math.dist(r['vertices'][vi],other))
    # Join the original unmodified exposed bead to the complete new opposed
    # groove at phase5. It is a finite edge closure, not a gauge sample.
    for i in range(25):
        j=(i+1)%25;a,b=root5[i],root5[j];c,d=opposed[rings[5][i]],opposed[rings[5][j]]
        add([a,b,d],'bead_stock_end_cap');add([a,d,c],'bead_stock_end_cap')
    for fi in offsetfaces:add([opposed[v]for v in reversed(r['triangles'][fi])],'opposed_'+r['domains'][fi])
    # Close every true free sheet boundary once. Root phase5 is joined above.
    edges=defaultdict(list)
    for fi in offsetfaces:
        t=r['triangles'][fi]
        for a,b in zip(t,t[1:]+t[:1]):edges[min(a,b),max(a,b)].append((a,b))
    ring5=set(rings[5]);caps=[]
    for e,uses in edges.items():
        if len(uses)!=1 or set(e)<=ring5:continue
        a,b=uses[0];add([a,opposed[a],opposed[b]],'finite_free_section_cap');add([a,opposed[b],b],'finite_free_section_cap');caps.append([a,b])
    flips=orient(r['triangles'],fixed);set_geometric_new_fields(r,fixed)
    assert r['vertices'][:len(old['vertices'])]==old['vertices']
    return r,{'retained_source_faces':[i for i in range(300)if i not in owned], 'source_mask':sorted(owned),
               'stock':stock,'pressure_section':pressure,'pressure_transport':transported,'footprints':pm,'floor':floor,'gasket_correspondence':knots_all,
               'exact_zero_native_floor_faces':native_collapsed_floor_faces,'actual_shared_arrival_m':arr,'free_caps':caps,'native_orientation_flips':flips,
               'net_triangles':len(r['triangles'])-len(old['triangles']),
               'stock_min_m':min(p['minimum_incident_stock_m']for p in stock),'stock_max_m':max(p['maximum_incident_stock_m']for p in stock),
               'whole_assembly_static_and_field_checks_pending':True}
