"""Actual-scene outer C/cantrail closing-section form trial. No I/O or saves."""
import math
from fractions import Fraction as F
from collections import Counter, defaultdict
import bpy
import bmesh
from mathutils import Vector

CUT=-1.400
C_FULL=-1.310
RAIL_END=-.73125
CROSS=6
GAP=.004
YS=(-1.380,-1.360,-1.330,-1.310,-1.295,-1.280,-1.270,-1.264,-1.250,-1.230,-1.2297)
CONTROL_YS=YS
YS=tuple(sorted((*YS,-1.345,-1.320)))
PARAMS=tuple(i/CROSS for i in range(CROSS+1))
TS=PARAMS[1:-1]

def smooth(t):
    t=max(0.,min(1.,t));return t*t*t*(10+t*(-15+6*t))

def section(row,y):
    hits=[]
    for tri in row['triangles']:
        ps=[row['vertices'][i] for i in tri]
        for a,b in zip(ps,ps[1:]+ps[:1]):
            if (a[1]<y)!=(b[1]<y):
                t=(y-a[1])/(b[1]-a[1]);hits.append([a[k]+t*(b[k]-a[k]) for k in range(3)])
    if not hits:
        hits=[list(p) for p in row['vertices'] if abs(p[1]-y)<1e-7]
    if not hits:raise ValueError('Missing actual section')
    return hits

def feature(ps):
    minx=min(abs(p[0]) for p in ps)
    # In the actual roof-supported stations, features0/1 share the exact
    # inboard X line. The outer top may be a few micrometers higher on the
    # asymmetric native roof, so global max-Z is not semantic feature0.
    inner=[p for p in ps if abs(p[0])<minx+1e-7]
    upper=max(inner,key=lambda p:p[2]) if ps[0][1]>=-.264001-1.0 else max(ps,key=lambda p:p[2])
    return [upper,min(inner,key=lambda p:p[2]),
            min(ps,key=lambda p:p[2]),max(ps,key=lambda p:abs(p[0])),max(ps,key=lambda p:abs(p[0])+p[2])]

def sash_top(frame,y):
    ps=section(frame,y);z=max(p[2] for p in ps)
    top=[p for p in ps if p[2]>z-1e-7]
    return [sum(p[0] for p in top)/len(top),y,z]

def rolled(a,d,theta,weight=1.):
    t=theta/(math.pi/2)
    line=[a[k]*(1-t)+d[k]*t for k in range(3)]
    arc=[a[0]+(d[0]-a[0])*math.sin(theta),a[1],d[2]+(a[2]-d[2])*math.cos(theta)]
    return [line[k]+weight*(arc[k]-line[k]) for k in range(3)]

def mesh_object(obj,points,faces,uvs,targets,mats,encode,label):
    mesh=bpy.data.meshes.new(obj.name+'_Private'+label); inv=obj.matrix_world.inverted()
    mesh.from_pydata([inv@Vector(p) for p in points],[],faces);mesh.update()
    bm=bmesh.new()
    try:bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh)
    finally:bm.free()
    lookup={tuple(sorted(f)):i for i,f in enumerate(faces)}
    if len(lookup)!=len(faces):raise ValueError('Duplicate authored triangle')
    normals=[];ordered={n:[] for n in uvs}
    for p in mesh.polygons:
        old=lookup[tuple(sorted(p.vertices))];p.material_index=mats[old];p.use_smooth=True
        for vi in p.vertices:
            j=3*old+faces[old].index(vi);normals.append(targets[j])
            for name in uvs:ordered[name].append(uvs[name][j])
    mesh.update();mesh.set_sharp_from_angle(angle=math.radians(35));mesh.update()
    auto=[tuple(n.vector) for n in mesh.corner_normals]
    normals=[n if n is not None else auto[i] for i,n in enumerate(normals)]
    for name,values in ordered.items():
        layer=mesh.uv_layers.new(name=name)
        for data,uv in zip(layer.data,values):data.uv=uv
    for m in obj.data.materials:mesh.materials.append(m)
    mesh.update();proof=encode(mesh,normals)
    candidate=bpy.data.objects.new(obj.name+'_Private'+label,mesh)
    candidate.matrix_world=obj.matrix_world.copy();bpy.context.scene.collection.objects.link(candidate)
    return candidate,proof

