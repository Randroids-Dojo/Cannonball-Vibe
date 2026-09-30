"""Current-input cover construction: returns. Source provenance is in the private port manifest."""

from collections import Counter

import copy

import numpy as np

from . import cover as cover36

from . import domain as domain07

from . import base_mesh as mesh16

from . import front as front358

from . import triangulation as triangulate270

from . import wall_envelope as wall_envelope313

from . import strip as strip331

GAP=.001002

SIDE_INSET=.001202

REACH=.021

REVEAL=.00545

def _smooth(t):
    t=max(0.,min(1.,float(t)))
    return t*t*(3-2*t)

def _side_opening(body,x,zlo,zhi):
    """Entire finite rear boundary of the actual axial inner pocket wall."""
    vv=np.asarray(body['vertices']);tt=np.asarray(body['triangles']);p=vv[tt]
    n=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);ln=np.linalg.norm(n,axis=1)
    sign=1 if x>0 else -1
    keep=np.flatnonzero(np.all(p[:,:,0]==x,axis=1)&(n[:,0]*sign<-.99*ln))
    edges=Counter((int(a),int(b)) for i in keep for a,b in zip(tt[i],np.roll(tt[i],-1)))
    boundary=[(a,b) for (a,b),count in edges.items() if count-edges[(b,a)]==1]
    segments=[]
    for a,b in boundary:
        aa,bb=vv[a],vv[b]
        if aa[2]==bb[2]:continue
        if aa[2]>bb[2]:aa,bb=bb,aa
        lo,hi=max(zlo,aa[2]),min(zhi,bb[2])
        if hi<=lo:continue
        q=[aa+(bb-aa)*((z-aa[2])/(bb[2]-aa[2])) for z in (lo,hi)]
        # Rear-facing chain of this finite side wall. The other side is its
        # actual forward/back plane, separated by >10mm throughout this band.
        segments.append(dict(edge=[a,b],points=q))
    knots=sorted({zlo,zhi}|{float(q[2]) for r in segments for q in r['points']})
    chosen=[]
    for z in knots:
        hits=[]
        for r in segments:
            a,b=r['points']
            if a[2]-1e-12<=z<=b[2]+1e-12:
                y=a[1]+(b[1]-a[1])*((z-a[2])/(b[2]-a[2]))
                hits.append((float(y),r['edge']))
        if not hits:raise ValueError('Actual finite pocket side boundary has a gap')
        y,edge=min(hits)
        chosen.append(dict(z=z,y=y,edge=edge))
    # Finite YZ offset to the rear of every incident actual edge. At each kink
    # the two incident offset lines meet, so no independently shifted seam.
    lines=[]
    for a,b in zip(chosen,chosen[1:]):
        d=np.array([b['y']-a['y'],b['z']-a['z']]);n=np.array([-d[1],d[0]])
        n/=np.linalg.norm(n)
        lines.append((n,float(n@np.array([a['y'],a['z']]))+GAP))
    result=[]
    for i,r in enumerate(chosen):
        if i in (0,len(chosen)-1):
            n,c=lines[0 if i==0 else -1];q=np.array([(c-n[1]*r['z'])/n[0],r['z']])
        else:
            n0,c0=lines[i-1];n1,c1=lines[i]
            if abs(np.linalg.det([n0,n1]))<1e-10:
                q=np.array([r['y'],r['z']])+n0*GAP
            else:q=np.linalg.solve([n0,n1],[c0,c1])
        result.append([x,float(q[0]),float(q[1])])
    return result,dict(actual_faces=keep.tolist(),actual_boundary=chosen,offset_lines=[dict(normal=n.tolist(),constant=c) for n,c in lines])

