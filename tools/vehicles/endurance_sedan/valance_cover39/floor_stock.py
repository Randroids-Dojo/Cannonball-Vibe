"""Current-input cover construction: floor_stock. Source provenance is in the private port manifest."""

import numpy as np

def derive(layout, minimum_norm, gauge=.0012):
    vv=np.asarray(layout['vertices']);facets=[]
    for index,(t,role) in enumerate(zip(layout['added'],layout['authored_patch_domains'])):
        if role!='bottom_return':continue
        p=vv[t]
        if not np.all(p[:,2]==p[0,2]):raise ValueError('Expected actual horizontal bottom stock facet')
        xy=p[:,:2];area=sum(float(a[0]*b[1]-a[1]*b[0]) for a,b in zip(xy,np.roll(xy,-1,axis=0)))
        if not area:raise ValueError('Collapsed actual bottom footprint')
        if area<0:xy=xy[::-1]
        edges=[]
        for a,b in zip(xy,np.roll(xy,-1,axis=0)):
            d=b-a;n=np.array([-d[1],d[0]]);n/=np.linalg.norm(n);edges.append((n,float(n@a)-gauge))
        facets.append(dict(index=index,low=xy.min(0)-gauge,high=xy.max(0)+gauge,edges=edges,z=float(p[0,2])+gauge))
    if not facets:raise ValueError('No complete actual bottom sheet')
    records=[]
    def prepare(vertices, inner, constraints, movable):
        initial=np.asarray(vertices).copy()
        for v,planes in constraints.items():
            if v in movable:
                unique={tuple(np.round(n,10))+(round(c,10),):(n,c) for n,c in planes}
                initial[v]=minimum_norm(list(unique.values()),initial[v])
        extra={}
        for index,row in enumerate(inner):
            p=initial[row['ids'],:2];low=p.min(0);high=p.max(0)
            for f in facets:
                if np.any(low>f['high']) or np.any(high<f['low']):continue
                poly=[q.copy() for q in p]
                for n,c in f['edges']:
                    clipped=[]
                    for a,b in zip(poly,poly[1:]+poly[:1]):
                        da=float(n@a)-c;db=float(n@b)-c
                        if da>=0:clipped.append(a)
                        if (da<0<db) or (db<0<da):clipped.append(a+(b-a)*(da/(da-db)))
                    poly=clipped
                    if not poly:break
                if not poly:continue
                records.append(dict(initial_inner_triangle=index,inner_vertices=row['ids'],actual_outer_floor_facet=f['index'],finite_expanded_xy_fragment=[q.tolist() for q in poly],z_minimum=f['z']))
                for v in row['ids']:
                    extra.setdefault(v,[]).append((np.array([0.,0.,1.]),f['z']))
        return extra,records
    return prepare
