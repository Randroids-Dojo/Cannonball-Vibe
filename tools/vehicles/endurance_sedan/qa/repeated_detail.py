"""Independent repeated-detail source replay and current assembly certificates.

Only disposable in-memory replay/intersection objects are authored. Sources,
constructors and supplied payloads are read-only; no saves, exports or renders.
"""
import argparse
from datetime import datetime, timezone
from functools import lru_cache
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import numpy as np
from mathutils import Vector
import repeated_detail_report as report
from gate import artifact, load_source_binding, sha, strict_json
from geometry import bounds, box_distance2, tree, triangle_distance
from surface_minimum import Distances
from initial_containment import check_pair
from solid_interfaces import boundary_shell, intersection, shape_quality
from finish_interfaces import partition
from self_geometry import scan
import shoulder_checkpoint

require = report.require
digest = report.digest


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False,
        default=lambda item: item.tolist() if hasattr(item, 'tolist') else
        (_ for _ in ()).throw(TypeError(type(item).__name__))))


def load_file(name, path):
    path = path.resolve(strict=True)
    before = sha(path)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Missing independent native checker')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        require(Path(module.__file__).resolve() == path and sha(path) == before,
                'Changed independent checker while loading')
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def uv_comparison(a, b, label):
    require(set(a) == set(b), 'UV layer inventory changed: ' + label)
    rows = []
    for key in sorted(a):
        require(len(a[key]) == len(b[key]) and all(len(x) == len(y) == 2 for x, y in zip(a[key], b[key])),
                'UV corner inventory changed: ' + label)
        values = [abs(x-y) for u, v in zip(a[key], b[key]) for x, y in zip(u, v)]
        require(all(math.isfinite(v) for v in values), 'Nonfinite UV residual')
        maximum = max(values, default=0.)
        require(maximum <= 1e-5, 'Evaluated UV residual exceeds unchanged guard: ' + label)
        rows.append({'layer': key, 'corners': len(a[key]), 'maximum_absolute': maximum, 'exact': maximum == 0})
    return rows


def compare_evaluated(a, b, label):
    require(set(a) == set(b), 'Evaluated field inventory changed: ' + label)
    require({k: v for k, v in a.items() if k != 'uvs'} == {k: v for k, v in b.items() if k != 'uvs'},
            'Evaluated geometry/normal/material/rig field changed: ' + label)
    return uv_comparison(a['uvs'], b['uvs'], label)


def compare_captures(a, b, label):
    require(set(a) == set(b) == {'raw', 'evaluated'}, 'Wrong complete native capture: ' + label)
    require(a['raw'] == b['raw'], 'Raw native field changed: ' + label)
    return compare_evaluated(a['evaluated'], b['evaluated'], label)


def inventory(module, checker, api, recipe, modifier_capture):
    bpy.context.view_layer.update()
    objects = checker.objects(api, recipe, modifier_capture)
    native = {obj.name: module.capture(obj) for obj in bpy.data.objects if obj.type == 'MESH'}
    materials = {obj.name: shoulder_checkpoint.material_fields(obj.data)
                 for obj in bpy.data.objects if obj.type == 'MESH'}
    extra = {}
    for obj in bpy.data.objects:
        row = {'constraints': [{'name': c.name, 'type': c.type, 'values': shoulder_checkpoint.rna_values(c)}
                              for c in obj.constraints]}
        if obj.type in ('LIGHT', 'CAMERA', 'FONT'):
            row['data'] = shoulder_checkpoint.rna_values(obj.data)
            row['data_animation'] = checker.animation(obj.data)
        extra[obj.name] = row
    material_drivers = {material.name: checker.animation(material.node_tree)
                       for material in bpy.data.materials if material.node_tree}
    return plain({'objects': objects, 'native': native, 'materials': materials,
                  'extra': extra, 'material_drivers': material_drivers})


def compare_inventories(a, b, *, excluded=()):
    require(set(a) == set(b), 'Native inventory sections changed')
    excluded = set(excluded)
    for key in ('objects', 'native', 'materials', 'extra'):
        require(set(a[key]) == set(b[key]), 'Missing or extra native objects: ' + key)
        for name in a[key]:
            if name in excluded:
                continue
            require(a[key][name] == b[key][name] if key != 'native' else True,
                    'Unrelated original native field changed: ' + key + '/' + name)
    require(a['material_drivers'] == b['material_drivers'], 'Material drivers changed')
    uv = {}
    for name in a['native']:
        if name not in excluded:
            uv[name] = compare_captures(a['native'][name], b['native'][name], name)
    return {'object_names': sorted(set(a['objects'])-excluded),
            'mesh_names': sorted(set(a['native'])-excluded), 'evaluated_uv': uv}


def world_row(name, native):
    row = native['evaluated']
    return {'name': name, **row, 'vertices': row['world_vertices'],
            'properties': native['raw']['properties'],
            'ancestors': [a['name'] for a in native['raw']['ancestors']]}


def finite_area(row):
    points = np.asarray(row['vertices'], dtype=float)
    return [float(np.linalg.norm(np.cross(points[b]-points[a], points[c]-points[a])))*.5
            for a, b, c in row['triangles']]


def shell(mesh, target, maximum):
    sizes = finite_area(target)
    keep = [i for i, a in enumerate(sizes) if a > 0 and math.isfinite(a)]
    require(keep and mesh['triangles'], 'Empty/degenerate finite support target or input')
    narrowed = {**target, 'triangles': [target['triangles'][i] for i in keep]}
    with np.errstate(all='raise'):
        value = boundary_shell(mesh, narrowed, maximum=maximum)
    require(value['status'] == 'passed', 'Incomplete finite boundary coverage: ' + str(value))
    return {**value, 'maximum_allowed_m': maximum, 'positive_target_triangles': len(keep),
            'omitted_zero_area_target_indices': [i for i in range(len(sizes)) if i not in keep],
            'complete_input_triangles_including_boundary_sheets': len(mesh['triangles'])}


def embedded(before, after):
    quality = [shape_quality(row['vertices'], row['triangles']) if row['triangles'] else None
               for row in (before, after)]
    require(all(q and q['signed_volume_m3'] > 0 and q['nonmanifold_edges'] == 0
                and q['duplicate_triangles'] == 0 for q in quality), 'Missing closed positive-volume embedded stock')
    areas = [math.fsum(finite_area(row)) for row in (before, after)]
    require(min(areas) > 1e-12, 'Degenerate finite stock area')
    return {'quality': quality, 'positive_surface_area_m2': areas,
            'complete_boundary': [shell(before, after, 2e-7), shell(after, before, 2e-7)]}


def cap(row):
    y = min(p[1] for p in row['vertices'])
    faces = [t for t in row['triangles'] if all(row['vertices'][i][1] == y for i in t)]
    return {**row, 'triangles': faces}, y


def fin(before, after, receiver):
    original, y0 = cap(before)
    current, y = cap(after)
    corners = lambda row: sorted({tuple(row['vertices'][i]) for t in row['triangles'] for i in t})
    require(corners(original) == corners(current) and len(corners(current)) == 4 and y == y0,
            'Complete original fin landing changed')
    areas = [math.fsum(finite_area(row)) for row in (original, current)]
    require(min(areas) > 1e-12, 'Missing positive-area fin landing')
    halfspaces = {'receiver_maximum_y': max(p[1] for p in receiver['vertices']),
                  'fin_minimum_y': min(p[1] for p in after['vertices']), 'plane_y': y}
    require(halfspaces['receiver_maximum_y'] <= y+1e-6 and halfspaces['fin_minimum_y'] >= y-1e-6,
            'Complete fin/receiver stock halfspaces changed')
    return {'original_y': y0, 'candidate_y': y, 'landing_vertices': [list(p) for p in corners(current)],
            'positive_cap_area_m2': areas, 'halfspaces': halfspaces,
            'full_cap_coverage': [shell(original, current, 2e-7), shell(current, original, 2e-7),
                                  shell(current, receiver, 1e-6)]}


