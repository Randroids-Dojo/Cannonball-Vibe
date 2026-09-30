"""Pure current-construction normal target transport. No IO or mesh writes.

Keep this stream separate from decoded native normals. Existing native
encoders still perform and verify each actual write under .025 degrees.
"""
import math

UNIT=1e-6


def values(normals,count):
    result=[tuple(n) for n in normals]
    if type(count) is not int or count<=0 or len(result)!=count:
        raise ValueError('Incomplete ideal normal target domain')
    if any(len(n)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in n)
           or abs(math.hypot(*n)-1)>UNIT for n in result):
        raise ValueError('Invalid ideal unit normal target')
    return result


def seed(before,witness,arch_targets,current):
    """Original shoulder targets, then explicitly authored radial arch targets.

    before/current are actual in-process native states, with the same physical
    layout. The independent checker separately verifies the native transition.
    arch_targets must be freshly derived from actual unchanged current geometry.
    """
    for key in ('object','coordinate_frame','physical','material_response','loops','faces','triangles'):
        if before[key]!=current[key]:raise ValueError('Target seed physical/layout bridge changed: '+key)
    result=values(before['normals'],len(before['loops']));used=set()
    for item in witness['details']+witness['propagated_boundary_fans']:
        li=item['loop']
        if type(li) is not int or not 0<=li<len(result) or li in used:raise ValueError('Invalid/duplicate original shoulder target')
        result[li]=values([item['target']],1)[0];used.add(li)
    for li,target in arch_targets.items():
        if type(li) is not int or not 0<=li<len(result):raise ValueError('Invalid current arch target')
        result[li]=values([target],1)[0]
    return result


def explicit(normals,triangle_loops,source_corner_count):
    normals=values(normals,source_corner_count)
    mapping=[]
    for loops in triangle_loops:
        if len(loops)!=3 or len(set(loops))!=3 or any(type(i) is not int or not 0<=i<source_corner_count for i in loops):
            raise ValueError('Invalid original triangle corner mapping')
        mapping.extend(loops)
    if set(mapping)!=set(range(source_corner_count)):raise ValueError('Incomplete original triangle corner coverage')
    return [normals[i] for i in mapping]


def bend(normals,loop_vertices,points,field):
    """Ground-frame inverse transpose of the existing front bend Jacobian."""
    from mathutils import Vector
    normals=values(normals,len(loop_vertices));samples=[field(Vector(p)) for p in points];out=[]
    for vi,normal in zip(loop_vertices,normals):
        if type(vi) is not int or not 0<=vi<len(samples):raise ValueError('Invalid bend target vertex')
        _,(a,b,c,d,e)=samples[vi]
        if not all(math.isfinite(v) for v in (a,b,c,d,e)) or min(a,d)<=.2:raise ValueError('Invalid monotone bend Jacobian')
        n=Vector(normal);nx=n.x/a;ny=(n.y-b*nx)/d
        out.append(tuple(Vector((nx,ny,n.z-c*nx-e*ny)).normalized()))
    return values(out,len(normals))


def optical(normals,loop_vertices,points,field,*,role='body'):
    from mathutils import Vector,Matrix
    normals=values(normals,len(loop_vertices));points=[Vector(p) for p in points]
    if not points:raise ValueError('Missing actual optical points')
    cx=(min(p.x for p in points)+max(p.x for p in points))/2
    samples=[field(p,role,cx) for p in points];out=[];identity=Matrix.Identity(3)
    for vi,normal in zip(loop_vertices,normals):
        if type(vi) is not int or not 0<=vi<len(samples):raise ValueError('Invalid optical target vertex')
        jacobian=samples[vi][1]
        if not math.isfinite(jacobian.determinant()) or jacobian.determinant()<.2:raise ValueError('Invalid optical Jacobian')
        out.append(tuple((identity@jacobian.inverted().transposed()@identity@Vector(normal)).normalized()))
    return values(out,len(normals))


def planar(normals,face_loops,components):
    """Match the existing retained-face prefix then authored planar groups."""
    count=sum(len(face) for face in face_loops);normals=values(normals,count)
    if sorted(i for face in face_loops for i in face)!=list(range(count)):
        raise ValueError('Invalid original planar face/corner partition')
    selected=[i for c in components for i in c['old_faces']]
    if len(set(selected))!=len(selected) or any(type(i) is not int or not 0<=i<len(face_loops) for i in selected):
        raise ValueError('Invalid selected planar domain')
    out=[normals[li] for fi,face in enumerate(face_loops) if fi not in set(selected) for li in face]
    for c in components:
        sign=c['normal_z']
        if type(sign) is not int or sign not in (-1,1):raise ValueError('Invalid planar target orientation')
        out.extend([(0.,0.,float(sign)) for _ in range(3*len(c['new_triangles']))])
    return values(out,len(out))


