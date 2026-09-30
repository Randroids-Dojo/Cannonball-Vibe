"""Temporary technical diagrams and swatches made from the opened source.

These are explicitly labeled inspection views. No overlay, ghost material or
swatch geometry is saved to the production source or included in its export.
"""

import json
import math

import bpy
import numpy as np
from mathutils import Vector

from . import geometry as geo


SWATCHES = ('Paint', 'Trim', 'Rubber', 'Leather', 'Carpet', 'Fabric',
            'Alloy', 'Metal', 'Glass')

GRAZING_CONFIG = {'mode': 'moving physical strips; original vehicle materials',
                  'count': 3, 'power_w_each': 400., 'width_m': .15,
                  'height_m': 3., 'horizontal_radius_m': 2.2,
                  'height_above_target_m': 1.1, 'sweep_degrees': [-65., 65.],
                  'rear_roof_light_side': 'opposite camera in XY, matched elevation; original paint',
                  'strip_angle_spacing_rad': .33,
                  'world_color_linear': [.03, .03, .03, 1.],
                  'world_strength': .2, 'preview_studio_lights_disabled': True,
                  'exposure': 'unchanged from opened source', 'source_saved': False}


def collection(name):
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


def grazing_lights(scene):
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT' and obj.name.startswith('Preview_'):
            obj.hide_render = True
    background = scene.world.node_tree.nodes['Background']
    background.inputs[0].default_value = GRAZING_CONFIG['world_color_linear']
    background.inputs[1].default_value = GRAZING_CONFIG['world_strength']
    lamps = []
    for index in range(GRAZING_CONFIG['count']):
        data = bpy.data.lights.new(f'QA_MovingReflectionStrip_{index}', 'AREA')
        data.shape = 'RECTANGLE'
        data.energy = GRAZING_CONFIG['power_w_each']
        data.size = GRAZING_CONFIG['width_m']
        data.size_y = GRAZING_CONFIG['height_m']
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        lamps.append(obj)
    return lamps


def pose_grazing(lamps, camera_location, target, phase, capture_view):
    target = Vector(target)
    outward = Vector(camera_location)-target
    center = math.atan2(outward.y, outward.x)
    height = 1.1
    if capture_view.startswith('graze_rear_'):
        # A roof reflection needs light on the opposite horizontal side of
        # its upward-facing surface. Preserve the recorded strip sweep while
        # matching camera elevation, instead of lighting only the side glass.
        center += math.pi
        height = 2.2*outward.z/math.hypot(outward.x, outward.y)
    sweep = math.radians(-65+130*phase)
    result = []
    for index, lamp in enumerate(lamps):
        angle = center+sweep+(index-1)*GRAZING_CONFIG['strip_angle_spacing_rad']
        lamp.location = target+Vector((2.2*math.cos(angle), 2.2*math.sin(angle), height))
        lamp.rotation_euler = (target-lamp.location).to_track_quat('-Z', 'Y').to_euler()
        result.append({'name': lamp.name, 'location_source_m': list(lamp.location),
                       'rotation_euler_rad': list(lamp.rotation_euler),
                       'target_source_m': list(target), 'power_w': float(lamp.data.energy),
                       'size_m': [float(lamp.data.size), float(lamp.data.size_y)]})
    return result


