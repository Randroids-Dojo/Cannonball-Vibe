"""Portable native checkpoint API. No file IO, scene save or mandatory bpy import."""
import hashlib
import json
import math
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def plain(value):
    return json.loads(json.dumps(value,allow_nan=False))


def rna_values(value):
    result={}
    for prop in value.bl_rna.properties:
        key=prop.identifier
        if prop.is_readonly or key in ('rna_type','name','name_full'):continue
        if prop.type not in ('BOOLEAN','INT','FLOAT','STRING','ENUM'):continue
        item=getattr(value,key)
        if isinstance(item,set):item=sorted(item)
        elif getattr(prop,'is_array',False):item=list(item)
        result[key]=item
    return result


def material_fields(mesh):
    rows=[]
    for material in mesh.materials:
        if material is None:rows.append(None);continue
        row={'name':material.name,'values':rna_values(material),'nodes':[],'links':[]}
        if material.node_tree:
            for node in sorted(material.node_tree.nodes,key=lambda n:n.name):
                item={'name':node.name,'type':node.bl_idname,'values':rna_values(node),'inputs':[]}
                for socket in node.inputs:
                    if hasattr(socket,'default_value'):
                        value=socket.default_value
                        if value is not None and not isinstance(value,(str,float,int,bool)):
                            value=list(value) if hasattr(value,'__iter__') else {'id':value.name_full}
                        item['inputs'].append([socket.identifier,value])
                image=getattr(node,'image',None)
                if image:
                    import bpy
                    packed=image.packed_file
                    # Saving can rebase // URIs; before construction is saved,
                    # there may be no blend path at all. Actual image bytes,
                    # not a workstation path spelling, are the portable identity.
                    external=Path(os.path.normpath(bpy.path.abspath(image.filepath))) if not packed else None
                    item['image']={'name':image.name,'source':image.source,
                                   'colorspace':image.colorspace_settings.name,
                                   'packed_sha256':hashlib.sha256(packed.data).hexdigest() if packed else None,
                                   'external_sha256':hashlib.sha256(external.read_bytes()).hexdigest() if external else None}
                row['nodes'].append(item)
            row['links']=sorted([link.from_node.name,link.from_socket.identifier,link.to_node.name,link.to_socket.identifier]
                                for link in material.node_tree.links)
        rows.append(row)
    return rows


def native_state(obj,helper):
    if obj.type!='MESH' or obj.modifiers:raise ValueError('Checkpoint requires final native mesh without modifiers')
    mesh=obj.data;mesh.calc_loop_triangles()
    normals=[list(n.vector) for n in mesh.corner_normals]
    if not all(helper.valid_normal(n) for n in normals):raise ValueError('Invalid checkpoint raw normal')
    codes=mesh.attributes.get('custom_normal')
    if codes is None or codes.domain!='CORNER' or codes.data_type!='INT16_2D':
        raise ValueError('Missing native INT16 custom-normal codes')
    state={'object':obj.name,'coordinate_frame':[list(r) for r in obj.matrix_world],
           'physical':helper.fields(mesh),'material_response':material_fields(mesh),
           'normals':normals,'normal_codes':[list(n.value) for n in codes.data],
           'sharp':[e.use_edge_sharp for e in mesh.edges],
           'loops':[[loop.vertex_index,loop.edge_index] for loop in mesh.loops],
           'faces':[{'loops':list(face.loop_indices),'normal':list(face.normal)} for face in mesh.polygons],
           'triangles':[{'face':t.polygon_index,'vertices':list(t.vertices),'loops':list(t.loops)} for t in mesh.loop_triangles]}
    return plain(state)


def capture_checkpoint(obj,reference,profile,construction_inputs,helper,*,provenance):
    """Call synchronously immediately before helper.apply on the final bumper.

    construction_inputs: nonempty rows {role,path,sha256,bytes}; include exactly
    one specification, constructor, normal_module and ownership_module, plus
    every imported construction component. Caller hashes actual files before
    construction and rechecks them after save. provenance describes the real
    boundary; it is not a replacement for that command record.
    """
    helper.validate_profile(profile)
    helper.reference_field(obj,reference,profile)
    state=native_state(obj,helper)
    core={'schema':'shoulder-before-apply.v1','phase':'final-geometry-before-shoulder-apply',
          'profile':plain(profile),'profile_sha256':digest(profile),'reference':plain(reference),
          'reference_sha256':digest(reference),'construction_inputs':plain(construction_inputs),
          'constructor_inputs_sha256':digest(construction_inputs),'before':state,
          'before_sha256':digest(state),'provenance':plain(provenance)}
    return {'core':core,'sha256':digest(core)}


def complete_packet(checkpoint,witness):
    """Call after apply; retain the complete witness and explicit partition."""
    witness=plain(witness)
    targets=sorted(row['loop'] for row in witness['details']+witness['propagated_boundary_fans'])
    if len(targets)!=len(set(targets)):raise ValueError('Duplicate witness target')
    count=len(checkpoint['core']['before']['normals'])
    if not targets or any(type(i) is not int or not 0<=i<count for i in targets):raise ValueError('Invalid target inventory')
    selected=set(targets)
    core={'schema':'shoulder-construction-packet.v1','checkpoint':checkpoint,'witness':witness,
          'witness_sha256':digest(witness),'selected_corners':targets,
          'unselected_corners':[i for i in range(count) if i not in selected]}
    return {'core':core,'sha256':digest(core)}
