"""Current-input finite verification; source bodies bound in extraction01."""

import heapq,itertools,math
import numpy as np

def open_surface_distance(a,b,geometry):
    """Use existing triangle features/tree, without a closed-solid parity test.

    A cover outer/inner subset is an open patch, so treating it as a solid is
    invalid. This routine is only for those explicitly open surface patches;
    ordinary unrelated-part checks still call the unchanged solid Distances.
    """
    aa=geometry.Mesh(a);bb=geometry.Mesh(b)
    at=[([aa.vertices[i] for i in t],geometry.bounds([aa.vertices[i] for i in t])) for t in aa.triangles]
    bt=[([bb.vertices[i] for i in t],geometry.bounds([bb.vertices[i] for i in t])) for t in bb.triangles]
    ar,br=geometry.tree(at),geometry.tree(bt)
    best,p,q=geometry.triangle_distance(at[0][0],bt[0][0]);witness={'triangles':[0,0],'point_a':list(p),'point_b':list(q)}
    serial=itertools.count();queue=[(geometry.box_distance2(ar[0],br[0]),next(serial),ar,br)];tested=1
    while queue:
        lower,_,left,right=heapq.heappop(queue)
        if lower>=best*best:continue
        if left[1] is not None and right[1] is not None:
            for ai in left[1]:
                for bi in right[1]:
                    if geometry.box_distance2(at[ai][1],bt[bi][1])>=best*best:continue
                    d,p,q=geometry.triangle_distance(at[ai][0],bt[bi][0]);tested+=1
                    if d<best:best=d;witness={'triangles':[ai,bi],'point_a':list(p),'point_b':list(q)}
        else:
            split_left=right[1] is not None or (left[1] is None and sum((left[0][1][i]-left[0][0][i])**2 for i in range(3))>=sum((right[0][1][i]-right[0][0][i])**2 for i in range(3)))
            for x,y in ([(c,right) for c in left[2:]] if split_left else [(left,c) for c in right[2:]]):
                lower=geometry.box_distance2(x[0],y[0])
                if lower<best*best:heapq.heappush(queue,(lower,next(serial),x,y))
    return {'distance_m':best,'witness':witness,'triangle_pairs_evaluated':tested,
            'method':'Unchanged triangle-feature/tree primitives on two open boundary patches; no invalid solid containment predicate.'}

def cells(actual,plan,exact):
    """Exact union of two front webs and the middle back-plate prism."""
    if actual['vertices']!=plan['vertices'] or actual['triangles']!=plan['triangles']:
        raise ValueError('Actual support differs from the finite construction')
    foot=plan['finite_interfaces']['body_land_triangles']
    p=[exact.vector(actual['vertices'][v]) for v in actual['triangles'][foot[0]]]
    n=exact.cross(exact.sub(p[1],p[0]),exact.sub(p[2],p[0]));d=exact.dot(n,p[0])
    if not n[1]:raise ValueError('Invalid finite rear land plane')
    if any(exact.dot(n,exact.vector(actual['vertices'][v]))!=d for i in foot for v in actual['triangles'][i]):
        raise ValueError('Native rear land is not one exact manufactured plane')
    coef=(-n[0]/n[1],-n[2]/n[1],d/n[1])
    front_ids=plan['finite_interfaces']['cover_left']['triangles']+plan['finite_interfaces']['cover_right']['triangles']
    front_ids += [i for i,v in enumerate(plan['triangle_domains']) if v in ('back_plate_inner','back_plate_flange')]
    result=[]
    for i in front_ids:
        p=[exact.vector(actual['vertices'][v]) for v in actual['triangles'][i]]
        signed=sum(a[0]*b[2]-a[2]*b[0] for a,b in zip(p,p[1:]+p[:1]))
        if signed==0:raise ValueError('Cell has no finite X/Z area')
        if signed<0:p.reverse()
        q=[(a[0],coef[0]*a[0]+coef[1]*a[2]+coef[2],a[2]) for a in p]
        normal=exact.cross(exact.sub(p[1],p[0]),exact.sub(p[2],p[0]));constant=exact.dot(normal,p[0])
        planes=[(tuple(-x for x in normal),-constant),((coef[0],exact.F(-1),coef[1]),-coef[2])]
        for a,b in zip(p,p[1:]+p[:1]):
            dx,dz=b[0]-a[0],b[2]-a[2];inward=(-dz,exact.F(0),dx)
            planes.append((inward,exact.dot(inward,a)))
        vertices=p+q;center=tuple(sum(v[j] for v in vertices)/6 for j in range(3))
        if not all(exact.dot(n,center)>c for n,c in planes):raise ValueError('Invalid finite support prism')
        if not all(exact.dot(n,v)>=c for n,c in planes for v in vertices):raise ValueError('Nonconvex finite support cell')
        faces=[p,list(reversed(q))]+[[p[j],p[(j+1)%3],q[(j+1)%3],q[j]] for j in range(3)]
        result.append(dict(front_native_triangle=i,vertices=vertices,planes=planes,faces=faces,center=center))
    return result

