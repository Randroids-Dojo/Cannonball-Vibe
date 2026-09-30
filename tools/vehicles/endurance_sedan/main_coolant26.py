"""Portable original cooling-package correction; no file reads, saves or exports."""
import math
import bpy
from mathutils import Vector, Quaternion

OLD_HOSE = [(-.559, 1.107, .698), (-.439, 1.817, .575), (-.491, 2.007, .518)]
def inboard_route():
    first=Vector(OLD_HOSE[0]);direction=(Vector(OLD_HOSE[1])-first).normalized()
    start=first+direction*.010
    controls=[start,start+direction*.030,Vector((-.432,1.14,.738)),Vector((-.432,1.20,.725))]
    points=[tuple(first),tuple(start)]
    for t in (.25,.5,.75,1.):
        weights=((1-t)**3,3*(1-t)**2*t,3*(1-t)*t*t,t**3)
        points.append(tuple(sum((p*w for p,w in zip(controls,weights)),Vector())))
    points.extend([(-.432,1.48,.660),(-.432,1.76,.594),(-.433,1.835,.570),
                   (-.440,1.90,.547),(-.462,1.94,.538),
                   tuple(a+.15*(b-a) for a,b in zip(OLD_HOSE[2],OLD_HOSE[1])),OLD_HOSE[2]])
    return points

NEW_HOSE=inboard_route()


