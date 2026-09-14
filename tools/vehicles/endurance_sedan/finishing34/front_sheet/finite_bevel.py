"""Actual generated 1.2 mm bevel transitions adjacent to owned outer sheet.

Original sheet edges fix the new field. Independently protected manufactured
faces never receive targets. Their existing bevel-side limits remain fixed
except at a common original-sheet corner, where the original-sheet limit owns
the exterior and the real manufactured split is measured separately.
"""
import collections
import json
import math

from . import field_support as support
from . import sheet_reference as sheet
from . import manufactured


def prepare(state, original, projection, return_profile):
    import numpy as np
    points, tris = state['points'], state['triangles']
    attrs = state['attrs']
    tag, strength = attrs['cb_fascia_cap'], attrs['__mod_weightednormals_faceweight']
    before, targets = state['normals'], list(original['targets'])
    selected_sheet = set(original['selected_faces'])
    return_domains = manufactured.radial_returns(state, return_profile)
    return_faces = {row['face'] for row in return_domains}
    rows, by_face, edges = [], collections.defaultdict(list), collections.defaultdict(list)
    face_edges = collections.defaultdict(set)
    for ti, t in enumerate(tris):
        ps = [tuple(points[v]) for v in t['vertices']]
        row = {'triangle': ti, 'face': t['face'], 'points': ps, 'box': support._box(ps)}
        rows.append(row)
        by_face[t['face']].append(row)
        ids = t['vertices']
        for a, b in zip(ids, ids[1:]+ids[:1]):
            key = tuple(sorted((a, b)))
            if t['face'] not in edges[key]:
                edges[key].append(t['face'])
            face_edges[t['face']].add(key)
    # Ignore triangulation diagonals inside a polygon when collecting its
    # true boundary. Every actual adjacent face remains in the inventory.
    face_edges = {fi: {e for e in es if len(edges[e]) == 2} for fi, es in face_edges.items()}
    references = [r for r in rows if r['face'] in selected_sheet]
    eligible = {}
    for fi, rs in by_face.items():
        if fi in selected_sheet or fi in return_faces or tag[fi] != 0 or strength[fi] not in (-16384, 0):
            continue
        # Constant-axis opening/closure facets are manufactured planes, not
        # permission for smoothing the adjoining physical return.
        if all(max(abs(v) for v in sheet.normal(r['points'])) >= .999 for r in rs):
            continue
        complete = []
        for row in rs:
            owned = support._whole_near(row['points'], references, projection.closest)
            if owned is None:
                break
            complete.append({'triangle': row['triangle'], **owned})
        else:
            eligible[fi] = complete
    seeds = {fi for e, fs in edges.items() if any(f in selected_sheet for f in fs) for fi in fs if fi in eligible}
    selected = set(seeds)
    pending = list(seeds)
    while pending:
        fi = pending.pop()
        for e in face_edges[fi]:
            for other in edges[e]:
                if other in eligible and other not in selected:
                    selected.add(other)
                    pending.append(other)
    if not selected:
        raise ValueError('No complete actual finite generated bevels')
    vertex_loops = collections.defaultdict(list)
    for fi in selected:
        for li in state['face_loops'][fi]:
            vertex = next(t['vertices'][t['loops'].index(li)] for t in tris if t['face'] == fi and li in t['loops'])
            vertex_loops[vertex].append(li)
    constraints, boundary = collections.defaultdict(list), []
    for edge, fs in sorted(edges.items()):
        inside = [fi for fi in fs if fi in selected]
        if len(fs) != 2 or len(inside) != 1:
            continue
        fi = inside[0]
        other = next(f for f in fs if f != fi)
        kind = 'owned_original_sheet' if other in selected_sheet else 'protected_manufactured_boundary'
        item = {'vertices': edge, 'bevel_face': fi, 'other_face': other, 'kind': kind, 'conditions': []}
        for vi in edge:
            loops = [next(t['loops'][t['vertices'].index(vi)] for t in tris if t['face'] == f and vi in t['vertices']) for f in (fi, other)]
            value = targets[loops[1]] if kind == 'owned_original_sheet' else before[loops[0]]
            entry = {'bevel_loop': loops[0], 'other_loop': loops[1], 'kind': kind, 'target': value,
                     'other_target': targets[loops[1]], 'edge': edge, 'bevel_face': fi, 'other_face': other}
            constraints[vi].append(entry)
            item['conditions'].append(entry)
        boundary.append(item)
    fixed, conditions, protected_corner_limits = {}, [], {}
    for vi, rs in sorted(constraints.items()):
        original_rows = [r for r in rs if r['kind'] == 'owned_original_sheet']
        chosen = original_rows or rs
        value = sheet.unit(tuple(sum(r['target'][i] for r in chosen) for i in range(3)))
        error = max(support.angle(value, r['target']) for r in chosen)
        record = {'vertex': vi, 'position': points[vi], 'conditions': rs, 'fixed_target': value,
                  'maximum_fixed_error_degrees': error, 'original_sheet_limit_owns_exterior': bool(original_rows)}
        conditions.append(record)
        if original_rows and error > .025:
            raise ValueError('Incompatible actual finite shoulder boundary: '+json.dumps(record))
        if not original_rows:
            # A manufactured boundary may already have distinct per-corner
            # limits. Preserve each actual limit; do not flatten them to the
            # consensus used only as the interior rotation boundary condition.
            for li in vertex_loops[vi]:
                protected_corner_limits[li] = tuple(before[li])
        fixed[vi] = value
    graph = {vi: {} for vi in vertex_loops}
    for fi in selected:
        for row in by_face[fi]:
            ids = tris[row['triangle']]['vertices']
            for a, b in zip(ids, ids[1:]+ids[:1]):
                distance = math.dist(points[a], points[b])
                if distance == 0:
                    raise ValueError('Degenerate actual generated bevel edge')
                graph[a][b] = graph[b][a] = 1/distance
    tangents = {vi: [0., 0., 0.] for vi in vertex_loops}
    for fi in selected:
        for row in by_face[fi]:
            ids = tris[row['triangle']]['vertices']
            gn = sheet.normal(row['points'])
            for vi in ids:
                vs = [v for v in ids if v != vi]
                weight = math.radians(support.angle(sheet.sub(points[vs[0]], points[vi]), sheet.sub(points[vs[1]], points[vi])))
                for axis in range(3):
                    tangents[vi][axis] += weight*gn[axis]
    base = {vi: sheet.unit(n) for vi, n in tangents.items()}

    def log_rotation(a, b):
        axis = sheet.cross(a, b)
        sine = math.hypot(*axis)
        theta = math.atan2(sine, sum(x*y for x, y in zip(a, b)))
        if theta < 1e-12:
            return (0., 0., 0.)
        if sine < 1e-12:
            raise ValueError('Ambiguous finite bevel rotation')
        return tuple(theta*v/sine for v in axis)

    def rotate(a, r):
        theta = math.hypot(*r)
        if theta < 1e-12:
            return a
        axis = tuple(v/theta for v in r)
        crossed = sheet.cross(axis, a)
        dot = sum(x*y for x, y in zip(a, axis))
        return sheet.unit(tuple(math.cos(theta)*a[i]+math.sin(theta)*crossed[i]+(1-math.cos(theta))*dot*axis[i] for i in range(3)))

    free = sorted(set(vertex_loops)-set(fixed))
    at = {vi: i for i, vi in enumerate(free)}
    matrix = np.zeros((len(free), len(free)))
    rhs = np.zeros((len(free), 3))
    rotations = {vi: log_rotation(base[vi], n) for vi, n in fixed.items()}
    for vi in free:
        i = at[vi]
        for other, weight in graph[vi].items():
            matrix[i, i] += weight
            if other in at:
                matrix[i, at[other]] -= weight
            else:
                rhs[i] += weight*np.asarray(rotations[other])
    field = dict(fixed)
    residual = 0.
    if free:
        solution = np.linalg.solve(matrix, rhs)
        residual = float(np.max(np.abs(matrix@solution-rhs)))
        for vi, r in zip(free, solution):
            field[vi] = rotate(base[vi], tuple(float(v) for v in r))
    for vi, loops in vertex_loops.items():
        for li in loops:
            targets[li] = protected_corner_limits.get(li, field[vi])
    return {'object': state['object'], 'targets': targets, 'selected_faces': sorted(selected_sheet|selected),
            'selected_triangles': [ti for ti, t in enumerate(tris) if t['face'] in selected_sheet|selected],
            'original_sheet_faces': sorted(selected_sheet), 'bevel_faces': sorted(selected),
            'complete_original_ownership': original['complete_original_ownership'],
            'complete_bevel_geometry': [{'face': fi, 'triangles': eligible[fi]} for fi in sorted(selected)],
            'fixed_conditions': conditions, 'boundary': boundary, 'harmonic_residual': residual,
            'preserved_actual_manufactured_corner_limits': [{'loop': li, 'target': n} for li, n in sorted(protected_corner_limits.items())],
            'authorship': 'Actual finite generated bevel tangents; harmonic rotation to owned original sheet and protected manufactured limits',
            'bevel_width_m': .0012, 'complete_geometry_guard_m': 1e-6,
            'independently_protected_complete_return_facets': return_domains,
            'protected_manufactured_faces_receive_no_targets': True}