def wiper_sweep(scene, controls, camera):
    """Draw sampled actual evaluated rubber projections, never a contact proof.

    The continuous wiper/glass gate remains authoritative. All display geometry
    and labels live only in this unsaved review scene. No asset mesh is hidden.
    """
    group = collection('QA_SampledWiperSweep')
    materials = {}
    for name, color in {'rubber': (.02, .7, 1), 'glass': (1, .4, .04),
                        'label': (1, 1, 1), 'label_background': (.002, .002, .002)}.items():
        material = bpy.data.materials.new('QA_WiperDiagnostic_' + name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = (*color, 1)
        output = nodes.new('ShaderNodeOutputMaterial')
        material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
        materials[name] = material

    def evaluated(name):
        obj = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = obj.to_mesh()
        try:
            mesh.calc_loop_triangles()
            return ([obj.matrix_world @ vertex.co for vertex in mesh.vertices],
                    [tuple(tri.vertices) for tri in mesh.loop_triangles])
        finally:
            obj.to_mesh_clear()

    def boundary(triangles, selected):
        edges = {}
        for tri in triangles:
            if not set(tri) <= selected:
                continue
            for a, b in zip(tri, (*tri[1:], tri[0])):
                edge = tuple(sorted((a, b)))
                edges[edge] = edges.get(edge, 0)+1
        if not edges or max(edges.values()) > 2:
            raise ValueError('Invalid evaluated diagnostic surface boundary')
        return [edge for edge, count in edges.items() if count == 1]

    saved_controls = {key: controls[key] for key in ('wiper_sweep', 'wipers_running')}
    saved_frame, saved_subframe = scene.frame_current, scene.frame_subframe
    samples, lift = [], .002
    try:
        controls['wiper_sweep'] = controls['wipers_running'] = 0.
        controls.update_tag()
        scene.frame_set(1)
        bpy.context.view_layer.update()
        normal = (bpy.data.objects['Wiper_L'].matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        vertices, triangles = evaluated('LOD0_Windshield')
        distances = [point.dot(normal) for point in vertices]
        outer = {i for i, distance in enumerate(distances) if distance >= max(distances)-.001}
        # The actual rigid wiper axis selects the outside skin but is not the
        # exact glass plane. Fit the selected native vertices as the source QA
        # does; testing projection spread against the approximate axis would
        # incorrectly reject a planar pane with a slightly different normal.
        selected = np.asarray([list(vertices[i]) for i in sorted(outer)], dtype=float)
        if len(selected) < 3:
            raise ValueError('Missing actual outer glass vertices')
        _, _, basis = np.linalg.svd(selected-selected.mean(axis=0), full_matrices=False)
        fitted = basis[-1]
        if float(fitted @ np.asarray(normal)) < 0:
            fitted = -fitted
        fitted_distances = selected @ fitted
        span = float(np.ptp(fitted_distances))
        normal = Vector(fitted)
        if len(outer) < 3 or span > 2e-7:
            raise ValueError('Sampled overlay requires the actual planar outer glass skin')
        offset = float(fitted_distances.mean())
        glass_edges = boundary(triangles, outer)
        for index, edge in enumerate(glass_edges):
            geo.tube(f'QA_GlassBoundary_{index}',
                     [vertices[i]+normal*lift for i in edge], .001,
                     materials['glass'], group, sides=6)
        for step in range(21):
            fraction = step/20
            controls['wiper_sweep'] = fraction
            controls.update_tag()
            bpy.context.view_layer.update()
            for side in ('L', 'R'):
                pivot = bpy.data.objects['Wiper_' + side]
                inverse = pivot.matrix_world.inverted()
                points, faces = evaluated('LOD0_Wiper_' + side + 'Rubber')
                local = [inverse @ point for point in points]
                minimum = min(point.z for point in local)
                bottom = {i for i, point in enumerate(local) if point.z <= minimum+2e-7}
                edges = boundary(faces, bottom)
                if len(bottom) < 4:
                    raise ValueError('Missing actual lower rubber face')
                projected = {i: points[i]+normal*(offset-points[i].dot(normal)+lift) for i in bottom}
                for index, edge in enumerate(edges):
                    geo.tube(f'QA_WiperSample_{side}_{step}_{index}',
                             [projected[i] for i in edge], .00055,
                             materials['rubber'], group, sides=6)
                samples.append({'wiper': side, 'fraction': fraction,
                                'evaluated_bottom_vertex_indices': sorted(bottom),
                                'evaluated_bottom_source_m': [list(points[i]) for i in sorted(bottom)],
                                'signed_gap_m': [points[i].dot(normal)-offset for i in sorted(bottom)],
                                'boundary_edges': [list(edge) for edge in edges]})
    finally:
        for key, value in saved_controls.items():
            controls[key] = value
        controls.update_tag()
        scene.frame_set(saved_frame, subframe=saved_subframe)
        bpy.context.view_layer.update()
    text = bpy.data.curves.new('QA_WiperDiagnosticLabel', 'FONT')
    text.body = ('DIAGNOSTIC: 21 SAVED-DRIVER POSES\n'
                 'Cyan: projected rubber. Orange: actual glass edge.\n'
                 '2 mm display lift. No continuous-contact claim.')
    text.size = .0026
    text.materials.append(materials['label'])
    label = bpy.data.objects.new(text.name, text)
    group.objects.link(label)
    label.parent = camera
    board_mesh = bpy.data.meshes.new('QA_WiperDiagnosticLabelBackground')
    board_mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)],
                           [], [(0, 1, 2, 3)])
    board_mesh.materials.append(materials['label_background'])
    board = bpy.data.objects.new(board_mesh.name, board_mesh)
    group.objects.link(board)
    board.parent = camera
    board.location = (0, 0, -.201)
    return {'mode': 'sampled diagnostic, not continuous contact or rain simulation',
            'source_meshes': ['LOD0_Windshield', 'LOD0_Wiper_LRubber', 'LOD0_Wiper_RRubber'],
            'normal_source': list(normal), 'outer_glass_plane_offset_m': offset,
            'outer_glass_planarity_span_m': span, 'display_lift_m': lift,
            'samples': samples, 'label': 'top-margin text with dark diagnostic backdrop; vehicle materials unchanged',
            'source_saved': False}


