"""Hero GT materials: Principled node trees with sourced CC0 textures, and
the custom properties Godot needs to rebuild what glTF cannot carry.

Godot 4.7 imports base colour, metallic-roughness, normal, occlusion and
emissive textures plus emissive strength, and keeps material custom
properties as ``extras`` metadata. It drops clearcoat, specular and
transmission, so every material here also records ``cv_*`` properties the
project-owned wrapper reads by name: shader family, clear-coat parameters,
flake scale, glass tint. The Blender values are still set so the contact
sheet and previews show the same intent.

Texture paths are absolute at build time; the glTF export embeds the images.
"""

from __future__ import annotations

import math
from pathlib import Path

import bmesh
import bpy

SOURCED = Path("assets/vehicles/sourced")


class Textures:
    """Resolves sourced texture files by set id and map name."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.loaded: dict[str, bpy.types.Image] = {}

    def image(self, relative: str, non_color: bool = False) -> bpy.types.Image:
        path = (self.repo_root / relative).resolve()
        key = str(path)
        if key not in self.loaded:
            if not path.exists():
                raise FileNotFoundError(path)
            image = bpy.data.images.load(str(path), check_existing=True)
            image.name = path.name
            if non_color:
                image.colorspace_settings.name = "Non-Color"
            self.loaded[key] = image
        return self.loaded[key]

    def ambientcg(self, asset: str, attribute: str, map_name: str, extension: str = "jpg") -> bpy.types.Image:
        non_color = map_name != "Color"
        return self.image(f"{SOURCED}/ambientcg/{asset}/{asset}_{attribute}_{map_name}.{extension}", non_color)


def _node(tree, kind: str, location=(0, 0), **props):
    node = tree.nodes.new(kind)
    node.location = location
    for key, value in props.items():
        setattr(node, key, value)
    return node


def principled(
    name: str,
    color=(0.5, 0.5, 0.5, 1.0),
    *,
    metallic: float = 0.0,
    roughness: float = 0.5,
    specular: float = 0.5,
    coat: float = 0.0,
    coat_roughness: float = 0.05,
    alpha: float = 1.0,
    emission=None,
    emission_strength: float = 1.0,
    textures: dict | None = None,
    uv_scale: tuple[float, float] = (1.0, 1.0),
    extras: dict | None = None,
    backface_culling: bool = True,
    normal_strength: float = 1.0,
) -> bpy.types.Material:
    """A Principled material; ``textures`` maps color/normal/roughness/
    metalness/opacity/ao to loaded images."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = color
    material.use_backface_culling = backface_culling
    tree = material.node_tree
    shader = tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Specular IOR Level"].default_value = specular
    if coat > 0:
        shader.inputs["Coat Weight"].default_value = coat
        shader.inputs["Coat Roughness"].default_value = coat_roughness
    if emission is not None:
        shader.inputs["Emission Color"].default_value = emission
        shader.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        shader.inputs["Alpha"].default_value = alpha
        material.surface_render_method = "BLENDED"
    textures = textures or {}
    if textures:
        mapping = None
        if uv_scale != (1.0, 1.0):
            coords = _node(tree, "ShaderNodeTexCoord", (-1100, 0))
            mapping = _node(tree, "ShaderNodeMapping", (-900, 0))
            mapping.inputs["Scale"].default_value = (uv_scale[0], uv_scale[1], 1.0)
            tree.links.new(coords.outputs["UV"], mapping.inputs["Vector"])
        y = 300
        for key, image in textures.items():
            tex = _node(tree, "ShaderNodeTexImage", (-650, y), image=image)
            if mapping is not None:
                tree.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
            if key == "color":
                if color != (1.0, 1.0, 1.0, 1.0):
                    mix = _node(tree, "ShaderNodeMix", (-300, y), data_type="RGBA", blend_type="MULTIPLY")
                    mix.inputs["Factor"].default_value = 1.0
                    mix.inputs[7].default_value = color
                    tree.links.new(tex.outputs["Color"], mix.inputs[6])
                    tree.links.new(mix.outputs[2], shader.inputs["Base Color"])
                else:
                    tree.links.new(tex.outputs["Color"], shader.inputs["Base Color"])
            elif key == "normal":
                normal_map = _node(tree, "ShaderNodeNormalMap", (-300, y))
                normal_map.inputs["Strength"].default_value = normal_strength
                tree.links.new(tex.outputs["Color"], normal_map.inputs["Color"])
                tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
            elif key == "roughness":
                tree.links.new(tex.outputs["Color"], shader.inputs["Roughness"])
            elif key == "metalness":
                tree.links.new(tex.outputs["Color"], shader.inputs["Metallic"])
            elif key == "opacity":
                tree.links.new(tex.outputs["Color"], shader.inputs["Alpha"])
                material.surface_render_method = "DITHERED"
                material["cv_alpha_scissor"] = 0.5
            elif key == "ao":
                occlusion = _gltf_output(tree)
                tree.links.new(tex.outputs["Color"], occlusion.inputs["Occlusion"])
            y -= 300
    for key, value in (extras or {}).items():
        material[key] = value
    return material


