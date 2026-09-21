"""Current-input cover construction: front. Source provenance is in the private port manifest."""

from collections import defaultdict, Counter

import numpy as np

from . import cover as cover36

from . import partition as form09

from . import layout as layout11

from . import base_mesh as mesh16

from . import triangulation as triangulate270

def prepare(cover,reference,exact,vertices,nodes,zbottom,vertex,sign,reveal,floor_z,body,inboard_x):
    base_reveal=.003-cover['common_translation_y_m']
    # Retained curve vertices are not fit samples: their exact current edges
    # delimit the whole authored patch. First low edges belong to the bottom.
    active=0
    start=nodes[active];after=nodes[active+1]
    # One lower section tied to the actual cup and finite floor boundary.
    vv=np.asarray(body['vertices']);tt=np.asarray(body['triangles']);pp=vv[tt]
    floor_level=cover36.f32(.2375)
    nn=np.cross(pp[:,1]-pp[:,0],pp[:,2]-pp[:,0])
    floor_ids=np.flatnonzero(np.all(pp[:,:,2]==floor_level,axis=1)&(nn[:,2]>0))
    incident=Counter((int(a),int(b)) for i in floor_ids for a,b in zip(tt[i],np.roll(tt[i],-1)))
    boundary=[(a,b) for a,b in incident if incident[a,b]-incident[b,a]==1]
    candidates=sorted({v for edge in boundary for v in edge
        if inboard_x<sign*vv[v,0]<abs(vertices[nodes[-1]][0]) and -2.46<vv[v,1]<-2.38},key=lambda v:sign*vv[v,0])
    if not candidates:raise ValueError('Current finite floor has no terminal rear corner beyond the closing plane')
    end_vertex=candidates[0];end_x=sign*float(vv[end_vertex,0])
    if end_x-inboard_x<.0012:raise ValueError('Complete floor corner leaves no stock-width lower transition')
    lower=[(vertices[start][0],zbottom),(sign*cover36.f32(inboard_x),zbottom)]
    for f in (.25,.5,.75,1.):
        x=inboard_x+(end_x-inboard_x)*f;t=f*f*(3-2*f)
        lower.append((sign*cover36.f32(x),cover36.f32(zbottom+(floor_z-zbottom)*t)))
    lower.append((vertices[nodes[-1]][0],floor_z))
    lower_proof=dict(inboard_closing_plane_x_m=sign*inboard_x,floor_level_m=floor_level,
        complete_floor_triangles=floor_ids.tolist(),complete_oriented_floor_boundary=boundary,
        current_terminal_corner=end_vertex,current_corner_point=vv[end_vertex].tolist(),
        candidate_corner_inventory=candidates,ray_coordinates_used=False)
    upper=[tuple(exact.F(vertices[v][j]) for j in (0,2)) for v in nodes[active:]]
    polygon=upper+[(exact.F(x),exact.F(z)) for x,z in reversed(lower)]
    polygon=[q for i,q in enumerate(polygon) if i==0 or q!=polygon[i-1]]
    if polygon[-1]==polygon[0]:polygon.pop()
    patch=form09.exact_patches(reference,exact);groups=defaultdict(list)
    for ids in triangulate270.ears(list(range(len(polygon))),dict(enumerate(polygon))):
        tri=[(polygon[i][0],exact.F(0),polygon[i][1]) for i in ids]
        for poly,owner in form09.partition(tri,patch,exact):
            if owner is None:raise ValueError('Front transition leaves the actual finite carrier')
            q=[(p[0],p[2]) for p in poly]
            if len(q)>=3 and sum(layout11.cross2(a,b) for a,b in zip(q,q[1:]+q[:1])):groups[owner['index']].append(q)
    polys=[dict(owner=o,points=q) for o,pieces in groups.items() for q in layout11.boundary(pieces)]
    coeff={r['index']:r['coeff'] for r in patch}
    protected={tuple(exact.F(vertices[v][j]) for j in (0,2)):v for v in nodes}
    owner_sets=defaultdict(set)
    for r in polys:
        for q in r['points']:owner_sets[q].add(r['owner'])
    for r in polys:
        p=r['points'];r['points']=[q for i,q in enumerate(p) if q in protected or len(owner_sets[q])>=3 or layout11.cross2(layout11.sub2(q,p[i-1]),layout11.sub2(p[(i+1)%len(p)],q))]
    pool={q for r in polys for q in r['points']}
    native_xz={tuple(vertices[v][j] for j in (0,2)):v for v in nodes};triangles=[];metadata=[]
    def upper_z(x):
        for a,b in zip(nodes,nodes[1:]):
            xa,xb=sign*vertices[a][0],sign*vertices[b][0]
            if xa-1e-7<=sign*x<=xb+1e-7:return vertices[a][2]+(vertices[b][2]-vertices[a][2])*(sign*x-xa)/(xb-xa)
        raise ValueError('New finite front point lacks protected curve interval')
    for r in polys:
        ids=[];conformed=[]
        for a,b in zip(r['points'],r['points'][1:]+r['points'][:1]):
            edge=layout11.sub2(b,a);axis=0 if edge[0] else 1
            qs=[q for q in pool if layout11.cross2(layout11.sub2(q,a),edge)==0 and min(a[0],b[0])<=q[0]<=max(a[0],b[0]) and min(a[1],b[1])<=q[1]<=max(a[1],b[1])]
            qs.sort(key=lambda q:(q[axis]-a[axis])/edge[axis]);conformed+=qs[:-1]
        aa,bb,cc=coeff[r['owner']]
        for x,z in conformed:
            if (x,z) in protected:v=protected[(x,z)]
            else:
                tx,tz=float(x),float(z);t=max(0.,min(1.,(upper_z(tx)-tz)/.006));t=t*t*(3-2*t);sx=max(0.,min(1.,(abs(tx)-float(cover36.f32(.755)))/.008));t*=sx*sx*(3-2*sx)
                native=[cover36.f32(tx),cover36.f32(float(aa*x+bb*z+cc)-base_reveal-(reveal-base_reveal)*t),cover36.f32(tz)]
                close=[v for v in nodes if np.linalg.norm(np.asarray(vertices[v])-np.asarray(native))<=1e-6]
                if len(close)>1:raise ValueError('Ambiguous fixed native boundary')
                if close:v=close[0]
                else:
                    key=tuple(native[j] for j in (0,2))
                    if key in native_xz:
                        v=native_xz[key]
                        if np.linalg.norm(np.asarray(vertices[v])-native)>1e-6:raise ValueError('Inconsistent shared carrier boundary')
                    else:v=vertex(native);native_xz[key]=v
            if not ids or ids[-1]!=v:ids.append(v)
        if len(ids)>1 and ids[-1]==ids[0]:ids.pop()
        if len(set(ids))<3:continue
        coords={v:tuple(exact.F(vertices[v][j]) for j in (0,2)) for v in ids}
        area=sum(layout11.cross2(coords[a],coords[b]) for a,b in zip(ids,ids[1:]+ids[:1]))
        if not area:continue
        for t in triangulate270.ears(ids,coords):
            p=np.asarray([vertices[v] for v in t]);n=np.cross(p[1]-p[0],p[2]-p[0]);triangles.append(list(t) if n[1]<0 else list(reversed(t)));metadata.append(r['owner'])
    boundary=mesh16.loops(triangles)
    ids={v for loop in boundary for v in loop}
    front_side=sorted([v for v in ids if vertices[v][0]==vertices[nodes[-1]][0]],key=lambda v:vertices[v][2],reverse=True)
    if front_side[0]!=nodes[-1]:raise ValueError('Current upper side endpoint is not exact')
    lower_ids=set(nodes[:active+1])
    for v in ids:
        q=np.array([vertices[v][0],vertices[v][2]])
        for a,b in zip(lower,lower[1:]):
            a,b=np.asarray(a),np.asarray(b);d=b-a;f=float((q-a)@d/(d@d))
            if -1e-6<=f<=1+1e-6 and np.linalg.norm(q-(a+f*d))<=1e-7:lower_ids.add(v)
    bottom=sorted(lower_ids,key=lambda v:sign*vertices[v][0])
    if bottom[-1]!=front_side[-1]:raise ValueError('Side and bottom do not share the same front knot')
    return triangles,bottom,front_side,dict(actual_carrier_owners=metadata,whole_lower_profile=lower,active_curve=nodes[active:],receiver_lower_section=lower_proof)
