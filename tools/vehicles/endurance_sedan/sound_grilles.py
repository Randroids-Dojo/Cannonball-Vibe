"""Six finite supported cosmetic grille caps; callable, unsaved native trial.

No report inputs, source loading, saving, exporting, or scene lighting changes.
Only the six named speaker meshes change. Existing materials/parents survive.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from endurance_sedan import geometry as geo
from endurance_sedan.qa import finish_interfaces as finite

NAMES = tuple('LOD0_DoorSpeaker_' + s for s in ('FL', 'FR', 'RL', 'RR')) + (
    'LOD0_RearSpeaker_-1', 'LOD0_RearSpeaker_1')
POCKET_CLEARANCE = .0012


def row(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return {'name': obj.name,
                'vertices': [list(evaluated.matrix_world @ v.co) for v in mesh.vertices],
                'triangles': [list(t.vertices) for t in mesh.loop_triangles],
                'properties': {k: obj[k] for k in obj.keys()},
                'parent': obj.parent.name if obj.parent else None}
    finally:
        evaluated.to_mesh_clear()


def hull(points):
    points = sorted(set(tuple(float(x) for x in p) for p in points))
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1]+upper[:-1]


def mounting_plane(support, axis):
    points = finite.triangles(support)
    normals = np.cross(points[:, 1]-points[:, 0], points[:, 2]-points[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    ids = np.flatnonzero(normals @ axis > 1-1e-12)
    if not len(ids):
        raise ValueError('Missing axis-aligned actual support face')
    constants = points[ids, 0] @ axis
    plane = float(np.max(constants))
    if float(np.max(np.asarray(support['vertices']) @ axis))-plane > 1e-6:
        raise ValueError('Support extends outward beyond its mounting plane')
    return plane


def finish(data, axis, plane):
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='FIXED', ngon_method='EAR_CLIP')
    bm.to_mesh(data)
    bm.free()
    data.update()
    for polygon in data.polygons:
        on_back = all(abs(float(np.asarray(data.vertices[i].co) @ axis)-plane) < 1e-7
                      for i in polygon.vertices)
        polygon.use_smooth = not on_back
    for edge in data.edges:
        edge.use_edge_sharp = all(abs(float(np.asarray(data.vertices[i].co) @ axis)-plane) < 1e-7
                                 for i in edge.vertices)


def build_one(obj):
    old = row(obj)
    door = 'DoorSpeaker' in obj.name
    axes = [1, 2] if door else [0, 1]
    axis = np.array([1. if obj.name.endswith('L') else -1., 0., 0.]) if door else np.array([0., 0., 1.])
    support_name = 'LOD0_DoorCard_' + obj.name[-2:] if door else 'LOD0_ParcelShelf'
    support = row(bpy.data.objects[support_name])
    plane = mounting_plane(support, axis)
    points = np.asarray(old['vertices'])
    outline = np.asarray(hull(points[:, axes]))
    n = 20 if door else 24
    if len(outline) != n or len(old['triangles']) != (360 if door else 336):
        raise ValueError('Expected original six ellipse inventories')
    projected_center = (points[:, axes].min(axis=0)+points[:, axes].max(axis=0))*.5
    depth = points @ axis
    center_depth = (float(depth.min())+float(depth.max()))*.5
    front_depth = float(depth.max())
    half_depth = front_depth-center_depth
    if not depth.min() < plane < center_depth < front_depth:
        raise ValueError('Expected concealed old back below actual support')
    vertices = []
    # Original projected perimeter is retained as ring 1. The front ring and
    # front peak form a low convex cap, not an arbitrarily decimated sphere.
    for scale, d in (((.60 if obj.name[-2:].startswith('R') else .86) if door else .90, plane), (1., center_depth), (.58, center_depth+.8*half_depth)):
        for p in projected_center + scale*(outline-projected_center):
            v = axis*d
            v[axes] = p
            vertices.append(tuple(v))
    for d in (plane, front_depth):
        v = axis*d
        v[axes] = projected_center if d == plane else points[int(np.argmax(depth)), axes]
        vertices.append(tuple(v))
    faces = []
    for i in range(n):
        j = (i+1) % n
        faces += [(3*n, j, i), (i, j, n+j, n+i),
                  (n+i, n+j, 2*n+j, 2*n+i), (2*n+i, 2*n+j, 3*n+1)]
    candidate = geo.mesh(obj.name+'__cap_trial', vertices, faces, obj.data.materials[0], obj.users_collection[0])
    finish(candidate.data, axis, plane)
    relief = None
    if door and obj.name[-2:].startswith('R'):
        pocket = row(bpy.data.objects['LOD0_DoorPocket_'+obj.name[-2:]])
        p = np.asarray(pocket['vertices'])
        contour = np.asarray(hull(p[:, [1, 2]]))
        edges = np.roll(contour, -1, axis=0)-contour
        outward = np.column_stack((edges[:, 1], -edges[:, 0]))
        outward /= np.linalg.norm(outward, axis=1)[:, None]
        constants = np.einsum('ij,ij->i', outward, contour)+POCKET_CLEARANCE
        expanded = [np.linalg.solve(np.stack((outward[i-1], outward[i])),
                                    np.array([constants[i-1], constants[i]])) for i in range(len(contour))]
        low_x, high_x = float(points[:, 0].min()-.02), float(points[:, 0].max()+.02)
        # A complete convex projected pocket envelope with an outward 1.2 mm
        # offset follows its real rounded corners. The cutter spans grille X.
        cutter = geo.prism_x(obj.name+'__pocket_clearance', expanded, low_x, high_x,
                             None, obj.users_collection[0])
        try:
            geo.boolean(candidate, cutter)
        finally:
            bpy.data.objects.remove(cutter, do_unlink=True)
        relief = {'pocket': pocket['name'], 'pocket_bounds_m': [p.min(axis=0).tolist(), p.max(axis=0).tolist()],
                  'original_projected_contour_yz_m': contour.tolist(),
                  'protected_projected_contour_yz_m': [p.tolist() for p in expanded],
                  'outward_planes_yz': [{'normal': n.tolist(), 'constant_m': float(c)} for n, c in zip(outward, constants)],
                  'depth_x_m': [low_x, high_x], 'nominal_clearance_m': POCKET_CLEARANCE}
    finish(candidate.data, axis, plane)
    candidate.data.materials.clear()
    candidate.data.materials.append(obj.data.materials[0])
    for polygon in candidate.data.polygons:
        polygon.material_index = 0
    geo.project_uv(candidate)
    data = candidate.data.copy()
    # Retain every existing semantic transform and parent. Candidate vertices
    # were authored in the actual closed-pose world coordinate system.
    inv = obj.matrix_world.inverted()
    data.transform(inv)
    obj.modifiers.clear()
    obj.data = data
    obj['manufacturing_form'] = 'Supported closed three-ring cosmetic speaker cap'
    bpy.data.objects.remove(candidate, do_unlink=True)
    bpy.context.view_layer.update()
    result = row(obj)
    finite.validate_row(obj.name, result)
    return obj, {'name': obj.name, 'support': support_name, 'outward': axis.tolist(),
                 'projection_axes': axes, 'original_outline_m': outline.tolist(),
                 'original_depth_range_m': [float(depth.min()), float(depth.max())],
                 'mounting_plane_m': plane, 'new_depth_range_m': [float(np.min(np.asarray(result['vertices']) @ axis)),
                                                                  float(np.max(np.asarray(result['vertices']) @ axis))],
                 'profile': {'back_scale': (.60 if obj.name[-2:].startswith('R') else .86) if door else .90, 'inner_front_scale': .58, 'inner_front_rise_fraction': .8},
                 'original_triangles': len(old['triangles']), 'new_triangles': len(result['triangles']),
                 'relief': relief, 'parent': result['parent']}


def build():
    """Return (six changed objects, construction records). Does not save/export."""
    if any(n not in bpy.data.objects for n in NAMES):
        raise ValueError('All six original speakers required')
    result = [build_one(bpy.data.objects[n]) for n in NAMES]
    return [p[0] for p in result], [p[1] for p in result]