def finite_proof(before, current):
    rows = []
    for name in report.NAMES:
        receiver = report.receiver(name)
        if name in report.FINS:
            value = fin(before[name], current[name], current[receiver])
            kind = 'fin_landing'
        else:
            old = intersection(before[name], before[receiver])
            new = intersection(current[name], current[receiver])
            old['name'], new['name'] = name+'_old_stock', name+'_new_stock'
            value = {**embedded(old, new), 'original_intersection': old, 'current_intersection': new}
            kind = 'embedded_rib'
        rows.append({'name': name, 'pair': [name, receiver], 'kind': kind, **value})
    return rows


def rest_proof(rows):
    expected = report.rest_pairs(rows)
    joints = {tuple(sorted((name, report.receiver(name)))) for name in report.NAMES}
    distance = Distances(rows)
    boxes = {name: bounds(row['vertices']) for name, row in rows.items()}
    cache, checks = {}, []
    for pair in expected:
        if pair in joints:
            continue
        a, b = pair
        lower = math.sqrt(box_distance2(boxes[a], boxes[b]))
        if lower >= .001001:
            checks.append({'pair': list(pair), 'method': 'whole_aabb', 'lower_bound_m': lower})
        else:
            minimum = distance.minimum(a, b)
            require(minimum['distance_m'] >= .001001, 'Current nonmate gap: ' + str((pair, minimum)))
            containment = check_pair(rows, pair, cache)
            require(containment['status'] in ('outside_by_disjoint_rest_aabbs', 'outside_by_components_and_parity'),
                    'Current nonmate containment: ' + str(containment))
            checks.append({'pair': list(pair), 'method': 'complete_triangles_and_containment',
                           'minimum': minimum, 'containment': containment})
    return {'all_pairs': [list(pair) for pair in expected], 'named_pairs': [list(p) for p in sorted(joints)],
            'nonmates': checks}


def scalar_range(c, x, y, lo, hi):
    values = [c+x*math.cos(t)+y*math.sin(t) for t in (lo, hi)]
    phase = math.atan2(y, x)
    for k in range(math.floor((lo-phase)/math.pi)-1, math.ceil((hi-phase)/math.pi)+2):
        t = phase+k*math.pi
        if lo <= t <= hi:
            values.append(c+x*math.cos(t)+y*math.sin(t))
    return min(values), max(values)


def near(node, box, threshold):
    if box_distance2(node[0], box) >= threshold**2:
        return
    if node[1] is not None:
        yield from node[1]
    else:
        yield from near(node[2], box, threshold)
        yield from near(node[3], box, threshold)


