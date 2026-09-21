"""Regenerate original linear-data paint microtextures for the reviewed finish."""
import hashlib
import bpy
from endurance_sedan import microtextures

def apply():
    material = bpy.data.materials['Material_Paint']
    nodes = material.node_tree.nodes
    shader = nodes['Principled BSDF']
    image_nodes = [n for n in nodes if n.type == 'TEX_IMAGE']
    images = {n.image for n in image_nodes}
    assert {i.name for i in images} == {'Meridian_paint_normal_v1', 'Meridian_paint_roughness_v1'}
    before = {i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in images}
    allowed = {'TEX_IMAGE', 'NORMAL_MAP', 'BSDF_PRINCIPLED', 'OUTPUT_MATERIAL'}
    assert all(n.type in allowed for n in nodes)
    for node in list(nodes):
        if node.type in {'TEX_IMAGE', 'NORMAL_MAP'}:
            nodes.remove(node)
    for image in images:
        assert image.users == 0, image.name
        bpy.data.images.remove(image)
    shader.inputs['Base Color'].default_value = (.004,.005,.006,1.)
    shader.inputs['Roughness'].default_value = .14
    shader.inputs['Coat Roughness'].default_value = .055
    material.diffuse_color = (.004,.005,.006,1.)
    material['coat_roughness'] = .055
    microtextures.apply(material,'paint',.14)
    after = {n.image.name:hashlib.sha256(n.image.packed_file.data).hexdigest()
             for n in nodes if n.type == 'TEX_IMAGE'}
    assert set(after) == set(before)
    assert before['Meridian_paint_normal_v1'] == after['Meridian_paint_normal_v1']
    assert before['Meridian_paint_roughness_v1'] != after['Meridian_paint_roughness_v1']
    return {'base_color_linear':[.004,.005,.006], 'coat_roughness':.055,
            'roughness_center':.14,'roughness_modulation':.02,
            'repeat_m':.25,'size_px':512,'texture_before_sha256':before,
            'texture_after_sha256':after,
            'scope':'Actual regenerated packed roughness texture, unchanged seeded normal map; no external material inputs.'}