def outer_layout(cover,reference,body,exact):
    for row in (cover,reference,body):domain07.validate(row)
    vertices=copy.deepcopy(cover['vertices']);nf=cover['front_triangle_count']
    old=copy.deepcopy(cover['triangles'][:nf]);vv=np.asarray(vertices)
    xmin=cover36.f32(.755);xmax=cover36.f32(.82);ztop=cover36.f32(.275)
    zfloor=cover36.f32(.2375);zbottom=cover36.f32(.230)
    selected=[(a,b) for loop in cover['front_boundary'] for a,b in zip(loop,loop[1:]+loop[:1])
        if vv[a,0]*vv[b,0]>0 and min(abs(vv[a,0]),abs(vv[b,0]))>=xmin and max(vv[a,2],vv[b,2])<=ztop]
    if len(selected)!=39:raise ValueError('Actual protected39 upper curve is incomplete')
    base_reveal=.003-cover['common_translation_y_m']
    patch=domain07.projected_carrier(reference)
    lookup={tuple(p):i for i,p in enumerate(vertices)};added=[];domains=[];profiles=[]
    def vertex(p):
        q=tuple(cover36.f32(v) for v in p)
        if q not in lookup:lookup[q]=len(vertices);vertices.append(list(q))
        return lookup[q]
    def emit(t,domain):
        if len(set(t))<3:return
        p=np.asarray([vertices[v] for v in t]);n=np.cross(p[1]-p[0],p[2]-p[0])
        if np.linalg.norm(n)<1e-14:raise ValueError('Collapsed authored return triangle')
        added.append(list(t));domains.append(domain)
    def quad(a,b,c,d,domain):
        # All four points share the same section construction. Shorter diagonal
        # selection is a topology choice, not a displaced boundary or field fit.
        pts=np.asarray([vertices[v] for v in (a,b,c,d)])
        if np.linalg.norm(pts[0]-pts[2])<=np.linalg.norm(pts[1]-pts[3]):
            emit([a,b,c],domain);emit([a,c,d],domain)
        else:emit([a,b,d],domain);emit([b,c,d],domain)
    def polygon(ids,axes,desired,domain):
        ids=[v for i,v in enumerate(ids) if i==0 or v!=ids[i-1]]
        if ids[-1]==ids[0]:ids.pop()
        if len(ids)<3:return
        if len(set(ids))!=len(ids):raise ValueError('Repeated vertex in complete return patch')
        coords={v:tuple(exact.F(vertices[v][j]) for j in axes) for v in ids}
        for t in triangulate270.ears(ids,coords):
            p=np.asarray([vertices[v] for v in t]);n=np.cross(p[1]-p[0],p[2]-p[0])
            emit(list(t) if float(n@desired)>0 else list(reversed(t)),domain)
    for sign in (-1,1):
        ed=[e for e in selected if sign*vertices[e[0]][0]>0]
        nodes=sorted({v for e in ed for v in e},key=lambda v:sign*vertices[v][0])
        if len(nodes)!=len(ed)+1:raise ValueError('Protected curve is not one monotonic section')
        front,b,front_side,front_proof=front358.prepare(cover,reference,exact,vertices,nodes,zbottom,vertex,sign,REVEAL,cover36.f32(zfloor+GAP),body,float(cover36.f32(.81)))
        for t in front:emit(t,'formed_front')
        opening,proof=wall_envelope313.prepare(body,sign*xmax,cover36.f32(zfloor+GAP),ztop)
        end=np.asarray(vertices[nodes[-1]])
        original_inner=np.asarray(cover['vertices'][nodes[-1]+cover['front_vertex_count']])
        upper_turn_forward=min(.0005,float(original_inner[1]-end[1])-.0012-.0002)
        if upper_turn_forward<=0:raise ValueError('Fixed upper inner point leaves no finite turn root')
        g=[];h=[];k=[];j=[];e=[]
        hx=sign*cover36.f32(xmax-3*.0012);jx=sign*(xmax-.010)
        floor_z=cover36.f32(zfloor+GAP)
        def wall_y(z):
            for a,b in zip(opening,opening[1:]):
                if a[2]-1e-9<=z<=b[2]+1e-9:
                    return a[1]+(b[1]-a[1])*(z-a[2])/(b[2]-a[2])
            raise ValueError('Return leaves complete finite wall interval')
        for q in opening:
            q=np.asarray(q);blend=_smooth((ztop-q[2])/.008)
            gz=q[2]
            gx=q[0]
            front_y=domain07.rear_y(gx,gz,patch)[0]-base_reveal-(REVEAL-base_reveal)*_smooth((ztop-gz)/.006)
            # One upper section descends below the unchanged exterior boundary
            # before entering the deep return. Its shared wall plane must still
            # pass complete actual stock and old-boundary checks below.
            gy=wall_y(gz)
            if blend==1:gy=wall_y(gz)
            gg=np.array([gx,gy,gz]);hz=gz;hy=gy
            hh=np.array([hx,hy,hz])
            kz=q[2]
            ky=domain07.rear_y(hx,kz,patch)[0]-base_reveal+REACH
            jy=domain07.rear_y(jx,kz,patch)[0]-base_reveal+REACH
            if min(ky,jy)<=hy:raise ValueError('Actual finite section has no forward closing reach')
            g.append(vertex(gg));h.append(vertex(hh));k.append(vertex([hx,ky,kz]));j.append(vertex([jx,jy,kz]));e.append(vertex([jx,hy,hz]))
        for t in strip331.triangles(vertices,list(reversed(front_side)),g):emit(t,'outer_side')
        for i in range(len(g)-1):
            args=[g[i],h[i],h[i+1],g[i+1]]
            if sign<0:args.reverse()
            quad(*args,'inward_side_bend')
        polygon(h+list(reversed(k)),[1,2],np.array([sign,0,0]),'deep_side')
        for i in range(len(k)-1):
            args=[k[i],j[i],j[i+1],k[i+1]]
            if sign<0:args.reverse()
            quad(*args,'closing_back')
        polygon(e+list(reversed(j)),[1,2],np.array([-sign,0,0]),'inboard_closing_return')
        # The upper surface is a finite stock END closure, constructed only
        # after the whole inner sheet. There is no independent broad top plate.
        floor_front=[v for v in b if abs(vertices[v][0])>=cover36.f32(.81) and vertices[v][2]==floor_z]
        if not floor_front or floor_front[-1]!=front_side[-1]:raise ValueError('Missing complete raised front/floor edge')
        polygon(floor_front+[g[0],h[0],k[0],j[0],e[0]],[0,1],np.array([0,0,-1]),'bottom_return')
        profiles.append(dict(sign=sign,protected_curve=nodes,front_lower=b,side_outer=g,side_inner=h,
            closing_edge=k,closing_inboard=j,open_inboard=e,receiver=proof,front=front_proof,
            upper_turn_forward=upper_turn_forward,upper_inward_start=2*.0012,upper_drop=3*.0012,
            side_inset=xmax-abs(hx),inward_width=.010,shared_floor_z=floor_z))
    # Orient the connected triangulation from the protected original front.
    # Projected polygon choices do not define the side of a nonplanar ramp.
    faces=old+added;inc={}
    for i,t in enumerate(faces):
        for a,b in zip(t,t[1:]+t[:1]):inc.setdefault(tuple(sorted((a,b))),[]).append((i,a,b))
    if any(len(rows)>2 for rows in inc.values()):raise ValueError('Nonmanifold common return edge')
    flip={i:False for i in range(len(old))};todo=list(flip)
    while todo:
        i=todo.pop();t=faces[i]
        for a,b in zip(t,t[1:]+t[:1]):
            for j,c,d in inc[tuple(sorted((a,b)))]:
                if i==j:continue
                expected=flip[i]^((a,b)==(c,d))
                if j in flip:
                    if flip[j]!=expected:raise ValueError('Inconsistent orientable return')
                else:flip[j]=expected;todo.append(j)
    if len(flip)!=len(faces):raise ValueError('Disconnected outer return patch')
    if any(flip[i] for i in range(len(old))):raise ValueError('Original face orientation changed')
    added=[list(reversed(t)) if flip[i+len(old)] else t for i,t in enumerate(added)]
    outer=old+added;boundary=mesh16.loops(outer)
    oldedges={(a,b) for loop in cover['front_boundary'] for a,b in zip(loop,loop[1:]+loop[:1])}
    newedges={(a,b) for loop in boundary for a,b in zip(loop,loop[1:]+loop[:1])}
    shared=sorted(oldedges-newedges)
    if set(shared)!=set(selected):raise ValueError('New return does not share exactly the original39 edges')
    domain07.validate(dict(vertices=vertices,triangles=outer))
    return dict(vertices=vertices,outer=outer,added=added,boundary=boundary,shared=shared,
        authored_patch_domains=domains,profiles=profiles,body_changed=False,
        parameters=dict(gap=GAP,side_inset=SIDE_INSET,reach=REACH,max_front_reveal=REVEAL),
        geometry_authoring='Complete low front fascia plus one finite cup return with shared side, floor, back and top; original39 exact, receiver wholly unchanged.')