def motion_proof(rows, opening, motion):
    groups, member, wheel_members = report.motion_inventory(rows, opening, motion)
    coefficients, radii = {}, {}
    for name, group in member.items():
        record = groups[group]
        axis, pivot = record['axis_source'], record['pivot_source_m']
        values, radius = [], 0.
        for vertex in rows[name]['vertices']:
            u = [vertex[i]-pivot[i] for i in range(3)]
            dot = sum(u[i]*axis[i] for i in range(3))
            x = [u[i]-axis[i]*dot for i in range(3)]
            y = [axis[1]*u[2]-axis[2]*u[1], axis[2]*u[0]-axis[0]*u[2], axis[0]*u[1]-axis[1]*u[0]]
            c = [pivot[i]+axis[i]*dot for i in range(3)]
            values.append((c, x, y)); radius = max(radius, math.hypot(*x))
        coefficients[name], radii[name] = values, radius
    boxes = {name: bounds(rows[name]['vertices']) for name in report.NAMES}

    @lru_cache(maxsize=12000)
    def swept(name, lo, hi):
        factor = groups[member[name]]['factor_rad']
        a, b = sorted((lo*factor, hi*factor))
        intervals = [[scalar_range(c[i], x[i], y[i], a, b) for c, x, y in coefficients[name]] for i in range(3)]
        return tuple(min(v[0] for v in r)-1e-12 for r in intervals), tuple(max(v[1] for v in r)+1e-12 for r in intervals)

    @lru_cache(maxsize=1200)
    def at(name, fraction):
        if name not in member:
            points = [Vector(v) for v in rows[name]['vertices']]
        else:
            angle = groups[member[name]]['factor_rad']*fraction
            co, si = math.cos(angle), math.sin(angle)
            points = [Vector([c[i]+x[i]*co+y[i]*si for i in range(3)]) for c, x, y in coefficients[name]]
        triangles = [([points[i] for i in t], bounds([points[i] for i in t])) for t in rows[name]['triangles']]
        return triangles, tree(triangles)

    def movement(name, lo, hi):
        width = abs(groups[member[name]]['factor_rad']*(hi-lo))
        return 2*radii[name]*math.sin(min(math.pi/2, width/4))

    def witness(fixed, moving, fraction, threshold):
        first, _ = at(fixed, 0)
        second, bvh = at(moving, fraction)
        for i, (a, ab) in enumerate(first):
            for j in near(bvh, ab, threshold):
                b, bb = second[j]
                if box_distance2(ab, bb) >= threshold**2:
                    continue
                gap, p, q = triangle_distance(a, b)
                if gap < threshold:
                    return {'distance_m': gap, 'triangles': [i, j], 'points': [list(p), list(q)]}
        return None

    rotations = []
    for fixed in report.NAMES:
        for moving in sorted(member):
            domain = groups[member[moving]]['domain']
            stack = [(domain[0], domain[1], 0)]
            leaves, visited = [], 0
            while stack:
                lo, hi, depth = stack.pop(); visited += 1
                require(visited <= 30000, 'Unresolved motion cell ceiling')
                lower = math.sqrt(box_distance2(boxes[fixed], swept(moving, lo, hi)))
                if lower >= .001001:
                    leaves.append({'domain': [lo, hi], 'method': 'whole_aabb', 'lower_bound_m': lower})
                    continue
                displacement, mid = movement(moving, lo, hi), (lo+hi)/2
                found = None
                if displacement <= .025 or depth >= 18:
                    found = witness(fixed, moving, mid, .001001+displacement)
                    if found is None:
                        leaves.append({'domain': [lo, hi], 'method': 'triangle_features_plus_displacement',
                                       'midpoint': mid, 'displacement_m': displacement,
                                       'tested_threshold_m': .001001+displacement, 'lower_bound_m': .001001})
                        continue
                    require(found['distance_m'] >= .000999, 'Current swept collision: ' + str((fixed, moving, found)))
                require(depth < 26 and displacement >= 1e-9,
                        'Unresolved motion depth/numeric guard: ' + str((fixed, moving, lo, hi, found)))
                stack.extend(((mid, hi, depth+1), (lo, mid, depth+1)))
            leaves.sort(key=lambda r: r['domain'])
            report.check_intervals([r['domain'] for r in leaves], domain)
            rotations.append({'pair': [fixed, moving], 'group': member[moving], 'domain': domain,
                              'visited_cells': visited, 'leaves': leaves})
    wheels = []
    for driver in motion['tires']:
        names = wheel_members[driver['wheel']]
        center = driver['center_source_m']
        lo, hi = driver['continuous_travel_m']
        radius = max(math.dist(vertex, center) for name in names for vertex in rows[name]['vertices'])
        box = ([center[0]-radius, center[1]-radius, center[2]+lo-radius],
               [center[0]+radius, center[1]+radius, center[2]+hi+radius])
        for name in report.NAMES:
            gap = math.sqrt(box_distance2(boxes[name], box))
            require(gap >= .001001, 'Unresolved complete wheel/suspension sphere: ' + str((name, driver['wheel'], gap)))
            wheels.append({'fixed': name, 'wheel': driver['wheel'], 'complete_moving_members': names,
                           'center_source_m': center, 'travel_m': [lo, hi], 'sphere_radius_m': radius,
                           'swept_box': box, 'lower_bound_m': gap})
    return {'groups': groups, 'member_groups': member, 'rotations': rotations, 'wheels': wheels}


def local_proof(name, old, current, module, field_certificate):
    before = old['evaluated']; after = current['evaluated']
    old_points, new_points = np.asarray(before['vertices']), np.asarray(after['vertices'])
    require(np.array_equal(old_points.min(0), new_points.min(0)) and
            np.array_equal(old_points.max(0), new_points.max(0)), 'Changed retained complete extrema: ' + name)
    original_planes = [module.plane(old_points[t]) for t in before['triangles']]
    new_planes = [module.plane(new_points[t]) for t in after['triangles']]
    if name in report.FINS:
        ids = [i for i, (normal, _) in enumerate(new_planes) if any(float(normal@on) > .99985
               and max(abs(float(on@p)-od) for p in new_points[after['triangles'][i]]) <= 2e-7
               for on, od in original_planes)]
        fields = field_certificate(before, after, ids, partition, module.area)
        direction = 'new_retained_triangles_over_original_fields'
    else:
        ids = [i for i, (normal, _) in enumerate(original_planes) if any(float(normal@on) > .99985
               and max(abs(float(on@p)-od) for p in old_points[before['triangles'][i]]) <= 2e-7
               for on, od in new_planes)]
        fields = field_certificate(after, before, ids, partition, module.area)
        direction = 'complete_original_retained_triangles_over_new_fields'
    require(ids and fields['status'] == 'passed', 'Incomplete retained field: ' + name)
    physical = world_row(name, current)
    quality, self_test = shape_quality(physical['vertices'], physical['triangles']), scan(physical)
    normals = after['normals']
    require(normals and all(len(n) == 3 and all(math.isfinite(v) for v in n) for n in normals), 'Missing native normals')
    unit = max(abs(math.hypot(*n)-1) for n in normals)
    require(unit <= 1e-6 and self_test['status'] == 'passed' and not self_test['bad_pairs'], 'Invalid native normal/self result')
    require(quality['signed_volume_m3'] > 0 and quality['nonmanifold_edges'] == 0 and
            quality['duplicate_triangles'] == 0 and min(finite_area(physical)) > 1e-12, 'Invalid complete native shell')
    return plain({'name': name, 'direction': direction, 'retained_triangle_indices': ids,
                  'fields': fields, 'shape': quality, 'self': self_test, 'raw_normal_unit_error': unit,
                  'corner_targets': report.corner_targets(old, current),
                  'triangles_before': len(before['triangles']), 'triangles_after': len(after['triangles']),
                  'before_native': old, 'after_native': current})


def replay_preview(root):
    constructor = load_file('_source_qa_replay_preview', root / 'tools/vehicles/create_endurance_sedan.py')
    collection = bpy.data.collections['Preview']
    require(not collection.objects, 'Unexpected earlier preview construction')
    names = ('Light_Head_FL', 'Light_Head_FR', 'Light_Reverse_L', 'Light_Reverse_R')
    pivots = {name: bpy.data.objects[name] for name in names}
    controls = bpy.data.objects['RigControls']
    constructor.preview(collection)
    from endurance_sedan.mechanisms import preview_illumination
    preview_illumination(collection, pivots, controls)
    bpy.context.scene.render.fps = 60
    bpy.context.scene.frame_end = 600
    bpy.context.view_layer.update()
    expected = sorted(['PreviewFloor', 'PreviewCamera', 'Preview_Key', 'Preview_Fill',
                       'Preview_RearStrip', 'Preview_TopStrip', *['PreviewBeam_'+n for n in names]])
    require(sorted(obj.name for obj in collection.objects) == expected, 'Unexpected exact preview addition inventory')
    return expected


