"""Current-member flush foot with fixed-vertex repair and owned field transport.

No I/O, source load, original assignment, source save or export. The receiver
is the caller's actual current body, including any earlier body-field stage.
"""
import bpy, math, copy
from fractions import Fraction as F
from .boundary02 import sub, dot, cross, unit, angle
from .joint43 import distance2
from endurance_sedan.qa.exact_triangles import vector
from endurance_sedan import roof_feature26 as native, geometry
from endurance_sedan.qa.self_geometry import scan
from . import base78
from . import base_repair82

def barycentric(point, triangle):
    p = vector(point)
    a, b, c = map(vector, triangle)
    v = sub(b, a)
    w = sub(c, a)
    n = cross(v, w)
    n2 = dot(n, n)
    if n2 == 0:
        raise ValueError('Degenerate complete reference face')
    q = sub(p, a)
    wb = dot(cross(q, w), n) / n2
    wc = dot(cross(v, q), n) / n2
    return [1 - wb - wc, wb, wc]

def make(member, body, member_proof, encode):
    obj, proof = base78.make(member, body)
    try:
        original = proof['original_member_row']
        receiver = proof['actual_body_row']
        if len(member_proof['ideal_targets']) != len(original['normals']):
            raise ValueError('Immediate member ideal stream length changed')
        before = native.row(obj)
        origins = proof['native_origin_per_triangle']
        fixed, correction = base_repair82.repair(before, origins, original, receiver)
        coordinates = [list(v.co) for v in obj.data.vertices]
        mesh = bpy.data.meshes.new('Private_CQuarter_FlushFoot84')
        mesh.from_pydata(coordinates, [], fixed['triangles'])
        mesh.update()
        for mat in member.data.materials:
            mesh.materials.append(mat)
        for name in original['uvs']:
            mesh.uv_layers.new(name=name)
        targets = []
        uv_targets = {k: [] for k in original['uvs']}
        corners = []
        max_pos = 0.0
        owners = []
        for fi, (face, origin) in enumerate(zip(fixed['triangles'], origins)):
            reference = original if origin > 0 else receiver
            oi = abs(origin) - 1
            if oi >= len(reference['triangles']):
                raise ValueError('Native face provenance out of range')
            ids = reference['triangles'][oi]
            ls = reference['triangle_loops'][oi]
            points = [reference['vertices'][v] for v in ids]
            n = unit(cross(sub(points[1], points[0]), sub(points[2], points[0])))
            if origin > 0:
                nt = [member_proof['ideal_targets'][i] for i in ls]
                if any((angle(nt[0], x) > 1e-09 for x in nt[1:])):
                    raise ValueError('Expected immediate authored member facet field')
                n = nt[0]
            else:
                n = [-v for v in n]
            e = unit(sub(points[1], points[0]))
            v = cross(n, e)
            actual = [fixed['vertices'][i] for i in face]
            normal = cross(sub(actual[1], actual[0]), sub(actual[2], actual[0]))
            if dot(normal, n) <= 0:
                raise ValueError(('Foot face opposes complete owner hemisphere', fi, origin))
            ds = [distance2(vector(p), points) for p in actual]
            if max(ds) > F(1e-06) ** 2:
                raise ValueError(('Full triangle leaves its native owner', fi, origin, math.sqrt(float(max(ds)))))
            max_pos = max(max_pos, math.sqrt(float(max(ds))))
            ws = [barycentric(p, points) for p in actual]
            corners.append([[str(t) for t in w] for w in ws])
            owners.append(origin)
            for p, w, li in zip(actual, ws, mesh.polygons[fi].loop_indices):
                targets.append(list(n))
                for name, layer in ((k, mesh.uv_layers[k]) for k in original['uvs']):
                    uv = [sum((float(t) * reference['uvs'][name][loop][k] for t, loop in zip(w, ls))) for k in range(2)] if origin > 0 else [dot(sub(p, points[0]), e) / 0.25, dot(sub(p, points[0]), v) / 0.25]
                    layer.data[li].uv = uv
                    uv_targets[name].append(uv)
            mesh.polygons[fi].material_index = original['triangle_materials'][oi] if origin > 0 else 0
            mesh.polygons[fi].use_smooth = True
        encoding = encode(mesh, targets)
        old_mesh = obj.data
        obj.data = mesh
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
        final = native.row(obj)
        if final['vertices'] != before['vertices'] or final['triangles'] != fixed['triangles']:
            raise ValueError('Native foot encoding changed geometry')
        counts = geometry.evaluated_counts(obj)
        self_check = scan(final)
        keys = ('duplicate_faces', 'nonmanifold_edges', 'degenerate_faces', 'degenerate_triangles', 'triangulated_duplicate_faces', 'triangulated_nonmanifold_edges', 'nonfinite_corner_normals', 'zero_corner_normals', 'nonunit_corner_normals')
        if any((counts[k] for k in keys)) or self_check['status'] != 'passed':
            raise ValueError(('Final foot native validity rejected', counts, self_check))
        proof.update({'fixed_vertex_diagonal_repair': correction, 'ideal_targets': targets, 'UV_targets': uv_targets, 'exact_corner_reference_barycentric': corners, 'native_origin_per_triangle': owners, 'maximum_complete_native_face_to_owner_m': max_pos, 'encoding': encoding, 'native_counts': counts, 'exact_self': self_check, 'bearing_seats': copy.deepcopy(member_proof['bearing_seats']), 'field_status': 'Direct original ideal targets on every retained member fragment; new reversed native receiver-facet targets and isometric/.25 UVs on the foot. Independent full field/contact checks pending.'})
        return (obj, proof)
    except BaseException:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise
