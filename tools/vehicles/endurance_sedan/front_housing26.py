"""Unsaved current-source front housing proposal; caller owns scene IO."""
import math

import bpy
from mathutils import Vector


def build_candidates(geo, row, finish_native):
    originals = bpy.data.objects
    made, proof = {}, {'scope': 'Two liners, two walls and twelve fully seated retainer heads only', 'liners': [], 'walls': [], 'retainers': []}
    temporary = []

    def create_name(name):
        return 'QA_Housing_' + name

    def trim_only(obj, material):
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for p in obj.data.polygons: p.material_index = 0
        geo.project_uv(obj)

    def dispose(obj):
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0: bpy.data.meshes.remove(mesh)

    def cut(obj, tool):
        # Use the actual evaluated triangles as the receiving boundary. The
        # original object, modifiers and field arrays remain untouched.
        actual = row(tool)
        cutter = geo.mesh('QA_ExactEvaluatedCutter', actual['vertices'], actual['triangles'],
                          None, obj.users_collection[0])
        try:
            geo.boolean(obj, cutter)
        finally:
            dispose(cutter)

    def pin_outer_quads(obj):
        # Pin only the nonplanar outboard strip, leaving unrelated Boolean
        # input faces unchanged. This is the actual pre-cut rendered surface.
        mesh = obj.data
        mesh.calc_loop_triangles()
        selected = {poly.index for poly in mesh.polygons if len(poly.vertices) == 4
                    and min(abs(mesh.vertices[i].co.x) for i in poly.vertices) > .466}
        assert len(selected) == 54, 'Expected complete54-facet outer strip'
        faces, smooth, materials = [], [], []
        for poly in mesh.polygons:
            children = [tuple(t.vertices) for t in mesh.loop_triangles if t.polygon_index == poly.index] if poly.index in selected else [tuple(poly.vertices)]
            for face in children:
                faces.append(face)
                smooth.append(poly.use_smooth)
                materials.append(poly.material_index)
        original = row(obj)
        data = bpy.data.meshes.new(obj.name + 'PinnedOuterStrip')
        data.from_pydata([tuple(v.co) for v in mesh.vertices], [], faces)
        for material in mesh.materials: data.materials.append(material)
        for poly, sm, mat in zip(data.polygons, smooth, materials):
            poly.use_smooth = sm
            poly.material_index = mat
        data.update()
        obj.data = data
        geo.project_uv(obj)
        def triangles(actual):
            values = []
            for face in actual['triangles']:
                p = tuple(tuple(actual['vertices'][i]) for i in face)
                values.append(min(p, p[1:] + p[:1], p[2:] + p[:2]))
            return sorted(values)
        assert triangles(row(obj)) == triangles(original), 'Outer pin altered initial actual geometry'
        if mesh.users == 0: bpy.data.meshes.remove(mesh)
        return {'outer_quad_count': len(selected), 'actual_oriented_triangle_surface_exact': True,
                'field_scope': 'New molded liner field is evaluated on the explicit actual triangle partition; final requested-native encoding remains guarded.'}

    def endpoint_centers(name, sides):
        points = [Vector(p) for p in row(originals[name])['vertices']]
        if len(points) != 2 * sides: raise ValueError('Unexpected retained two-ring primitive: ' + name)
        return [sum(points[k:k + sides], Vector()) / sides for k in (0, sides)]

    for side, symbol in ((-1, 'L'), (1, 'R')):
        liner_name = 'LOD0_WheelArchLiner_F' + symbol
        original = originals[liner_name]
        old = row(original)
        if len(old['vertices']) != 220: raise ValueError('Expected current55-station liner')
        rings = []
        for offset in range(0, len(old['vertices']), 4):
            points = old['vertices'][offset:offset + 4]
            inner = sorted([p for p in points if abs(math.hypot(p[1] - 1.46, p[2] - .3433) - .444) < 2e-7], key=lambda p: abs(p[0]))
            outer = sorted([p for p in points if abs(math.hypot(p[1] - 1.46, p[2] - .3433) - .449) < 2e-7], key=lambda p: abs(p[0]))
            if len(inner) != 2 or len(outer) != 2: raise ValueError('Malformed original annular section')
            a = math.degrees(math.atan2(inner[0][2] - .3433, inner[0][1] - 1.46))
            if a < -28: a += 360
            rings.append((a, inner, outer))
        rings.sort(key=lambda r: r[0])
        if abs(rings[0][0] + 27) > .0001 or abs(rings[-1][0] - 207) > .0001:
            raise ValueError('Unexpected current angular endpoints')
        vertices, new_rings = [], []
        for index, (angle, inner, outer) in enumerate(rings):
            if index == 0: angle = -26.8
            if index == len(rings) - 1: angle = 206.8
            theta = math.radians(angle)
            inboard, outboard = inner[0][0], inner[1][0]
            a = [inboard, 1.46 + .444 * math.cos(theta), .3433 + .444 * math.sin(theta)]
            b = [outboard, a[1], a[2]]
            if index not in (0, len(rings) - 1): a, b = inner
            c = [outboard, 1.46 + .4465 * math.cos(theta), .3433 + .4465 * math.sin(theta)]
            d = [inboard, c[1], c[2]]
            station = [a, b, c, d]
            vertices.extend(station)
            new_rings.append((angle, station))
        faces = []
        for i in range(54):
            for j in range(4): faces.append((4 * i + j, 4 * i + (j + 1) % 4, 4 * (i + 1) + (j + 1) % 4, 4 * (i + 1) + j))
        faces += [(3, 2, 1, 0), (216, 217, 218, 219)]
        liner = geo.mesh(create_name(liner_name), vertices, faces, original.data.materials[0], original.users_collection[0], original.parent, smooth=True)
        made[liner_name] = liner
        pinned_strip = pin_outer_quads(liner)
        uncut_liner = row(liner)
        tower_name = 'LOD0_StrutTower_' + str(side)
        cut(liner, originals[tower_name])
        centers = endpoint_centers('LOD0_FDamper_' + str(side), 12)
        service = geo.tube('QA_DamperService', centers, .024, None, original.users_collection[0], sides=12)
        temporary.append(service)
        cut(liner, service)
        geo.repair_triangulation(liner)
        trim_only(liner, original.data.materials[0])
        proof['liners'].append({'object': liner_name, 'section_inner_outer_m': [.444, .4465], 'pinned_outer_strip': pinned_strip,
            'angles_degrees': [a for a, _ in new_rings], 'inner_middle_vertices_exact': 106,
            'tower_receiver': tower_name, 'damper_service_centers_m': [list(p) for p in centers],
            'damper_service_radius_m': .024, 'uncut_mesh': uncut_liner})

        wall_name = 'LOD0_InnerWheelTub_F' + symbol
        wall_original = originals[wall_name]
        low, high = sorted((side * (abs(new_rings[0][1][0][0]) - .00375), side * abs(new_rings[0][1][0][0])))
        wall = geo.prism_x(create_name(wall_name), [(r[3][1], r[3][2]) for _, r in new_rings], low, high,
                           bpy.data.materials['Material_Trim'], original.users_collection[0], wall_original.parent)
        made[wall_name] = wall
        axle = geo.tube('QA_AxleService', [(side * (.465 - .016), 1.46, .35), (side * (.465 + .016), 1.46, .35)],
                        .047, None, original.users_collection[0], sides=24)
        temporary.append(axle)
        cut(wall, axle)
        wall_receivers = ['LOD0_StructuralBody', tower_name, 'LOD0_FrontBumper']
        for name in wall_receivers: cut(wall, originals[name])
        passages = []
        for cy in (1.27, 1.63):
            name = 'LOD0_FLowerLink_' + str(side) + str(cy)
            centers = endpoint_centers(name, 8)
            bore = geo.tube('QA_RetainedArmPassage', centers, .021, None, original.users_collection[0], sides=6)
            temporary.append(bore)
            cut(wall, bore)
            passages.append({'arm': name, 'actual_axis_endpoints_m': [list(p) for p in centers], 'radius_m': .021, 'sides': 6})
        geo.repair_triangulation(wall)
        trim_only(wall, bpy.data.materials['Material_Trim'])
        proof['walls'].append({'object': wall_name, 'receivers': wall_receivers, 'wall_x_range_m': [low, high],
                              'arm_passages': passages, 'axle_radius_m': .047})

        for index, wanted in enumerate((15, 45, 75, 105, 135, 165)):
            left = min(range(54), key=lambda i: abs((new_rings[i][0] + new_rings[i + 1][0]) / 2 - wanted))
            a, b = new_rings[left][1], new_rings[left + 1][1]
            p, q = Vector(a[0]), Vector(b[0])
            tangent = (q - p).normalized()
            normal = Vector((0., tangent.z, -tangent.y))
            center = (p + q) / 2
            radial = Vector((0., center.y - 1.46, center.z - .3433))
            if normal.dot(radial) > 0: normal = -normal
            normal.normalize()
            center.x = side * (min(abs(a[1][0]), abs(b[1][0])) - .007)
            name = 'LOD0_LinerRetainer_F' + symbol + str(index)
            retainer = geo.tube(create_name(name), [center + .0015 * normal, center], .004,
                               originals[name].data.materials[0], original.users_collection[0], originals[name].parent, sides=8)
            made[name] = retainer
            old_points = row(originals[name])['vertices']
            old_center = sum((Vector(p) for p in old_points), Vector()) / len(old_points)
            proof['retainers'].append({'object': name, 'liner': liner_name, 'original_center_m': list(old_center),
                'seat_center_m': list(center), 'inward_axis_source': list(normal), 'head_radius_m': .004,
                'head_thickness_m': .0015, 'actual_facet_angles_degrees': [new_rings[left][0], new_rings[left + 1][0]],
                'center_shift_m': (center + normal * .00075 - old_center).length})
    for obj in temporary: dispose(obj)
    proof['native_topology_finish'] = {name: finish_native(obj) for name, obj in made.items()}
    return made, proof
