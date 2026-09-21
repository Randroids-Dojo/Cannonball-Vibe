"""Unsaved native D-section reinforcement trial. No I/O or scene installation.

Only the actual original circular member is trimmed. The complete actual guide
prism and end-axis centers must survive. Glass and C skin remain untouched.
The closed member represents a modeled reinforcement, not a certified section.
"""
from fractions import Fraction as F
import math
from .boundary02 import sub, dot, cross, unit

def fpoint(p):
    return tuple(map(F, p))

def plane_value(plane, p):
    return dot(plane[0], p) - plane[1]

def lerp(a, b, t):
    return tuple((x + (y - x) * t for x, y in zip(a, b)))

def unique(ps):
    return list(dict.fromkeys(ps))

def section_points(row, y):
    found = []
    for tri in row['triangles']:
        ps = [fpoint(row['vertices'][i]) for i in tri]
        for a, b in zip(ps, ps[1:] + ps[:1]):
            if a[1] == y:
                found.append(a)
            if min(a[1], b[1]) < y < max(a[1], b[1]):
                found.append(lerp(a, b, (y - a[1]) / (b[1] - a[1])))
    return unique(found)

def plan(member, skin, glass, guide, seal, aperture):
    v = member['vertices']
    if len(v) != 20 or len(member['triangles']) != 36:
        raise ValueError('Expected original20-vertex closed circular member')
    a = [sum((p[k] for p in v[:10])) / 10 for k in range(3)]
    b = [sum((p[k] for p in v[10:])) / 10 for k in range(3)]
    axis = unit(sub(b, a))
    e = unit(sub(v[0], a))
    f = cross(axis, e)
    sign = -1 if a[0] < 0 else 1
    n = unit([sign * 0.5846612888555904, -0.28482817331732213, 0.7596341810348418])
    lo = min((p[1] for p in skin['vertices']))
    hi = max((p[1] for p in skin['vertices']))
    knots = sorted(set(map(F, [lo, -1.75, -1.5, -1.31, hi])))
    nf = tuple(map(F, n))
    ds = []
    for y in knots:
        ps = section_points(skin, y)
        if not ps:
            raise ValueError(('Missing actual skin slice', float(y)))
        ds.append(min((dot(nf, p) for p in ps)))
    original = list(ds)
    for j in range(len(knots) - 1):
        y0, y1 = knots[j:j + 2]
        ps = [fpoint(p) for p in skin['vertices'] if y0 <= F(p[1]) <= y1]
        ps += section_points(skin, y0) + section_points(skin, y1)
        violation = max((ds[j] + (ds[j + 1] - ds[j]) * (p[1] - y0) / (y1 - y0) - dot(nf, p) for p in ps), default=F(0))
        if violation > 0:
            ds[j] -= violation
            ds[j + 1] -= violation
    slope = [(ds[j + 1] - ds[j]) / (knots[j + 1] - knots[j]) for j in range(len(knots) - 1)]
    lipschitz = max((math.hypot(n[0], n[1] - float(s), n[2]) for s in slope))
    margin = F(0.0012 * math.nextafter(lipschitz, math.inf))
    ds = [d - margin for d in ds]
    cap = []
    minimum = math.inf
    for j in range(len(knots) - 1):
        y0, y1 = knots[j:j + 2]
        m = (ds[j + 1] - ds[j]) / (y1 - y0)
        p = ((nf[0], nf[1] - m, nf[2]), ds[j] - m * y0)
        cap.append(p)
        ps = [fpoint(q) for q in skin['vertices'] if y0 <= F(q[1]) <= y1]
        ps += section_points(skin, y0) + section_points(skin, y1)
        minimum = min(minimum, min((float(plane_value(p, q)) for q in ps)))
    if minimum / lipschitz < 0.001199999:
        raise ValueError('Complete skin separating-function construction failed')
    glass_n = unit([0.0, -0.49334005, 0.86983653])
    gn = tuple(map(F, glass_n))
    glass_plane = (gn, min((dot(gn, fpoint(p)) for p in seal['vertices'])) - F(0.00105))

    def slab(y):
        return min(len(cap) - 1, max(0, next((i for i in range(len(cap)) if y <= knots[i + 1]), len(cap) - 1)))
    low = [min((p[k] for p in guide['vertices'])) for k in range(3)]
    high = [max((p[k] for p in guide['vertices'])) for k in range(3)]
    ys = sorted({F(low[1]), F(high[1]), *[y for y in knots if F(low[1]) < y < F(high[1])]})
    prism = [(F(x), y, F(z)) for x in (low[0], high[0]) for y in ys for z in (low[2], high[2])]
    actual_guide = unique([fpoint(p) for p in guide['vertices']] + [p for y in ys for p in section_points(guide, y)])
    guide_c_margin = min((-float(plane_value(cap[slab(p[1])], p)) for p in actual_guide))
    guide_glass_margin = min((-float(plane_value(glass_plane, p)) for p in actual_guide))
    an = tuple(map(F, unit([0.0, 0.72, -1.0])))
    aperture_plane = (an, min((dot(an, fpoint(p)) for p in aperture['vertices'])) - F(0.0012))
    guide_aperture_margin = min((-float(plane_value(aperture_plane, p)) for p in actual_guide))
    if guide_aperture_margin < 1e-06:
        raise ValueError(('Aperture separator changes actual guide', guide_aperture_margin))
    if min(guide_c_margin, guide_glass_margin) < 1e-06:
        raise ValueError(('Cap would alter original guide domain', guide_c_margin, guide_glass_margin))
    centers = []
    for point in (a, b):
        p = fpoint(point)
        centers.append({'point': point, 'C_margin': -float(plane_value(cap[slab(p[1])], p)), 'glass_margin': -float(plane_value(glass_plane, p))})
    if min((r[k] for r in centers for k in ('C_margin', 'glass_margin'))) < 0:
        raise ValueError(('An original end axis center is excluded', centers))
    return {'knots': knots, 'planes': cap, 'glass_plane': glass_plane, 'aperture_plane': aperture_plane, 'actual_guide_vertices': actual_guide, 'guide_prism_historical_only': prism, 'axis_centers': centers, 'metrics': {'C_complete_separation_m': minimum / lipschitz, 'Lipschitz_bound': lipschitz, 'BacklightSeal_separation_m': 0.00105, 'aperture_seal_separation_m': 0.0012, 'guide_aperture_margin': guide_aperture_margin, 'guide_C_preservation_margin': guide_c_margin, 'guide_glass_preservation_margin': guide_glass_margin, 'knots': list(map(float, knots)), 'nominal_original_radius_m': 0.03, 'section_direction': n, 'envelope_reductions': list(map(float, (a - b for a, b in zip(original, ds))))}}

