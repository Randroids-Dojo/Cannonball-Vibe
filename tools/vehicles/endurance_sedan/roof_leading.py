"""Unsaved leading-flange recipe with an explicitly bound original top field.

The caller supplies original25x10 closed-rail vertices/faces immediately
after roof_closing_faces. The pinned native top diagonal is derived from
that recipe indexing, guarded by its exact face inventory and native corners.
No Blender data is read, changed, saved or exported by this geometry function.
"""
from collections import Counter
from fractions import Fraction
import math
import struct

def native(point):
    return tuple(struct.unpack('<f',struct.pack('<f',float(x)))[0] for x in point)

def interpolation(a,b,y):
    t=(Fraction(float(y))-Fraction(float(a[1])))/(Fraction(float(b[1]))-Fraction(float(a[1])))
    return native(tuple(Fraction(float(x))+(Fraction(float(z))-Fraction(float(x)))*t for x,z in zip(a,b)))

STATION_COUNT = 25
SECTION_SIZE = 10
NATIVE_COORDINATE_GUARD_M = 1e-7
# These are guard coordinates of the existing native roof recipe, not new
# shape inputs. The actual input coordinates form every constructed triangle.
TOP_GUARD_ABS = {
    230:(.69936603307724,.04458333179354668,1.398430347442627),
    239:(.5920000076293945,.04458333179354668,1.3999810218811035),
    240:(.6936761736869812,.10000000149011612,1.3954570293426514),
    249:(.5920000076293945,.10000000149011612,1.3960838317871094),
}

def derive_top_reference(original,original_faces):
    points=[tuple(float(v) for v in point) for point in original]
    faces=[tuple(face) for face in original_faces]
    if len(points)!=STATION_COUNT*SECTION_SIZE:
        raise ValueError('Expected untouched original25x10 roof closing rail')
    if any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in points):
        raise ValueError('Nonfinite or malformed original rail point')
    side=-1 if points[0][0]<0 else 1
    if any(side*p[0]<=0 for p in points):
        raise ValueError('Roof rail side is inconsistent')
    for i in range(STATION_COUNT):
        y=native((-1.230+1.330*i/(STATION_COUNT-1),))[0]
        if any(abs(points[i*SECTION_SIZE+j][1]-y)>NATIVE_COORDINATE_GUARD_M for j in range(SECTION_SIZE)):
            raise ValueError('Original25-station Y table changed')
    if any(any(type(i) is not int or not 0<=i<len(points) for i in face) or len(set(face))!=len(face) for face in faces):
        raise ValueError('Malformed original face indices')
    expected=[(10*i+j,10*i+(j+1)%10,10*(i+1)+(j+1)%10,10*(i+1)+j) for i in range(24) for j in range(10)]
    expected += [tuple(reversed(range(10))),tuple(range(240,250))]
    if Counter(tuple(sorted(f)) for f in faces)!=Counter(tuple(sorted(f)) for f in expected):
        raise ValueError('Original closed loft face inventory changed')
    for index,guard in TOP_GUARD_ABS.items():
        expected_point=(side*guard[0],guard[1],guard[2])
        if max(abs(a-b) for a,b in zip(points[index],expected_point))>NATIVE_COORDINATE_GUARD_M:
            raise ValueError('Original upper-seat guard coordinate changed: '+str(index))
    # Last-span upper quad: prior station role9 -> tip role0 is the native
    # accepted diagonal. Explicit triangles avoid Blender choosing its other
    # nonplanar diagonal after the three added longitudinal stations.
    previous=(STATION_COUNT-2)*SECTION_SIZE
    tip=(STATION_COUNT-1)*SECTION_SIZE
    a,b,c,d=previous+9,previous,tip,tip+9
    indices=((a,d,c),(a,c,b)) if side<0 else ((a,b,c),(a,c,d))
    return [[points[i] for i in t] for t in indices],indices

