"""Complete native sheet ownership and current construction carriers.

Only plain attribution/target arrays are built here. No mesh is installed,
constructed, saved or exported. References must be captured by the caller from
the actual corresponding construction, and bound independently to that source.
"""
import collections
import math

from . import field_support as support

GUARD = 1e-6
CORNER = 2e-6
ALIGNMENT = .99985
NORMAL = .025
SEMANTICS = ('LOD0_FrontFender_L', 'LOD0_FrontFender_R', 'LOD0_FrontBumper')


def unit(v):
    length = math.hypot(*v)
    if not math.isfinite(length) or length <= 0:
        raise ValueError('Invalid sheet vector')
    return tuple(float(x) / length for x in v)


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def cross(a, b):
    return a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]


def normal(ps):
    return unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))


def numeric(v, length):
    return (type(v) in (list, tuple) and len(v) == length
            and all(type(x) in (int, float) and math.isfinite(x) for x in v))


def validate_reference(ref):
    if set(ref) != {'schema', 'object', 'matrix_world', 'vertices', 'triangles', 'normals', 'source_kind', 'face_domains'}:
        raise ValueError('Invalid actual reference schema')
    if ref['schema'] != 'actual-original-front-sheet.v1' or ref['source_kind'] != 'actual-pre-voids-native':
        raise ValueError('Reference is not an actual pre-voids native capture')
    if ref['object'] != 'LOD0_StructuralBody':
        raise ValueError('Wrong original sheet semantic')
    matrix = ref['matrix_world']
    if (type(matrix) not in (list, tuple) or len(matrix) != 4
            or not all(numeric(r, 4) for r in matrix)
            or matrix != [[float(i == j) for j in range(4)] for i in range(4)]):
        raise ValueError('Original sheet must use the actual ground frame')
    ps, ts, ns = ref['vertices'], ref['triangles'], ref['normals']
    if not ps or not ts or len(ns) != len(ts) or not all(numeric(p, 3) for p in ps):
        raise ValueError('Incomplete original geometry')
    if (len(ref['face_domains']) != len(ts)
            or any(type(r) is not dict or set(r) != {'marker', 'strength'}
                   or type(r['marker']) is not int or r['marker'] not in (0, 1, 2)
                   or type(r['strength']) is not int or r['strength'] not in (-16384, 0, 16384)
                   for r in ref['face_domains'])):
        raise ValueError('Missing/malformed actual original FACE domains')
    seen = set()
    for tri, values in zip(ts, ns):
        if (type(tri) not in (list, tuple) or len(tri) != 3 or len(set(tri)) != 3
                or any(type(i) is not int or not 0 <= i < len(ps) for i in tri)):
            raise ValueError('Invalid reference triangle indices')
        key = tuple(sorted(tri))
        if key in seen:
            raise ValueError('Duplicate original reference triangle')
        seen.add(key)
        normal([ps[i] for i in tri])
        if len(values) != 3 or not all(numeric(n, 3) and abs(math.hypot(*n)-1) <= 1e-6 for n in values):
            raise ValueError('Invalid original native normal field')


def capture_original(obj):
    """Call on actual original StructuralBody immediately before its void cuts."""
    if obj.type != 'MESH' or obj.modifiers:
        raise ValueError('Capture the evaluated actual original sheet first')
    mesh = obj.data
    mesh.calc_loop_triangles()
    ns = [tuple(n.vector) for n in mesh.corner_normals]
    attributes = []
    for key in ('cb_fascia_cap', '__mod_weightednormals_faceweight'):
        a = mesh.attributes.get(key)
        if a is None or a.domain != 'FACE' or a.data_type != 'INT':
            raise ValueError('Original native capture lacks actual FACE provenance')
        attributes.append(a)
    result = {'schema': 'actual-original-front-sheet.v1', 'object': obj.name,
              'matrix_world': [list(r) for r in obj.matrix_world],
              'vertices': [list(v.co) for v in mesh.vertices],
              'triangles': [list(t.vertices) for t in mesh.loop_triangles],
              'normals': [[list(ns[i]) for i in t.loops] for t in mesh.loop_triangles],
              'face_domains': [{'marker': attributes[0].data[t.polygon_index].value,
                               'strength': attributes[1].data[t.polygon_index].value} for t in mesh.loop_triangles],
              'source_kind': 'actual-pre-voids-native'}
    validate_reference(result)
    return result


