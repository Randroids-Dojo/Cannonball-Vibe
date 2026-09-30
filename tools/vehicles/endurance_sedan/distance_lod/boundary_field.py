"""Bounded original upper-A field and exact windshield seal for distant LODs."""
import json
import math

import bpy


def capture_upper(source, feature):
    if source.name not in {'LOD0_PillarA_L', 'LOD0_PillarA_R'} or source.parent is None or source.parent.name != 'Visual_LOD0' or source.modifiers:
        raise ValueError('Exact native original A-pillar source required')
    if [m.name if m else None for m in source.data.materials] != ['Material_Paint']:
        raise ValueError('A-pillar material mismatch')
    if abs(source.get('formed_return_m', -1.) - .018) > 1e-9 or abs(source.get('structural_joint_plane_z_m', -1.) - 1.05) > 1e-6:
        raise ValueError('Missing declared formed-return source construction')
    data = source.data
    if data.uv_layers.active is None:
        raise ValueError('Missing original A-pillar UV')
    data.calc_loop_triangles()
    sign = -1 if source.name.endswith('_L') else 1
    world = {v.index: source.matrix_world @ v.co for v in data.vertices}
    seeds = []
    for triangle in data.loop_triangles:
        points = [world[i] for i in triangle.vertices]
        normal = (points[1] - points[0]).cross(points[2] - points[0])
        if normal.length <= 1e-12:
            raise ValueError('Degenerate original A-pillar triangle')
        normal.normalize()
        if data.polygons[triangle.polygon_index].use_smooth and min(p.z for p in points) >= 1.24 and sign * normal.x >= .8:
            seeds.append(triangle)
    if not seeds:
        raise ValueError('Empty complete outward upper-A source domain')
    protected = {i for t in seeds for i in t.vertices}
    rows = []
    for triangle in data.loop_triangles:
        if not all(i in protected for i in triangle.vertices):
            continue
        points = [data.vertices[i].co.copy() for i in triangle.vertices]
        normals = [data.corner_normals[i].vector.copy() for i in triangle.loops]
        for n in normals:
            feature._angle(n, n)
        rows.append({'points': points, 'key': feature._key(points), 'normals': normals,
            'uv': [data.uv_layers.active.data[i].uv.copy() for i in triangle.loops],
            'smooth': data.polygons[triangle.polygon_index].use_smooth})
    if len({r['key'] for r in rows}) != len(rows):
        raise ValueError('Ambiguous upper-A original triangle inventory')
    return {'triangles': rows, 'points': {tuple(data.vertices[i].co) for i in protected},
        'matrix': tuple(tuple(r) for r in source.matrix_world), 'seed_count': len(seeds),
        'initial': len(data.loop_triangles), 'source_name': source.name,
        'domain': {'minimum_world_Z_m': 1.24, 'minimum_outward_geometric_X': .8, 'source_smooth_seed': True}}


def build_pillar(source, parent, collection, *, feature, encoder, paint, selective, geometry, shell_certificate):
    if parent is None or parent.name not in {'Visual_LOD1', 'Visual_LOD2'}:
        raise ValueError('Upper-A distant policy requires an actual lowerLOD parent')
    reference = capture_upper(source, feature)
    adapter = object.__new__(feature.Adapter)
    adapter.reference, adapter.existing, adapter.encoder = reference, paint, encoder
    attempts = []
    for ratio in selective.ratios(.065):
        obj = source.copy()
        obj.data = source.data.copy()
        obj.name = 'LOD' + parent.name[-1] + '_ProtectedUpperA_' + source.name[-1]
        collection.objects.link(obj)
        world = source.matrix_world.copy()
        obj.parent, obj.matrix_world = parent, world
        bpy.context.view_layer.update()
        item, accepted = {'ratio': ratio}, False
        try:
            if feature.verify(obj, reference)['maximum_native_normal_angle_degrees'] != 0.:
                raise ValueError('Source copy changed the upper-A field')
            protection = adapter.prepare(obj)
            if ratio < 1:
                modifier = obj.modifiers.new('Protected original upper-A return', 'DECIMATE')
                modifier.ratio = adapter.configure(obj, modifier, protection, ratio)
                modifier.use_collapse_triangulate = True
                item['actual_native_ratio'] = modifier.ratio
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            if obj.data.validate(clean_customdata=False):
                raise ValueError('Native validation changed the upper-A geometry')
            obj.data.update()
            item['field'] = adapter.restore(obj, protection)
            geometry.repair_triangulation(obj)
            item['final_field'] = feature.verify(obj, reference)
            item['counts'] = geometry.evaluated_counts(obj)
            if any(item['counts'][k] for k in ('nonmanifold_edges', 'degenerate_triangles', 'duplicate_faces',
                    'triangulated_nonmanifold_edges', 'triangulated_duplicate_faces', 'zero_corner_normals', 'nonfinite_corner_normals', 'nonunit_corner_normals')):
                raise ValueError('Invalid upper-A topology/raw normal')
            item['self'] = shell_certificate(selective.native_row(obj))
            if item['self']['status'] != 'passed':
                raise ValueError('Upper-A indexed shell self failure')
            item['status'], accepted = 'passed', True
        except Exception as error:
            item.update(status='rejected', failure=type(error).__name__ + ': ' + str(error))
        attempts.append(item)
        if accepted:
            obj['source_components'], obj['lod_index'] = json.dumps([source.name]), int(parent.name[-1])
            return obj, {'source_component': source.name, 'domain': reference['domain'], 'source_triangles': reference['initial'],
                'protected_complete_triangles': len(reference['triangles']), 'source_seed_faces': reference['seed_count'],
                'attempts': attempts, 'final_triangles': len(obj.data.loop_triangles), 'original_reference': reference,
                'scope': 'Original upper formed-return geometry/field, not generic paint retention. Separate final native mesh; do not rebake.'}
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    raise ValueError('No valid upper-A native candidate: ' + str(attempts))


def build_seal(source, parent, collection, *, raw_fields, shell_certificate, native_row):
    if source.name != 'LOD0_WindshieldSeal' or source.parent is None or source.parent.name != 'Visual_LOD0' or source.modifiers:
        raise ValueError('Exact native windshield-seal source required')
    if parent is None or parent.name not in {'Visual_LOD1', 'Visual_LOD2'} or [m.name if m else None for m in source.data.materials] != ['Material_Rubber']:
        raise ValueError('Windshield-seal parent/material mismatch')
    before = raw_fields(source)
    obj = source.copy()
    obj.data = source.data.copy()
    obj.name = 'LOD' + parent.name[-1] + '_OriginalWindshieldSeal'
    collection.objects.link(obj)
    world = source.matrix_world.copy()
    obj.parent, obj.matrix_world = parent, world
    obj['source_components'], obj['lod_index'] = json.dumps([source.name]), int(parent.name[-1])
    bpy.context.view_layer.update()
    after = raw_fields(obj)
    if any(before[k] != after[k] for k in before if k != 'parent'):
        raise ValueError('Exact original seal field/physical copy changed')
    row = native_row(obj)
    if any(abs(math.hypot(*n) - 1.) > 1e-6 or not all(math.isfinite(v) for v in n) for face in row['normals'] for n in face):
        raise ValueError('Original seal raw-normal invalid')
    proof = shell_certificate(row)
    if proof['status'] != 'passed':
        raise ValueError('Original seal indexed shell invalid')
    return obj, {'source_component': source.name, 'triangles': len(row['triangles']), 'source_field_copy_exact': True,
        'self': proof, 'scope': 'Entire original64-triangle narrow seal, exact field/UV/topology/physical envelope. Separate final native mesh.'}
