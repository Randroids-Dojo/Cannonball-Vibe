"""Proposed partial original upper-strip sampling, before native bevel/Booleans.

No bpy/IO. Parameters are explicit constructor (t, source_y, side) values for
side vertices, None for cap/radial vertices. Existing vertices never move.
Three midpoint rows are limited to t5..7+1/3 on both upper shoulders. Adjacent
polygons receive the same edge vertex so there are no T junctions. Those four
boundary polygons per row are part of the explicitly authored shape domain.
"""
import math
Y_BANDS=((2.0912500000000005,2.17),(2.194166666666667,2.297083333333333),(2.297083333333333,2.4))
T_MIN=5.
T_MAX=7.+1./3.

def refine(vertices,faces,parameters,point):
    if len(vertices)!=len(parameters):raise ValueError('Missing exact original source parameters')
    vertices=[tuple(v) for v in vertices];faces=[tuple(f) for f in faces];params=list(parameters)
    original_vertices=tuple(vertices);original_count=len(vertices);split={};edge_points={};records=[]
    for fi,face in enumerate(faces):
        if len(face)!=4 or any(params[i] is None for i in face):continue
        values=[params[i] for i in face];sides={v[2] for v in values}
        ts=sorted({v[0] for v in values});ys=sorted({v[1] for v in values})
        if len(sides)!=1 or len(ts)!=2 or len(ys)!=2 or tuple(ys) not in Y_BANDS:continue
        if ts[0]<T_MIN or ts[1]>T_MAX:continue
        if {tuple(v[:2]) for v in values}!={(t,y) for t in ts for y in ys}:raise ValueError('Selected face is not an original parameter rectangle')
        side=next(iter(sides));middle=sum(ys)/2.;hits=[]
        for j,(a,b) in enumerate(zip(face,face[1:]+face[:1])):
            pa,pb=params[a],params[b]
            if pa[0]!=pb[0] or pa[1]==pb[1]:continue
            key=tuple(sorted((a,b)))
            if key not in edge_points:
                p=tuple(point(pa[0],middle,side))
                if len(p)!=3 or not all(math.isfinite(x) for x in p):raise ValueError('Invalid new source point')
                edge_points[key]=len(vertices);vertices.append(p);params.append((pa[0],middle,side))
            hits.append((j,edge_points[key]))
        if len(hits)!=2 or (hits[1][0]-hits[0][0])%2:raise ValueError('Wrong rectangle crossing edges')
        (a,ia),(b,ib)=hits
        # Retain the original oriented polygon order on both children.
        f1=[ia];k=(a+1)%4
        while True:
            f1.append(face[k])
            if k==b:break
            k=(k+1)%4
        f1.append(ib);f2=[ib];k=(b+1)%4
        while True:
            f2.append(face[k])
            if k==a:break
            k=(k+1)%4
        f2.append(ia);split[fi]=(tuple(f1),tuple(f2))
        records.append({'original_face':fi,'t_interval':ts,'source_y_interval':ys,'new_source_y':middle,'side':side})
    if len(records)!=114:raise ValueError('Unexpected original upper strip coverage: '+str(len(records)))
    output=[];owners=[];incident=[]
    for fi,face in enumerate(faces):
        if fi in split:
            output.extend(split[fi]);owners.extend([fi,fi]);continue
        out=[]
        for a,b in zip(face,face[1:]+face[:1]):
            out.append(a);key=tuple(sorted((a,b)))
            if key in edge_points:out.append(edge_points[key])
        if len(out)!=len(face):incident.append(fi)
        output.append(tuple(out));owners.append(fi)
    before=sum(len(f)-2 for f in faces);after=sum(len(f)-2 for f in output)
    return vertices,output,params,{'original_vertices':original_count,'added_vertices':len(vertices)-original_count,
        'triangle_delta_before_native_bevel':after-before,'original_vertices_exact':tuple(vertices[:original_count])==original_vertices,
        'refined_rectangles':records,'additional_incident_boundary_faces':incident,'output_face_original_owners':owners}