def ears(points,ids):
    if len(ids)==3:return [tuple(ids)]
    n=[0.,0.,0.]
    for a,b in zip(ids,ids[1:]+ids[:1]):
        p,q=points[a],points[b]
        for j,k,l in ((0,1,2),(1,2,0),(2,0,1)):n[j]+=(p[k]-q[k])*(p[l]+q[l])
    drop=max(range(3),key=lambda k:abs(n[k]));axes=[i for i in range(3)if i!=drop]
    ps={i:tuple(F(points[i][a])for a in axes)for i in ids}
    def cross(a,b,c):
        p,q,r=ps[a],ps[b],ps[c];return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    area=sum(ps[a][0]*ps[b][1]-ps[b][0]*ps[a][1]for a,b in zip(ids,ids[1:]+ids[:1]));sign=1 if area>0 else -1
    todo=list(ids);out=[]
    while len(todo)>3:
        choices=[]
        for j,b in enumerate(todo):
            a,c=todo[j-1],todo[(j+1)%len(todo)];size=sign*cross(a,b,c)
            if size<=0:continue
            if any(all(sign*cross(x,y,p)>=0 for x,y in ((a,b),(b,c),(c,a)))for p in todo if p not in (a,b,c)):continue
            choices.append((size,j,(a,b,c)))
        if not choices:raise ValueError('No exact projected ear; new polygon needs geometry correction')
        _,j,t=max(choices);out.append(t);todo.pop(j)
    out.append(tuple(todo));return out


