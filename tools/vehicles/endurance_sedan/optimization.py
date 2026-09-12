"""Derived LODs and deterministic batching within one material and rigid parent.

The editable LOD0 assemblies remain individual source objects. LOD0 export
batching preserves evaluated triangles, normals and UVs with exact range maps.
Lower LOD maps explicitly distinguish original pre-simplification membership
from ranges constructed after per-component simplification.
"""

import json
from pathlib import Path
import re
import sys
from collections import defaultdict

import bmesh
import bpy
from mathutils import Matrix


PRESERVE_EXPORT = {
    'LOD0_Tire_' + suffix for suffix in ('FL', 'FR', 'RL', 'RR')
} | {'LOD0_Pedal_AcceleratorPad', 'LOD0_Pedal_BrakePad',
     'CollisionProxy_Body', 'CollisionProxy_Cabin', 'LOD0_Roof'}

# Independent corner-attribute comparison found larger split-normal encoding
# drift on these evaluated assemblies after rebatching. Keep their original
# meshes; the remaining batches still remove over a thousand source objects.
PRESERVE_EXPORT |= {
    'LOD0_Door_'+suffix for suffix in ('FL','FR','RL','RR')
} | {
    'LOD0_Hood','LOD0_Trunk','LOD0_FrontBumper','LOD0_RearBumper',
    'LOD0_FrontFender_L','LOD0_FrontFender_R','LOD0_StructuralBody',
    'LOD0_V8Crankcase','LOD0_Sump','LOD0_DoorCard_RL','LOD0_DoorCard_RR',
    'LOD0_DoorFrame_FR','LOD0_DoorGlassSeal_FR','LOD0_CabinFloor',
    'LOD0_FrontUndertray_-1','LOD0_FrontUndertray_1',
    'LOD0_MainFuelLobe_-1','LOD0_MainFuelLobe_1','LOD0_TransferPump',
}

# Actual indexed-shell failures identify these rigid-parent/material groups.
# Selection uses source semantics; transient batch ordinals carry no authority.
SELECTIVE_LOD_GROUPS = {
    (1,'Visual_LOD0','Material_'+material) for material in ('Metal','OpticalGlass','Rubber','Trim')
} | {
    (lod,parent,'Material_Paint') for lod in (1,2) for parent in ('Door_RL','Door_RR')
} | {
    (2,parent,'Material_BrakeLight') for parent in ('Light_Brake_L','Light_Brake_R')
} | {(2,'Light_Tail_RL','Material_Taillight')} | {
    (2,'Visual_LOD0','Material_'+material)
    for material in ('Fabric','Metal','Mirror','OpticalGlass','Paint','Rubber','Trim')
}
assert len(SELECTIVE_LOD_GROUPS)==18


def clean_name(value):
    return re.sub(r'[^A-Za-z0-9_]', '_', value)


def groups(objects, lod_index, target_parent=None):
    result = defaultdict(list)
    for obj in sorted(objects, key=lambda item: item.name):
        if obj.type != 'MESH' or obj.get('source_preview_only', False):
            continue
        if lod_index > obj.get('maximum_lod', 2):
            continue
        used_indices = {polygon.material_index for polygon in obj.data.polygons}
        materials = list({obj.material_slots[index].material for index in used_indices})
        # This source contract deliberately uses one material per mesh. A later
        # author must handle a multi-material mesh explicitly rather than lose it.
        if len(materials) != 1 or materials[0] is None:
            raise ValueError('Batch requires exactly one material: ' + obj.name)
        parent = target_parent if target_parent and obj.parent.name == 'Visual_LOD0' else obj.parent
        if parent is None:
            raise ValueError('Batch requires a declared rigid parent: ' + obj.name)
        result[(parent.name, materials[0].name)].append(obj)
    return sorted(result.items())


