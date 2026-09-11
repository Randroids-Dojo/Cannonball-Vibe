"""Conservative all-angle clearance bounds for actual rigid opening assemblies.

Every component pair is independent. Two moving components have independent
angle intervals; no equal-angle assumption is made. Failed and unresolved cells
remain explicit. This tool reads evaluated QA geometry, never production scenes.
"""
import argparse
import ast
import gzip
import hashlib
import itertools
import json
import math
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from mathutils import Matrix, Vector, geometry

p=argparse.ArgumentParser()
p.add_argument('--input',type=Path,required=True)
p.add_argument('--drivers',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--mode',choices=('moving-moving','moving-fixed','all'),default='all')
p.add_argument('--max-cells-per-pair',type=int,default=30000)
p.add_argument('--include-group',action='append',default=[])
p.add_argument('--include-component',action='append',default=[])
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
assert not a.output.exists()
qa=Path(__file__).resolve().parent
helper=qa/'geometry.py'
sys.path.insert(0,str(qa))
from geometry import bounds, box_distance2, tree, segment_distance, triangle_distance

def near(node,box,threshold):
    if box_distance2(node[0],box)>=threshold**2:return
    if node[1] is not None:yield from node[1]
    else:
        yield from near(node[2],box,threshold)
        yield from near(node[3],box,threshold)

def scalar_range(c,x,y,lo,hi):
    """Exact extrema of c+x*cos(angle)+y*sin(angle) on a finite interval."""
    values=[c+x*math.cos(t)+y*math.sin(t) for t in (lo,hi)]
    phase=math.atan2(y,x)
    for k in range(math.floor((lo-phase)/math.pi)-1,math.ceil((hi-phase)/math.pi)+2):
        t=phase+k*math.pi
        if lo<=t<=hi:values.append(c+x*math.cos(t)+y*math.sin(t))
    return min(values),max(values)

assert scalar_range(0.,1.,0.,-.5,.5)[1]==1.
assert triangle_distance([Vector(v) for v in ((-1,0,0),(1,0,0),(0,1,0))],
                         [Vector(v) for v in ((0,.2,-1),(0,.2,1),(0,-1,0))])[0]==0.
assert abs(segment_distance(Vector((-1,0,0)),Vector((1,0,0)),Vector((0,-1,.002)),Vector((0,1,.002)))[0]-.002)<1e-8

started=time.perf_counter();utc=datetime.now(timezone.utc).isoformat()
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
d=json.loads(gzip.decompress(a.input.read_bytes()))
contract=json.loads(a.drivers.read_text(encoding='utf-8'))
assert contract['status']=='passed' and contract['source_sha256']==d['source_sha256']
groups={r['name']:r for r in contract['opening_groups']}
assert len(groups)==6
rows={n:r for n,r in d['meshes'].items() if r['properties'].get('source_preview_only') is not True}
membership={n:next((g for g in r['ancestors'] if g in groups),None) for n,r in rows.items()}
for n,g in membership.items():
    if g:assert n in groups[g]['descendants'],(n,g)
poses={r['name']:r for r in d['poses']}
rest=poses['rest']['semantic_world_matrices']
guard=1e-6;target=.001
coefficients={};radii={};fixed_boxes={}
for n,r in rows.items():
    vs=r['vertices'];g=membership[n]
    if g is None:
        fixed_boxes[n]=bounds(vs);radii[n]=0.;continue
    record=groups[g];axis=record['axis_source'];pivot=record['pivot_source_m']
    coeff=[];radius=0.
    for v in vs:
        u=[v[i]-pivot[i] for i in range(3)];dot=sum(u[i]*axis[i] for i in range(3))
        x=[u[i]-axis[i]*dot for i in range(3)]
        y=[axis[1]*u[2]-axis[2]*u[1],axis[2]*u[0]-axis[0]*u[2],axis[0]*u[1]-axis[1]*u[0]]
        c=[pivot[i]+axis[i]*dot for i in range(3)]
        coeff.append((c,x,y));radius=max(radius,math.sqrt(sum(q*q for q in x)))
    coefficients[n]=coeff;radii[n]=radius

# Verify each recorded native opening matrix on every affected component's
# conservative bounding-box corners. These points bound affine position error.
native_max_error=0.;native_checks=0
for pose in d['poses']:
    for g,record in groups.items():
        key=g+'_open'
        if key not in pose['controls']:continue
        fraction=pose['controls'][key]
        native=Matrix(pose['semantic_world_matrices'][g])@Matrix(rest[g]).inverted()
        pivot=Vector(record['pivot_source_m'])
        analytic=Matrix.Translation(pivot)@Matrix.Rotation(record['factor_rad']*fraction,4,Vector(record['axis_source']))@Matrix.Translation(-pivot)
        for n in rows:
            if membership[n]!=g:continue
            box=bounds(rows[n]['vertices'])
            for point in itertools.product(*zip(box[0],box[1])):
                error=(native@Vector(point)-analytic@Vector(point)).length
                native_max_error=max(native_max_error,error);native_checks+=1
assert native_max_error<guard,(native_max_error,guard)

@lru_cache(maxsize=12000)
def swept_box(n,lo,hi):
    if membership[n] is None:return fixed_boxes[n]
    angle=groups[membership[n]]['factor_rad'];alo,ahi=sorted((lo*angle,hi*angle))
    low=[math.inf]*3;high=[-math.inf]*3
    for c,x,y in coefficients[n]:
        for i in range(3):
            mi,ma=scalar_range(c[i],x[i],y[i],alo,ahi)
            low[i]=min(low[i],mi);high[i]=max(high[i],ma)
    return (tuple(q-1e-12 for q in low),tuple(q+1e-12 for q in high))

@lru_cache(maxsize=1200)
def at(n,fraction):
    g=membership[n]
    if g is None:vs=[Vector(v) for v in rows[n]['vertices']]
    else:
        theta=groups[g]['factor_rad']*fraction;co=math.cos(theta);si=math.sin(theta)
        vs=[Vector([c[i]+x[i]*co+y[i]*si for i in range(3)]) for c,x,y in coefficients[n]]
    triangles=[([vs[i] for i in tri],bounds([vs[i] for i in tri])) for tri in rows[n]['triangles']]
    return triangles,tree(triangles)

def movement(n,lo,hi):
    g=membership[n]
    return 0. if g is None else 2*radii[n]*math.sin(abs(groups[g]['factor_rad'])*(hi-lo)/4)

def near_witness(n,m,f,g,threshold):
    first,_=at(n,f);second,bvh=at(m,g)
    for i,(av,ab) in enumerate(first):
        for j in near(bvh,ab,threshold):
            bv,bb=second[j]
            if box_distance2(ab,bb)>=threshold**2:continue
            dist,x,y=triangle_distance(av,bv)
            if dist<threshold:return {'distance_m':dist,'triangle_a':i,'triangle_b':j,'point_a_m':list(x),'point_b_m':list(y)}
    return None

# Exact published pin/sleeve pairs have their own nominal 0.5 mm radial bearing
# clearance. They are not exempt from nonintersection; here certify >1um, and
# require a separate radius/axial-fitting measurement for their nominal value.
bearing_pairs={}
for door in ('FL','FR','RL','RR'):
    for height in ('0.6','0.84'):
        base='LOD0_Door_'+door+'Hinge_'+height
        bearing_pairs[tuple(sorted((base+'MovingKnuckle',base+'Pin')))]='packaging-revision-v8.md exact 4/4.5 mm pin/bore bearing'
for closure in ('Hood','Trunk'):
    for side in ('-1','1'):
        bearing_pairs[tuple(sorted(('LOD0_'+closure+'HingeMovingKnuckle_'+side,'LOD0_'+closure+'HingePin_'+side)))]= 'packaging-revision-v4.md exact 4/4.5 mm pin/bore bearing'
for pair in bearing_pairs:assert all(n in rows for n in pair),pair
seal_pairs={tuple(sorted(('LOD0_Door_'+side,'LOD0_DoorApertureSeal_'+side))):'Door_'+side for side in ('RL','RR')}

names_sorted=sorted(rows);moving=[n for n in names_sorted if membership[n]]
candidate_pairs=[];aabb_certified=0;aabb_certificates=[];same_group_omitted=0
assert all(n in rows for n in a.include_component), 'Unknown component filter'
for i,n in enumerate(names_sorted):
    for m in names_sorted[i+1:]:
        ng,mg=membership[n],membership[m]
        if ng is None and mg is None:continue
        if ng==mg:same_group_omitted+=1;continue
        if a.mode=='moving-moving' and (ng is None or mg is None):continue
        if a.mode=='moving-fixed' and ng is not None and mg is not None:continue
        if a.include_group and not any(g in (ng,mg) for g in a.include_group):continue
        if a.include_component and not any(c in (n,m) for c in a.include_component):continue
        if box_distance2(swept_box(n,0.,1.),swept_box(m,0.,1.))>=(target+guard)**2:
            aabb_certified+=1;aabb_certificates.append({'pair':[n,m],'lower_bound_m':math.sqrt(box_distance2(swept_box(n,0.,1.),swept_box(m,0.,1.)))});continue
        candidate_pairs.append((n,m))

results=[]
for pair_index,(n,m) in enumerate(candidate_pairs):
    key=tuple(sorted((n,m)));ng,mg=membership[n],membership[m]
    policy='general 1 mm unrelated moving-solid clearance'
    intervals=[(0.,1.,0.,1.,target)]
    if key in bearing_pairs:
        policy=bearing_pairs[key];intervals=[(0.,1.,0.,1.,0.)]
    elif key in seal_pairs:
        group=seal_pairs[key];end=.41/abs(math.degrees(groups[group]['factor_rad']))
        policy='Only exact rear shell/perimeter seal inside0.41 degrees: positive separation; outside zone1 mm. packaging-revision-v9.md'
        intervals=[(0.,end,0.,1.,0.),(end,1.,0.,1.,target)] if ng==group else [(0.,1.,0.,end,0.),(0.,1.,end,1.,target)]
    cells=0;leaves=0;minimum_bound=math.inf;max_depth=0;witness=None;unresolved=None
    stack=[(*cell,0) for cell in intervals]
    while stack:
        lo,hi,ol,oh,minimum,depth=stack.pop();cells+=1;max_depth=max(max_depth,depth)
        if cells>a.max_cells_per_pair:
            unresolved={'reason':'bounded cell budget exceeded','intervals':[lo,hi,ol,oh],'pending_cells':len(stack)+1};break
        bound=math.sqrt(box_distance2(swept_box(n,lo,hi),swept_box(m,ol,oh)))
        if bound>=minimum+guard:
            leaves+=1;minimum_bound=min(minimum_bound,bound-guard);continue
        da=movement(n,lo,hi);db=movement(m,ol,oh);displacement=da+db
        f=(lo+hi)/2 if ng else 0.;g=(ol+oh)/2 if mg else 0.
        # Broad intervals are split before costly near-field triangle work.
        found=None
        if displacement<=.025 or depth>=18:
            found=near_witness(n,m,f,g,minimum+guard+displacement)
            if found is None:
                leaves+=1;minimum_bound=min(minimum_bound,minimum);continue
            if found['distance_m']<minimum-guard:
                witness={**found,'fraction_a':f,'fraction_b':g,'required_m':minimum,'intervals':[lo,hi,ol,oh]};break
        if depth>=26 or displacement<1e-9:
            unresolved={'reason':'numeric guard or depth limit could not certify','intervals':[lo,hi,ol,oh],'midpoint_witness':found};break
        if da>=db and ng:
            middle=(lo+hi)/2;stack.append((middle,hi,ol,oh,minimum,depth+1));stack.append((lo,middle,ol,oh,minimum,depth+1))
        else:
            middle=(ol+oh)/2;stack.append((lo,hi,middle,oh,minimum,depth+1));stack.append((lo,hi,ol,middle,minimum,depth+1))
    row={'pair':[n,m],'groups':[ng,mg],'policy':policy,'cells':cells,'certified_leaves':leaves,'maximum_depth':max_depth,
         'lower_bound_m':None if math.isinf(minimum_bound) else minimum_bound,'witness':witness,'unresolved':unresolved,
         'status':'failed-witness' if witness else 'unresolved' if unresolved else 'continuous-bound-certified'}
    results.append(row)
    print('QA_CONTINUOUS '+json.dumps({'index':pair_index+1,'total':len(candidate_pairs),**row}),flush=True)

status='failed' if any(r['witness'] for r in results) else 'unresolved' if any(r['unresolved'] for r in results) else 'passed'
report={'task_id':'P1-018','milestone':'M5','start_utc':utc,'end_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-started,
        'source_sha256':d['source_sha256'],'inputs':[{'path':str(q),'sha256':sha(q)} for q in (a.input,a.drivers,helper,Path(__file__))],
        'mode':a.mode,'groups_filter':a.include_group,'components_filter':a.include_component,'mesh_count':len(rows),'moving_mesh_count':len(moving),'target_m':target,'numeric_guard_m':guard,
        'native_affine_corner_checks':native_checks,'maximum_native_position_error_m':native_max_error,
        'entire_domain_aabb_certified_pairs':aabb_certified,'entire_domain_aabb_certificates':aabb_certificates,'same_rigid_group_pairs_not_part_of_motion_check':same_group_omitted,
        'remaining_pairs':results,'status':status,
        'method':'Analytic vertex-coordinate sine/cosine extrema bound each swept component AABB. Unresolved intervals use midpoint triangle clearance minus the exact maximal point-displacement bound2R*sin(half-angular-width/2). Each independent moving group has its own parameter interval. Every accepted interval has a conservative gap bound; subdivision alone is not acceptance.',
        'limits':'Actual retained evaluated LOD0 surfaces and six proportional opening drivers only. Other controls remain at their retained rest geometry; steering/suspension and wipers require separate swept envelopes. Same-rigid assembly construction interfaces need separate static QA. Named pin/bore cases are certified for positive separation only and require separate nominal radius/axial interface measurement. Exact rear rubber zone is individually bounded; all other pairs retain1 mm. Numerical1um margin is retained. Native rest-state intersection diagnostics must independently exclude preexisting solid containment.',
        'human_approval_reference':None}
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
print('QA_CONTINUOUS_COMPLETE '+json.dumps({'status':status,'pairs':len(results),'whole_domain_aabb_pairs':aabb_certified}),flush=True)
raise SystemExit(0 if status=='passed' else 1)
