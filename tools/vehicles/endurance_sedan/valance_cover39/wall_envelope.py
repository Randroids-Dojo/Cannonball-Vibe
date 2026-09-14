"""Current-input cover construction: wall_envelope. Source provenance is in the private port manifest."""

import math

import numpy as np

def hull(points):
    points=sorted(set(tuple(map(float,q)) for q in points))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lo=[];hi=[]
    for p in points:
        while len(lo)>1 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(points):
        while len(hi)>1 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return lo[:-1]+hi[:-1]

def prepare(body,x,zlo,zhi,clearance=.001002,sides=32):
    if not (clearance>0 and sides>=8 and sides%4==0 and zlo<zhi):
        raise ValueError('Invalid finite wall-envelope construction')
    vv=np.asarray(body['vertices']);tt=np.asarray(body['triangles']);q=vv[tt]
    nn=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);length=np.linalg.norm(nn,axis=1)
    sign=1 if x>0 else -1
    owners=np.flatnonzero(np.all(q[:,:,0]==x,axis=1)&(nn[:,0]*sign<-.999999*length))
    if not len(owners):raise ValueError('No actual axial receiving wall')
    radius=clearance/math.cos(math.pi/sides)
    disk=[(radius*math.cos(2*math.pi*i/sides),radius*math.sin(2*math.pi*i/sides)) for i in range(sides)]
    polygons=[];lines=[]
    for owner in owners:
        yz=q[owner,:,1:]
        poly=hull([(a[0]+b[0],a[1]+b[1]) for a in yz for b in disk])
        polygons.append(dict(actual_triangle=int(owner),polygon_yz=poly))
        for a,b in zip(poly,poly[1:]+poly[:1]):
            if a[1]==b[1]:continue
            if a[1]>b[1]:a,b=b,a
            lo=max(zlo,a[1]);hi=min(zhi,b[1])
            if hi<=lo:continue
            m=(b[0]-a[0])/(b[1]-a[1]);c=a[0]-m*a[1]
            lines.append(dict(lo=lo,hi=hi,m=m,c=c,actual_triangle=int(owner)))
    knots={zlo,zhi}|{r[k] for r in lines for k in ('lo','hi')}
    for i,a in enumerate(lines):
        for b in lines[i+1:]:
            lo=max(a['lo'],b['lo']);hi=min(a['hi'],b['hi'])
            if lo>=hi or abs(a['m']-b['m'])<1e-14:continue
            z=(b['c']-a['c'])/(a['m']-b['m'])
            if lo<z<hi:knots.add(z)
    pieces=[];knots=sorted(knots)
    for lo,hi in zip(knots,knots[1:]):
        if hi-lo<1e-14:continue
        z=(lo+hi)/2;active=[r for r in lines if r['lo']<=z<=r['hi']]
        if not active:raise ValueError('Expanded finite receiver has a missing section')
        r=min(active,key=lambda r:(r['m']*z+r['c'],r['actual_triangle']))
        row=dict(lo=lo,hi=hi,m=r['m'],c=r['c'],actual_triangle=r['actual_triangle'])
        if pieces and abs(pieces[-1]['m']-row['m'])<1e-11 and abs(pieces[-1]['c']-row['c'])<1e-11:
            pieces[-1]['hi']=hi
        else:pieces.append(row)
    points=[];offset_lines=[]
    for i,r in enumerate(pieces):
        y=r['m']*r['lo']+r['c'];p=[x,y,r['lo']]
        if points and abs(points[-1][1]-y)>1e-9:raise ValueError('Discontinuous finite union envelope')
        if not points:points.append(p)
        points.append([x,r['m']*r['hi']+r['c'],r['hi']])
        # y <= m*z+c is the common rear/exterior halfspace.
        n=np.asarray([-1.,r['m']]);n/=np.linalg.norm(n)
        offset_lines.append(dict(normal=n.tolist(),constant=-r['c']/math.sqrt(1+r['m']**2)))
    return points,dict(actual_faces=owners.tolist(),expanded_finite_triangles=polygons,
        generated_boundary=[dict(y=p[1],z=p[2]) for p in points],
        offset_lines=offset_lines,segments=pieces,clearance_inradius_m=clearance,
        circumscribed_sides=sides,maximum_polygon_radius_m=radius,
        method='Complete rear envelope of actual finite triangle Minkowski polygons; all active edge intersections included.',
        limit='This axial-wall envelope alone does not certify other actual receiver faces, stock, caps, or an assembled cover.')