def source_phase(value):
    require(bpy.context.scene.get('repeated_detail_phase') == value, 'Wrong actual repeated-detail phase')


def replay_checkpoints(*, root, checkpoint, pre_lod, specification, proof, module,
                       checker, api, recipe, modifier_capture, payload):
    """Callable native replay slice. Caller verifies/holds actual file/tool rows.

    Opens only the named actual checkpoint/pre-LOD sources. This supplies native
    correspondence, not final-source, finite, motion or whole-gate acceptance.
    On failure payload retains every earlier completed observation.
    """
    bpy.ops.wm.open_mainfile(filepath=str(checkpoint), load_ui=False, use_scripts=False)
    source_phase('pre-construction-checkpoint')
    require(json.loads(bpy.context.scene['specification']) == specification, 'Checkpoint specification differs')
    before = inventory(module, checker, api, recipe, modifier_capture)
    payload['before_native'] = {name: before['native'][name] for name in report.NAMES + report.RECEIVERS}
    payload['witness_before_comparison'] = {
        name: compare_captures(proof['before'][name], before['native'][name], name)
        for name in report.NAMES + report.RECEIVERS}
    require(proof.get('source_phase') == 'pre-lod', 'Wrong held witness construction phase')
    observed = module.prepare(specification, objects={obj.name: obj for obj in bpy.data.objects}, source_phase='pre-lod')
    require(observed['source_phase'] == proof['source_phase'], 'Actual constructor phase differs')
    require(observed['before'] == payload['before_native'], 'Pre-application recapture changed')
    # The stored digest still binds its complete actual writer preimage, even
    # when separately measured reevaluation UV residuals are within the guard.
    report.validate_context_preimage(observed, proof)
    staged = module.stage(observed, expected_context_digest=digest(observed),
                          objects={obj.name: obj for obj in bpy.data.objects})
    replay = module.install(staged, expected_stage_digest=digest(staged['proof']),
                            objects={obj.name: obj for obj in bpy.data.objects})
    require(replay['source_phase'] == 'pre-lod', 'Replay used the wrong construction phase')
    after = inventory(module, checker, api, recipe, modifier_capture)
    payload['replay_outside'] = compare_inventories(before, after, excluded=report.NAMES)
    payload['witness_after_comparison'] = {name: compare_captures(proof['after_native'][name], after['native'][name], name)
                                          for name in report.NAMES}
    require(all(proof['after_evaluated'][name] == proof['after_native'][name]['evaluated']
                for name in report.NAMES), 'Stored native/evaluated witness domains disagree')
    # The saved JSON schema represents each native hull coordinate pair as a
    # list. Preserve exact coordinate equality across that explicit boundary.
    for name in report.RIBS:
        domain = replay['local'][name]['domain']
        domain['actual_middle_profile'] = [list(point) for point in domain['actual_middle_profile']]
    payload['replayed_local_domains'] = replay['local']
    require({name: {key: proof['local'][name][key] for key in ('domain', 'carriers')}
             for name in report.NAMES} ==
            {name: {key: replay['local'][name][key] for key in ('domain', 'carriers')}
             for name in report.NAMES}, 'Stored actual construction domains differ from independent replay')
    payload['preview_additions'] = replay_preview(root)
    reconstructed = inventory(module, checker, api, recipe, modifier_capture)
    bpy.ops.wm.open_mainfile(filepath=str(pre_lod), load_ui=False, use_scripts=False)
    source_phase('constructed')
    actual_pre_lod = inventory(module, checker, api, recipe, modifier_capture)
    payload['actual_pre_lod_correspondence'] = compare_inventories(reconstructed, actual_pre_lod)
    return before, actual_pre_lod