def pillar(obj,old,frame,encode,profile):
    sign=-1 if obj.name.endswith('L') else 1
    if obj.name not in ('LOD0_StampedPillar_CL','LOD0_StampedPillar_CR'):raise ValueError('Wrong C target')
    points=[];faces=[];normals=[];uvs={n:[] for n in old['uvs']};mats=[];index={};outer_parameters={};outer_faces=[]
    def vertex(p):
        key=tuple(round(v,11) for v in p)
        if key not in index:index[key]=len(points);points.append(list(p))
        return index[key]
    def emit(ids,values=None,material=0,outer=False):
        faces.append(tuple(ids));mats.append(material)
        if outer:outer_faces.append(len(faces)-1)
        for j,i in enumerate(ids):
            target=None if values is None else values[j]['n']
            if outer and i in outer_parameters:
                y,t=outer_parameters[i];target=list((obj.matrix_world.to_3x3().transposed()@Vector(profile.normal(y,t))).normalized())
            normals.append(target)
            for name in uvs:uvs[name].append([abs(points[i][0])*2,points[i][1]*2+3] if values is None else values[j]['uv'][name])
    for tri,loops,material in zip(old['triangles'],old['triangle_loops'],old['triangle_materials']):
        ps=[{'p':old['vertices'][i],'n':old['normals'][j],'uv':{name:old['uvs'][name][j] for name in uvs}} for i,j in zip(tri,loops)]
        clipped=[]
        for a,b in zip(ps,ps[1:]+ps[:1]):
            ain=a['p'][1]<=CUT;bin=b['p'][1]<=CUT
            if ain:clipped.append(a)
            if ain!=bin:
                t=(CUT-a['p'][1])/(b['p'][1]-a['p'][1]);p=[a['p'][k]+t*(b['p'][k]-a['p'][k]) for k in range(3)];p[1]=CUT
                n=Vector(a['n']).lerp(Vector(b['n']),t).normalized()
                clipped.append({'p':p,'n':list(n),'uv':{name:[a['uv'][name][k]+t*(b['uv'][name][k]-a['uv'][name][k]) for k in range(2)] for name in uvs}})
        for j in range(1,len(clipped)-1):
            vals=[clipped[k] for k in (0,j,j+1)];emit([vertex(v['p']) for v in vals],vals,material)
    kept=len(faces)
    count=Counter(tuple(sorted((t[k],t[(k+1)%3]))) for t in faces for k in range(3))
    edges=[e for e,n in count.items() if n==1];adj=defaultdict(list)
    if any(abs(points[i][1]-CUT)>1e-8 for e in edges for i in e):raise ValueError('Unexpected lower boundary')
    for a,b in edges:adj[a].append(b);adj[b].append(a)
    if any(len(v)!=2 for v in adj.values()):raise ValueError('Broken lower boundary')
    start=max(adj,key=lambda i:(points[i][2],-abs(points[i][0])));loop=[start];prev=None;cur=start
    while True:
        nxt=next(v for v in adj[cur] if v!=prev)
        if nxt==start:break
        if nxt in loop:raise ValueError('Repeated cut cycle')
        loop.append(nxt);prev,cur=cur,nxt
    if len(loop)!=len(adj):raise ValueError('Multiple cut cycles')
    area=sum(abs(points[a][0])*points[b][2]-abs(points[b][0])*points[a][2] for a,b in zip(loop,loop[1:]+loop[:1]))
    if area<0:loop=[loop[0],*reversed(loop[1:])]
    ps=[points[i] for i in loop]
    feats=[0,min(range(len(ps)),key=lambda i:abs(ps[i][0])),min(range(len(ps)),key=lambda i:ps[i][2]),
           max(range(len(ps)),key=lambda i:abs(ps[i][0])),max(range(len(ps)),key=lambda i:abs(ps[i][0])+ps[i][2])]
    if feats!=sorted(set(feats)) or len(feats)!=5:raise ValueError('Unexpected five-feature cut cycle')
    rings=[];details=[]
    last_y=max(p[1] for p in old['vertices'])
    for y in YS:
        if abs(y-last_y)<1e-6:y=last_y
        old_y=sorted(set(p[1] for p in old['vertices'] if abs(p[1]-y)<1e-7))
        if old_y:y=old_y[0]
        f=feature(section(old,y));top=sash_top(frame,y);weight=smooth((y-CUT)/(C_FULL-CUT))
        a=profile.point(y,0.);d=profile.point(y,1.)
        inner=[d[0]-sign*.002,y,d[2]+.0015]
        inner=[f[2][k]+weight*(inner[k]-f[2][k]) for k in range(3)]
        ring=[f[0],f[1],inner,*[profile.point(y,t) for t in reversed(PARAMS)]]
        ids=[vertex(p) for p in ring]
        if len(set(ids))!=CROSS+4:raise ValueError('Collapsed C cross section')
        for j in range(CROSS+1):outer_parameters[ids[3+j]]=(y,PARAMS[CROSS-j])
        rings.append(ids);details.append({'y_m':y,'weight':weight,'original_features':f,'authored_ring':ring,'actual_sash_top':top})
    # Major feature correspondence is explicit; only the outer arc has extra samples.
    destinations=[0,1,2,3,CROSS+3]
    for k,a in enumerate(feats):
        b=feats[k+1] if k+1<5 else len(loop)
        cut_ids=[loop[j%len(loop)] for j in range(a,b+1)]
        da=destinations[k];db=destinations[k+1] if k+1<5 else CROSS+4
        next_ids=[rings[0][j%(CROSS+4)] for j in range(da,db+1)]
        # A bounded fan over each consistently named cut strip; first and last
        # endpoints are shared across all neighboring strips.
        for j in range(len(cut_ids)-1):emit((cut_ids[j],cut_ids[j+1],next_ids[0]),outer=k==3)
        for j in range(len(next_ids)-1):emit((cut_ids[-1],next_ids[j+1],next_ids[j]),outer=k==3)
    for a,b in zip(rings,rings[1:]):
        for i in range(CROSS+4):
            j=(i+1)%(CROSS+4);emit((a[i],a[j],b[j]),outer=3<=i<CROSS+3);emit((a[i],b[j],b[i]),outer=3<=i<CROSS+3)
    for triangle in ears(points,rings[-1]):emit(triangle)
    candidate,code=mesh_object(obj,points,faces,uvs,normals,mats,encode,'Outer50')
    return candidate,{'cut_y_m':CUT,'full_sash_closing_edge_y_m':C_FULL,'nominal_vertical_sash_gap_m':GAP,
                      'closed_section_lower_lip_m':[.002,.0015],'cross_spans':CROSS,'rings':details,'outer_faces':outer_faces,'profile':profile.record(),
                      'retained_clipped_lower_triangles':kept,'triangles':len(faces),'delta':len(faces)-len(old['triangles']),
                      'normal_encoding':code,'scope':'Authored upper C outer section; retained actual inner roof/tab features. Lower original triangles clipped at new plane; their field proof remains explicit pending.'}

