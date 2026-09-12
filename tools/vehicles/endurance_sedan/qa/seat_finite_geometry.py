"""Portable complete finite seat predicates. No historical payload or source loader.

Functions below retain the reviewed whole-domain fit36/tuck40 algorithms.
Current carrier support planes, sockets and assembly parameters are derived
separately from the supplied source rows by seat_finish_interfaces.
"""
from collections import Counter
import copy
import math
import numpy as np
from mathutils import Vector
from geometry import Mesh
from self_geometry import scan
import finish_interfaces as fi


def cap(row, normal, constant):
    ids=[i for i,t in enumerate(fi.triangles(row)) if max(abs(t@normal-constant))<=1e-7]
    fi.require(bool(ids), 'Missing finite cap: '+row['name'])
    return fi.subset(row,ids,'_cap')


def clipped_boundary(row,normal,constants,contraction):
    planes=[(-n,-d+contraction) for n,d in zip(normal,constants)]
    fragments=[]
    for i,tri in enumerate(fi.triangles(row)):
        inside,_=fi.partition(list(tri),planes)
        if inside:fragments.append({'triangle':i,'vertices_m':[p.tolist() for p in inside]})
    return fragments


def socket(post,carrier,params,endpoint):
    points=np.array(post['vertices']);axis=np.array(params['axis'])
    # A convex straight prism encloses every actual post vertex; it does not
    # assume that native triangulated tube side quads are exactly coplanar.
    # The extra radial 0.3 mm is smaller than the actual 1.2 mm socket gap.
    radial=[]
    for a,b in zip(points[:8],np.roll(points[:8],-1,axis=0)):
        n=np.cross(b-a,axis);n/=np.linalg.norm(n)
        if float(n@(a-points[:8].mean(0)))<0:n=-n
        radial.append(n)
    normal=np.array(radial+[axis,-axis])
    constants=np.array([float((points@n).max())+.0003 for n in radial]+
                       [float((points@axis).max()),-float((points@axis).min())])
    residual=float((points@normal.T-constants).max())
    assert residual<=1e-12
    # Use a tighter internal test than the unchanged 1 um interface guard.
    contraction=5e-7
    fragments=clipped_boundary(carrier,normal,constants,contraction)
    center=np.array(post['vertices']).mean(0)
    outside=Mesh(carrier).inside(Vector(center))
    assert outside is not None and all(c%2==0 for c in outside['ray_hit_counts'])
    end=np.array(params['center0' if endpoint==0 else 'center1'])
    endpoint_cap=cap(post,axis,float(axis@end))
    support=fi.surface_cover(endpoint_cap,carrier)
    result={'status':'passed' if not fragments and support['status']=='passed' else 'failed',
            'post':post['name'],'carrier':carrier['name'],'actual_post_enclosing_plane_residual_m':residual,
            'enclosing_prism_planes':[{'outward':n.tolist(),'constant_m':float(d)} for n,d in zip(normal,constants)],
            'radial_prism_expansion_m':.0003,'contraction_m':contraction,'complete_carrier_triangles':len(carrier['triangles']),
            'carrier_boundary_in_contracted_post':fragments,'interior_reference_point':center.tolist(),
            'interior_outside_carrier_three_rays':outside,'complete_actual_endpoint_support':support,
            'scope':'Every actual post vertex and its complete closed solid lie inside the declared convex prism. No carrier boundary enters its connected interior beyond the 0.5 um endpoint guard, and an interior point is outside the carrier. Radial expansion ensures actual post side surfaces remain strictly inside the checked prism. All actual finite endpoint triangles have support. The endpoint guard is stricter than the unchanged 1 um interface guard; no diagnostic volume is waived.'}
    return result


def pouch(pouch,backing,params):
    normal=np.array(params['actual_rear_normal']);d=params['plane_constant']
    p=np.array(pouch['vertices'])@normal-d;b=np.array(backing['vertices'])@normal-d
    support=fi.surface_cover(cap(pouch,normal,d),backing)
    return {'status':'passed' if p.min()>=-1e-6 and b.max()<=1e-6 and support['status']=='passed' else 'failed',
            'minimum_pouch_outward_m':float(p.min()),'maximum_backing_outward_m':float(b.max()),
            'complete_mount_support':support,'method':'Complete bounded closed solids occupy opposing actual backing-plane halfspaces; all pouch mounting triangles supported.'}


