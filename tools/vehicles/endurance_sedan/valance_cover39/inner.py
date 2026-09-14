"""Current-input cover construction: inner. Source provenance is in the private port manifest."""

import copy

import numpy as np

from mathutils import Vector

from mathutils.geometry import delaunay_2d_cdt

from . import shared as shared378

from . import base_mesh as mesh16

from . import cover as cover36

def prepare(cover,layout,exact):
    row=shared378.prepare(cover,layout,exact);v=row['vertices'];vv=np.asarray(v)
    selected=[i for i,r in enumerate(row['triangle_authored_roles']) if r in ('formed_front','terminal_inner_reprofile')]
    if any(row['triangle_domains'][i]=='terminal_outer' for i in selected):raise ValueError('Inner chart ownership includes exterior')
    keep=[i for i in range(len(row['triangles'])) if i not in set(selected)]
    triangles=[row['triangles'][i] for i in keep];domains=[row['triangle_domains'][i] for i in keep];roles=[row['triangle_authored_roles'][i] for i in keep]
    targets=[row['requested_triangle_normals'][i] for i in keep];uvs={name:[values[i] for i in keep] for name,values in row['triangle_uvs'].items()};proof=[]
    for sign in (-1,1):
        old=[row['triangles'][i] for i in selected if sign*sum(v[x][0] for x in row['triangles'][i])>0]
        loops=mesh16.loops(old)
        if len(loops)!=1:raise ValueError('Authored inner chart lacks one complete finite boundary')
        loop=loops[0];vertices=sorted({x for t in old for x in t});local={x:i for i,x in enumerate(vertices)}
        coords=[Vector((v[x][0],v[x][2])) for x in vertices];boundary=[local[x] for x in loop]
        area=sum(float(coords[a].x*coords[b].y-coords[b].x*coords[a].y) for a,b in zip(boundary,boundary[1:]+boundary[:1]))
        if area<0:boundary.reverse()
        # Retain the actual whole-chart facet partitions. Only interior edges
        # that conflict in the exact projected arrangement are released.
        # No point is moved, no boundary is released, and all conflicts are kept.
        edges={tuple(sorted((local[a],local[b]))) for t in old for a,b in zip(t,t[1:]+t[:1])}
        rim={tuple(sorted((a,b))) for a,b in zip(boundary,boundary[1:]+boundary[:1])}
        ratios=[[float(c).as_integer_ratio() for c in p] for p in coords];den=max(b for p in ratios for a,b in p)
        ip=[tuple(a*(den//b) for a,b in p) for p in ratios]
        def orient(a,b,c):
            aa,bb,cc=ip[a],ip[b],ip[c];return (bb[0]-aa[0])*(cc[1]-aa[1])-(bb[1]-aa[1])*(cc[0]-aa[0])
        conflicts=[];released=set();all_edges=sorted(edges)
        for i,(a,b) in enumerate(all_edges):
            for c,d in all_edges[i+1:]:
                if len({a,b,c,d})<4:continue
                if orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0:
                    pair=[(a,b),(c,d)]
                    if all(e in rim for e in pair):raise ValueError('Actual fixed inner boundary crosses itself')
                    released.update(e for e in pair if e not in rim);conflicts.append(pair)
        constraints=sorted(edges-released)
        cv,ce,cf,vo,eo,fo=delaunay_2d_cdt(coords,constraints,[boundary],1,1e-12,True)
        if any(len(o)!=1 for o in vo):raise ValueError('Native chart triangulation merged or generated an actual knot')
        mapping={i:vertices[o[0]] for i,o in enumerate(vo)}
        discrepancy=max(float((p-coords[o[0]]).length) for p,o in zip(cv,vo))
        if discrepancy>1e-7:raise ValueError('Native topology proposal changed the projected vertex inventory')
        new=[]
        for f in cf:
            if len(f)!=3:raise ValueError('Native chart result is not triangular')
            t=[mapping[x] for x in f];p=vv[t];n=np.cross(p[1]-p[0],p[2]-p[0])
            if n[1]<0:t.reverse();n=-n
            nn=cover36.unit(n).tolist();new.append(t);triangles.append(t);domains.append('authored_inner_front');roles.append('formed_inner_front');targets.append([nn]*3)
            for name in uvs:uvs[name].append([[v[x][0]*4,v[x][2]*4] for x in t])
        oldedges={(a,b) for a,b in zip(loop,loop[1:]+loop[:1])};newloops=mesh16.loops(new);newedges={(a,b) for q in newloops for a,b in zip(q,q[1:]+q[:1])}
        if oldedges!=newedges:raise ValueError('Whole inner triangulation changed the shared oriented boundary')
        proof.append(dict(sign=sign,complete_boundary=loop,original_triangles=len(old),new_triangles=len(new),input_vertices=vertices,all_used_positions_exact=True,native_topology_coordinate_difference_m=discrepancy,complete_original_edge_count=len(edges),retained_constraint_count=len(constraints),released_conflicting_interior_edges=[[vertices[v] for v in e] for e in sorted(released)],exact_projected_crossings=[[[vertices[v] for v in e] for e in pair] for pair in conflicts]))
    row.update(triangles=triangles,triangle_domains=domains,triangle_authored_roles=roles,requested_triangle_normals=targets,triangle_uvs=uvs,complete_inner_chart=proof)
    if mesh16.loops(triangles):raise ValueError('Rebuilt whole inner front has an open seam')
    return row