def make(original,original_faces,clipper):
    top_triangles,reference_indices=derive_top_reference(original,original_faces)
    original=[tuple(float(v) for v in p) for p in original]
    if len(original)!=250 or len(top_triangles)!=2:
        raise ValueError('Expected original25x10 rail and two actual top triangles')
    if not all(math.isfinite(v) for p in original for v in p):raise ValueError('Nonfinite rail input')
    if any(len(t)!=3 for t in top_triangles):raise ValueError('Nontriangle top reference')
    old=original[-20:-10];tip=original[-10:]
    low,high=old[0][1],tip[0][1]
    if not (.055<high-low<.056 and abs(high-.1)<1e-7):raise ValueError('Wrong leading interval')
    corners={old[0],old[9],tip[0],tip[9]}
    if {tuple(p) for t in top_triangles for p in t}!=corners:
        raise ValueError('Actual top reference is not exactly the original four corners')
    for triangle in top_triangles:
        a,b,c=triangle
        u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in n))
        if not math.isfinite(length) or length<1e-12 or n[2]/length<.8:
            raise ValueError('Actual top reference has invalid or reversed winding')
    counts=Counter(tuple(sorted((tuple(t[i]),tuple(t[(i+1)%3])))) for t in top_triangles for i in range(3))
    if sorted(counts.values())!=[1,1,1,1,2]:raise ValueError('Top reference topology is not one diagonal quad')
    cuts=[low]+[native((low+(high-low)*f,))[0] for f in (.25,.5,.75)]+[high]
    top=[];top_owners=[]
    for interval,(a,b) in enumerate(zip(cuts,cuts[1:])):
        for owner,triangle in enumerate(top_triangles):
            for t in clipper.patch([triangle],(-2.,2.,a,b)):
                top.append([tuple(p) for p in t]);top_owners.append(owner)
    edge_points={}
    for y in cuts:
        candidates={p for t in top for p in t if p[1]==y}
        if len(candidates)<2:raise ValueError('Missing native top edge station')
        side=-1 if old[0][0]<0 else 1
        outer=max(candidates,key=lambda p:abs(p[0]));inner=min(candidates,key=lambda p:abs(p[0]))
        for role,point in ((0,outer),(9,inner)):
            expected=interpolation(old[role],tip[role],y)
            if max(abs(a-b) for a,b in zip(point,expected))>1e-7:
                raise ValueError('Clipped edge and lower loft disagree')
            edge_points[(y,role)]=point
    vertices=list(original);lookup={p:i for i,p in enumerate(vertices)}
    def index(point):
        point=tuple(point)
        if point not in lookup:
            lookup[point]=len(vertices);vertices.append(point)
        return lookup[point]
    rings=[(list(range(230,240)),list(range(10)))];changes=[]
    for y in cuts[1:]:
        ring=[list(interpolation(a,b,y)) for a,b in zip(old,tip)]
        fraction=(y-low)/(high-low);weight=fraction**3*(10+fraction*(-15+6*fraction))
        side=-1 if ring[0][0]<0 else 1
        ring[0]=list(edge_points[(y,0)]);ring[9]=list(edge_points[(y,9)])
        cross=(.679-abs(ring[2][0]))/(abs(ring[3][0])-abs(ring[2][0]))
        if not 0<cross<1:raise ValueError('Knee is outside original lower shelf')
        knee=native((side*.679,y,ring[2][2]+(ring[3][2]-ring[2][2])*cross))
        for role in (1,2):
            # The terminal cross section lies on the original Y=high edge;
            # the prescribed2mm target uses that actual upper edge.
            x_fraction=(ring[role][0]-ring[0][0])/(ring[9][0]-ring[0][0])
            upper=ring[0][2]+(ring[9][2]-ring[0][2])*x_fraction
            target=upper-.002
            if target<ring[role][2]:raise ValueError('Leading taper would expand downward')
            before=ring[role][2]
            ring[role][2]=native((before+(target-before)*weight,))[0]
            changes.append({'y_m':y,'role':role,'before_z_m':before,'after_z_m':ring[role][2]})
        newring=[tuple(p) for p in ring[:3]]+[knee]+[tuple(p) for p in ring[3:]]
        if y==high:
            # Retain original vertex identities for every unmodified tip role.
            for role in (1,2):
                vertices[240+role]=tuple(ring[role]);lookup[tuple(ring[role])]=240+role
        rings.append(([index(p) for p in newring],[0,1,2,2.5,3,4,5,6,7,8,9]))
    # Keep the original preceding23 spans and original rear cap unchanged.
    def is_last_span(face):
        return all(i>=230 for i in face) and any(i<240 for i in face) and any(i>=240 for i in face)
    def is_tip(face):return all(i>=240 for i in face)
    faces=[tuple(f) for f in original_faces if not is_last_span(f) and not is_tip(f)]
    for (left,lk),(right,rk) in zip(rings,rings[1:]):
        i=j=0
        while lk[i]<9 or rk[j]<9:
            nl=lk[i+1] if i+1<len(lk) else 10
            nr=rk[j+1] if j+1<len(rk) else 10
            a,b=left[i],right[j]
            if nl==nr:
                faces.append((a,left[i+1],right[j+1],b));i+=1;j+=1
            elif nl<nr:
                faces.append((a,left[i+1],b));i+=1
            else:
                faces.append((a,right[j+1],b));j+=1
    faces.append(tuple(rings[-1][0]))
    top_indices=[]
    for t,owner in zip(top,top_owners):
        face=tuple(index(p) for p in t);top_indices.append((len(faces),owner));faces.append(face)
    # Old242/241 positions replaced in place; unused originals are never kept.
    used={i for f in faces for i in f}
    if len(used)!=len(vertices):
        raise ValueError('Unreferenced candidate vertices')
    if any(vertices[i]!=original[i] for i in range(250) if i not in (241,242)):
        raise ValueError('Original vertices outside the two tip-lip roles changed')
    proof={'derived_top_triangle_indices':[list(t) for t in reference_indices],'cuts_y_m':cuts,'knee_abs_x_m':.679,'terminal_depth_m':.002,
           'changed_original_vertex_indices':[241,242],
           'original_unchanged_vertices':248,'changes':changes,
           'top_face_ownership':[{'face':face,'original_triangle':owner} for face,owner in top_indices],
           'actual_top_reference':top_triangles,'top_boundary_points_shared_with_lower_loft':True,
           'original_inner_shelf_at_abs_x_le_0679_retained':True,
           'source_save_or_export':False}
    return vertices,faces,proof
