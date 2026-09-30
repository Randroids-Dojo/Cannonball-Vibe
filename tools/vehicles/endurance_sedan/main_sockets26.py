"""Finite actual-hose receiving cavities; no file IO or source saves."""
import bpy


def apply(geo, row, after_cut=None):
    hose = bpy.data.objects['LOD0_CoolantHose']
    changed = []
    proof = []
    for name in ('LOD0_ExpansionTank', 'LOD0_RadiatorStack'):
        obj = bpy.data.objects[name]
        assert len(obj.data.materials) == 1
        before = row(obj)
        # Use the actual evaluated bevels as the editable receiving housing.
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(graph)
        baked = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
        obj.modifiers.clear()
        obj.data = baked
        assert row(obj) == before, 'Evaluated housing bake changed actual mesh fields'
        original_material = obj.data.materials[0]
        native_hose = row(hose)
        tool = geo.mesh('Private_ActualTriangulatedHose', native_hose['vertices'], native_hose['triangles'], None, obj.users_collection[0])
        tool.data.materials.clear()
        tool.data.materials.append(original_material)
        for face in tool.data.polygons:
            face.material_index = 0
        try:
            geo.boolean(obj, tool)
        finally:
            data = tool.data
            bpy.data.objects.remove(tool, do_unlink=True)
            if not data.users:
                bpy.data.meshes.remove(data)
        obj.data.materials.clear()
        obj.data.materials.append(original_material)
        for face in obj.data.polygons:
            face.material_index = 0
        retained_fields = after_cut(obj, before, native_hose) if after_cut is not None else None
        quality = geo.evaluated_counts(obj)
        for key in ('nonmanifold_edges', 'duplicate_faces', 'degenerate_faces',
                    'degenerate_triangles', 'triangulated_nonmanifold_edges',
                    'triangulated_duplicate_faces', 'nonfinite_corner_normals',
                    'zero_corner_normals', 'nonunit_corner_normals'):
            assert quality[key] == 0, (name, key, quality[key])
        after = row(obj)
        bounds = lambda r: [[min(v[k] for v in r['vertices']), max(v[k] for v in r['vertices'])] for k in range(3)]
        assert bounds(before) == bounds(after), (name, 'Outer dimensions changed')
        changed.append(obj)
        proof.append({'object': name, 'receiving_surface': hose.name,
                      'native': quality, 'outer_bounds_exact': True,
                      'triangle_delta': len(after['triangles']) - len(before['triangles']),
                      'complete_contact_acceptance': False, 'retained_fields': retained_fields})
    return changed, proof
