"""Exact rational actual-cell subtraction; no tiny positive fragment discard."""
from fractions import Fraction as F

def vector(v):return tuple(F(float(x)) for x in v)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def cleanup(poly):
    values=[]
    for p in poly:
        if not values or p!=values[-1]:values.append(p)
    if len(values)>1 and values[0]==values[-1]:values.pop()
    return values
def positive_area(poly):
    return len(poly)>=3 and any(any(x for x in cross(sub(poly[i],poly[0]),sub(poly[i+1],poly[0]))) for i in range(1,len(poly)-1))
def split(poly,n,d):
    if not poly:return [],[]
    distances=[dot(n,p)-d for p in poly]
    if min(distances)>=0:return poly,[]
    if max(distances)<=0:return [],poly
    inside=[];outside=[]
    for i,a in enumerate(poly):
        b=poly[(i+1)%len(poly)];da=distances[i];db=distances[(i+1)%len(poly)]
        if da>=0:inside.append(a)
        if da<=0:outside.append(a)
        if da*db<0:
            t=da/(da-db);p=tuple(a[k]+t*(b[k]-a[k]) for k in range(3));inside.append(p);outside.append(p)
    return cleanup(inside),cleanup(outside)
def partition(poly,planes):
    inside=poly;outside=[]
    for n,d in planes:
        inside,out=split(inside,n,d)
        if positive_area(out):outside.append(out)
        if not positive_area(inside):inside=[];break
    return inside,outside
def tetrahedra(cell):
    vertices=[vector(v) for v in cell['vertices']]
    kernel=tuple(sum(v[i] for v in vertices)/len(vertices) for i in range(3))
    result=[]
    for tri in cell['triangles']:
        actual=[vertices[i] for i in tri]
        n=cross(sub(actual[1],actual[0]),sub(actual[2],actual[0]));d=dot(n,actual[0])
        if not dot(n,kernel)<d:raise ValueError('Exact kernel outside actual terminal face')
        p=[kernel,*actual];planes=[]
        for f,op in [((0,1,2),3),((0,1,3),2),((0,2,3),1),((1,2,3),0)]:
            a,b,c=(p[i] for i in f);n=cross(sub(b,a),sub(c,a));d=dot(n,a)
            if dot(n,p[op])<d:n=tuple(-x for x in n);d=-d
            if not dot(n,p[op])>d:raise ValueError('Degenerate exact tetrahedron')
            planes.append((n,d))
        result.append(planes)
    return result,kernel
def subtract(old,cell):
    planes,kernel=tetrahedra(cell);vertices=[];triangles=[];kept=[];removed=[]
    for ti,triangle in enumerate(old['triangles']):
        todo=[[vector(old['vertices'][i]) for i in triangle]]
        for tetra in planes:
            remaining=[]
            for poly in todo:
                hit,out=partition(poly,tetra);remaining.extend(out)
                if hit:removed.append({'triangle':ti,'polygon':[[float(x) for x in p] for p in hit]})
            todo=remaining
            if not todo:break
        for poly in todo:
            if not positive_area(poly):raise ValueError('Invalid retained exact polygon')
            start=len(vertices);ps=[[float(x) for x in p] for p in poly];vertices.extend(ps)
            kept.append({'original_triangle':ti,'polygon':ps})
            for i in range(1,len(poly)-1):
                if positive_area([poly[0],poly[i],poly[i+1]]):triangles.append([start,start+i,start+i+1])
    return {'name':'OriginalRadiatorOutsideExactActualHoseCell','vertices':vertices,'triangles':triangles},kept,removed,{'kernel_rational':[str(x) for x in kernel],'actual_triangular_tetrahedra':len(planes),'arithmetic':'Exact rational native-coordinate planes and intersections; only exact zero-area fragments omitted.'}