def pad(pad,switch,frame,params):
    low=params['outer_plane_x'];high=params['inner_plane_x']
    p=np.array(pad['vertices'])[:,0];s=np.array(switch['vertices'])[:,0];f=np.array(frame['vertices'])[:,0]
    a=fi.surface_cover(cap(pad,np.array([1.,0.,0.]),low),switch)
    b=fi.surface_cover(cap(pad,np.array([1.,0.,0.]),high),frame)
    return {'status':'passed' if min(p)>=low-1e-6 and max(p)<=high+1e-6 and max(s)<=low+1e-6 and min(f)>=high-1e-6 and a['status']==b['status']=='passed' else 'failed',
            'complete_cap_support':[a,b],'pad_interval_m':[float(min(p)),float(max(p))],
            'switch_maximum_m':float(max(s)),'frame_minimum_m':float(min(f)),
            'method':'All actual vertices and therefore full closed solids occupy three ordered opposing X halfspaces, with two complete cap supports.'}


def add_box(row,low,high):
    result=copy.deepcopy(row);offset=len(result['vertices'])
    points=[[float(x),float(y),float(z)] for z in (low[2],high[2]) for y in (low[1],high[1]) for x in (low[0],high[0])]
    faces=[[0,2,3],[0,3,1],[4,5,7],[4,7,6],[0,1,5],[0,5,4],[2,6,7],[2,7,3],[0,4,6],[0,6,2],[1,3,7],[1,7,5]]
    result['vertices']+=points;result['triangles'] += [[offset+i for i in face] for face in faces]
    return result


def sewn(seam,foam,radius,axes,allowed):
    sp=fi.triangles(seam)@axes.T
    low=sp.min((0,1))-np.array([2e-6,2e-6,2*radius+2e-6])
    high=sp.max((0,1))+np.array([2e-6,2e-6,2*radius+2e-6])
    planes=[(sign*axis,float(sign*(low if sign>0 else high)[i])) for i,axis in enumerate(np.eye(3)) for sign in (1,-1)]
    polygons=[];rows=[];wrong=[]
    for index,tri in enumerate(fi.triangles(foam)@axes.T):
        inside,_=fi.partition(list(tri),planes)
        if not inside:continue
        normal=fi.unit(np.cross(tri[1]-tri[0],tri[2]-tri[0]))
        item={'foam_triangle':index,'outward_axis_component':float(normal[2]),'polygon_local_m':[p.tolist() for p in inside]}
        rows.append(item)
        if normal[2]<=0:wrong.append(item)
        polygons.append([p@axes for p in inside])
    if not polygons:
        return {'status':'failed_no_local_boundary','pair':[seam['name'],foam['name']],
                'complete_prism_bounds_m':[low.tolist(),high.tolist()],'actual_all_foam_triangles_checked':len(foam['triangles'])}
    local=fi.polygon_mesh(polygons,foam['name']+'_complete_local_boundary')
    result=fi.cloth_joint(seam,local,radius,axes)
    witness=((low+high)/2);witness[2]=high[2]-1e-6
    outside=Mesh(foam).inside(Vector(witness@axes))
    certified_outside=outside is not None and all(q%2==0 for q in outside['ray_hit_counts'])
    distances=result['complete_surface_signed_distance_range_m']
    route=all(not row['uncovered_intervals'] for row in result['complete_route_spans'])
    status='passed_proposed_finite_sewn_domain' if not wrong and certified_outside and not result['uncovered_footprint'] and route and distances and distances[0]>=-allowed-1e-6 else 'failed'
    return {'status':status,'pair':[seam['name'],foam['name']],'radius_m':radius,'declared_maximum_intrusion_m':allowed,
            'construction_policy':'Existing15%-radius cushion stitch' if allowed==.15*radius else 'Proposed soft back-welt tuck bounded by one actual welt diameter; root design acceptance remains pending.',
            'complete_prism_bounds_m':[low.tolist(),high.tolist()],
            'actual_all_foam_triangles_checked':len(foam['triangles']),'complete_local_boundary':rows,
            'non_front_boundary_fragments':wrong,'whole_prism_top_outside_witness_m':(witness@axes).tolist(),
            'prism_top_outside_foam_three_rays':outside,'complete_local_cloth_proof':result,
            'argument':'Every actual foam boundary triangle is clipped to the whole thread prism. All admitted boundaries face outward along its height axis, and a top witness is outside. Thus no hidden lower-facing layer may occupy the checked prism. Every local height chart participates independently; complete footprint and route proofs are separate. Remote charts outside this certified prism are not treated as contact.'}


