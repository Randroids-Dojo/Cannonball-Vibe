"""Current-input cover construction: shared. Source provenance is in the private port manifest."""

import copy

import numpy as np

from . import cover as cover36

from . import base_mesh as mesh16

from . import triangulation as triangulate270

from . import stock as stock377

from . import floor_stock as floor_stock376

from .corners import _minimum_norm

def prepare(cover,layout,exact):
    row=stock377.prepare(cover,layout,exact,finite_sheet_constraints=floor_stock376.derive(layout,_minimum_norm))
    vertices=row['vertices'];vv=np.asarray(vertices);count=cover['front_vertex_count']
    ids=[i for i,d in enumerate(row['triangle_domains']) if d=='terminal_inner']
    if len(ids)!=len(layout['added']):raise ValueError('Complete generated inner ownership missing')
    mapped={};owners={}
    for i,t,domain in zip(ids,layout['added'],layout['authored_patch_domains']):
        owners[i]=domain
        for a,b in zip(t,reversed(row['triangles'][i])):
            if a in mapped and mapped[a]!=b:raise ValueError('Nonshared inner-grid identity')
            mapped[a]=b
    planes={pr['sign']:float(vertices[mapped[pr['side_outer'][0]]][0]) for pr in layout['profiles']}
    upper=float(np.float32(.275));lookup={tuple(v):i for i,v in enumerate(vertices)}
    triangles=[];domains=[];targets=[];roles=[];active_role=None;uvs={name:[] for name in row['triangle_uvs']};removed=[];fragments=[];edge_nodes={};edge_conform=[]
    def vertex(q):
        p=tuple(float(np.float32(x)) for x in q)
        if p not in lookup:lookup[p]=len(vertices);vertices.append(list(p))
        return lookup[p]
    def weights(q,points):
        a,b,c=points;ab=b-a;ac=c-a;d=np.asarray(q)-a
        u=np.linalg.solve([[ab@ab,ab@ac],[ab@ac,ac@ac]],[ab@d,ac@d]);return np.array([1-u.sum(),u[0],u[1]])
    def add(t,d,ns,tex):
        triangles.append(list(t));domains.append(d);targets.append(ns);roles.append(active_role)
        for name in uvs:uvs[name].append(tex[name])
    cap_remove=set()
    for pr in layout['profiles']:
        end=pr['protected_curve'][-1];gt=pr['side_outer'][-1];ie=end+count;gi=mapped[gt]
        for i,(t,d) in enumerate(zip(row['triangles'],row['triangle_domains'])):
            if d=='terminal_rim' and set(t)<={end,gt,ie,gi}:cap_remove.add(i)
    for i,(t,d,ns) in enumerate(zip(row['triangles'],row['triangle_domains'],row['requested_triangle_normals'])):
        if owners.get(i)=='outer_side' or i in cap_remove:
            removed.append(dict(triangle=i,domain=d,authored_role=owners.get(i)));continue
        active_role=owners.get(i,d)
        tex={name:values[i] for name,values in row['triangle_uvs'].items()}
        eligible=d in ('inner_preserved_fragment','terminal_inner_reprofile') or owners.get(i)=='formed_front'
        p=[exact.vector(vertices[v]) for v in t];sign=1 if sum(q[0] for q in p)>0 else -1
        if not eligible or min(q[2] for q in p)>=exact.F(upper):
            add(t,d,ns,tex);continue
        clip=[((exact.F(sign),exact.F(0),exact.F(0)),exact.F(sign*planes[sign])),((exact.F(0),exact.F(0),exact.F(-1)),exact.F(-upper))]
        hit,outside=exact.partition(p,clip)
        if not hit:
            add(t,d,ns,tex);continue
        if exact.positive_area(hit):removed.append(dict(triangle=i,domain=d,authored_role=owners.get(i),removed_polygon=[[float(x) for x in q] for q in hit]))
        source=np.asarray([vertices[v] for v in t]);normal=np.cross(source[1]-source[0],source[2]-source[0]);axes=[j for j in range(3) if j!=int(np.argmax(np.abs(normal)))]
        for poly in outside:
            if not exact.positive_area(poly):continue
            ids0=[vertex(q) for q in poly]
            for q,v in zip(poly,ids0):
                for a,b in zip(t,t[1:]+t[:1]):
                    aa,bb=exact.vector(vertices[a]),exact.vector(vertices[b]);step=exact.sub(bb,aa);axis=next(j for j in range(3) if step[j]);f=(q[axis]-aa[axis])/step[axis]
                    if 0<f<1 and all(q[j]==aa[j]+f*step[j] for j in range(3)):
                        key=tuple(sorted((a,b)));edge_nodes.setdefault(key,{})[v]=f if a==key[0] else 1-f
            ids0=[v for j,v in enumerate(ids0) if j==0 or v!=ids0[j-1]]
            if len(ids0)>1 and ids0[0]==ids0[-1]:ids0.pop()
            if len(set(ids0))<3:continue
            coords={v:tuple(exact.F(vertices[v][j]) for j in axes) for v in ids0}
            for nt in triangulate270.ears(ids0,coords):
                w=[weights(vertices[v],source) for v in nt]
                nn=[cover36.unit(q@np.asarray(ns)).tolist() for q in w]
                uv={name:[(q@np.asarray(values)).tolist() for q in w] for name,values in tex.items()}
                ni=len(triangles);add(nt,d,nn,uv);fragments.append(dict(old_triangle=i,new_triangle=ni,barycentric=[q.tolist() for q in w]))
    # Every source edge receives its complete exact clipping-node inventory.
    # Quantize each shared intersection once, including the retained neighbor.
    # The outside surface/field correspondence still requires its original guard.
    for i in range(len(triangles)):
        old=triangles[i];poly=[];active_role=roles[i]
        for a,b in zip(old,old[1:]+old[:1]):
            key=tuple(sorted((a,b)));split=edge_nodes.get(key,{})
            poly.append(a);poly.extend(v for v,f in sorted(split.items(),key=lambda pair:pair[1] if a==key[0] else 1-pair[1]) if v not in old)
        if len(poly)==3:continue
        source=np.asarray([vertices[v] for v in old]);normal=np.cross(source[1]-source[0],source[2]-source[0]);axes=[j for j in range(3) if j!=int(np.argmax(np.abs(normal)))]
        coords={v:tuple(exact.F(vertices[v][j]) for j in axes) for v in poly};parts=triangulate270.ears(poly,coords)
        ns=np.asarray(targets[i]);tex={name:np.asarray(values[i]) for name,values in uvs.items()};domain=domains[i]
        for j,nt in enumerate(parts):
            w=[weights(vertices[v],source) for v in nt];nn=[cover36.unit(q@ns).tolist() for q in w];uv={name:[(q@values).tolist() for q in w] for name,values in tex.items()}
            if j==0:
                triangles[i]=list(nt);targets[i]=nn
                for name in uvs:uvs[name][i]=uv[name]
            else:add(nt,domain,nn,uv)
        edge_conform.append(dict(triangle=i,old_vertices=old,shared_boundary=poly,triangles=parts))
    holes=mesh16.loops(triangles);before=copy.deepcopy(holes);closures=[]
    def authored(poly,role,axes):
        nonlocal active_role
        active_role=role
        coords={v:tuple(exact.F(vertices[v][j]) for j in axes) for v in poly}
        for t in triangulate270.ears(list(reversed(poly)),coords):
            p=np.asarray([vertices[v] for v in t]);n=cover36.unit(np.cross(p[1]-p[0],p[2]-p[0])).tolist()
            add(t,role,[n]*3,{name:[[vertices[v][j]*4 for j in axes] for v in t] for name in uvs})
    for pr in layout['profiles']:
        sign=pr['sign'];ie=pr['protected_curve'][-1]+count;gt=pr['side_outer'][-1];gi=mapped[gt]
        loops=[q for q in holes if ie in q and gt in q and gi in q]
        if len(loops)!=1:raise ValueError('Missing one complete side/end boundary: '+str(dict(sign=sign,holes=holes)))
        loop=loops[0];aa=[v for v in loop if vertices[v][0]==planes[sign] and vertices[v][2]==upper]
        if len(aa)!=1:raise ValueError('Actual fixed inner cut lacks unique side-plane intersection: '+str(aa))
        a=aa[0];i,j=loop.index(a),loop.index(gi);paths=[loop[i:j+1] if i<=j else loop[i:]+loop[:j+1],loop[j:i+1] if j<=i else loop[j:]+loop[:i+1]]
        side=[q for q in paths if all(vertices[v][0]==planes[sign] for v in q)]
        if len(side)!=1:raise ValueError('Complete inner side boundary is not the common receiving plane')
        authored(side[0],'formed_side_inner',[1,2])
        holes=mesh16.loops(triangles);cap=[q for q in holes if ie in q and gt in q and gi in q]
        if len(cap)!=1:raise ValueError('Missing finite common end closure')
        cap=cap[0];pts=np.asarray([vertices[v] for v in cap]);normal=sum((np.cross(p,q) for p,q in zip(pts,np.roll(pts,-1,axis=0))),np.zeros(3));axes=[j for j in range(3) if j!=int(np.argmax(np.abs(normal)))]
        authored(cap,'finite_upper_stock_cap',axes);closures.append(dict(sign=sign,inner_side_boundary=side[0],finite_end_cap=cap,stock_plane_x=planes[sign],fixed_end_vertex=ie))
        holes=mesh16.loops(triangles)
    if holes:raise ValueError('Unclosed common stock sheet: '+str(holes))
    row.update(vertices=vertices,triangles=triangles,triangle_domains=domains,requested_triangle_normals=targets,triangle_uvs=uvs,triangle_authored_roles=roles,
               common_side_boundary=dict(original_holes=before,closures=closures,removed_authored_fragments=removed,retained_fragment_mapping=fragments,shared_edge_conformance=edge_conform,
                   scope='Original receiver unchanged. Only finite terminal inner band intersected with the side stock plane; fixed .275 upper chain retained.'))
    return row
