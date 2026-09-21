"""Private reusable coherent seat construction; never saves or renders a scene.

prepare_seat leaves originals untouched and returns staged replacements. Callers
supply the project's exact self predicate and the reviewed native normal encoder.
No report, checkpoint, hash or mesh index selects the construction.
"""
from collections import Counter
from types import SimpleNamespace
import math

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

from endurance_sedan import geometry, boolean_surface, surface_normals


COUNTERS = ('nonmanifold_edges', 'duplicate_faces', 'degenerate_faces',
            'degenerate_triangles', 'triangulated_nonmanifold_edges',
            'triangulated_duplicate_faces')
FOAM_PARTS = ('BackInsert', 'BackBolster-1', 'BackBolster1',
              'ThighBolster-1', 'ThighBolster1', 'CushionInsert')


def _native(obj):
    if obj.modifiers:
        obj = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = obj.data
    mesh.calc_loop_triangles()
    return {'name': obj.name,
            'vertices': [list(obj.matrix_world @ v.co) for v in mesh.vertices],
            'triangles': [list(t.vertices) for t in mesh.loop_triangles]}


def _check(obj, exact_scan):
    counts = geometry.evaluated_counts(obj)
    if any(counts[k] for k in COUNTERS):
        raise ValueError(f'Invalid closed seat surface {obj.name}: {counts}')
    proof = exact_scan(_native(obj))
    if proof['status'] != 'passed' or proof['bad_pairs']:
        raise ValueError(f'Self-intersecting seat surface {obj.name}: {proof}')
    return {'counts': counts, 'self': proof}


