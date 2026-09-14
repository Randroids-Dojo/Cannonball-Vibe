"""Current-input cover construction: mounts. Source provenance is in the private port manifest."""

from collections import Counter

import math

import numpy as np

from . import cover as cover36

from . import domain as domain07

from . import base_mesh as mesh16

GAUGE = .0012

CENTERS = (-.45, -.31, .31, .45)

NAMES = ('LOD0_RearValanceMount_L1','LOD0_RearValanceMount_L2',
         'LOD0_RearValanceMount_R1','LOD0_RearValanceMount_R2')

def placed(cover):
    """Uniform third-form placement; all relative native positions exact."""
    result = dict(cover)
    result['vertices'] = [[x,cover36.f32(y-.0008),z] for x,y,z in cover['vertices']]
    shifts = {q[1]-p[1] for p,q in zip(cover['vertices'],result['vertices'])}
    if len(shifts)!=1: raise ValueError('Placement is not one exact rigid native translation')
    result['nominal_outer_y_reveal_m'] = .0038
    result['common_translation_y_m'] = next(iter(shifts))
    result['geometry_authoring'] += '; uniform 3.8 mm nominal outward reveal'
    return result

def plane_at(x,z,current,roles,exact):
    if len(roles)!=len(current['triangles']): raise ValueError('Missing actual backing roles')
    choices=[]
    for i,(ids,role) in enumerate(zip(current['triangles'],roles)):
        if role!='back': continue
        p=[exact.vector(current['vertices'][j]) for j in ids]
        n=exact.cross(exact.sub(p[1],p[0]),exact.sub(p[2],p[0]))
        if not n[1]: continue
        c=(-n[0]/n[1],-n[2]/n[1],exact.dot(n,p[0])/n[1])
        q=(exact.F(x),c[0]*exact.F(x)+c[1]*exact.F(z)+c[2],exact.F(z))
        xz={j:(v[0],v[2]) for j,v in enumerate(p)}
        signs=[]
        for j in range(3):
            a,b=xz[j],xz[(j+1)%3]
            signs.append((b[0]-a[0])*(q[2]-a[1])-(b[1]-a[1])*(q[0]-a[0]))
        if min(signs)>=0 or max(signs)<=0: choices.append((q[1],i,c,n))
    if not choices: raise ValueError('No actual backing facet at declared land')
    _,i,c,n=min(choices)
    normal=cover36.unit(list(map(float,n)))
    return c,i,normal

class Builder:
    def __init__(self,name,materials,uv_names,exact):
        self.name=name;self.materials=materials;self.uv_names=uv_names;self.e=exact
        self.vertices=[];self.lookup={};self.triangles=[];self.domains=[];self.rounding=[]

    def vertex(self,p):
        native=tuple(cover36.f32(x) for x in p)
        error=math.sqrt(sum((float(a)-b)**2 for a,b in zip(p,native)))
        if error>1e-6: raise ValueError('Support vertex exceeds native geometry guard')
        if native not in self.lookup:
            self.lookup[native]=len(self.vertices);self.vertices.append(list(native))
            self.rounding.append(error)
        return self.lookup[native]

    def polygon(self,points,domain,axes,direction):
        ids=[]
        for p in points:
            i=self.vertex(p)
            if not ids or ids[-1]!=i:ids.append(i)
        if ids[0]==ids[-1]:ids.pop()
        if len(set(ids))!=len(ids) or len(ids)<3:raise ValueError('Collapsed/repeated support polygon')
        coords={i:tuple(self.e.F(self.vertices[i][j]) for j in axes) for i in ids}
        tris=mesh16.ears(ids,coords)
        out=[]
        for tri in tris:
            tri=list(tri);v=np.asarray(self.vertices)[tri]
            if np.dot(np.cross(v[1]-v[0],v[2]-v[0]),direction)<0:tri.reverse()
            out.append(len(self.triangles));self.triangles.append(tri);self.domains.append(domain)
        return out

    def result(self):
        normals=[];uvs={n:[] for n in self.uv_names}
        for tri in self.triangles:
            v=np.asarray(self.vertices)[tri];n=cover36.unit(np.cross(v[1]-v[0],v[2]-v[0]))
            normals.append([n.tolist()]*3);axes=[j for j in range(3) if j!=int(np.argmax(abs(n)))]
            for name in uvs:uvs[name].append([[self.vertices[i][j]*4 for j in axes] for i in tri])
        row=dict(name=self.name,vertices=self.vertices,triangles=self.triangles,
                 triangle_domains=self.domains,requested_triangle_normals=normals,
                 triangle_uvs=uvs,materials=self.materials,
                 maximum_native_quantization_m=max(self.rounding,default=0.))
        domain07.validate(row)
        edges=Counter((a,b) for t in self.triangles for a,b in zip(t,t[1:]+t[:1]))
        bad=[(a,b,count,edges[(b,a)]) for (a,b),count in edges.items() if count!=1 or edges[(b,a)]!=1]
        if bad:raise ValueError('Open/nonmanifold support: '+repr(bad[:8]))
        return row

