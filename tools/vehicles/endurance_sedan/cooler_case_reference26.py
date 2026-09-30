"""New authored tank chamfer field; no geometry edits or source/report IO.

The actual pre-socket receiver supplies the six broad planes and their inset
boundaries. Only complete original chamfer/corner faces receive the new field.
Broad panel and socket native codes are retained exactly.
"""
import math

import bpy
from mathutils import Vector


GUARD = 1e-6


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def unit(a):
    length = math.hypot(*a)
    if not math.isfinite(length) or length <= 0:
        raise ValueError('Invalid authored tank field vector')
    return tuple(x/length for x in a)


def angle(a, b):
    return math.degrees(math.atan2(math.hypot(*cross(a, b)), dot(a, b)))


def normal(points):
    return unit(cross(sub(points[1], points[0]), sub(points[2], points[0])))


def validate_row(row):
    vertices, triangles = row['vertices'], row['triangles']
    if not vertices or not triangles:
        raise ValueError('Missing receiver or socket surface')
    if any(len(v) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in v) for v in vertices):
        raise ValueError('Invalid receiver or socket vertex')
    for tri in triangles:
        if len(tri) != 3 or len(set(tri)) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in tri):
            raise ValueError('Invalid receiver or socket triangle')
        normal([vertices[i] for i in tri])


def reference_field(reference):
    """Derive the round-box direction domain from actual broad panel facets."""
    validate_row(reference)
    points = reference['vertices']
    outer = [[min(p[a] for p in points), max(p[a] for p in points)] for a in range(3)]
    broad = {(a, side): [] for a in range(3) for side in range(2)}
    for index, tri in enumerate(reference['triangles']):
        ps = [points[i] for i in tri]
        n = normal(ps)
        owners = [(a, side) for a in range(3) for side in range(2)
                  if max(abs(p[a]-outer[a][side]) for p in ps) <= GUARD
                  and n[a] * (1 if side else -1) > .99999]
        if len(owners) > 1:
            raise ValueError('Ambiguous broad panel reference')
        if owners:
            broad[owners[0]].append(index)
    if any(not indices for indices in broad.values()):
        raise ValueError('Receiver lacks one of six actual broad panel planes')
    inner = []
    for axis in range(3):
        tangent = [points[v][axis] for (a, _), tris in broad.items() if a != axis
                   for t in tris for v in reference['triangles'][t]]
        bounds = [min(tangent), max(tangent)]
        if not outer[axis][0] + GUARD < bounds[0] < bounds[1] < outer[axis][1] - GUARD:
            raise ValueError('Receiver does not have a finite inset chamfer boundary')
        inner.append(bounds)
    return outer, inner, {f'{a}:{side}': value for (a, side), value in broad.items()}


def field(point, inner):
    direction = [p-lo if p < lo else p-hi if p > hi else 0. for p, (lo, hi) in zip(point, inner)]
    return unit(direction)


def fingerprint(mesh):
    """Exact native scope snapshot; only custom-normal shorts may change."""
    attrs = {}
    for attr in mesh.attributes:
        if attr.name == 'custom_normal':
            continue
        values = []
        for item in attr.data:
            value = next((getattr(item, key) for key in ('value', 'vector', 'color') if hasattr(item, key)), None)
            if value is None:
                raise ValueError('Unsupported mesh attribute in conservation guard')
            values.append(value if isinstance(value, (bool, int, float, str)) else tuple(value))
        attrs[attr.name] = (attr.domain, attr.data_type, values)
    mesh.calc_loop_triangles()
    return {'vertices': [tuple(v.co) for v in mesh.vertices],
            'edges': [tuple(e.vertices) for e in mesh.edges],
            'polygons': [(tuple(p.vertices), p.material_index, p.use_smooth) for p in mesh.polygons],
            'triangles': [(tuple(t.vertices), tuple(t.loops), t.polygon_index) for t in mesh.loop_triangles],
            'uvs': {layer.name: [tuple(v.uv) for v in layer.data] for layer in mesh.uv_layers},
            'materials': [m.name if m else None for m in mesh.materials], 'attributes': attrs}