def rail(obj,old,frame,encode,profile):
    sign=-1 if obj.name.endswith('L') else 1
    if obj.name not in ('LOD0_RoofSideRail_L','LOD0_RoofSideRail_R'):raise ValueError('Wrong rail target')
    points=[list(p) for p in old['vertices']];stations=[];moved=set();table=[]
    for i in range(10):
        nominal=-1.23+1.33*i/24
        if nominal>RAIL_END+1e-6:continue
        ys=[p[1] for p in points if abs(p[1]-nominal)<1e-6]
        if not ys:raise ValueError('Missing original rear rail station')
        y=min(ys,key=lambda y:abs(y-nominal));section_ids=[j for j,p in enumerate(points) if abs(p[1]-y)<1e-7]
        top=sash_top(frame,y);expected_z=top[2]+.007
        lows=[j for j in section_ids if abs(points[j][2]-expected_z)<2e-6 and abs(points[j][0])>.67]
        if len(lows)!=1:raise ValueError(('Unidentified original rail outer lower vertex',i,lows))
        low=lows[0];original=points[low][:]
        near=[j for j in section_ids if abs(abs(points[j][0])-(abs(original[0])-.002))<2e-6 and abs(points[j][2]-(original[2]+.0015))<2e-6]
        if len(near)!=1:raise ValueError('Unidentified original rail folded lower vertex')
        inner=near[0]
        outer=max(section_ids,key=lambda j:(abs(points[j][0]),points[j][2]))
        if outer==low or points[outer][2]<=original[2]:raise ValueError('Invalid true outer upper rail vertex')
        a=points[outer][:]
        weight=1-smooth((y+1.175)/(RAIL_END+1.175))
        desired=[top[0],y,top[2]+GAP]
        d=profile.point(y,1.);
        if math.dist(a,profile.point(y,0.))>2e-7:raise ValueError('Original rail upper boundary drift')
        points[low]=d;points[inner]=[d[0]-sign*.002,y,d[2]+.0015]
        moved|={low,inner}
        middle=[]
        for t in TS:
            middle.append(len(points));points.append(profile.point(y,t))
        stations.append([outer,*middle,low]);table.append({'y_m':y,'outer':outer,'old_low':original,'new_low':d,
            'inner':inner,'arc_indices':stations[-1],'weight':weight,'actual_sash_top':top})
    if len(stations)!=10:raise ValueError(('Expected ten original rear rail stations',len(stations)))
    ends={tuple(sorted((s[0],s[-1]))):s for s in (stations[0],stations[-1])}
    owners={v:i for i,s in enumerate(stations) for v in (s[0],s[-1])}
    parameters={v:(points[v][1],PARAMS[j]) for station in stations for j,v in enumerate(station)}
    replaced=[];faces=[];normals=[];uvs={n:[] for n in old['uvs']};mats=[];authored=[]
    def emit(ids,ti=None,weights=None):
        faces.append(tuple(ids));mats.append(0 if ti is None else old['triangle_materials'][ti])
        if ti is None:authored.append(len(faces)-1)
        for j,vi in enumerate(ids):
            if ti is None:
                y,t=parameters[vi];normals.append(list((obj.matrix_world.to_3x3().transposed()@Vector(profile.normal(y,t))).normalized()))
            elif any(v in moved for v in old['triangles'][ti]):
                normals.append(None)
            else:
                w=weights[j];normals.append(list(sum((Vector(old['normals'][li])*q for li,q in zip(old['triangle_loops'][ti],w)),Vector()).normalized()))
            for name in uvs:
                if ti is None:uvs[name].append([abs(points[vi][0])*2,points[vi][1]*2+3])
                else:uvs[name].append([sum(old['uvs'][name][li][k]*q for li,q in zip(old['triangle_loops'][ti],weights[j])) for k in range(2)])
    for ti,t in enumerate(old['triangles']):
        if all(v in owners for v in t) and max(owners[v] for v in t)-min(owners[v] for v in t)==1:
            replaced.append(ti);continue
        split=None
        for edge,station in ends.items():
            if all(v in t for v in edge):split=station;break
        if split is None:
            emit(t,ti,[[float(k==j) for k in range(3)] for j in range(3)]);continue
        a,b=split[0],split[-1];other=next(v for v in t if v not in (a,b))
        path=split if (t.index(b)-t.index(a))%3==1 else list(reversed(split))
        for x,y in zip(path,path[1:]):
            weights=[]
            for v in (x,y,other):
                if v==other:w=[float(k==t.index(other)) for k in range(3)]
                else:
                    f=PARAMS[split.index(v)];w=[0.,0.,0.];w[t.index(a)]=1-f;w[t.index(b)]=f
                weights.append(w)
            emit((x,y,other),ti,weights)
    if len(replaced)!=18:raise ValueError(('Unexpected exact outer wall triangle domain',replaced))
    for a,b in zip(stations,stations[1:]):
        for j in range(CROSS):emit((a[j],a[j+1],b[j+1]));emit((a[j],b[j+1],b[j]))
    candidate,code=mesh_object(obj,points,faces,uvs,normals,mats,encode,'Outer50')
    return candidate,{'original_outer_face_indices':replaced,'stations':table,'outer_faces':authored,'profile':profile.record(),'triangles':len(faces),
                      'delta':len(faces)-len(old['triangles']),'normal_encoding':code,
                      'scope':'New rear outer closing wall and adjacent lower fold. Actual inboard roof/rail/seal support geometry held. Terminal shared-edge subdivision is explicit; outside-field proof pending.'}


