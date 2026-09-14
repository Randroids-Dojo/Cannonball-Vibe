"""Analytical field for the original eight flat friction rings."""
import math
import bpy


def apply(geo, row, encode):
    proof = []
    objects = []
    for suffix in ('FL', 'FR', 'RL', 'RR'):
        for name in ('LOD0_BrakeFace_' + suffix + '-1', 'LOD0_BrakeFace_' + suffix + '1', 'LOD0_BrakeHat_' + suffix):
            obj = bpy.data.objects[name]
            assert not obj.modifiers and len(obj.data.materials) == 1
            old = row(obj)
            mesh = obj.data
            targets = [None] * len(mesh.loops)
            counts = {'axial': 0, 'radial': 0}
            for face in mesh.polygons:
                points = [mesh.vertices[i].co for i in face.vertices]
                if max(p.x for p in points) - min(p.x for p in points) <= 1e-7:
                    assert abs(face.normal.x) > .99999
                    n = (math.copysign(1., face.normal.x), 0., 0.)
                    for index in face.loop_indices:
                        targets[index] = n
                    counts['axial'] += len(face.loop_indices)
                else:
                    radii = [math.hypot(p.y, p.z) for p in points]
                    assert max(radii) - min(radii) <= 1e-7
                    assert abs(face.normal.x) < 1e-6
                    for index in face.loop_indices:
                        p = mesh.vertices[mesh.loops[index].vertex_index].co
                        radius = math.hypot(p.y, p.z)
                        sign = math.copysign(1., face.normal.y * p.y + face.normal.z * p.z)
                        targets[index] = (0., sign * p.y / radius, sign * p.z / radius)
                    counts['radial'] += len(face.loop_indices)
            assert all(target is not None for target in targets)
            result = encode(mesh, targets)
            assert result['passed'], obj.name
            current = row(obj)
            assert {k: v for k, v in old.items() if k != 'normals'} == {k: v for k, v in current.items() if k != 'normals'}
            info = geo.evaluated_counts(obj)
            assert all(info[k] == 0 for k in ('nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals'))
            objects.append(obj)
            proof.append({'object': obj.name, 'owned_corner_domains': counts, 'native_encoding': result,
                          'geometry_uv_material_fields_exact': True, 'triangle_delta': 0})
    return objects, proof
