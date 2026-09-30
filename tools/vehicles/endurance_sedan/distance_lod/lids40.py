"""Construct complete distant lids from the live original source fields.

The locked hashes certify the particular representation already measured by
finite comparison and rendered at its intended distances. No report or saved
candidate geometry is a construction input. Original lids are never assigned.
"""
import json

import bpy
import numpy as np

from .binding import digest, require
from .lid_policy40 import POLICY
from .lid_fields40 import constraints
from .selective_lod import native_row
from .. import corner_encoding, reserve_correspondence26, source_generation as records
from ..front_compact40.reduce import reduce
from ..front_compact40.geometry import source_target
from ..front_compact40.uv_source import LocalTree


def _source(original):
    require(original.name in POLICY['members'], 'Unreviewed distant lid source')
    expected = POLICY['measured'][original.name]
    require(original.type == 'MESH' and original.parent is not None
            and original.parent.name == expected['parent'], 'Distant lid original parent differs')
    require(np.array_equal(np.asarray(original.matrix_world), np.eye(4)),
            'Construct distant lids only at the original closed rest frame')
    old = records.read_plain(reserve_correspondence26.evaluated(original))
    require(digest(old) == expected['source_sha256'],
            'Distant lid source differs from the complete measured field: ' + original.name)
    return old, expected


def target(original):
    old, expected = _source(original)
    held = constraints(old, POLICY['seam_degrees'], POLICY['collar_degrees'])
    # The measured construction domain retained seam edges and complete face
    # charts; its diagnostic list of every smooth interior edge was omitted.
    held.pop('all_edges')
    require(digest(held) == expected['constraints_sha256'],
            'Original distant lid seam/collar domain differs')
    candidate = reduce(old['vertices'], old['triangles'], old['triangle_materials'],
        set(held['protected_vertices']), plane_error=POLICY['plane_error_m'],
        target_triangles=round(len(old['triangles']) * POLICY['target_ratio']))
    surviving = {face: at for at, face in enumerate(candidate['source_face_ids'])}
    for face in held['protected_complete_faces']:
        require(face in surviving, 'Lost a complete protected lid face')
        tri = candidate['triangles'][surviving[face]]
        require([candidate['vertices'][v] for v in tri]
                == [old['vertices'][v] for v in old['triangles'][face]],
                'Changed a manufactured lid return or source seam')
    original_targets = source_target(old)
    trees = {label: LocalTree({'vertices': old['vertices'],
        'triangles': [old['triangles'][face] for face in ids],
        'normal_corner_targets': [original_targets['normal_corner_targets'][face] for face in ids]})
        for label, ids in enumerate(held['charts'])}
    normals, uvs, correspondences = [], [], []
    for face, tri in enumerate(candidate['triangles']):
        survivor = candidate['source_face_ids'][face]
        original_tri = old['triangles'][survivor]
        chart = held['face_charts'][survivor]
        xyz = np.asarray([candidate['vertices'][v] for v in tri])
        geometric = np.cross(xyz[1] - xyz[0], xyz[2] - xyz[0])
        geometric /= np.linalg.norm(geometric)
        nn, uu, cc = [], [], []
        for vertex in tri:
            original_vertex = candidate['source_vertex_ids'][vertex]
            point = candidate['vertices'][vertex]
            if original_vertex in original_tri and point == old['vertices'][original_vertex]:
                corner = original_tri.index(original_vertex)
                normal = original_targets['normal_corner_targets'][survivor][corner]
                uv = original_targets['uv_corner_targets']['SurfaceMeters'][survivor][corner]
                source_face, weights, distance, literal = survivor, [int(i == corner) for i in range(3)], 0., True
            else:
                distance, chart_face, _, weights = trees[chart].nearest_sheet(point, geometric)
                source_face = held['charts'][chart][chart_face]
                require(held['face_charts'][source_face] == chart, 'Cross-chart distant lid lookup')
                normal = np.asarray(weights) @ np.asarray(original_targets['normal_corner_targets'][source_face])
                normal = (normal / np.linalg.norm(normal)).tolist()
                uv = (np.asarray(weights) @ np.asarray(original_targets['uv_corner_targets']['SurfaceMeters'][source_face])).tolist()
                literal = False
            nn.append(normal)
            uu.append(uv)
            cc.append({'surviving_original_face': survivor, 'source_face': source_face,
                'source_chart': chart, 'weights': list(weights), 'distance_m': distance,
                'literal_retained_corner': literal, 'original_vertex': original_vertex})
        normals.append(nn)
        uvs.append(uu)
        correspondences.append(cc)
    require(len(candidate['triangles']) == expected['triangles'], 'Distant lid representation cost changed')
    return candidate, normals, uvs, correspondences


