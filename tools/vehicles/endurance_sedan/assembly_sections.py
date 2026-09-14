"""Reports-only small explicit formed floor section table; no saved source."""
from . import geometry as geo

Y_STATIONS=(-1.650,-1.400,-1.360,-1.354,-1.345,-.845,-.795,.205,.2395,.650,.757,.800)
X_STATIONS=(0,.050,.065,.190,.210,.230,.670,.785)
BASE_PROFILE=((-1.650,.3885),(-1.400,.3885),(-1.345,.296),(-.845,.296),(-.795,.266),(.800,.266))
CROWN_PROFILE=((-1.650,.481),(-1.360,.481),(-1.354,.385),(.205,.385),(.2395,.508),(.800,.508))

def linear(rows,y):
    if y<=rows[0][0]:return rows[0][1]
    for (a,av),(b,bv) in zip(rows,rows[1:]):
        if y<=b:return av+(bv-av)*(y-a)/(b-a)
    return rows[-1][1]

def section(y,inside=False):
    base=linear(BASE_PROFILE,y);crown=linear(CROWN_PROFILE,y)
    wide=max(1-min(1,max(0,(y+1.360)/.006)),min(1,max(0,(y-.205)/.0345)))
    shoulder=max(base,.287)
    upper=shoulder+(crown-shoulder)*wide
    z=[crown,crown,upper,upper,shoulder+(base-shoulder)*wide,base,base,base]
    positive=[]
    for x,height in zip(X_STATIONS,z):
        if x==.785 and y>.650:x=linear(((.650,.785),(.757,.740),(.800,.740)),y)
        if inside:
            if 0<x<=.210:x-=.004
            height-=.004
        positive.append((x,y,height))
    return [(-x,y,z) for x,y,z in reversed(positive[1:])]+positive

def volume(name,collection,material,parent=None,inner=False,low=-.1):
    rings=[]
    for y in Y_STATIONS:
        roof=section(y,inner)
        rings.append(roof+[(roof[-1][0],y,low),(roof[0][0],y,low)])
    n=len(rings[0]);vertices=[v for ring in rings for v in ring]
    faces=[]
    for j in range(len(rings)-1):
        for i in range(n):
            # Explicit planar triangles; no nonplanar ngons.
            a=j*n+i;b=j*n+(i+1)%n;c=(j+1)*n+(i+1)%n;d=(j+1)*n+i
            faces.extend(((a,b,c),(a,c,d)))
    faces.extend((tuple(reversed(range(n))),tuple((len(rings)-1)*n+i for i in range(n))))
    return geo.mesh(name,vertices,faces,material,collection,parent)

def shell(name,collection,material,parent=None):
    outer=[section(y) for y in Y_STATIONS];inner=[section(y,True) for y in Y_STATIONS]
    n=len(outer[0]);ny=len(outer);stride=n*ny
    vertices=[v for rows in (outer,inner) for ring in rows for v in ring];faces=[]
    for j in range(ny-1):
        for i in range(n-1):
            a=j*n+i;b=a+1;c=(j+1)*n+i+1;d=c-1
            faces.extend(((a,b,c),(a,c,d),(stride+a,stride+c,stride+b),(stride+a,stride+d,stride+c)))
    perimeter=list(range(n))+[j*n+n-1 for j in range(1,ny)]+list(range((ny-1)*n+n-2,(ny-1)*n-1,-1))+[j*n for j in range(ny-2,0,-1)]
    for a,b in zip(perimeter,perimeter[1:]+perimeter[:1]):faces.extend(((a,stride+a,stride+b),(a,stride+b,b)))
    return geo.mesh(name,vertices,faces,material,collection,parent)
