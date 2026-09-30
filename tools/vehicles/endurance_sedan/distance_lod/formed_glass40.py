"""Literal current formed Backlight at both lower levels; no pane simplification."""
import json

import bpy

from .binding import digest, plain
from .. import reserve_correspondence26
from ..front_finish40.native import verify_fields
from ..qa.upper_finish_report import LOWER_POLICY, require

SOURCE = 'LOD0_Backlight'
SCHEMA = 'formed-backlight-lower40.v1'


def bind(source, context):
    require(source.name == SOURCE and context['profile'].get('current_upper_revision40') == LOWER_POLICY,
            'Missing selected current formed Backlight profile')
    if context.get('current_revision40') is True:
        from .front_feature40 import bind as bind_front
    else:
        from .front_feature_current import bind as bind_front
    bind_front(bpy.data.objects['LOD0_FrontBumper'], context)
    packet = context['upper_packet']
    require(packet['sha256'] == digest(packet['core']) == context['expected']['upper_packet_sha256']
            and packet['core']['current_source_sha256'] == context['expected']['source_sha256'],
            'Current formed Backlight differs from held upper packet')
    require(source.parent and source.parent.name == 'Visual_LOD0' and not source.modifiers,
            'Current formed Backlight must be the explicit source shell')
    actual = plain(reserve_correspondence26.evaluated(source))
    require(actual == packet['core']['current_native'][SOURCE], 'Current formed Backlight source fields changed')
    require(len(actual['triangles']) == 248 and actual['materials'] == ['Material_GlassPrivacy'],
            'Current formed Backlight shell/material inventory changed')
    return actual


def targets(row):
    return {**{key: row[key] for key in ('vertices', 'triangles', 'materials', 'triangle_materials')},
            'normal_corner_targets': [[row['normals'][loop] for loop in triangle] for triangle in row['triangle_loops']],
            'uv_corner_targets': {channel: [[values[loop] for loop in triangle] for triangle in row['triangle_loops']]
                                  for channel, values in row['uvs'].items()}}


def verify_output(obj, proof, expected_digest, *, context):
    require(context is not None and digest(proof) == expected_digest and proof['schema'] == SCHEMA
            and proof['policy'] == LOWER_POLICY,
            'Missing caller-held current formed Backlight witness')
    source = bind(bpy.data.objects[SOURCE], context)
    require(source == proof['original_fields'] and proof['source'] == SOURCE
            and proof['upper_packet_digest'] == context['expected']['upper_packet_sha256'],
            'Formed Backlight lower witness belongs to another source')
    require(obj.parent and obj.parent.name == proof['parent'] in ('Visual_LOD1', 'Visual_LOD2')
            and not obj.modifiers and json.loads(obj['source_components']) == [SOURCE]
            and [list(row) for row in obj.matrix_world] == proof['matrix_world'],
            'Current lower formed Backlight frame or source identity changed')
    actual = dict(plain(reserve_correspondence26.evaluated(obj)), name=SOURCE)
    require(actual == source, 'Current lower formed Backlight lost literal source fields')
    return verify_fields({SOURCE: actual}, {SOURCE: targets(source)}, names=(SOURCE,))[SOURCE]


def build(source, parent, collection, *, context, certificate, **unused):
    original = bind(source, context)
    require(parent and parent.name in ('Visual_LOD1', 'Visual_LOD2'), 'Wrong formed Backlight lower parent')
    name = 'LOD' + parent.name[-1] + '_Field_Backlight'
    obj = bpy.data.objects.new(name, source.data.copy())
    collection.objects.link(obj)
    obj.parent = parent
    obj.matrix_world = source.matrix_world.copy()
    obj['source_components'] = json.dumps([SOURCE])
    bpy.context.view_layer.update()
    try:
        proof = {'schema': SCHEMA, 'source': SOURCE, 'parent': parent.name,
                 'upper_packet_digest': context['expected']['upper_packet_sha256'],
                 'original_fields': original, 'matrix_world': [list(row) for row in obj.matrix_world],
                 'source_triangles': len(original['triangles']), 'derived_triangles': len(original['triangles']),
                 'policy': LOWER_POLICY}
        verify_output(obj, proof, digest(proof), context=context)
        actual = reserve_correspondence26.evaluated(obj)
        shell = certificate(actual)
        require(shell['status'] == 'passed', 'Current lower formed Backlight indexed shell failed')
        proof['shell_proof'] = shell
        proof['final_current_field'] = verify_output(obj, proof, digest(proof), context=context)
        return obj, proof
    except BaseException:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise
