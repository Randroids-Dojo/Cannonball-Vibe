"""Unsaved, same-topology roof-return curve proposal; no I/O or source loading."""
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

CUT = -1.310
YS = (-1.295, -1.280, -1.264, -1.258, -1.245, -1.2297)

def angle(a, b):
    a, b = Vector(a), Vector(b)
    return math.degrees(math.atan2(a.cross(b).length, a.dot(b)))

def section_features(points):
    return [max(points, key=lambda p:p[2]), min(points, key=lambda p:abs(p[0])),
            min(points, key=lambda p:p[2]), max(points, key=lambda p:abs(p[0])),
            max(points, key=lambda p:abs(p[0])+p[2])]

def slice_points(row, y):
    result=[]
    for ids in row['triangles']:
        ps=[row['vertices'][i] for i in ids]
        for a,b in zip(ps,ps[1:]+ps[:1]):
            if (a[1]<y)!=(b[1]<y):
                k=(y-a[1])/(b[1]-a[1])
                result.append([a[j]+k*(b[j]-a[j]) for j in range(3)])
    if not result:raise ValueError('Missing actual lower section')
    return result

def station_ids(row):
    result=[];points=row['vertices']
    for y in YS:
        ids={i for i,p in enumerate(points) if abs(p[1]-y)<1e-7}
        if len(ids)!=5:raise ValueError('Expected exactly five current station vertices')
        edges=set()
        for tri in row['triangles']:
            pair=set(tri)&ids
            if len(pair)==2 and min(points[i][1] for i in tri)<y-1e-6:
                edges.add(tuple(sorted(pair)))
        adjacent={i:[] for i in ids}
        for a,b in edges:adjacent[a].append(b);adjacent[b].append(a)
        if len(edges)!=5 or any(len(v)!=2 for v in adjacent.values()):
            raise ValueError('Actual station is not one five-edge boundary cycle')
        ordered=sorted(ids,key=lambda i:abs(points[i][0]))
        d=ordered[-1]
        if abs(points[d][0])-abs(points[ordered[-2]][0])<=1e-6:
            raise ValueError('Lower outer station feature is not distinct')
        e=max(adjacent[d],key=lambda i:points[i][2])
        if abs(points[adjacent[d][0]][2]-points[adjacent[d][1]][2])<=1e-5:
            raise ValueError('Top/bottom outer edge ordering is ambiguous')
        cycle=[d,e]
        while len(cycle)<5:
            nxt=next(i for i in adjacent[cycle[-1]] if i!=cycle[-2])
            if nxt in cycle:raise ValueError('Premature station cycle closure')
            cycle.append(nxt)
        if d not in adjacent[cycle[-1]]:raise ValueError('Station cycle did not close')
        result.append([cycle[2],cycle[3],cycle[4],cycle[0],cycle[1]])
    return result

def coefficients(a,b,m0,m1,length):
    return [a, m0*length, 3*(b-a)-length*(2*m0+m1), 2*(a-b)+length*(m0+m1)]

def at(c,t):return ((c[3]*t+c[2])*t+c[1])*t+c[0]

def derivative(c,t):return (3*c[3]*t+2*c[2])*t+c[1]

def extrema(c):
    roots=[];a,b,d=3*c[3],2*c[2],c[1]
    if abs(a)<1e-18:
        if abs(b)>1e-18:roots=[-d/b]
    else:
        disc=b*b-4*a*d
        if disc>=0:roots=[(-b-math.sqrt(disc))/(2*a),(-b+math.sqrt(disc))/(2*a)]
    samples=[(t,at(c,t)) for t in [0.,1.,*[t for t in roots if 0<t<1]]]
    return {'stationary_points':samples,'minimum':min(v for _,v in samples),'maximum':max(v for _,v in samples)}

def ordered_slopes(a,b,m0,m1,length):
    """Ordered Bezier controls give complete no-overshoot scalar coverage."""
    s=(b-a)/length
    if s==0:return 0.,0.
    u=max(0.,m0/s);v=max(0.,m1/s)
    if u+v>3:u,v=3*u/(u+v),3*v/(u+v)
    return s*u,s*v