class Patch:
    def __init__(self, points, normals, ownership, projection, ids=None):
        import numpy as np
        self.np = np
        self.ps = [[tuple(p) for p in tri] for tri in points]
        self.ns = [[tuple(n) for n in values] for values in normals]
        self.ids = list(range(len(points))) if ids is None else list(ids)
        if len(self.ps) != len(self.ns) or len(self.ids) != len(self.ps) or len(set(self.ids)) != len(self.ids):
            raise ValueError('Incomplete unique actual carrier')
        self.ownership, self.projection = ownership, projection
        self.gn = np.asarray([normal(ps) for ps in self.ps])
        self.array = np.asarray(self.ps)
        self.low, self.high = self.array.min(axis=1), self.array.max(axis=1)
        flat = [p for tri in self.ps for p in tri]
        indices = [list(range(i, i+3)) for i in range(0, len(flat), 3)]
        self.patch = ownership._patch((None, flat, indices, self.ns))

    def candidates(self, ps):
        a = self.np.asarray(ps)
        keep = ((self.gn @ self.np.asarray(normal(ps)) >= ALIGNMENT)
                & self.np.all(self.low <= a.max(axis=0)+GUARD, axis=1)
                & self.np.all(self.high >= a.min(axis=0)-GUARD, axis=1))
        ids = self.np.flatnonzero(keep).tolist()
        return [i for i in ids if max(abs(float(self.np.dot(self.np.asarray(p)-self.array[i, 0], self.gn[i]))) for p in ps) <= GUARD]

    def owner(self, ps, *, target=True):
        ps = [tuple(p) for p in ps]
        ids = self.candidates(ps)
        exact = [i for i in ids if set(ps) == set(self.ps[i])]
        if len(exact) > 1:
            raise ValueError('Duplicate coincident actual reference ownership')
        if exact:
            # An unchanged complete oriented triangle has an exact actual
            # owner. Its manufactured per-corner limits must not be averaged
            # with a different neighboring face touching the same vertex.
            ids = exact
        if not ids or not self.ownership._covers(ps, [self.patch[i] for i in ids]):
            return None
        result = {'reference_triangles': [self.ids[i] for i in ids], 'exact_oriented_triangle': bool(exact), 'complete_geometry_guard_m': GUARD,
                  'corner_guard_m': CORNER, 'uncovered_fragments': 0}
        if not target:
            return result
        values, corners = [], []
        for p in ps:
            choices = []
            for i in ids:
                distance, weights = self.projection.closest(p, self.ps[i])
                if distance <= CORNER:
                    value = unit(self.projection.interpolate(self.ns[i], weights))
                    choices.append((distance, self.ids[i], value, tuple(weights)))
            if not choices:
                raise ValueError('Complete fragment has no bounded actual corner lookup')
            best = min(choices, key=lambda r: r[:2])
            ties = [r for r in choices if r[0] <= best[0]+1e-9]
            spread = max(support.angle(best[2], r[2]) for r in ties)
            if spread > NORMAL:
                return None
            values.append(best[2])
            corners.append({'distance_m': best[0], 'reference_triangle': best[1],
                            'weights': best[3], 'tied_field_spread_degrees': spread})
        result.update(targets=values, corners=corners)
        return result


def original_patch(ref, ownership, projection):
    validate_reference(ref)
    indices = [i for i, row in enumerate(ref['face_domains']) if row['marker'] == 0]
    return Patch([[ref['vertices'][i] for i in ref['triangles'][ti]] for ti in indices],
                 [ref['normals'][ti] for ti in indices], ownership, projection, indices)