def bake_batch(name, members, parent, collection, material):
    vertices, faces, normals, uvs, smooth = [], [], [], [], []
    components = []
    graph = bpy.context.evaluated_depsgraph_get()
    parent_inverse = parent.matrix_world.inverted_safe()
    for obj in members:
        evaluated = obj.evaluated_get(graph)
        data = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        try:
            data.calc_loop_triangles()
            transform = parent_inverse @ obj.matrix_world
            normal_transform = transform.to_3x3().inverted().transposed()
            offset, first_triangle = len(vertices), len(faces)
            vertices.extend(tuple(transform @ vertex.co) for vertex in data.vertices)
            layer = data.uv_layers.active
            if layer is None:
                raise ValueError('Missing UV layer in ' + obj.name)
            for triangle in data.loop_triangles:
                faces.append(tuple(offset + index for index in triangle.vertices))
                smooth.append(data.polygons[triangle.polygon_index].use_smooth)
                for loop in triangle.loops:
                    uvs.append(tuple(layer.data[loop].uv))
                    normals.append(tuple((normal_transform @ data.corner_normals[loop].vector).normalized()))
            components.append({
                'source_component': obj.name,
                'source_parent': obj.parent.name,
                'vertex_start': offset, 'vertex_count': len(data.vertices),
                'triangle_start': first_triangle, 'triangle_count': len(data.loop_triangles),
                'component_to_batch': [list(row) for row in transform],
            })
        finally:
            evaluated.to_mesh_clear()
    data = bpy.data.meshes.new(name + 'Mesh')
    data.from_pydata(vertices, [], faces)
    data.materials.append(material)
    data.update()
    uv = data.uv_layers.new(name='SurfaceMeters')
    uv.data.foreach_set('uv', [value for pair in uvs for value in pair])
    for polygon, use_smooth in zip(data.polygons, smooth):
        polygon.use_smooth = use_smooth
    data.normals_split_custom_set(normals)
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.parent = parent
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)
    obj['source_components'] = json.dumps([item['source_component'] for item in components])
    return obj, {
        'batch': name, 'parent': parent.name, 'material': material.name,
        'triangles': len(faces), 'components': components,
        'method': 'Evaluated triangles, corner UVs and normals in common rigid parent coordinates',
    }