def main():
    parser = argparse.ArgumentParser()
    for name in ('source', 'source-binding', 'construction-root', 'geometry', 'opening-contract',
                 'motion-contract', 'lower-report', 'lower-payload', 'run-binding', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--expected-binding-sha256', required=True)
    parser.add_argument('--expected-run-binding-sha256', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    require(not args.output.exists(), 'Retain earlier stage output')
    require(sha(args.source_binding) == args.expected_binding_sha256 and
            sha(args.run_binding) == args.expected_run_binding_sha256, 'Caller-held binding hash changed')
    lock = load_source_binding(args.source_binding, args.source, args.construction_root,
                               args.output.parent / 'unused-repeated-detail-preflight')
    require(lock.pipeline is not None, 'Current repeated detail requires v2')
    sys.path.insert(1, str(lock.root / 'tools/vehicles'))
    from endurance_sedan import repeated_detail38 as module, source_generation as records, bevel_reserve26
    from endurance_sedan import main_fields_certificate26
    from endurance_sedan.distance_lod import api, recipe
    checker = load_file('endurance_sedan.qa._repeated_detail_distance_inventory', Path(__file__).with_name('distance_lod.py'))
    construction = strict_json(lock.pipeline.construction.path)
    generation = strict_json(lock.pipeline.generation.path)
    specification_file = artifact(lock.pipeline.portable_input_lock['roles']['specification'], lock.root)
    specification = strict_json(specification_file.path)
    input_files = [artifact(row, lock.root) for row in generation['input_artifacts']]
    detail = report.lock_optional(specification, construction, is_pipeline=True,
        artifact=lambda row: artifact(row, lock.root), generation_inputs=input_files,
        phase_outputs=[artifact(row, lock.root) for row in generation['commands'][0]['outputs']],
        source_artifacts=[lock.source, lock.pipeline.pre_lod, lock.pipeline.pre_front, lock.pipeline.historical.source,
                          lock.pipeline.construction, lock.pipeline.lower_bundle, lock.pipeline.generation],
        logical_files={key: next(row for row in input_files if row.path == lock.root / logical)
            for key, logical in (('constructor', 'tools/vehicles/endurance_sedan/repeated_detail38.py'),
                                ('encoder', 'tools/vehicles/endurance_sedan/corner_encoding.py'))})
    require(detail is not None and Path(module.__file__).resolve() == detail.constructor.path
            and module.POLICY == report.POLICY, 'Wrong actual source constructor')
    held = strict_json(args.run_binding)
    report.validate_run_binding(held, args, lock, detail, specification_file)
    records.verify_rows(held['roles'].values())
    records.verify_rows(held['tools'])
    require((bpy.app.version, bpy.app.build_hash.decode()) == ((5, 1, 2), 'ec6e62d40fa9'), 'Wrong native engine')
    begin = time.perf_counter()
    proof = construction['repeated_detail38']
    result = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': lock.source.sha256, 'source_binding_sha256': lock.binding.sha256,
              'run_binding': records.file_row(args.run_binding), 'source_saved': False, 'exported': False,
              'human_approval_reference': None, 'native': {'version': bpy.app.version_string,
                                                         'build': bpy.app.build_hash.decode()}}
    payload = {'input_roles': held['roles'], 'tools': held['tools']}
    try:
        before, actual_pre_lod = replay_checkpoints(
            root=lock.root, checkpoint=detail.checkpoint.path, pre_lod=lock.pipeline.pre_lod.path,
            specification=specification, proof=proof, module=module, checker=checker,
            api=api, recipe=recipe, modifier_capture=bevel_reserve26.modifier_state, payload=payload)
        bundle = strict_json(lock.pipeline.lower_bundle.path)
        require(actual_pre_lod['objects'] == bundle['before'], 'Actual pre-LOD inventory differs from saved lower before')
        require({name: digest(rows) for name, rows in actual_pre_lod['materials'].items()} == bundle['material_before'],
                'Actual pre-LOD material fields differ from lower before')
        lower_report = strict_json(args.lower_report)
        lower_payload = strict_json(args.lower_payload)
        report.validate_lower_prerequisite(lower_report, lower_payload, lock, args.lower_payload,
                                           digest(actual_pre_lod['objects']))
        bpy.ops.wm.open_mainfile(filepath=str(lock.source.path), load_ui=False, use_scripts=False)
        source_phase('constructed')
        actual = inventory(module, checker, api, recipe, bevel_reserve26.modifier_state)
        require(actual['objects'] == lower_payload['final_inventory'], 'Actual final inventory differs from bound independent lower stage')
        payload['lower_chain'] = {'before_digest': digest(actual_pre_lod['objects']),
                                  'actual_final_inventory_digest': digest(actual['objects']),
                                  'original_names': sorted(actual_pre_lod['objects'])}
        payload['original_correspondence'] = {}
        for name in report.NAMES + report.RECEIVERS:
            changes = lower_payload['metadata_changes'].get(name, {})
            expected = report.lower_metadata_preimage(actual_pre_lod['native'][name], actual['native'][name], changes)
            payload['original_correspondence'][name] = {'lower_metadata_changes': changes,
                'native_fields': compare_captures(expected, actual['native'][name], name)}
        payload['local'] = [local_proof(name, before['native'][name], actual['native'][name], module,
                                       main_fields_certificate26.field_certificate) for name in report.NAMES]
        extraction = strict_json(args.geometry)
        require(extraction['source_sha256'] == lock.source.sha256 and extraction['embedded_specification'] == specification,
                'Wrong current extraction/specification')
        rows = {name: world_row(name, native) for name, native in actual['native'].items()
                if name.startswith('LOD0_') and not native['raw']['properties'].get('source_preview_only')}
        expected_rows = {name: row for name, row in extraction['meshes'].items() if not row['properties'].get('source_preview_only')}
        require(set(rows) == set(expected_rows), 'Incomplete actual current physical inventory')
        for name, row in rows.items():
            for key in ('vertices', 'triangles', 'ancestors'):
                require(row[key] == expected_rows[name][key], 'Actual current physical extraction differs: ' + name + '/' + key)
        payload['current_geometry_names'] = sorted(rows)
        old_world = {name: world_row(name, before['native'][name]) for name in report.NAMES + report.RECEIVERS}
        payload['finite'] = finite_proof(old_world, rows)
        payload['rest'] = rest_proof(rows)
        opening, motion = strict_json(args.opening_contract), strict_json(args.motion_contract)
        require(all(row['status'] == 'passed' and row['source_sha256'] == lock.source.sha256 for row in (opening, motion)),
                'Wrong current motion prerequisites')
        payload['motion'] = motion_proof(rows, opening, motion)
        require(inventory(module, checker, api, recipe, bevel_reserve26.modifier_state)['objects'] == actual['objects'],
                'Source raw inventory changed during diagnostic geometry')
        lock.verify(); records.verify_rows(held['roles'].values()); records.verify_rows(held['tools'])
        payload['counts'] = {'before': sum(len(before['native'][n]['evaluated']['triangles']) for n in report.NAMES),
                             'after': sum(len(rows[n]['triangles']) for n in report.NAMES), 'members': len(report.NAMES)}
        result.update(status='passed', all_locked_inputs_unchanged=True, elapsed_seconds=time.perf_counter()-begin)
        payload = plain(payload)
        report.validate_payload(payload, held, extraction, opening, motion)
        path = args.output.with_suffix('.payload.json.gz')
        records.write(path, payload)
        result['payload'] = records.file_row(path)
        records.write(args.output, result)
        print('SEDAN_REPEATED_DETAIL '+json.dumps({'status': 'passed', 'seconds': result['elapsed_seconds']}), flush=True)
    except BaseException as error:
        result.update(status='failed', error=type(error).__name__+': '+str(error), traceback=traceback.format_exc(),
                      elapsed_seconds=time.perf_counter()-begin)
        records.write(args.output.with_suffix('.failure-payload.json.gz'), plain(payload))
        records.write(args.output, result)
        raise


if __name__ == '__main__':
    main()
