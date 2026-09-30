"""One opposed stock section per actual finite receiving facet, no IO."""
import math
from collections import defaultdict
from .vectors import sub,dot,cross,unit,normal,f32
from .maths import closest_double
from .mesh import ear_indices


def hull(ids, q):
    ids=sorted(set(ids),key=lambda i:tuple(q[i]))
    def turn(a,b,c):return (q[b][0]-q[a][0])*(q[c][1]-q[a][1])-(q[b][1]-q[a][1])*(q[c][0]-q[a][0])
    lo=[];hi=[]
    for i in ids:
        while len(lo)>1 and turn(lo[-2],lo[-1],i)<=1e-13:lo.pop()
        lo.append(i)
    for i in reversed(ids):
        while len(hi)>1 and turn(hi[-2],hi[-1],i)<=1e-13:hi.pop()
        hi.append(i)
    return lo[:-1]+hi[:-1]


def bary(p,a,b,c):
    u,v,w=sub(b,a),sub(c,a),sub(p,a);uu,uv,vv,wu,wv=dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
    den=uu*vv-uv*uv;y=(wu*vv-wv*uv)/den;z=(wv*uu-wu*uv)/den
    return [1-y-z,y,z]


def opposed_section(receiver, footv, footq, foott, parents, arrival, wall_reference, miter, complete_wall_normals=None):
    groups=defaultdict(list)
    for t,p in zip(foott,parents):groups[p['face']].extend(t)
    polys={fi:hull(ids,footq) for fi,ids in groups.items()};inc=defaultdict(list)
    for fi,ids in polys.items():
        for i in ids:inc[i].append(fi)
    wall={}
    for fi,ids in polys.items():
        edge=sorted((footq[i][0],i) for i in ids if abs(footq[i][1])<1e-10)
        if len(edge)==2:
            n=unit(cross(sub(footv[edge[1][1]],footv[edge[0][1]]),arrival or [1.,0.,0.]))
            if dot(n,wall_reference)<0:n=[-x for x in n]
            wall[fi]=n
    stock={};proof=[]
    for i,fs in inc.items():
        ns=[[-x for x in normal(receiver['vertices'],receiver['triangles'][fi])] for fi in fs]
        anchors=[receiver['vertices'][receiver['triangles'][fi][0]] for fi in fs]
        if abs(footq[i][1])<1e-10:
            if complete_wall_normals:
                ns.extend(complete_wall_normals);anchors.extend([footv[i]]*len(complete_wall_normals))
            else:
                for fi in fs:
                    if fi in wall:ns.append(wall[fi]);anchors.append(footv[i])
        stock[i],p=miter(footv[i],ns,anchors,depth=.001205)
        proof.append({'source_foot_vertex':i,'source_faces':fs,**p})
    triangles=[(fi,[ids[i] for i in t]) for fi,ids in polys.items() for t in ear_indices([footv[i] for i in ids])]
    result=[];transport=[]
    for i,p in enumerate(footv):
        choices=[]
        for fi,t in triangles:
            ps=[footv[j] for j in t];q=closest_double(p,*ps)
            choices.append((math.dist(p,q),fi,t,bary(q,*ps)))
        d,fi,t,w=min(choices,key=lambda x:x[0])
        if d>2e-7:raise ValueError(('Complete finite receiver transport',i,d))
        result.append(f32([sum(w[j]*stock[t[j]][k] for j in range(3)) for k in range(3)]))
        transport.append({'foot_vertex':i,'source_face':fi,'source_triangle':t,'weights':w,'residual_m':d})
    return result,{'finite_parent_polygons':polys,'coarse_stock':proof,'transport':transport,'coarse_wall_normals':wall}
