"""Meter-scale, editable mesh primitives for the original sedan.

All dimensions are baked into mesh coordinates. Animated transforms belong to
semantic parent empties; these helpers do not apply or destroy rig transforms.
"""

from __future__ import annotations

import math
from collections import Counter

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


def empty(name, collection, parent=None, location=(0, 0, 0), **properties):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    obj.empty_display_size = 0.08
    obj["semantic_role"] = name
    for key, value in properties.items():
        obj[key] = value
    return obj


def mesh(name, vertices, faces, material, collection, parent=None, smooth=False):
    data = bpy.data.meshes.new(name + "Mesh")
    data.from_pydata(vertices, [], faces)
    data.update()
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    if material:
        data.materials.append(material)
    for poly in data.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.parent = parent
    project_uv(obj)
    return obj


def project_uv(obj, meters_per_repeat=0.25):
    """Per-face dominant-axis UVs with explicit physical repeat scale.

    Suitable for isotropic microtexture; upholstery's directional panels get
    dedicated authored UVs. A measured meter always has the same UV frequency.
    """
    data = obj.data
    layer = data.uv_layers.get("SurfaceMeters") or data.uv_layers.new(name="SurfaceMeters")
    for face in data.polygons:
        axis = max(range(3), key=lambda i: abs(face.normal[i]))
        axes = [i for i in range(3) if i != axis]
        for loop_index in face.loop_indices:
            vertex = data.vertices[data.loops[loop_index].vertex_index].co
            layer.data[loop_index].uv = (
                vertex[axes[0]] / meters_per_repeat,
                vertex[axes[1]] / meters_per_repeat,
            )
    obj["uv_meters_per_repeat"] = meters_per_repeat


def bevel(obj, radius=0.003, segments=3, angle=0.45):
    modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
    modifier.width = radius
    modifier.segments = segments
    modifier.limit_method = "ANGLE"
    modifier.angle_limit = angle
    modifier.harden_normals = True
    return modifier


def box(name, center, size, material, collection, parent=None, radius=0.003, rotation=None):
    coordinates = [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                   (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]
    transform = rotation.to_matrix() if rotation is not None else Matrix.Identity(3)
    vertices = [Vector(center) + transform @ Vector(tuple(p[i]*size[i]/2 for i in range(3)))
                for p in coordinates]
    faces = [(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)]
    obj = mesh(name, vertices, faces, material, collection, parent)
    if radius:
        # Staying below half the thinnest dimension prevents the bevel clamp
        # collapsing opposing faces into zero-area slivers on thin housings.
        bevel(obj, min(radius, min(size)*0.40), segments=2)
    return obj


def ellipsoid(name, center, size, material, collection, parent=None, segments=24, rings=12):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1)
    for vertex in bm.verts:
        vertex.co = Vector(center) + Vector(tuple(vertex.co[i] * size[i] / 2 for i in range(3)))
    data = bpy.data.meshes.new(name + "Mesh")
    bm.to_mesh(data)
    bm.free()
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.parent = parent
    data.materials.append(material)
    for polygon in data.polygons:
        polygon.use_smooth = True
    project_uv(obj)
    return obj


def tube(name, points, radius, material, collection, parent=None, sides=8, closed=False, caps=True):
    points = [Vector(p) for p in points]
    vertices, faces = [], [];tangents=[]
    for index, point in enumerate(points):
        previous = points[(index - 1) % len(points)] if closed or index else point
        following = points[(index + 1) % len(points)] if closed or index < len(points)-1 else point
        tangents.append((following-previous).normalized())
    guide=Vector((0,0,1)) if abs(tangents[0].z)<.95 else Vector((0,1,0))
    normals=[tangents[0].cross(guide).normalized()]
    # Parallel transport avoids a 90-degree cross-section jump wherever a
    # steering rim or seal passes the old arbitrary vertical-guide threshold.
    for previous,tangent in zip(tangents,tangents[1:]):
        normal=previous.rotation_difference(tangent)@normals[-1]
        normals.append((normal-tangent*normal.dot(tangent)).normalized())
    if closed:
        end=tangents[-1].rotation_difference(tangents[0])@normals[-1]
        correction=math.atan2(tangents[0].dot(end.cross(normals[0])),end.dot(normals[0]))
        normals=[Quaternion(tangent,correction*i/len(points))@normal for i,(tangent,normal) in enumerate(zip(tangents,normals))]
    for index,(point,tangent,normal) in enumerate(zip(points,tangents,normals)):
        binormal = tangent.cross(normal).normalized()
        local_radius = radius[index] if isinstance(radius, (tuple, list)) else radius
        for side in range(sides):
            angle = 2 * math.pi * side / sides
            vertices.append(point + local_radius*(math.cos(angle)*normal + math.sin(angle)*binormal))
    for index in range(len(points) if closed else len(points)-1):
        following = (index+1) % len(points)
        for side in range(sides):
            nxt = (side+1) % sides
            faces.append((index*sides+side,index*sides+nxt,following*sides+nxt,following*sides+side))
    if caps and not closed:
        faces.extend([tuple(reversed(range(sides))), tuple((len(points)-1)*sides+i for i in range(sides))])
    return mesh(name, vertices, faces, material, collection, parent, smooth=True)


