"""Pure current-geometry pressure section, extracted from frozen571. No IO or Blender."""

import math,itertools

import numpy as np

from .vectors import clip,mix,sub,cross,dot,unit,normal,f32

from .maths import plane_miter

def convex_boundary(points):
    ts=[];planes=[]
    for ids in itertools.combinations(range(len(points)),3):
        a,b,c=[points[i]for i in ids];nn=cross(sub(b,a),sub(c,a));ln=math.sqrt(dot(nn,nn))
        if ln<1e-15:continue
        n=[x/ln for x in nn];ds=[dot(n,sub(p,a))for p in points]
        if min(ds)<-1e-9 and max(ds)>1e-9:continue
        t=list(ids)
        if max(ds)>1e-9:n=[-x for x in n];t.reverse()
        ts.append(t);planes.append({'normal':n,'anchor':a})
    if not ts:raise ValueError('No finite proposed stock envelope')
    return {'vertices':points,'triangles':ts,'planes':planes}

def layout(rows,side,phase,band,arrival_override=None):
    name='LOD0_DoorApertureSeal_R'+side;se=rows[name];pts=[];records=[];cache={};cells=[];polys=[];edge_ideals=[]
    for branch,(a,b)in enumerate(((14,15),(15,16),(16,0))):
        ids={a*8+phase:(0.,0.),a*8+(phase+1)%8:(0.,1.),b*8+phase:(1.,0.),b*8+(phase+1)%8:(1.,1.)}
        fs=[i for i,t in enumerate(se['triangles'])if set(t)<=set(ids)]
        e=sub(mix(se['vertices'][b*8+phase],se['vertices'][b*8+(phase+1)%8],.5),mix(se['vertices'][a*8+phase],se['vertices'][a*8+(phase+1)%8],.5))
        wall_n=unit([0.,-e[2],e[1]])
        width=sub(se['vertices'][a*8+(phase+1)%8],se['vertices'][a*8+phase]);forward=dot(width,wall_n)>0
        root_v=band[0]if forward else band[1]
        for fi in fs:
            poly=[{'q':list(ids[v]),'p':se['vertices'][v],'w':[float(j==k)for k in range(3)]}for j,v in enumerate(se['triangles'][fi])]
            poly=clip(clip(poly,1,band[0]),1,band[1],False);pi=[]
            root_edge=sorted([q for q in poly if abs(q['q'][1]-root_v)<1e-12],key=lambda q:q['q'][0])
            if len(root_edge)==2:
                tangent=sub(root_edge[1]['p'],root_edge[0]['p']);wall_base=unit([0.,-tangent[2],tangent[1]])
                foot_n=normal(se['vertices'],se['triangles'][fi]);wall_n=unit([wall_base[k]+foot_n[k]for k in range(3)])
                edge_ideals.append({'facet':fi,'normal':wall_n,'tangent':tangent,'length_m':math.dist(root_edge[0]['p'],root_edge[1]['p'])})
            elif any(abs(q['q'][1]-root_v)<1e-12 for q in poly):
                # A polygon touching only the end of a root edge does not own
                # an arrival wall plane; the adjacent complete edge does.
                wall_n=None
            for q in poly:
                # Shared ring/facet coordinates are retained as actual source
                # parameters; duplicate numerical expressions must agree.
                key=(round(branch+q['q'][0],13),round(q['q'][1],13))
                if key not in cache:cache[key]=len(pts);pts.append(f32(q['p']));records.append([])
                vi=cache[key]
                if math.dist(pts[vi],q['p'])>2e-7:raise ValueError('Inconsistent finite native receiving parameter')
                pi.append(vi);records[vi].append({'facet':fi,'branch':branch,'is_wall_root':wall_n is not None and abs(q['q'][1]-root_v)<1e-12,'wall_normal':wall_n,'normal':normal(se['vertices'],se['triangles'][fi]),'anchor':se['vertices'][se['triangles'][fi][0]]})
            if len(pi)>=3:polys.append({'source_face':fi,'branch':branch,'vertices':pi,'pressure_polygon_m':[pts[v]for v in pi]})
    dx=.006*(1 if side=='R'else-1)
    A=np.array([[q['normal'][1],q['normal'][2]]for q in edge_ideals]);rhs=np.array([-q['normal'][0]*dx for q in edge_ideals]);weights=np.sqrt(np.array([q['length_m']for q in edge_ideals]))
    yz=np.linalg.lstsq(A*weights[:,None],rhs*weights,rcond=None)[0];arrival=arrival_override or[dx,float(yz[0]),float(yz[1])]
    if math.sqrt(dot(arrival,arrival))>.012:raise ValueError('Shared arrival span exceeds12mm finite proposal')
    wall_normals={q['facet']:unit(cross(arrival,q['tangent'])if side=='R'else cross(q['tangent'],arrival))for q in edge_ideals}
    for recs in records:
        for q in recs:
            if q['is_wall_root']:q['wall_normal']=wall_normals[q['facet']]
    outer=[];stock=[]
    for vi,p in enumerate(pts):
        ns=[q['normal']for q in records[vi]];anchors=[q['anchor']for q in records[vi]]
        roots=[q for q in records[vi]if q['is_wall_root']]
        ns += [q['wall_normal']for q in roots];anchors += [p for q in roots]
        q,m=plane_miter(p,[[-x for x in n]for n in ns],anchors,depth=.001201)
        outer.append(q);stock.append({'pressure_vertex':vi,'outer_vertex_m':q,'incident_receiving_faces':[r['facet']for r in records[vi]],'wall_root':bool(roots),**m})
    arrivals={};arrival_stock=[]
    for vi,p in enumerate(pts):
        rec=[q for q in records[vi]if q['is_wall_root']]
        if not rec:continue
        ns=[q['wall_normal']for q in rec];inner=f32([p[k]+arrival[k]for k in range(3)])
        outer_s,proof=plane_miter(inner,[[-x for x in n]for n in ns],[inner for n in ns],depth=.001201)
        arrivals[vi]={'inner':inner,'outer':outer_s,'wall_normals':ns,'from_pressure_m':math.dist(inner,p)};arrival_stock.append({'pressure_vertex':vi,**proof})
    for poly in polys:
        ids=poly['vertices'];ps=[pts[v]for v in ids]+[outer[v]for v in ids];h=convex_boundary(ps);h['name']='FiniteProposedFoot_'+side+'_'+str(poly['source_face']);cells.append({**poly,'kind':'complete_pressure_stock','hull':h})
        roots=[v for v in ids if v in arrivals and any(q['facet']==poly['source_face']and q['is_wall_root']for q in records[v])]
        if len(roots)==2:
            a,b=roots;ps=[pts[a],pts[b],outer[a],outer[b],arrivals[a]['inner'],arrivals[b]['inner'],arrivals[a]['outer'],arrivals[b]['outer']]
            h=convex_boundary(ps);h['name']='FiniteProposedArrival_'+side+'_'+str(poly['source_face']);cells.append({'source_face':poly['source_face'],'branch':poly['branch'],'kind':'complete_shared_arrival_stock','hull':h})
    return {'phase':phase,'band':band,'pressure_vertices_m':pts,'stock_vertices_m':outer,'stock':stock,'complete_cells':cells,
            'arrival_sections':arrivals,'arrival_stock':arrival_stock,'shared_arrival_translation_m':arrival,'ideal_edge_planes':edge_ideals,'wall_arrival':'One complete-chain, edge-length-weighted least-squares arrival vector is mirrored across the vehicle and has exactly4mm outboard X. The span is bounded by the actual lower Door receiver; the rejected6mm version intersected that receiver. Every actual wall plane is derived from its finite native root edge and that shared vector. This prevents the previous per-diagonal near-parallel intersection spur; all finite foot and arrival stock is measured. The remaining sash transition is separate and unaccepted.',
            'normal_stock_target_m':.001201,'native_assignment':False}
