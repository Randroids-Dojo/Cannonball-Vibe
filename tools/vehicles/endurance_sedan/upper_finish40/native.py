"""Install explicit upper meshes while retaining original object and rig frames."""
import bpy

from .. import corner_encoding, reserve_correspondence26, source_generation as records
from ..bevel_reserve26 import modifier_state
from ..front_finish40.native import verify_fields as complete_fields
from ..qa.upper_finish_report import INPUTS, NAMES, require


def capture(obj):
    return records.read_plain(reserve_correspondence26.evaluated(obj))


def frame(obj):
    return {'parent': obj.parent.name if obj.parent else None,
            'matrix_world': [list(row) for row in obj.matrix_world],
            'matrix_parent_inverse': [list(row) for row in obj.matrix_parent_inverse],
            'matrix_basis': [list(row) for row in obj.matrix_basis],
            'rotation_mode': obj.rotation_mode,
            'modifiers': records.read_plain(modifier_state(obj))}


def protected(obj):
    return records.digest({'raw': reserve_correspondence26.raw(obj), 'frame': frame(obj),
                           'custom_normals': obj.data.has_custom_normals})


def verify_fields(actual, requested):
    return complete_fields(actual, requested, names=NAMES)


def install(plans):
    require(set(plans) == set(NAMES), 'Incomplete current upper installation domain')
    identity = [[float(i == j) for j in range(4)] for i in range(4)]
    originals = {name: bpy.data.objects[name] for name in NAMES}
    before_frames = {name: frame(obj) for name, obj in originals.items()}
    staged, encodings = {}, {}
    try:
        for name, plan in plans.items():
            original = originals[name]
            require(original.type == 'MESH' and before_frames[name]['matrix_world'] == identity,
                    'Current upper requires the original closed rest frame: ' + name)
            require([material.name if material else None for material in original.data.materials]
                    == plan['materials'], 'Current upper changes material slots: ' + name)
            mesh = bpy.data.meshes.new(name + '_UpperSections40')
            obj = original.copy()
            obj.name = name + '_UpperEncoding40'
            obj.data = mesh
            bpy.context.scene.collection.objects.link(obj)
            staged[name] = obj
            obj.modifiers.clear()
            mesh.from_pydata(plan['vertices'], [], plan['triangles'])
            mesh.update()
            require([list(face.vertices) for face in mesh.polygons] == plan['triangles'],
                    'Current upper changed oriented native triangle order')
            for material in original.data.materials:
                mesh.materials.append(material)
            for face, material in zip(mesh.polygons, plan['triangle_materials'], strict=True):
                face.use_smooth = True
                face.material_index = material
            for channel, triangles in plan['uv_corner_targets'].items():
                layer = mesh.uv_layers.new(name=channel)
                for item, value in zip(layer.data, [uv for triangle in triangles for uv in triangle], strict=True):
                    item.uv = value
            require(not mesh.validate(clean_customdata=False), 'Current upper native validation changed geometry')
            encodings[name] = corner_encoding.encode(mesh,
                [normal for triangle in plan['normal_corner_targets'] for normal in triangle])
            require(encodings[name]['passed'], 'Current upper native field encoding failed: ' + name)
        bpy.context.view_layer.update()
        preview = {name: dict(capture(obj), name=name) for name, obj in staged.items()}
        fields = verify_fields(preview, plans)
        # Assignment happens only after every staged original-frame mesh passes.
        # The earlier saved checkpoint remains recovery authority on any failure.
        for name, obj in originals.items():
            obj.data = staged[name].data
            obj.modifiers.clear()
        bpy.context.view_layer.update()
        actual = {name: capture(obj) for name, obj in originals.items()}
        require(actual == preview, 'Installed upper differs from original-frame staged fields')
        after_frames = {name: frame(obj) for name, obj in originals.items()}
        require(after_frames == {name: dict(value, modifiers=[]) for name, value in before_frames.items()},
                'Current upper installation changed an original rig frame')
        # The companion crosses a JSON/file boundary before cold observation.
        # Native encoder diagnostics include integer keys and tuple values;
        # normalize them here so warm and reopened proof comparisons agree.
        return records.read_plain({'after': actual, 'encoding': encodings, 'complete_fields': fields,
                'before_frames': before_frames, 'after_frames': after_frames,
                'source_saved': False, 'exported': False})
    finally:
        for obj in staged.values():
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def input_rows():
    return {name: capture(bpy.data.objects[name]) for name in INPUTS}
