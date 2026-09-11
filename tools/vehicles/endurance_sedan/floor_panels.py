"""Removable front floor panels fitted into real structural recesses."""

import json
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import geometry as geo


def freeze(obj):
    """Use exact evaluated triangles and corner attributes as Boolean input.

    Nonplanar evaluated n-gons may produce a duplicate fan triangle after a
    later Boolean. The actual loop triangles are the already rendered surface;
    preserve those faces, their original corner normals and every UV layer.
    """
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    source = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    source.calc_loop_triangles()
    loops = [index for triangle in source.loop_triangles for index in triangle.loops]
    data = bpy.data.meshes.new(obj.name+'EvaluatedTriangleInput')
    data.from_pydata([tuple(vertex.co) for vertex in source.vertices], [],
                     [tuple(triangle.vertices) for triangle in source.loop_triangles])
    for material in source.materials:
        # Evaluated material IDs belong to the depsgraph and become invalid
        # when its temporary mesh is cleared. Retain the original datablock.
        original = material.original if material is not None else None
        if original is not None and bpy.data.materials.get(original.name) != original:
            raise ValueError(f'Nonpersistent evaluated material on {obj.name}')
        data.materials.append(original)
    for polygon, triangle in zip(data.polygons, source.loop_triangles):
        original = source.polygons[triangle.polygon_index]
        polygon.material_index = original.material_index
        polygon.use_smooth = original.use_smooth
    for original in source.uv_layers:
        layer = data.uv_layers.new(name=original.name)
        layer.data.foreach_set('uv', [value for index in loops for value in original.data[index].uv])
    data.update()
    data.normals_split_custom_set([tuple(source.corner_normals[index].vector) for index in loops])
    evaluated.to_mesh_clear()
    obj.modifiers.clear()
    obj.data = data


def prism(name, outline, low, high, material, collection, parent=None):
    count = len(outline)
    vertices = [(x, y, z) for z in (low, high) for x, y in outline]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count)
              for i in range(count)]
    return geo.mesh(name, vertices, faces, material, collection, parent)


def offset(outline, gap):
    result = []
    for index, point in enumerate(outline):
        a, b, c = (Vector(outline[i % len(outline)])
                   for i in (index - 1, index, index + 1))
        first, second = (b - a).normalized(), (c - b).normalized()
        normal_a, normal_b = Vector((first.y, -first.x)), Vector((second.y, -second.x))
        direction = (normal_a + normal_b).normalized()
        result.append(tuple(b + direction * (gap / direction.dot(normal_a))))
    return result


def wheel_cut(name, side, radius, start, collection):
    vertices = [(side * x, 1.46 + radius * math.cos(i * math.tau / 64),
                 .3433 + radius * math.sin(i * math.tau / 64))
                for x in (start, 1.15) for i in range(64)]
    faces = [tuple(reversed(range(64))), tuple(range(64, 128))]
    faces += [(i, (i + 1) % 64, (i + 1) % 64 + 64, i + 64) for i in range(64)]
    return geo.mesh(name, vertices, faces, None, collection)


def remove(obj):
    bpy.data.objects.remove(obj, do_unlink=True)


def coat_cut_faces(obj, material):
    """New recess faces retain this assembly's declared single coating.

    The exact Boolean solver can add a null cutter slot. Reject an actual
    second material instead of silently changing a legitimately mixed mesh.
    """
    if any(slot is not None and slot != material for slot in obj.data.materials):
        raise ValueError(f'Unexpected second coating on {obj.name}')
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for face in obj.data.polygons:
        face.material_index = 0


def clean_new_slivers(obj, original_vertices):
    """Dissolve only a new, sub-0.1 micrometer collinear Boolean vertex.

    Original vertices are protected. Both directions of the actual vertex to
    surface comparison must stay below0.1 micrometer; this is not a general
    decimator or a relaxation of the exported triangle-validity gate.
    """
    records = []
    original = {tuple(v) for v in original_vertices}
    for _ in range(12):
        mesh = obj.data
        mesh.calc_loop_triangles()
        bad = [t for t in mesh.loop_triangles
               if (mesh.vertices[t.vertices[1]].co - mesh.vertices[t.vertices[0]].co).cross(
                   mesh.vertices[t.vertices[2]].co - mesh.vertices[t.vertices[0]].co).length / 2 <= 1e-12]
        if not bad:
            return records
        triangle = bad[0]
        options = []
        for index in range(3):
            vertex = mesh.vertices[triangle.vertices[index]]
            point = vertex.co.copy()
            a, b = (mesh.vertices[triangle.vertices[(index + j) % 3]].co.copy() for j in (1, 2))
            edge = b - a
            if edge.length_squared == 0:
                continue
            fraction = (point - a).dot(edge) / edge.length_squared
            distance = (point - (a + fraction * edge)).length
            if 0 <= fraction <= 1 and distance < 1e-7 and tuple(point) not in original:
                options.append((distance, vertex.index, list(point)))
        if not options:
            raise RuntimeError(f'No bounded new-vertex correction in {obj.name}: {tuple(triangle.vertices)}')
        distance, index, point = min(options)
        before_vertices = [v.co.copy() for v in mesh.vertices]
        before_triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
        edit = bmesh.new()
        edit.from_mesh(mesh)
        edit.verts.ensure_lookup_table()
        bmesh.ops.dissolve_verts(edit, verts=[edit.verts[index]], use_face_split=True, use_boundary_tear=False)
        edit.to_mesh(mesh)
        edit.free()
        mesh.update()
        mesh.calc_loop_triangles()
        after_vertices = [v.co.copy() for v in mesh.vertices]
        after_triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
        before = BVHTree.FromPolygons(before_vertices, before_triangles, all_triangles=True)
        after = BVHTree.FromPolygons(after_vertices, after_triangles, all_triangles=True)
        old_to_new = max(after.find_nearest(p)[3] for p in before_vertices)
        new_to_old = max(before.find_nearest(p)[3] for p in after_vertices)
        if old_to_new >= 1e-7 or new_to_old >= 1e-7:
            raise RuntimeError(f'Bounded sliver correction changed {obj.name} surface')
        records.append({'removed_new_vertex_m': point, 'edge_distance_m': distance,
                        'old_to_new_vertex_surface_max_m': old_to_new,
                        'new_to_old_vertex_surface_max_m': new_to_old})
    raise RuntimeError(f'Bounded sliver correction did not converge for {obj.name}')


def build(body, collection, lod, mats):
    bumper = bpy.data.objects['LOD0_FrontBumper']
    bodies = (body, bumper)
    for obj in bodies:
        freeze(obj)
    before = {obj.name: [tuple(v.co) for v in obj.data.vertices] for obj in bodies}
    outline = [(.255, .880), (.645, .880), (.645, 2.100), (.638, 2.127),
               (.605, 2.211), (.588, 2.240), (.160, 2.240), (.160, 1.100), (.255, 1.100)]
    expanded = offset(outline, .0025)
    for side in (-1, 1):
        old = bpy.data.objects.get('LOD0_FrontUndertray_' + str(side))
        if old:
            remove(old)
        panel = prism('LOD0_FrontUndertray_' + str(side), [(side*x, y) for x, y in outline],
                      .1355, .1395, mats['trim'], collection, lod)
        panel['maximum_lod'] = 0
        panel['assembly_boundary'] = 'Removable4mm floor panel;2.5mm perimeter clearance; eight separate mounting spacers across the car'
        wheel = wheel_cut('FrontPanelWheelClearance', side, .4483, .460, collection)
        geo.boolean(panel, wheel)
        remove(wheel)
        pocket = prism('FrontFloorPanelRecess', [(side*x, y) for x, y in expanded],
                       -.100, .1455, None, collection)
        wheel = wheel_cut('FrontPocketWheelBoundary', side, .4458, .4625, collection)
        geo.boolean(pocket, wheel)
        remove(wheel)
        for obj in bodies:
            geo.boolean(obj, pocket)
        remove(pocket)
        for index, (x, y) in enumerate(((.34, .94), (.55, .94), (.34, 2.08), (.55, 2.08))):
            center = side*x
            pad = prism(f'LOD0_FrontTrayMount_{side}_{index}',
                        [(center-.006, y-.006), (center+.006, y-.006),
                         (center+.006, y+.006), (center-.006, y+.006)],
                        .1395, .1455, mats['trim'], collection, lod)
            pad['maximum_lod'] = 0
            pad['mounted_component'] = panel.name
            pad['mounting_body'] = body.name if y < 1.8 else bumper.name
            pad['assembly_boundary'] = 'Exact planar panel/spacer/body mounting faces; no nonmating overlap waiver'
    for obj in bodies:
        obj['front_floor_boolean_cleanup'] = json.dumps(clean_new_slivers(obj, before[obj.name]), separators=(',', ':'))
        coat_cut_faces(obj, mats['paint'])
    splitter(bumper, collection, lod, mats)


