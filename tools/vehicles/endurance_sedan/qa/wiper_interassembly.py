"""Conservative continuous separating-axis certificates for wiper assemblies.

Full scalar sweep is shared by both wipers. Hood angle is independent. Every
unresolved cell is a failure; finite samples are never promoted to clearance.
"""
import argparse
from datetime import datetime,timezone
import gzip,hashlib,json,math
from pathlib import Path
import sys,time

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from wipers import Motion,GUARD,plain


def aabb_gap(al,ah,bl,bh):
    return np.linalg.norm(np.maximum(np.maximum(bl-ah,al-bh),0),axis=-1)


class Shape:
    def __init__(self,row,driver=None,parameter=None):
        self.name=row['name'];self.vertices=np.asarray(row['vertices'],dtype=float)
        self.triangles=np.asarray(row['triangles'],dtype=int)
        self.motion=Motion(self.vertices,driver,parameter) if driver else None
        self.parameter=parameter
        if self.motion:
            vlow,vhigh,_,_=self.motion.bounds(np.eye(3))
        else:vlow=vhigh=self.vertices
        self.low,self.high=vlow.min(axis=0),vhigh.max(axis=0)
        self.tri_low,self.tri_high=vlow[self.triangles].min(axis=1),vhigh[self.triangles].max(axis=1)

    def at(self,index,domain):
        tri=self.triangles[index]
        if not self.motion:return self.vertices[tri]
        interval=domain[self.parameter]
        return self.motion.at(sum(interval)/2,tri)

    def projection(self,index,axes,domain):
        tri=self.triangles[index]
        if not self.motion:
            values=self.vertices[tri]@axes.T
            return values.min(axis=0),values.max(axis=0)
        low,high,_,_=self.motion.bounds(axes,domain[self.parameter],tri)
        return low.min(axis=0),high.max(axis=0)

    def radius(self,index):
        return np.linalg.norm(self.motion.cosine[self.triangles[index]],axis=1).max() if self.motion else 0.


def axes_for(a,b):
    ea=np.roll(a,-1,axis=0)-a;eb=np.roll(b,-1,axis=0)-b
    na=np.cross(ea[0],ea[1]);nb=np.cross(eb[0],eb[1])
    candidates=np.vstack((np.eye(3),na,nb,np.cross(ea[:,None,:],eb[None,:,:]).reshape(-1,3),
                          np.cross(na,ea),np.cross(nb,eb)))
    length=np.linalg.norm(candidates,axis=1)
    candidates=candidates[length>1e-12];length=length[length>1e-12]
    return candidates/length[:,None]


def cell_certificate(a,ia,b,ib,domain):
    axes=axes_for(a.at(ia,domain),b.at(ib,domain))
    al,ah=a.projection(ia,axes,domain);bl,bh=b.projection(ib,axes,domain)
    gaps=np.maximum(bl-ah,al-bh)
    index=int(np.argmax(gaps))
    return float(gaps[index]),axes[index]


