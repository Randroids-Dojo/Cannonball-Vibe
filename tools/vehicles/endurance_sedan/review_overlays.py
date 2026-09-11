"""Temporary technical diagrams and swatches made from the opened source.

These are explicitly labeled inspection views. No overlay, ghost material or
swatch geometry is saved to the production source or included in its export.
"""

import json
import math

import bpy
from mathutils import Vector

from . import geometry as geo


SWATCHES = ('Paint', 'Trim', 'Rubber', 'Leather', 'Carpet', 'Fabric',
            'Alloy', 'Metal', 'Glass')


def collection(name):
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


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
