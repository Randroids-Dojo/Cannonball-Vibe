"""Real shoulder incisions with the undisturbed rubber normal field retained."""

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import geometry as geo


def cut_shoulders(tire, construction_guides):
    """Replace56 temporary profile guides with closed Boolean recesses."""
    tire.data.calc_loop_triangles()
    triangles = list(tire.data.loop_triangles)
    original_tree = BVHTree.FromPolygons(
        [v.co.copy() for v in tire.data.vertices],
        [tuple(triangle.vertices) for triangle in triangles], all_triangles=True)
    original = [([tire.data.vertices[i].co.copy() for i in triangle.vertices],
                 [tire.data.corner_normals[i].vector.copy() for i in triangle.loops])
                for triangle in triangles]
    vertices, faces = [], []
    if len(construction_guides) != 56:
        raise ValueError('A complete tire requires56 shoulder construction guides')
    for guide in construction_guides:
        points = []
        for index in range(0, len(guide.data.vertices), 4):
            center = sum((v.co for v in guide.data.vertices[index:index+4]), Vector()) / 4
            radial = Vector((0, center.y, center.z)).normalized()
            points.append(center - radial*.0004)
        cutter = geo.tube('ShoulderConstructionCutter', [points[i] for i in (0, 1, 3)],
                          .0012, None, tire.users_collection[0], tire.parent, sides=4)
        start = len(vertices)
        vertices.extend(v.co.copy() for v in cutter.data.vertices)
        faces.extend(tuple(start+i for i in face.vertices) for face in cutter.data.polygons)
        bpy.data.objects.remove(cutter, do_unlink=True)
    combined = geo.mesh('CombinedShoulderConstructionCutters', vertices, faces,
                        None, tire.users_collection[0], tire.parent)
    geo.boolean(tire, combined)
    bpy.data.objects.remove(combined, do_unlink=True)
    for guide in construction_guides:
        bpy.data.objects.remove(guide, do_unlink=True)
    geo.repair_triangulation(tire)

    # Boolean valence changes must not make dents in surviving smooth rubber.
    # Only original-surface faces get interpolated normals; recess walls keep
    # their own geometric normals and therefore their actual sharp boundary.
    corner_normals = [None] * len(tire.data.loops)
    for polygon in tire.data.polygons:
        matches = [original_tree.find_nearest(tire.data.vertices[tire.data.loops[i].vertex_index].co)
                   for i in polygon.loop_indices]
        on_surface = all(hit[0] is not None and hit[3] <= .0000005 for hit in matches)
        polygon.use_smooth = True
        for index, match in zip(polygon.loop_indices, matches):
            if not on_surface:
                corner_normals[index] = polygon.normal.copy()
                continue
            point, _, triangle_index, _ = match
            positions, normals = original[triangle_index]
            a, b, c = positions
            v0, v1, v2 = b-a, c-a, point-a
            d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
            d20, d21 = v2.dot(v0), v2.dot(v1)
            denominator = d00*d11-d01*d01
            if denominator <= 0:
                raise ValueError('Invalid original tire normal interpolation triangle')
            v = (d11*d20-d01*d21)/denominator
            w = (d00*d21-d01*d20)/denominator
            corner_normals[index] = ((1-v-w)*normals[0]+v*normals[1]+w*normals[2]).normalized()
    tire.data.normals_split_custom_set(corner_normals)
    tire['shoulder_construction'] = '56 actual recessed cuts; no raised trim strips; original surface normals preserved outside cavities'
    tire['shoulder_cutter_radius_m'] = .0012
    tire['shoulder_cutter_center_below_nominal_m'] = .0007
