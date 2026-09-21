"""Build actual native topology/containment and intermediate-opening fixtures."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import mesh_defects, sha
from initial_containment import check_pair
from surface_minimum import Distances
from solid_interfaces import prove_join


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--opening-contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert not args.output.exists()
    args.output.mkdir()
    base = json.loads(gzip.decompress(args.geometry.read_bytes()))
    contract = json.loads(args.opening_contract.read_text(encoding='utf8'))
    assert base['source_sha256'] == contract['source_sha256'] == sha(args.source)
    vertices = [[-1., -1., -1.], [1., -1., -1.], [1., 1., -1.], [-1., 1., -1.],
                [-1., -1., 1.], [1., -1., 1.], [1., 1., 1.], [-1., 1., 1.]]
    faces = [[0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
             [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    topology = []
    for case in ('valid', 'zero-area', 'duplicate', 'open'):
        data = bpy.data.meshes.new('QaTopology_' + case)
        points = vertices + ([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]] if case == 'zero-area' else [])
        triangles = faces + ([[8, 9, 10]] if case == 'zero-area' else [faces[0]] if case == 'duplicate' else [])
        if case == 'open':
            triangles = triangles[:-1]
        data.from_pydata(points, [], triangles)
        data.update()
        data.calc_loop_triangles()
        actual = [list(tri.vertices) for tri in data.loop_triangles]
        values = [v.co.copy() for v in data.vertices]
        areas = [((values[b] - values[a]).cross(values[c] - values[a])).length / 2 for a, b, c in actual]
        edges = Counter(tuple(sorted((tri[i], tri[(i + 1) % 3]))) for tri in actual for i in range(3))
        row = {'name': data.name, 'triangles': len(actual), 'minimum_triangle_area_m2': min(areas),
               'degenerate_loop_triangles': sum(area <= 1e-12 for area in areas),
               'duplicate_loop_triangles': sum(value - 1 for value in Counter(tuple(sorted(tri)) for tri in actual).values()),
               'nonmanifold_edges': sum(value != 2 for value in edges.values()),
               'triangulated_nonmanifold_edges': sum(value != 2 for value in edges.values())}
        actual_accept = not mesh_defects([row])
        assert actual_accept == (case == 'valid'), (case, row)
        topology.append({'case': case, 'actual_native_inventory': row, 'expected_accept': case == 'valid',
                         'actual_accept': actual_accept, 'passed': True})
    def cube(name, center, half):
        return {'name': name, 'vertices': [[center[i] + p[i] * half for i in range(3)] for p in vertices],
                'triangles': faces, 'ancestors': [], 'properties': {}, 'material_names': [],
                'rest_world_matrix': [list(row) for row in Matrix.Identity(4)]}
    nested = {'outer': cube('outer', (0, 0, 0), 1.), 'inner': cube('inner', (0, 0, 0), .1)}
    rejected = check_pair(nested, ('outer', 'inner'), {})
    assert rejected['status'].startswith('failed'), rejected
    nested['inner'] = cube('inner', (0, 0, 3), .1)
    corrected = check_pair(nested, ('outer', 'inner'), {})
    assert corrected['status'].startswith('outside'), corrected
    joint_rows = {'first': cube('first', (0, 0, 0), .02), 'second': cube('second', (.04, 0, 0), .02)}
    rule = {'pair': ['first', 'second'], 'solid_policy': 'zero_solid_intrusion',
            'allowed_contact_region': {'kind': 'actual_mesh_boundary', 'mesh': 'first', 'maximum_surface_distance_m': 1e-6}}
    exact_seat, _ = prove_join(joint_rows, rule)
    assert exact_seat['status'] == 'passed', exact_seat
    joint_rows['second'] = cube('second', (.03999, 0, 0), .02)
    intrusion, _ = prove_join(joint_rows, rule)
    assert intrusion['status'] != 'passed', intrusion
    bpy.ops.wm.open_mainfile(filepath=str(args.source), load_ui=False, use_scripts=True)
    controls = bpy.data.objects['RigControls']
    door = bpy.data.objects['Door_FL']
    data = bpy.data.meshes.new('QaOpeningCube')
    data.from_pydata([[value * .02 for value in p] for p in vertices], [], faces)
    obj = bpy.data.objects.new('LOD0_QaNegativeMovingCube', data)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = door
    obj.location = (0., -1., 3.)
    numeric = {key: controls[key] for key in controls.keys() if isinstance(controls[key], (int, float))}
    def pose(fraction):
        for key, value in numeric.items():
            controls[key] = value if key.startswith('source_sim_') else 0.
        controls['Door_FL_open'] = fraction
        controls.update_tag(refresh={'OBJECT'})
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        return [list(evaluated.matrix_world @ v.co) for v in evaluated.data.vertices], evaluated.matrix_world.copy()
    rest, matrix = pose(0.)
    middle, middle_matrix = pose(.5)
    end, _ = pose(1.)
    moving = {'name': obj.name, 'vertices': rest, 'triangles': faces, 'ancestors': ['Door_FL'],
              'properties': {'qa_synthetic_fixture': True}, 'material_names': [], 'rest_world_matrix': [list(row) for row in matrix]}
    obstacle = {'name': 'LOD0_QaNegativeFixedObstacle', 'vertices': [[v[0] + .007, v[1], v[2]] for v in middle],
                'triangles': faces, 'ancestors': [], 'properties': {'qa_synthetic_fixture': True},
                'material_names': [], 'rest_world_matrix': [list(row) for row in Matrix.Identity(4)]}
    sampled = []
    for fraction, points in ((0., rest), (.5, middle), (1., end)):
        rows = {moving['name']: {**moving, 'vertices': points}, obstacle['name']: obstacle}
        measure = Distances(rows).minimum(moving['name'], obstacle['name'])
        assert (measure['distance_m'] > .001001) == (fraction != .5), (fraction, measure)
        sampled.append({'fraction': fraction, 'minimum': measure})
    for case, delta in (('middle-collision', 0.), ('corrected', .2)):
        payload = dict(base)
        fixed = {**obstacle, 'vertices': [[v[0], v[1], v[2] + delta] for v in obstacle['vertices']]}
        payload['meshes'] = base['meshes'] | {moving['name']: moving, fixed['name']: fixed}
        payload['qa_derived_fixture'] = {'case': case, 'description': 'Two added cubes only; all supplied production geometry/driver inputs unchanged',
                                         'native_middle_matrix': [list(row) for row in middle_matrix]}
        (args.output / (case + '.json.gz')).write_bytes(gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), mtime=0))
    derived_contract = dict(contract)
    derived_contract['opening_groups'] = [dict(row) for row in contract['opening_groups']]
    target = next(row for row in derived_contract['opening_groups'] if row['name'] == 'Door_FL')
    assert obj in door.children_recursive
    target['descendants'] = [*target['descendants'], obj.name]
    derived_contract['qa_derived_fixture'] = 'Actual native-added cube parented to existing source Door_FL; original driver expressions, axes and controls unchanged'
    (args.output / 'opening-contract.json').write_text(json.dumps(derived_contract, indent=2) + '\n', encoding='utf8', newline='\n')
    report = {'source_sha256': base['source_sha256'], 'status': 'passed', 'topology': topology,
              'containment_negative': rejected, 'containment_corrected': corrected,
              'exact_interface_seat': exact_seat, 'interface_intrusion_negative': intrusion,
              'actual_native_opening_sampled_distances': sampled, 'human_approval_reference': None,
              'scope': 'Synthetic native fixtures and two diagnostic added cubes; no saved production source or shipping export'}
    (args.output / 'fixtures.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8', newline='\n')
    assert sha(args.source) == base['source_sha256']
    print('Native negative fixtures prepared; original source unchanged.', flush=True)


if __name__ == '__main__':
    main()
