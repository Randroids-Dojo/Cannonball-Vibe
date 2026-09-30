"""Source-ready reports candidate: simplify declared components, then batch.

No source/file access, saving, coordinate welding, or post-batch simplification.
The caller supplies its normal batching/protected-paint routines and the exact
indexed-shell checker. The caller decides which measured semantic groups need
this fallback; this helper never guesses provenance from a decimated mesh.
"""
import json
import math

import bmesh
import bpy


def native_row(obj):
    bpy.context.view_layer.update()
    mesh = obj.data
    mesh.calc_loop_triangles()
    if mesh.uv_layers.active is None:
        raise ValueError('Missing active UV layer: ' + obj.name)
    row = {'name': obj.name, 'parent': obj.parent.name,
           'vertices': [list(obj.matrix_world @ vertex.co) for vertex in mesh.vertices],
           'triangles': [list(triangle.vertices) for triangle in mesh.loop_triangles],
           'normals': [[list(mesh.corner_normals[index].vector) for index in triangle.loops]
                       for triangle in mesh.loop_triangles],
           'uvs': [[list(mesh.uv_layers.active.data[index].uv) for index in triangle.loops]
                   for triangle in mesh.loop_triangles],
           'material_names': [material.name if material else None for material in mesh.materials]}
    if not all(math.isfinite(value) for vector in row['vertices'] for value in vector):
        raise ValueError('Nonfinite component position: ' + obj.name)
    if not all(math.isfinite(value) for face in row['normals'] for vector in face for value in vector):
        raise ValueError('Nonfinite component normal: ' + obj.name)
    zero = next(((triangle, corner, vector) for triangle, face in enumerate(row['normals'])
                 for corner, vector in enumerate(face)
                 if sum(value * value for value in vector) <= 1e-12), None)
    if zero is not None:
        triangle, corner, vector = zero
        point = row['vertices'][row['triangles'][triangle][corner]]
        raise ValueError('Zero component normal: ' + obj.name + ': triangle=' + str(triangle)
                         + ', corner=' + str(corner) + ', normal=' + repr(vector) + ', point=' + repr(point))
    if not all(math.isfinite(value) for face in row['uvs'] for vector in face for value in vector):
        raise ValueError('Nonfinite component UV: ' + obj.name)
    return row


def ratios(requested, include_rear_door_quarter=False):
    if not math.isfinite(requested) or not 0 < requested <= 1:
        raise ValueError('LOD ratio must be finite and positive')
    values = [requested, min(1., requested * 2), min(1., requested * 4), .5, .75, 1.]
    if include_rear_door_quarter:
        values.append(.26)
    return sorted({value for value in values if value >= requested})


def check_members(members, parent, material, expected_source_parent):
    if not members or len({obj.name for obj in members}) != len(members):
        raise ValueError('Nonempty distinct source members are required')
    for obj in members:
        if obj.type != 'MESH' or obj.get('source_preview_only', False):
            raise ValueError('Only authored source meshes may be simplified: ' + obj.name)
        if obj.parent is None or obj.parent.name != expected_source_parent:
            raise ValueError('Source rigid-parent mismatch: ' + obj.name)
        used = {polygon.material_index for polygon in obj.data.polygons}
        if not used or any(index >= len(obj.material_slots)
                           or obj.material_slots[index].material != material for index in used):
            raise ValueError('Source material mismatch: ' + obj.name)
    if parent is None:
        raise ValueError('Target rigid parent is required')
    if parent.name != expected_source_parent and not (
            expected_source_parent == 'Visual_LOD0' and parent.name in ('Visual_LOD1', 'Visual_LOD2')):
        raise ValueError('Unrelated target rigid parent')


