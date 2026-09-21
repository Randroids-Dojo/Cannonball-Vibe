"""Actual-input rear-channel construction primitive."""
import copy, math, struct
from collections import defaultdict, deque

def sub(a,b): return [x-y for x,y in zip(a,b)]

def dot(a,b): return sum(x*y for x,y in zip(a,b))

def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def unit(a):
    d=math.sqrt(dot(a,a))
    if d<1e-15: raise ValueError(('Degenerate vector',a))
    return [v/d for v in a]

def mix(a,b,t): return [x+(y-x)*t for x,y in zip(a,b)]

def f32(p): return [struct.unpack('<f',struct.pack('<f',v))[0] for v in p]

def normal(v,t): return unit(cross(sub(v[t[1]],v[t[0]]),sub(v[t[2]],v[t[0]])))

def area(v,t): return math.sqrt(dot(cross(sub(v[t[1]],v[t[0]]),sub(v[t[2]],v[t[0]])),cross(sub(v[t[1]],v[t[0]]),sub(v[t[2]],v[t[0]]))))/2

def clip(poly,axis,bound,above=True):
    """Clip polygon records with param q and actual position p; carry barycentrics."""
    out=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da=(a['q'][axis]-bound)*(1 if above else -1);db=(b['q'][axis]-bound)*(1 if above else -1)
        if da>=0: out.append(a)
        if (da<0<db) or (db<0<da):
            t=da/(da-db); q=mix(a['q'],b['q'],t);q[axis]=bound
            out.append({'q':q,'p':mix(a['p'],b['p'],t),'w':mix(a['w'],b['w'],t)})
    return out

def initial(old,ideal=None):
    r=copy.deepcopy(old)
    r['owners']=list(range(len(old['triangles'])))
    r['normal_corner_targets']=copy.deepcopy(ideal['normal_corner_targets'] if ideal else [[old['normals'][l] for l in ls] for ls in old['triangle_loops']])
    r['uv_corner_targets']=copy.deepcopy(ideal['uv_corner_targets'] if ideal else {n:[[vs[l] for l in ls] for ls in old['triangle_loops']] for n,vs in old['uvs'].items()})
    return r

def zipper(a,b):
    i=j=0;out=[]
    while i<len(a)-1 or j<len(b)-1:
        x=a[i+1][0] if i+1<len(a) else math.inf;y=b[j+1][0] if j+1<len(b) else math.inf
        if abs(x-y)<1e-11:out.extend([[a[i][1],b[j][1],b[j+1][1]],[a[i][1],b[j+1][1],a[i+1][1]]]);i+=1;j+=1
        elif x<y:out.append([a[i][1],b[j][1],a[i+1][1]]);i+=1
        else:out.append([a[i][1],b[j][1],b[j+1][1]]);j+=1
    return out

def orient(tris,fixed_count):
    em=defaultdict(list)
    for fi,t in enumerate(tris):
        for a,b in zip(t,t[1:]+t[:1]):em[min(a,b),max(a,b)].append((fi,a<b))
    bad=[(e,fs) for e,fs in em.items() if len(fs)!=2]
    if bad:raise ValueError(('Incomplete connected construction edges',bad[:12],len(bad)))
    flips={i:False for i in range(fixed_count)};queue=deque(flips)
    while queue:
        fi=queue.popleft();t=tris[fi]
        for a,b in zip(t,t[1:]+t[:1]):
            pair=em[min(a,b),max(a,b)];other,sign=next(p for p in pair if p[0]!=fi);need=flips[fi]^((a<b)==sign)
            if other in flips:
                if flips[other]!=need:raise ValueError(('Contradictory connected orientation',fi,other))
            else:flips[other]=need;queue.append(other)
    if len(flips)!=len(tris):raise ValueError(('Detached shell',len(flips),len(tris)))
    for i,f in flips.items():
        if f:tris[i]=list(reversed(tris[i]))
    return [i for i,f in flips.items() if f]