def pose_wiper_caption(scene, camera):
    """Place the caption after the shot sets its actual lens and projection."""
    frame = list(camera.data.view_frame(scene=scene))
    if camera.data.type == 'PERSP':
        frame = [point * (.2 / -point.z) for point in frame]
    half_width = max(abs(point.x) for point in frame)
    half_height = max(abs(point.y) for point in frame)
    label = bpy.data.objects['QA_WiperDiagnosticLabel']
    label.location = (-.955*half_width, .925*half_height, -.2)
    label.data.size = .0253*half_width
    corners = [(-.98*half_width, .76*half_height, 0),
               (.30*half_width, .76*half_height, 0),
               (.30*half_width, .98*half_height, 0),
               (-.98*half_width, .98*half_height, 0)]
    board = bpy.data.objects['QA_WiperDiagnosticLabelBackground']
    scale = .201/.2 if camera.data.type == 'PERSP' else 1.
    for vertex, corner in zip(board.data.vertices, corners, strict=True):
        vertex.co = Vector(corner)*scale
    board.data.update()
    return {'camera_type': camera.data.type, 'lens_mm': camera.data.lens,
            'label_camera_local_m': list(label.location),
            'font_size_m': label.data.size,
            'board_camera_local_corners_m': [list(vertex.co+board.location)
                                             for vertex in board.data.vertices]}


def swatches():
    group = collection('QA_MaterialSwatches')
    result = {}
    for name in SWATCHES:
        material = bpy.data.materials['Material_' + name]
        sphere = geo.ellipsoid('QA_Swatch_' + name, (0, 0, .46),
                               (.86, .86, .86), material, group,
                               segments=64, rings=32)
        sphere.hide_render = True
        result[name] = sphere
    return result


