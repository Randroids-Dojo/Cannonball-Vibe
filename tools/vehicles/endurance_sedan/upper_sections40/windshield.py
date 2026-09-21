"""Functional planar windshield with one connected front header/aperture.

Pure current-input arrays. The caller supplies the actual proved planar
windshield role from fresh construction, not an archived replacement mesh.
Rear Roof, Backlight, the middle boundary and all wiper roles are untouched.
"""
import copy, math, struct
from collections import defaultdict


def sub(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def unit(a):
    d=math.hypot(*a)
    if d<1e-15:raise ValueError('Degenerate physical header direction')
    return [v/d for v in a]
def mix(a,b,t):return [x+(y-x)*t for x,y in zip(a,b)]
def f32(p):return [struct.unpack('<f',struct.pack('<f',x))[0]for x in p]
def smooth(t):
    t=max(0.,min(1.,t));return t*t*t*(10+t*(-15+6*t))
def field_row(old):
    r=copy.deepcopy(old)
    if 'normal_corner_targets' not in r:r['normal_corner_targets']=[[old['normals'][l]for l in ls]for ls in old['triangle_loops']]
    if 'uv_corner_targets' not in r:r['uv_corner_targets']={c:[[vs[l]for l in ls]for ls in old['triangle_loops']]for c,vs in old['uvs'].items()}
    return r


def mask(row,moving):
    owned=[i for i,t in enumerate(row['triangles'])if set(t)&set(moving)]
    allowned=set(owned);stars=defaultdict(set)
    for i,t in enumerate(row['triangles']):
        for v in t:stars[v].add(i)
    return {'moving_vertices':sorted(moving),'owned_faces':owned,
            'fixed_boundary_vertices':sorted(v for v,fs in stars.items()if fs&allowned and fs-allowned),
            'source_faces':[{'face':i,'indices':row['triangles'][i],'points':[row['vertices'][v]for v in row['triangles'][i]]}for i in owned]}


def finish(row,old,scope,kind):
    owned=scope['owned_faces'];boundary=set(scope['fixed_boundary_vertices']);sums=defaultdict(lambda:[0.,0.,0.])
    for i in owned:
        t=row['triangles'][i];n=unit(cross(sub(row['vertices'][t[1]],row['vertices'][t[0]]),sub(row['vertices'][t[2]],row['vertices'][t[0]])))
        for v in t:sums[kind(i,t),v]=[a+b for a,b in zip(sums[kind(i,t),v],n)]
    for i in owned:
        t=row['triangles'][i]
        row['normal_corner_targets'][i]=[old['normal_corner_targets'][i][j]if v in boundary else unit(sums[kind(i,t),v])for j,v in enumerate(t)]
        for c in row['uv_corner_targets']:
            row['uv_corner_targets'][c][i]=[old['uv_corner_targets'][c][i][j]if v in boundary else f32([row['vertices'][v][0]/.25,row['vertices'][v][1]/.25])for j,v in enumerate(t)]


def build(current,planar_windshield):
    """Return the original functional pane and coherent front Roof/seal arrays."""
    pane=field_row(planar_windshield);pane['name']='LOD0_Windshield'
    roof=field_row(current['LOD0_Roof']);seal=field_row(current['LOD0_WindshieldSeal'])
    oldroof=copy.deepcopy(roof);oldseal=copy.deepcopy(seal)
    if len(pane['vertices'])!=126 or len(pane['triangles'])!=248:raise ValueError('Planar windshield role topology drift')
    if len(roof['vertices'])!=486 or len(seal['vertices'])!=84:raise ValueError('Connected header role topology drift')
    a0,b0,a1,b1=[pane['vertices'][i]for i in(0,56,6,62)]
    n=unit(cross(sub(b1,a1),sub(a0,a1)))
    if n[2]<0:n=[-v for v in n]
    if max(abs(dot(sub(p,a0),n))for p in pane['vertices'][:63])>1e-6:raise ValueError('Required actual contact surface is not planar')
    def flat(u,v):return mix(mix(a0,b0,(u+1)/2),mix(a1,b1,(u+1)/2),v)
    tangent=unit(cross(n,sub(b1,a1)))
    if tangent[2]<0:tangent=[-v for v in tangent]
    def desired(u):return [p+.002*t for p,t in zip(flat(u,1.),tangent)]
    def previous(u):
        t=(u+1)*4;k=max(0,min(7,int(t)));return mix(oldroof['vertices'][468+k],oldroof['vertices'][469+k],t-k)
    moving=set(range(468,486))
    moving.update(i*15+j-1+layer for i in range(15)for j in(14,15)for layer in(0,225))
    roof_mask=mask(roof,moving);seal_mask=mask(seal,range(24,78))
    # Masks are complete before the first coordinate assignment.
    for i in range(15):
        u=i/7-1;delta=sub(desired(u),previous(u))
        for j in(14,15):
            w=1-smooth((16-j)/3)
            for layer in(0,225):
                v=i*15+j-1+layer;roof['vertices'][v]=f32([oldroof['vertices'][v][k]+w*delta[k]for k in range(3)])
    stations=[]
    for i in range(9):
        u=i/4-1;p=desired(u);off=sub(oldroof['vertices'][477+i],oldroof['vertices'][468+i])
        roof['vertices'][468+i]=f32(p);roof['vertices'][477+i]=f32([p[k]+off[k]for k in range(3)])
        stations.append({'u':u,'pane':flat(u,1.),'Roof':roof['vertices'][468+i]})
    outer=set(range(225))|set(range(450,459))|set(range(468,477))
    inner=set(range(225,450))|set(range(459,468))|set(range(477,486))
    def roof_kind(i,t):return 'outer'if set(t)<=outer else'inner'if set(t)<=inner else('rim',i)
    finish(roof,oldroof,roof_mask,roof_kind)
    params=[(-1,0),(0,0),(1,0),(1,.5)]+[(1-k/4,1)for k in range(9)]+[(-1,.5)]
    def curved(u,v):
        p=flat(u,v);weight=(1-u*u)*max(0.,2*v-1)**2
        return [p[0],p[1]+.02*weight,p[2]+.03*weight]
    def curved_normal(u,v):
        h0=(b0[0]-a0[0])/2;h1=(b1[0]-a1[0])/2;t=max(0.,2*v-1);long=sub(mix(a1,b1,.5),mix(a0,b0,.5))
        du=[h0+(h1-h0)*v,-2*u*.02*t*t,-2*u*.03*t*t]
        dv=[u*(h1-h0),long[1]+4*t*(1-u*u)*.02,long[2]+4*t*(1-u*u)*.03]
        nn=unit(cross(du,dv));return nn if dot(nn,n)>0 else[-x for x in nn]
    oldpath=[curved(u,v)for u,v in params];newpath=[flat(u,v)for u,v in params]
    for ring in range(4,13):
        u,v=params[ring];on=curved_normal(u,v)
        ot=sub(oldpath[(ring+1)%14],oldpath[(ring-1)%14]);ot=unit([ot[k]-dot(ot,on)*on[k]for k in range(3)]);ob=unit(cross(ot,on))
        nt=sub(newpath[(ring+1)%14],newpath[(ring-1)%14]);nt=unit([nt[k]-dot(nt,n)*n[k]for k in range(3)]);nb=unit(cross(nt,n))
        for j in range(6):
            index=ring*6+j;off=sub(oldseal['vertices'][index],oldpath[ring]);coords=[dot(off,ot),dot(off,ob),dot(off,on)]
            seal['vertices'][index]=f32([newpath[ring][k]+coords[0]*nt[k]+coords[1]*nb[k]+coords[2]*n[k]for k in range(3)])
    # Each actual section face is its own physical normal domain around the
    # six-point rubber section; share the field along the smooth path only.
    def seal_kind(i,t):
        phases=tuple(sorted({v%6 for v in t}));return phases
    finish(seal,oldseal,seal_mask,seal_kind)
    return {'parts':{'LOD0_Windshield':pane,'LOD0_Roof':roof,'LOD0_WindshieldSeal':seal},
            'masks':{'LOD0_Roof':roof_mask,'LOD0_WindshieldSeal':seal_mask},
            'shared_header_stations':stations,'net_triangles':0,
            'planar_contact_surface_exact':True,'wiper_roles_changed':[],
            'maximum_header_displacement_m':max(math.dist(a,b)for a,b in zip(oldroof['vertices'],roof['vertices'])),
            'maximum_gasket_displacement_m':max(math.dist(a,b)for a,b in zip(oldseal['vertices'],seal['vertices'])),
            'pending':['native encoding and field replay','complete Roof/front receiver stock and finite joints','combined wiper/trim sweep','actual whole-car visual comparison']}