def make(obj, old, roof, variant, encode):
    if variant not in ('outer','outer_flare'):raise ValueError('Unknown bounded proposal')
    if obj.modifiers:raise ValueError('Expected actual modifier-free current return')
    if len(old['triangles'])!=216:raise ValueError('Expected current 216-triangle return')
    sign=-1 if obj.name.endswith('L') else 1
    ids=station_ids(old);points=[list(p) for p in old['vertices']]
    cutpoints=[p for p in points if abs(p[1]-CUT)<1e-7]
    anchors=section_features(cutpoints)
    if len({tuple(p) for p in anchors})!=5:raise ValueError('Actual cut feature ambiguity')
    cut=anchors[0][1];end=points[ids[2][0]][1];front=points[ids[-1][0]][1]
    sample=section_features(slice_points(old,cut-.001))
    sample2=section_features(slice_points(old,cut-.002))
    incoming=[[(a[k]-b[k])/.001 for k in range(3)] for a,b in zip(anchors,sample)]
    linear=max(math.dist(sample[j],[(anchors[j][k]+sample2[j][k])*.5 for k in range(3)]) for j in range(5))
    if linear>1e-6:raise ValueError('Incoming feature no longer follows the actual straight lower plane')
    tree=BVHTree.FromPolygons(roof['vertices'],roof['triangles'],all_triangles=True)
    def height(x,y):
        p,n,face,_=tree.ray_cast(Vector((x,y,0)),Vector((0,0,1)),3)
        if p is None or abs(n.z)<.5:raise ValueError('Missing actual roof underside')
        return float(p.z),list(n),face
    curves=[]
    # The actual measured C-tube tab (feature 1) remains completely fixed below
    # the support. Exterior features use limited cubic Hermite tracks.
    for feature in (0,2,3,4):
        a=anchors[feature];b=points[ids[2][feature]];n=points[ids[3][feature]]
        m0=incoming[feature]
        m1=[(n[k]-b[k])/(n[1]-b[1]) for k in range(3)]
        if feature==0:
            # Match the modest previous/next secant mean, not the old 6mm kink.
            dx0=(b[0]-a[0])/(end-cut);dx1=(points[ids[-1][0]][0]-b[0])/(front-end)
            m1[0]=2*dx0*dx1/(dx0+dx1)
            _,normal,_=height(b[0],end)
            m1[2]=-(normal[0]*m1[0]+normal[1])/normal[2]
        for axis in (0,2):
            aa,bb=m0[axis],m1[axis]
            # Z is monotone by construction; X may turn smoothly to meet the
            # actual roof rail, with all cubic extrema explicitly reported.
            if axis==2:aa,bb=ordered_slopes(a[axis],b[axis],aa,bb,end-cut)
            c=coefficients(a[axis],b[axis],aa,bb,end-cut)
            for ring in (0,1):
                vi=ids[ring][feature];t=(points[vi][1]-cut)/(end-cut)
                points[vi][axis]=at(c,t)
            curves.append({'feature':feature,'axis':axis,'y_interval_m':[cut,end],
                'coefficients':c,'input_derivatives':[m0[axis],m1[axis]],
                'authored_derivatives':[aa,bb],'extrema':extrema(c)})
    # Preserve a positive top-strip width as a feature, rather than curve its
    # two boundary coordinates independently through one another.
    a=anchors[0][0]-anchors[4][0]
    b=points[ids[2][0]][0]-points[ids[2][4]][0]
    dm0=incoming[0][0]-incoming[4][0]
    dm0,dm1=ordered_slopes(a,b,dm0,0.,end-cut)
    width=coefficients(a,b,dm0,dm1,end-cut)
    for ring in (0,1):
        p,q=ids[ring][0],ids[ring][4];t=(points[p][1]-cut)/(end-cut)
        points[p][0]=points[q][0]+at(width,t)
    curves.append({'feature':'0-minus-4','supersedes_independent_feature0_x':True,'axis':0,'y_interval_m':[cut,end],
        'coefficients':width,'authored_derivatives':[dm0,dm1],'extrema':extrema(width)})
    if variant=='outer_flare':
        a=points[ids[2][0]];b=points[ids[-1][0]]
        previous=next(c for c in curves if c['feature']==4 and c['axis']==0)
        m0=previous['authored_derivatives'][1]
        c=coefficients(a[0],b[0],m0,0.,front-end)
        for ring in (3,4):
            vi,vj=ids[ring][0],ids[ring][1];y=points[vi][1]
            x=at(c,(y-end)/(front-end));z,_,_=height(x,y)
            thickness=old['vertices'][vi][2]-old['vertices'][vj][2]
            points[vi]=[x,y,z+.00025];points[vj]=[x,y,z+.00025-thickness]
        curves.append({'feature':[0,1],'axis':0,'y_interval_m':[end,front],
            'coefficients':c,'authored_derivatives':[m0,0.],'extrema':extrema(c),
            'z_contract':'actual roof underside +0.25mm; native existing section thickness retained'})
    allowed={i for ring in ids[:2] for i in (ring[0],ring[2],ring[3],ring[4])}
    if variant=='outer_flare':allowed|={ids[r][f] for r in (3,4) for f in (0,1)}
    changed=[i for i,(a,b) in enumerate(zip(old['vertices'],points)) if a!=b]
    if not set(changed)<=allowed:raise ValueError('Changed feature outside bounded ownership')
    mesh=obj.data.copy();inverse=obj.matrix_world.inverted()
    for i in changed:mesh.vertices[i].co=inverse@Vector(points[i])
    mesh.update()
    # Derive the new geometry-owned field from geometry only. A copied encoded
    # mesh retains custom-normal/cache state; zero targets do not erase it.
    scratch=bpy.data.meshes.new(obj.name+'_PrivateNormalGeometry')
    try:
        scratch.from_pydata([tuple(v.co) for v in mesh.vertices],[],[tuple(p.vertices) for p in mesh.polygons])
        for p in scratch.polygons:p.use_smooth=True
        scratch.update();scratch.set_sharp_from_angle(angle=math.radians(35));scratch.update()
        auto=[list(n.vector) for n in scratch.corner_normals]
        if len(auto)!=len(mesh.loops):raise ValueError('Fresh normal geometry changed corner layout')
        if any(not all(math.isfinite(c) for c in n) or abs(math.hypot(*n)-1)>1e-6 for n in auto):
            raise ValueError('Invalid fresh geometry-derived normal')
    finally:bpy.data.meshes.remove(scratch)
    old_native=[list(n.vector) for n in obj.data.corner_normals]
    owned_loops={li for p in mesh.polygons if min((obj.matrix_world@mesh.vertices[i].co).y for i in p.vertices)>=cut-1e-7 for li in p.loop_indices}
    targets=[auto[i] if i in owned_loops else old_native[i] for i in range(len(auto))]
    encoded=encode(mesh,targets)
    candidate=bpy.data.objects.new(obj.name+'_PrivateContinuity',mesh)
    candidate.matrix_world=obj.matrix_world.copy();bpy.context.scene.collection.objects.link(candidate)
    actual=[list(n.vector) for n in mesh.corner_normals]
    deviations=[angle(a,b) for a,b in zip(actual,targets)]
    return candidate,{'variant':variant,'curves':curves,'changed_vertex_indices':changed,
        'station_vertex_indices':ids,'cut_feature_points_m':anchors,'incoming_tangents':incoming,
        'incoming_linearity_m':linear,'maximum_vertex_movement_m':max(math.dist(a,b) for a,b in zip(old['vertices'],points)),
        'maximum_normal_encoding_error_degrees':max(deviations),'normal_encoder':encoded,
        'changed_points_m':[{'index':i,'old':old['vertices'][i],'new':points[i]} for i in changed],
        'scope':'Same indexed surface topology. Cut ring, terminal cap and first two actual C-tube tab vertices unchanged. New geometry-owned upper field only; all existing UV values retained.'}
