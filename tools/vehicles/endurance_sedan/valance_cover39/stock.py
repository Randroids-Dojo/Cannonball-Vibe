"""Current-input cover construction: stock. Source provenance is in the private port manifest."""

from collections import defaultdict

import copy

import numpy as np

from . import cover as cover36

from . import domain as domain07

from . import base_mesh as mesh16

from .corners import _minimum_norm

GAUGE=.0012

NATIVE_GUARD=1e-6

def prepare(cover, layout, exact, inner_solver=None, finite_sheet_constraints=None):
    """Explicit supplied shared outer layout; no hidden construction state or I/O."""
    layout=copy.deepcopy(layout)
    vertices=layout['vertices'];outer=layout['outer'];added=layout['added']
    count=cover['front_vertex_count'];nf=cover['front_triangle_count']
    lookup={tuple(p):i for i,p in enumerate(vertices)}
    oldvv=np.asarray(cover['vertices']);oldtr=np.asarray(cover['triangles'])
    outer_id_by_vertices={tuple(sorted(t)):i for i,t in enumerate(oldtr[:nf])}
    inner=[];pieces=[];point_meta={};movable=set()
    lowerx=float(np.float32(.755));upperz=float(np.float32(.275))
    old_nodes={exact.vector(p):i for i,p in enumerate(vertices)}

    def barycentric(p,t):
        a,b,c=t;ab=b-a;ac=c-a;ap=np.asarray(p)-a
        uv=np.linalg.solve(np.array([[ab@ab,ab@ac],[ab@ac,ac@ac]]),[ab@ap,ac@ap])
        return np.array([1-uv.sum(),uv[0],uv[1]])

    # One finite partition per actual source triangle. A global exact node pool
    # is conformed across every resulting edge before triangulation.
    polygons=[]
    for oi,(t,domain) in enumerate(zip(cover['triangles'],cover['triangle_domains'])):
        if domain!='inner':continue
        p=[exact.vector(cover['vertices'][v]) for v in t]
        sign=1 if sum(q[0] for q in p)>=0 else -1
        band=[((exact.F(sign),exact.F(0),exact.F(0)),exact.F(lowerx)),
              ((exact.F(0),exact.F(0),exact.F(-1)),exact.F(-upperz))]
        hit,outside=exact.partition(p,band)
        # If the complete band misses a face, earlier partial clips are not an
        # ownership change; preserve the original complete face.
        if not hit:groups=[(p,False)]
        else:groups=[(q,False) for q in outside]+[(hit,True)]
        for poly,inside in groups:
            if len(poly)>=3:polygons.append(dict(old=oi,poly=poly,inside=inside))
    all_nodes={q for part in polygons for q in part['poly']}
    for part in polygons:
        poly=part['poly'];split=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            axis=next(j for j in range(3) if a[j]!=b[j]);step=tuple(b[j]-a[j] for j in range(3))
            nodes=[]
            for q in all_nodes:
                f=(q[axis]-a[axis])/step[axis]
                if 0<=f<1 and all(q[j]==a[j]+f*step[j] for j in range(3)):nodes.append((f,q))
            split.extend(q for f,q in sorted(nodes))
        oi=part['old'];oldids=cover['triangles'][oi];oldpoints=oldvv[oldids]
        ids=[]
        for q in split:
            native=tuple(cover36.f32(x) for x in q)
            if native not in lookup:lookup[native]=len(vertices);vertices.append(list(native))
            v=lookup[native];ids.append(v)
            w=barycentric(native,oldpoints)
            original_outer=[j-count for j in oldids]
            point_meta[v]=dict(outer_point=(w@oldvv[original_outer]).tolist(),old_inner_point=list(native))
            if abs(native[0])>lowerx+1e-8 and native[2]<upperz-1e-8:movable.add(v)
        n=np.cross(oldpoints[1]-oldpoints[0],oldpoints[2]-oldpoints[0]);axes=[j for j in range(3) if j!=int(np.argmax(np.abs(n)))]
        coords={v:tuple(exact.F(vertices[v][j]) for j in axes) for v in ids}
        for t in mesh16.ears(ids,coords):
            pieces.append(dict(old=oi,ids=list(t),inside=part['inside']))
            inner.append(dict(ids=list(t),outer=outer_id_by_vertices[tuple(sorted(j-count for j in oldids))]))
    outer_to_inner={i:i+count for i in range(count)}
    new_outer=sorted({v for t in added for v in t}-set(range(count)))
    for v in new_outer:
        i=len(vertices);outer_to_inner[v]=i;vertices.append(vertices[v].copy());movable.add(i)
        point_meta[i]=dict(outer_point=vertices[v].copy(),old_inner_point=vertices[v].copy())
    for oi,t in enumerate(added,start=nf):inner.append(dict(ids=[outer_to_inner[v] for v in reversed(t)],outer=oi))
    vv=np.asarray(vertices,dtype=float);ot=vv[np.asarray(outer)]
    constraints=defaultdict(list)
    for row in inner:
        p=ot[row['outer']];n=-cover36.unit(np.cross(p[1]-p[0],p[2]-p[0]));c=float(n@p[0])+GAUGE
        for v in row['ids']:constraints[v].append((n,c))
    # Complete lower side/floor receiving interval belongs to the same solve.
    # Apply it to both ends of the common finite closing rim, as established
    # by corner317; no unrelated-body pair or old-field exemption is introduced.
    receiver_constraints={}
    for pr in layout['profiles']:
        eligible=set(pr['side_outer'])|{pr['side_inner'][0]}
        for ov in eligible:
            iv=outer_to_inner[ov];z=vv[ov,2];hi=z+GAUGE if ov in (pr['side_outer'][0],pr['side_inner'][0]) else z
            selected=[]
            for line,a,b in zip(pr['receiver']['offset_lines'],pr['receiver']['generated_boundary'],pr['receiver']['generated_boundary'][1:]):
                if a['z']<=hi+1e-7 and b['z']>=z-1e-7:
                    ny,nz=line['normal'];selected.append((np.array([0.,ny,nz]),line['constant']))
            constraints[iv].extend(selected);receiver_constraints[iv]=selected
    fixed_original_inner={v for part in pieces if not part['inside'] for v in part['ids']}
    shared_inner={v+count for pr in layout['profiles'] for v in pr['protected_curve']}
    movable-=fixed_original_inner
    for v in movable:constraints[v].append((np.array([0.,0.,1.]),float(np.float32(.230))))
    complete_floor_records=[]
    if finite_sheet_constraints is not None:
        extra,complete_floor_records=finite_sheet_constraints(vv,inner,constraints,movable)
        for v,planes in extra.items():constraints[v].extend(planes)
    fixed_conflicts=[];solutions=[]
    for v,planes in constraints.items():
        if v not in movable:
            deficit=max(c-float(n@vv[v]) for n,c in planes)
            if deficit>NATIVE_GUARD:fixed_conflicts.append(dict(vertex=v,normal_stock_deficit_m=deficit,point=vv[v].tolist()))
            continue
        # Deduplicate nearly identical constraints only for computation; every
        # original plane is checked again against the resulting native point.
        unique={tuple(np.round(n,10))+ (round(c,10),):(n,c) for n,c in planes}
        q=_minimum_norm(list(unique.values()),vv[v]) if inner_solver is None else inner_solver(v,list(unique.values()),vv[v])
        native=np.asarray(q,dtype=np.float32).astype(float)
        solutions.append(dict(vertex=v,old=vv[v].tolist(),requested=q.tolist(),native=native.tolist(),
                              maximum_native_plane_deficit_m=max(c-float(n@native) for n,c in planes)))
        vv[v]=native
    vertices=vv.tolist()
    # Build every face against the same solved vertex table. No independently
    # clipped old/new sheet can leave an unmatched seam or hidden T-junction.
    shared={tuple(sorted(e)) for e in layout['shared']}
    redundant_caps=[]
    triangles=[];domains=[];targets=[];uvs={n:[] for n in cover['triangle_uvs']};retained=[];outside=[]
    def add(t,d,ns=None,old=None,weights=None):
        p=vv[t];cross=np.cross(p[1]-p[0],p[2]-p[0])
        if not np.linalg.norm(cross):
            if d!='terminal_rim':raise ValueError('Non-cap zero-area construction')
            ep=[exact.vector(q) for q in p]
            if any(exact.cross(exact.sub(ep[1],ep[0]),exact.sub(ep[2],ep[0]))):raise ValueError('Uncertified collapsed cap')
            redundant_caps.append(dict(vertices=list(t),points=p.tolist(),reason='Three existing boundary knots are exactly collinear; split the adjacent actual edge, with no positive-area surface removed.'))
            return None
        n=cover36.unit(cross).tolist()
        triangles.append(list(t));domains.append(d);targets.append(ns if ns is not None else [n]*3)
        axes=[0,2] if abs(n[1])>=max(abs(n[0]),abs(n[2])) else [j for j in range(3) if j!=int(np.argmax(np.abs(n)))]
        for name in uvs:
            if old is None:values=[[vertices[v][j]*4 for j in axes] for v in t]
            elif weights is None:values=copy.deepcopy(cover['triangle_uvs'][name][old])
            else:values=[(w@np.asarray(cover['triangle_uvs'][name][old])).tolist() for w in weights]
            uvs[name].append(values)
        return len(triangles)-1
    for oi,(t,d) in enumerate(zip(cover['triangles'],cover['triangle_domains'])):
        if d=='inner':continue
        ids={v if v<count else v-count for v in t}
        if d=='rim' and len(ids)==2 and tuple(sorted(ids)) in shared:continue
        if any(vertices[v]!=cover['vertices'][v] for v in t):raise ValueError('Protected outer/rim vertex changed')
        retained.append([oi,add(t,d,cover['requested_triangle_normals'][oi],oi)])
    old_targets={v:n for t,ns in zip(cover['triangles'][:nf],cover['requested_triangle_normals'][:nf]) for v,n in zip(t,ns)}
    sums=defaultdict(lambda:np.zeros(3))
    for t in added:
        p=vv[t];n=np.cross(p[1]-p[0],p[2]-p[0])
        for v in t:sums[v]+=n
    for t in added:add(t,'terminal_outer',[old_targets[v] if v in old_targets else cover36.unit(sums[v]).tolist() for v in t])
    for part in pieces:
        t=part['ids'];oi=part['old']
        if part['inside']:add(t,'terminal_inner_reprofile')
        else:
            if any(v in movable for v in t):raise ValueError('Outside inner fragment contains a movable point')
            weights=[barycentric(vv[v],oldvv[cover['triangles'][oi]]) for v in t]
            ns=[cover36.unit(w@np.asarray(cover['requested_triangle_normals'][oi])).tolist() for w in weights]
            ni=add(t,'inner_preserved_fragment',ns,oi,weights)
            outside.append(dict(old_triangle=oi,new_triangle=ni,barycentric=[w.tolist() for w in weights]))
    for t in added:add([outer_to_inner[v] for v in reversed(t)],'terminal_inner')
    old_edges={(a,b) for loop in cover['front_boundary'] for a,b in zip(loop,loop[1:]+loop[:1])}
    new_edges={(a,b) for loop in layout['boundary'] for a,b in zip(loop,loop[1:]+loop[:1])}
    for a,b in sorted(new_edges-old_edges):
        cap=[b,a,outer_to_inner[a],outer_to_inner[b]]
        # Resolve exact collinear retracing of an end boundary symmetrically;
        # choosing the opposite diagonal must not change the resulting solid.
        while len(cap)>3:
            remove=None
            for j,v in enumerate(cap):
                triple=[cap[j-1],v,cap[(j+1)%len(cap)]]
                p=[exact.vector(vertices[k]) for k in triple]
                if not any(exact.cross(exact.sub(p[1],p[0]),exact.sub(p[2],p[0]))):
                    remove=j;redundant_caps.append(dict(vertices=triple,points=[vertices[k] for k in triple],reason='Exact collinear generated cap boundary retraces an existing shared end edge.'));break
            if remove is None:break
            cap.pop(remove)
        for j in range(1,len(cap)-1):add([cap[0],cap[j],cap[j+1]],'terminal_rim')
    # A retained old inner endpoint can lie exactly on the new outer end edge.
    # The old unpartitioned edge plus a zero-area cap would be a T-junction.
    # Conform only the new authored outer triangles to these existing knots.
    # All protected original faces/fields and every actual positive-area cap stay.
    cap_knots={v for row in redundant_caps for v in row['vertices']}
    conformed=[]
    for i in range(len(triangles)):
        if domains[i]!='terminal_outer':continue
        original=triangles[i];edge_poly=[]
        for a,b in zip(original,original[1:]+original[:1]):
            aa,bb=exact.vector(vertices[a]),exact.vector(vertices[b]);step=exact.sub(bb,aa)
            axis=next(j for j in range(3) if step[j]);points=[(exact.F(0),a)]
            for v in cap_knots-set(original):
                q=exact.vector(vertices[v]);f=(q[axis]-aa[axis])/step[axis]
                if 0<f<1 and all(q[j]==aa[j]+f*step[j] for j in range(3)):points.append((f,v))
            edge_poly.extend(v for _,v in sorted(points))
        if len(edge_poly)==3:continue
        n=np.cross(vv[original[1]]-vv[original[0]],vv[original[2]]-vv[original[0]])
        axes=[j for j in range(3) if j!=int(np.argmax(np.abs(n)))]
        coords={v:tuple(exact.F(vertices[v][j]) for j in axes) for v in edge_poly}
        parts=mesh16.ears(edge_poly,coords);oldns=np.asarray(targets[i]);olduv={name:np.asarray(values[i]) for name,values in uvs.items()}
        new_values=[]
        for t in parts:
            w=[barycentric(vv[v],vv[original]) for v in t]
            new_values.append((list(t),[cover36.unit(q@oldns).tolist() for q in w],{name:[(q@values).tolist() for q in w] for name,values in olduv.items()}))
        for j,(t,ns,tex) in enumerate(new_values):
            if j==0:
                triangles[i]=t;targets[i]=ns
                for name in uvs:uvs[name][i]=tex[name]
            else:
                triangles.append(t);domains.append('terminal_outer');targets.append(ns)
                for name in uvs:uvs[name].append(tex[name])
        conformed.append(dict(original_triangle=i,old_vertices=original,complete_polygon=edge_poly,triangles=parts))
    result=copy.deepcopy(cover)
    result['complete_floor_stock_constraints']=complete_floor_records
    result['exact_end_boundary_conformance']=dict(redundant_zero_area_generated_caps=redundant_caps,positive_area_outer_partitions=conformed)
    result['receiver_plane_ownership']={str(v):[dict(normal=n.tolist(),constant=c) for n,c in ps] for v,ps in receiver_constraints.items()}
    result['inner_constraint_schema']={str(v):dict(movable=v in movable,reference=point_meta[v]['old_inner_point'] if v in point_meta else cover['vertices'][v],planes=[dict(normal=n.tolist(),constant=c) for n,c in planes]) for v,planes in constraints.items()}
    result.update(vertices=vertices,triangles=triangles,triangle_domains=domains,requested_triangle_normals=targets,triangle_uvs=uvs,
                  shared_terminal_sections=dict(shared_edges=layout['shared'],fixed_plane_conflicts=fixed_conflicts,
                      three_dimensional_inner_solutions=solutions,complete_outer_boundary=layout['boundary'],
                      authored_inner_vertex_ids=sorted(movable),
                      old_inner_outside_correspondence=outside,preserved_old_triangles=retained,
                      new_outer_triangles=len(added),triangle_delta=len(triangles)-len(cover['triangles'])),
                  geometry_authoring='Complete carrier-facet terminal return and one shared finite-band 3D inner section. No Y-only thickening or lower clipping plane.')
    domain07.validate(result)
    if mesh16.loops(triangles):raise ValueError('Shared carrier return has open boundary')
    return result
