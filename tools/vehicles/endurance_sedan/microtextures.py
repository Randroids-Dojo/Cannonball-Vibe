"""Seeded original physical-scale microtextures packed into the editable source.

No external image inputs, network resources or nondeterministic random state.
The pinned Blender NumPy generator and formulas are the reproducible inputs.
"""

import hashlib

import bpy
import numpy as np


def packed_image(name, rgb):
    height,width,_=rgb.shape
    image=bpy.data.images.new(name,width=width,height=height,alpha=False,float_buffer=False)
    image.colorspace_settings.name='Non-Color'
    rgba=np.ones((height,width,4),dtype=np.float32);rgba[:,:,:3]=rgb
    image.pixels.foreach_set(rgba.ravel())
    # filepath's RNA setter reloads and can discard generated pixels. Assign
    # the non-reloading path, then align the packed record's independent path.
    image.filepath_raw='//textures/'+name+'.png'
    image.file_format='PNG';image.pack()
    for packed in image.packed_files:packed.filepath=image.filepath_raw
    image['provenance']='Project-original seeded mathematical texture; microtextures.py'
    image['physical_repeat_m']=.25
    return image


def field(kind,size,seed):
    rng=np.random.default_rng(seed)
    noise=rng.random((size,size),dtype=np.float32)-.5
    # Periodic smoothing leaves seamless borders and removes single-pixel spikes.
    for _ in range(2):
        noise=(noise+np.roll(noise,1,0)+np.roll(noise,-1,0)+np.roll(noise,1,1)+np.roll(noise,-1,1))/5
    u,v=np.meshgrid(np.arange(size)/size,np.arange(size)/size)
    if kind=='paint':return noise*.000014
    if kind=='leather':return (noise+.10*np.sin(u*2*np.pi*91)*np.sin(v*2*np.pi*77))*.00016
    return (np.sin(u*2*np.pi*125)*np.sin(v*2*np.pi*125)*.45+noise*.15)*.00022


def apply(material,kind,roughness,size=512):
    seed=int.from_bytes(hashlib.sha256(('meridian-s8r-'+kind+'-v1').encode()).digest()[:8],'little')
    heights=field(kind,size,seed)
    spacing=.25/size
    dx=(np.roll(heights,-1,1)-np.roll(heights,1,1))/(2*spacing)
    dy=(np.roll(heights,-1,0)-np.roll(heights,1,0))/(2*spacing)
    normal=np.stack((-dx,-dy,np.ones_like(dx)),axis=-1)
    normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
    normal_image=packed_image('Meridian_'+kind+'_normal_v1',(normal+1)/2)
    modulation=heights/(np.max(np.abs(heights))+1e-12)
    rough=np.clip(roughness+modulation*(.020 if kind=='paint' else .045),0,1)
    rough_image=packed_image('Meridian_'+kind+'_roughness_v1',np.repeat(rough[:,:,None],3,axis=2))
    nodes=material.node_tree.nodes;links=material.node_tree.links
    shader=nodes['Principled BSDF']
    normal_tex=nodes.new('ShaderNodeTexImage');normal_tex.name='Physical microstructure normal';normal_tex.image=normal_image
    normal_node=nodes.new('ShaderNodeNormalMap');normal_node.inputs['Strength'].default_value=.60 if kind=='paint' else 1
    links.new(normal_tex.outputs['Color'],normal_node.inputs['Color']);links.new(normal_node.outputs['Normal'],shader.inputs['Normal'])
    rough_tex=nodes.new('ShaderNodeTexImage');rough_tex.name='Physical roughness variation';rough_tex.image=rough_image
    links.new(rough_tex.outputs['Color'],shader.inputs['Roughness'])
    material['microtexture_seed']=str(seed)
    material['microtexture_repeat_m']=.25
    material['microtexture_texels_per_meter']=size/.25
    material['microtexture_construction']='Original seamless height-derived tangent normals and independent roughness; linear data'
