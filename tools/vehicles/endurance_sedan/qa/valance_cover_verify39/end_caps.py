"""Current-input finite verification; source bodies bound in extraction01."""

from collections import Counter,defaultdict
import math

def classify(row,pairs,ex,distance):
    p=[ex.vector(v) for v in row['vertices']];tt=row['triangles'];roles=row['triangle_authored_roles'];domains=row['triangle_domains'];upper=ex.F(float(.2750000059604645));limit=ex.F('.001199')
    edge_uses=defaultdict(list);oriented=Counter();links=defaultdict(list);volume=ex.F(0)
    for i,t in enumerate(tt):
        if len(t)!=3 or len(set(t))!=3:raise ValueError('Invalid native stock face')
        a,b,c=[p[v] for v in t];n=ex.cross(ex.sub(b,a),ex.sub(c,a))
        if not any(n):raise ValueError('Degenerate native stock face')
        volume+=ex.dot(a,ex.cross(b,c))/6
        for k in range(3):
            a,b=t[k],t[(k+1)%3];edge_uses[tuple(sorted((a,b)))].append(i);oriented[a,b]+=1;links[t[k]].append((t[(k+1)%3],t[(k+2)%3]))
    if volume<=0 or any(len(v)!=2 for v in edge_uses.values()) or any(c!=1 or oriented[b,a]!=1 for (a,b),c in oriented.items()):raise ValueError('Stock is not a closed outward oriented surface')
    for v,pairs2 in links.items():
        graph=defaultdict(set)
        for a,b in pairs2:graph[a].add(b);graph[b].add(a)
        if any(len(ns)!=2 for ns in graph.values()):raise ValueError('Stock vertex link is not a simple cycle')
        seen=set();todo=[next(iter(graph))]
        while todo:
            x=todo.pop()
            if x in seen:continue
            seen.add(x);todo.extend(graph[x]-seen)
        if len(seen)!=len(graph):raise ValueError('Pinched disconnected stock vertex link')
    def adjacent(i):
        t=tt[i];return {j for a,b in zip(t,t[1:]+t[:1]) for j in edge_uses[tuple(sorted((a,b)))]}-{i}
    caps={i for i,r in enumerate(roles) if r=='finite_upper_stock_cap'}
    if len(caps)!=5:raise ValueError('Complete actual five-facet upper end closure is missing')
    components=[];pending=set(caps)
    while pending:
        group={pending.pop()};todo=list(group)
        while todo:
            i=todo.pop();new=adjacent(i)&pending;pending-=new;group|=new;todo.extend(new)
        components.append(sorted(group))
    if sorted(map(len,components))!=[2,3]:raise ValueError('Upper cap is not the two actual complete end patches')
    def boundary(ids):
        uses=Counter((a,b) for i in ids for a,b in zip(tt[i],tt[i][1:]+tt[i][:1]))
        if any(c!=1 for c in uses.values()):raise ValueError('Duplicate oriented finite cap edge')
        rim=[(a,b) for a,b in uses if (b,a) not in uses]
        following={a:b for a,b in rim}
        if len(following)!=len(rim) or set(following)!=set(following.values()):raise ValueError('Finite cap does not have one oriented boundary')
        loop=[min(following)];x=following[loop[0]]
        while x!=loop[0]:
            if x in loop:raise ValueError('Finite cap boundary repeats');
            loop.append(x);x=following[x]
        if len(loop)!=len(rim):raise ValueError('Disconnected finite cap boundary')
        return loop
    def rectangle(ids,parameters,normal_width_squared,label):
        if normal_width_squared<limit*limit:raise ValueError('Finite end spans less than1.2mm stock after existing1um guard')
        loop=boundary(ids);used={v for i in ids for v in tt[i]}
        if used!=set(parameters):raise ValueError('Incomplete finite cap parametrization')
        if any(not(0<=u<=1 and 0<=v<=1) for u,v in parameters.values()):raise ValueError('End surface leaves complete stock rectangle')
        corners={(ex.F(0),ex.F(0)),(ex.F(1),ex.F(0)),(ex.F(1),ex.F(1)),(ex.F(0),ex.F(1))}
        if not corners.issubset(set(parameters.values())):raise ValueError('Missing full end-stock corner')
        for a,b in zip(loop,loop[1:]+loop[:1]):
            x,y=parameters[a],parameters[b]
            if not any(x[k]==y[k] and x[k] in (0,1) for k in (0,1)):raise ValueError('Cap boundary is not the entire rectangle rim')
        signs=[];areas=[]
        for i in ids:
            a,b,c=[parameters[v] for v in tt[i]];area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);areas.append(area);signs.append(area>0)
            if not area:raise ValueError('Degenerate positive-stock cap cell')
        if len(set(signs))!=1 or abs(sum(areas))!=2:raise ValueError('Actual complete cap triangles do not tile the unit stock rectangle once')
        return dict(kind=label,faces=ids,oriented_boundary=loop,parameters={v:[str(q) for q in parameters[v]] for v in sorted(parameters)},exact_total_twice_area=str(sum(areas)),normal_width_squared=str(normal_width_squared),normal_stock_width_m=math.sqrt(float(normal_width_squared)),proof='The actual oriented facets map one-to-one to the complete unit rectangle, with no boundary omissions or flipped/overlapping parameter cells. The stock coordinate is affine on every triangle. Every full transverse parameter line spans the measured normal separation of the two actual receiving sheet edges; end caps are finite cut surfaces, not opposing sheets.')
    cap_records=[];side_info={}
    for group in components:
        vertices={v for i in group for v in tt[i]};sign=1 if sum(p[v][0] for v in vertices)>0 else -1
        x_outer=max(sign*p[v][0] for v in vertices);x_inner=min(sign*p[v][0] for v in vertices);width=x_outer-x_inner
        outer=sorted([v for v in vertices if sign*p[v][0]==x_outer],key=lambda v:p[v][1]);inner=[v for v in vertices if sign*p[v][0]==x_inner]
        if len(outer)!=2 or len(inner)!=2:raise ValueError('Upper cap does not join two complete side-stock receiving edges')
        if any(p[v][2]!=upper for v in outer) or sum(p[v][2]==upper for v in inner)!=1:raise ValueError('Fixed finite upper section was changed')
        params={}
        for v in vertices:
            u=(x_outer-sign*p[v][0])/width
            if v in outer:along=ex.F(outer.index(v))
            elif p[v][2]==upper:along=ex.F(0)
            elif v in inner:along=ex.F(1)
            else:raise ValueError('Undeclared interior upper-cap knot')
            params[v]=(u,along)
        proof=rectangle(group,params,width*width,'finite_side_stock_end');cap_records.append(proof)
        upper_edges={tuple(sorted((a,b))) for a,b in zip(proof['oriented_boundary'],proof['oriented_boundary'][1:]+proof['oriented_boundary'][:1]) if params[a][1]==params[b][1]==0}
        outer_edge=tuple(sorted(outer));side_faces={i for i,d in enumerate(domains) if d=='terminal_outer' and all(sign*p[v][0]==x_outer for v in tt[i])}
        reachable=set(edge_uses[outer_edge])&side_faces;todo=list(reachable)
        while todo:
            i=todo.pop();new=adjacent(i)&side_faces-reachable;reachable|=new;todo.extend(new)
        side_info[sign]=dict(group=group,proof=proof,upper_edges=upper_edges,side_faces=reachable,parameters=params)
    def projected_area(a,b):
        n=ex.cross(ex.sub(a[1],a[0]),ex.sub(a[2],a[0]));poly=list(b)
        for v,w in zip(a,a[1:]+a[:1]):
            m=ex.cross(n,ex.sub(w,v));poly,_=ex.split(poly,m,ex.dot(m,v))
            if not poly:break
        area=sum(ex.dot(n,ex.cross(v,w)) for v,w in zip(poly,poly[1:]+poly[:1])) if poly else ex.F(0)
        return area,poly
    result=[];return_caps={}
    for pair in pairs:
        oi,ii=pair;outer=[p[v] for v in tt[oi]];inner=[p[v] for v in tt[ii]];sign=1 if sum(v[0] for v in outer)>0 else -1;info=side_info[sign]
        if domains[oi]!='terminal_outer' or domains[ii]!='inner_preserved_fragment':raise ValueError('Short relation is outside declared sheet-end domains')
        if not(max(v[2] for v in outer)==upper and min(v[2] for v in outer)<upper and min(v[2] for v in inner)==upper and max(v[2] for v in inner)>upper):raise ValueError('Complete actual old/new end facets are not separated at fixed upper section')
        ie={tuple(sorted((a,b))) for a,b in zip(tt[ii],tt[ii][1:]+tt[ii][:1])};attached=ie&info['upper_edges']
        if len(attached)!=1:raise ValueError('Old inner face does not use an entire actual finite upper-cap receiving edge')
        area,poly=projected_area(outer,inner)
        if area:raise ValueError('Short actual inner facet has positive opposing normal footprint')
        mode='side_end'
        if oi not in info['side_faces']:
            mode='formed_return_end';normal=ex.cross(ex.sub(outer[1],outer[0]),ex.sub(outer[2],outer[0]));nn=ex.dot(normal,normal)
            if normal[0]!=0:raise ValueError('Unclassified short face lacks actual side/return construction')
            touches={j for ci in info['group'] for j in adjacent(ci) if domains[j]=='terminal_rim'}
            matching=[]
            for j in touches:
                q=[p[v] for v in tt[j]];s=[ex.dot(normal,v) for v in q];outside=ex.dot(normal,outer[0])
                if outside not in s or len(set(s))!=2:continue
                other=next(x for x in s if x!=outside)
                if (outside-other)**2/nn<limit*limit:continue
                matching.append((j,outside,other,normal,nn))
            if len(matching)!=1:raise ValueError('Return does not have one finite adjoining normal-stock end cap')
            seed,s0,s1,n,nn=matching[0];t=[p[v] for v in tt[seed]];m=ex.cross(ex.sub(t[1],t[0]),ex.sub(t[2],t[0]));d=ex.dot(m,t[0]);group={seed};todo=[seed]
            while todo:
                j=todo.pop();new={k for k in adjacent(j) if k not in group and domains[k]=='terminal_rim' and all(ex.dot(m,p[v])==d for v in tt[k])};group|=new;todo.extend(new)
            vertices={v for j in group for v in tt[j]};layers={0:[],1:[]};parameters={}
            for v in vertices:
                u=(s0-ex.dot(n,p[v]))/(s0-s1)
                if u not in (0,1):raise ValueError('Return cap has an undeclared interior stock layer')
                layers[int(u)].append(v)
            ends={k:(min(p[v][0] for v in values),max(p[v][0] for v in values)) for k,values in layers.items()}
            if any(a==b for a,b in ends.values()):raise ValueError('Collapsed finite return receiving edge')
            for v in vertices:
                u=(s0-ex.dot(n,p[v]))/(s0-s1);a,b=ends[int(u)];parameters[v]=(u,(p[v][0]-a)/(b-a))
            proof=rectangle(sorted(group),parameters,(s0-s1)**2/nn,'finite_return_stock_end');return_caps[tuple(sorted(group))]=proof
        measure=distance([[float(x) for x in v] for v in outer],[[float(x) for x in v] for v in inner])
        if ex.F(measure['exact_distance_squared_m2'])>=limit*limit:raise ValueError('The supplied pair is not an actual short end relation')
        result.append(dict(outer_face=oi,inner_face=ii,classification=mode,actual_minimum=measure,common_upper_plane_z=str(upper),complete_opposing_projected_area_exact=str(area),projected_boundary_fragment=[[str(x) for x in v] for v in poly],inner_receiving_edge=list(next(iter(attached))),side_end_faces=info['group'],shared_vertices=sorted(set(tt[oi])&set(tt[ii])),complete_closed_vertex_links=True))
    if len(result)!=10:raise ValueError('Actual complete short-end inventory changed')
    return dict(status='passed_finite_stock_end_classification',pairs=result,side_caps=cap_records,return_caps=list(return_caps.values()),whole_mesh_closed_oriented=True,whole_vertex_link_cycles=len(links),positive_signed_volume_m3=float(volume),guard_m=.001199,limits='This classifies only the ten actual finite cut-end relations in an independently exact-self-passing closed solid. It is not a whole-pair clearance exemption and does not turn a cap into an opposing sheet. All other whole opposed-sheet distances, finite exterior/inner footprint ownership, receiver/rest/motion and render review remain separately bound.')
