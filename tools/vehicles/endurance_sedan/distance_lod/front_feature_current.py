"""Current finite geometry binding and explicitly scoped lamp protection."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json
import bpy
from .binding import digest, plain, sha, read, CURRENT_FRONT_PROTECTION
from . import current_front as current

from . import front_feature_mixed as _base
DOMAIN=_base.DOMAIN
Adapter=_base.Adapter
verify=_base.verify
material_metadata=_base.material_metadata
_cache={}

def bind(source,context):
    expected=context['expected']
    current.require(digest(expected)==context['expected_binding_digest'],'Caller current-front binding digest mismatch')
    current.require(context['observed']==expected,'Observed current source/packet/module/profile binding differs')
    current.require(expected['schema']=='current-finite-front-source-binding36.v1','Wrong finite current binding schema')
    current.require(Path(bpy.data.filepath).resolve()==Path(expected['source_path']),'Loaded source path differs')
    current.require(sha(expected['source_path'])==expected['source_sha256'],'Loaded source file bytes differ')
    current.require(digest(context['input_files'])==expected['input_files_sha256'],'Current input-role inventory differs')
    for row in context['input_files']:
        current.require(sha(row['path'])==row['sha256'],'Current constructor/helper input bytes differ: '+row['path'])
    current.require(digest(context['profile'])==expected['profile_sha256']
        and context['profile']['mixed_front']==DOMAIN,'Changed current LOD profile')
    current.require(digest(json.loads(bpy.context.scene['specification']))==expected['specification_sha256'],'Embedded current specification differs')
    packet=context['packet'];core=packet['core']
    current.require(packet['sha256']==digest(core)==expected['field_core_sha256'],'Current finite field packet differs')
    current.require(core['current_source_sha256']==expected['source_sha256'],'Current field packet belongs to another source')
    current.require(sha(context['construction_path'])==expected['construction_sha256'],'Current source construction companion differs')
    native=plain(context['dependencies']['sheet'].native_state(source))
    physical=plain(context['dependencies']['support'].fields(source))
    material=context['material_capture'](source.data)
    key=(context['expected_binding_digest'],digest(native),digest(physical),digest(material))
    if key not in _cache:
        _cache[key]=current.verify_packet(source,packet,context['dependencies'],context['material_capture'])
    context['current_native_chain_proof']=_cache[key]
    return expected,core['original_inlet_packet']


def capture(source,*,context):
    reference=_base.capture(source,context=context,binding_check=bind)
    core=context['packet']['core']
    inventory=current.protection_inventory(source,core['lamp_plan']['domain']['selected_faces'])
    current.require(set(inventory['protected_triangles'])=={r['source_triangle'] for r in reference['triangles']},'Original mixed-front selector differs from independent inventory')
    policy=context['profile']['current_front_protection']
    current.require(policy==CURRENT_FRONT_PROTECTION,'Changed finite lamp protection profile')
    vertices=set(inventory['protected_vertices'])|set(inventory['missing_lamp_vertices'])
    mesh=source.data;mesh.calc_loop_triangles()
    protected={i for i,t in enumerate(mesh.loop_triangles) if set(t.vertices)<=vertices}
    added=sorted(protected-set(inventory['protected_triangles']))
    current.require(len(protected)==policy['protected_faces'] and len(added)==policy['additional_complete_faces']
        and len(inventory['protected_triangles'])==policy['original_protected_faces'],
        'Current geometric lamp closure differs from scoped complete face inventory')
    current.require(set(core['lamp_plan']['domain']['selected_faces'])<=protected,'Current complete finite lamp protection omitted faces')
    points=[tuple(v.co) for v in mesh.vertices]
    for index in added:
        tri=mesh.loop_triangles[index]
        normals=[tuple(mesh.corner_normals[li].vector) for li in tri.loops]
        reference['triangles'].append({'points':[points[v] for v in tri.vertices],
            'key':_base._key([points[v] for v in tri.vertices]),'normals':normals,
            'uv':[tuple(mesh.uv_layers.active.data[li].uv) for li in tri.loops],
            'smooth':mesh.polygons[tri.polygon_index].use_smooth,'material_index':tri.material_index,
            'source_triangle':index,'source_field_minimum':_base.affine.preserve_field(normals,normals)})
    reference['triangles'].sort(key=lambda r:r['source_triangle'])
    reference['points']={points[v] for v in vertices}
    reference['domain'].update(complete_triangles=len(protected),protected_vertices=len(vertices),
        minimum_original_affine_length_lower=min(r['source_field_minimum']['minimum_original_length_lower'] for r in reference['triangles']),
        finite_lamp_extension={'profile_sha256':digest(policy),'domain_sha256':digest({'protected':sorted(protected),'added':added,'vertices':sorted(vertices)}),
            'original_protected_faces':len(inventory['protected_triangles']),'added_complete_faces':added,
            'finite_lamp_faces':sorted(core['lamp_plan']['domain']['selected_faces']),
            'source_field_policy':'Complete current native original geometry/UV/normal/material fields; no target repaint'})
    return reference
