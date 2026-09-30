"""Finite actual-carrier lamp transition. Plain-array preparation, no file IO.

The caller supplies its own actual pre-void source capture, original parameter
capture, front recorder packet and verified complete-sheet ownership plan.
These observations select/measure the actual delivered mesh; no archived mesh
is installed. The current native normals are the retained boundary first jets.
"""
from collections import defaultdict
import math
import numpy as np

NAME='LOD0_FrontBumper'
T_BOUNDS=(5.,7.)
Y_REAR=2.09125
GUARD=1e-6
NORMAL=.025

def unit(v):
    a=np.asarray(v,dtype=float);length=np.linalg.norm(a)
    if not np.isfinite(length) or length<=0:raise ValueError('Invalid finite surface direction')
    return a/length

def angle(a,b):return math.degrees(math.atan2(float(np.linalg.norm(np.cross(a,b))),float(np.dot(a,b))))

def domain(actual, original, prefix, packet, sheet_plan):
    """Require actual native and complete original fragment ownership first."""
    if actual['object']!=NAME or sheet_plan['object']!=NAME:raise ValueError('Wrong lamp sheet semantic')
    core=packet['core'];initial=core['initial'];final=core['final']
    if (actual['points']!=final['physical']['vertices'] or actual['triangles']!=final['triangles']
            or sheet_plan['physical']['positions']!=actual['points']):
        raise ValueError('Current geometry differs from actual construction reference')
    if tuple(s['stage'] for s in core['stages'])!=('bend','planar','lamp','rear_planar','inlet'):
        raise ValueError('Missing actual front construction stage')
    previous=initial
    for stage in core['stages']:
        if stage['before']!=previous:raise ValueError('Unobserved front stage boundary')
        previous=stage['after']
    if previous!=final:raise ValueError('Missing actual final carrier')
    if sheet_plan['evidence']['source_packet_sha256']!=packet['sha256']:
        raise ValueError('Complete original ownership belongs to a different carrier')
    params={}
    for row in prefix['retained_targets']:
        key=tuple(row['point']);value=row['parameters']
        if key in params and math.dist(params[key],value)>1e-7:raise ValueError('Ambiguous actual parameter point')
        params[key]=value
    for sf in prefix['source_faces']:
        for point,value in zip(sf['points'],sf['parameters']):
            if value is not None and tuple(point) not in params:params[tuple(point)]=value
    initial_params={};owned=set();ownership=[]
    for face in sheet_plan['evidence']['initial_authored_domains']['complete_original_ownership']:
        for row in face['complete_triangles']:
            ti=row['triangle'];tri=initial['triangles'][ti]
            if row['points']!=[initial['physical']['vertices'][v] for v in tri['vertices']]:raise ValueError('False actual original fragment')
            if (max(p[2] for p in row['points'])<.70 or max(p[1] for p in row['points'])<2.
                    or not (all(p[0]>.6 for p in row['points']) or all(p[0]<-.6 for p in row['points']))):continue
            recovered=[]
            for vi,point,corner in zip(tri['vertices'],row['points'],row['corners']):
                ri=corner['reference_triangle'];rf=prefix['faces'][ri]
                ids=original['triangles'][ri]
                if ids!=rf['vertices']:raise ValueError('False original sheet reference partition')
                if rf['tag'] or rf['strength']!=16384:recovered=[];break
                pts=[original['vertices'][j] for j in ids]
                if any(tuple(p) not in params for p in pts):recovered=[];break
                weights=np.asarray(corner['weights'])
                if np.linalg.norm(weights@np.asarray(pts)-point)>2e-6:raise ValueError('Actual original corner outside finite reference')
                q=(weights@np.asarray([params[tuple(p)] for p in pts])).tolist();q[2]=int(round(q[2]))
                if q[2] not in (-1,1):raise ValueError('Invalid original sheet side')
                if vi in initial_params and math.dist(initial_params[vi],q)>1e-5:raise ValueError('Ambiguous finite parameter ownership')
                initial_params[vi]=q;recovered.append(q)
            if recovered:owned.add(ti);ownership.append(row)
    before=core['stages'][-1]['before'];by_point=defaultdict(list)
    for vi,p in enumerate(before['physical']['vertices']):by_point[tuple(p)].append(vi)
    current_old={}
    for vi,p in enumerate(actual['points']):
        hits=by_point[tuple(p)]
        if len(hits)==1:current_old[vi]=hits[0]
    old_tri={tuple(sorted(t['vertices'])):i for i,t in enumerate(initial['triangles'])}
    selected=[];current_params={};proof=[]
    for ti,tri in enumerate(actual['triangles']):
        vs=tri['vertices']
        if any(v not in current_old for v in vs):continue
        old=[current_old[v] for v in vs];ii=old_tri.get(tuple(sorted(old)))
        if ii not in owned:continue
        qs=[initial_params[v] for v in old]
        current_params.update(zip(vs,qs))
        if (all(5.-1e-7<=q[0]<=7.+1e-7 and Y_REAR-1e-7<=q[1]<=2.4+1e-7 for q in qs)
                and len({q[2] for q in qs})==1 and ti in sheet_plan['selected_faces']):
            selected.append(ti);proof.append(dict(current_triangle=ti,initial_triangle=ii,initial_vertices=old,parameters=qs))
    if not selected:raise ValueError('Empty actual lamp transition')
    chosen=set(selected);edges=defaultdict(list);incident=defaultdict(list)
    for ti,tri in enumerate(actual['triangles']):
        vs=tri['vertices']
        for v in vs:incident[v].append(ti)
        for a,b in zip(vs,vs[1:]+vs[:1]):edges[tuple(sorted((a,b)))].append(ti)
    boundary=[]
    for edge,adj in edges.items():
        if len(set(adj)&chosen)==1:
            if len(adj)!=2:raise ValueError('Open finite transition boundary')
            boundary.append(dict(vertices=list(edge),triangles=adj))
    all_vertices=sorted({v for ti in selected for v in actual['triangles'][ti]['vertices']})
    fixed=sorted({v for row in boundary for v in row['vertices']});free=sorted(set(all_vertices)-set(fixed))
    if not free or any(not set(incident[v]).issubset(chosen) for v in free):raise ValueError('Free point would move a protected face')
    return dict(selected_faces=selected,vertices=all_vertices,boundary=boundary,fixed_vertices=fixed,free_vertices=free,
        parameters=current_params,current_to_initial=current_old,actual_ownership=proof,
        pre_lamp=core['stages'][2]['before'],incident=dict(incident),original_fragment_count=len(ownership))

