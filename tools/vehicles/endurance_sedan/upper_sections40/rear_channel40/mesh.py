"""Actual-input rear-channel construction primitive."""
import copy, math
from collections import defaultdict
from .vectors import (initial, f32, mix, sub, dot, cross, unit, normal,
                          area, clip, orient)

def empty(old, ideal=None):
    r = initial(old, ideal)
    for k in ('triangles', 'owners', 'triangle_materials', 'normal_corner_targets'):
        r[k] = []
    r['uv_corner_targets'] = {n: [] for n in old['uvs']}
    r['domains'] = []
    return r

def old_face(r, old, fi, ideal=None):
    init = ideal or {'normal_corner_targets': [[old['normals'][l] for l in ls]
                                               for ls in old['triangle_loops']],
                     'uv_corner_targets': {n: [[uv[l] for l in ls] for ls in old['triangle_loops']]
                                           for n, uv in old['uvs'].items()}}
    r['triangles'].append(old['triangles'][fi][:])
    r['owners'].append(fi)
    r['triangle_materials'].append(old['triangle_materials'][fi])
    r['normal_corner_targets'].append(copy.deepcopy(init['normal_corner_targets'][fi]))
    for n, uv in init['uv_corner_targets'].items():
        r['uv_corner_targets'][n].append(copy.deepcopy(uv[fi]))
    r['domains'].append('retained')

def new_face(r, t, domain, material=0, owner=None, uv=None, ns=None):
    if len(set(t)) != 3 or area(r['vertices'], t) <= 1e-14:
        raise ValueError(('Degenerate authored face', domain, t))
    r['triangles'].append(list(t))
    r['owners'].append(owner)
    r['triangle_materials'].append(material)
    n = normal(r['vertices'], t)
    r['normal_corner_targets'].append(copy.deepcopy(ns or [n, n, n]))
    axis = max(range(3), key=lambda k: abs(n[k]))
    axes = [k for k in range(3) if k != axis]
    for name in r['uv_corner_targets']:
        values = uv[name] if uv else [[r['vertices'][v][k]/.25 for k in axes] for v in t]
        r['uv_corner_targets'][name].append(values)
    r['domains'].append(domain)

def set_geometric_new_fields(r, start=0):
    for i in range(start, len(r['triangles'])):
        if r['domains'][i] == 'retained':
            continue
        n = normal(r['vertices'], r['triangles'][i])
        r['normal_corner_targets'][i] = [n[:], n[:], n[:]]

def ear_indices(poly):
    """Triangulate a finite ordered convex clipped polygon, keeping all edges."""
    if len(poly) == 3:
        return [[0, 1, 2]]
    best = max((cross(sub(poly[j], poly[0]), sub(poly[j+1], poly[0]))
                for j in range(1, len(poly)-1)), key=lambda n: dot(n, n))
    axis = max(range(3), key=lambda k: abs(best[k]))
    axes = [k for k in range(3) if k != axis]
    ps = [[p[k] for k in axes] for p in poly]
    def cr(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    sign = 1 if sum(cr([0, 0], a, b) for a, b in zip(ps, ps[1:]+ps[:1])) > 0 else -1
    ids = list(range(len(poly))); out = []
    while len(ids) > 3:
        choices = []
        for j, b in enumerate(ids):
            a, c = ids[j-1], ids[(j+1)%len(ids)]
            ar = sign*cr(ps[a], ps[b], ps[c])
            if ar <= 1e-14:
                continue
            if any(min(sign*cr(ps[a], ps[b], ps[v]), sign*cr(ps[b], ps[c], ps[v]),
                       sign*cr(ps[c], ps[a], ps[v])) >= -1e-16
                   for v in ids if v not in (a, b, c)):
                continue
            choices.append((ar, j, [a, b, c]))
        if not choices:
            raise ValueError(('No finite polygon ear', ps, ids))
        _, j, tri = max(choices)
        out.append(tri); ids.pop(j)
    out.append(ids)
    return out