def union_boundary(cells,exact):
    polygons=[]
    for i,cell in enumerate(cells):
        for face in cell['faces']:
            parts=[face]
            for j,other in enumerate(cells):
                if i==j:continue
                todo=[]
                for p in parts:
                    _,outside=exact.partition(p,other['planes']);todo.extend(outside)
                parts=todo
                if not parts:break
            polygons.extend(parts)
    return polygons

def as_triangles(polys,exact,retain_zero=False):
    result=[]
    for p in polys:
        if exact.positive_area(p):
            for i in range(1,len(p)-1):
                t=[p[0],p[i],p[i+1]]
                if exact.positive_area(t):result.append([[float(x) for x in q] for q in t])
        elif retain_zero and p:
            q=list(p)+[p[-1]]*max(0,3-len(p))
            result.append([[float(x) for x in v] for v in q[:3]])
    return result

def full_contact(actual,plan,target,cap_ids,exact,fi,coverage,geometry):
    """Every target facet clipped to every support cell, finite caps only."""
    import mathutils
    cell_rows=cells(actual,plan,exact)
    boundary=coverage.row(as_triangles(union_boundary(cell_rows,exact),exact))
    cap=fi.subset(actual,cap_ids,'_finite_caps')
    native_to_cells=coverage.cover(actual,boundary,fi)
    cells_to_native=coverage.cover(boundary,actual,fi)
    target_points=fi.triangles(target);target_mesh=geometry.Mesh(target)
    lower=target_points.min(1);upper=target_points.max(1)
    fragments=[];interiors=[];tests=0;failure=[]
    for ci,cell in enumerate(cell_rows):
        points=np.asarray([[float(x) for x in p] for p in cell['vertices']]);lo=points.min(0);hi=points.max(0)
        center=mathutils.Vector(tuple(map(float,cell['center'])));inside=target_mesh.inside(center)
        clear=inside is not None and all(n%2==0 for n in inside['ray_hit_counts'])
        interiors.append(dict(cell=ci,point=list(center),parity=inside,all_three_even=clear))
        if not clear:failure.append(dict(kind='cell_containment_not_excluded',cell=ci,parity=inside))
        for ti in np.flatnonzero(np.all(lower<=hi,axis=1)&np.all(upper>=lo,axis=1)):
            tests+=1;part=[exact.vector(p) for p in target_points[ti]]
            for n,d in cell['planes']:
                part,_=exact.split(part,n,d)
                if not part:break
            if not part:continue
            diagnostic=coverage.row(as_triangles([part],exact,retain_zero=True))
            proof=coverage.cover(diagnostic,cap,fi)
            item=dict(cell=ci,target_triangle=int(ti),positive_area=exact.positive_area(part),
                      points=[[float(x) for x in p] for p in part],finite_cap_coverage=proof)
            fragments.append(item)
            if proof['status']!='passed':failure.append(item)
    passed=native_to_cells['status']=='passed' and cells_to_native['status']=='passed' and not failure
    return dict(status='passed' if passed else 'failed',cell_count=len(cell_rows),
                complete_native_to_cell_union=native_to_cells,complete_cell_union_to_native=cells_to_native,
                current_target_facet_cell_tests=tests,target_fragments=fragments,interior_witnesses=interiors,
                failures=failure,finite_cap_triangles=cap_ids,guard_m=1e-6,
                method='Exact native-coordinate convex cell union, complete bidirectional surface coverage, all target facets clipped to each cell; only the named actual finite caps may meet. Strict even-parity witnesses in every cell exclude containment. Zero-area contact fragments are retained; no volume-cancellation or whole-pair exception.')
