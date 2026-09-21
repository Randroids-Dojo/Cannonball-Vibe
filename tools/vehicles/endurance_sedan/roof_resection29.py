"""Unsaved full upper C-return resection with actual incoming/outgoing tracks.

New authored geometry above the actual Y=-1.310 cut. No I/O/save/export.
"""
import math
from collections import Counter, defaultdict
import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

YS = (-1.295, -1.280, -1.272, -1.264, -1.258, -1.245, -1.2377, -1.2337, -1.2297)

def coefficients(a,b,m0,m1,length):
    return [a,m0*length,3*(b-a)-length*(2*m0+m1),2*(a-b)+length*(m0+m1)]

def at(c,t): return ((c[3]*t+c[2])*t+c[1])*t+c[0]

def extrema(c):
    a,b,d=3*c[3],2*c[2],c[1];roots=[]
    if abs(a)<1e-18:
        if abs(b)>1e-18: roots=[-d/b]
    elif b*b-4*a*d>=0:
        q=math.sqrt(b*b-4*a*d);roots=[(-b-q)/(2*a),(-b+q)/(2*a)]
    samples=[(t,at(c,t)) for t in (0.,1.,*[t for t in roots if 0<t<1])]
    return {'samples':samples,'minimum':min(v for _,v in samples),'maximum':max(v for _,v in samples)}

def features(points):
    return [max(points,key=lambda p:p[2]),min(points,key=lambda p:abs(p[0])),
            min(points,key=lambda p:p[2]),max(points,key=lambda p:abs(p[0])),
            max(points,key=lambda p:abs(p[0])+p[2])]

def slice_points(row,y):
    out=[]
    for tri in row['triangles']:
        points=[row['vertices'][i] for i in tri]
        for a,b in zip(points,points[1:]+points[:1]):
            if (a[1]<y)!=(b[1]<y):
                t=(y-a[1])/(b[1]-a[1]);out.append([a[k]+t*(b[k]-a[k]) for k in range(3)])
    if not out: raise ValueError('Missing actual section')
    return out