def apply(geo, row):
    results = []
    core = bpy.data.objects['LOD0_CentralRadiator']
    assert not core.modifiers
    old_core = row(core)
    for vertex in core.data.vertices:
        vertex.co.y += .005
    core.data.update()
    new_core = row(core)
    delta = [[b[k] - a[k] for k in range(3)] for a, b in zip(old_core['vertices'], new_core['vertices'])]
    expected_points = [list(Vector((a[0], a[1] + .005, a[2]))) for a in old_core['vertices']]
    assert new_core['vertices'] == expected_points, 'Core is not the exact native-float translated mesh'
    assert max(abs(d[1] - .005) for d in delta) <= 2e-7
    assert all(old_core[k] == new_core[k] for k in ('triangles', 'uvs', 'triangle_materials', 'materials'))
    normal_error = max(math.degrees(math.acos(max(-1., min(1., sum(x*y for x,y in zip(a,b))/(math.hypot(*a)*math.hypot(*b)))))) for a,b in zip(old_core['normals'],new_core['normals']))
    assert normal_error <= .025
    assert all(abs(math.hypot(*n)-1) <= 1e-6 for n in new_core['normals'])
    results.append({'object': core.name, 'translation_m': [0, .005, 0], 'native_float_positions_exact': True, 'maximum_native_normal_change_degrees': normal_error, 'maximum_translation_rounding_error_m': max(abs(d[1]-.005) for d in delta), 'triangle_delta': 0})
    carrier = bpy.data.objects['LOD0_ChargeCoolingRadiator']
    carrier_points = [carrier.matrix_world @ vertex.co for vertex in carrier.data.vertices]
    receiving_y = max(p.y for p in carrier_points)
    assert abs(receiving_y - 2.1415) < 1e-6
    for number in range(36):
        obj = bpy.data.objects['LOD0_CoolerFin_' + str(number)]
        assert not obj.modifiers and len(obj.data.materials) == 1
        old = row(obj)
        points = [list(vertex.co) for vertex in obj.data.vertices]
        rear_y = min(p[1] for p in points)
        selected = [i for i, p in enumerate(points) if abs(p[1] - rear_y) < 1e-7]
        assert len(selected) == 4 and abs(rear_y - receiving_y - .0005) < 1e-6
        for index in selected:
            points[index][1] = receiving_y
        faces = [list(face.vertices) for face in obj.data.polygons]
        fresh = geo.mesh('Private_ChargeFinLanding', points, faces, obj.data.materials[0], obj.users_collection[0], obj.parent)
        fresh.matrix_world = obj.matrix_world.copy()
        counts = geo.evaluated_counts(fresh)
        assert counts['triangles'] == len(old['triangles'])
        for key in ('nonmanifold_edges', 'duplicate_faces', 'degenerate_faces', 'degenerate_triangles',
                    'triangulated_nonmanifold_edges', 'triangulated_duplicate_faces',
                    'nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals'):
            assert counts[key] == 0, (obj.name, key)
        updated = row(fresh)
        assert all(updated['vertices'][i] == point for i, point in enumerate(old['vertices']) if i not in selected)
        obj.data = fresh.data
        bpy.data.objects.remove(fresh, do_unlink=True)
        results.append({'object': obj.name, 'rear_edge_vertices': selected,
                        'original_rear_y_m': rear_y, 'receiving_y_m': receiving_y,
                        'back_extension_m': rear_y - receiving_y, 'triangle_delta': 0,
                        'scope': 'Unchanged front profile; new rear chamfer and landing geometry. Full receiving-cap proof pending.'})
    hose = bpy.data.objects['LOD0_CoolantHose']
    assert not hose.modifiers and len(hose.data.materials) == 1
    old_hose = row(hose)
    recreated = geo.tube('Private_OriginalCoolantRoute', OLD_HOSE, .017, hose.data.materials[0], hose.users_collection[0], hose.parent, sides=10)
    recreated.matrix_world = hose.matrix_world.copy()
    old_points = row(recreated)['vertices']
    actual_points = old_hose['vertices']
    assert len(old_points) == len(actual_points)
    assert max((Vector(a) - Vector(b)).length for a, b in zip(old_points, actual_points)) <= 1e-7
    original_rings = [old_points[:10], old_points[-10:]]
    data = recreated.data
    bpy.data.objects.remove(recreated, do_unlink=True)
    if data.users == 0:
        bpy.data.meshes.remove(data)
    fresh = geo.tube('Private_CorrectedCoolantRoute', NEW_HOSE, .017, hose.data.materials[0], hose.users_collection[0], hose.parent, sides=10)
    fresh.matrix_world = hose.matrix_world.copy()
    initial_route = row(fresh)
    initial_endpoint_errors = [max((Vector(a)-Vector(b)).length for a,b in zip(old,new))
                               for old,new in zip(original_rings,[initial_route['vertices'][:10],initial_route['vertices'][-10:]])]
    end = Vector(NEW_HOSE[-1]); tangent = (end-Vector(NEW_HOSE[-2])).normalized()
    initial_axis = (Vector(initial_route['vertices'][-10])-end).normalized()
    desired_axis = (Vector(original_rings[-1][0])-end).normalized()
    phase = math.atan2(tangent.dot(initial_axis.cross(desired_axis)), initial_axis.dot(desired_axis))
    distances=[0.]
    for a,b in zip(NEW_HOSE,NEW_HOSE[1:]): distances.append(distances[-1]+(Vector(b)-Vector(a)).length)
    for index,point in enumerate(NEW_HOSE):
        previous = Vector(NEW_HOSE[max(0,index-1)]); following = Vector(NEW_HOSE[min(len(NEW_HOSE)-1,index+1)])
        axis=(following-previous).normalized(); center=Vector(point)
        correction=Quaternion(axis,phase*distances[index]/distances[-1])
        for vertex in fresh.data.vertices[index*10:(index+1)*10]: vertex.co=center+correction@(vertex.co-center)
    for index,point in enumerate(original_rings[0]): fresh.data.vertices[index].co=point
    for index,point in enumerate(original_rings[1]): fresh.data.vertices[(len(NEW_HOSE)-1)*10+index].co=point
    fresh.data.update();geo.project_uv(fresh)
    current = row(fresh)
    endpoint_errors = [max((Vector(a) - Vector(b)).length for a, b in zip(old, new))
                       for old, new in zip(original_rings, [current['vertices'][:10], current['vertices'][-10:]])]
    assert max(endpoint_errors) <= 2e-7
    counts = geo.evaluated_counts(fresh)
    for key in ('nonmanifold_edges', 'duplicate_faces', 'degenerate_faces', 'degenerate_triangles',
                'triangulated_nonmanifold_edges', 'triangulated_duplicate_faces',
                'nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals'):
        assert counts[key] == 0, key
    hose.data = fresh.data
    bpy.data.objects.remove(fresh, do_unlink=True)
    results.append({'object': hose.name, 'old_centerline_m': OLD_HOSE, 'new_centerline_m': NEW_HOSE,
                    'end_ring_maximum_coordinate_errors_m': endpoint_errors, 'uncorrected_parallel_transport_end_errors_m': initial_endpoint_errors, 'distributed_frame_correction_radians': phase,
                    'triangle_delta': len(current['triangles']) - len(old_hose['triangles']),
                    'scope': 'Same endpoints, endpoint rings, tangents and radius; middle route changed. Full fit and continuous clearance pending.'})
    return results
