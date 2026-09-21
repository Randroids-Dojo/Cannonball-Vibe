"""Install and read complete current front fields; no source saves or exports."""
import math

import bpy

from .. import corner_encoding, reserve_correspondence26, source_generation as records
from ..finishing34.front_sheet import field_support
from ..qa.front_finish_report import NAMES, POLICY, require


def capture(obj):
    if obj.name in NAMES:
        identity = [[float(i == j) for j in range(4)] for i in range(4)]
        require(obj.type == 'MESH' and not obj.modifiers and obj.parent and obj.parent.name == 'Visual_LOD0'
                and [list(row) for row in obj.matrix_world] == identity,
                'Current front native member has changed frame, parent or modifier inventory')
    return records.read_plain(reserve_correspondence26.evaluated(obj))


def verify_fields(actual, requested, *, names=NAMES):
    require(set(actual) == set(requested) == set(names), 'Incomplete current front native field domain')
    result = {}
    for name in names:
        row, plan = actual[name], requested[name]
        require(row['name'] == name and
                all(row[key] == plan[key] for key in ('vertices', 'triangles', 'materials', 'triangle_materials')),
                'Current front native geometry/material differs from request: ' + name)
        require(set(row['uvs']) == set(plan['uv_corner_targets']) and row['uvs'],
                'Current front UV layer domain differs: ' + name)
        require(len(row['triangles']) == len(row['triangle_loops']) == len(plan['normal_corner_targets']) and
                all(len(value) == len(row['triangles']) for value in plan['uv_corner_targets'].values()),
                'Current front target triangle inventory differs: ' + name)
        require(sorted(loop for triangle in row['triangle_loops'] for loop in triangle)
                == list(range(len(row['normals']))), 'Current explicit front loops omitted or duplicated: ' + name)
        unit = max(abs(math.hypot(*normal) - 1.) for normal in row['normals'])
        require(math.isfinite(unit) and unit <= POLICY['normal_unit_error'] and
                all(all(math.isfinite(value) for value in normal) for normal in row['normals']),
                'Invalid current front native normal: ' + name)
        fields = []
        maximum_uv = 0.
        for index, loops in enumerate(row['triangle_loops']):
            targets = plan['normal_corner_targets'][index]
            require(len(loops) == len(targets) == 3 and
                    all(len(normal) == 3 and all(math.isfinite(value) for value in normal) and
                        abs(math.hypot(*normal) - 1.) <= POLICY['normal_unit_error'] for normal in targets),
                    'Invalid complete current front target normal: ' + name)
            fields.append({'triangle': index, **field_support.complete_affine_angle(
                targets, [row['normals'][loop] for loop in loops], POLICY['normal_angle_degrees'])})
            for layer, values in plan['uv_corner_targets'].items():
                require(len(values[index]) == 3, 'Incomplete front target UV triangle')
                for loop, uv in zip(loops, values[index], strict=True):
                    native_uv = row['uvs'][layer][loop]
                    require(len(uv) == len(native_uv) == 2 and
                            all(math.isfinite(value) for value in (*uv, *native_uv)), 'Invalid front UV coordinate')
                    maximum_uv = max(maximum_uv, *(abs(a - b) for a, b in zip(uv, native_uv, strict=True)))
        require(maximum_uv <= POLICY['uv_absolute'], 'Current front native UV exceeds target guard: ' + name)
        result[name] = {'triangles': len(row['triangles']), 'corners': len(row['normals']),
                        'complete_target_fields': fields,
                        'maximum_normal_degrees': max(value['maximum_degrees'] for value in fields),
                        'maximum_uv_error': maximum_uv, 'maximum_normal_unit_error': unit}
    return result


def install(plans):
    require(set(plans) == set(NAMES), 'Missing current front installation member')
    originals = {name: bpy.data.objects[name] for name in NAMES}
    original_meshes = {name: obj.data for name, obj in originals.items()}
    identity = [[float(i == j) for j in range(4)] for i in range(4)]
    for name, obj in originals.items():
        require(obj.type == 'MESH' and not obj.modifiers and obj.parent and obj.parent.name == 'Visual_LOD0'
                and [list(row) for row in obj.matrix_world] == identity,
                'Current front requires original frozen identity-space member: ' + name)
        require([material.name if material else None for material in obj.data.materials] == plans[name]['materials'],
                'Current front request changes ordered material slots: ' + name)
    staged, encoding = {}, {}
    try:
        for name, plan in plans.items():
            mesh = bpy.data.meshes.new(name + '_GuideFinish40')
            staged[name] = mesh
            mesh.from_pydata(plan['vertices'], [], plan['triangles'])
            mesh.update()
            require([list(polygon.vertices) for polygon in mesh.polygons] == plan['triangles'],
                    'Native front changed requested triangle order')
            for material in original_meshes[name].materials:
                mesh.materials.append(material)
            for polygon, material in zip(mesh.polygons, plan['triangle_materials'], strict=True):
                polygon.use_smooth = True
                polygon.material_index = material
            for layer_name, triangles in plan['uv_corner_targets'].items():
                layer = mesh.uv_layers.new(name=layer_name)
                values = [uv for triangle in triangles for uv in triangle]
                for item, value in zip(layer.data, values, strict=True):
                    item.uv = value
            targets = [normal for triangle in plan['normal_corner_targets'] for normal in triangle]
            require(len(targets) == len(mesh.loops), 'Incomplete native front corner target inventory')
            require(not mesh.validate(clean_customdata=False), 'Native front validation changed requested geometry')
            encoding[name] = corner_encoding.encode(mesh, targets)
            require(encoding[name]['passed'], 'Native front requested field encoding failed: ' + name)
        for name, mesh in staged.items():
            originals[name].data = mesh
        bpy.context.view_layer.update()
        actual = {name: capture(obj) for name, obj in originals.items()}
        fields = verify_fields(actual, plans)
        return {'after': actual, 'encoding': encoding, 'complete_fields': fields,
                'source_saved': False, 'exported': False}
    except BaseException:
        for name, mesh in original_meshes.items():
            originals[name].data = mesh
        for mesh in staged.values():
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
