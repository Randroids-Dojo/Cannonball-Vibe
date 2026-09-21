"""Formed structural A-pillar upstands with a defined upper butt joint."""

import itertools
import json

import bmesh
import bpy
import numpy as np
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree

from . import geometry as geo
from .floor_panels import coat_cut_faces, freeze, remove


def hull(name, points, collection):
    edit = bmesh.new()
    vertices = [edit.verts.new(tuple(point)) for point in points]
    bmesh.ops.convex_hull(edit, input=vertices, use_existing_faces=False)
    bmesh.ops.recalc_face_normals(edit, faces=list(edit.faces))
    mesh = bpy.data.meshes.new(name)
    edit.to_mesh(mesh)
    edit.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def offset_hull(points, clearance, collection):
    """Offset each supporting plane of the actual lower ribbon envelope."""
    seed = hull('APillarFootClearanceSeed', points, collection)
    center = sum((v.co for v in seed.data.vertices), Vector()) / len(seed.data.vertices)
    planes, keys = [], set()
    for polygon in seed.data.polygons:
        normal = polygon.normal.copy()
        point = seed.data.vertices[polygon.vertices[0]].co
        if normal.dot(point-center) < 0:
            normal = -normal
        distance = max(normal.dot(Vector(p)) for p in points)
        key = tuple(round(value, 6) for value in (*normal, distance))
        if key not in keys:
            keys.add(key)
            planes.append((*normal, distance+clearance))
    array = np.array(planes, dtype=float)
    coefficients, distances = array[:, :3], array[:, 3]
    vertices, seen = [], set()
    for combination in itertools.combinations(range(len(planes)), 3):
        matrix = coefficients[list(combination)]
        if abs(np.linalg.det(matrix)) < 1e-9:
            continue
        point = np.linalg.solve(matrix, distances[list(combination)])
        if np.max(coefficients @ point-distances) > 1e-7:
            continue
        key = tuple(round(value, 7) for value in point)
        if key not in seen:
            seen.add(key)
            vertices.append(point)
    remove(seed)
    if len(vertices) < 4:
        raise RuntimeError('A-pillar offset envelope is empty')
    return hull('APillarFenderRelief', vertices, collection), planes


def normal_reference(obj):
    obj.data.calc_loop_triangles()
    vertices = [v.co.copy() for v in obj.data.vertices]
    triangles = [tuple(t.vertices) for t in obj.data.loop_triangles]
    normals = [[obj.data.corner_normals[i].vector.copy() for i in t.loops]
               for t in obj.data.loop_triangles]
    return BVHTree.FromPolygons(vertices, triangles, all_triangles=True), vertices, triangles, normals


def preserve_surface_normals(obj, references):
    """Retain the unchanged outer sheet's shading across its new butt split."""
    updated, distances = [], []
    for face in obj.data.polygons:
        for loop in face.loop_indices:
            point = obj.data.vertices[obj.data.loops[loop].vertex_index].co
            best = None
            for tree, vertices, triangles, normals in references:
                hit, normal, index, distance = tree.find_nearest(point)
                if distance > 2e-6 or face.normal.dot(normal) < .8:
                    continue
                value = geometry.barycentric_transform(
                    hit, *[vertices[k] for k in triangles[index]], *normals[index]).normalized()
                score = (distance, -face.normal.dot(normal))
                if best is None or score < best[0]:
                    best = score, value
            if best is None:
                updated.append(obj.data.corner_normals[loop].vector.copy())
            else:
                updated.append(best[1])
                distances.append(best[0][0])
    obj.data.normals_split_custom_set(updated)
    obj.data.update()
    obj['a_joint_normal_preservation'] = json.dumps(
        {'loops': len(distances), 'maximum_unchanged_surface_distance_m': max(distances, default=0),
         'boundary': 'Original exterior interpolated corner normals only; new planar butt caps keep their own face normals'},
        separators=(',', ':'))


def build(body, collection):
    freeze(body)
    coating = body.data.materials[0]
    originals = {body.name: normal_reference(body)}
    for side in ('L', 'R'):
        for prefix in ('LOD0_PillarA_', 'LOD0_FrontFender_'):
            obj = bpy.data.objects[prefix+side]
            freeze(obj)
            originals[obj.name] = normal_reference(obj)
    clip = hull('APillarStructuralFootSplit',
                [(x, y, z) for x in (-2, 2) for y in (-3, 3) for z in (-1, 1.05)], collection)
    for side in ('L', 'R'):
        pillar = bpy.data.objects['LOD0_PillarA_'+side]
        fender = bpy.data.objects['LOD0_FrontFender_'+side]
        envelope = [v.co.copy() for v in pillar.data.vertices if v.co.z < 1.14]
        foot = pillar.copy()
        foot.data = pillar.data.copy()
        foot.name = 'APillarStructuralFoot_'+side
        collection.objects.link(foot)
        geo.boolean(pillar, clip)
        geo.boolean(foot, clip, 'INTERSECT')
        geo.boolean(body, foot, 'UNION')
        remove(foot)
        relief, planes = offset_hull(envelope, .0035, collection)
        geo.boolean(fender, relief)
        remove(relief)
        pillar['assembly_boundary'] = 'Closed upper ribbon meets joined structural upstand on exact Z1.05m planar butt; roof butt remains separately defined'
        pillar['structural_joint_plane_z_m'] = 1.05
        fender['a_pillar_relief_nominal_m'] = .0035
        fender['a_pillar_relief_support_planes'] = json.dumps(planes, separators=(',', ':'))
    body['a_pillar_upstands'] = 'Lower original ribbon feet are unioned into this structural mesh below Z1.05m; no lower-fender overlap waiver'
    remove(clip)
    coat_cut_faces(body, coating)
    preserve_surface_normals(body, list(originals.values()))
    for side in ('L', 'R'):
        for prefix in ('LOD0_PillarA_', 'LOD0_FrontFender_'):
            obj = bpy.data.objects[prefix+side]
            coat_cut_faces(obj, coating)
            preserve_surface_normals(obj, [originals[obj.name]])