def prepare(cover,current,roles,exact):
    """The caller validates roles and rechecks all complete finite current mates."""
    domain07.validate(cover);domain07.validate(current)
    if set(cover['triangle_domains'])!={'outer','inner','rim'}:raise ValueError('Incomplete actual cover domains')
    inner=[i for i,d in enumerate(cover['triangle_domains']) if d=='inner']
    rows={}
    for name,cx in zip(NAMES,CENTERS):
        coeff,owner,normal=plane_at(cx,.2815,current,roles,exact)
        # The back plate's actual finite normal gauge, rather than assumed Y thickness.
        delta_y=GAUGE/abs(float(normal[1]))
        inset=GAUGE if name=='LOD0_RearValanceMount_L1' else 0.
        land_left=cover36.f32(cx-.010)
        lx,li,ri,rx=[cover36.f32(x) for x in (cx-.010+inset,cx-.010+inset+GAUGE,cx+.010-GAUGE,cx+.010)]
        low,high=[cover36.f32(z) for z in (.2765,.2865)]
        b=Builder(name,cover['materials'],list(cover['triangle_uvs']),exact)
        def rear(x,z,inward=False):
            y=coeff[0]*exact.F(x)+coeff[1]*exact.F(z)+coeff[2]
            if inward:y-=exact.F(delta_y)
            return [x,y,z]
        def front_strip(a,c,label):
            clips=[((exact.F(1),exact.F(0),exact.F(0)),exact.F(a)),
                   ((exact.F(-1),exact.F(0),exact.F(0)),-exact.F(c)),
                   ((exact.F(0),exact.F(0),exact.F(1)),exact.F(low)),
                   ((exact.F(0),exact.F(0),exact.F(-1)),-exact.F(high))]
            ids=[];source=[]
            for i in inner:
                tri=[exact.vector(cover['vertices'][v]) for v in cover['triangles'][i]]
                hit,_=exact.partition(tri,clips)
                if not hit:continue
                # Exact partition retains boundary-only polygons; they have no cap area.
                area=sum(p[0]*q[2]-p[2]*q[0] for p,q in zip(hit,hit[1:]+hit[:1]))
                if not area:continue
                new=b.polygon(hit,label,[0,2],[0,-1,0]);ids.extend(new)
                source.extend([i]*len(new))
            if not ids:raise ValueError('Missing complete front strip')
            verts={v for i in ids for v in b.triangles[i]}
            def line(axis,value,sortaxis):
                points=[b.vertices[v] for v in verts if b.vertices[v][axis]==value]
                points.sort(key=lambda p:p[sortaxis])
                if len(points)<2 or len({p[sortaxis] for p in points})!=len(points):raise ValueError('Ambiguous cap edge')
                return points
            return dict(triangles=ids,source_cover_triangles=source,
                        left=line(0,a,2),right=line(0,c,2),
                        lower=line(2,low,0),upper=line(2,high,0))
        left=front_strip(lx,li,'cover_cap_left');right=front_strip(ri,rx,'cover_cap_right')
        for x,profile,isinner,direction,label in [
                (lx,left['left'],bool(inset),[-1,0,0],'outer_web_left'),
                (li,left['right'],True,[1,0,0],'inner_web_left'),
                (ri,right['left'],True,[-1,0,0],'inner_web_right'),
                (rx,right['right'],False,[1,0,0],'outer_web_right')]:
            b.polygon(profile+[rear(x,high,isinner),rear(x,low,isinner)],label,[1,2],direction)
        foot=b.polygon([rear(land_left,low),rear(rx,low),rear(rx,high),rear(land_left,high)],'body_land',[0,2],[0,1,0])
        if inset:
            b.polygon([rear(land_left,low,True),rear(lx,low,True),rear(lx,high,True),rear(land_left,high,True)],'back_plate_flange',[0,2],[0,-1,0])
            b.polygon([rear(land_left,low,True),rear(land_left,high,True),rear(land_left,high),rear(land_left,low)],'flange_outer_left',[1,2],[-1,0,0])
        b.polygon([rear(li,low,True),rear(ri,low,True),rear(ri,high,True),rear(li,high,True)],
                  'back_plate_inner',[0,2],[0,-1,0])
        for z,key,sign in ((low,'lower',-1),(high,'upper',1)):
            points=[left[key][0]]
            if inset:points += [rear(lx,z,True),rear(land_left,z,True)]
            points += [rear(land_left,z),rear(rx,z)]+list(reversed(right[key]))
            points += [rear(ri,z,True),rear(li,z,True)]+list(reversed(left[key]))
            b.polygon(points,'bottom' if sign<0 else 'top',[0,1],[0,0,sign])
        row=b.result()
        row['finite_interfaces']={'body_land_triangles':foot,
            'cover_left':{'triangles':left['triangles'],'source_cover_triangles':left['source_cover_triangles']},
            'cover_right':{'triangles':right['triangles'],'source_cover_triangles':right['source_cover_triangles']}}
        row['declared_land']={'center_xz_m':[cx,.2815],'size_xz_m':[.020,.010],
            'actual_bounds_xz_m':[[land_left,low],[rx,high]],'left_web_inset_m':inset,'current_back_triangle':owner,
            'normal_plate_gauge_m':GAUGE,'plate_y_depth_m':delta_y,'web_x_gauge_m':GAUGE}
        rows[name]=row
    return rows