def _gltf_output(tree):
    """The exporter's occlusion hook: a node group named 'glTF Material Output'."""
    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        group.nodes.new("NodeGroupInput")
    node = tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    node.location = (200, -400)
    return node


def build_materials(textures: Textures) -> dict[str, bpy.types.Material]:
    """Every material the Hero GT uses, keyed by role."""
    t = textures
    paint_color = (0.040, 0.125, 0.270, 1.0)
    materials = {}
    materials["paint"] = principled(
        "Material_Body", paint_color, metallic=0.30, roughness=0.22, coat=1.0, coat_roughness=0.03,
        textures={"normal": t.ambientcg("Paint005", "1K-JPG", "NormalGL")}, uv_scale=(3.0, 3.0), normal_strength=0.1,
        extras={"cv_shader": "car_paint", "cv_clearcoat": 1.0, "cv_clearcoat_roughness": 0.03, "cv_normal_strength": 0.1,
                "cv_flake_scale": 900.0, "cv_flake_strength": 0.22, "cv_edge_tint": [0.02, 0.05, 0.12]},
    )
    materials["dark"] = principled("Material_Shut", (0.006, 0.006, 0.007, 1.0), roughness=0.85, specular=0.3)
    materials["glass"] = principled(
        "Material_Glass", (0.012, 0.02, 0.03, 1.0), roughness=0.04, alpha=0.62, specular=0.5,
        extras={"cv_shader": "glass", "cv_tint": [0.55, 0.62, 0.68]},
    )
    materials["lens_glass"] = principled(
        "Material_LensGlass", (0.20, 0.24, 0.30, 1.0), roughness=0.03, alpha=0.10, specular=0.7,
        extras={"cv_shader": "glass"},
    )
    materials["lens_glass_red"] = principled(
        "Material_LensGlassRed", (0.60, 0.04, 0.03, 1.0), roughness=0.05, alpha=0.45, specular=0.6,
        extras={"cv_shader": "glass"},
    )
    materials["chrome"] = principled(
        "Material_Chrome", (0.94, 0.94, 0.95, 1.0), metallic=1.0, roughness=0.06,
        textures={"normal": t.ambientcg("Metal051A", "1K-JPG", "NormalGL")}, uv_scale=(4.0, 4.0),
    )
    materials["carbon"] = principled(
        "Material_Carbon", (0.75, 0.75, 0.78, 1.0), metallic=0.0, roughness=0.32, coat=1.0, coat_roughness=0.06,
        textures={
            "color": t.ambientcg("Fabric004", "2K-JPG", "Color"),
            "normal": t.ambientcg("Fabric004", "2K-JPG", "NormalGL"),
            "roughness": t.ambientcg("Fabric004", "2K-JPG", "Roughness"),
        },
        uv_scale=(6.0, 6.0),
        extras={"cv_shader": "clearcoat", "cv_clearcoat": 1.0, "cv_clearcoat_roughness": 0.06},
    )
    materials["housing"] = principled(
        "Material_Trim", (0.30, 0.30, 0.31, 1.0), roughness=0.6,
        textures={
            "color": t.ambientcg("Plastic012A", "1K-JPG", "Color"),
            "normal": t.ambientcg("Plastic012A", "1K-JPG", "NormalGL"),
            "roughness": t.ambientcg("Plastic012A", "1K-JPG", "Roughness"),
        },
        uv_scale=(5.0, 5.0),
    )
    materials["cavity"] = principled("Material_Cavity", (0.004, 0.004, 0.005, 1.0), roughness=0.95, specular=0.2)
    # Wheel-well liners are seen from outside through the arch and from
    # inside the cabin, where a single-sided shell would show the tyres.
    materials["well"] = principled(
        "Material_Well", (0.20, 0.20, 0.21, 1.0), roughness=0.75,
        textures={
            "color": t.ambientcg("Plastic012A", "1K-JPG", "Color"),
            "normal": t.ambientcg("Plastic012A", "1K-JPG", "NormalGL"),
        },
        uv_scale=(4.0, 4.0), backface_culling=False,
    )
    materials["grille"] = principled(
        "Material_Grille", (0.9, 0.9, 0.9, 1.0), metallic=0.85, roughness=0.45,
        textures={
            "color": t.ambientcg("SheetMetal001", "1K-PNG", "Color", "png"),
            "normal": t.ambientcg("SheetMetal001", "1K-PNG", "NormalGL", "png"),
            "roughness": t.ambientcg("SheetMetal001", "1K-PNG", "Roughness", "png"),
            "opacity": t.ambientcg("SheetMetal001", "1K-PNG", "Opacity", "png"),
        },
        backface_culling=False,
    )
    materials["headlamp"] = principled(
        "Material_Headlight", (0.85, 0.92, 1.0, 1.0), roughness=0.1, emission=(0.75, 0.88, 1.0, 1.0), emission_strength=4.0,
    )
    materials["led"] = principled(
        "Material_HeadlightLed", (1.0, 1.0, 1.0, 1.0), roughness=0.2, emission=(0.85, 0.93, 1.0, 1.0), emission_strength=7.0,
    )
    materials["taillamp"] = principled(
        "Material_Taillight", (0.62, 0.015, 0.02, 1.0), roughness=0.2, emission=(1.0, 0.02, 0.02, 1.0), emission_strength=5.0,
    )
    materials["plate"] = principled("Material_Plate", (0.88, 0.88, 0.85, 1.0), roughness=0.45)
    materials["tyre"] = principled(
        "Material_Tire", (0.80, 0.80, 0.81, 1.0), roughness=0.85, specular=0.3, normal_strength=0.8,
        textures={
            "color": t.image(f"{SOURCED}/texturecan/plastic_0022/plastic_0022_color_2k.jpg"),
            "normal": t.image(f"{SOURCED}/texturecan/plastic_0022/plastic_0022_normal_opengl_2k.jpg", True),
            "roughness": t.image(f"{SOURCED}/texturecan/plastic_0022/plastic_0022_roughness_2k.jpg", True),
            "ao": t.image(f"{SOURCED}/texturecan/plastic_0022/plastic_0022_ao_2k.jpg", True),
        },
        uv_scale=(1.0, 1.0),
    )
    materials["tyre_side"] = principled(
        "Material_TireSidewall", (0.16, 0.16, 0.165, 1.0), roughness=0.88, specular=0.3,
        textures={
            "color": t.ambientcg("Plastic012A", "1K-JPG", "Color"),
            "normal": t.ambientcg("Plastic012A", "1K-JPG", "NormalGL"),
            "roughness": t.ambientcg("Plastic012A", "1K-JPG", "Roughness"),
        },
        uv_scale=(1.0, 1.0), normal_strength=0.6,
    )
    materials["rim"] = principled(
        "Material_Wheel", (0.30, 0.31, 0.33, 1.0), metallic=1.0, roughness=0.28,
        textures={"normal": t.ambientcg("Metal051A", "1K-JPG", "NormalGL"), "roughness": t.ambientcg("Metal051A", "1K-JPG", "Roughness")},
        uv_scale=(3.0, 3.0), extras={"cv_shader": "metal"},
    )
    materials["rim_dark"] = principled("Material_WheelBarrel", (0.04, 0.04, 0.045, 1.0), metallic=0.9, roughness=0.55)
    materials["disc"] = principled(
        "Material_BrakeDisc", (0.55, 0.55, 0.56, 1.0), metallic=1.0, roughness=0.42,
        textures={"color": t.ambientcg("Metal051A", "1K-JPG", "Color"), "normal": t.ambientcg("Metal051A", "1K-JPG", "NormalGL"),
                  "roughness": t.ambientcg("Metal051A", "1K-JPG", "Roughness")},
        uv_scale=(2.0, 2.0),
    )
    materials["hat"] = principled("Material_BrakeHat", (0.08, 0.08, 0.085, 1.0), metallic=0.8, roughness=0.5)
    materials["caliper"] = principled("Material_Brake", (0.62, 0.035, 0.02, 1.0), metallic=0.15, roughness=0.32, coat=0.6)
    materials["leather"] = principled(
        "Material_Interior", (0.55, 0.53, 0.52, 1.0), roughness=0.6, specular=0.4,
        textures={"color": t.ambientcg("Leather027", "1K-JPG", "Color"), "normal": t.ambientcg("Leather027", "1K-JPG", "NormalGL"),
                  "roughness": t.ambientcg("Leather027", "1K-JPG", "Roughness")},
        uv_scale=(2.5, 2.5),
    )
    materials["dash_leather"] = principled(
        "Material_InteriorDash", (0.42, 0.40, 0.40, 1.0), roughness=0.62, specular=0.4,
        textures={"color": t.ambientcg("Leather026", "1K-JPG", "Color"), "normal": t.ambientcg("Leather026", "1K-JPG", "NormalGL"),
                  "roughness": t.ambientcg("Leather026", "1K-JPG", "Roughness")},
        uv_scale=(2.0, 2.0),
    )
    materials["suede"] = principled(
        "Material_InteriorSuede", (0.20, 0.20, 0.22, 1.0), roughness=0.9, specular=0.25,
        textures={"color": t.image(f"{SOURCED}/polyhaven/scuba_suede/scuba_suede_diff_1k.jpg"),
                  "normal": t.image(f"{SOURCED}/polyhaven/scuba_suede/scuba_suede_nor_gl_1k.jpg", True)},
        uv_scale=(3.0, 3.0),
    )
    materials["alu"] = principled(
        "Material_InteriorAlu", (0.8, 0.8, 0.82, 1.0), metallic=1.0, roughness=0.35,
        textures={"color": t.ambientcg("Metal009", "1K-JPG", "Color"), "normal": t.ambientcg("Metal009", "1K-JPG", "NormalGL"),
                  "roughness": t.ambientcg("Metal009", "1K-JPG", "Roughness")},
        uv_scale=(2.0, 2.0),
    )
    materials["plastic"] = principled("Material_InteriorPlastic", (0.03, 0.03, 0.032, 1.0), roughness=0.7, specular=0.35)
    materials["screen"] = principled(
        "Material_Screen", (0.02, 0.03, 0.05, 1.0), roughness=0.15, emission=(0.10, 0.35, 0.60, 1.0), emission_strength=2.5,
    )
    return materials


