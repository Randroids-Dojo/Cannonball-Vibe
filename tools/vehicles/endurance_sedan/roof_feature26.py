"""Unsaved local formed C-pillar return trial; no source/save/export calls."""
import math, hashlib, json
from collections import Counter, defaultdict
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

CUT=-1.310
FRONT=-1.2297

def physical(obj):
    m=obj.data
    return hashlib.sha256(json.dumps({'vertices':[list(p.co) for p in m.vertices],
      'polygons':[list(p.vertices) for p in m.polygons],
      'uvs':{layer.name:[list(d.uv) for d in layer.data] for layer in m.uv_layers},
      'normals':[list(n.vector) for n in m.corner_normals],
      'matrix':[list(r) for r in obj.matrix_world],
      'materials':[p.name if p else None for p in m.materials],
      'modifiers':[{'name':p.name,'type':p.type} for p in obj.modifiers]},sort_keys=True).encode()).hexdigest()

def row(obj):
    graph=bpy.context.evaluated_depsgraph_get();o=obj.evaluated_get(graph)
    m=o.to_mesh(preserve_all_data_layers=True,depsgraph=graph);m.calc_loop_triangles()
    r={'name':obj.name,'vertices':[list(o.matrix_world@p.co) for p in m.vertices],
      'triangles':[list(t.vertices) for t in m.loop_triangles],
      'normals':[list(n.vector) for n in m.corner_normals],
      'triangle_loops':[list(t.loops) for t in m.loop_triangles],
      'uvs':{layer.name:[list(v.uv) for v in layer.data] for layer in m.uv_layers},
      'materials':[p.name if p else None for p in m.materials],
      'triangle_materials':[t.material_index for t in m.loop_triangles]}
    o.to_mesh_clear();return r

def polygon_area(points):
    return sum(a[0]*b[2]-b[0]*a[2] for a,b in zip(points,points[1:]+points[:1]))*.5

def hull2(points):
    ps=sorted(set((float(x),float(z)) for x,z in points))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lo=[];hi=[]
    for p in ps:
        while len(lo)>1 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(ps):
        while len(hi)>1 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return lo[:-1]+hi[:-1]

def roof_height(roof,x,y):
    tree=BVHTree.FromPolygons(roof['vertices'],roof['triangles'],all_triangles=True)
    p,_,_,_=tree.ray_cast(Vector((x,y,0)),Vector((0,0,1)),3)
    if p is None:raise ValueError('No actual roof underside at return support')
    return float(p.z)

def roof_half(roof,y):
    result=[]
    for t in roof['triangles']:
        ps=[roof['vertices'][i] for i in t]
        for a,b in zip(ps,ps[1:]+ps[:1]):
            if min(a[1],b[1])<=y<=max(a[1],b[1]) and a[1]!=b[1]:
                k=(y-a[1])/(b[1]-a[1]);result.append(abs(a[0]+k*(b[0]-a[0])))
    if not result:raise ValueError('No actual roof section')
    return max(result)

def angle(a,b):
    ax,ay,az=a;bx,by,bz=b
    cross=(ay*bz-az*by,az*bx-ax*bz,ax*by-ay*bx)
    return math.degrees(math.atan2(math.sqrt(sum(c*c for c in cross)),sum(x*y for x,y in zip(a,b))))

