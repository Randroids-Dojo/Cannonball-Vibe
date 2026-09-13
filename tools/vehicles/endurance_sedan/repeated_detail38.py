"""Current-native repeated detail constructor; caller owns all scene/file IO.

The actual eight-point rib section, six retained fin profile points, affine
carrier selection and native codec operations match the reviewed revision38
recipe. Full original-field, finite-contact, form and motion certificates are
independent validation, never silently replaced by these construction guards.
"""
from copy import deepcopy
import hashlib
import json
import math
import bpy
import numpy as np
from . import geometry, corner_encoding as codec

RIBS = tuple(sorted('LOD0_AirboxRib_' + str(side) + str(i)
                    for side in (-1, 1) for i in range(5)))
FINS = tuple('LOD0_CoolerFin_' + str(i) for i in range(36))
NAMES = tuple(sorted(RIBS + FINS))
RECEIVERS = ('LOD0_Airbox_-1', 'LOD0_Airbox_1', 'LOD0_ChargeCoolingRadiator')
POLICY = {'schema': 'source-repeated-detail38.v1', 'members': list(NAMES),
          'rib_axis': 0, 'rib_section_points': 8, 'rib_original_triangles': 44,
          'rib_replacement_triangles': 28, 'fin_keep': [0, 1, 3, 4, 5, 6],
          'fin_original_triangles': 28, 'fin_replacement_triangles': 20,
          'normal_angle_degrees': .025, 'raw_unit_error': 1e-6,
          'carrier_plane_match_m': 2e-7, 'retained_uv_absolute': 1e-5}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def plain(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if hasattr(value, 'items'):
        return {str(k): plain(v) for k, v in value.items()}
    return [plain(v) for v in value]


def modifiers(obj):
    result = []
    for modifier in obj.modifiers:
        row = {'name': modifier.name, 'type': modifier.type}
        for prop in modifier.bl_rna.properties:
            if prop.is_readonly or prop.identifier in ('name', 'type', 'rna_type'):
                continue
            if prop.type in ('BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'):
                row[prop.identifier] = plain(getattr(modifier, prop.identifier))
        result.append(row)
    return result


def raw(obj):
    mesh = obj.data
    attributes = {}
    for attribute in mesh.attributes:
        values = []
        for value in attribute.data:
            key = next((k for k in ('value', 'vector', 'color', 'uv') if hasattr(value, k)), None)
            require(key is not None, 'Unsupported actual native attribute')
            values.append(plain(getattr(value, key)))
        attributes[attribute.name] = {'type': attribute.data_type, 'domain': attribute.domain, 'values': values}
    return {'name': obj.name, 'vertices': [list(v.co) for v in mesh.vertices],
            'edges': [[list(e.vertices), e.use_edge_sharp] for e in mesh.edges],
            'polygons': [[list(p.vertices), p.material_index, p.use_smooth] for p in mesh.polygons],
            'normals': [list(n.vector) for n in mesh.corner_normals],
            'uvs': {u.name: [list(v.uv) for v in u.data] for u in mesh.uv_layers},
            'attributes': attributes, 'mesh_properties': plain(dict(mesh.items())),
            'properties': plain(dict(obj.items())), 'modifiers': modifiers(obj),
            'material_links': [[s.material.name if s.material else None, s.link] for s in obj.material_slots],
            'parent': obj.parent.name if obj.parent else None,
            'ancestors': ancestors(obj), 'matrix_world': [list(r) for r in obj.matrix_world],
            'matrix_basis': [list(r) for r in obj.matrix_basis],
            'matrix_parent_inverse': [list(r) for r in obj.matrix_parent_inverse],
            'rotation_mode': obj.rotation_mode,
            'collections': sorted(c.name for c in obj.users_collection),
            'visibility': [obj.hide_render, obj.hide_viewport, obj.hide_get()],
            'vertex_groups': [[g.name, g.lock_weight] for g in obj.vertex_groups],
            'vertex_weights': [[[g.group, g.weight] for g in v.groups] for v in mesh.vertices],
            'shape_keys': mesh.shape_keys is not None, 'constraints': len(obj.constraints),
            'animation': obj.animation_data is not None}


def ancestors(obj):
    result = []
    parent = obj.parent
    while parent is not None:
        result.append({'name': parent.name, 'world': [list(r) for r in parent.matrix_world],
                       'basis': [list(r) for r in parent.matrix_basis],
                       'properties': plain(dict(parent.items()))})
        parent = parent.parent
    return result


def evaluated(obj):
    graph = bpy.context.evaluated_depsgraph_get()
    current = obj.evaluated_get(graph)
    mesh = current.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        mesh.calc_loop_triangles()
        return {'vertices': [list(v.co) for v in mesh.vertices],
                'world_vertices': [list(current.matrix_world @ v.co) for v in mesh.vertices],
                'triangles': [list(t.vertices) for t in mesh.loop_triangles],
                'triangle_loops': [list(t.loops) for t in mesh.loop_triangles],
                'normals': [list(n.vector) for n in mesh.corner_normals],
                'uvs': {u.name: [list(v.uv) for v in u.data] for u in mesh.uv_layers},
                'materials': [m.name if m else None for m in mesh.materials],
                'triangle_materials': [t.material_index for t in mesh.loop_triangles]}
    finally:
        current.to_mesh_clear()


def capture(obj):
    return {'raw': raw(obj), 'evaluated': evaluated(obj)}


def _preconditions(objects):
    require(all(name in objects for name in NAMES + RECEIVERS), 'Missing member or finite receiver')
    require(all(objects[name].name == name and objects[name].type == 'MESH'
                for name in NAMES + RECEIVERS), 'Wrong semantic target mapping')
    rows = {name: capture(objects[name]) for name in NAMES + RECEIVERS}
    radiator = rows['LOD0_ChargeCoolingRadiator']['evaluated']
    landing_y = max(p[1] for p in radiator['world_vertices'])
    for name in NAMES:
        obj, row = objects[name], rows[name]
        r, old = row['raw'], row['evaluated']
        require(np.array_equal(np.asarray(obj.matrix_world)[:3, :3], np.eye(3)), 'Changed rest basis: ' + name)
        require(r['parent'] == 'Visual_LOD0' and [a['name'] for a in r['ancestors']] ==
                ['Visual_LOD0', 'Chassis', 'AssetRoot'], 'Changed parent chain: ' + name)
        material = 'Material_Trim' if name in RIBS else 'Material_Metal'
        require(r['material_links'] == [[material, 'DATA']] and old['materials'] == [material], 'Changed material: ' + name)
        require(not r['shape_keys'] and not r['vertex_groups'] and not r['constraints'] and not r['animation'], 'Unexpected deformation: ' + name)
        require(r['properties'].get('maximum_lod') == 0 and r['properties'].get('lod_index') == 0
                and r['properties'].get('uv_meters_per_repeat') == .25, 'Changed source representation: ' + name)
        require(set(old['uvs']) == {'SurfaceMeters'}, 'Changed UV layer domain: ' + name)
        require(all(abs(math.hypot(*n)-1) <= 1e-6 for n in old['normals']), 'Invalid source normal: ' + name)
        if name in RIBS:
            require(len(r['vertices']) == 8 and len(r['polygons']) == 6 and len(old['triangles']) == 44, 'Wrong original rib inventory: ' + name)
            require(len(r['modifiers']) == 1, 'Wrong original rib modifier count')
            m = r['modifiers'][0]
            require(m['name'] == 'Manufactured edge radius' and m['type'] == 'BEVEL'
                    and m['segments'] == 1 and abs(m['width']-.001) <= 1e-10
                    and m['limit_method'] == 'ANGLE' and m['harden_normals']
                    and m['show_render'] and m['show_viewport'], 'Changed original rib bevel')
            dimensions = np.ptp(np.asarray(old['vertices']), axis=0)
            require(np.max(np.abs(dimensions-np.array([.196,.008,.004]))) <= 2e-7, 'Changed rib dimensions')
            extrusion(old)
        else:
            require(not r['modifiers'] and len(r['vertices']) == 16 and len(old['triangles']) == 28, 'Wrong original fin inventory: ' + name)
            # The receiving plane is derived from the actual repaired radiator.
            local_landing = landing_y-float(obj.matrix_world.translation.y)
            fins(old, local_landing)
            require(np.max(np.abs(np.ptp(np.asarray(old['vertices']), axis=0)-np.array([.006,.0045,.201]))) <= 2e-7,
                    'Changed original fin profile dimensions')
    return rows, landing_y


def prepare(specification, *, objects):
    require((bpy.app.version, bpy.app.build_hash.decode()) == ((5, 1, 2), 'ec6e62d40fa9'),
            'Expected pinned native Blender5.1.2')
    declared = specification.get('original_packaging', {}).get('repeated_detail_revision38')
    require(declared == POLICY, 'Missing or unknown repeated detail revision38')
    bpy.context.view_layer.update()
    rows, landing_y = _preconditions(objects)
    return {'schema': 'source-repeated-detail-context38.v1', 'policy': deepcopy(POLICY),
            'before': rows, 'landing_world_y': landing_y,
            'native': {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()}}


def _validate_context(context, expected_digest, objects):
    require(digest(context) == expected_digest and context['schema'] == 'source-repeated-detail-context38.v1'
            and context['policy'] == POLICY, 'Wrong held construction context')
    bpy.context.view_layer.update()
    rows, landing_y = _preconditions(objects)
    require(rows == context['before'] and landing_y == context['landing_world_y'], 'Stale native source context')
    require(context['native'] == {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()}, 'Changed native engine')


def discard(staged):
    collection = staged.get('collection')
    if collection is not None and collection.name in bpy.data.collections:
        for obj in list(collection.objects):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.data.collections.remove(collection)
    staged['collection'] = None


def stage(context, *, expected_context_digest, objects):
    _validate_context(context, expected_context_digest, objects)
    collection = bpy.data.collections.new('PrivateRepeatedDetail38')
    bpy.context.scene.collection.children.link(collection)
    staged = {'collection': collection, 'members': {}, 'context': deepcopy(context),
              'context_digest': expected_context_digest}
    try:
        local = {}
        for name in NAMES:
            obj = objects[name]
            donor, report = _build_member(obj, context['before'][name]['evaluated'], collection=collection,
                landing_y=context['landing_world_y']-float(obj.matrix_world.translation.y))
            staged['members'][name] = donor
            local[name] = report
        # Actual source preimages remain exact while all donors are constructed.
        _validate_context(context, expected_context_digest, objects)
        staged['proof'] = {'schema': 'source-repeated-detail-construction38.v1', 'policy': deepcopy(POLICY),
            'context_digest': expected_context_digest, 'before': deepcopy(context['before']),
            'after_evaluated': {name: evaluated(donor) for name, donor in staged['members'].items()},
            'local': local, 'modifier_removals': list(RIBS),
            'triangles_before': 1448, 'triangles_after': 1000, 'lod0_saving': 448,
            'independent_full_field_finite_motion_validation': 'required separately', 'visual_accepted': False}
        require(sum(len(r['evaluated']['triangles']) for name,r in context['before'].items() if name in NAMES) == 1448,
                'Changed original total')
        require(sum(len(r['triangles']) for r in staged['proof']['after_evaluated'].values()) == 1000, 'Changed candidate total')
        return staged
    except BaseException:
        discard(staged)
        raise


def install(staged, *, expected_stage_digest, objects):
    try:
        require(digest(staged['proof']) == expected_stage_digest, 'Wrong held staged result')
        require(set(staged['members']) == set(NAMES), 'Missing staged member')
        _validate_context(staged['context'], staged['context_digest'], objects)
        require(all(evaluated(staged['members'][name]) == staged['proof']['after_evaluated'][name]
                    for name in NAMES), 'Changed staged native mesh')
    except BaseException:
        discard(staged)
        raise
    old_meshes = {name: objects[name].data for name in NAMES}
    old_modifiers = {name: modifiers(objects[name]) for name in NAMES}
    try:
        for name in NAMES:
            objects[name].data = staged['members'][name].data
            objects[name].modifiers.clear()
        bpy.context.view_layer.update()
        require(all(evaluated(objects[name]) == staged['proof']['after_evaluated'][name]
                    for name in NAMES), 'Installed native result changed')
        result = deepcopy(staged['proof'])
        result['after_native'] = {name: capture(objects[name]) for name in NAMES}
        result['receivers_unchanged'] = all(capture(objects[name]) == staged['context']['before'][name] for name in RECEIVERS)
        require(result['receivers_unchanged'], 'Receiver changed during installation')
        return result
    except BaseException:
        for name in NAMES:
            obj = objects[name]
            obj.data = old_meshes[name]
            obj.modifiers.clear()
            for row in old_modifiers[name]:
                modifier = obj.modifiers.new(row['name'], row['type'])
                for key, value in row.items():
                    if key not in ('name', 'type'):
                        setattr(modifier, key, value)
        bpy.context.view_layer.update()
        raise
    finally:
        discard(staged)


def apply(specification, *, objects):
    context = prepare(specification, objects=objects)
    staged = stage(context, expected_context_digest=digest(context), objects=objects)
    return install(staged, expected_stage_digest=digest(staged['proof']), objects=objects)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def unit(v):
    v = np.asarray(v, dtype=float)
    length = float(np.linalg.norm(v))
    require(math.isfinite(length) and length > 1e-12, "Invalid finite vector")
    return v / length

def plane(points):
    points = np.asarray(points)
    n = unit(np.cross(points[1]-points[0], points[2]-points[0]))
    return n, float(n @ points[0])

def bary(p, ps):
    a, b = ps[1]-ps[0], ps[2]-ps[0]
    d = p-ps[0]
    aa, ab, bb = float(a@a), float(a@b), float(b@b)
    determinant = aa*bb-ab*ab
    require(determinant > 0, "Degenerate affine carrier")
    v = (bb*float(a@d)-ab*float(b@d))/determinant
    w = (aa*float(b@d)-ab*float(a@d))/determinant
    return np.array([1-v-w, v, w])

def area(poly):
    return sum(float(np.linalg.norm(np.cross(poly[i]-poly[0], poly[i+1]-poly[0])))*.5
               for i in range(1, len(poly)-1))

def hull(points):
    out = []
    for values in (sorted(set(map(tuple, points))), sorted(set(map(tuple, points)), reverse=True)):
        chain = []
        for p in values:
            while len(chain) > 1:
                a, b = chain[-2:]
                cross = (b[0]-a[0])*(p[1]-b[1])-(b[1]-a[1])*(p[0]-b[0])
                if cross > 1e-7*math.dist(a, p):
                    break
                chain.pop()
            chain.append(p)
        out += chain[:-1]
    return out

def extrusion(row):
    vertices = np.asarray(row['vertices'])
    low, high = float(vertices[:, 0].min()), float(vertices[:, 0].max())
    middle = (low+high)/2
    points = []
    for face in row['triangles']:
        for i, j in zip(face, face[1:]+face[:1]):
            a, b = vertices[i], vertices[j]
            if a[0] != b[0] and min(a[0], b[0]) <= middle <= max(a[0], b[0]):
                p = a+(b-a)*(middle-a[0])/(b[0]-a[0])
                if not any(math.dist(p[1:], q) < 1e-9 for q in points):
                    points.append(p[1:].tolist())
    profile = hull(points)
    require(len(profile) == 8, 'Missing actual eight-point long profile')
    vertices = [[x, y, z] for x in (low, high) for y, z in profile]
    faces = [list(reversed(range(8))), list(range(8, 16))]
    faces += [[i, (i+1)%8, (i+1)%8+8, i+8] for i in range(8)]
    return vertices, faces, {'kind': 'end_treatment', 'axis': 0, 'low': low, 'high': high,
                              'actual_middle_profile': profile, 'original_triangles': 44}

def fins(row, landing_y):
    points = row['vertices']
    require(len(points) == 16 and len(row['triangles']) == 28, 'Fin original inventory')
    require(all(points[i][:2] == points[i+8][:2] for i in range(8)), 'Fin paired ring correspondence')
    keep = [0, 1, 3, 4, 5, 6]
    require(min(p[1] for p in points) == landing_y, 'Changed actual fin landing')
    vertices = [points[k+i] for k in (0, 8) for i in keep]
    faces = [list(reversed(range(6))), list(range(6, 12))]
    faces += [[i, (i+1)%6, (i+1)%6+6, i+6] for i in range(6)]
    return vertices, faces, {'kind': 'fin', 'retained_original_vertices': keep+[i+8 for i in keep],
                             'retained_whole_landing': [points[i] for i in (0, 1, 8, 9)],
                             'new_taper_polygon_indices': [3, 7], 'original_triangles': 28}

def _build_member(obj, old, *, collection, landing_y):
    name = obj.name
    require(np.array_equal(np.asarray(obj.matrix_world)[:3, :3], np.eye(3)), 'Expected current rigid translated rest basis: ' + name)
    require(len(obj.data.materials) == 1, 'Original single material changed: ' + name)
    require(abs(max((abs(math.hypot(*n) - 1) for n in old['normals']))) <= 1e-06, 'Original raw normal')
    if name in RIBS:
        vertices, faces, domain = extrusion(old)
    elif name in FINS:
        vertices, faces, domain = fins(old, landing_y)
    else:
        raise ValueError('Unowned semantic mesh')
    require(len(old['triangles']) == domain['original_triangles'], 'Original count changed')
    out = geometry.mesh('PrivateReserve_' + name, vertices, faces, obj.data.materials[0], collection, obj.parent)
    out.matrix_world = obj.matrix_world.copy()
    data = out.data
    for u in list(data.uv_layers):
        if u.name not in old['uvs']:
            data.uv_layers.remove(u)
    for name_uv in old['uvs']:
        if name_uv not in data.uv_layers:
            data.uv_layers.new(name=name_uv)
    source_points = np.asarray(old['vertices'])
    source_faces = [source_points[t] for t in old['triangles']]
    planes = [plane(p) for p in source_faces]
    normals = []
    carriers = []
    for face in data.polygons:
        ps = np.asarray([list(data.vertices[v].co) for v in face.vertices])
        normal = np.asarray(list(face.normal))
        matches = [i for i, (n, d) in enumerate(planes) if float(n @ normal) > 0.99985 and max((abs(float(n @ p) - d) for p in ps)) <= 2e-07]
        carrier = max(matches, key=lambda i: area(source_faces[i]), default=None)
        carriers.append({'polygon': face.index, 'source_triangles': matches, 'source_carrier': carrier, 'domain': 'original_source_field' if carrier is not None else 'new_physical_facet'})
        for loop_index in face.loop_indices:
            vertex_index = data.loops[loop_index].vertex_index
            p = np.array(data.vertices[vertex_index].co)
            if carrier is not None:
                w = bary(p, source_faces[carrier])
                ls = old['triangle_loops'][carrier]
                target = unit(w @ np.array([old['normals'][i] for i in ls])).tolist()
                for uvname, values in old['uvs'].items():
                    data.uv_layers[uvname].data[loop_index].uv = w @ np.array([values[i] for i in ls])
            else:
                target = normal.tolist()
                axis = int(np.argmax(abs(normal)))
                uv = [p[k] / 0.25 for k in range(3) if k != axis]
                for uvname in old['uvs']:
                    data.uv_layers[uvname].data[loop_index].uv = uv
            normals.append((loop_index, tuple(target)))
    normals = [v for _, v in sorted(normals)]
    encoding = codec.encode(data, normals)
    new = evaluated(out)
    new['name'] = obj.name
    counts = geometry.evaluated_counts(out)
    bad = ('nonmanifold_edges', 'degenerate_triangles', 'duplicate_faces',
           'triangulated_nonmanifold_edges', 'triangulated_duplicate_faces',
           'nonunit_corner_normals', 'zero_corner_normals', 'nonfinite_corner_normals')
    require(encoding['passed'] and not any(counts[k] for k in bad), 'Invalid native candidate')
    old_points, new_points = np.asarray(old['vertices']), np.asarray(new['vertices'])
    require(np.array_equal(old_points.min(0), new_points.min(0))
            and np.array_equal(old_points.max(0), new_points.max(0)), 'Changed native extrema')
    volume = sum(float(np.dot(new_points[a], np.cross(new_points[b], new_points[c])))
                 for a, b, c in new['triangles']) / 6
    require(volume > 0, 'Wrong solid orientation')
    expected = 28 if obj.name in RIBS else 20
    require(len(new['triangles']) == expected, 'Unexpected constructed count')
    if obj.name in FINS:
        old_landing = sorted(tuple(p) for p in old['vertices'] if p[1] == landing_y)
        new_landing = sorted(tuple(p) for p in new['vertices'] if p[1] == landing_y)
        require(old_landing == new_landing and len(new_landing) == 4, 'Changed complete landing')
    return out, {'domain': domain, 'carriers': carriers, 'encoding': encoding,
                 'counts': counts, 'signed_volume_m3': volume,
                 'triangles_before': len(old['triangles']), 'triangles_after': len(new['triangles'])}