def box_uv(obj: bpy.types.Object, scale: float = 1.0) -> None:
    """Project UVs per face along its dominant normal axis (tri-planar box map)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    bm.normal_update()
    for face in bm.faces:
        n = face.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for loop in face.loops:
            co = loop.vert.co
            if ax >= ay and ax >= az:
                uv = (co.y, co.z)
            elif ay >= ax and ay >= az:
                uv = (co.x, co.z)
            else:
                uv = (co.x, co.y)
            loop[uv_layer].uv = (uv[0] * scale, uv[1] * scale)
    bm.to_mesh(obj.data)
    bm.free()


def cylinder_uv(obj: bpy.types.Object, axis: str = "X", repeats: float = 1.0, length_scale: float = 1.0) -> None:
    """Wrap UVs around an axis: u from the angle, v along the axis."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    for face in bm.faces:
        angles = []
        for loop in face.loops:
            co = loop.vert.co
            if axis == "X":
                a, along = math.atan2(co.z, co.y), co.x
            elif axis == "Y":
                a, along = math.atan2(co.z, co.x), co.y
            else:
                a, along = math.atan2(co.y, co.x), co.z
            angles.append((loop, a, along))
        base = angles[0][1]
        for loop, a, along in angles:
            if a - base > math.pi:
                a -= math.tau
            elif base - a > math.pi:
                a += math.tau
            loop[uv_layer].uv = (a / math.tau * repeats, along * length_scale)
    bm.to_mesh(obj.data)
    bm.free()
