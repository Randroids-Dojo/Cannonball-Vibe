"""Two reduced ribs with integrated, finite end feet fitted to the actual lid.

Reads current named native objects only. No file IO, source save, export or
render. Only the two rib meshes and their declared detail metadata change.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from . import ribbon_recipe02 as ribbon

NAMES = ('LOD0_TrunkRib_-1', 'LOD0_TrunkRib_1')
FOOT_LENGTH = .005
GUARD = .000001
MAXIMUM_VERTEX_EXTENSION = .0015


def unit(vector):
    vector = np.asarray(vector, dtype=float)
    size = float(np.linalg.norm(vector))
    if not math.isfinite(size) or size < 1e-12: raise ValueError('Invalid normal')
    return vector / size


def contains_xy(triangle, point):
    a, b, c = np.asarray(triangle)[:, :2]
    edges = (b-a, c-b, a-c)
    points = (point[:2]-a, point[:2]-b, point[:2]-c)
    signs = [float(e[0]*p[1]-e[1]*p[0]) for e, p in zip(edges, points)]
    # This construction choice must lie strictly inside a single actual chart.
    return min(signs) >= 0 or max(signs) <= 0


def foot_plane(lid, xs, ys, at_start):
    candidates = []
    terminal = ys[0] if at_start else ys[1]
    for index, ids in enumerate(lid['triangles']):
        tri = np.asarray([lid['vertices'][i] for i in ids])
        n = unit(np.cross(tri[1]-tri[0], tri[2]-tri[0]))
        if n[2] >= -.9: continue
        # Solve the exact complete-width interval inside this projected chart.
        sign = 1 if np.cross(tri[1]-tri[0], tri[2]-tri[0])[2] > 0 else -1
        low, high = -math.inf, math.inf
        for x in xs:
            for a, b in zip(tri, np.roll(tri, -1, axis=0)):
                ex, ey = b[0]-a[0], b[1]-a[1]
                coefficient = sign*ex
                constant = sign*(-ex*a[1]-ey*x+ey*a[0])
                if coefficient > 0: low = max(low, -constant/coefficient)
                elif coefficient < 0: high = min(high, -constant/coefficient)
                elif constant < 0: low, high = math.inf, -math.inf
        exact = [np.array((x,y,0.)) for x in xs for y in ys]
        if all(contains_xy(tri,p) for p in exact):
            actual = list(ys)
        elif at_start:
            begin = max(terminal, low+.000002)
            actual = [begin, begin+FOOT_LENGTH]
            if actual[1] > high-.000002: continue
        else:
            finish = min(terminal, high-.000002)
            actual = [finish-FOOT_LENGTH, finish]
            if actual[0] < low+.000002: continue
        inset = actual[0]-terminal if at_start else terminal-actual[1]
        if not 0 <= inset <= .015: continue
        corners = [np.array((x,y,0.)) for x in xs for y in actual]
        if not all(contains_xy(tri,p) for p in corners): continue
        candidates.append((inset,index,tri[0],n,actual))
    if not candidates: raise ValueError('No complete five-millimetre lid foot inside the declared 15 mm end region')
    inset,index,point,normal,actual = min(candidates,key=lambda row:(row[0],row[1]))
    return {'lid_triangle':index,'point':point.tolist(),'normal':normal.tolist(),
            'x':list(xs),'y':actual,'length_m':FOOT_LENGTH,'end_inset_m':inset,
            'maximum_declared_inset_m':.015,'native_chart_interior_margin_m':.000002}


def on_plane(plane, x, y):
    n, a = np.asarray(plane['normal']), np.asarray(plane['point'])
    return np.array((x, y, a[2]-(n[0]*(x-a[0])+n[1]*(y-a[1]))/n[2]))


def build_one(obj, lid):
    original = ribbon.row(obj)
    if obj.parent is None or obj.parent.name != 'Trunk_Hinge':
        raise ValueError('Actual rigid trunk parent required')
    original_frame = [list(r) for r in obj.matrix_world]
    obj, reduction = ribbon.build_one(obj, 12, 6, (0, 4, 8, 11))
    old = obj.data
    old.calc_loop_triangles()
    points = np.asarray([list(obj.matrix_world @ v.co) for v in old.vertices])
    if points.shape != (24, 3): raise ValueError('Four retained hexagonal sections required')
    station_y = points[np.arange(4)*6+4, 1]
    if not np.all(np.diff(station_y) > 0): raise ValueError('Ordered closed trunk rib required')
    if not all(abs(points[i*6+4, 1]-points[i*6+5, 1]) < 1e-12 for i in range(4)):
        raise ValueError('Actual top strip has inconsistent section stations')
    x4, x5 = points[4, 0], points[5, 0]
    if not all(abs(points[i*6+4, 0]-x4) < 1e-12 and abs(points[i*6+5, 0]-x5) < 1e-12 for i in range(4)):
        raise ValueError('Constant original top width required')
    if not .0089 < abs(x4-x5) < .0091: raise ValueError('Original nine-millimetre upper strip required')
    feet = [foot_plane(lid, sorted((float(x4), float(x5))), (float(station_y[0]), float(station_y[0]+FOOT_LENGTH)), True),
            foot_plane(lid, sorted((float(x4), float(x5))), (float(station_y[-1]-FOOT_LENGTH), float(station_y[-1])), False)]
    normal_values = [tuple(n.vector) for n in old.corner_normals]
    lookup, original_faces, reference_normals = {}, [], {}
    for poly in old.polygons:
        ids = list(poly.vertices); stations = {v//6 for v in ids}
        if len(stations) == 1:
            owner = ('cap', next(iter(stations)))
        else:
            sides = {v % 6 for v in ids}
            j = next(j for j in range(6) if sides == {j, (j+1) % 6})
            owner = ('side', j)
            reference_normals[j] = np.asarray(poly.normal)
        original_faces.append((ids, owner, poly.use_smooth))
        for vertex, loop in zip(ids, poly.loop_indices):
            lookup[owner, vertex] = {'normal': normal_values[loop],
                                    'uvs': [tuple(layer.data[loop].uv) for layer in old.uv_layers]}
    new_points = [p.copy() for p in points]
    info = {i: {'vertex': i, 'side': i % 6, 'y': float(station_y[i//6])} for i in range(24)}
    chains = {j: [i*6+j for i in range(4)] for j in range(6)}
    maximum_extension = 0.
    for side in (4, 5):
        chain = []
        all_y = sorted(set(float(v) for v in station_y) | {y for f in feet for y in f['y']})
        for y in all_y:
            matches = [i for i,value in enumerate(station_y) if abs(y-value)<1e-12]
            k = max(0,min(2,int(np.searchsorted(station_y,y)-1)))
            f = float((y-station_y[k])/(station_y[k+1]-station_y[k]))
            previous = (1-f)*points[k*6+side]+f*points[(k+1)*6+side]
            if matches: index=matches[0]*6+side
            else:
                index=len(new_points);new_points.append(previous.copy())
                info[index]={'side':side,'y':float(y)}
            foot = next((foot for foot in feet if foot['y'][0]-1e-12<=y<=foot['y'][1]+1e-12),None)
            if foot is not None:
                target=on_plane(foot,float(points[side,0]),y)
                maximum_extension=max(maximum_extension,float(np.linalg.norm(target-previous)))
                new_points[index]=target
            chain.append(index)
        chains[side]=chain
    if maximum_extension > MAXIMUM_VERTEX_EXTENSION:
        raise ValueError('Fitted end foot exceeds declared 1.5 mm local extension')
    faces, metadata = [], []
    def add(ids, owner, smooth, foot=None):
        if owner[0] == 'side':
            n = np.cross(new_points[ids[1]]-new_points[ids[0]], new_points[ids[2]]-new_points[ids[0]])
            if float(n @ reference_normals[owner[1]]) < 0: ids = list(reversed(ids))
        faces.append(ids); metadata.append((owner, smooth, foot))
    for ids, owner, smooth in original_faces:
        if owner[0] == 'side' and owner[1] in (0, 1, 2): add(ids, owner, smooth)
    for side in (3, 4, 5):
        left, right = chains[side], chains[(side+1) % 6]
        i = j = 0
        while i < len(left)-1 or j < len(right)-1:
            a = info[left[i+1]]['y'] if i < len(left)-1 else math.inf
            b = info[right[j+1]]['y'] if j < len(right)-1 else math.inf
            if abs(a-b) < 1e-12:
                ids = [left[i], right[j], right[j+1], left[i+1]]; i += 1; j += 1
            elif a < b:
                ids = [left[i], right[j], left[i+1]]; i += 1
            else:
                ids = [left[i], right[j], right[j+1]]; j += 1
            ys = [info[v]['y'] for v in ids]
            foot = None
            if side == 4:
                if min(ys) >= feet[0]['y'][0]-1e-12 and max(ys) <= feet[0]['y'][1]+1e-12: foot = 0
                elif min(ys) >= feet[1]['y'][0]-1e-12 and max(ys) <= feet[1]['y'][1]+1e-12: foot = 1
            add(ids, ('side', side), foot is None, foot)
    for ids, owner, smooth in original_faces:
        if owner[0] == 'cap': add(ids, owner, False)
    inverse = obj.matrix_world.inverted()
    mesh = bpy.data.meshes.new(obj.name+'FittedEndFeet')
    mesh.from_pydata([tuple(inverse @ Vector(p)) for p in new_points], [], faces); mesh.update()
    mesh.materials.append(old.materials[0])
    layers = [mesh.uv_layers.new(name=layer.name) for layer in old.uv_layers]
    def original_value(owner, index):
        if 'vertex' in info[index]: return lookup[owner, info[index]['vertex']]
        y, side = info[index]['y'], info[index]['side']
        k = max(0, min(2, int(np.searchsorted(station_y, y)-1)))
        f = float((y-station_y[k])/(station_y[k+1]-station_y[k]))
        a, b = lookup[owner, k*6+side], lookup[owner, (k+1)*6+side]
        return {'normal': unit((1-f)*np.asarray(a['normal'])+f*np.asarray(b['normal'])),
                'uvs': [(1-f)*np.asarray(x)+f*np.asarray(z) for x, z in zip(a['uvs'], b['uvs'])]}
    targets = []; feet_polygons = [[], []]; retained_uvs = 0
    for poly, (owner, smooth, foot) in zip(mesh.polygons, metadata):
        poly.use_smooth = smooth
        if foot is not None: feet_polygons[foot].append(poly.index)
        for index, loop in zip(poly.vertices, poly.loop_indices):
            original_value_at_corner = original_value(owner, index)
            for layer, uv in zip(layers, original_value_at_corner['uvs']): layer.data[loop].uv = uv
            if 'vertex' in info[index]: retained_uvs += 1
            if foot is not None:
                target = -np.asarray(feet[foot]['normal'])
            elif owner[0] == 'cap':
                target = np.asarray(poly.normal)
            else:
                target = np.asarray(original_value_at_corner['normal'])
            # Only rotation is present; protect this assumption explicitly below.
            targets.append(tuple(unit(target)))
    if not np.allclose(np.asarray(obj.matrix_world.to_3x3()), np.eye(3), rtol=0, atol=1e-12):
        raise ValueError('This fitted source-local recipe requires the existing identity rotation/scale')
    mesh.normals_split_custom_set(targets); mesh.update(); mesh.calc_loop_triangles()
    actual = [tuple(v.vector) for v in mesh.corner_normals]
    error = max(ribbon.angle(a, b) for a, b in zip(actual, targets))
    if error > .025: raise ValueError('Fitted field target-to-native guard: '+str(error))
    if not 28 <= len(mesh.vertices) <= 32 or len(mesh.loop_triangles) != 2*len(mesh.vertices)-4: raise ValueError('Fitted rib exceeds the declared 52 to 60 triangle budget')
    untouched_vertices = [i for i in range(24) if np.array_equal(new_points[i],points[i])]
    for i in untouched_vertices:
        if tuple(mesh.vertices[i].co) != tuple(old.vertices[i].co): raise ValueError('Unselected retained vertex changed')
    obj.data = mesh
    obj['ribbon_detail_form'] = 'Four retained body sections with two integrated 5 mm lid-fitted end feet'
    bpy.context.view_layer.update()
    if [list(r) for r in obj.matrix_world] != original_frame: raise ValueError('Rigid trunk transform changed')
    report = {'name': obj.name, 'original_triangles': 140, 'new_triangles': len(mesh.loop_triangles), 'triangle_delta': len(mesh.loop_triangles)-140,
              'vertices': len(mesh.vertices), 'unchanged_retained_vertex_indices': untouched_vertices,
              'retained_corner_uv_count': retained_uvs, 'maximum_upper_extension_m': maximum_extension,
              'maximum_target_to_native_degrees': error, 'feet': [], 'reduction': reduction,
              'new_corner_targets': targets, 'new_faces': faces, 'new_face_owners': metadata,
              'normal_scope': 'Original targets on unchanged side domains; actual fitted lid plane on end feet and actual planar normals on changed end caps.',
              'source_saved': False}
    for i, plane in enumerate(feet):
        report['feet'].append({**plane, 'polygon_indices': feet_polygons[i],
                              'triangle_indices': [t.index for t in mesh.loop_triangles if t.polygon_index in feet_polygons[i]]})
    return obj, report


def build():
    if any(name not in bpy.data.objects for name in (*NAMES, 'LOD0_Trunk')): raise ValueError('Exact rib/lid semantic inventory required')
    lid = ribbon.row(bpy.data.objects['LOD0_Trunk'])
    if lid['ancestors'][0] != 'Trunk_Hinge': raise ValueError('Actual same-rigid lid required')
    result = [build_one(bpy.data.objects[name], lid) for name in NAMES]
    return [row[0] for row in result], [row[1] for row in result]
