"""Exact scoped LOD1 cabin ratio dispatch; original decimation guards follow."""
import json

import bmesh
import bpy


EXPECTED_POLICY = {'schema': 'distance-lod29-cabin-reuse.v1', 'lod': 1, 'requested_ratio': 0.065, 'components': {'Material_Trim': ['LOD0_CenterConsole', 'LOD0_DashboardCore', 'LOD0_RearBulkheadLower', 'LOD0_RearConsoleChase', 'LOD0_SteeringColumn'], 'Material_Leather': ['LOD0_ConsoleArmrest', 'LOD0_Glovebox', 'LOD0_RearCenterBack', 'LOD0_RearCenterCushion'], 'Material_Carpet': ['LOD0_InstrumentShade', 'LOD0_InstrumentShadeWing_-1', 'LOD0_InstrumentShadeWing_1', 'LOD0_NavigationSurround', 'LOD0_RearBulkheadUpper', 'LOD0_RearDamperEnclosure_-1', 'LOD0_RearDamperEnclosure_1']}, 'whole_groups': [{'parent': 'Door_FL', 'material': 'Material_Leather', 'members': ['LOD0_Armrest_FL', 'LOD0_DoorCard_FL'], 'method': 'ordinary'}, {'parent': 'Door_FR', 'material': 'Material_Leather', 'members': ['LOD0_Armrest_FR', 'LOD0_DoorCard_FR'], 'method': 'ordinary'}, {'parent': 'Door_RL', 'material': 'Material_Leather', 'members': ['LOD0_Armrest_RL', 'LOD0_DoorCard_RL'], 'method': 'ordinary'}, {'parent': 'Door_RR', 'material': 'Material_Leather', 'members': ['LOD0_Armrest_RR', 'LOD0_DoorCard_RR'], 'method': 'ordinary'}, {'parent': 'Visual_LOD0', 'material': 'Material_Fabric', 'members': ['LOD0_FrontBeltWeb_-1', 'LOD0_FrontBeltWeb_1', 'LOD0_Headliner', 'LOD0_ParcelShelf', 'LOD0_RearBeltWeb_-1', 'LOD0_RearBeltWeb_1', 'LOD0_RearCenterBelt', 'LOD0_RearCenterBuckleWeb', 'LOD0_Sunvisor_-1', 'LOD0_Sunvisor_1'], 'method': 'selective'}], 'selective_addition': [1, 'Visual_LOD0', 'Material_Fabric']}


def validate(policy):
    if policy != EXPECTED_POLICY:
        raise ValueError('Unreviewed cabin ratio/member/LOD/group policy')


def target_names(policy):
    validate(policy)
    names = [name for values in policy['components'].values() for name in values]
    names += [name for group in policy['whole_groups'] for name in group['members']]
    if len(names) != len(set(names)) or len(names) != 34:
        raise ValueError('Missing or overlapping34 cabin inventory')
    return set(names)


def validate_source(originals, policy, eligibility):
    targets = target_names(policy)
    objects = {obj.name: obj for obj in originals}
    if not targets <= set(objects) or any(eligibility[n] != 2 for n in targets):
        raise ValueError('Cabin member absent or no longer eligible at both levels')
    expected = {name: ('Visual_LOD0', material) for material, names in policy['components'].items() for name in names}
    expected.update({name: (g['parent'], g['material']) for g in policy['whole_groups'] for name in g['members']})
    for name, (parent, material) in expected.items():
        obj = objects[name]
        used = {obj.data.materials[p.material_index].name for p in obj.data.polygons}
        if obj.type != 'MESH' or obj.parent is None or obj.parent.name != parent or used != {material}:
            raise ValueError('Cabin rigid-parent/material source contract differs: ' + name)


def group_ratio(level, parent, material, members, default, policy, seen):
    validate(policy)
    if level != 1:
        return default
    source_parent = 'Visual_LOD0' if parent == 'Visual_LOD1' else parent
    for group in policy['whole_groups']:
        if (source_parent, material) == (group['parent'], group['material']):
            names = [obj.name for obj in members]
            if len(names) != len(set(names)) or sorted(names) != sorted(group['members']):
                raise ValueError('Whole cabin batch membership differs')
            if seen & set(names):
                raise ValueError('Cabin members processed more than once')
            seen.update(names)
            return policy['requested_ratio']
    return default


def component_overrides(key, members, policy, seen):
    validate(policy)
    if key[0:2] != (1, 'Visual_LOD0') or key[2] not in policy['components']:
        return {}
    names = policy['components'][key[2]]
    actual = [obj.name for obj in members]
    if len(actual) != len(set(actual)) or not set(names) <= set(actual):
        raise ValueError('Partial cabin batch membership differs')
    if seen & set(names):
        raise ValueError('Cabin members processed more than once')
    seen.update(names)
    return {name: policy['requested_ratio'] for name in names}


def verify_seen(seen, policy):
    if seen != target_names(policy):
        raise ValueError('Incomplete or unexpected applied cabin policy inventory')


def make_lods(optimization, package, shell_certificate, collection, lods, distance_only_names=(), *, policy, seen):
    lod_paint, selective_lod = package.lod_paint, package.selective_lod
    originals = [obj for obj in collection.objects if obj.type == 'MESH' and obj.name.startswith('LOD0_')]
    distance_only_names = set(distance_only_names)
    missing = distance_only_names - {obj.name for obj in originals}
    if missing:
        raise ValueError('Declared distance-only source components are absent: ' + ', '.join(sorted(missing)))
    for obj in originals:
        obj['lod_index'] = 0
    bpy.context.view_layer.update()
    for obj in originals:
        # Subpixel hardware and stitched seams disappear before the medium LOD.
        # Named semantic anchors are empties and are never removed by this rule.
        if obj.name in distance_only_names or max(obj.dimensions) < .080 or any(word in obj.name for word in ('Stitch','Piping','CushionSeam','RotorVane','BrakeVane','LugBolt','ValveStem')):
            obj['maximum_lod'] = 0
    manifest = []
    selective_seen=set()
    for index, default_ratio in ((1, .23), (2, .065)):
        for ordinal, ((parent_name, material_name), members) in enumerate(optimization.groups(originals, index, lods[index])):
            ratio = group_ratio(index, parent_name, material_name, members, default_ratio, policy, seen)
            parent = bpy.data.objects[parent_name]
            name = f'LOD{index}_Batch_{ordinal:03d}_{optimization.clean_name(parent_name)}_{optimization.clean_name(material_name)}'
            obj, entry = optimization.bake_batch(name, members, parent, collection, bpy.data.materials[material_name])
            initial = len(obj.data.polygons)
            source_parent='Visual_LOD0' if parent_name in ('Visual_LOD1','Visual_LOD2') else parent_name
            key=(index,source_parent,material_name)
            if key in optimization.SELECTIVE_LOD_GROUPS:
                selective_seen.add(key)
                obsolete=obj.data
                bpy.data.objects.remove(obj,do_unlink=True)
                if obsolete.users==0:
                    bpy.data.meshes.remove(obsolete)
                obj,entry=selective_lod.simplify_group(name,members,parent,collection,
                    bpy.data.materials[material_name],ratio,expected_source_parent=source_parent,
                    original_group_triangles=initial,bake_batch=optimization.bake_batch,protected_paint=lod_paint,
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
    if selective_seen!=optimization.SELECTIVE_LOD_GROUPS:
        raise ValueError('A declared selective LOD semantic group is absent')
    bpy.context.scene['lod_construction'] = json.dumps(manifest, sort_keys=True)
