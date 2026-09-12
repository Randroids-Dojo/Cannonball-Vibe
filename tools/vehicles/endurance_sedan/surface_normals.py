"""Preserve a formed surface's normal field by complete face ownership."""
import math

from mathutils import Vector, geometry


def _sub(a,b):return tuple(x-y for x,y in zip(a,b))
def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _unit(v):
    length=math.sqrt(_dot(v,v))
    if length==0:raise ValueError('Degenerate surface-normal reference')
    return tuple(x/length for x in v)


def _clip(poly,normal,offset,inside):
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da,db=_dot(a,normal)-offset,_dot(b,normal)-offset
        ia=da>=0 if inside else da<=0
        ib=db>=0 if inside else db<=0
        if ia:result.append(a)
        if ia!=ib:
            t=da/(da-db)
            result.append(tuple(x+(y-x)*t for x,y in zip(a,b)))
    return list(dict.fromkeys(result))


def _subtract(poly,planes):
    remainder=[];inside=poly
    for normal,offset in planes:
        if not inside:break
        outside=_clip(inside,normal,offset,False)
        if outside:remainder.append(outside)
        inside=_clip(inside,normal,offset,True)
    return remainder


def _patch(reference):
    _,vertices,triangles,normals=reference
    rows=[]
    for index,face in enumerate(triangles):
        points=[tuple(vertices[i]) for i in face]
        n=_unit(_cross(_sub(points[1],points[0]),_sub(points[2],points[0])))
        planes=[]
        for a,b in zip(points,points[1:]+points[:1]):
            inward=_unit(_cross(n,_sub(b,a)))
            planes.append((inward,_dot(inward,a)-1e-6))
        rows.append((points,n,planes,normals[index]))
    return rows


def _covers(triangle,patch):
    normal=_unit(_cross(_sub(triangle[1],triangle[0]),_sub(triangle[2],triangle[0])))
    remaining=[triangle]
    for points,n,planes,_ in patch:
        if _dot(normal,n)<.99985:continue
        if max(abs(_dot(_sub(point,points[0]),n)) for point in triangle)>1e-6:continue
        remaining=[piece for polygon in remaining for piece in _subtract(polygon,planes)]
        if not remaining:return True
    return False


def restore_owned(obj,references):
    """Override only faces fully covered by one declared original surface.

    Coverage subtracts every aligned reference triangle's expanded footprint
    from every actual face triangle. The1um projection guard accommodates
    native Boolean encoding; no small-area remainder is discarded. A face
    receives one owning patch before any of its corners are interpolated.
    """
    mesh=obj.data;mesh.calc_loop_triangles()
    patches=[_patch(reference) for reference in references]
    triangles={}
    for triangle in mesh.loop_triangles:
        triangles.setdefault(triangle.polygon_index,[]).append(
            [tuple(mesh.vertices[i].co) for i in triangle.vertices])
    updated=[normal.vector.copy() for normal in mesh.corner_normals]
    faces=0;loops=0;maximum=0.
    for face in mesh.polygons:
        owner=next((patch for patch in patches if all(_covers(triangle,patch)
                    for triangle in triangles[face.index])),None)
        if owner is None:continue
        for index in face.loop_indices:
            point=mesh.vertices[mesh.loops[index].vertex_index].co
            candidates=[]
            for points,normal,_,normals in owner:
                if face.normal.dot(Vector(normal))<.8:continue
                vectors=[Vector(p) for p in points]
                hit=geometry.closest_point_on_tri(point,*vectors)
                distance=(hit-point).length
                if distance>2e-6:continue
                value=geometry.barycentric_transform(hit,*vectors,*normals)
                if value.length<.5:raise ValueError('Invalid owned surface corner field')
                candidates.append((distance,value.normalized()))
            if not candidates:raise ValueError('Owned face corner lacks its surface reference')
            distance,value=min(candidates,key=lambda item:item[0])
            updated[index]=value;loops+=1;maximum=max(maximum,distance)
        faces+=1
    mesh.normals_split_custom_set(updated);mesh.update()
    return {'owned_faces':faces,'owned_loops':loops,'maximum_reference_distance_m':maximum,
            'complete_face_projection_guard_m':1e-6}


def mark_fold_edges(obj,angle_degrees=35):
    """Keep physical folded edges sharp while smoothing longitudinal sections."""
    import bmesh
    edit=bmesh.new();edit.from_mesh(obj.data)
    for edge in edit.edges:
        if len(edge.link_faces)==2 and edge.calc_face_angle()>math.radians(angle_degrees):
            edge.smooth=False
    edit.to_mesh(obj.data);edit.free();obj.data.update()