def build(original, level, collection, shell_certificate):
    require(level in POLICY['levels'], 'Distant lid requires a declared lower level')
    before = digest(reserve_correspondence26.raw(original))
    candidate, normals, uvs, correspondence = target(original)
    name = 'LOD' + str(level) + '_CurrentLid_' + original.name.removeprefix('LOD0_')
    require(bpy.data.objects.get(name) is None, 'Distant lid already constructed')
    mesh = bpy.data.meshes.new(name + '_Mesh')
    obj = None
    try:
        mesh.from_pydata(candidate['vertices'], [], candidate['triangles'])
        for material in original.data.materials:
            mesh.materials.append(material)
        for poly, material in zip(mesh.polygons, candidate['triangle_materials'], strict=True):
            poly.use_smooth = True
            poly.material_index = material
        layer = mesh.uv_layers.new(name='SurfaceMeters')
        for item, uv in zip(layer.data, (v for tri in uvs for v in tri), strict=True):
            item.uv = uv
        mesh.update()
        require(not mesh.validate(clean_customdata=False), 'Native distant lid geometry required repair')
        encoding = corner_encoding.encode(mesh, [n for tri in normals for n in tri])
        require(encoding['passed'], 'Native distant lid encoding failed')
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        obj.parent = original.parent
        obj.matrix_world = original.matrix_world.copy()
        obj['source_components'] = json.dumps([original.name])
        obj['lod_index'] = level
        obj['distant_lid_revision'] = POLICY['schema']
        proof = verify(obj, original, level, shell_certificate)
        require(before == digest(reserve_correspondence26.raw(original)), 'Distant lid changed original source')
        proof.update(native_encoding=records.read_plain(encoding),
            source_correspondence=correspondence, constrained_reduction=candidate,
            unchanged_original_raw_sha256=before)
        return obj, proof
    except BaseException:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def verify(obj, original, level, shell_certificate):
    _, expected = _source(original)
    require(level in POLICY['levels'] and obj.get('lod_index') == level,
            'Distant lid lower-level metadata differs')
    require(json.loads(obj.get('source_components', 'null')) == [original.name]
            and obj.get('distant_lid_revision') == POLICY['schema'],
            'Distant lid complete source identity differs')
    require(obj.parent == original.parent and not obj.modifiers, 'Distant lid motion frame or modifiers differ')
    actual = native_row(obj)
    require(digest({k: v for k, v in actual.items() if k != 'name'}) == expected['actual_sha256'],
            'Distant lid actual native field differs from the complete measured representation')
    require(set(obj.data.uv_layers.keys()) == {'SurfaceMeters'}
            and all(p.material_index == 0 and p.use_smooth for p in obj.data.polygons),
            'Distant lid UV/material/smoothing assignment differs')
    shell = shell_certificate(actual)
    require(shell['status'] == 'passed', 'Distant lid indexed closed/self check failed')
    return {'source': original.name, 'lod': level, 'parent': obj.parent.name,
        'source_sha256': expected['source_sha256'], 'actual_sha256': expected['actual_sha256'],
        'triangles': len(actual['triangles']), 'complete_indexed_shell': shell,
        'measured_original_field_bounds': expected['maximum_field_bounds'],
        'meaning': 'Exact measured representation; complete lower assembly fit and runtime transitions remain separate.'}
