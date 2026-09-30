"""Current-input finite verification; source bodies bound in extraction01."""



def point_triangle_squared(p,t,ex):
    a,b,c=t;n=ex.cross(ex.sub(b,a),ex.sub(c,a));nn=ex.dot(n,n)
    if not nn:raise ValueError('Degenerate exact target triangle')
    d=ex.dot(n,ex.sub(p,a));q=tuple(p[k]-d*n[k]/nn for k in range(3))
    if all(ex.dot(ex.cross(ex.sub(y,x),ex.sub(q,x)),n)>=0 for x,y in zip(t,t[1:]+t[:1])):return d*d/nn
    candidates=[]
    for x,y in zip(t,t[1:]+t[:1]):
        e=ex.sub(y,x);u=max(ex.F(0),min(ex.F(1),ex.dot(ex.sub(p,x),e)/ex.dot(e,e)));q=tuple(x[k]+u*e[k] for k in range(3));v=ex.sub(p,q);candidates.append(ex.dot(v,v))
    return min(candidates)

def cover(polygons,targets,ex,maximum=2e-7):
    limit=ex.F(str(maximum))**2;records=[];failed=[]
    if not targets:return dict(status='failed',reason='No finite target triangles',records=[],uncovered=polygons)
    for index,poly in enumerate(polygons):
        if not ex.positive_area(poly):raise ValueError('Degenerate source polygon')
        n=ex.cross(ex.sub(poly[1],poly[0]),ex.sub(poly[2],poly[0]));nn=ex.dot(n,n)
        # Collinear initial triples can occur on clipped boundary polygons.
        if not nn:
            n=next(ex.cross(ex.sub(poly[i],poly[0]),ex.sub(poly[i+1],poly[0])) for i in range(1,len(poly)-1) if any(ex.cross(ex.sub(poly[i],poly[0]),ex.sub(poly[i+1],poly[0]))));nn=ex.dot(n,n)
        direct=[max(point_triangle_squared(p,t,ex) for p in poly) for t in targets]
        if min(direct)<=limit:
            j=min(range(len(direct)),key=direct.__getitem__);records.append(dict(polygon=index,cells=1,target=j,bound_squared=str(direct[j])));continue
        lines={}
        for tri in targets:
            q=[]
            for p in tri:
                d=ex.dot(n,ex.sub(p,poly[0]));q.append(tuple(p[k]-d*n[k]/nn for k in range(3)))
            for a,b in zip(q,q[1:]+q[:1]):
                m=ex.cross(n,ex.sub(b,a))
                if not any(m):continue
                d=ex.dot(m,a);pivot=next(x for x in m if x);key=tuple(x/pivot for x in (*m,d));lines[key]=(m,d)
        cells=[poly]
        for m,d in lines.values():
            new=[]
            for cell in cells:
                a,b=ex.split(cell,m,d)
                if ex.positive_area(a):new.append(a)
                if ex.positive_area(b):new.append(b)
            cells=new
            if len(cells)>4096:raise ValueError('Finite owner arrangement exceeds4096 cells')
        rows=[]
        for ci,cell in enumerate(cells):
            distances=[max(point_triangle_squared(p,t,ex) for p in cell) for t in targets];j=min(range(len(distances)),key=distances.__getitem__);distance=distances[j]
            item=dict(cell=ci,target=j,bound_squared=str(distance),points=[[str(x) for x in p] for p in cell]);rows.append(item)
            if distance>limit:failed.append(dict(polygon=index,**item))
        records.append(dict(polygon=index,cells=len(cells),complete_cells=rows))
    return dict(status='passed' if not failed else 'failed',records=records,uncovered=failed,guard_m=maximum,argument='Exact supporting-line arrangement partitions every positive source polygon completely. Squared point-to-finite-triangle distances are rational; convexity bounds every whole closed cell by its vertex maximum. Closure includes cell edges. No witness or area tolerance discards a gap.')
