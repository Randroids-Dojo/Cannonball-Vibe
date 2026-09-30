"""Seal-clear member65 plus two actual-C-facet bearing bosses per side.

Each small triangular bearing lands on an explicitly indexed inner surface of
the newly authored13x8 skin. Its lower end enters the actual member by2mm before
a native exact union. No original scene data is assigned, saved or exported.
"""
import math
from .boundary02 import sub, dot, cross, unit
from . import reinforcement65 as previous

def make(original, member, skin, glass, guide, seal, aperture, encode):
    import bpy, bmesh
    from mathutils import Vector
    from endurance_sedan import roof_feature26 as native, geometry, boolean_surface
    from endurance_sedan.qa import geometry as measure
    from endurance_sedan.qa.self_geometry import scan
    obj, proof = previous.make(original, member, skin, glass, guide, seal, aperture, encode)
    if len(skin['vertices']) != 208 or len(skin['triangles']) != 412:
        raise ValueError('Expected declared13x8 double-sided C skin')
    records = []
    for j, k, branch in ((7, 1, 1), (9, 1, 0)):
        fi = 4 * (j * 7 + k) + 1 + 2 * branch
        tri = skin['triangles'][fi]
        if not all((104 <= v < 208 for v in tri)):
            raise ValueError('Bearing owner is not the actual inner C field')
        ps = [Vector(skin['vertices'][v]) for v in tri]
        center = sum(ps, Vector()) / 3
        top = [center + 0.4 * (p - center) for p in reversed(ps)]
        current = native.row(obj)
        beam = measure.Mesh(current)
        bottom = []
        depths = []
        for p in top:
            hit, n, owner, d = beam.bvh.ray_cast(p, Vector((0, 0, -1)), 0.04)
            if hit is None or d < 0.001 or d > 0.025:
                raise ValueError(('No bounded actual bearing section', fi, d))
            q = hit + Vector((0, 0, -0.002))
            inside = beam.inside(q)
            if not inside or not inside['inside_all_three_rays']:
                raise ValueError(('Bearing root not inside actual member', fi, list(q)))
            bottom.append(q)
            depths.append(d)
        points = [list(p) for p in top + bottom]
        faces = [[0, 1, 2], [5, 4, 3], [0, 3, 4], [0, 4, 1], [1, 4, 5], [1, 5, 2], [2, 5, 3], [2, 3, 0]]
        mesh = bpy.data.meshes.new('Private_CQuarter_Bearing67')
        mesh.from_pydata(points, [], faces)
        mesh.update()
        if sum((dot(list(mesh.vertices[t[0]].co), cross(list(mesh.vertices[t[1]].co), list(mesh.vertices[t[2]].co))) for t in faces)) < 0:
            raise ValueError('Inverted bearing prism')
        pad = bpy.data.objects.new(mesh.name, mesh)
        bpy.context.scene.collection.objects.link(pad)
        try:
            if scan(native.row(pad))['status'] != 'passed':
                raise ValueError('Bearing solid exact self failed')
            bpy.context.view_layer.objects.active = obj
            modifier = obj.modifiers.new('Finite C bearing union', 'BOOLEAN')
            modifier.operation = 'UNION'
            modifier.solver = 'EXACT'
            modifier.object = pad
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        finally:
            bpy.data.objects.remove(pad, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        records.append({'skin_grid_cell': [j, k], 'branch': branch, 'actual_inner_triangle': fi, 'actual_original_triangle': [list(p) for p in ps], 'bearing_prism': points, 'triangle_faces': faces, 'area_m2': (top[1] - top[0]).cross(top[2] - top[0]).length / 2, 'actual_initial_gap_m': depths, 'member_root_insertion_m': 0.002})
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    def author():
        targets = []
        for poly in obj.data.polygons:
            ps = [list(obj.data.vertices[v].co) for v in poly.vertices]
            n = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
            e = unit(sub(ps[1], ps[0]))
            v = cross(n, e)
            poly.use_smooth = True
            for loop, p in zip(poly.loop_indices, ps):
                targets.append(n)
                for layer in obj.data.uv_layers:
                    layer.data[loop].uv = (dot(sub(p, ps[0]), e) / 0.25, dot(sub(p, ps[0]), v) / 0.25)
        return (targets, encode(obj.data, targets))
    targets, encoding = author()
    repair = boolean_surface.repair(obj, scan, geometry.evaluated_counts)
    if repair['changed']:
        targets, encoding = author()
    proof['bearing_seats'] = records
    proof['bearing_native_diagonal_repair'] = repair
    proof['ideal_targets'] = targets
    proof['encoding'] = encoding
    proof['final_native_topology'] = {'vertices': [list(v.co) for v in obj.data.vertices], 'triangles': [list(p.vertices) for p in obj.data.polygons]}
    proof['limits'] = 'Candidate finite bearing construction; complete native C-seat, seal/guide, upper web and base/body interfaces still require independent checks.'
    return (obj, proof)
