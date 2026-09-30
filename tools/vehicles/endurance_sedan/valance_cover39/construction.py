"""Capture the real construction boundary and install the finite rear cover."""
from pathlib import Path
import json

import bpy

from . import apply, finite_domains, triangle_domains
from .. import corner_encoding, main_fields_cell26, reserve_correspondence26, source_generation
from .. import staged_normals
from ..finishing34.front_sheet import field_support
from ..qa.precision import point_triangle
from ..qa.valance_cover_report import POLICY, SELECTOR, NAMES, RECEIVER


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def capture(obj):
    return plain(reserve_correspondence26.evaluated(obj))


def construct(proof, root, stage_root):
    specification = json.loads(bpy.context.scene['specification'])
    declared = specification['original_packaging'].get(SELECTOR)
    if SELECTOR not in specification['original_packaging']:
        return None
    if source_generation.digest(declared) != source_generation.digest(POLICY):
        raise ValueError('Unknown original valance cover revision')
    obj, body = (bpy.data.objects[name] for name in (NAMES[0], RECEIVER))
    roles = triangle_domains(obj, proof['current_surface34']['valance_plan'],
        proof['current_surface34']['original_valance'],
        fingerprint=staged_normals.fingerprint, digest=staged_normals.digest)
    before = {o.name: capture(o) for o in (obj, body)}
    protected = {o.name: source_generation.digest(reserve_correspondence26.raw(o))
                 for o in bpy.data.objects if o.type == 'MESH' and o.name != obj.name}
    directory = stage_root / 'pre-cover'
    directory.mkdir(parents=True, exist_ok=False)
    checkpoint = directory / 'source.blend'
    bpy.context.scene['valance_cover_phase'] = 'pre-construction-checkpoint'
    bpy.context.view_layer.update()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint), compress=True, check_existing=False)
    requested = directory / 'requested.json.gz'

    def freeze_requested(plans):
        source_generation.write(requested, plans)
        if source_generation.read(requested) != plans:
            raise ValueError('Pre-encoding requested cover packet readback differs')
        return source_generation.file_row(requested, root)

    declaration = finite_domains()
    result = apply(obj, body, reference=plain(proof['prelate_rear34']),
        triangle_domains=roles, finite_field_domains=declaration, capture=capture,
        exact=main_fields_cell26, point_triangle=point_triangle,
        complete_angle=field_support.complete_affine_angle, encode=corner_encoding.encode,
        freeze_requested=freeze_requested)
    if any(source_generation.digest(reserve_correspondence26.raw(bpy.data.objects[name])) != held
           for name, held in protected.items()):
        raise ValueError('Cover construction changed an unowned raw mesh')
    if set(result['native']['after']) != set(NAMES):
        raise ValueError('Incomplete native cover installation')
    count = sum(len(r['triangles']) for r in result['native']['after'].values())
    if count != POLICY['cover_triangles'] + POLICY['mount_triangles']:
        raise ValueError('Unexpected cover constructor triangle cost')
    value = {'schema': 'source-valance-cover-construction39.v1', 'policy': plain(POLICY),
        'source_phase': 'pre-lod', 'checkpoint': source_generation.file_row(checkpoint, root),
        'requested': source_generation.file_row(requested, root),
        'constructor': source_generation.file_row(Path(__file__), root),
        'encoder': source_generation.file_row(Path(corner_encoding.__file__), root),
        'before': before, 'triangle_domains': roles, 'finite_field_domains': declaration,
        'native': result['native'], 'layout': result['layout'], 'base': result['base'],
        'unowned_raw_before': protected, 'unowned_raw_unchanged': True,
        'triangles_before': len(before[obj.name]['triangles']), 'triangles_after': count,
        'independent_source_acceptance': False}
    bpy.context.scene['valance_cover_phase'] = 'constructed'
    print('FRESH39 current-input rear cover; pre-cover source and pre-encoding request retained', flush=True)
    return value