def clip(polygons, plane, label):
    answer = []
    cut_edges = []
    for face in polygons:
        ps = face['points']
        out = []
        for a, b in zip(ps, ps[1:] + ps[:1]):
            va, vb = (plane_value(plane, a), plane_value(plane, b))
            if va <= 0:
                out.append(a)
            if va < 0 < vb or vb < 0 < va:
                out.append(lerp(a, b, va / (va - vb)))
        out = unique(out)
        if len(out) >= 3:
            answer.append({**face, 'points': out})
            on = [p for p in out if plane_value(plane, p) == 0]
            if len(on) == 2 and any((plane_value(plane, p) != 0 for p in out)):
                for a, b in zip(out, out[1:] + out[:1]):
                    if a in on and b in on:
                        cut_edges.append((b, a))
    if cut_edges:
        after = {}
        for a, b in cut_edges:
            if a in after and after[a] != b:
                raise ValueError('Ambiguous convex clipping boundary')
            after[a] = b
        start = next(iter(after))
        p = start
        loop = []
        while p not in loop:
            loop.append(p)
            if p not in after:
                raise ValueError('Open convex clipping boundary')
            p = after[p]
        if p != start or len(loop) != len(after):
            raise ValueError('Disconnected convex clipping boundary')
        answer.append({'points': loop, 'owner': None, 'domain': label})
    return answer

