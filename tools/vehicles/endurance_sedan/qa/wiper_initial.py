"""Complete surface-clearance evidence with initial closed-solid parity checks."""
import argparse
from datetime import datetime,timezone
import gzip,hashlib,json
from pathlib import Path
import sys,time

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from wiper_interassembly import aabb_gap

DIRECTIONS=np.asarray([[.713,.417,.563],[-.512,.793,.331],[.157,-.631,.827],
                       [.911,.173,-.377],[-.421,-.883,.207]],dtype=float)
DIRECTIONS/=np.linalg.norm(DIRECTIONS,axis=1)[:,None]


def components(row):
    vertices=np.asarray(row['vertices'],dtype=float);triangles=np.asarray(row['triangles'],dtype=int)
    parent=list(range(len(vertices)));edges={}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for tri in triangles:
        for a,b in zip(tri,np.roll(tri,-1)):
            a,b=int(a),int(b);ra,rb=find(a),find(b);parent[rb]=ra
            edge=tuple(sorted((a,b)));edges[edge]=edges.get(edge,0)+1
    ids={}
    for i in set(triangles.flat):ids.setdefault(find(int(i)),int(i))
    return {'vertices':vertices,'triangles':vertices[triangles],
            'representatives':sorted(ids.values()),'nonmanifold_edges':sum(n!=2 for n in edges.values()),
            'low':vertices.min(axis=0),'high':vertices.max(axis=0)}


def parity(point,target):
    tri=target['triangles'];e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];t=point-tri[:,0]
    rows=[]
    for direction in DIRECTIONS:
        h=np.cross(direction,e2);det=np.einsum('ij,ij->i',e1,h)
        valid=np.abs(det)>1e-14
        inv=np.zeros_like(det);inv[valid]=1/det[valid]
        u=inv*np.einsum('ij,ij->i',t,h);q=np.cross(t,e1)
        v=inv*(q@direction);distance=inv*np.einsum('ij,ij->i',e2,q)
        hits=valid&(u>=-1e-10)&(v>=-1e-10)&(u+v<=1+1e-10)&(distance>1e-9)
        near_edge=hits&((u<1e-8)|(v<1e-8)|(1-u-v<1e-8))
        if near_edge.any():continue
        values=sorted(distance[hits].tolist());unique=[]
        for d in values:
            if not unique or d-unique[-1]>1e-7:unique.append(d)
        rows.append({'direction':direction.tolist(),'positive_distances_m':unique,'inside_odd_parity':bool(len(unique)%2)})
        if len(rows)==3:break
    states={row['inside_odd_parity'] for row in rows}
    if len(rows)<3 or len(states)!=1:return {'status':'unresolved_ray_parity','rays':rows}
    return {'status':'inside' if rows[0]['inside_odd_parity'] else 'outside','rays':rows}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--geometry',type=Path,required=True)
    parser.add_argument('--contacts',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=parser.parse_args(argv);assert not args.output.exists();clock=time.perf_counter()
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    g=json.loads(gzip.decompress(args.geometry.read_bytes()));contacts=json.loads(args.contacts.read_text(encoding='utf8'))
    assert g['source_sha256']==contacts['source_sha256'] and contacts['status']=='passed'
    meshes=g['meshes'];cache={};rows=[];failures=[];ray_points=0
    for pair in contacts['near_pair_reports']:
        an,bn=pair['pair']
        for name in (an,bn):
            if name not in cache:cache[name]=components(meshes[name])
        a,b=cache[an],cache[bn]
        gap=float(aabb_gap(a['low'],a['high'],b['low'],b['high']))
        row={'pair':[an,bn],'rest_aabb_gap_m':gap,'checks':[]}
        if gap>0:row['status']='outside_by_disjoint_rest_aabbs'
        elif a['nonmanifold_edges'] or b['nonmanifold_edges']:
            row['status']='unresolved_nonclosed_mesh';row['nonmanifold_edges']=[a['nonmanifold_edges'],b['nonmanifold_edges']]
        else:
            for shape,target,origin_name,target_name in ((a,b,an,bn),(b,a,bn,an)):
                for index in shape['representatives']:
                    point=shape['vertices'][index]
                    if np.any(point<target['low']) or np.any(point>target['high']):
                        check={'status':'outside_target_aabb'}
                    else:check=parity(point,target);ray_points+=1
                    row['checks'].append({'source_mesh':origin_name,'target_mesh':target_name,
                                           'representative_vertex':index,'point_source_m':point.tolist(),**check})
            row['status']='outside_by_components_and_parity' if all(check['status'] in ('outside','outside_target_aabb') for check in row['checks']) else 'failed_or_unresolved_containment'
        if row['status'].startswith(('unresolved','failed')):failures.append(row)
        rows.append(row)
    result={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
            'source_sha256':g['source_sha256'],'status':'passed' if not failures else 'failed',
            'inputs':[{'path':str(p.resolve()),'sha256':sha(p)} for p in (args.geometry,args.contacts,Path(__file__))],
            'pairs_checked':len(rows),'whole_domain_aabb_pairs_already_exclude_containment':len(contacts['whole_domain_aabb_certificates']),
            'three_ray_representatives_checked':ray_points,'rows':rows,'failures':failures,
            'elapsed_seconds':time.perf_counter()-clock,
            'method':'The full-domain surface certificate excludes boundary crossing. At rest, disjoint AABBs exclude containment directly; otherwise each connected closed mesh component has a representative vertex checked outside the other object using its AABB or three unambiguous agreeing odd-even ray parities. Both directions are checked.',
            'limits':'Solid interpretation is the actual closed triangle surfaces with odd-even interior. This does not validate mounting strength or imply final-source/runtime/human acceptance.',
            'human_approval_reference':None}
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'status':result['status'],'near_pairs':len(rows),'ray_representatives':ray_points,'failures':len(failures),'seconds':result['elapsed_seconds']}),flush=True)
    raise SystemExit(0 if not failures else 1)


if __name__=='__main__':main()