def prove_pair(a,ia,b,ib,max_cells=1024,max_depth=24):
    parameters={p:(0.,1.) for p in (a.parameter,b.parameter) if p}
    stack=[(parameters,0)];cells=0;leaves=0;lowest=math.inf;deepest=0
    while stack:
        domain,depth=stack.pop();cells+=1;deepest=max(deepest,depth)
        lower,axis=cell_certificate(a,ia,b,ib,domain)
        if lower>=.001+GUARD:
            leaves+=1;lowest=min(lowest,lower-GUARD);continue
        if cells>=max_cells or depth>=max_depth:
            return {'status':'unresolved','cells':cells,'depth':deepest,'unresolved_domain':domain,
                    'best_separating_projection_lower_bound_m':lower,'best_axis':axis,
                    'reason':'Bound did not certify the guarded target within declared cell/depth budget. This is not an inferred actual collision.'}
        costs={p:0. for p in domain}
        for shape,index in ((a,ia),(b,ib)):
            if shape.parameter:
                interval=domain[shape.parameter]
                costs[shape.parameter]+=shape.radius(index)*abs(shape.motion.factor)*(interval[1]-interval[0])
        split=max(costs,key=costs.get);lo,hi=domain[split];mid=(lo+hi)/2
        left=dict(domain);right=dict(domain);left[split]=(lo,mid);right[split]=(mid,hi)
        stack.extend(((right,depth+1),(left,depth+1)))
    return {'status':'certified','cells':cells,'certified_leaves':leaves,'depth':deepest,'guarded_lower_bound_m':lowest}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--geometry',type=Path,required=True)
    parser.add_argument('--motion-contract',type=Path,required=True)
    parser.add_argument('--opening-contract',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=180.)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=parser.parse_args(argv);assert not args.output.exists();clock=time.perf_counter()
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source_sha=sha(args.source)
    payload=json.loads(gzip.decompress(args.geometry.read_bytes()))
    motion=json.loads(args.motion_contract.read_text(encoding='utf8'))
    opening=json.loads(args.opening_contract.read_text(encoding='utf8'))
    assert payload['source_sha256']==motion['source_sha256']==opening['source_sha256']==source_sha
    assert motion['status']==opening['status']=='passed'
    meshes={n:r for n,r in payload['meshes'].items() if r['properties'].get('source_preview_only') is not True}
    wipers={row['name']:row for row in motion['wipers']}
    openings={row['name']:row for row in opening['opening_groups']}
    wiper_names={name:sorted(n for n in row['rigid_descendants'] if n in meshes) for name,row in wipers.items()}
    shapes={}
    for group,names in wiper_names.items():
        shapes.update({name:Shape(meshes[name],wipers[group],'wiper') for name in names})
    opening_members={group:[name for name in record['descendants'] if name in meshes] for group,record in openings.items()}
    for group,names in opening_members.items():
        shapes.update({name:Shape(meshes[name],openings[group],group) for name in names})
    cabin={row['name']:row for row in motion['cabin_controls']}
    assert set(cabin)=={'SteeringWheel_Pivot','Pedal_Accelerator','Pedal_Brake'}
    cabin_members={group:[n for n in record['rigid_descendants'] if n in meshes] for group,record in cabin.items()}
    for group,names in cabin_members.items():
        record=dict(cabin[group])
        if group=='SteeringWheel_Pivot':
            # +/-464deg spans every rigid orientation; one complete revolution
            # is the exact geometric image, independently of the wiper sweep.
            assert abs(record['factor_rad'])*(record['control_domain'][1]-record['control_domain'][0])>=math.tau
            record['factor_rad']=math.tau
        else:assert record['control_domain']==[0.,1.]
        shapes.update({name:Shape(meshes[name],record,group) for name in names})
    wheel_bounds={}
    for record in motion['tires']:
        suffix=record['wheel'];center=np.asarray(record['center_source_m']);travel=record['continuous_travel_m']
        for name,row in meshes.items():
            if 'Suspension_'+suffix not in row['ancestors']:continue
            radius=float(np.linalg.norm(np.asarray(row['vertices'])-center,axis=1).max())
            wheel_bounds[name]=(center+[-radius,-radius,-radius+travel[0]],center+[radius,radius,radius+travel[1]])
    fixed=[];omitted=[]
    for name,row in meshes.items():
        if name in shapes or name in wheel_bounds or name=='LOD0_Windshield':continue
        shapes[name]=Shape(row);fixed.append(name)
    targets=[('cross_wiper',a,b) for a in wiper_names['Wiper_L'] for b in wiper_names['Wiper_R']]
    targets += [('wiper_opening',a,b) for names in wiper_names.values() for a in names for members in opening_members.values() for b in members]
    targets += [('wiper_cabin_control',a,b) for names in wiper_names.values() for a in names for members in cabin_members.values() for b in members]
    targets += [('wiper_fixed',a,b) for names in wiper_names.values() for a in names for b in fixed]
    broad=[];near=[];wheel_unresolved=[]
    for names in wiper_names.values():
        for an in names:
            shape=shapes[an]
            for bn,(low,high) in wheel_bounds.items():
                gap=float(aabb_gap(shape.low,shape.high,low,high))
                row={'scope':'wiper_wheel_complete_rotation_and_travel_sphere','pair':[an,bn],'guarded_swept_aabb_lower_bound_m':gap-GUARD}
                if gap>=.001+GUARD:broad.append(row)
                else:wheel_unresolved.append(row)
    for kind,an,bn in targets:
        a,b=shapes[an],shapes[bn];gap=float(aabb_gap(a.low,a.high,b.low,b.high))
        if gap>=.001+GUARD:broad.append({'scope':kind,'pair':[an,bn],'guarded_swept_aabb_lower_bound_m':gap-GUARD})
        else:near.append((kind,an,bn))
    print(json.dumps({'stage':'broad_phase','object_pairs':len(targets),'whole_domain_aabb_certified':len(broad),'near_object_pairs':len(near)}),flush=True)
    reports=[];total_cells=0;unresolved=[];timed_out=[]
    for pair_i,(kind,an,bn) in enumerate(near):
        if time.perf_counter()-clock>args.seconds:
            timed_out=near[pair_i:];break
        a,b=shapes[an],shapes[bn];candidates=[];pruned=0
        for start in range(0,len(b.triangles),512):
            distance=aabb_gap(a.tri_low[:,None,:],a.tri_high[:,None,:],b.tri_low[None,start:start+512,:],b.tri_high[None,start:start+512,:])
            ai,bi=np.nonzero(distance<.001+GUARD)
            candidates.extend(zip(ai.tolist(),(bi+start).tolist()));pruned+=distance.size-len(ai)
        pair_report={'scope':kind,'pair':[an,bn],'triangle_aabb_certified':pruned,'near_triangle_pairs':len(candidates),'certificates':[],'unresolved':[]}
        for ci,(ia,ib) in enumerate(candidates):
            if time.perf_counter()-clock>args.seconds:
                pair_report['unprocessed_triangle_pairs']=len(candidates)-ci
                timed_out=near[pair_i+1:];break
            result=prove_pair(a,ia,b,ib);total_cells+=result['cells']
            result['triangles']=[ia,ib]
            if result['status']=='certified':pair_report['certificates'].append(result)
            else:
                result['actual_rest_triangle_vertices']=[a.vertices[a.triangles[ia]],b.vertices[b.triangles[ib]]]
                pair_report['unresolved'].append(result)
        if pair_report['unresolved'] or pair_report.get('unprocessed_triangle_pairs'):
            unresolved.append([an,bn])
        reports.append(pair_report)
        print(json.dumps({'stage':'pair','pair':[an,bn],'near_triangles':len(candidates),'certified':len(pair_report['certificates']),'unresolved':len(pair_report['unresolved']),'cells_total':total_cells}),flush=True)
        if time.perf_counter()-clock>args.seconds:break
    status='passed' if not unresolved and not timed_out and not wheel_unresolved else 'failed_unresolved_domains'
    result={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),'source_sha256':source_sha,
            'source_unchanged':sha(args.source)==source_sha,'inputs':[{'path':str(p.resolve()),'sha256':sha(p)} for p in (args.source,args.geometry,args.motion_contract,args.opening_contract,Path(__file__),Path(__file__).with_name('wipers.py'))],
            'status':status,'elapsed_seconds':time.perf_counter()-clock,'numeric_guard_m':GUARD,'target_m':.001,
            'wiper_members':wiper_names,'opening_members':opening_members,'cabin_control_members':cabin_members,'wheel_motion_member_count':len(wheel_bounds),'fixed_mesh_count':len(fixed),'omitted_other_motion_meshes':omitted,
            'object_pair_count':len(targets)+sum(len(n) for n in wiper_names.values())*len(wheel_bounds),'whole_domain_aabb_certificates':broad,'near_pair_reports':reports,
            'unresolved_wheel_sphere_pairs':wheel_unresolved,
            'unresolved_object_pairs':unresolved,'unprocessed_object_pairs':timed_out,'cells':total_cells,
            'mathematical_method':'Full angle-interval point projections use analytic sine/cosine extrema. A normalized separating axis with interval projection gap >=1mm+guard proves Euclidean clearance for every point of both actual triangles over the whole parameter cell. Adaptive dyadic cells partition the complete one- or two-dimensional domain; unresolved cells are failures, never passes from samples.',
            'scope':'Cross-wiper assemblies share their actual scalar control. Every one of six opening groups and three cabin controls has an independent full-domain angle. All wheel suspension coassemblies use conservative full-rotation spheres plus complete translation travel. Remaining shipping LOD0 meshes are fixed. Windshield has its separate rubber/plane certificate. Same rigid wiper internal assembly joins are outside this interassembly proof.',
            'limits':['No cleaning-force, hinge-mount strength, dynamic deflection, runtime/export or human acceptance claim.',
                      'A separating surface certificate assumes components begin outside one another; a separate initial-containment check is required before calling this a full solid-volume certificate.'],
            'human_approval_reference':None}
    args.output.write_text(json.dumps(result,indent=2,default=plain)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'status':status,'object_pairs':result['object_pair_count'],'whole_domain_aabb':len(broad),'near_pairs':len(reports),'unresolved_pairs':len(unresolved),'unprocessed_pairs':len(timed_out),'cells':total_cells,'seconds':result['elapsed_seconds']}),flush=True)
    raise SystemExit(0 if status=='passed' else 1)


if __name__=='__main__':main()