def ring_x(name, profile, center, material, collection, parent=None, segments=64):
    """Revolve a closed (axial offset, radius) profile around the wheel X axis."""
    vertices, faces = [], []
    for axial, radius in profile:
        for j in range(segments):
            angle = 2*math.pi*j/segments
            vertices.append((center[0]+axial,center[1]+radius*math.sin(angle),center[2]+radius*math.cos(angle)))
    for i in range(len(profile)):
        next_i = (i+1) % len(profile)
        for j in range(segments):
            next_j = (j+1) % segments
            faces.append((i*segments+j,next_i*segments+j,next_i*segments+next_j,i*segments+next_j))
    return mesh(name, vertices, faces, material, collection, parent, smooth=True)


def hollow_tube(name, start, end, radius, wall, material, collection, parent=None, segments=24):
    direction = Vector(end) - Vector(start)
    length = direction.length
    obj = ring_x(name, [(0, radius), (length, radius), (length, radius - wall), (0, radius - wall)], (0, 0, 0), material, collection, parent, segments)
    rotation = Vector((1, 0, 0)).rotation_difference(direction.normalized())
    for vertex in obj.data.vertices:
        vertex.co = rotation @ vertex.co + Vector(start)
    obj.data.update()
    project_uv(obj)
    return obj


def prism_x(name, outline_yz, low_x, high_x, material, collection, parent=None):
    n = len(outline_yz)
    vertices = [(x,y,z) for x in (low_x,high_x) for y,z in outline_yz]
    faces = [tuple(reversed(range(n))), tuple(range(n,2*n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return mesh(name, vertices, faces, material, collection, parent)


def boolean(obj, cutter, operation="DIFFERENCE"):
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("Assembly aperture", "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    project_uv(obj)


def parent_at_pivot(obj, pivot):
    """Keep authored world position when assigning an animation pivot."""
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = pivot
    obj.matrix_world = world


def evaluated_counts(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = evaluated.to_mesh()
    data.calc_loop_triangles()
    # Edge-relative double arithmetic avoids absolute-coordinate cancellation
    # in BMesh.calc_area on valid micrometer-scale bevel triangles.
    polygon_areas=[0.0]*len(data.polygons)
    triangle_areas=[]
    for triangle in data.loop_triangles:
        a,b,c=([float(v) for v in data.vertices[index].co] for index in triangle.vertices)
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        area=math.sqrt(sum(value*value for value in cross))*.5
        triangle_areas.append(area);polygon_areas[triangle.polygon_index]+=area
    bm = bmesh.new()
    bm.from_mesh(data)
    triangle_keys=Counter(tuple(sorted(t.vertices)) for t in data.loop_triangles)
    triangle_edges=Counter(tuple(sorted((t.vertices[i],t.vertices[(i+1)%3]))) for t in data.loop_triangles for i in range(3))
    native_normals=[tuple(float(c) for c in value.vector) for value in data.corner_normals]
    lengths=[math.hypot(*value) for value in native_normals if all(math.isfinite(c) for c in value)]
    result = {"vertices":len(data.vertices),"triangles":len(data.loop_triangles),
              "duplicate_faces":sum(count-1 for count in Counter(tuple(sorted(p.vertices)) for p in data.polygons).values()),
              "nonmanifold_edges":sum(not edge.is_manifold for edge in bm.edges),
              "degenerate_faces":sum(area <= 1e-12 for area in polygon_areas),
              "degenerate_triangles":sum(area <= 1e-12 for area in triangle_areas),
              "triangulated_duplicate_faces":sum(count-1 for count in triangle_keys.values()),
              "triangulated_nonmanifold_edges":sum(count!=2 for count in triangle_edges.values()),
              "uv_layers":len(data.uv_layers),
              "normal_corners":len(native_normals),
              "nonfinite_corner_normals":len(native_normals)-len(lengths),
              "zero_corner_normals":sum(value<=1e-12 for value in lengths),
              "nonunit_corner_normals":sum(abs(value-1)>1e-6 for value in lengths),
              "normal_length_min":min(lengths,default=None),
              "normal_length_max":max(lengths,default=None)}
    bm.free()
    evaluated.to_mesh_clear()
    return result


def repair_triangulation(obj):
    """Bake only defective evaluated assemblies and collapse numerical slivers.

    Construction inputs stay in Python; the saved assembly remains an ordinary
    editable mesh. Do not delete degenerate faces and leave holes behind.
    """
    before = evaluated_counts(obj)
    if not before["degenerate_triangles"]:
        return
    graph = bpy.context.evaluated_depsgraph_get()
    data = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), preserve_all_data_layers=True, depsgraph=graph)
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
    for _ in range(3):
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.000001)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.000001)
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    obj.modifiers.clear()
    obj.data = data
    after = evaluated_counts(obj)
    obj["triangulation_repair"] = "Submicrometer sliver collapse after evaluated modifier stack"
    if after["nonmanifold_edges"] or after["degenerate_triangles"]:
        audit=bmesh.new();audit.from_mesh(obj.data)
        boundary=[{'faces':len(e.link_faces),'length':e.calc_length(),'vertices':[list(v.co) for v in e.verts]} for e in audit.edges if not e.is_manifold]
        audit.free()
        raise ValueError(f"Could not repair triangulation of {obj.name}: before={before}, after={after}, boundary={boundary[:16]}")