def _reference(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return (obj.name, [v.co.copy() for v in mesh.vertices],
            [tuple(t.vertices) for t in mesh.loop_triangles],
            [[mesh.corner_normals[i].vector.copy() for i in t.loops]
             for t in mesh.loop_triangles])


def _triangulate(obj):
    """Freeze the actual evaluated diagonals before every Boolean operation."""
    old = obj.data
    old.calc_loop_triangles()
    triangles = list(old.loop_triangles)
    normals = [tuple(old.corner_normals[i].vector) for t in triangles for i in t.loops]
    uvs = {layer.name: [tuple(layer.data[i].uv) for t in triangles for i in t.loops]
           for layer in old.uv_layers}
    materials = [old.polygons[t.polygon_index].material_index for t in triangles]
    smooth = [old.polygons[t.polygon_index].use_smooth for t in triangles]
    mesh = bpy.data.meshes.new(obj.name + '_ActualTriangles')
    mesh.from_pydata([tuple(v.co) for v in old.vertices], [],
                     [tuple(t.vertices) for t in triangles])
    mesh.update()
    for material in old.materials:
        mesh.materials.append(material)
    for face, index, flag in zip(mesh.polygons, materials, smooth):
        face.material_index, face.use_smooth = index, flag
    for name, values in uvs.items():
        layer = mesh.uv_layers.new(name=name)
        for item, value in zip(layer.data, values):
            item.uv = value
    mesh.normals_split_custom_set(normals)
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def _boolean(first, second, operation, exact_scan):
    _triangulate(first)
    _triangulate(second)
    bpy.context.view_layer.objects.active = first
    mod = first.modifiers.new('Coherent seat construction', 'BOOLEAN')
    mod.operation, mod.solver, mod.object = operation, 'EXACT', second
    bpy.ops.object.modifier_apply(modifier=mod.name)
    first.data.update()
    before = _native(first)
    if geometry.evaluated_counts(first)['degenerate_triangles']:
        geometry.repair_triangulation(first)
    if not first.data.has_custom_normals:
        first.data.normals_split_custom_set([tuple(n.vector) for n in first.data.corner_normals])
    repair = boolean_surface.repair(first, exact_scan, geometry.evaluated_counts,
                                    allow_sliver_flip=True)
    after = _native(first)
    # Existing diagnosed repairs may retessellate but may not move a vertex.
    if sorted(map(tuple, before['vertices'])) != sorted(map(tuple, after['vertices'])):
        a, b = np.array(before['vertices']), np.array(after['vertices'])
        distances = np.linalg.norm(a[:, None] - b[None, :], axis=2)
        if max(float(distances.min(0).max()), float(distances.min(1).max())) > 1e-6:
            raise ValueError('Seat Boolean repair exceeds unchanged geometry guard')
    return {'operation': operation, 'operand': second.name, 'repair': repair,
            'quality': _check(first, exact_scan)}


class _CaptureTargets:
    def __init__(self, mesh):
        self.mesh, self.targets = mesh, None

    def __getattr__(self, name):
        return getattr(self.mesh, name)

    def normals_split_custom_set(self, values):
        self.targets = [tuple(v) for v in values]


def _finish(obj, references, encode, exact_scan):
    capture = _CaptureTargets(obj.data)
    ownership = surface_normals.restore_owned(SimpleNamespace(data=capture), references)
    if capture.targets is None:
        raise ValueError('Missing declared corner field')
    # The form has an explicitly authored new interpolation field. Encoding,
    # not comparison with the previous seat's interior field, is guarded here.
    encoding = encode(obj.data, capture.targets)
    if not encoding['passed'] or encoding['maximum_native_decoded_degrees'] > .025:
        raise ValueError(f'Native seat encoding failed: {encoding}')
    invalid = [i for i, n in enumerate(obj.data.corner_normals)
               if not all(math.isfinite(v) for v in n.vector)
               or abs(math.hypot(*n.vector) - 1) > 1e-6]
    if invalid:
        raise ValueError(f'Invalid raw native seat normals: {invalid}')
    return {'ownership': ownership, 'encoding': encoding,
            'quality': _check(obj, exact_scan)}


def _mesh(name, vertices, faces, material, staged):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([[float(x) for x in v] for v in vertices], [], faces)
    mesh.update()
    edit = bmesh.new()
    edit.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(edit, faces=list(edit.faces))
    edit.to_mesh(mesh)
    edit.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    staged.append(obj)
    mesh.materials.append(material)
    geometry.project_uv(obj)
    return obj


def _clone(original, materials, staged):
    if max(abs(original.matrix_world[i][j] - Matrix.Identity(4)[i][j])
           for i in range(4) for j in range(4)) > 1e-9:
        raise ValueError('Seat construction expects frozen world-space carriers')
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(original.evaluated_get(deps),
                                          preserve_all_data_layers=True, depsgraph=deps)
    old = list(mesh.materials)
    indices = [materials.index(old[p.material_index]) for p in mesh.polygons]
    mesh.materials.clear()
    for material in materials:
        mesh.materials.append(material)
    for polygon, index in zip(mesh.polygons, indices):
        polygon.material_index = index
    obj = bpy.data.objects.new('STAGED_' + original.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    staged.append(obj)
    return obj


def _bore(post, low, high, material, staged):
    points = np.array(_native(post)['vertices'])
    if len(points) != 16:
        raise ValueError('Expected original two eight-corner headrest-post rings')
    center0, center1 = points[:8].mean(0), points[8:].mean(0)
    length = float(np.linalg.norm(center1 - center0))
    axis = (center1 - center0) / length
    radial = points[:8] - center0
    radial -= np.outer(radial @ axis, axis)
    distances = []
    for a, b in zip(radial, np.roll(radial, -1, axis=0)):
        normal = np.cross(b-a, axis)
        normal /= np.linalg.norm(normal)
        distances.append(abs(float(normal @ a)))
    scale = 1 + .0012 / min(distances)
    vertices = [center0 + axis*t + r*scale for t in (low, high) for r in radial]
    faces = [tuple(reversed(range(8))), tuple(range(8, 16))]
    faces += [(i, (i+1) % 8, (i+1) % 8 + 8, i+8) for i in range(8)]
    obj = _mesh('STAGED_SeatPostBore', vertices, faces, material, staged)
    return obj, {'axis': axis.tolist(), 'center0': center0.tolist(),
                 'center1': center1.tolist(), 'length_m': length,
                 'bore_interval_m': [low, high], 'radial_scale': scale,
                 'minimum_nominal_normal_side_clearance_m': .0012}


def _pouch(backing, old, material, staged):
    row = _native(backing)
    triangles = np.array(row['vertices'])[row['triangles']]
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    areas = np.linalg.norm(normals, axis=1)
    normals /= areas[:, None]
    expected = np.array([0., -math.cos(math.radians(18)), -math.sin(math.radians(18))])
    ids = np.flatnonzero(normals @ expected > 1-1e-8)
    if not len(ids):
        raise ValueError('Front pouch lacks original raked rear mounting face')
    index = int(max(ids, key=lambda i: areas[i]))
    normal, constant = normals[index], float(normals[index] @ triangles[index, 0])
    points = np.array(_native(old)['vertices'])
    cx = float((points[:, 0].min()+points[:, 0].max())/2)
    # Existing inspected nominal envelope, now formed as a real hollow pouch.
    width, bottom, top, wall, depth = .327, .6175, .8925, .0015, .018
    def transform(p):
        x, y, z = p
        x += cx
        return [x, (constant-normal[0]*x-normal[2]*z)/normal[1]+y, z]
    def ring(x0, x1, y0, y1, z):
        return [(x0,y0,z), (x1,y0,z), (x1,y1,z), (x0,y1,z)]
    vertices = ring(-width/2,width/2,-depth,0,bottom) + ring(-width/2,width/2,-depth,0,top)
    vertices += ring(-width/2+wall,width/2-wall,-depth+wall,-wall,bottom+wall)
    vertices += ring(-width/2+wall,width/2-wall,-depth+wall,-wall,top)
    faces = [(3,2,1,0), (8,9,10,11)]
    for i in range(4):
        j = (i+1) % 4
        faces += [(i,j,j+4,i+4), (i+8,i+12,j+12,j+8), (i+4,j+4,j+12,i+12)]
    obj = _mesh('STAGED_FittedMapPouch', [transform(p) for p in vertices], faces, material, staged)
    return obj, {'actual_rear_normal': normal.tolist(), 'plane_constant': constant,
                 'original_face': index, 'width_m': width, 'world_height_m': top-bottom,
                 'world_y_depth_m': depth, 'wall_m': wall}


def _switch_pad(switch, frame, material, staged):
    s, f = _native(switch), _native(frame)
    sign = 1 if np.mean(np.array(s['vertices'])[:, 0]) < 0 else -1
    sp, fp = np.array(s['vertices']), np.array(f['vertices'])
    sx, fx = float((sp[:,0]*sign).max()), float((fp[:,0]*sign).min())
    if fx <= sx:
        raise ValueError('Switch and seat frame do not have an ordered mounting gap')
    ids = [i for i, t in enumerate(s['triangles']) if all(abs(sp[j,0]*sign-sx)<1e-7 for j in t)]
    if not ids:
        raise ValueError('Switch has no actual inner mounting cap')
    old = sorted({j for i in ids for j in s['triangles'][i]})
    mapping = {v:i for i,v in enumerate(old)}
    points = [s['vertices'][i] for i in old]
    count = len(points)
    faces = [tuple(mapping[j] for j in s['triangles'][i]) for i in ids]
    edges = Counter((a,b) for face in faces for a,b in zip(face, face[1:]+face[:1]))
    boundary = [(a,b) for (a,b) in edges if (b,a) not in edges]
    vertices = points + [[fx*sign, p[1], p[2]] for p in points]
    faces += [tuple(i+count for i in reversed(face)) for face in faces[:]]
    faces += [(a,b,b+count,a+count) for a,b in boundary]
    obj = _mesh('STAGED_SeatSwitchMount', vertices, faces, material, staged)
    return obj, {'coordinate_sign': sign, 'outer_plane_x': sx*sign,
                 'inner_plane_x': fx*sign, 'thickness_m': fx-sx,
                 'complete_original_switch_cap_triangles': len(ids)}


def _hidden_seam(seam, backing):
    row = _native(backing)
    points = np.array(row['vertices'])
    triangles = points[row['triangles']]
    normals = np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0])
    normals /= np.linalg.norm(normals, axis=1)[:,None]
    constants = np.einsum('ij,ij->i', normals, triangles[:,0])
    residual = float((points @ normals.T - constants).max())
    hidden = float((np.array(_native(seam)['vertices']) @ normals.T - constants).max())
    if residual > 1e-6:
        raise ValueError(f'Backing lacks the declared convex bound: {residual}')
    return {'carrier_own_plane_residual_m': residual, 'minimum_interior_margin_m': -hidden,
            'wholly_hidden': hidden < -1e-6,
            'action': 'remove_proved_hidden_thread' if hidden < -1e-6 else 'retain_original_thread_for_assembly_fit'}