def rail_sections(old,frame,count=11):
    points=old['vertices'];out=[]
    for i in range(count):
        nominal=-1.23+1.33*i/24
        ys=[p[1] for p in points if abs(p[1]-nominal)<1e-6]
        if not ys:raise ValueError('Missing reference rail station')
        y=min(ys,key=lambda y:abs(y-nominal));ids=[j for j,p in enumerate(points) if abs(p[1]-y)<1e-7]
        top=sash_top(frame,y);expected=top[2]+.007
        low=[j for j in ids if abs(points[j][2]-expected)<2e-6 and abs(points[j][0])>.67]
        if len(low)!=1:raise ValueError('Missing native low rail feature')
        upper=max(ids,key=lambda j:(abs(points[j][0]),points[j][2]));inner=max(ids,key=lambda j:points[j][2])
        if upper==low[0]:raise ValueError('Collapsed reference upper boundary')
        out.append({'y':y,'a':points[upper],'d':points[low[0]],'b':points[inner],'sash':top,'upper':upper,'low':low[0]})
    return out

class Curve:
    def __init__(self,x,y):
        self.x=list(x);self.y=list(y)
        h=[b-a for a,b in zip(x,x[1:])]
        if any(v<=1e-7 for v in h):raise ValueError('Repeated or reversed smooth-track knots')
        d=[(b-a)/v for a,b,v in zip(y,y[1:],h)];m=[d[0]]
        for i in range(1,len(x)-1):
            if d[i-1]*d[i]<=0:m.append(0.)
            else:
                w1=2*h[i]+h[i-1];w2=h[i]+2*h[i-1]
                m.append((w1+w2)/(w1/d[i-1]+w2/d[i]))
        m.append(d[-1]);self.m=m
    def evaluate(self,x):
        if x<self.x[0]-1e-7 or x>self.x[-1]+1e-7:raise ValueError('Surface evaluation outside declared knots')
        i=next((j for j in range(len(self.x)-1) if x<=self.x[j+1]),len(self.x)-2)
        h=self.x[i+1]-self.x[i];t=(x-self.x[i])/h;a,b=self.y[i:i+2];u,v=self.m[i:i+2]
        f=(2*t**3-3*t*t+1)*a+(t**3-2*t*t+t)*h*u+(-2*t**3+3*t*t)*b+(t**3-t*t)*h*v
        df=((6*t*t-6*t)*a+(3*t*t-4*t+1)*h*u+(-6*t*t+6*t)*b+(3*t*t-2*t)*h*v)/h
        return f,df

