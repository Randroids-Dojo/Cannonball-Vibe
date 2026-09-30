"""Build the original visible finned core inside its existing native package.

This models heat-exchanger construction only, with no thermal or airflow claim.
"""
import bpy
import numpy as np
from . import geometry as geo, materials
from .qa import self_geometry


def apply():
    old = bpy.data.objects['LOD0_CentralRadiator']
    evaluated = old.evaluated_get(bpy.context.evaluated_depsgraph_get())
    native = evaluated.to_mesh()
    native.calc_loop_triangles()
    old_points = np.asarray([list(evaluated.matrix_world @ v.co) for v in native.vertices], dtype=np.float64)
    old_triangles = [list(t.vertices) for t in native.loop_triangles]
    lo, hi = old_points.min(axis=0), old_points.max(axis=0)
    assert np.max(np.abs(hi-lo-np.array([1.09, .025, .223]))) < 1e-6
    old_count = len(old_triangles)
    planes = []
    for indices in old_triangles:
        a,b,c = old_points[indices]
        normal = np.cross(b-a,c-a)
        normal /= np.linalg.norm(normal)
        planes.append((normal, float(normal @ a)))
    evaluated.to_mesh_clear()

    # Original authored inspection-scale corrugations. The complete new closed
    # core lies inside the actual original convex package, including bevels.
    edge = .003
    front, back, bottom, top = float(hi[1]), float(lo[1]), float(lo[2]), float(hi[2])
    z0, z1 = bottom + edge, top - edge
    folds, depth = 52, .0018
    pitch = (z1-z0)/folds
    profile = [(back+edge,bottom),(front-edge,bottom),(front,z0)]
    for i in range(folds):
        profile.extend([(front-depth,z0+pitch*(i+.5)),(front,z0+pitch*(i+1))])
    profile += [(front-edge,top),(back+edge,top),(back,top-edge),(back,bottom+edge)]
    material = materials.principled('Material_CoolingCore', (.018,.021,.025), .52, metallic=0)
    material['provenance'] = 'Project-original black-coated heat-exchanger response; no external material input'
    material['finish_role'] = 'Matte black protective coating over modeled aluminum core; no thermal-performance claim'
    fresh = geo.prism_x('Private_FinnedCoolingCore', profile, float(lo[0])+.0035,
                        float(hi[0])-.0035, material, old.users_collection[0], old.parent)
    assert fresh.matrix_world == old.matrix_world
    geo.repair_triangulation(fresh)
    fresh.data.calc_loop_triangles()
    points = np.asarray([list(fresh.matrix_world @ v.co) for v in fresh.data.vertices], dtype=np.float64)
    maximum_outside = max(float((points @ n - d).max()) for n,d in planes)
    assert maximum_outside <= 1e-6, maximum_outside
    row = {'name': old.name, 'vertices': points.tolist(),
           'triangles': [list(t.vertices) for t in fresh.data.loop_triangles]}
    counts = geo.evaluated_counts(fresh)
    for key in ('nonmanifold_edges','duplicate_faces','degenerate_faces','degenerate_triangles',
                'triangulated_duplicate_faces','triangulated_nonmanifold_edges',
                'nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals'):
        assert counts[key] == 0, (key, counts[key])
    certificate = self_geometry.scan(row)
    assert certificate['status'] == 'passed' and not certificate['bad_pairs']
    old.modifiers.clear()
    old.data = fresh.data
    bpy.data.objects.remove(fresh, do_unlink=True)
    old['manufacturing_form'] = 'Closed recessed heat-exchanger inspection core with52 folded face courses; dark protective coating'
    old['cooling_simulation'] = 'none; visible packaging only'
    return old, {
        'old_bounds_m': [lo.tolist(), hi.tolist()],
        'new_bounds_m': [points.min(axis=0).tolist(), points.max(axis=0).tolist()],
        'whole_new_core_inside_original_native_convex_envelope_m': maximum_outside,
        'fold_count': folds, 'pitch_m': pitch, 'face_recess_m': depth,
        'triangles_before': old_count, 'triangles_after': len(row['triangles']),
        'triangle_delta': len(row['triangles'])-old_count,
        'counts': counts, 'self': certificate,
        'scope': 'Modeled packaging only. Complete source, LOD, export, runtime and visual acceptance are separate.'}
