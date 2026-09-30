"""Editable native Roof domain split across the actual Solidify boundary."""
import math
import bpy

def make(original):
    if original.name != 'LOD0_Roof':
        raise ValueError('Roof domain proposal requires exact semantic Roof')
    mesh = original.data
    if len(mesh.vertices) != 255 or len(mesh.polygons) != 224 or any((len(p.vertices) != 4 for p in mesh.polygons)):
        raise ValueError('Unexpected editable roof sheet recipe')
    if mesh.has_custom_normals:
        raise ValueError('Separately authored custom Roof field requires an explicit rebind')
    if len(original.modifiers) != 1 or original.modifiers[0].type != 'SOLIDIFY':
        raise ValueError('Unexpected Roof modifier stack')
    mod = original.modifiers[0]
    if mod.solidify_mode != 'EXTRUDE' or abs(mod.thickness - 0.0012) > 1e-09 or mod.offset != -1.0 or (not mod.use_rim):
        raise ValueError('Unexpected actual Roof sheet thickness contract')
    counts = {e.index: 0 for e in mesh.edges}
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            counts[mesh.loops[li].edge_index] += 1
    boundary = [i for i, n in counts.items() if n == 1]
    if len(boundary) != 60 or any((n not in (1, 2) for n in counts.values())):
        raise ValueError('Unexpected finite roof perimeter')
    obj = original.copy()
    obj.data = mesh.copy()
    obj.name = 'Private_CQuarter_RoofFields12'
    try:
        bpy.context.scene.collection.objects.link(obj)
        m = obj.data
        sharp = m.attributes.get('sharp_edge') or m.attributes.new(name='sharp_edge', type='BOOLEAN', domain='EDGE')
        for i, datum in enumerate(sharp.data):
            datum.value = counts[i] == 1
        m.update()
        bpy.context.view_layer.update()
        return (obj, {'authorship': 'The60 actual raw boundary edges are sharp. Solidify propagates the separate top/underside-to-rim boundaries while the224 original top quads remain smooth.', 'raw_boundary_edge_indices': boundary, 'raw_vertices': 255, 'raw_quads': 224, 'raw_triangles': 448, 'normals_are_new_authored_targets': True, 'custom_normal_encoding_used': False, 'triangle_delta': 0, 'controls': 'Editable source sharp_edge attribute; actual Solidify modifier is unchanged and retained.', 'must_compare_evaluated_geometry_with_original': True})
    except BaseException:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
        raise