def native_state(obj):
    """Small actual native state; no report or constructor assumptions."""
    from mathutils import Matrix
    if obj.name not in SEMANTICS or obj.type != 'MESH' or obj.modifiers or obj.matrix_world != Matrix.Identity(4):
        raise ValueError('Expected actual ground-frame front mesh')
    mesh = obj.data
    mesh.calc_loop_triangles()
    attrs = {}
    for key in ('cb_fascia_cap', '__mod_weightednormals_faceweight'):
        a = mesh.attributes.get(key)
        if a is not None:
            if a.domain != 'FACE' or a.data_type != 'INT':
                raise ValueError('Malformed actual FACE ownership')
            attrs[key] = [v.value for v in a.data]
    return {'object': obj.name, 'points': [tuple(v.co) for v in mesh.vertices],
            'triangles': [{'face': t.polygon_index, 'vertices': list(t.vertices), 'loops': list(t.loops)} for t in mesh.loop_triangles],
            'face_loops': [list(p.loop_indices) for p in mesh.polygons],
            'normals': [tuple(n.vector) for n in mesh.corner_normals], 'attrs': attrs}


def state_from_capture(state):
    attrs = state['physical']['attributes']
    result = {'object': state['object'], 'points': state['physical']['vertices'], 'triangles': state['triangles'],
              'face_loops': [f['loops'] for f in state['faces']], 'normals': state['normals'], 'attrs': {}}
    for key in ('cb_fascia_cap', '__mod_weightednormals_faceweight'):
        if key in attrs:
            if attrs[key][:2] != ['FACE', 'INT']:
                raise ValueError('Malformed construction FACE ownership')
            result['attrs'][key] = attrs[key][2]
    return result


def prepare_sheet(state, patch):
    if state['object'] not in SEMANTICS:
        raise ValueError('Wrong current sheet semantic')
    attrs = state['attrs']
    if set(attrs) != {'cb_fascia_cap', '__mod_weightednormals_faceweight'}:
        raise ValueError('Missing actual pre-operation FACE provenance')
    tag, strength = attrs['cb_fascia_cap'], attrs['__mod_weightednormals_faceweight']
    if (len(tag) != len(state['face_loops']) or len(strength) != len(tag)
            or any(type(i) is not int or i not in (0, 1, 2) for i in tag)
            or any(type(i) is not int or i not in (-16384, 0, 16384) for i in strength)):
        raise ValueError('Invalid actual ownership inventory')
    by_face = collections.defaultdict(list)
    for ti, tri in enumerate(state['triangles']):
        by_face[tri['face']].append((ti, tri))
    targets = [tuple(n) for n in state['normals']]
    records, protected = [], []
    selected = set()
    for fi, loops in enumerate(state['face_loops']):
        if tag[fi] != 0 or strength[fi] != 16384:
            protected.append({'face': fi, 'reason': 'independent-manufactured-or-generated', 'marker': tag[fi], 'strength': strength[fi]})
            continue
        complete, requests = [], collections.defaultdict(list)
        for ti, tri in by_face[fi]:
            ps = [state['points'][vi] for vi in tri['vertices']]
            owner = patch.owner(ps)
            if owner is None:
                break
            for li, value in zip(tri['loops'], owner['targets']):
                requests[li].append(value)
            complete.append({'triangle': ti, 'vertices': tri['vertices'], 'points': ps, **owner})
        else:
            if set(requests) != set(loops):
                raise ValueError('Incomplete owned face corner inventory')
            if any(max(support.angle(a, b) for a in rows for b in rows) > NORMAL for rows in requests.values()):
                raise ValueError('One actual loop has incompatible original fields')
            for li, rows in requests.items():
                targets[li] = rows[0]
            selected.add(fi)
            records.append({'face': fi, 'complete_triangles': complete})
            continue
        protected.append({'face': fi, 'reason': 'not-completely-owned-original-sheet', 'marker': tag[fi], 'strength': strength[fi]})
    if not selected:
        raise ValueError('No actual original outer sheet was completely owned')
    selected_triangles = [ti for ti, tri in enumerate(state['triangles']) if tri['face'] in selected]
    return {'object': state['object'], 'targets': targets, 'selected_faces': sorted(selected),
            'selected_triangles': selected_triangles, 'complete_original_ownership': records,
            'protected_faces': protected, 'reference_geometry_guard_m': GUARD,
            'corner_lookup_guard_m': CORNER, 'scope': 'Actual corresponding original outer sheet; independent manufactured fields excluded'}
