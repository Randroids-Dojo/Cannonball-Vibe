"""Corrected finite C end-wall receiver with a recessed inner pocket. No I/O.

This is a candidate to test, not an accepted production helper. A 0.5 mm
unchanged collar remains inside the measured 20 mm ownership boundary.
"""
from fractions import Fraction as F
from collections import defaultdict, Counter
import math, struct
import bpy
from mathutils import Vector, geometry, Matrix
from .boundary02 import sub, dot, cross, unit
from .fragment04 import clip
from .strip23 import area, polygon_clip

def native(p):
    return tuple((struct.unpack('<f', struct.pack('<f', float(v)))[0] for v in p))

def ear(poly, coords):
    poly = list(poly)
    answer = []
    orientation = 1 if area([coords[i] for i in poly]) > 0 else -1

    def turn(a, b, c):
        return cross((*sub(b, a), 0), (*sub(c, a), 0))[2] * orientation
    while len(poly) > 3:
        for i, b in enumerate(poly):
            a, c = (poly[i - 1], poly[(i + 1) % len(poly)])
            t = [coords[k] for k in (a, b, c)]
            if turn(*t) <= 0:
                continue
            others = [j for j in poly if j not in (a, b, c)]
            if any((all((turn(t[k], t[(k + 1) % 3], coords[j]) >= 0 for k in range(3))) for j in others)):
                continue
            answer.append((a, b, c))
            poly.pop(i)
            break
        else:
            raise ValueError('Retained polygon has no strict complete-boundary ear')
    if turn(*(coords[k] for k in poly)) <= 0:
        raise ValueError('Retained last ear is not positive')
    answer.append(tuple(poly))
    return answer

