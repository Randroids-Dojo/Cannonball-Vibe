"""Original continuous cap field and woven acoustic cover on supported grilles."""
import hashlib
import json
import math

import bpy
from mathutils import Vector
from . import geometry as geo


def physical(obj):
    data = obj.data
    return hashlib.sha256(json.dumps({
        'vertices': [list(v.co) for v in data.vertices],
        'polygons': [list(p.vertices) for p in data.polygons],
        'uv': {layer.name: [list(v.uv) for v in layer.data] for layer in data.uv_layers},
        'matrix': [list(row) for row in obj.matrix_world],
        'parent': obj.parent.name if obj.parent else None,
    }, separators=(',', ':')).encode()).hexdigest()


def apply(engineering):
    """Use current construction parameters; no historical mesh or source input."""
    if 'Material_AcousticCloth' in bpy.data.materials:
        raise ValueError('Acoustic finish must be applied once')
    cloth = bpy.data.materials['Material_Fabric'].copy()
    cloth.name = 'Material_AcousticCloth'
    color = (.012, .013, .014, 1.)
    cloth.diffuse_color = color
    cloth.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = color
    cloth['provenance'] = 'Project-original acoustic textile response; shares the existing original packed fabric normal and roughness textures'
    cloth['finish_role'] = 'Woven textile wraps the complete modeled cosmetic speaker cover, including its perimeter and concealed return; no acoustic-performance simulation'
    images = {node.image.name: hashlib.sha256(node.image.packed_file.data).hexdigest()
              for node in cloth.node_tree.nodes if getattr(node, 'image', None)}
    records = []
    for form in engineering:
        obj = bpy.data.objects[form['name']]
        mesh = obj.data
        before = physical(obj)
        assert len(obj.material_slots) == 1
        mesh.materials.clear()
        mesh.materials.append(cloth)
        axis = Vector(form['outward'])
        plane = form['mounting_plane_m']
        axes = form['projection_axes']
        outline = form['original_outline_m']
        lower = [min(p[i] for p in outline) for i in range(2)]
        upper = [max(p[i] for p in outline) for i in range(2)]
        center = [(a+b)/2 for a, b in zip(lower, upper)]
        radii = [(b-a)/2 for a, b in zip(lower, upper)]
        depth_range = form['original_depth_range_m']
        middle = sum(depth_range)/2
        half_depth = (depth_range[1]-depth_range[0])/2
        targets = [None] * len(mesh.loops)
        classes = {}
        local_normal_matrix = obj.matrix_world.to_3x3().transposed()
        for face in mesh.polygons:
            points = [obj.matrix_world @ mesh.vertices[i].co for i in face.vertices]
            role = 'skin'
            if max(abs(p.dot(axis)-plane) for p in points) <= 1e-6:
                role = 'back'
            if form['relief'] is not None:
                for index, cut in enumerate(form['relief']['outward_planes_yz']):
                    n, d = cut['normal'], cut['constant_m']
                    if max(abs(n[0]*p.y+n[1]*p.z-d) for p in points) <= 1e-6:
                        role = 'relief_' + str(index)
                        break
            classes[face.index] = role
            face.use_smooth = role == 'skin'
            face.material_index = 0
            for loop_index in face.loop_indices:
                if role != 'skin':
                    value = face.normal.copy()
                else:
                    p = obj.matrix_world @ mesh.vertices[mesh.loops[loop_index].vertex_index].co
                    gradient = axis * ((p.dot(axis)-middle)/(half_depth*half_depth))
                    for dimension, index in enumerate(axes):
                        gradient[index] += (p[index]-center[dimension])/(radii[dimension]*radii[dimension])
                    if gradient.length < 1e-8:
                        raise ValueError('Undefined acoustic cap field')
                    value = local_normal_matrix @ gradient
                    value.normalize()
                targets[loop_index] = value
        links = {}
        for face in mesh.polygons:
            for loop_index in face.loop_indices:
                links.setdefault(mesh.loops[loop_index].edge_index, []).append(face.index)
        added_sharp = []
        for edge_index, faces in links.items():
            if len(faces) != 2:
                raise ValueError('Open acoustic cap')
            if classes[faces[0]] != classes[faces[1]]:
                if not mesh.edges[edge_index].use_edge_sharp:
                    added_sharp.append(edge_index)
                mesh.edges[edge_index].use_edge_sharp = True
        mesh.normals_split_custom_set(targets)
        mesh.update()
        maximum = 0.
        for actual, expected in zip(mesh.corner_normals, targets):
            a, b = actual.vector, expected
            if not all(math.isfinite(x) for x in a) or abs(a.length-1.) > 1e-6:
                raise ValueError('Invalid raw acoustic corner normal')
            cross = a.cross(b)
            error = math.degrees(math.atan2(cross.length, a.dot(b)))
            maximum = max(maximum, error)
        if maximum > .025:
            raise ValueError('Acoustic normal encoding exceeded .025 degrees: ' + str(maximum))
        assert physical(obj) == before
        counts = geo.evaluated_counts(obj)
        for key in ('nonmanifold_edges', 'duplicate_faces', 'degenerate_faces', 'degenerate_triangles',
                    'triangulated_duplicate_faces', 'triangulated_nonmanifold_edges',
                    'nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals'):
            assert counts[key] == 0, (obj.name, key, counts[key])
        records.append({'name': obj.name, 'physical_before_after_sha256': before,
                        'new_sharp_edge_indices': added_sharp,
                        'cloth_faces': len(mesh.polygons),
                        'maximum_native_target_error_deg': maximum,
                        'classes': classes, 'local_corner_targets': [list(v) for v in targets],
                        'field': 'Continuous elliptical cap gradient; flat supported back and relief boundaries are separate domains.'})
    return {'parts': records, 'new_material': cloth.name, 'base_color_linear': color,
            'shared_packed_images': images, 'new_image_count': 0, 'material_policy': 'One material on each closed wrapped cover; existing batching contract preserved.',
            'scope': 'New authored field and surface finish. Physical geometry, UVs and supports unchanged; final rendered/export/runtime acceptance remains separate.'}
