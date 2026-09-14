"""Two-case staged normal-only finish; caller supplies actual construction rows.

No source, report, export or rendering IO. The native tank field algorithm is
injected, with complete actual surface coverage. No cooler dimensions copied
from a historical payload: original uncut_body comes from this construction.
"""
import bpy


def merge(rows):
    vertices=[];triangles=[]
    for row in rows:
        offset=len(vertices)
        vertices.extend(row['vertices'])
        triangles.extend([[offset+i for i in t] for t in row['triangles']])
    return {'name':'ActualThreeChargePortSurfaces','vertices':vertices,'triangles':triangles}


def shape(snapshot):
    result=dict(snapshot)
    result['attributes']={k:v for k,v in snapshot['attributes'].items() if k not in ('sharp_edge','custom_normal')}
    return result


def apply(construction, *, reference, row, encode, complete_boundary, exact_scan, evaluated_counts):
    targets={f'LOD0_WaterToAirChargeCooler_{p["side"]}':p for p in construction}
    if set(targets) != {'LOD0_WaterToAirChargeCooler_-1','LOD0_WaterToAirChargeCooler_1'}:
        raise ValueError('Expected two actual in-process cooler construction records')
    staged=[];owned_meshes=[];proof={};assigned=False
    try:
        for name, original in sorted(targets.items()):
            obj=bpy.data.objects[name]
            if obj.type!='MESH' or obj.modifiers or obj.data.has_custom_normals or any(p.use_smooth for p in obj.data.polygons):
                raise ValueError('Expected the exact initially flat applied candidate21 case')
            before=reference.fingerprint(obj.data)
            old_row=row(obj)
            old_normals=[tuple(n.vector) for n in obj.data.corner_normals]
            side=original['side']
            ports=merge([row(bpy.data.objects[f'LOD0_{kind}_{side}']) for kind in ('HotChargePipe','ColdChargePipe','ChargeCoolantHose')])
            stage=obj.copy();stage.data=obj.data.copy();stage.name='Private_CoolerChamfer_'+str(side)
            obj.users_collection[0].objects.link(stage);staged.append((obj,stage));owned_meshes.append(stage.data)
            mesh=stage.data
            sharp=mesh.attributes.get('sharp_edge') or mesh.attributes.new(name='sharp_edge',type='BOOLEAN',domain='EDGE')
            for value in sharp.data:value.value=True
            mesh.normals_split_custom_set(old_normals)
            for value in mesh.attributes['custom_normal'].data:value.value=(0,0)
            mesh.update()
            if [tuple(n.vector) for n in mesh.corner_normals] != old_normals:
                raise ValueError('Automatic flat fields changed when creating independent native spaces')
            if shape(reference.fingerprint(mesh)) != shape(before):
                raise ValueError('Independent native normal spaces changed another surface field')
            result=reference.apply(stage,original['new_uncut_cooler'],ports,
                row=row,encode=encode,boundary_shell=complete_boundary,
                exact_scan=exact_scan,evaluated_counts=evaluated_counts)
            owned_meshes.append(stage.data)
            after=row(stage)
            if any(after[k]!=old_row[k] for k in old_row if k not in ('name','normals')):
                raise ValueError('Cooler finish changed a non-normal evaluated field')
            if shape(reference.fingerprint(stage.data)) != shape(before):
                raise ValueError('Cooler finish changed original geometry/UV/material/flags')
            if stage.parent!=obj.parent or stage.matrix_world!=obj.matrix_world:
                raise ValueError('Cooler frame or parent changed')
            retained=result['retained_loops']
            if any(tuple(stage.data.corner_normals[i].vector)!=old_normals[i] for i in retained):
                raise ValueError('Original panel/socket field is not exact')
            result['initially_automatic_flat_normals']=True
            result['protected_auto_codes_retained_zero']=True
            result['original_geometry_uv_material_flags_exact']=True
            result['receiving_ports']=[f'LOD0_{kind}_{side}' for kind in ('HotChargePipe','ColdChargePipe','ChargeCoolantHose')]
            proof[name]=result
        # The original two objects are touched only after both staged cases pass.
        for obj,stage in staged:obj.data=stage.data
        assigned=True
        return proof
    finally:
        for _,stage in staged:
            data=stage.data;bpy.data.objects.remove(stage,do_unlink=True)
            if data not in owned_meshes:owned_meshes.append(data)
        for data in owned_meshes:
            if data.users==0:bpy.data.meshes.remove(data)