def make_lods(collection, lods):
    from . import lod_paint, selective_lod
    qa_path=str(Path(__file__).resolve().with_name('qa'))
    sys.path.insert(0,qa_path)
    try:
        from lod_self_intersections import shell_certificate
    finally:
        sys.path.remove(qa_path)
    originals = [obj for obj in collection.objects if obj.type == 'MESH' and obj.name.startswith('LOD0_')]
    for obj in originals:
        obj['lod_index'] = 0
    bpy.context.view_layer.update()
    for obj in originals:
        # Subpixel hardware and stitched seams disappear before the medium LOD.
        # Named semantic anchors are empties and are never removed by this rule.
        if max(obj.dimensions) < .080 or any(word in obj.name for word in ('Stitch','Piping','CushionSeam','RotorVane','BrakeVane','LugBolt','ValveStem')):
            obj['maximum_lod'] = 0
    manifest = []
    selective_seen=set()
    for index, ratio in ((1, .23), (2, .065)):
        for ordinal, ((parent_name, material_name), members) in enumerate(groups(originals, index, lods[index])):
            parent = bpy.data.objects[parent_name]
            name = f'LOD{index}_Batch_{ordinal:03d}_{clean_name(parent_name)}_{clean_name(material_name)}'
            obj, entry = bake_batch(name, members, parent, collection, bpy.data.materials[material_name])
            initial = len(obj.data.polygons)
            source_parent='Visual_LOD0' if parent_name in ('Visual_LOD1','Visual_LOD2') else parent_name
            key=(index,source_parent,material_name)
            if key in SELECTIVE_LOD_GROUPS:
                selective_seen.add(key)
                obsolete=obj.data
                bpy.data.objects.remove(obj,do_unlink=True)
                if obsolete.users==0:
                    bpy.data.meshes.remove(obsolete)
                obj,entry=selective_lod.simplify_group(name,members,parent,collection,
                    bpy.data.materials[material_name],ratio,expected_source_parent=source_parent,
                    original_group_triangles=initial,bake_batch=bake_batch,protected_paint=lod_paint,
                    shell_certificate=shell_certificate,
                    include_rear_door_quarter=index==1 and source_parent in ('Door_RL','Door_RR'))
                entry['lod']=index
                manifest.append(entry)
                obj['lod_index']=index
                obj.hide_render=True
                obj.hide_set(True)
                continue
            base = obj.data.copy()
            protected_paint = lod_paint.prepare(obj)
            attempts = []
            for candidate_ratio in sorted(set((ratio, min(1,ratio*2), min(1,ratio*4), 1.0))):
                old = obj.data
                obj.data = base.copy()
                if old.users == 0:bpy.data.meshes.remove(old)
                if initial > 50 and candidate_ratio < 1 and not (protected_paint and protected_paint['full']):
                    decimate = obj.modifiers.new('Measured distance LOD simplification', 'DECIMATE')
                    decimate.ratio = lod_paint.configure(obj, decimate, protected_paint, candidate_ratio)
                    decimate.use_collapse_triangulate = True
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.modifier_apply(modifier=decimate.name)
                changed = obj.data.validate(clean_customdata=False)
                obj.data.update()
                audit = bmesh.new();audit.from_mesh(obj.data)
                invalid_edges = sum(not edge.is_manifold for edge in audit.edges)
                audit.free()
                obj.data.calc_loop_triangles()
                degenerate = sum(triangle.area <= 1e-12 for triangle in obj.data.loop_triangles)
                attempts.append({'ratio':candidate_ratio,'mesh_validate_changed':changed,
                                 'nonmanifold_edges':invalid_edges,'degenerate_triangles':degenerate})
                if not changed and not invalid_edges and not degenerate:break
            else:
                raise ValueError('No valid closed LOD candidate for '+name+': '+str(attempts))
            protected_result = lod_paint.restore(obj, protected_paint)
            if base.users == 0:bpy.data.meshes.remove(base)
            obj.data.calc_loop_triangles()
            entry.update({'lod': index, 'requested_ratio': ratio,
                          'triangles_after': len(obj.data.loop_triangles), 'attempts': attempts,
                          'rear_paint_preservation': protected_result})
            entry['source_components_before_simplification']=entry.pop('components')
            entry['component_range_domain']='Original input only; no final component ranges are claimed after batch Decimate'
            manifest.append(entry)
            obj['lod_index'] = index
            obj.hide_render = True
            obj.hide_set(True)
    if selective_seen!=SELECTIVE_LOD_GROUPS:
        raise ValueError('A declared selective LOD semantic group is absent')
    bpy.context.scene['lod_construction'] = json.dumps(manifest, sort_keys=True)


def batch_export(collection):
    mappings = []
    preserved=PRESERVE_EXPORT | {obj.name for obj in collection.objects if obj.type=='MESH'
                                and obj.name.startswith('LOD0_') and ('Mirror' in obj.name or 'Antenna' in obj.name or obj.get('lettering_provenance'))}
    originals = [obj for obj in collection.objects if obj.type == 'MESH'
                 and obj.name.startswith('LOD0_') and obj.name not in preserved]
    for ordinal, ((parent_name, material_name), members) in enumerate(groups(originals, 0)):
        name = f'LOD0_Batch_{ordinal:03d}_{clean_name(parent_name)}_{clean_name(material_name)}'
        obj, entry = bake_batch(name, members, bpy.data.objects[parent_name], collection,
                                bpy.data.materials[material_name])
        obj['lod_index'] = 0
        entry['lod'] = 0
        mappings.append(entry)
    for obj in originals:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    return {
        'preserved_meshes': sorted(preserved), 'batches': mappings,
        'source_component_count': sum(len(item['components']) for item in mappings),
        'export_batch_count': len(mappings),
        'shape_change': 'None; no simplification or welding occurs during LOD0 batching',
    }
