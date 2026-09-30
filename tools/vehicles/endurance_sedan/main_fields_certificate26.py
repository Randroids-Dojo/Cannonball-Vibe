"""Complete retained fields and actual terminal-cell subtraction, no scene IO."""
import math
from collections import Counter
import numpy as np


def points(row,tri):return [np.asarray(row['vertices'][i],dtype=float) for i in tri]
def plane(ps):
    n=np.cross(ps[1]-ps[0],ps[2]-ps[0]);length=np.linalg.norm(n)
    if not length:raise ValueError('Degenerate plane')
    n=n/length;return n,float(n@ps[0])
def bary(p,ps):
    a,b=ps[1]-ps[0],ps[2]-ps[0];d=p-ps[0];aa,ab,bb=a@a,a@b,b@b;det=aa*bb-ab*ab
    if det<=0:raise ValueError('Degenerate field triangle')
    v=(bb*(a@d)-ab*(b@d))/det;w=(aa*(b@d)-ab*(a@d))/det
    return np.array([1-v-w,v,w])


def field_certificate(old,new,indices,partition,area):
    patch=[]
    for ti,t in enumerate(old['triangles']):
        ps=points(old,t);n,d=plane(ps);edges=[]
        for a,b in zip(ps,ps[1:]+ps[:1]):
            inward=np.cross(n,b-a);inward/=np.linalg.norm(inward);edges.append((inward,float(inward@a)-1e-6))
        patch.append((ti,ps,n,d,edges))
    normal_max=0.;uv_max={name:0. for name in old['uvs']};certificates=[];unresolved=[]
    for ni in indices:
        nps=points(new,new['triangles'][ni]);nn,nd=plane(nps);todo=[nps]
        for oi,ops,on,od,edges in patch:
            if nn@on<.99985 or max(abs(float(on@p)-od) for p in nps)>1e-6:continue
            next_todo=[]
            for poly in todo:
                hit,remain=partition(poly,edges);next_todo.extend(remain)
                if not hit or area(hit)==0:continue
                nw=np.asarray([bary(p,nps) for p in hit]);ow=np.asarray([bary(p,ops) for p in hit])
                nloops=new['triangle_loops'][ni];oloops=old['triangle_loops'][oi]
                an=nw@np.asarray([new['normals'][i] for i in nloops]);bn=ow@np.asarray([old['normals'][i] for i in oloops])
                delta=float(np.linalg.norm(an-bn,axis=1).max());lower=min(float((an@on).min()),float((bn@on).min()))
                bound=math.degrees(2*math.asin(min(1,delta/lower))) if lower>0 else 180.
                normal_max=max(normal_max,bound);uv={}
                for name in uv_max:
                    a=nw@np.asarray([new['uvs'][name][i] for i in nloops]);b=ow@np.asarray([old['uvs'][name][i] for i in oloops])
                    uv[name]=float(np.abs(a-b).max());uv_max[name]=max(uv_max[name],uv[name])
                certificates.append({'candidate_triangle':ni,'source_triangle':oi,'complete_polygon':hit,
                    'affine_normal_difference_max':delta,'both_interpolant_length_lower_bound':lower,
                    'whole_polygon_normal_angle_upper_degrees':bound,'whole_polygon_uv_max_abs':uv})
            todo=next_todo
            if not todo:break
        if any(area(p)>0 for p in todo):unresolved.append({'candidate_triangle':ni,'polygons':todo})
    return {'status':'passed' if not unresolved and normal_max<=.025 and max(uv_max.values())<=1e-5 else 'failed',
            'maximum_whole_normal_bound_degrees':normal_max,'maximum_whole_uv_absolute':uv_max,
            'complete_polygons':certificates,'unresolved':unresolved,'candidate_triangles_checked':len(indices)}


def terminal_cell(hose,receiver,scan):
    # The actual authored13-ring /10-sided hose's last straight span is the
    # only span that reaches this receiver. No convex hull replaces its sides.
    count=len(hose['vertices']);sides=10
    if count!=130:raise ValueError('Changed actual hose ring inventory')
    start=count-2*sides
    lo=np.min(np.asarray(receiver['vertices']),axis=0);hi=np.max(np.asarray(receiver['vertices']),axis=0)
    selected=[];near=[]
    for ti,t in enumerate(hose['triangles']):
        ps=np.asarray(points(hose,t))
        if np.all(ps.max(axis=0)>=lo-1e-6) and np.all(ps.min(axis=0)<=hi+1e-6):near.append(ti)
        if all(i>=start for i in t):selected.append(ti)
    if not near or any(ti not in selected for ti in near):raise ValueError('Other hose span reaches original receiver')
    tris=[[i-start for i in hose['triangles'][ti]] for ti in selected]
    cap=list(reversed(range(sides)))
    tris.extend([[cap[0],cap[i],cap[i+1]] for i in range(1,sides-1)])
    row={'name':'ActualMainHoseTerminalCell','vertices':hose['vertices'][start:],'triangles':tris}
    edges=Counter(tuple(sorted((t[i],t[(i+1)%3]))) for t in tris for i in range(3))
    if any(v!=2 for v in edges.values()):raise ValueError('Terminal cell is not closed')
    exact=scan(row)
    if exact['status']!='passed' or exact['bad_pairs']:raise ValueError('Terminal cell self intersects')
    vertices=np.asarray(row['vertices']);kernel=vertices.mean(axis=0)
    margin=min(float(d-n@kernel) for n,d in [plane(points(row,t)) for t in tris])
    if margin<=1e-6:raise ValueError('No strict actual-cell star kernel')
    # Strict kernel behind each actual oriented face proves its outward
    # triangular fan is a union of interior tetrahedra, without re-entry.
    tetra=[]
    for ti,t in enumerate(tris):
        ps=[kernel,*points(row,t)];planes=[]
        for f,opposite in [((0,1,2),3),((0,1,3),2),((0,2,3),1),((1,2,3),0)]:
            n,d=plane([ps[i] for i in f])
            if float(n@ps[opposite]-d)<0:n,d=-n,-d
            planes.append((n,d))
        tetra.append(planes)
    return row,tetra,{'actual_hose_triangle_indices':selected,'receiver_near_hose_triangles':near,
                     'source_ring_vertex_range':[start,count-1],'added_internal_cap_ring':list(range(start,start+sides)),
                     'closed_edge_incidence':True,'exact_self':exact,'strict_kernel':kernel,'minimum_kernel_margin_m':margin,
                     'method':'Actual terminal side/end triangles plus internal ring cap; strict-kernel tetrahedral fan. Every other hose triangle lies outside the receiver AABB.'}


def subtract_actual_cell(old,tetra,partition,area):
    vertices=[];triangles=[];kept=[];removed=[]
    for ti,t in enumerate(old['triangles']):
        todo=[points(old,t)]
        for planes in tetra:
            remaining=[]
            for poly in todo:
                hit,outside=partition(poly,planes)
                remaining.extend(outside)
                if hit and area(hit)>0:removed.append({'triangle':ti,'polygon':hit})
            todo=remaining
            if not todo:break
        for poly in todo:
            if not poly or area(poly)==0:continue
            start=len(vertices);vertices.extend(poly);kept.append({'original_triangle':ti,'polygon':poly})
            for i in range(1,len(poly)-1):
                if np.linalg.norm(np.cross(poly[i]-poly[0],poly[i+1]-poly[0]))>0:triangles.append([start,start+i,start+i+1])
    return {'name':'OriginalRadiatorOutsideActualTerminalCell','vertices':vertices,'triangles':triangles},kept,removed