def apply(obj, original_receiver, hose, *, row, encode, boundary_shell, exact_scan, evaluated_counts):
    """Apply only after an unsaved staged copy passes scope/ownership/encoding."""
    if obj.modifiers or len(obj.data.materials) != 1 or not obj.data.has_custom_normals:
        raise ValueError('Requires the applied one-material repaired tank')
    sharp = obj.data.attributes.get('sharp_edge')
    if sharp is None or not all(item.value for item in sharp.data):
        raise ValueError('Requires the retained independent native corner spaces')
    validate_row(hose)
    outer, inner, broad_reference = reference_field(original_receiver)
    reference_points = [[original_receiver['vertices'][v] for v in tri] for tri in original_receiver['triangles']]
    reference_normals = [normal(ps) for ps in reference_points]
    before = fingerprint(obj.data)
    before_row = row(obj)
    native_before = [tuple(n.vector) for n in obj.data.corner_normals]
    codes_before = [tuple(v.value) for v in obj.data.attributes['custom_normal'].data]
    stage = obj.copy()
    stage.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(stage)
    applied = False
    try:
        mesh = stage.data
        mesh.calc_loop_triangles()
        world = [tuple(stage.matrix_world @ v.co) for v in mesh.vertices]
        targets = list(native_before)
        changed = set()
        faces = []
        panel_domains = set()
        for face in mesh.polygons:
            triangles = [t for t in mesh.loop_triangles if t.polygon_index == face.index]
            largest = max(triangles, key=lambda t: math.hypot(*cross(sub(world[t.vertices[1]], world[t.vertices[0]]), sub(world[t.vertices[2]], world[t.vertices[0]]))))
            n = normal([world[v] for v in largest.vertices])
            ps = [world[v] for v in face.vertices]
            planarity = max(abs(dot(sub(p, world[largest.vertices[0]]), n)) for p in ps)
            if planarity > GUARD:
                raise ValueError('Tank polygon is not planar within existing 1um guard')
            part = {'name': obj.name, 'vertices': world, 'triangles': [list(t.vertices) for t in triangles]}
            parallel = [i for i, ref in enumerate(reference_normals) if dot(n, ref) > .99999]
            patch = {**original_receiver, 'triangles': [original_receiver['triangles'][i] for i in parallel]}
            support = boundary_shell(part, patch, maximum=GUARD) if parallel else {'status': 'failed'}
            if support['status'] == 'passed':
                owners = [(axis, side) for axis in range(3) for side in range(2)
                          if max(abs(p[axis]-outer[axis][side]) for p in ps) <= GUARD
                          and n[axis] * (1 if side else -1) > .99999]
                if len(owners) > 1:
                    raise ValueError('Ambiguous current broad panel')
                if owners:
                    domain = 'retained_flat_broad_panel'
                    panel_domains.add(owners[0])
                else:
                    domain = 'authored_original_chamfer_corner'
                    for loop in face.loop_indices:
                        direction = field(world[mesh.loops[loop].vertex_index], inner)
                        targets[loop] = unit(tuple(stage.matrix_world.to_3x3().transposed() @ Vector(direction)))
                        changed.add(loop)
            else:
                support = boundary_shell(part, hose, maximum=GUARD)
                if support['status'] != 'passed':
                    raise ValueError('Face lacks complete original outer or socket ownership')
                domain = 'retained_flat_socket'
            faces.append({'polygon': face.index, 'domain': domain, 'triangles': len(triangles),
                          'loops': list(face.loop_indices), 'maximum_planarity_m': planarity, 'support': support})
        if len(panel_domains) != 6 or not changed or not any(f['domain'] == 'retained_flat_socket' for f in faces):
            raise ValueError('Incomplete declared tank finish inventory')
        encoding = encode(mesh, targets)
        if not encoding['passed']:
            raise ValueError('Chamfer target native encoding failed')
        retained = sorted(set(range(len(mesh.loops))) - changed)
        # Encoding spaces are unchanged/all-sharp. Preserve protected shorts
        # exactly rather than silently re-encoding socket or broad-panel fields.
        for loop in retained:
            mesh.attributes['custom_normal'].data[loop].value = codes_before[loop]
        mesh.update()
        actual = [tuple(n.vector) for n in mesh.corner_normals]
        errors = [angle(targets[i], actual[i]) for i in sorted(changed)]
        if max(errors) > .025 or any(abs(math.hypot(*n)-1) > 1e-6 or not all(math.isfinite(v) for v in n) for n in actual):
            raise ValueError('Actual authored normal field exceeds unchanged native guard')
        if any(actual[i] != native_before[i] or tuple(mesh.attributes['custom_normal'].data[i].value) != codes_before[i] for i in retained):
            raise ValueError('Protected broad-panel or socket native field changed')
        if fingerprint(mesh) != before:
            raise ValueError('Shading trial changed geometry, topology, UV, material or other attributes')
        after_row = row(stage)
        if any(after_row[k] != before_row[k] for k in before_row if k not in ('name', 'normals')):
            raise ValueError('Evaluated scope changed outside corner normals')
        quality = evaluated_counts(stage)
        counters = ('nonmanifold_edges', 'duplicate_faces', 'degenerate_faces', 'degenerate_triangles',
                    'triangulated_nonmanifold_edges', 'triangulated_duplicate_faces',
                    'nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals')
        if any(quality[k] for k in counters):
            raise ValueError('Native tank quality failed')
        exact = exact_scan(after_row)
        if exact['status'] != 'passed' or exact['bad_pairs']:
            raise ValueError('Tank exact self check failed')
        # Shared surface-edge endpoints have identical requested vectors. Socket
        # rims intentionally remain split from the external appearance field.
        vertex_targets = {}
        for loop in sorted(changed):
            vertex_targets.setdefault(mesh.loops[loop].vertex_index, []).append(targets[loop])
        if any(any(n != ns[0] for n in ns[1:]) for ns in vertex_targets.values()):
            raise ValueError('New chamfer field is discontinuous at shared vertices')
        report = {'faces': faces, 'outer_bounds_m': outer, 'inner_boundary_m': inner,
                  'actual_broad_reference_triangles': broad_reference, 'changed_loops': sorted(changed),
                  'retained_loops': retained, 'targets': targets, 'encoding': encoding,
                  'maximum_actual_target_degrees': max(errors),
                  'maximum_authored_change_from_flat_degrees': max(angle(native_before[i], actual[i]) for i in changed),
                  'quality': quality, 'exact_self': exact, 'triangle_delta': 0,
                  'all_geometry_topology_uv_material_other_attributes_exact': True,
                  'retained_broad_panel_socket_normals_and_codes_exact': True,
                  'new_shared_vertex_targets_exact': True, 'old_field_preservation_claim_in_chamfers': False,
                  'appearance_approval': None}
        obj.data = mesh
        applied = True
        return report
    finally:
        data = stage.data
        bpy.data.objects.remove(stage, do_unlink=True)
        if not applied and data.users == 0:
            bpy.data.meshes.remove(data)