def build(original, body, skins, plans, encode):
    if original.name != 'LOD0_StructuralBody' or len(original.modifiers):
        raise ValueError('Expected current unmodified structural body')
    if any((abs(original.matrix_world[r][c] - (1.0 if r == c else 0.0)) > 1e-12 for r in range(4) for c in range(4))):
        raise ValueError('Body world/local field conversion is not owned')
    vertices = [tuple(p) for p in body['vertices']]
    weights = {i: ((i, F(1)),) for i in range(len(vertices))}
    index = {w: i for i, w in weights.items()}
    edge_points = defaultdict(set)
    parts = {}
    inside = {}
    domains = {}
    originals = {}
    identity = [[F(1), F(0), F(0)], [F(0), F(1), F(0)], [F(0), F(0), F(1)]]

    def add_weight(tri, w):
        key = tuple(sorted(((i, t) for i, t in zip(tri, w) if t)))
        if key not in index:
            index[key] = len(vertices)
            weights[index[key]] = key
            vertices.append(native([sum((t * F(body['vertices'][i][k]) for i, t in key)) for k in range(3)]))
        at = index[key]
        if len(key) == 2:
            edge_points[tuple((i for i, t in key))].add(at)
        return at
    for side, plan in plans.items():
        a = list(map(F, plan['seed_a']))
        b = list(map(F, plan['seed_b']))
        q = list(map(F, plan['toward_C_xy']))
        d = list(map(F, unit([float(b[k] - a[k]) if k < 2 else 0.0 for k in range(3)])))
        length = F(math.hypot(float(b[0] - a[0]), float(b[1] - a[1])))
        limits = (-F(0.0045), length + F(0.0045), -F(0.007), F(0.0085))

        def coords(p):
            return (dot(sub(list(map(F, p)), a), d), dot(sub(list(map(F, p)), a), q))
        inside[side] = []
        domains[side] = {'a': a, 'd': d, 'q': q, 'limits': limits}
        originals[side] = []
        for fi, tri in enumerate(body['triangles']):
            ps = [body['vertices'][v] for v in tri]
            n = cross(sub(ps[1], ps[0]), sub(ps[2], ps[0]))
            if min((p[2] for p in ps)) < 0.9 or n[2] <= 0:
                continue
            uv = [coords(p) for p in ps]
            if any((max((p[k] for p in uv)) < lo or min((p[k] for p in uv)) > hi for k, lo, hi in ((0, limits[0], limits[1]), (1, limits[2], limits[3])))):
                continue
            values = [[p[0] - limits[0], limits[1] - p[0], p[1] - limits[2], limits[3] - p[1]] for p in uv]
            pending = identity
            outside = []
            for k in range(4):
                field = [v[k] for v in values]
                other = clip(pending, [-v for v in field])
                if len(other) >= 3 and abs(area([(p[1], p[2]) for p in other])) > 0:
                    outside.append(other)
                pending = clip(pending, field)
                if len(pending) < 3:
                    break
            if len(pending) < 3 or abs(area([(p[1], p[2]) for p in pending])) == 0:
                continue
            if fi in parts:
                raise ValueError('Paired receiver domains overlap')
            if abs(area([(p[1], p[2]) for p in pending])) + sum((abs(area([(p[1], p[2]) for p in p])) for p in outside)) != F(1, 2):
                raise ValueError('Incomplete original face partition')
            parts[fi] = [[add_weight(tri, w) for w in poly] for poly in outside]
            inside[side].append([add_weight(tri, w) for w in pending])
            originals[side].append(fi)
    polygons = {}
    coordinates = {i: tuple(map(F, p[:2])) for i, p in enumerate(vertices)}
    for fi, tri in enumerate(body['triangles']):
        source_polys = parts.get(fi, [list(tri)])
        local = set((i for poly in source_polys for i in poly))
        for a, b in zip(tri, tri[1:] + tri[:1]):
            local.update(edge_points[tuple(sorted((a, b)))])
        if fi in parts:
            for polys in inside.values():
                for poly in polys:
                    local.update((i for i in poly if set((j for j, t in weights[i])) <= set(tri)))
        for poly in source_polys:
            expanded = []
            for a, b in zip(poly, poly[1:] + poly[:1]):
                wa = dict(weights[a])
                wb = dict(weights[b])
                axes = sorted(set(wa) | set(wb))
                delta = {i: wb.get(i, F(0)) - wa.get(i, F(0)) for i in axes}
                axis = next((i for i in axes if delta[i]))
                found = []
                for p in local:
                    wp = dict(weights[p])
                    t = (wp.get(axis, F(0)) - wa.get(axis, F(0))) / delta[axis]
                    if not 0 <= t < 1:
                        continue
                    if all((wp.get(i, F(0)) == wa.get(i, F(0)) + t * delta.get(i, F(0)) for i in set(axes) | set(wp))):
                        found.append((t, p))
                expanded.extend((p for t, p in sorted(found)))
            polygons.setdefault(fi, []).append(expanded)
    faces = []
    targets = []
    uvs = {k: [] for k in body['uvs']}
    materials = []
    owners = []
    source_barycentric = []
    patches = {}
    new_targets = {}

    def retained(fi, tri):
        original_tri = body['triangles'][fi]
        ls = body['triangle_loops'][fi]
        ns = [body['normals'][l] for l in ls]
        faces.append(tuple(tri))
        materials.append(body['triangle_materials'][fi])
        owners.append(fi)
        source_barycentric.append([[str(dict(weights[i]).get(v, F(0))) for v in original_tri] for i in tri])
        for i in tri:
            w = dict(weights[i])
            ws = [float(w.get(v, F(0))) for v in original_tri]
            targets.append(unit([sum((t * n[k] for t, n in zip(ws, ns))) for k in range(3)]))
            for layer in uvs:
                uvs[layer].append([sum((t * body['uvs'][layer][l][k] for t, l in zip(ws, ls))) for k in range(2)])
    for fi, polys in polygons.items():
        for poly in polys:
            if len(poly) == 3:
                retained(fi, poly)
            else:
                tri = body['triangles'][fi]
                ps = [body['vertices'][v] for v in tri]
                n = cross(sub(ps[1], ps[0]), sub(ps[2], ps[0]))
                axis = max(range(3), key=lambda k: abs(n[k]))
                axes = [k for k in range(3) if k != axis]
                plane = {i: tuple((dict(weights[i]).get(v, F(0)) for v in tri[1:])) for i in poly}
                for t in ear(poly, plane):
                    retained(fi, t)

    def add_new(p, n):
        i = len(vertices)
        vertices.append(native(p))
        new_targets[i] = tuple(unit(n))
        return i

    def append_new(tri, kind):
        faces.append(tuple(tri))
        materials.append(body['triangle_materials'][originals[side][0]])
        owners.append(None)
        source_barycentric.append(None)
        geometric = unit(cross(sub(vertices[tri[1]], vertices[tri[0]]), sub(vertices[tri[2]], vertices[tri[0]])))
        for i in tri:
            if kind in ('butt', 'inner_pocket'):
                n = geometric
            elif i in new_targets:
                n = new_targets[i]
            else:
                ns = []
                for fi in originals[side]:
                    if set((k for k, w in weights[i])) <= set(body['triangles'][fi]):
                        ls = body['triangle_loops'][fi]
                        ws = dict(weights[i])
                        ns.append(unit([sum((float(ws.get(v, F(0))) * body['normals'][l][k] for v, l in zip(body['triangles'][fi], ls))) for k in range(3)]))
                if not ns:
                    raise ValueError('Missing receiver perimeter source field')
                n = unit([sum((v[k] for v in ns)) for k in range(3)])
            targets.append(n)
            for layer in uvs:
                uvs[layer].append([vertices[i][0] / 0.25, vertices[i][1] / 0.25])
    for side, polys in inside.items():
        directed = Counter(((a, b) for poly in polys for a, b in zip(poly, poly[1:] + poly[:1])))
        boundary = {(a, b) for a, b in directed if (b, a) not in directed}
        if any((n != 1 for n in directed.values())):
            raise ValueError('Repeated original patch edge')
        nxt = {a: b for a, b in boundary}
        if len(nxt) != len(boundary):
            raise ValueError('Receiver boundary branches')
        loop = [min(nxt)]
        while nxt[loop[-1]] != loop[0]:
            loop.append(nxt[loop[-1]])
            if len(loop) > len(boundary):
                raise ValueError('Open receiver boundary')
        if len(loop) != len(boundary):
            raise ValueError('Receiver has additional boundary loop')
        skin = skins[side]['row']
        proof = skins[side]['proof']
        nu = len(proof['u_knots'])
        nv = len(proof['s_knots'])
        offset = nu * nv
        co = []
        ci = []
        to = []
        ti = []
        for k in range(nu):
            v = (nv - 1) * nu + k
            old = (nv - 2) * nu + k
            p = skin['vertices'][v]
            inner = skin['vertices'][v + offset]
            li = next((l for t, ls in zip(skin['triangles'], skin['triangle_loops']) if v in t and all((i < offset for i in t)) for i, l in zip(t, ls) if i == v))
            n = skin['normals'][li]
            co.append(add_new(p, n))
            ci.append(add_new(inner, n))
            delta = sub(p, skin['vertices'][old])
            factor = 0.002 / math.hypot(*delta[:2])
            to.append(add_new([p[j] + factor * delta[j] for j in range(3)], n))
            delta = sub(skin['vertices'][old + offset], inner)
            factor = 0.002 / math.hypot(*delta[:2])
            ti.append(add_new([inner[j] + factor * delta[j] - (0.0015 if j == 2 else 0.0) for j in range(3)], n))
        regions = [co + list(reversed(ci)), co + list(reversed(to)), ci + list(reversed(ti))]
        all_loops = [loop, *regions]
        ids = sorted({i for l in all_loops for i in l})
        mapping = {i: j for j, i in enumerate(ids)}
        edges = {tuple(sorted((a, b))) for l in all_loops for a, b in zip(l, l[1:] + l[:1])}
        cdt = geometry.delaunay_2d_cdt([Vector(vertices[i][:2]) for i in ids], [(mapping[a], mapping[b]) for a, b in sorted(edges)], [], 0, 1e-12, True)
        out_v, _, out_f, origin, _, _ = cdt
        if len(out_v) != len(ids) or any((len(row) != 1 for row in origin)):
            raise ValueError('Receiver CDT invented, intersected or merged input vertices')
        remap = {j: ids[row[0]] for j, row in enumerate(origin)}
        if any((tuple(v) != vertices[remap[j]][:2] for j, v in enumerate(out_v))):
            raise ValueError('Receiver CDT moved native input vertices')

        def inside_loop(point, l):
            result = 0
            for a, b in zip(l, l[1:] + l[:1]):
                x, y = (vertices[a], vertices[b])
                turn = (y[0] - x[0]) * (point[1] - x[1]) - (y[1] - x[1]) * (point[0] - x[0])
                if x[1] <= point[1] < y[1] and turn > 0:
                    result += 1
                if y[1] <= point[1] < x[1] and turn < 0:
                    result -= 1
            return result != 0
        selected = []
        kinds = []
        for t in out_f:
            tri = tuple((remap[j] for j in t))
            center = [sum((F(vertices[i][k]) for i in tri)) / 3 for k in range(2)]
            if not inside_loop(center, loop) or any((inside_loop(center, l) for l in regions)):
                continue
            if area([tuple((F(v) for v in vertices[i][:2])) for i in tri]) < 0:
                tri = tuple(reversed(tri))
            selected.append(tri)
            kinds.append('inner_pocket' if any((i in ti for i in tri)) else 'transition')
        for lower, upper, kind in ((to, co, 'outer_tangent'), (ci, ti, 'inner_pocket')):
            for k in range(nu - 1):
                pair = [(lower[k], lower[k + 1], upper[k]), (lower[k + 1], upper[k + 1], upper[k])]
                for tri in pair:
                    if area([tuple((F(v) for v in vertices[i][:2])) for i in tri]) < 0:
                        tri = tuple(reversed(tri))
                    selected.append(tri)
                    kinds.append(kind)
        outer_ids = set(range((nv - 1) * nu, nv * nu))
        inner_ids = {i + offset for i in outer_ids}
        seam_map = {old: new for old, new in zip(sorted(outer_ids), co)}
        seam_map.update({old: new for old, new in zip(sorted(inner_ids), ci)})
        copied_end_faces = []
        for fi, t in enumerate(skin['triangles']):
            if set(t) <= set(seam_map) and set(t) & outer_ids and set(t) & inner_ids:
                selected.append(tuple((seam_map[i] for i in reversed(t))))
                kinds.append('butt')
                copied_end_faces.append(fi)
        if len(copied_end_faces) != 2 * (nu - 1):
            raise ValueError('Actual native C end-wall inventory differs')
        counter = Counter(((a, b) for t in selected for a, b in zip(t, t[1:] + t[:1])))
        actual = {(a, b) for a, b in counter if (b, a) not in counter}
        if any((n != 1 for n in counter.values())) or actual != set(zip(loop, loop[1:] + loop[:1])):
            raise ValueError('Complete native receiver boundary changed')
        source_area = area([tuple((F(v) for v in vertices[i][:2])) for i in loop])
        new_area = sum((area([tuple((F(v) for v in vertices[i][:2])) for i in t]) for t in selected))
        if source_area != new_area:
            raise ValueError('Complete receiver projected domain mismatch')
        for t, kind in zip(selected, kinds):
            append_new(t, kind)
        patches[side] = {'original_triangles': originals[side], 'boundary_vertices': loop, 'triangles': len(selected), 'source_projected_area': str(source_area), 'complete_indexed_boundary_exact': True, 'complete_projected_area_exact': True, 'C_outer_seam': co, 'C_inner_seam': ci, 'outside_authored_domain_collar_m': 0.0005, 'actual_new_surface': 'Exact paired C through-thickness end wall,2mm outer facet-tangent strip,1.5mm concealed inner pocket retreat at2mm inward. No inner lap contact is claimed; full triangle nonpenetration is required.'}
    used = sorted({i for t in faces for i in t})
    remap = {v: i for i, v in enumerate(used)}
    mesh = bpy.data.meshes.new('Private_CQuarter_Receiver40')
    mesh.from_pydata([vertices[i] for i in used], [], [tuple((remap[i] for i in t)) for t in faces])
    mesh.update()
    for material in original.data.materials:
        mesh.materials.append(material)
    for p, m in zip(mesh.polygons, materials):
        p.material_index = m
        p.use_smooth = True
    for name, values in uvs.items():
        layer = mesh.uv_layers.new(name=name)
        for datum, value in zip(layer.data, values):
            datum.uv = value
    encoding = encode(mesh, targets)
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = Matrix.Identity(4)
    return (obj, {'patches': patches, 'original_triangle_owners': owners, 'original_barycentric_correspondence': source_barycentric, 'ideal_targets': targets, 'encoding': encoding, 'cost': {'old_triangles': len(body['triangles']), 'new_triangles': len(faces), 'delta': len(faces) - len(body['triangles'])}, 'status': 'Unsaved candidate; complete self, physical fit, outside fields and all constraints must be tested.'})