def make(obj,old,roof,rail,station_ids,encode):
    if obj.name not in ('LOD0_StampedPillar_CL','LOD0_StampedPillar_CR'):
        raise ValueError('Wrong semantic target')
    if obj.modifiers or len(obj.data.polygons)!=len(old['triangles']):
        raise ValueError('Expected explicit actual triangles')
    if len(old['triangles']) not in (216,220) or len(old['materials'])!=1:
        raise ValueError('Unexpected input layout/material')
    sign=-1 if obj.name.endswith('L') else 1
    original_stations=station_ids(old)
    rings=[[list(old['vertices'][i]) for i in ids] for ids in original_stations]
    cut=max(p[1] for p in old['vertices'] if abs(p[1]+1.310)<1e-7)
    front=rings[-1][0][1];support_y=rings[2][0][1]
    anchors=features([list(p) for p in old['vertices'] if abs(p[1]-cut)<1e-8])
    sample=features(slice_points(old,cut-.001));sample2=features(slice_points(old,cut-.002))
    incoming=[[(a[k]-b[k])/.001 for k in range(3)] for a,b in zip(anchors,sample)]
    linear=max(math.dist(sample[i],[(anchors[i][k]+sample2[i][k])*.5 for k in range(3)]) for i in range(5))
    if linear>1e-6: raise ValueError('Changed actual lower-plane tangent')

    cap_y=min(p[1] for p in rail['vertices'])
    cap=[p for p in rail['vertices'] if abs(p[1]-cap_y)<1e-7]
    cap_x=max(abs(p[0]) for p in cap)
    cap_outer=[p for p in cap if abs(abs(p[0])-cap_x)<1e-7]
    if len(cap_outer)!=2: raise ValueError('Expected two original rail outer endpoints')
    top=max(cap_outer,key=lambda p:p[2]);bottom=min(cap_outer,key=lambda p:p[2])
    # The next complete original outer rail section is geometrically distinct
    # from intermediate Boolean cuts on the inboard return.
    candidates=sorted(set(p[1] for p in rail['vertices'] if cap_y+1e-4<p[1]<cap_y+.09))
    next_outer=None
    for y in candidates:
        section=[p for p in rail['vertices'] if abs(p[1]-y)<1e-7]
        x=max(abs(p[0]) for p in section)
        if x<=cap_x+1e-5: continue
        outer=[p for p in section if abs(abs(p[0])-x)<1e-7]
        if len(outer)==2:
            next_outer=outer;break
    if next_outer is None: raise ValueError('No actual outgoing outer rail section')
    top_next=max(next_outer,key=lambda p:p[2]);bottom_next=min(next_outer,key=lambda p:p[2])
    top_tangent=[(b-a)/(top_next[1]-top[1]) for a,b in zip(top,top_next)]
    bottom_tangent=[(b-a)/(bottom_next[1]-bottom[1]) for a,b in zip(bottom,bottom_next)]
    terminal_top=[a+(front-cap_y)*m for a,m in zip(top,top_tangent)];terminal_top[1]=front

    tree=BVHTree.FromPolygons(roof['vertices'],roof['triangles'],all_triangles=True)
    def roof_hit(x,y):
        p,n,face,_=tree.ray_cast(Vector((x,y,0)),Vector((0,0,1)),3)
        if p is None or n.z>=-.5: raise ValueError('Missing actual oriented roof underside')
        return float(p.z),tuple(n),face

    curves=[];lower={}
    for feature in (2,3):
        lower[feature]=[]
        for axis in (0,2):
            c=coefficients(anchors[feature][axis],rings[-1][feature][axis],incoming[feature][axis],bottom_tangent[axis],front-cut)
            lower[feature].append(c);curves.append({'feature':feature,'axis':axis,'y_span':[cut,front],
                'coefficients':c,'endpoint_tangents':[incoming[feature][axis],bottom_tangent[axis]],'extrema':extrema(c)})
    # Keep the actual supported anchor, then meet the exact outgoing rail outer
    # line. The upper surface remains constrained by the actual roof underside.
    anchor4=rings[2][4]
    top_start_dx=(rings[3][4][0]-anchor4[0])/(rings[3][4][1]-support_y)
    top_x=coefficients(anchor4[0],terminal_top[0],top_start_dx,top_tangent[0],front-support_y)
    z_end,n_end,_=roof_hit(terminal_top[0],front)
    end_offset=terminal_top[2]-z_end
    roof_end_dz=-(n_end[0]*top_tangent[0]+n_end[1])/n_end[2]
    offset=coefficients(.00025,end_offset,0.,top_tangent[2]-roof_end_dz,front-support_y)
    _,n_start,_=roof_hit(anchor4[0],support_y)
    top_start_dz=-(n_start[0]*top_start_dx+n_start[1])/n_start[2]
    upper_in=[coefficients(anchors[4][axis],anchor4[axis],incoming[4][axis],m,support_y-cut)
              for axis,m in ((0,top_start_dx),(2,top_start_dz))]
    curves.extend([{'feature':4,'axis':'X_after_support','coefficients':top_x,'extrema':extrema(top_x)},
                   {'feature':4,'axis':'roof_offset_after_support','coefficients':offset,'extrema':extrema(offset)}])

    def retained_inner(y,feature):
        for ring in rings:
            if abs(ring[0][1]-y)<1e-7: return list(ring[feature])
        index=next(i for i in range(len(rings)-1) if rings[i][0][1]<y<rings[i+1][0][1])
        a,b=rings[index][feature],rings[index+1][feature];t=(y-a[1])/(b[1]-a[1])
        p=[a[k]+t*(b[k]-a[k]) for k in range(3)];p[1]=y
        if y>=support_y:
            z,_,_=roof_hit(p[0],y)
            if feature==0:p[2]=z+.00025
            else:
                a0,b0=rings[index][0],rings[index+1][0]
                thick=(a0[2]-a[2])*(1-t)+(b0[2]-b[2])*t;p[2]=z+.00025-thick
        return p

    points=[];faces=[];targets=[];uvs={name:[] for name in old['uvs']};source_ids={};material=[]
    def original_vertex(vi):
        if vi not in source_ids:source_ids[vi]=len(points);points.append(list(old['vertices'][vi]))
        return source_ids[vi]
    for ti,t in enumerate(old['triangles']):
        if max(old['vertices'][i][1] for i in t)>cut+1e-7:continue
        faces.append(tuple(original_vertex(i) for i in t));material.append(old['triangle_materials'][ti])
        for li in old['triangle_loops'][ti]:
            targets.append(old['normals'][li])
            for name in uvs:uvs[name].append(old['uvs'][name][li])
    retained_face_count=len(faces)
    edges=Counter(tuple(sorted((t[k],t[(k+1)%3]))) for t in faces for k in range(3))
    border=[e for e,count in edges.items() if count==1];adj=defaultdict(list)
    if any(abs(points[i][1]-cut)>1e-7 for e in border for i in e):raise ValueError('Unexpected lower open boundary')
    for a,b in border:adj[a].append(b);adj[b].append(a)
    if any(len(v)!=2 for v in adj.values()):raise ValueError('Invalid lower boundary degree')
    start=max(adj,key=lambda i:(points[i][2],-abs(points[i][0])));loop=[start];prev=None;current=start
    while True:
        nxt=next(i for i in adj[current] if i!=prev)
        if nxt==start:break
        if nxt in loop:raise ValueError('Repeated lower cycle')
        loop.append(nxt);prev,current=current,nxt
    if len(loop)!=len(adj):raise ValueError('Multiple lower cycles')
    area=sum(abs(points[a][0])*points[b][2]-abs(points[b][0])*points[a][2] for a,b in zip(loop,loop[1:]+loop[:1]))
    if area<0:loop=[loop[0],*reversed(loop[1:])]
    ps=[points[i] for i in loop]
    cut_features=[0,min(range(len(loop)),key=lambda i:abs(ps[i][0])),min(range(len(loop)),key=lambda i:ps[i][2]),
                  max(range(len(loop)),key=lambda i:abs(ps[i][0])),max(range(len(loop)),key=lambda i:abs(ps[i][0])+ps[i][2])]
    if cut_features!=sorted(set(cut_features)) or len(cut_features)!=5:raise ValueError('Changed actual cut features')

    stations=[];changed=[]
    for y in YS:
        y=next((r[0][1] for r in rings if abs(r[0][1]-y)<1e-7),y)
        ring=[retained_inner(y,0),retained_inner(y,1),None,None,None]
        for feature in (2,3):
            t=(y-cut)/(front-cut);ring[feature]=[at(lower[feature][0],t),y,at(lower[feature][1],t)]
        if y<support_y-1e-8:
            t=(y-cut)/(support_y-cut);ring[4]=[at(upper_in[0],t),y,at(upper_in[1],t)]
        else:
            t=(y-support_y)/(front-support_y);x=at(top_x,t);z,_,_=roof_hit(x,y)
            ring[4]=[x,y,z+at(offset,t)]
        if abs(y-support_y)<1e-7:ring[4]=list(anchor4)
        if abs(y-front)<1e-7:ring[4]=list(terminal_top)
        ids=list(range(len(points),len(points)+5));points.extend(ring);stations.append(ids)
        for original in rings:
            if abs(original[0][1]-y)<1e-7:
                changed.append({'y':y,'before':original,'after':ring,'maximum_movement_m':max(math.dist(a,b) for a,b in zip(original,ring))})

    def newface(t):
        faces.append(tuple(t));material.append(0)
        for i in t:
            targets.append(None)
            for name in uvs:uvs[name].append([abs(points[i][0])*2,points[i][1]*2+3])
    first=stations[0]
    for k,start in enumerate(cut_features):
        end=cut_features[k+1] if k+1<5 else len(loop)
        for j in range(start,end):newface((loop[j],loop[(j+1)%len(loop)],first[k]))
        newface((loop[end%len(loop)],first[(k+1)%5],first[k]))
    for a,b in zip(stations,stations[1:]):
        for i in range(5):
            j=(i+1)%5
            if i==3:
                ids=[a[i],a[j],b[j],b[i]];center=len(points)
                points.append([sum(points[v][k] for v in ids)*.25 for k in range(3)])
                for x,y in zip(ids,ids[1:]+ids[:1]):newface((x,y,center))
            else:newface((a[i],a[j],b[j]));newface((a[i],b[j],b[i]))
    cap=stations[-1]
    for k in range(1,4):newface((cap[0],cap[k],cap[k+1]))
    mesh=bpy.data.meshes.new(obj.name+'_PrivateResection29');inverse=obj.matrix_world.inverted()
    mesh.from_pydata([inverse@Vector(p) for p in points],[],faces);mesh.update()
    bm=bmesh.new()
    try:bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh)
    finally:bm.free()
    mapping={tuple(sorted(f)):i for i,f in enumerate(faces)};ordered=[];ordered_uv={name:[] for name in uvs}
    for p in mesh.polygons:
        oi=mapping[tuple(sorted(p.vertices))];p.material_index=material[oi];p.use_smooth=True
        for vi in p.vertices:
            li=3*oi+faces[oi].index(vi);ordered.append(targets[li])
            for name in uvs:ordered_uv[name].append(uvs[name][li])
    mesh.update();mesh.set_sharp_from_angle(angle=math.radians(35));mesh.update()
    auto=[tuple(n.vector) for n in mesh.corner_normals]
    target=[a if a is not None else auto[i] for i,a in enumerate(ordered)]
    for name,values in ordered_uv.items():
        layer=mesh.uv_layers.new(name=name)
        for d,uv in zip(layer.data,values):d.uv=uv
    for m in obj.data.materials:mesh.materials.append(m)
    mesh.update();code=encode(mesh,target)
    candidate=bpy.data.objects.new(obj.name+'_PrivateResection29',mesh);candidate.matrix_world=obj.matrix_world.copy()
    bpy.context.scene.collection.objects.link(candidate)
    return candidate,{'scope':'New complete80.3mm upper return geometry; actual lower ring, all lower fields, original roof-support inner points and first two C-tube tab vertices held. Actual terminal outer top reseated to outgoing rail line; no roof/glass/rail/C-tube edits.',
        'station_y_m':[points[s[0]][1] for s in stations], 'station_indices':stations,
        'incoming_tangents':incoming,'actual_outgoing_rail_top_tangent':top_tangent,
        'actual_outgoing_rail_bottom_tangent':bottom_tangent,'terminal_top_before':rings[-1][4],
        'terminal_top_after':terminal_top,'upper_roof_offset_terminal_m':end_offset,
        'curves':curves,'changed_original_station_points':changed,'retained_original_faces':retained_face_count,
        'original_triangle_count':len(old['triangles']),'triangle_count':len(faces),'triangle_delta':len(faces)-len(old['triangles']),
        'normal_encoder':code,'lower_original_index_map':source_ids,'native_normal_targets':target,
        'visual_fit_motion_budget_acceptance':False}