def prepare(actual, original, prefix, packet, sheet_plan):
    """Plan one scalar thin-plate surface with complete fixed native boundary."""
    d=domain(actual,original,prefix,packet,sheet_plan)
    points=np.asarray(actual['points'],dtype=float);base=points.copy()
    for vi,oi in d['current_to_initial'].items():base[vi]=d['pre_lamp']['physical']['vertices'][oi]
    free=d['free_vertices'];free_set=set(free);index={v:i for i,v in enumerate(free)}
    triangles=[t['vertices'] for t in actual['triangles']]
    # All Laplacian rows touched by an interior unknown. Neighbor coordinates
    # stay fixed, supplying the clamped continuation on the actual carrier.
    active=set(free)
    for v in free:
        for ti in d['incident'][v]:active.update(triangles[ti])
    related={ti for v in active for ti in d['incident'][v]}
    if any(v not in d['current_to_initial'] for ti in related for v in triangles[ti]):raise ValueError('Thin-plate collar crosses an unobserved new surface')
    weights=defaultdict(float);mass=defaultdict(float)
    for ti in sorted(related):
        vs=triangles[ti];p=base[vs];area2=float(np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0])))
        if not math.isfinite(area2) or area2<=0:raise ValueError('Degenerate actual carrier triangle')
        for v in vs:mass[v]+=area2/6.
        for j in range(3):
            a,b,c=vs[j],vs[(j+1)%3],vs[(j+2)%3]
            cot=float(np.dot(base[a]-base[c],base[b]-base[c])/area2)/2.
            weights[tuple(sorted((a,b)))]+=cot
    lap=defaultdict(dict)
    for (a,b),w in weights.items():
        for u,v in ((a,b),(b,a)):
            lap[u][u]=lap[u].get(u,0.)+w;lap[u][v]=lap[u].get(v,0.)-w
    delta=points[:,2]-base[:,2]
    A=[];rhs=[]
    for v in sorted(active):
        row=np.zeros(len(free));fixed=0.
        scale=1./math.sqrt(mass[v])
        for j,w in lap[v].items():
            if j in free_set:row[index[j]]=w*scale
            else:fixed+=w*delta[j]*scale
        A.append(row);rhs.append(-fixed)
    A=np.asarray(A);rhs=np.asarray(rhs)
    solution,residuals,rank,singular=np.linalg.lstsq(A,rhs,rcond=None)
    if rank!=len(free) or not np.isfinite(solution).all():raise ValueError('Unresolved finite thin-plate solve')
    new_points=points.copy();new_points[free,2]=base[free,2]+solution
    # Native storage is float32; predictions bind the actual delivered values.
    new_points=np.asarray(new_points,dtype=np.float32).astype(float)
    correction=new_points[:,2]-points[:,2]
    if any(np.any(new_points[v]!=points[v]) for v in range(len(points)) if v not in free_set):raise ValueError('Moved a protected point')
    targets=np.asarray(actual['normals'],dtype=float).copy();jets=[]
    selected=set(d['selected_faces']);loops_at=defaultdict(list)
    for ti in selected:
        tri=actual['triangles'][ti]
        for vi,li in zip(tri['vertices'],tri['loops']):loops_at[vi].append(li)
    # Each actual triangle supplies its exact finite affine displacement
    # differential. Angle-weighted transported corner normals form a single
    # connected interior field; no polynomial fit or hidden old-field target.
    triangle_jets={};weighted=defaultdict(list)
    for ti in sorted(selected):
        tri=actual['triangles'][ti];vs=tri['vertices'];p=points[vs];q=new_points[vs]
        tangents=np.column_stack((p[1]-p[0],p[2]-p[0]))
        differences=np.array([correction[vs[1]]-correction[vs[0]],correction[vs[2]]-correction[vs[0]]])
        covector=np.linalg.lstsq(tangents.T,differences,rcond=None)[0]
        J=np.eye(3);J[2]+=covector
        determinant=float(np.linalg.det(J))
        if determinant<=.2:raise ValueError('Finite surface deformation folds its actual triangle differential')
        residual=float(np.max(np.abs(J@tangents-np.column_stack((q[1]-q[0],q[2]-q[0])))))
        if residual>1e-10:raise ValueError('Incomplete finite triangle displacement differential')
        triangle_jets[ti]=dict(triangle=ti,jacobian=J.tolist(),determinant=determinant,edge_transport_residual_m=residual,
            geometric_normal_change_degrees=angle(unit(np.cross(p[1]-p[0],p[2]-p[0])),unit(np.cross(q[1]-q[0],q[2]-q[0]))))
        for j,(vi,li) in enumerate(zip(vs,tri['loops'])):
            a=q[(j+1)%3]-q[j];b=q[(j+2)%3]-q[j]
            theta=math.atan2(float(np.linalg.norm(np.cross(a,b))),float(np.dot(a,b)))
            n=unit(np.linalg.solve(J.T,np.asarray(actual['normals'][li])))
            weighted[vi].append((theta,n,ti))
    for vi in free:
        before=unit(np.mean(np.asarray(actual['normals'])[loops_at[vi]],axis=0))
        new=unit(sum(w*n for w,n,ti in weighted[vi]))
        for li in loops_at[vi]:targets[li]=new
        jets.append(dict(vertex=vi,triangles=[ti for w,n,ti in weighted[vi]],target=new.tolist(),
            prior_native_to_new_degrees=angle(before,new),
            maximum_incident_transport_spread_degrees=max(angle(new,n) for w,n,ti in weighted[vi])))
    changed=sorted(v for v in free if np.any(new_points[v]!=points[v]))
    before_energy=float(np.linalg.norm(A@delta[free]-rhs)**2);after_energy=float(np.linalg.norm(A@solution-rhs)**2)
    return dict(schema='finite-lamp-surface-proposal.v1',object=NAME,domain=d,
        positions_before=actual['points'],positions=new_points.tolist(),normals_before=actual['normals'],targets=targets.tolist(),
        changed_vertices=changed,normal_jets=jets,triangle_differentials=list(triangle_jets.values()),rank=int(rank),thin_plate_energy_before=before_energy,thin_plate_energy_after=after_energy,
        maximum_displacement_m=float(np.max(np.abs(correction))),minimum_displacement_m=float(correction.min()),maximum_signed_displacement_m=float(correction.max()),
        boundary_positions_exact=True,boundary_native_targets_exact=True,triangle_delta=0,
        normal_guard_degrees=NORMAL,source_saved=False,exported=False,visual_acceptance=False,
        limitations=['New interior fields use angle-weighted exact actual-triangle affine transport. This is an explicit smooth manufactured-sheet field, not historical normal interpolation preservation.',
                     'Fixed edge positions and corner targets preserve the complete existing polygon boundary and affine native field there. Geometric adjacent facet turns remain separately measured.',
                     'Minimum-bending objective reduction is not a visual or optical-fit acceptance.'])
