"""Original material families; no third-party texture or model inputs."""

import bpy


def principled(name, color, roughness, metallic=0, coat=0, alpha=1, emission=None):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Coat Weight"].default_value = coat
    shader.inputs["Coat Roughness"].default_value = 0.10
    shader.inputs["Alpha"].default_value = alpha
    material.diffuse_color = (*color, alpha)
    if alpha < 1:
        shader.inputs["IOR"].default_value = 1.52
        shader.inputs["Transmission Weight"].default_value = 0.60
        material.surface_render_method = "DITHERED"
    if emission:
        shader.inputs["Emission Color"].default_value = (*emission, 1)
        shader.inputs["Emission Strength"].default_value = 0.1
    material["provenance"] = "Project-original physical-response parameters; no external image input"
    material["cv_shader"] = "standard"
    material["coat_weight"] = coat
    material["coat_roughness"] = 0.10
    return material


def build():
    result={
        "paint":principled("Material_Paint",(.008,.010,.012),.25,coat=1),
        "trim":principled("Material_Trim",(.016,.018,.020),.36),
        "rubber":principled("Material_Rubber",(.014,.014,.015),.68),
        "leather":principled("Material_Leather",(.022,.024,.026),.48),
        "carpet":principled("Material_Carpet",(.014,.015,.017),.91),
        "fabric":principled("Material_Fabric",(.032,.034,.037),.79),
        "alloy":principled("Material_Alloy",(.15,.16,.17),.29,metallic=1),
        "metal":principled("Material_Metal",(.23,.24,.25),.35,metallic=1),
        "wheel":principled("Material_Wheel",(.029,.032,.035),.26,metallic=.85),
        "caliper":principled("Material_Caliper",(.05,.053,.056),.30,metallic=.6),
        "glass":principled("Material_Glass",(.035,.042,.048),.075,alpha=.20),
        "glass_rear":principled("Material_GlassPrivacy",(.012,.016,.021),.09,alpha=.58),
        "optical_glass":principled("Material_OpticalGlass",(.65,.72,.79),.035,alpha=.20),
        "plate":principled("Material_Plate",(.44,.45,.47),.6),
        "mirror":principled("Material_Mirror",(.84,.87,.89),.015,metallic=1),
        "headlight":principled("Material_Headlight",(.58,.67,.77),.16,emission=(.85,.91,1)),
        "taillight":principled("Material_Taillight",(.20,.004,.006),.20,emission=(1,.007,.01)),
        "brake":principled("Material_BrakeLight",(.25,.004,.006),.18,emission=(1,.004,.008)),
        "reverse":principled("Material_ReverseLight",(.46,.50,.56),.18,emission=(.85,.92,1)),
        "indicator_left":principled("Material_IndicatorLeft",(.42,.09,.004),.20,emission=(1,.21,.003)),
        "indicator_right":principled("Material_IndicatorRight",(.42,.09,.004),.20,emission=(1,.21,.003)),
        "screen":principled("Material_Screen",(.006,.010,.013),.26),
        "stitch":principled("Material_Stitch",(.15,.16,.17),.72),
        "cabin_lettering":principled("Material_CabinLettering",(.5,.65,.75),.6,emission=(.5,.65,.75)),
    }
    result['cabin_lettering'].node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value=.2
    from . import microtextures
    for key,kind,roughness in (('paint','paint',.25),('leather','leather',.48),('fabric','fabric',.79)):
        microtextures.apply(result[key],kind,roughness)
    return result