def interpolate(point,reference_points,reference_normals,*,exact=False,project=False):
    """Called only after complete finite owner attribution has passed."""
    from mathutils import Vector,geometry
    ps=[Vector(p) for p in reference_points];ns=[Vector(n) for n in values(reference_normals,3)];p=Vector(point)
    if len(ps)!=3:raise ValueError('Invalid retained surface reference')
    if exact:
        matches=[i for i,q in enumerate(ps) if tuple(p)==tuple(q)]
        if len(matches)!=1:raise ValueError('Ambiguous exact retained original corner')
        return tuple(ns[matches[0]])
    if project:p=geometry.closest_point_on_tri(p,*ps)
    result=geometry.barycentric_transform(p,*ps,*ns)
    if not math.isfinite(result.length_squared) or result.length_squared<=1e-12:
        raise ValueError('Vanishing transported surface field')
    return values([tuple(result.normalized())],1)[0]


class Stream:
    """Validated target-array storage; accepting targets never reads native N."""
    def __init__(self,normals):self.current=values(normals,len(normals))
    def input(self,corner_count):return list(values(self.current,corner_count))
    def accept(self,normals,corner_count):
        self.current=values(normals,corner_count)
        return list(self.current)


REAR_PLANE_Y = 2.2300000190734863


def rear_planar(normals, face_loops, components):
    """Retained prefix then newly triangulated negative-Y closure components.

    Components must be freshly constructed from the actual indexed boundary.
    Their geometry and complete coverage are independently verified by QA.
    The mapping vocabulary is old_faces/new_triangles/normal_y.
    """
    count=sum(len(face) for face in face_loops);normals=values(normals,count)
    if sorted(i for face in face_loops for i in face)!=list(range(count)):
        raise ValueError('Invalid original rear-planar corner partition')
    if not components:raise ValueError('Missing authored rear-planar domain')
    selected=[i for c in components for i in c['old_faces']]
    if (not selected or len(set(selected))!=len(selected)
            or any(type(i) is not int or not 0<=i<len(face_loops) for i in selected)):
        raise ValueError('Invalid selected rear-planar domain')
    owned=set(selected)
    out=[normals[li] for fi,face in enumerate(face_loops) if fi not in owned for li in face]
    for component in components:
        if type(component['normal_y']) is not int or component['normal_y']!=-1:
            raise ValueError('Invalid authored rear-planar orientation')
        if not component['new_triangles'] or any(len(t)!=3 for t in component['new_triangles']):
            raise ValueError('Incomplete new rear-planar triangle inventory')
        out.extend([(0.,-1.,0.) for _ in range(3*len(component['new_triangles']))])
    return values(out,len(out))


def rear_closure(normals, points, triangles, face_loops, material_indices,
                 material_names, charts):
    """Apply the declared ALL-paint rear-closure target/chart override.

    Pure target construction only. Original-to-final complete surface ownership
    and the original/native normal cone remain independent caller obligations.
    Every input is the actual post-cut native inventory, not a historical row.
    No earlier decoded normal is used as the authored target on this domain.
    """
    count=sum(len(ls) for ls in face_loops)
    out=values(normals,count)
    if len(triangles)!=len(face_loops) or len(material_indices)!=len(triangles):
        raise ValueError('Incomplete actual rear-closure face inventory')
    if sorted(i for ls in face_loops for i in ls)!=list(range(count)):
        raise ValueError('Invalid actual rear-closure corner partition')
    if any(len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in points):
        raise ValueError('Invalid actual rear-closure point')
    if material_names.count('Material_Paint')!=1:
        raise ValueError('Missing or ambiguous actual paint slot')
    if set(charts)!={'SurfaceMeters'} or len(charts['SurfaceMeters'])!=count:
        raise ValueError('Unsupported or incomplete rear-closure UV channels')
    uv=[tuple(v) for v in charts['SurfaceMeters']]
    if any(len(v)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in v) for v in uv):
        raise ValueError('Invalid original UV inventory')
    paint=material_names.index('Material_Paint');selected=[]
    for fi,(tri,ls,mat) in enumerate(zip(triangles,face_loops,material_indices)):
        if (len(tri)!=3 or len(ls)!=3 or len(set(tri))!=3
                or any(type(i) is not int or not 0<=i<len(points) for i in tri)
                or any(type(i) is not int or not 0<=i<count for i in ls)
                or type(mat) is not int or not 0<=mat<len(material_names)):
            raise ValueError('Invalid actual triangular face domain')
        ps=[points[i] for i in tri]
        if mat!=paint or not all(p[1]==REAR_PLANE_Y for p in ps):continue
        a=[ps[1][k]-ps[0][k] for k in range(3)]
        b=[ps[2][k]-ps[0][k] for k in range(3)]
        ny=a[2]*b[0]-a[0]*b[2]
        if not math.isfinite(ny) or ny>=0:
            raise ValueError('Reversed or collapsed declared rear closure')
        for li,p in zip(ls,ps):
            out[li]=(0.,-1.,0.);uv[li]=(p[0]/.25,p[2]/.25)
        selected.append(fi)
    if not selected:raise ValueError('Declared actual paint rear closure missing')
    return {'normals':values(out,count),'charts':{'SurfaceMeters':uv},
            'faces':selected,'plane_y_m':REAR_PLANE_Y,
            'normal_target':(0.,-1.,0.),'UV_formula':'(X/0.25m,Z/0.25m)',
            'old_field_equivalence':False,'complete_surface_ownership_checked':False}
