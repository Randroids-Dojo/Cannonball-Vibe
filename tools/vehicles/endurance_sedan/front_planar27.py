"""Exact boundary triangulation of the declared planar fascia wall domains, including upper optical returns."""
from collections import defaultdict
from fractions import Fraction
import bpy

PLANES={0.13500000536441803,0.2045000046491623,0.36249998211860657,0.5974999666213989,0.6730000376701355,0.8149999976158142}


def cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def ears(boundary,points):
    poly=list(boundary)
    exact={i:tuple(Fraction(float(q)) for q in points[i][:2]) for i in poly}
    area=sum(exact[a][0]*exact[b][1]-exact[a][1]*exact[b][0] for a,b in zip(poly,poly[1:]+poly[:1]))
    if not area:raise ValueError('Zero planar boundary area')
    sign=1 if area>0 else -1
    output=[]
    while len(poly)>3:
        accepted=False
        for i,b in enumerate(poly):
            a,c=poly[i-1],poly[(i+1)%len(poly)]
            if sign*cross(exact[a],exact[b],exact[c])<=0:continue
            if any(all(sign*cross(exact[u],exact[v],exact[p])>=0 for u,v in ((a,b),(b,c),(c,a))) for p in poly if p not in (a,b,c)):continue
            output.append((a,b,c));del poly[i];accepted=True;break
        if not accepted:raise ValueError('No exact valid ear in complete indexed boundary')
    if sign*cross(*(exact[p] for p in poly))<=0:raise ValueError('Collapsed final ear')
    output.append(tuple(poly))
    return output,sign


def insert_interior(triangles,interior,points,sign):
    triangles=list(triangles)
    exact={i:tuple(Fraction(float(q)) for q in p[:2]) for i,p in enumerate(points)}
    for vertex in sorted(interior):
        containing=[]
        for index,tri in enumerate(triangles):
            values=[sign*cross(exact[a],exact[b],exact[vertex]) for a,b in zip(tri,tri[1:]+tri[:1])]
            if min(values)>=0:containing.append((index,tri,values))
        if not containing:raise ValueError('Original interior point lies outside new complete boundary')
        replacement=[]
        if len(containing)==1 and min(containing[0][2])>0:
            index,(a,b,c),_=containing[0]
            replacement=[(a,b,vertex),(b,c,vertex),(c,a,vertex)]
        elif len(containing)==2:
            for index,tri,values in containing:
                if values.count(0)!=1:raise ValueError('Coincident original planar vertex')
                edge=values.index(0);a,b,c=tri[edge],tri[(edge+1)%3],tri[(edge+2)%3]
                replacement.extend([(a,vertex,c),(vertex,b,c)])
        else:raise ValueError('Interior point reaches boundary or has ambiguous indexed containment')
        for tri in replacement:
            if sign*cross(*(exact[i] for i in tri))<=0:raise ValueError('Interior insertion creates collapsed/reversed triangle')
        removed={index for index,_,_ in containing}
        triangles=[tri for index,tri in enumerate(triangles) if index not in removed]+replacement
    return triangles


def apply(obj,encode,*,ideal_stream=None):
    assert obj.name=='LOD0_FrontBumper' and not obj.modifiers
    old=obj.data;old.calc_loop_triangles()
    assert all(len(p.vertices)==3 for p in old.polygons)
    points=[tuple(v.co) for v in old.vertices]
    selected={p.index for p in old.polygons if len({points[i][2] for i in p.vertices})==1 and points[p.vertices[0]][2] in PLANES}
    if not selected:raise ValueError('Declared planar opening walls missing')
    edge_faces=defaultdict(list)
    for i in selected:
        ids=tuple(old.polygons[i].vertices)
        for a,b in zip(ids,ids[1:]+ids[:1]):edge_faces[tuple(sorted((a,b)))].append(i)
    components=[];pending=set(selected)
    while pending:
        stack=[min(pending)];pending.remove(stack[0]);part=[]
        while stack:
            i=stack.pop();part.append(i);ids=tuple(old.polygons[i].vertices)
            for a,b in zip(ids,ids[1:]+ids[:1]):
                for j in edge_faces[tuple(sorted((a,b)))]:
                    if j in pending and points[old.polygons[j].vertices[0]][2]==points[ids[0]][2]:pending.remove(j);stack.append(j)
        components.append(sorted(part))
    faces=[];materials=[];smooth=[];normal_targets=[];uvs={layer.name:[] for layer in old.uv_layers}
    if set(uvs)!={'SurfaceMeters'}:raise ValueError('Unknown planar wall chart requires explicit authorship')
    old_normals=(ideal_stream.input(len(old.loops)) if ideal_stream is not None
                 else [tuple(n.vector) for n in old.corner_normals])
    def append(ids,mat,flag,ns,charts):
        faces.append(tuple(ids));materials.append(mat);smooth.append(flag);normal_targets.extend(ns)
        for name in uvs:uvs[name].extend(charts[name])
    for p in old.polygons:
        if p.index in selected:continue
        append(p.vertices,p.material_index,p.use_smooth,[old_normals[i] for i in p.loop_indices],
               {layer.name:[tuple(layer.data[i].uv) for i in p.loop_indices] for layer in old.uv_layers})
    proofs=[]
    for component in components:
        members=set(component);directed=[];uv_at={};mats={old.polygons[i].material_index for i in component}
        if len(mats)!=1:raise ValueError('Selected plane crosses material boundary')
        for i in component:
            p=old.polygons[i];ids=tuple(p.vertices)
            for a,b in zip(ids,ids[1:]+ids[:1]):
                if len(members.intersection(edge_faces[tuple(sorted((a,b)))]))==1:directed.append((a,b))
            for index,vertex in zip(p.loop_indices,p.vertices):
                chart={layer.name:tuple(layer.data[index].uv) for layer in old.uv_layers}
                if vertex in uv_at and chart!=uv_at[vertex]:raise ValueError('Selected plane has a UV seam')
                uv_at[vertex]=chart
        successor={a:b for a,b in directed}
        if len(successor)!=len(directed) or len({b for _,b in directed})!=len(directed):raise ValueError('Branched planar boundary')
        first=min(successor);boundary=[first];following=successor[first]
        while following!=first:
            if following in boundary or following not in successor:raise ValueError('Open planar boundary')
            boundary.append(following);following=successor[following]
        if len(boundary)!=len(directed):raise ValueError('Multiple loops or holes require separate construction')
        interior=set(uv_at)-set(boundary)
        new,sign=ears(boundary,points)
        new=insert_interior(new,interior,points,sign)
        if len(new)!=len(component):raise ValueError('Planar triangulation changed triangle count')
        for ids in new:
            append(ids,next(iter(mats)),False,[(0.,0.,float(sign))]*3,
                   {name:[(points[i][0]/.25,points[i][1]/.25) for i in ids] for name in uvs})
        proofs.append({'old_faces':component,'boundary':boundary,'original_interior_vertices':sorted(interior),'new_triangles':new,'plane_z_m':points[first][2],'normal_z':sign})
    mesh=bpy.data.meshes.new(obj.name+'CompletePlanarWalls')
    mesh.from_pydata(points,[],faces)
    for mat in old.materials:mesh.materials.append(mat)
    for p,mat,flag in zip(mesh.polygons,materials,smooth):p.material_index=mat;p.use_smooth=flag
    for name,rows in uvs.items():mesh.uv_layers.new(name=name).data.foreach_set('uv',[c for uv in rows for c in uv])
    mesh.update();obj.data=mesh
    result=encode(mesh,normal_targets)
    if not result['passed']:raise ValueError('Planar wall native field target failed')
    if ideal_stream is not None:ideal_stream.accept(normal_targets,len(mesh.loops))
    assert [tuple(v.co) for v in mesh.vertices]==points
    return {'selected_planar_faces':len(selected),'components':proofs,'positions_and_boundary_indices_exact':True,
            'triangle_count_before':len(old.polygons),'triangle_count_after':len(mesh.polygons),'native_encoding':result,
            'authored_uv_field':{'channel':'SurfaceMeters','scope':'Selected actual constant-Z walls only',
                'formula':'(X/0.25m,Y/0.25m)','old_interior_field_preserved':False,
                'unselected_triangle_uvs_exact':True,'native_target_guard':1e-5}}