def triangulate(ps):
    if len(ps) == 3:
        return [ps]
    n = next((cross(sub(ps[j], ps[0]), sub(ps[j + 1], ps[0])) for j in range(1, len(ps) - 1) if cross(sub(ps[j], ps[0]), sub(ps[j + 1], ps[0])) != [0, 0, 0]), None)
    if n is None:
        raise ValueError('Degenerate clipped polygon')
    axis = max(range(3), key=lambda k: abs(n[k]))
    axes = [k for k in range(3) if k != axis]
    q = [(p[axes[0]], p[axes[1]]) for p in ps]
    turn = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    area = sum((a[0] * b[1] - b[0] * a[1] for a, b in zip(q, q[1:] + q[:1])))
    sgn = 1 if area > 0 else -1
    ids = list(range(len(ps)))
    out = []
    while len(ids) > 3:
        for j, b in enumerate(ids):
            a, c = (ids[j - 1], ids[(j + 1) % len(ids)])
            if sgn * turn(q[a], q[b], q[c]) <= 0:
                continue
            if any((all((sgn * turn(q[x], q[y], q[v]) >= 0 for x, y in ((a, b), (b, c), (c, a)))) for v in ids if v not in (a, b, c))):
                continue
            out.append([ps[a], ps[b], ps[c]])
            ids.pop(j)
            break
        else:
            raise ValueError('Exact convex ear selection failed')
    if turn(*[q[i] for i in ids]) == 0:
        raise ValueError('Final exact ear is degenerate')
    out.append([ps[i] for i in ids])
    return out

def arrays(member, planned):
    original = [{'points': [fpoint(member['vertices'][v]) for v in tri], 'owner': i, 'domain': 'original_member'} for i, tri in enumerate(member['triangles'])]
    polygons = []
    knots = planned['knots']
    planes = planned['planes']
    for j, (lo, hi) in enumerate(zip(knots, knots[1:])):
        part = clip(original, ((F(0), F(-1), F(0)), -lo), 'internal_slice')
        part = clip(part, ((F(0), F(1), F(0)), hi), 'internal_slice')
        if not part:
            continue
        part = clip(part, planned['glass_plane'], 'backlight_seal_clearance_cap')
        part = clip(part, planned['aperture_plane'], 'aperture_seal_clearance_cap')
        part = clip(part, planes[j], 'C_clearance_cap')
        polygons.extend((p for p in part if p['domain'] != 'internal_slice'))
    registry = {}
    vertices = []
    faces = []
    owners = []
    domains = []
    exact = []
    for poly in polygons:
        for tri in triangulate(poly['points']):
            ids = []
            for p in tri:
                if p not in registry:
                    registry[p] = len(vertices)
                    vertices.append(list(map(float, p)))
                    exact.append(p)
                ids.append(registry[p])
            faces.append(ids)
            owners.append(poly['owner'])
            domains.append(poly['domain'])
    edges = {}
    for tri in faces:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append((a, b))
    bad = [(e, v) for e, v in edges.items() if len(v) != 2 or v[0] != tuple(reversed(v[1]))]
    if bad:
        raise ValueError(('Constructed D-section is not an oriented closed indexed shell', bad[:10]))
    return {'vertices': vertices, 'triangles': faces, 'owners': owners, 'domains': domains, 'exact_points': exact}

def make(original, member, skin, glass, guide, seal, aperture, encode):
    import bpy
    from mathutils import Matrix
    planned = plan(member, skin, glass, guide, seal, aperture)
    data = arrays(member, planned)
    mesh = bpy.data.meshes.new('Private_CQuarter_DSection64_' + original.name[-1])
    mesh.from_pydata(data['vertices'], [], data['triangles'])
    mesh.update()
    for material in original.data.materials:
        mesh.materials.append(material)
    points = [list(v.co) for v in mesh.vertices]
    targets = []
    uvs = {n: [] for n in member['uvs']}
    for face, owner in zip(data['triangles'], data['owners']):
        ps = [points[i] for i in face]
        g = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
        e = unit(sub(ps[1], ps[0]))
        v = cross(g, e)
        for p in ps:
            targets.append(g)
            for name in uvs:
                uvs[name].append([dot(sub(p, ps[0]), e) / 0.25, dot(sub(p, ps[0]), v) / 0.25])
    for poly in mesh.polygons:
        poly.use_smooth = True
    for name, values in uvs.items():
        layer = mesh.uv_layers.new(name=name)
        for datum, value in zip(layer.data, values):
            datum.uv = value
    encoding = encode(mesh, targets)
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = Matrix.Identity(4)
    return (obj, {'plan': planned, 'topology': data, 'ideal_targets': targets, 'encoding': encoding, 'authored_field': 'Geometric facet normals and facet-local orthonormal SurfaceMeters/.25 on this concealed replacement member. This is new authorship, not old member UV/normal equivalence.', 'limits': 'C bearing seats, original base/body interface, upper closure/rail and whole-neighbor/motion checks remain open.'})