def ribbon(name, xs, zs, back, forward, material, collection, parent=None):
    vertices = [(x, function(x, z), z) for function in (back, forward) for x in xs for z in zs]
    stride, layer = len(zs), len(xs)*len(zs)
    faces = []
    for i in range(len(xs)-1):
        for j in range(len(zs)-1):
            a, b = i*stride+j, (i+1)*stride+j
            faces += [(a, b, b+1, a+1), (a+layer, a+1+layer, b+1+layer, b+layer)]
    boundary = ([i*stride for i in range(len(xs))]
                + [(len(xs)-1)*stride+j for j in range(1, len(zs))]
                + [i*stride+stride-1 for i in reversed(range(len(xs)-1))]
                + [j for j in reversed(range(1, len(zs)-1))])
    faces += [(a, a+layer, b+layer, b) for a, b in zip(boundary, boundary[1:]+boundary[:1])]
    return geo.mesh(name, vertices, faces, material, collection, parent)


def splitter(bumper, collection, lod, mats):
    """Fit a restrained front lip and four supports to the actual fascia."""
    # Floor recesses create new n-gons. Freeze their rendered triangles before
    # another Boolean so an unrelated floor face cannot change triangulation.
    freeze(bumper)
    bumper.data.calc_loop_triangles()
    vertices = [v.co.copy() for v in bumper.data.vertices]
    triangles = [tuple(t.vertices) for t in bumper.data.loop_triangles]
    reference = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)

    def front(x, z):
        hit = reference.ray_cast(Vector((x, 3, z)), Vector((0, -1, 0)), 2)[0]
        if hit is None:
            raise RuntimeError(f'Front splitter misses actual fascia at {x},{z}')
        return hit.y

    xs, zs = [-.830+1.660*i/24 for i in range(25)], [.207, .219]
    old = bpy.data.objects.get('LOD0_FrontSplitter')
    if old:
        remove(old)
    panel = ribbon('LOD0_FrontSplitter', xs, zs, lambda x, z: front(x, z)-.010,
                   lambda x, z: min(2.400, front(x, z)+.020*(1-(abs(x)/.830)**8)),
                   mats['trim'], collection, lod)
    panel['assembly_boundary'] = '12mm original lip fitted to actual fascia; four4mm mounting supports;2.5mm pocket edge clearance'
    pocket = ribbon('FrontSplitterRecess', [-.8325, *xs, .8325], [.2045, *zs, .2215],
                    lambda x, z: front(x, z)-.014, lambda x, z: 3., None, collection)
    geo.boolean(bumper, pocket)
    remove(pocket)
    for index, cell in enumerate((3, 8, 15, 20)):
        pad = ribbon(f'LOD0_SplitterMount_{index}', xs[cell:cell+2], zs,
                     lambda x, z: front(x, z)-.014, lambda x, z: front(x, z)-.010,
                     mats['trim'], collection, lod)
        pad['maximum_lod'] = 0
        pad['mounted_component'] = panel.name
        pad['mounting_body'] = bumper.name
        pad['assembly_boundary'] = 'Exact fascia/support/lip seating faces; no unrelated overlap waiver'
    bumper['splitter_boolean_cleanup'] = json.dumps(clean_new_slivers(bumper, vertices), separators=(',', ':'))
    coat_cut_faces(bumper, mats['paint'])
