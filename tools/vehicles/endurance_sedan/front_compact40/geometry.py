"""Budget-only reduction of the actual original front exterior.

No styling deformation or old-cap reconstruction is applied. Finite assembly
collars and actual physical field seams are locked. Every new normal/UV corner
comes from a nearby compatible original sheet. Original geometry is the form
reference; the changed tessellation has an explicitly authored interpolation.
"""
import copy,math
from collections import defaultdict
import numpy as np
from .common import ROLES,unit
from .arch import arch_faces
from .common import receiver_tree
from .reduce import reduce
from .uv_source import LocalTree as OrientedTree

def source_target(row):
    t=copy.deepcopy(row);t['normal_corner_targets']=[[row['normals'][l]for l in ls]for ls in row['triangle_loops']]
    t['uv_corner_targets']={n:[[data[l]for l in ls]for ls in row['triangle_loops']]for n,data in row['uvs'].items()}
    return t

def field_boundaries(row,limit_degrees=65.):
    edges=defaultdict(list);v=np.asarray(row['vertices']);t=np.asarray(row['triangles']);ps=v[t];ns=np.cross(ps[:,1]-ps[:,0],ps[:,2]-ps[:,0]);ns/=np.linalg.norm(ns,axis=1)[:,None];records=[];locked=set();limit=math.cos(math.radians(65.))
    for f,tri in enumerate(row['triangles']):
        for a,b in zip(tri,tri[1:]+tri[:1]):edges[tuple(sorted((a,b)))].append(f)
    for(a,b),fs in sorted(edges.items()):
        if len(fs)!=2:raise ValueError('Actual reference shell is not manifold')
        f,g=fs;d=float(ns[f]@ns[g])
        if row['triangle_materials'][f]!=row['triangle_materials'][g]or d<limit:
            locked.update((a,b));records.append({'vertices':[a,b],'faces':fs,'geometric_turn_degrees':math.degrees(math.acos(max(-1.,min(1.,d))))})
    arches=arch_faces(row);locked.update(v for f in arches for v in row['triangles'][f])
    return locked,records

def build(actual,receivers,unused_triangulate=None,*,plane_error=.0001,ratios=(.20,.20,.20)):
    tree,labels=receiver_tree(actual,receivers);parts={};targets={};proof={}
    for n,ratio in zip(ROLES,ratios):
        old=actual[n];target=source_target(old);protected,seams=field_boundaries(old,5.);contacts=[];collars=[]
        for i,p in enumerate(old['vertices']):
            d,f,q,w=tree.nearest(p)
            if d<=.001001:
                protected.add(i);collars.append(i)
                if d<=.001001:contacts.append({'vertex':i,'receiver':labels[f][0],'face':labels[f][1],'distance_m':d,'point':q.tolist()})
        # Exact dimensional support points remain fixed even away from a mate.
        points=np.asarray(old['vertices']);extrema=[]
        for axis in range(3):
            for value in (float(points[:,axis].min()),float(points[:,axis].max())):
                extrema.extend(int(i)for i in np.flatnonzero(points[:,axis]==value))
        protected.update(extrema)
        fixed={i for i,t in enumerate(old['triangles'])if set(t)<=protected}
        result=reduce(old['vertices'],old['triangles'],old['triangle_materials'],protected,plane_error=plane_error,target_triangles=round(len(old['triangles'])*ratio))
        fieldtree=OrientedTree(target);normals=[];uvs={c:[]for c in old['uvs']};reference=[];exactmap={};maximum=0.;minimum=1.
        for f,t in enumerate(result['triangles']):
            source=result['source_face_ids'][f];ps=np.asarray([result['vertices'][v]for v in t]);literal=ps.tolist()==[old['vertices'][v]for v in old['triangles'][source]];gn=np.asarray(unit(np.cross(ps[1]-ps[0],ps[2]-ps[0])));nn=[];uu={c:[]for c in uvs};parents=[]
            for j,p in enumerate(ps):
                if source in fixed or literal:
                    k=[old['vertices'][v]for v in old['triangles'][source]].index(p.tolist());nn.append(target['normal_corner_targets'][source][k])
                    for c in uu:uu[c].append(target['uv_corner_targets'][c][source][k])
                    parents.append({'source_face':source,'corner':k,'projection_m':0.});continue
                d,parent,q,w=fieldtree.nearest_sheet(p,gn)
                if d>.00025:raise ValueError(('Original sheet lookup exceeds strict nearby representation',n,f,j,d,parent))
                maximum=max(maximum,d);normal=unit(np.asarray(w)@np.asarray(target['normal_corner_targets'][parent]));minimum=min(minimum,float(gn@normal));nn.append(normal)
                for c in uu:uu[c].append((np.asarray(w)@np.asarray(target['uv_corner_targets'][c][parent])).tolist())
                parents.append({'source_face':parent,'weights':list(w),'projection_m':d})
            if source in fixed or literal:exactmap[f]=source
            normals.append(nn)
            for c in uvs:uvs[c].append(uu[c])
            reference.append(parents)
        if not fixed<=set(exactmap.values()):raise ValueError('Protected complete finite triangle lost')
        result.update(name=n,materials=old['materials'],normal_corner_targets=normals,uv_corner_targets=uvs);parts[n]=result;targets[n]=target
        proof[n]={'input_triangles':len(old['triangles']),'target_triangles':len(old['triangles']),'output_triangles':len(result['triangles']),'triangle_delta':len(result['triangles'])-len(old['triangles']),'protected_face_map':exactmap,'interface_vertices':contacts,'one_mm_actual_assembly_collar_vertices':collars,'geometric_feature_edges':seams,'geometric_crease_threshold_degrees':65.0,'literal_radial_return_vertices':True,'old_field_seams_are_not_geometry_locks':True,'literal_original_fields_carried':len(exactmap),'exact_dimension_vertices':sorted(set(extrema)),'maximum_design_displacement_m':0.,'maximum_reduced_vertex_projection_m':maximum,'minimum_corner_geometric_hemisphere':minimum,'corner_source_references':reference,'collapse_count':result['collapse_count'],'rejections':result['rejections'],'whole_old_field_equivalence':False,'new_interpolation':'New corner interpolation from finite actual original source fields, encoded directly; original interior interpolation is not claimed identical after topology change'}
        print(n,len(old['triangles']),'->',len(result['triangles']),'locked',len(protected),'projection',maximum,flush=True)
    return {'parts':parts,'targets':targets,'proof':proof,'net_triangles':sum(q['triangle_delta']for q in proof.values()),'whole_surface_and_visual_acceptance':False,'construction':'Actual193 exterior reference retained, no restyling; bounded source-topology reduction with exact assembly collar and physical seam positions'}