def make(obj,roof,rail,side):
    old=row(obj);sign=-1 if side=='L' else 1
    if obj.name!='LOD0_StampedPillar_C'+side:raise ValueError('Wrong exact semantic target')
    if len(old['materials'])!=1:raise ValueError('Unexpected material domain')
    vertices=[];faces=[];corner=[];uvrows={n:[] for n in old['uvs']};idx={};material=[]
    def vertex(p):
        key=tuple(round(v,11) for v in p)
        if key not in idx:idx[key]=len(vertices);vertices.append(list(p))
        return idx[key]
    def append(poly,mat=0):
        ids=[vertex(p['p']) for p in poly]
        for k in range(1,len(ids)-1):
            tri=[ids[0],ids[k],ids[k+1]]
            if len(set(tri))!=3:raise ValueError('Duplicate clipped triangle index')
            faces.append(tri);material.append(mat)
            for j in (0,k,k+1):
                corner.append(poly[j]['n'])
                for name in uvrows:uvrows[name].append(poly[j]['uv'][name])
    for ids,loops,mat in zip(old['triangles'],old['triangle_loops'],old['triangle_materials']):
        ps=[{'p':old['vertices'][i],'n':old['normals'][j],'uv':{n:old['uvs'][n][j] for n in old['uvs']}} for i,j in zip(ids,loops)]
        clipped=[]
        for a,b in zip(ps,ps[1:]+ps[:1]):
            ain=a['p'][1]<=CUT;bin=b['p'][1]<=CUT
            if ain:clipped.append(a)
            if ain!=bin:
                k=(CUT-a['p'][1])/(b['p'][1]-a['p'][1])
                p=[a['p'][j]+k*(b['p'][j]-a['p'][j]) for j in range(3)];p[1]=CUT
                n=[a['n'][j]+k*(b['n'][j]-a['n'][j]) for j in range(3)];ln=math.sqrt(sum(x*x for x in n));n=[x/ln for x in n]
                clipped.append({'p':p,'n':n,'uv':{name:[a['uv'][name][j]+k*(b['uv'][name][j]-a['uv'][name][j]) for j in range(2)] for name in old['uvs']}})
        if len(clipped)>=3:append(clipped,mat)
    retained_corner_count=len(corner)
    edges=Counter(tuple(sorted((t[i],t[(i+1)%3]))) for t in faces for i in range(3))
    boundary=[e for e,count in edges.items() if count==1]
    if any(abs(vertices[i][1]-CUT)>1e-9 for edge in boundary for i in edge):raise ValueError('Unexpected open boundary below cut')
    adjacent=defaultdict(list)
    for a,b in boundary:adjacent[a].append(b);adjacent[b].append(a)
    if not adjacent or any(len(v)!=2 for v in adjacent.values()):raise ValueError('Cut is not one closed cycle')
    start=max(adjacent,key=lambda i:(vertices[i][2],-abs(vertices[i][0])))
    loop=[start];previous=None;current=start
    while True:
        nxt=next(i for i in adjacent[current] if i!=previous)
        if nxt==start:break
        if nxt in loop:raise ValueError('Repeated section vertex')
        loop.append(nxt);previous,current=current,nxt
    if len(loop)!=len(adjacent):raise ValueError('Multiple cut loops')
    if polygon_area([[abs(vertices[i][0]),vertices[i][1],vertices[i][2]] for i in loop])<0:loop=[loop[0],*reversed(loop[1:])]
    section=[vertices[i] for i in loop]
    top=max(section,key=lambda p:p[2]);bottom=min(section,key=lambda p:p[2])
    end_top=(abs(top[0]),top[2]);end_bottom=(abs(bottom[0]),bottom[2])
    railpts=[p for p in rail['vertices'] if abs(p[1]+1.23)<1e-6]
    frontx=max(abs(p[0]) for p in railpts)
    frontz=min(p[2] for p in railpts if abs(abs(p[0])-frontx)<1e-6)
    stations=[]
    # The roof-supported portion ends before the actual rear-glass footprint.
    roof_end=-1.264
    anchorx=roof_half(roof,roof_end)-.0016
    anchorz=roof_height(roof,sign*anchorx,roof_end)+.00025
    for y in (-1.295,-1.280,-1.264,-1.258,-1.245,FRONT):
        t=(y-CUT)/(FRONT-CUT)
        bx=end_bottom[0]+t*(frontx-end_bottom[0]);bz=end_bottom[1]+t*(frontz-end_bottom[1])
        if y>=roof_end:
            tx=roof_half(roof,min(y,-1.2300001))-.0016
            tz=roof_height(roof,sign*tx,min(y,-1.2300001))+.00025
        else:
            q=(y-CUT)/(roof_end-CUT)
            tx=end_top[0]+q*(anchorx-end_top[0]);tz=end_top[1]+q*(anchorz-end_top[1])
        thickness=.0032+(1-t)*.0030
        inner=tx-thickness
        if y>=-1.258:inner=min(inner,.6745)
        elif y>=roof_end:inner=tx-.0012
        glass=row(bpy.data.objects['LOD0_Backlight'])
        if min(p[1] for p in glass['vertices'])<y<max(p[1] for p in glass['vertices']):
            inner=max(inner,roof_half(glass,y)+.0016)
        topinner=roof_height(roof,sign*inner,min(y,-1.2300001))+.00025 if y>=roof_end else tz
        cross_section=[(tx,tz),(bx,bz),(bx-thickness,bz+.0003),(inner,topinner-thickness),(inner,topinner)]
        if y<=-1.280:
            tube=row(bpy.data.objects['LOD0_PillarC_'+side])
            tree=BVHTree.FromPolygons(tube['vertices'],tube['triangles'],all_triangles=True)
            weld_z=(tz+bz)*.5
            hit,_,_,_=tree.ray_cast(Vector((sign*1.,y,weld_z)),Vector((-sign,0,0)),.5)
            if hit is None:raise ValueError('No actual C tube behind local return tab')
            cross_section.append((abs(hit.x)-.0005,weld_z))
        poly=hull2(cross_section)
        pts=[[sign*x,y,z] for x,z in poly]
        if polygon_area([[abs(p[0]),p[1],p[2]] for p in pts])<0:pts.reverse()
        anchor=[sign*inner,y,topinner]
        j=min(range(len(pts)),key=lambda i:math.dist(pts[i],anchor))
        if math.dist(pts[j],anchor)>1e-6:raise ValueError('Authored upper return anchor is not on the convex section')
        pts=pts[j:]+pts[:j]
        stations.append([vertex(p) for p in pts])
    # Geometric feature correspondence must also determine the loft endpoints.
    # The prior formula used the minimum-Z cut vertex for both lower features,
    # and maximum-Z for both upper features, creating an actual dip/crease.
    cut_points=[(abs(vertices[i][0]),vertices[i][2]) for i in loop]
    cut_features=[0,min(range(len(loop)),key=lambda i:cut_points[i][0]),
                  min(range(len(loop)),key=lambda i:cut_points[i][1]),
                  max(range(len(loop)),key=lambda i:cut_points[i][0]),
                  max(range(len(loop)),key=lambda i:cut_points[i][0]+cut_points[i][1])]
    if cut_features!=sorted(set(cut_features)) or len(cut_features)!=5:
        raise ValueError('Cut features are not one ordered cycle')
    terminal=next(ids for ids in stations if abs(vertices[ids[0]][1]-roof_end)<1e-9)
    loft_changes=[]
    for ids in stations:
        y=vertices[ids[0]][1]
        if y>=roof_end:continue
        q=(y-CUT)/(roof_end-CUT)
        old_points=[list(vertices[i]) for i in ids]
        for j,i in enumerate(ids):
            if j==1:continue  # retain the actual measured C-tube weld tab
            a=vertices[loop[cut_features[j]]];b=vertices[terminal[j]]
            vertices[i]=[a[k]+q*(b[k]-a[k]) for k in range(3)]
            vertices[i][1]=y
        loft_changes.append({'y':y,'before':old_points,'after':[vertices[i] for i in ids]})
    loops=[loop,*stations]
    def progress(ids):
        lengths=[math.dist(vertices[a],vertices[b]) for a,b in zip(ids,ids[1:]+ids[:1])]
        total=sum(lengths);res=[0.]
        for v in lengths:res.append(res[-1]+v/total)
        res[-1]=1.;return res
    def newface(ids):
        faces.append(list(ids));material.append(0)
        for i in ids:
            corner.append(None)
            for name in uvrows:uvrows[name].append([abs(vertices[i][0])*2,vertices[i][1]*2+3])
    # Station vertices already name five consistent geometric features:
    # upper inner, inner elbow, lower inner, lower outer, upper outer. Do not
    # remap them by perimeter progress when width/height changes.
    features=[]
    a,b=loops[0],loops[1]
    points=[(abs(vertices[i][0]),vertices[i][2]) for i in a]
    anchors=[0,min(range(len(a)),key=lambda i:points[i][0]),
             min(range(len(a)),key=lambda i:points[i][1]),
             max(range(len(a)),key=lambda i:points[i][0]),
             max(range(len(a)),key=lambda i:points[i][0]+points[i][1])]
    if anchors!=sorted(set(anchors)) or len(anchors)!=5:
        raise ValueError('Original C section lacks the five ordered geometric features')
    if len(b)!=5 or any(len(ids)!=5 for ids in loops[1:]):raise ValueError('Unexpected formed station features')
    for k,start in enumerate(anchors):
        end=anchors[k+1] if k+1<len(anchors) else len(a)
        for i in range(start,end):newface((a[i],a[(i+1)%len(a)],b[k]))
        newface((a[end%len(a)],b[(k+1)%5],b[k]))
        features.append({'feature':k,'cut_indices':list(range(start,end+1)),
                         'cut_points':[vertices[a[i%len(a)]] for i in range(start,end+1)]})
    for a,b in zip(loops[1:],loops[2:]):
        for i in range(5):
            j=(i+1)%5
            newface((a[i],a[j],b[j]));newface((a[i],b[j],b[i]))
    cap=loops[-1]
    for k in range(1,len(cap)-1):newface((cap[0],cap[k],cap[k+1]))
    # Preserve material ownership, close winding, then set the retained native field.
    mesh=bpy.data.meshes.new(obj.name+'_RearReturnTrial')
    inverse=obj.matrix_world.inverted();mesh.from_pydata([inverse@Vector(p) for p in vertices],[],faces);mesh.update()
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free();mesh.update()
    if any(tuple(p.vertices)!=tuple(faces[i]) for i,p in enumerate(mesh.polygons)):
        # Reversal alone is allowed; rotate/reorder the exact per-corner attributes.
        byface={tuple(sorted(f)):i for i,f in enumerate(faces)};oldcorner=corner;olduvs=uvrows;corner=[];uvrows={n:[] for n in olduvs}
        for p in mesh.polygons:
            oldi=byface[tuple(sorted(p.vertices))];f=faces[oldi]
            for vi in p.vertices:
                j=3*oldi+f.index(vi);corner.append(oldcorner[j])
                for name in uvrows:uvrows[name].append(olduvs[name][j])
    for p in mesh.polygons:p.use_smooth=True
    mesh.set_sharp_from_angle(angle=math.radians(35))
    for name,values in uvrows.items():
        layer=mesh.uv_layers.new(name=name)
        for slot,uv in zip(layer.data,values):slot.uv=uv
    for m in obj.data.materials:mesh.materials.append(m)
    auto=[list(n.vector) for n in mesh.corner_normals]
    targets=[n if n is not None else auto[i] for i,n in enumerate(corner)]
    mesh.normals_split_custom_set(targets);mesh.update();mesh.calc_loop_triangles()
    deviations=[angle(a.vector,t) for a,t,n in zip(mesh.corner_normals,targets,corner) if n is not None]
    candidate=bpy.data.objects.new(obj.name+'_TrialObject',mesh);candidate.matrix_world=obj.matrix_world.copy();bpy.context.scene.collection.objects.link(candidate)
    output=row(candidate);output['name']=obj.name
    return candidate,{'side':side,'old':old,'candidate':output,'old_triangles':len(old['triangles']),
      'new_triangles':len(output['triangles']),'cut_y_m':CUT,'front_y_m':FRONT,'cut_cycle_vertices':len(loop),
      'stations':[{'y':vertices[ids[0]][1],'vertices':[vertices[i] for i in ids]} for ids in loops],
      'feature_correspondence':features,'root_feature_loft_changes':loft_changes,
      'retained_corner_count':retained_corner_count,'maximum_retained_field_error_degrees':max(deviations),
      'support_limit_y_m':roof_end,'roof_penetration_target_m':.00025,
      'native_targets':targets,'native_actual':[list(n.vector) for n in mesh.corner_normals],
      'preserved_corner_mask':[n is not None for n in corner],'native_uv_targets':uvrows,
      'scope':'Only replace stamped C skin above Y=-1.310 with finite formed roof/rail termination. Unchanged existing C tube and all other meshes.'}