def prepare_seat(prefix, *, exact_scan, encode):
    """Return (replacements_by_semantic_name, engineering), originals unchanged.

    Prefix is FrontL, FrontR, RearL or RearR. Rear seats retain their existing
    absence of an electric switch/map pouch. Rail bases, cushion frames,
    headrest posts, all remaining piping/stitch objects and hardpoints stay put.
    """
    if prefix not in ('FrontL', 'FrontR', 'RearL', 'RearR'):
        raise ValueError('Unknown authored outboard seat')
    front = prefix.startswith('Front')
    name = lambda part: 'LOD0_' + prefix + part
    required = list(FOAM_PARTS) + ['BackShell','CushionFrame','Headrest',
               'HeadrestPost-1','HeadrestPost1','CushionSeam0']
    if front:
        required += ['MapPocket','SeatSwitch']
    originals = {part: bpy.data.objects[name(part)] for part in required}
    for obj in originals.values():
        if obj.type != 'MESH':
            raise ValueError('Seat input is not a mesh')
    mats = {key: bpy.data.materials['Material_' + key]
            for key in ('Leather','Trim','Fabric','Rubber')}
    staged, result = [], {}
    report = {'seat': prefix, 'operations': [], 'socket_parameters': [],
              'removed_originals': [name(p) for p in FOAM_PARTS] + [name('CushionSeam0')],
              'replaced_originals': [name('BackShell'), name('Headrest')],
              'new_semantic_objects': [name('JoinedUpholstery')],
              'retained_mounts': [name(p) for p in ('CushionFrame','HeadrestPost-1','HeadrestPost1')],
              'source_field_policy': 'New authored joined-leather interpolation; strict target-to-native .025 degree guard remains.'}
    try:
        # Validate the finite hidden deletion before staging the new construction.
        report['hidden_seam'] = _hidden_seam(originals['CushionSeam0'], originals['BackShell'])
        if not report['hidden_seam']['wholly_hidden']:
            report['removed_originals'].remove(name('CushionSeam0'))
            report['retained_mounts'].append(name('CushionSeam0'))
        objects = {p: _clone(originals[p], [mats['Leather'],mats['Trim']], staged)
                   for p in list(FOAM_PARTS)+['BackShell','CushionFrame']}
        references = {p: _reference(obj) for p,obj in objects.items()}
        foam = objects[FOAM_PARTS[0]]
        for part in FOAM_PARTS[1:]:
            report['operations'].append(_boolean(foam, objects[part], 'UNION', exact_scan))
        for part in ('BackShell','CushionFrame'):
            report['operations'].append(_boolean(foam, objects[part], 'DIFFERENCE', exact_scan))
        # All exterior foam is leather, including its hidden fitted carrier seat.
        for face in foam.data.polygons:
            face.material_index = 0
        foam.data.materials.clear()
        foam.data.materials.append(mats['Leather'])
        result[name('JoinedUpholstery')] = foam
        result[name('BackShell')] = _clone(originals['BackShell'], [mats['Trim']], staged)
        result[name('Headrest')] = _clone(originals['Headrest'], [mats['Leather']], staged)
        attachment_refs = {key: [_reference(obj)] for key,obj in result.items() if obj is not foam}
        for side in (-1,1):
            post = originals['HeadrestPost'+str(side)]
            points = np.array(_native(post)['vertices'])
            length = float(np.linalg.norm(points[8:].mean(0)-points[:8].mean(0)))
            for part, low, high, material in [('BackShell',0.,length+.02,mats['Trim']),
                                             ('Headrest',-.02,length,mats['Leather'])]:
                bore, params = _bore(post, low, high, material, staged)
                report['operations'].append(_boolean(result[name(part)], bore, 'DIFFERENCE', exact_scan))
                report['socket_parameters'].append({'post': name('HeadrestPost'+str(side)),
                                                    'target': name(part), 'parameters': params})
        if front:
            pouch, info = _pouch(objects['BackShell'], originals['MapPocket'], mats['Fabric'], staged)
            result[name('MapPocket')] = pouch
            report['pouch_parameters'] = info
            report['replaced_originals'].append(name('MapPocket'))
            pad, info = _switch_pad(originals['SeatSwitch'], originals['CushionFrame'], mats['Rubber'], staged)
            result[name('SeatSwitchMount')] = pad
            report['switch_pad_parameters'] = info
            report['new_semantic_objects'].append(name('SeatSwitchMount'))
        report['final'] = {}
        for key,obj in result.items():
            refs = [references[p] for p in FOAM_PARTS] if obj is foam else attachment_refs.get(key, [])
            report['final'][key] = _finish(obj, refs, encode, exact_scan)
            if len(obj.data.materials) != 1:
                raise ValueError('Seat batching requires one material per component')
            obj['coherent_seat_prefix'] = prefix
        changed = report['removed_originals'] + report['replaced_originals']
        report['before_triangles'] = {key: len(_native(bpy.data.objects[key])['triangles']) for key in changed}
        report['after_triangles'] = {key: len(_native(obj)['triangles']) for key,obj in result.items()}
        report['triangle_delta'] = sum(report['after_triangles'].values()) - sum(report['before_triangles'].values())
        report['status'] = 'prepared_native_valid_requires_assembly_fit'
        keep = {obj.as_pointer() for obj in result.values()}
        for obj in staged:
            if obj.as_pointer() not in keep:
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        return result, report
    except BaseException as error:
        error.seat_report = report
        error.seat_witnesses = {obj.name: _native(obj) for obj in staged if obj.name in bpy.data.objects}
        for obj in staged:
            if obj.name in bpy.data.objects:
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        raise
