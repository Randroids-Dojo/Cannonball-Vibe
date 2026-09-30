"""Native final-LOD connected-shell self checks, separate from assembly fit."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parent))
from self_intersections import sha, validate_row
import self_geometry


def partition(row):
    """Partition actual indices only; coincident coordinates are never welded."""
    validate_row(row['name'],row)
    vertices,triangles=row['vertices'],row['triangles']
    parent=list(range(len(vertices)))
    def find(index):
        while parent[index]!=index:
            parent[index]=parent[parent[index]];index=parent[index]
        return index
    for face in triangles:
        for a,b in ((face[0],face[1]),(face[0],face[2])):
            a,b=find(a),find(b)
            if a!=b:parent[max(a,b)]=min(a,b)
    groups={}
    for index,face in enumerate(triangles):
        groups.setdefault(find(face[0]),[]).append(index)
    groups=sorted(groups.values(),key=lambda group:group[0])
    assert sorted(index for group in groups for index in group)==list(range(len(triangles)))
    return groups


def shell_certificate(row):
    groups=partition(row);owner={};results=[]
    for index,group in enumerate(groups):
        used=sorted({vertex for i in group for vertex in row['triangles'][i]})
        remap={old:new for new,old in enumerate(used)}
        faces=[[remap[v] for v in row['triangles'][i]] for i in group]
        edges=Counter(tuple(sorted((face[i],face[(i+1)%3]))) for face in faces for i in range(3))
        if any(count!=2 for count in edges.values()):
            raise ValueError('Final lower-LOD shell is not closed: '+row['name'])
        if len({tuple(sorted(face)) for face in faces})!=len(faces):
            raise ValueError('Duplicate final lower-LOD triangle: '+row['name'])
        winding=Counter()
        for face in faces:
            for a,b in zip(face,face[1:]+face[:1]):
                winding[tuple(sorted((a,b)))]+=1 if a<b else -1
        if any(winding.values()):raise ValueError('Inconsistent shell winding: '+row['name'])
        part={'name':row['name']+'#shell'+str(index),'vertices':[row['vertices'][i] for i in used],
              'triangles':faces}
        proof=self_geometry.scan(part)
        proof.update(source_vertex_indices=used,source_triangle_indices=group)
        results.append(proof)
        owner.update({triangle:index for triangle in group})
    all_candidates=self_geometry.candidates(row)
    excluded=sum(owner[a]!=owner[b] for a,b in all_candidates)
    included=sum(len_result['aabb_candidates'] for len_result in results)
    if included+excluded!=len(all_candidates):
        raise ValueError('Final LOD candidate partition is incomplete')
    return {'name':row['name'],'status':'passed' if all(p['status']=='passed' for p in results) else 'failed',
            'triangles':len(row['triangles']),'shell_count':len(results),'shells':results,
            'all_batch_aabb_candidates':len(all_candidates),'tested_intrashell_candidates':included,
            'excluded_cross_shell_candidates':excluded,
            'scope':'Only indexed connected-shell self geometry. Excluded cross-shell pairs are unassessed assembly contacts, not accepted intersections.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.output.exists():parser.error('Use a fresh evidence path')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();source_hash=None;tool_hashes={}
    record={'task_id':'P1-018','utc':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),
            'blender_version':bpy.app.version_string,'blender_build':bpy.app.build_hash.decode(),
            'status':'failed','source_sha256':None,'human_approval_reference':None,
            'scope':'Final native LOD1/2 topology and every actual indexed connected-shell self domain; no inter-shell fit or visual acceptance claim.'}
    try:
        tool_hashes={str(path.resolve()):sha(path) for path in
                     (Path(__file__),Path(self_geometry.__file__),Path(self_geometry.exact.__file__),
                      Path(__file__).with_name('self_intersections.py'))}
        if (bpy.app.version_string,bpy.app.build_hash.decode())!=('5.1.2','ec6e62d40fa9'):
            raise ValueError('Pinned Blender identity required')
        source_hash=sha(args.source);record['source_sha256']=source_hash
        bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
        graph=bpy.context.evaluated_depsgraph_get();rows=[];lod_counts={1:0,2:0}
        for obj in sorted(bpy.data.collections['Asset'].all_objects,key=lambda value:value.name):
            if obj.type!='MESH' or not obj.name.startswith(('LOD1_','LOD2_')):continue
            lod_counts[int(obj.name[3])]+=1
            evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
            try:
                mesh.calc_loop_triangles()
                row={'name':obj.name,'vertices':[list(evaluated.matrix_world@v.co) for v in mesh.vertices],
                     'triangles':[list(t.vertices) for t in mesh.loop_triangles]}
                result=shell_certificate(row);rows.append(result)
                print(json.dumps({'name':obj.name,'status':result['status'],'shells':result['shell_count'],
                                  'excluded':result['excluded_cross_shell_candidates']}),flush=True)
            finally:evaluated.to_mesh_clear()
        if not all(lod_counts.values()):raise ValueError('Both final lower LODs are required')
        record.update(status='passed' if all(row['status']=='passed' for row in rows) else 'failed',
                      rows=rows,lod_mesh_counts=lod_counts,mesh_count=len(rows),
                      shell_count=sum(row['shell_count'] for row in rows),
                      triangle_count=sum(row['triangles'] for row in rows),
                      excluded_cross_shell_candidates=sum(row['excluded_cross_shell_candidates'] for row in rows))
    except Exception as error:
        record.update(status='failed',failure=type(error).__name__+': '+str(error))
    finally:
        record.update(source_unchanged=source_hash is not None and sha(args.source)==source_hash,
                      elapsed_seconds=time.monotonic()-started,
                      tools=[{'path':path,'sha256':digest} for path,digest in tool_hashes.items()],
                      tools_unchanged=all(Path(path).is_file() and sha(path)==digest for path,digest in tool_hashes.items()))
        if not record['source_unchanged'] or not record['tools_unchanged']:record['status']='failed'
        args.output.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    return 0 if record['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
