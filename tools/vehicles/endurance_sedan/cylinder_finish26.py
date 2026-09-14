"""Explicit flat end faces and cylindrical walls for33 visible two-ring details."""
import bpy
from mathutils import Vector


def scope():
    smooth = ['LOD0_WheelHub_' + suffix for suffix in ('FL', 'FR', 'RL', 'RR')]
    smooth += ['LOD0_StrutTop_-1', 'LOD0_StrutTop_1', 'LOD0_CoolantCap']
    flat = ['LOD0_LugBolt_' + suffix + '_' + str(j)
            for suffix in ('FL', 'FR', 'RL', 'RR') for j in range(5)]
    flat += ['LOD0_StrutNut_' + str(side) + str(j) for side in (-1, 1) for j in range(3)]
    return smooth, flat


def apply(geo, row, encode):
    smooth, flat = scope()
    proof, objects = [], []
    for name in smooth + flat:
        obj = bpy.data.objects[name]
        assert obj.type == 'MESH' and not obj.modifiers
        mesh = obj.data
        before = row(obj)
        sides = len(mesh.vertices) // 2
        assert len(mesh.vertices) == sides * 2 and len(mesh.polygons) == sides + 2
        centers = [sum((mesh.vertices[i].co for i in range(start, start+sides)), Vector()) / sides
                   for start in (0, sides)]
        axis = (centers[1] - centers[0]).normalized()
        assert (centers[1] - centers[0]).length > .0005
        targets = [None] * len(mesh.loops)
        counts = {'flat_caps': 0, 'radial_walls': 0, 'flat_hex_faces': 0}
        for face in mesh.polygons:
            is_cap = len(face.vertices) == sides and (all(i < sides for i in face.vertices) or all(i >= sides for i in face.vertices))
            if name in flat:
                counts['flat_hex_faces'] += len(face.loop_indices)
                for loop in face.loop_indices:
                    targets[loop] = tuple(face.normal)
            elif is_cap:
                counts['flat_caps'] += len(face.loop_indices)
                direction = axis if face.normal.dot(axis) > 0 else -axis
                assert abs(face.normal.dot(axis)) > .99999
                for loop in face.loop_indices:
                    targets[loop] = tuple(direction)
            else:
                assert len(face.vertices) == 4 and abs(face.normal.dot(axis)) < 1e-5
                counts['radial_walls'] += len(face.loop_indices)
                for loop in face.loop_indices:
                    point = mesh.vertices[mesh.loops[loop].vertex_index].co
                    radial = point - centers[0]
                    radial = (radial - axis * radial.dot(axis)).normalized()
                    assert radial.dot(face.normal) > .9
                    targets[loop] = tuple(radial)
        assert all(n is not None for n in targets)
        encoded = encode(mesh, targets)
        assert encoded['passed'], name
        after = row(obj)
        assert {k:v for k,v in before.items() if k != 'normals'} == {k:v for k,v in after.items() if k != 'normals'}
        quality = geo.evaluated_counts(obj)
        assert all(quality[k] == 0 for k in ('nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals'))
        proof.append({'name': name, 'domain': counts, 'axis_local': list(axis),
                      'geometry_uv_material_exact': True, 'native_encoding': encoded, 'triangle_delta': 0})
        objects.append(obj)
    assert len(objects) == 33
    return objects, proof
