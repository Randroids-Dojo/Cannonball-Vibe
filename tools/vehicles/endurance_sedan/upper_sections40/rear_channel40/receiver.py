"""Whole finite receiving stamping, incorporating recorded wall amendment.
Pure arrays; no source IO. Uses a common physical deformation for every face.
"""
from collections import defaultdict
import math
from .mesh import empty, initial, old_face, new_face, ear_indices
from .vectors import f32, clip, sub, dot, unit


def build(old, band, side, ideal=None):
    r=empty(old,ideal); original=initial(old,ideal);sgn=1 if side=='R'else-1
    owned=set(band['unchanged_top_parents'])|{f['face']for f in band['complete_end_band_parents']}
    # This finite mask is exactly receiver-band606 and the recorded amendment.
    def target(p):
        x=sgn*p[0];dx=max(0.,min(1.,(x-.8205)/.001,(.878-x)/.002))
        dz=max(0.,min(1.,(p[2]-1.009)/.0025))
        return f32([p[0],p[1],p[2]-.00019995*dx*dz])
    plans={}; edgecuts=defaultdict(dict);boundary_nodes=[]
    for fi in sorted(owned):
        t=old['triangles'][fi]
        polys=[[{'p':old['vertices'][v],'q':[sgn*old['vertices'][v][0],old['vertices'][v][2]],
                 'w':[float(j==k)for k in range(3)]}for j,v in enumerate(t)]]
        # First separate the exact unchanged sheet outside the finite
        # receiver. X grid lines must not continue through lower Door corners
        # where dz is zero: they create unnecessary nearly collinear slivers
        # after float32 parent-coordinate baking.
        unchanged=[]; active=[]
        for poly in polys:
            z=[v['q'][1] for v in poly]
            if max(z)<=1.009:unchanged.append(poly)
            elif min(z)>=1.009:active.append(poly)
            else:
                unchanged.append(clip(poly,1,1.009,False))
                active.append(clip(poly,1,1.009))
        for bound,keep_above in ((.8205,True),(.878,False)):
            inside=[]
            for poly in active:
                ds=[v['q'][0]-bound for v in poly]
                if min(ds)<0<max(ds):
                    inside.append(clip(poly,0,bound,keep_above))
                    unchanged.append(clip(poly,0,bound,not keep_above))
                elif (min(ds)>=0 if keep_above else max(ds)<=0):inside.append(poly)
                else:unchanged.append(poly)
            active=inside
        for ax,b in ((0,.8215),(0,.876),(1,1.0115)):
            parts=[]
            for poly in active:
                ds=[v['q'][ax]-b for v in poly]
                parts.extend([clip(poly,ax,b),clip(poly,ax,b,False)] if min(ds)<0<max(ds) else [poly])
            active=parts
        polys=[poly for poly in unchanged+active if len(poly)>=3]
        # Conform all adjacent active/inactive polygons in their common
        # source-triangle barycentric parameter space. Only existing boundary
        # nodes are inserted; no line continues through the inactive interior.
        nodes={tuple(round(x,13) for x in q['w']):q for poly in polys for q in poly}
        conformed=[]
        for poly in polys:
            result=[]
            for A,B in zip(poly,poly[1:]+poly[:1]):
                result.append(A);D=sub(B['w'],A['w']);den=dot(D,D)
                if den<=1e-26:raise ValueError('Coincident source partition edge')
                inserts=[]
                for q in nodes.values():
                    u=dot(sub(q['w'],A['w']),D)/den
                    if not 1e-12<u<1-1e-12:continue
                    residual=math.sqrt(sum((q['w'][k]-A['w'][k]-u*D[k])**2 for k in range(3)))
                    if residual<=1e-12:inserts.append((u,q,residual))
                for u,q,residual in sorted(inserts,key=lambda item:item[0]):
                    result.append(q);boundary_nodes.append({'source_face':fi,'source_weights':q['w'][:],'edge_weights':[A['w'][:],B['w'][:]],'fraction':u,'barycentric_edge_residual':residual})
            conformed.append(result)
        plans[fi]=conformed
        for poly in conformed:
            for v in poly:
                ix=[i for i,w in enumerate(v['w'])if w>1e-12]
                if len(ix)==2:
                    e=tuple(sorted(t[i]for i in ix));p=f32(v['p']);edgecuts[e][tuple(p)]=p
    for fi,t in enumerate(old['triangles']):
        if fi in plans:continue
        poly=[]
        for j,(a,b)in enumerate(zip(t,t[1:]+t[:1])):
            A=old['vertices'][a];D=sub(old['vertices'][b],A);den=dot(D,D)
            poly.append({'p':A,'w':[float(j==k)for k in range(3)]})
            for u,p in sorted((dot(sub(p,A),D)/den,p)for p in edgecuts.get(tuple(sorted((a,b))),{}).values()):
                if 1e-10<u<1-1e-10:
                    w=[0.,0.,0.];w[j]=1-u;w[(j+1)%3]=u;poly.append({'p':p,'w':w})
        if len(poly)>3:plans[fi]=[poly]
    cache={tuple(p):i for i,p in enumerate(old['vertices'])};fragments=[]
    def vertex(rec):
        p=f32(rec['p']);key=tuple(p)
        if key not in cache:cache[key]=len(r['vertices']);r['vertices'].append(p)
        vi=cache[key];r['vertices'][vi]=target(p);return vi
    for fi,t in enumerate(old['triangles']):
        if fi not in plans:old_face(r,old,fi,ideal);continue
        for poly in plans[fi]:
            ids=[vertex(v)for v in poly]
            for ix in ear_indices([v['p']for v in poly]):
                moved=any(r['vertices'][ids[k]]!=f32(poly[k]['p'])for k in ix)
                if moved and fi not in owned:raise ValueError(('Outside finite receiving parent moved',fi))
                uv={n:[[sum(poly[k]['w'][j]*values[fi][j][c]for j in range(3))for c in range(2)]for k in ix]
                    for n,values in original['uv_corner_targets'].items()}
                ns=None if moved else[unit([sum(poly[k]['w'][j]*original['normal_corner_targets'][fi][j][c]for j in range(3))for c in range(3)])for k in ix]
                new_face(r,[ids[k]for k in ix],'authored_receiver'if moved else'retained_fragment',old['triangle_materials'][fi],fi,uv,ns)
                fragments.append({'face':len(r['triangles'])-1,'source_face':fi,'source_weights':[poly[k]['w']for k in ix],'moved':moved})
    changes=[i for i,p in enumerate(old['vertices'])if r['vertices'][i]!=p]
    maxd=max([math.dist(old['vertices'][i],r['vertices'][i])for i in changes]or[0])
    assert maxd<=.0002,maxd
    return r,{'exact_source_parents':sorted(owned),'shared_deformation':'trapezoid(absX)*linear_Z1.009..1.0115',
              'subdivision_domain':'Only the finite active receiver footprint; inactive lower/side source polygons remain whole',
              'maximum_native_displacement_m':maxd,'original_vertices_changed':changes,'fragments':fragments,
              'net_triangles':len(r['triangles'])-len(old['triangles']), 'conforming_active_boundary_nodes':boundary_nodes}