def canonical(face):return min(tuple(face[i:]+face[:i]) for i in range(3))


def segments(row):
    vertices=np.array(row['vertices']);rings=vertices.reshape(-1,4,3);result=[];combined=Counter()
    for index in range(len(rings)-1):
        faces=[f[:] for f in row['triangles'] if {i//4 for i in f}=={index,index+1}]
        delta=rings[index+1].mean(0)-rings[index].mean(0)
        for ring,sign in ((index,-1),(index+1,1)):
            actual=[f[:] for f in row['triangles'] if {i//4 for i in f}=={ring}]
            if actual:faces+=actual;continue
            cap=[[ring*4,ring*4+1,ring*4+2],[ring*4,ring*4+2,ring*4+3]]
            for face in cap:
                a,b,d=vertices[face]
                if float(np.cross(b-a,d-a)@delta)*sign<0:face.reverse()
                faces.append(face)
        combined.update(canonical(face) for face in faces)
        part={'name':row['name']+f'_solid_segment{index}','vertices':vertices[index*4:index*4+8].tolist(),
              'triangles':[[i-index*4 for i in face] for face in faces],'properties':{}}
        fi.validate_row(part['name'],part)
        assert scan(part)['status']=='passed'
        result.append(part)
    for face in list(combined):
        reverse=canonical(list(reversed(face)));count=min(combined[face],combined[reverse])
        combined[face]-=count;combined[reverse]-=count
    assert +combined==Counter(canonical(f) for f in row['triangles'])
    return result


def certificate(row,foam,maximum=.0016):
    parts=segments(row);target=fi.triangles(foam);native=Mesh(foam)
    records=[];unresolved=[];cells=0;domains=[]
    for part_index,part in enumerate(parts):
        tri=fi.triangles(part);v=np.array(part['vertices'])
        axis=fi.unit(v[4:].mean(0)-v[:4].mean(0));coordinates=v@axis
        domain=[float(coordinates.min()),float(coordinates.max())]
        domains.append({'segment':part_index,'axial_interval_m':domain})
        todo=[(*domain,0)]
        while todo:
            low,high,depth=todo.pop();cells+=1
            polygons=[]
            for face in tri:
                inside,_=fi.partition(list(face),[(axis,low),(-axis,-high)])
                if inside:polygons.append(inside)
            points=np.array(list(dict.fromkeys(tuple(q) for polygon in polygons for q in polygon)))
            if not len(points):continue
            selected=set()
            for point in list(points)+[points.mean(0)]:
                hit= native.bvh.find_nearest(Vector(point))
                if hit[0] is not None:selected.add(int(hit[2]))
            candidates=[]
            for index in selected:
                bound=max(float(np.linalg.norm(point-fi.point_triangle(point,target[index]))) for point in points)
                candidates.append((bound,index))
            bound,owner=min(candidates,default=(math.inf,-1))
            if bound<=maximum-1e-9:
                records.append({'segment':part_index,'axial_interval_m':[low,high],'depth':depth,'foam_triangle':owner,
                                'complete_solid_convex_distance_upper_bound_m':bound,'boundary_vertex_count':len(points)})
                continue
            bad=[]
            for point in points:
                hit=native.bvh.find_nearest(Vector(point))
                if hit[0] is not None and hit[3]>maximum+1e-6:
                    bad.append({'actual_segment_boundary_point_m':point.tolist(),'native_nearest_distance_m':float(hit[3]),
                                'nearest_foam_point_m':list(hit[0]),'foam_triangle':int(hit[2])})
            if bad or depth>=20 or cells>50000:
                unresolved.append({'segment':part_index,'interval_m':[low,high],'depth':depth,
                                   'current_convex_bound_m':bound,'boundary_counterexamples':bad})
                return {'status':'failed_whole_solid_certificate','segments':len(parts),'cells':cells,'accepted_cells':records,'unresolved':unresolved}
            mid=(low+high)/2;todo.extend([(low,mid,depth+1),(mid,high,depth+1)])
    return {'status':'passed_complete_welt_solid_bound','segments':len(parts),'segment_domains_m':domains,'cells':cells,'accepted_cells':records,'unresolved':[],
            'maximum_whole_solid_distance_m':max(q['complete_solid_convex_distance_upper_bound_m'] for q in records),
            'method':'Exact original side facets plus canceling shared internal caps partition the entire closed welt into actual closed/self-clear segments. Parallel axial slabs partition each complete segment. Every slab solid lies in the convex hull of all clipped boundary vertices; distance to one actual convex foam triangle is convex, so the maximum vertex distance bounds the whole volume. Slabs are only accepted by this upper bound, never by samples or area.'}


def finite_overlap(row,foam):
    a,b=Mesh(row),Mesh(foam);rings=np.array(row['vertices']).reshape(-1,4,3);witnesses=[]
    for index in range(len(rings)-1):
        for t in (.25,.5,.75):
            point=(1-t)*rings[index].mean(0)+t*rings[index+1].mean(0)
            first,second=a.inside(Vector(point)),b.inside(Vector(point))
            if first is not None and second is not None and all(k%2==1 for k in first['ray_hit_counts']+second['ray_hit_counts']):
                radius=min(first['surface_distance_m'],second['surface_distance_m'])-1e-6
                if radius>0:witnesses.append({'segment':index,'fraction':t,'point_m':point.tolist(),'interior_ball_radius_m':radius,
                                             'thread_inside':first,'foam_inside':second})
    return max(witnesses,key=lambda q:q['interior_ball_radius_m']) if witnesses else None


def embedded_route(row,foam,route):
    rings=np.array(row['vertices']).reshape(-1,4,3)
    centers=rings.mean(1)
    target=fi.triangles(foam)
    low,high=target.min(1),target.max(1)
    native=Mesh(foam)
    accepted=[];unresolved=[];cells=0
    core_radius=.00005
    for entry in route:
        index=entry['segment']
        start,end=centers[index:index+2]
        todo=[(float(a),float(b),0) for a,b in entry['uncovered_intervals']]
        while todo:
            a,b,depth=todo.pop();cells+=1
            ends=np.array([(1-t)*start+t*end for t in (a,b)])
            proof=None
            for fraction in (.5,.37,.63):
                center=(1-fraction)*ends[0]+fraction*ends[1]
                radius=float(np.linalg.norm(ends-center,axis=1).max())+core_radius
                box_delta=np.maximum(0,np.maximum(low-center,center-high))
                bounds=np.linalg.norm(box_delta,axis=1)
                selected=np.flatnonzero(bounds<=radius+1e-6)
                exact=[float(np.linalg.norm(center-fi.point_triangle(center,target[i]))) for i in selected]
                excluded=bounds[bounds>radius+1e-6]
                boundary_lower=min([*exact,float(excluded.min()) if len(excluded) else float('inf')])
                if boundary_lower<=radius+1e-6:
                    continue
                inside=native.inside(Vector(center))
                if inside is None or not all(c%2==1 for c in inside['ray_hit_counts']):
                    continue
                proof={'segment':index,'original_route_interval':[a,b],'subdivision_depth':depth,
                       'center_m':center.tolist(),'complete_capsule_enclosing_radius_m':radius,
                       'finite_embedded_core_radius_m':core_radius,'all_actual_boundary_distance_lower_bound_m':boundary_lower,
                       'whole_ball_clearance_margin_m':boundary_lower-radius,
                       'foam_triangles_total':len(target),'whole_aabb_exclusions':len(target)-len(selected),
                       'exact_point_triangle_checks':len(selected),'point_inside_three_rays':inside}
                break
            if proof:
                accepted.append(proof)
            elif depth>=20 or cells>20000:
                unresolved.append({'segment':index,'original_route_interval':[a,b],'depth':depth})
            else:
                middle=(a+b)/2
                todo.extend([(a,middle,depth+1),(middle,b,depth+1)])
    return {'status':'passed_complete_embedded_route' if not unresolved else 'failed_embedded_route',
            'cells':cells,'intervals':accepted,'unresolved_intervals':unresolved,
            'finite_core_radius_m':core_radius,
            'method':'Every retained interval is enclosed with its complete50um-radius centerline capsule in a ball. All actual foam triangles are either excluded by a whole AABB distance lower bound or checked by binary64 point/triangle distance. No foam boundary intersects the ball and its center is inside on all3 rays. Thus its complete connected volume, including the entire route interval, is inside the receiving foam. This proves embedded support, not suspended visible piping.'}