def technical(scene):
    """Read actual anchors/proxy meshes and the source-embedded spec."""
    spec = json.loads(scene['specification'])
    group = collection('QA_TechnicalOverlay')
    materials = {}
    for name, color in {'wheel': (.02, .65, 1), 'camera': (1, .08, .55),
                        'occupant': (.1, 1, .2), 'collision': (1, .65, .02),
                        'com': (1, .18, .02), 'ruler': (.75, .8, .85)}.items():
        material = bpy.data.materials.new('QA_Overlay_' + name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = (*color, 1)
        emission.inputs['Strength'].default_value = 1
        output = nodes.new('ShaderNodeOutputMaterial')
        material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
        materials[name] = material
    ghost = bpy.data.materials.new('QA_TechnicalGhost_NotVehicleFinish')
    ghost.use_nodes = True
    nodes = ghost.node_tree.nodes
    nodes.clear()
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    diffuse = nodes.new('ShaderNodeBsdfDiffuse')
    diffuse.inputs['Color'].default_value = (.3, .35, .4, 1)
    mix = nodes.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = .09
    ghost.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    ghost.node_tree.links.new(diffuse.outputs[0], mix.inputs[2])
    output = nodes.new('ShaderNodeOutputMaterial')
    ghost.node_tree.links.new(mix.outputs[0], output.inputs['Surface'])
    for obj in list(bpy.data.collections['Asset'].all_objects):
        if obj.type == 'MESH' and not obj.hide_render:
            # A copied mesh prevents a shared datablock from changing another
            # visible inspection object. Only this disposable scene is affected.
            obj.data = obj.data.copy()
            obj.data.materials.clear()
            obj.data.materials.append(ghost)
            for face in obj.data.polygons:
                face.material_index = 0
    records = []

    def line(name, points, kind, radius=.004):
        if len(points)==2 and (Vector(points[1])-Vector(points[0])).length<1e-9:
            return
        geo.tube('QA_' + name, points, radius, materials[kind], group, sides=6)

    def marker(name, point, kind, radius=.024):
        geo.ellipsoid('QA_' + name, point, (radius*2,)*3,
                      materials[kind], group, segments=16, rings=8)
        records.append({'name': name, 'kind': kind, 'source_m': list(point)})

    def circle(name, center, radius, axis, kind):
        axes = [index for index in range(3) if index != axis]
        points = []
        for i in range(65):
            point = Vector(center)
            point[axes[0]] += radius * math.cos(i * math.tau / 64)
            point[axes[1]] += radius * math.sin(i * math.tau / 64)
            points.append(point)
        line(name, points, kind)

    for suffix in ('FL', 'FR', 'RL', 'RR'):
        center = bpy.data.objects['Wheel_' + suffix].matrix_world.translation
        marker('Wheel_' + suffix, center, 'wheel')
        circle('TireEnvelope_' + suffix, center, spec['geometry']['wheel_radius_m'], 0, 'wheel')
        for prefix in ('Contact_', 'Suspension_'):
            obj = bpy.data.objects.get(prefix + suffix)
            if obj is not None:
                marker(obj.name, obj.matrix_world.translation, 'wheel', .018)
                line(obj.name + '_link', [center, obj.matrix_world.translation], 'wheel')
    for name in spec['hardpoints_source_m']:
        if 'Camera' in name:
            obj = bpy.data.objects[name]
            marker(name, obj.matrix_world.translation, 'camera')
    center = (0, spec['geometry']['center_of_mass_forward_m'],
              spec['geometry']['center_of_mass_height_m'])
    marker('CenterOfMass', center, 'com', .06)
    for axis in range(3):
        a, b = Vector(center), Vector(center)
        a[axis] -= .15
        b[axis] += .15
        line('COM_axis_' + str(axis), [a, b], 'com')
    for occupant in spec['occupant_envelopes']:
        marker(occupant['seat'] + '_hip', occupant['hip'], 'occupant')
        marker(occupant['seat'] + '_eye', occupant['eye'], 'occupant')
        line(occupant['seat'] + '_torso', [occupant['hip'], occupant['eye']], 'occupant')
        for axis in range(3):
            circle(occupant['seat'] + '_head_' + str(axis), occupant['eye'],
                   occupant['head_radius_m'], axis, 'occupant')
    for obj in list(bpy.data.collections['Asset'].all_objects):
        if obj.type == 'MESH' and obj.name.startswith('CollisionProxy_'):
            points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
            for index, edge in enumerate(obj.data.edges):
                line(obj.name + '_' + str(index), [points[i] for i in edge.vertices], 'collision')
            records.append({'name': obj.name, 'kind': 'collision',
                            'source_vertices_m': [list(p) for p in points]})
    for axis, origin, start, end in ((0, (0, 2.85, 0), -1.5, 1.5),
                                    (1, (1.35, 0, 0), -3, 3),
                                    (2, (1.35, 2.85, 0), 0, 2)):
        a, b = Vector(origin), Vector(origin)
        a[axis], b[axis] = start, end
        line('Ruler_' + str(axis), [a, b], 'ruler')
        for tick in range(round(start*2), round(end*2)+1):
            p, q = Vector(origin), Vector(origin)
            p[axis] = q[axis] = tick / 2
            # Both perpendicular planes keep the marks legible when an
            # orthographic camera looks directly along either other axis.
            # Previously the longitudinal ruler's Z-only ticks disappeared
            # in the top and underside views.
            for cross in range(3):
                if cross == axis:
                    continue
                p, q = Vector(origin), Vector(origin)
                p[axis] = q[axis] = tick / 2
                p[cross] -= .04 if tick % 2 else .07
                q[cross] += .04 if tick % 2 else .07
                line(f'Ruler_{axis}_{tick}_{cross}', [p, q], 'ruler')
    return {'mode': 'technical x-ray; temporary materials and geometry',
            'source_specification_revision': spec.get('specification_revision'),
            'ruler_minor_m': .5, 'ruler_major_m': 1,
            'ruler_ticks': 'crosses in both perpendicular planes',
            'legend': {'cyan': 'wheel/contact/suspension', 'magenta': 'camera',
                       'green': 'occupant hip/eye/head envelope',
                       'yellow': 'actual collision proxy', 'orange': 'center of mass'},
            'markers': records, 'source_saved': False}