def _simplify_group(name, members, parent, collection, material, requested_ratio, *,
                   expected_source_parent, original_group_triangles, bake_batch, remember_base,
                   protected_paint, shell_certificate,
                   include_rear_door_quarter=False):
    """Return one final batch, exact post-simplification map, and attempt proof.

    Preserve the original group threshold (>50 triangles), matching the native
    controlled trials. Source component identity precedes every Decimate.
    """
    check_members(members, parent, material, expected_source_parent)
    schedule = ratios(requested_ratio, include_rear_door_quarter)
    built = []
    reports = []
    original_names = {}
    for original in sorted(members, key=lambda obj: obj.name):
        obj, _ = bake_batch('Private_' + name + '_' + original.name,
                            [original], parent, collection, material)
        original_names[obj.name] = original.name
        source_row = native_row(obj)
        source_proof = shell_certificate(source_row)
        if source_proof['status'] != 'passed' or source_proof['shell_count'] < 1:
            raise ValueError('Source component is already invalid or folded: ' + original.name)
        base = remember_base(obj.data.copy())
        protected = protected_paint.prepare(obj)
        attempts = []
        selected = None
        for ratio in schedule:
            old = obj.data
            obj.data = base.copy()
            if old.users == 0:
                bpy.data.meshes.remove(old)
            if original_group_triangles > 50 and ratio < 1 and not (protected and protected['full']):
                modifier = obj.modifiers.new('Per-component verified LOD candidate', 'DECIMATE')
                modifier.ratio = protected_paint.configure(obj, modifier, protected, ratio)
                modifier.use_collapse_triangulate = True
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            changed = obj.data.validate(clean_customdata=False)
            obj.data.update()
            obj.data.calc_loop_triangles()
            audit = bmesh.new()
            audit.from_mesh(obj.data)
            invalid_edges = sum(not edge.is_manifold for edge in audit.edges)
            audit.free()
            degenerate = sum(triangle.area <= 1e-12 for triangle in obj.data.loop_triangles)
            item = {'ratio': ratio, 'triangles': len(obj.data.loop_triangles),
                    'validate_changed': changed, 'nonmanifold_edges': invalid_edges,
                    'degenerate_triangles': degenerate}
            if changed or invalid_edges or degenerate or item['triangles'] < 4:
                item['status'] = 'invalid_topology'
                attempts.append(item)
                continue
            try:
                preservation = protected_paint.restore(obj, protected)
                row = native_row(obj)
                proof = shell_certificate(row)
                item.update(status=proof['status'], shell_count=proof['shell_count'],
                            folded_shells=sum(shell['status'] == 'failed' for shell in proof['shells']))
                if proof['shell_count'] != source_proof['shell_count']:
                    item['status'] = 'lost_source_shell'
            except Exception as error:
                item.update(status='rejected', failure=type(error).__name__ + ': ' + str(error))
                attempts.append(item)
                continue
            attempts.append(item)
            if item['status'] == 'passed':
                selected = (row, proof, preservation)
                break
        if selected is None:
            raise ValueError('No closed self-clear component candidate: ' + original.name + ': ' + str(attempts))
        reports.append({'source_component': original.name,
                        'source_triangles': len(source_row['triangles']),
                        'source_shells': source_proof['shell_count'],
                        'source_proof': source_proof, 'attempts': attempts,
                        'selected_triangles': len(selected[0]['triangles']),
                        'selected_shells': selected[1]['shell_count'],
                        'protected_paint': selected[2]})
        built.append(obj)
        if base.users == 0:
            bpy.data.meshes.remove(base)
    final, entry = bake_batch(name, built, parent, collection, material)
    final_row = native_row(final)
    proof = shell_certificate(final_row)
    if proof['status'] != 'passed' or proof['shell_count'] != sum(row['selected_shells'] for row in reports):
        raise ValueError('Final rebatch failed closed self geometry or lost component shells: ' + name)
    # These ranges are created after all Decimate operations and remain valid.
    # Rebind private object aliases to explicit original source identity.
    for component in entry['components']:
        component['private_component_name'] = component['source_component']
        component['source_component'] = original_names[component['source_component']]
        component['source_parent'] = expected_source_parent
        component['range_domain'] = 'final batch after all per-component simplification'
        original = next(obj for obj in members if obj.name == component['source_component'])
        component['original_source_to_batch'] = [list(row) for row in parent.matrix_world.inverted() @ original.matrix_world]
        component['range_coordinate_space'] = 'target rigid-parent coordinates after private bake'
    final['source_components'] = json.dumps([component['source_component'] for component in entry['components']])
    entry.update(method='Per-component verified simplification followed by unchanged rigid-parent batching',
                 requested_ratio=requested_ratio, triangles_after=len(final_row['triangles']),
                 component_attempts=reports, final_shell_proof=proof)
    for obj in built:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return final, entry


def simplify_group(name, members, parent, collection, material, requested_ratio, *,
                   expected_source_parent, original_group_triangles, bake_batch,
                   protected_paint, shell_certificate,
                   include_rear_door_quarter=False):
    """Own and clean private resources on both successful and failed attempts."""
    owned_objects = set()
    owned_meshes = set()
    retained = None
    def tracked_bake(*args, **kwargs):
        before_objects = set(bpy.data.objects.keys())
        before_meshes = set(bpy.data.meshes.keys())
        try:
            return bake_batch(*args, **kwargs)
        finally:
            owned_objects.update(set(bpy.data.objects.keys()) - before_objects)
            owned_meshes.update(set(bpy.data.meshes.keys()) - before_meshes)
    def remember_base(mesh):
        owned_meshes.add(mesh.name)
        return mesh
    try:
        result = _simplify_group(name, members, parent, collection, material,
            requested_ratio, expected_source_parent=expected_source_parent,
            original_group_triangles=original_group_triangles,
            bake_batch=tracked_bake, remember_base=remember_base,
            protected_paint=protected_paint, shell_certificate=shell_certificate,
            include_rear_door_quarter=include_rear_door_quarter)
        retained = result[0].name
        return result
    finally:
        for owned_name in sorted(owned_objects):
            if owned_name == retained:
                continue
            obj = bpy.data.objects.get(owned_name)
            if obj is not None:
                data = obj.data
                if data is not None:
                    owned_meshes.add(data.name)
                bpy.data.objects.remove(obj, do_unlink=True)
        for owned_name in sorted(owned_meshes):
            mesh = bpy.data.meshes.get(owned_name)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