class Surface:
    def __init__(self,knots,sign):
        self.knots=knots;self.sign=sign
        self.curves=[[Curve([q['y'] for q in knots],[q['controls'][i][k] for q in knots]) for k in (0,2)] for i in range(4)]
    def evaluate(self,y,t):
        if not 0<=t<=1:raise ValueError('Cross parameter outside formed span')
        controls=[];derivatives=[]
        for pair in self.curves:
            (x,dx),(z,dz)=[c.evaluate(y) for c in pair]
            controls.append([x,y,z]);derivatives.append([dx,1.,dz])
        b=[(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]
        db=[-3*(1-t)**2,3*(1-t)**2-6*t*(1-t),6*t*(1-t)-3*t*t,3*t*t]
        point=[sum(b[i]*controls[i][k] for i in range(4)) for k in range(3)]
        dy=[sum(b[i]*derivatives[i][k] for i in range(4)) for k in range(3)]
        dt=[sum(db[i]*controls[i][k] for i in range(4)) for k in range(3)]
        normal=Vector(dt).cross(Vector(dy))*self.sign
        if normal.length<=1e-10:raise ValueError('Singular authored surface tangent')
        return point,list(normal.normalized()),dy,dt
    def point(self,y,t):return self.evaluate(y,t)[0]
    def normal(self,y,t):return self.evaluate(y,t)[1]
    def record(self):return {'kind':'Single fair C upper-edge cubic at knots, C1 monotone control tracks and cubic Bezier formed cross profile; uniform cross stations and two measured longitudinal subdivisions','knots':self.knots,'cross_spans':CROSS,'cross_parameters':list(PARAMS),'rail_end_m':RAIL_END,'boundary':'Positions at original upper rail stations held. New formed outer field is the differential normal of this declared surface; original support, cap and lower field domains remain separate.'}

def make_surface(pillar_row,rail_row,frame):
    sign=-1 if pillar_row['name'].endswith('L') else 1
    rail_reference=rail_sections(rail_row,frame)
    fair_start=-1.310;fair_end=rail_reference[0]['y']
    a0=feature(section(pillar_row,fair_start))[4];am=feature(section(pillar_row,fair_start-.010))[4]
    a1=rail_reference[0]['a'];ap=rail_reference[1]['a'];span=fair_end-fair_start
    d0=[(a0[k]-am[k])/.010 for k in range(3)]
    d1=[(ap[k]-a1[k])/(ap[1]-a1[1]) for k in range(3)]
    def fair(y):
        t=(y-fair_start)/span
        return [(2*t**3-3*t*t+1)*a0[k]+(t**3-2*t*t+t)*span*d0[k]+(-2*t**3+3*t*t)*a1[k]+(t**3-t*t)*span*d1[k] for k in range(3)]
    inputs=[]
    for y in (CUT,*[v for v in CONTROL_YS if v< -1.2300001]):
        f=feature(section(pillar_row,y));top=sash_top(frame,y);weight=smooth((y-CUT)/(C_FULL-CUT))
        d=[f[3][k]+weight*([top[0],y,top[2]+GAP][k]-f[3][k]) for k in range(3)]
        a=fair(y) if y>=fair_start else f[4]
        inputs.append({'y':y,'a':a,'b':f[0],'d':d,'weight':weight})
    for q in rail_reference:
        weight=1-smooth((q['y']+1.175)/(RAIL_END+1.175))
        d=[q['d'][k]+weight*([q['sash'][0],q['y'],q['sash'][2]+GAP][k]-q['d'][k]) for k in range(3)]
        inputs.append({'y':q['y'],'a':q['a'],'b':q['b'],'d':d,'weight':weight})
    knots=[]
    for q in inputs:
        a,b,d=q['a'],q['b'],q['d'];w=q['weight'];height=a[2]-d[2];width=abs(d[0]-a[0])
        if height<=0:raise ValueError('Reversed formed wall vertical extent')
        m=max(0.,(b[2]-a[2])/max(1e-8,abs(a[0]-b[0])))
        k=.5522847498307936;run=width*k/(1+width*m*k/(height*(1-k)))
        direction=1 if d[0]>=a[0] else -1
        curved1=[a[0]+direction*run,q['y'],a[2]-run*m]
        curved2=[d[0],q['y'],d[2]+height*k]
        controls=[a]
        for j,curved in ((1,curved1),(2,curved2)):
            line=[a[k]+j/3*(d[k]-a[k]) for k in range(3)]
            controls.append([line[k]+w*(curved[k]-line[k]) for k in range(3)])
        controls.append(d);knots.append({'y':q['y'],'controls':controls,'reference_upper':a,'reference_top_inner':b,'weight':w})
    return Surface(knots,sign)
