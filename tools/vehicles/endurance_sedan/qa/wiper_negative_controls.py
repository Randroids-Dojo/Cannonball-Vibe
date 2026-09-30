"""Exercise clearance rejection on actual geometry modified only in memory."""
import argparse
from datetime import datetime,timezone
import gzip,hashlib,json,math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from wipers import Motion,outer_glass_skin,trig_bounds,GUARD
from wiper_interassembly import Shape,cell_certificate


def main():
    p=argparse.ArgumentParser();p.add_argument('--geometry',type=Path,required=True);p.add_argument('--motion-contract',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]);assert not args.output.exists()
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    source_sha=sha(args.source);geometry=json.loads(gzip.decompress(args.geometry.read_bytes()));contract=json.loads(args.motion_contract.read_text(encoding='utf8'))
    assert geometry['source_sha256']==contract['source_sha256']==source_sha and contract['status']=='passed'
    meshes=geometry['meshes'];driver=next(r for r in contract['wipers'] if r['name']=='Wiper_L')
    glass=outer_glass_skin(meshes['LOD0_Windshield'],np.asarray(driver['axis_source']))
    row=meshes['LOD0_Wiper_LRubber'];vertices=np.asarray(row['vertices']);inverse=np.linalg.inv(np.asarray(driver['rest_world_matrix']))
    local=(np.c_[vertices,np.ones(len(vertices))]@inverse.T)[:,:3]
    bottom=np.flatnonzero(local[:,2]<=local[:,2].min()+2e-7)
    cases=[]
    for name,delta,expected in [('unaltered',np.zeros(3),True),('penetrate_glass',-.001*glass['normal'],False),
                                ('float_above_contact_band',.003*glass['normal'],False),('outside_left_glass_edge',np.asarray([-2.,0,0]),False)]:
        # Shift the full assembly with its pivot, leaving its saved relative sweep intact.
        changed=dict(driver);changed['pivot_source_m']=(np.asarray(driver['pivot_source_m'])+delta).tolist()
        motion=Motion(vertices+delta,changed)
        low,high,_,_=motion.bounds([glass['normal']],indices=bottom)
        edge=motion.bounds(glass['edge_axes'],indices=bottom)[0]-glass['edge_constants']
        bounds=[float(low.min()-glass['d_max']-GUARD),float(high.max()-glass['d_min']+GUARD)]
        margin=float(edge.min()-GUARD);actual=bounds[0]>=0 and bounds[1]<=.002 and margin>0
        assert actual==expected,(name,bounds,margin)
        cases.append({'case':name,'translation_m':delta.tolist(),'guarded_gap_m':bounds,'guarded_edge_margin_m':margin,
                      'expected_accept':expected,'actual_accept':actual,'passed':True})
    scalar=[]
    for name,c,a,b,lo,hi,expected in [('cos_period',0.,1.,0.,-math.pi,math.pi,(-1.,1.)),
                                    ('sin_half_period',0.,0.,1.,-math.pi/2,math.pi/2,(-1.,1.)),
                                    ('mixed_full_period',4.,2.,3.,-5.,-5.+math.tau,(4.-math.sqrt(13),4.+math.sqrt(13))),
                                    ('endpoint_only',1.,0.,2.,.1,.3,(1.+2*math.sin(.1),1.+2*math.sin(.3)))]:
        mn,mx,_,_=trig_bounds(np.asarray(c),np.asarray(a),np.asarray(b),lo,hi)
        assert abs(float(mn)-expected[0])<1e-12 and abs(float(mx)-expected[1])<1e-12
        scalar.append({'case':name,'min':float(mn),'max':float(mx),'expected':expected,'passed':True})
    base={'name':'synthetic_triangle','vertices':[[0,0,0],[1,0,0],[0,1,0]],'triangles':[[0,1,2]]}
    a=Shape(base);overlap=Shape(base)
    separated=Shape({**base,'vertices':(np.asarray(base['vertices'])+np.asarray([0,0,.005])).tolist()})
    overlap_bound,_=cell_certificate(a,0,overlap,0,{})
    separate_bound,_=cell_certificate(a,0,separated,0,{})
    assert overlap_bound<.001+GUARD and separate_bound>=.001+GUARD
    output={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),'source_sha256':source_sha,
            'source_unchanged':sha(args.source)==source_sha,'status':'passed','actual_geometry_cases':cases,'known_scalar_extrema':scalar,
            'triangle_projection_controls':{'overlapping_bound_m':overlap_bound,'separated_bound_m':separate_bound,'passed':True},
            'inputs':[{'path':str(path.resolve()),'sha256':sha(path)} for path in (args.source,args.geometry,args.motion_contract,Path(__file__),Path(__file__).with_name('wipers.py'),Path(__file__).with_name('wiper_interassembly.py'))],
            'scope':'In-memory negative controls only; no scene edits/saves/exports, and no change to acceptance thresholds.',
            'human_approval_reference':None}
    args.output.write_text(json.dumps(output,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'status':'passed','actual_geometry_cases':len(cases),'scalar_cases':len(scalar),'triangle_projection_cases':2}),flush=True)


if __name__=='__main__':main()
