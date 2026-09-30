"""Private member-only finite-foot Boolean; no source assignment or file I/O.

The lead-scoped new termination uses the actual current closed body as a
receiver. FACE provenance is carried through the native Boolean and checked
later against complete original triangles; it is not accepted by label alone.
"""
import bpy, bmesh
from endurance_sedan import roof_feature26 as native, geometry
from endurance_sedan.qa.self_geometry import scan
ATTRIBUTE = 'c29_foot_origin'

def marked_copy(original, name, sign):
    obj = original.copy()
    obj.data = original.data.copy()
    obj.name = name
    bpy.context.scene.collection.objects.link(obj)
    mesh = obj.data
    if any((len(p.vertices) != 3 for p in mesh.polygons)):
        raise ValueError('Finite foot requires actual triangulated input')
    if mesh.attributes.get(ATTRIBUTE):
        raise ValueError('Finite foot provenance attribute already exists')
    indices = [p.index for p in mesh.polygons]
    layer = mesh.attributes.new(ATTRIBUTE, 'INT', 'FACE')
    for i in indices:
        layer.data[i].value = sign * (i + 1)
    return obj

def make(member, body):
    old_member = native.physical(member)
    old_body = native.physical(body)
    obj = marked_copy(member, 'Private_CQuarter_Foot78', 1)
    cutter = marked_copy(body, 'Private_CQuarter_FootReceiver78', -1)
    try:
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new('Finite current body receiving foot', 'BOOLEAN')
        modifier.operation = 'DIFFERENCE'
        modifier.solver = 'EXACT'
        modifier.object = cutter
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        origins = [d.value for d in obj.data.attributes[ATTRIBUTE].data]
        if len(origins) != len(obj.data.polygons) or any((v == 0 for v in origins)):
            raise ValueError('Native foot origin missing')
        for p in obj.data.polygons:
            p.material_index = 0
        row = native.row(obj)
        proof = {'native_origin_per_triangle': origins, 'native_counts': geometry.evaluated_counts(obj), 'exact_self': scan(row), 'original_member_row': native.row(member), 'actual_body_row': native.row(body), 'field_status': 'not yet restored; native diagnostic only'}
        if native.physical(member) != old_member or native.physical(body) != old_body:
            raise ValueError('Private foot trial changed its actual source inputs')
        return (obj, proof)
    except BaseException:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise
    finally:
        mesh = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
