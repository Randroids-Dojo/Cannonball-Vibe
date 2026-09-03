"""Create the project-original conifer Blender source and its rendered card textures.

The tree is a ponderosa-style pine built for MultiMesh instancing at highway
speed: a bark-mapped trunk and whorls of needle cards, three declared LODs,
and an impostor. Nothing here is sampled from third-party geometry; the needle
card and impostor textures are rendered from procedurally modelled needle
clusters in this file, so the asset is project-original and its provenance is
this script plus the pinned Blender build.

Outputs (all deterministic for a given Blender build):
  --output      the .blend source of record
  --textures    directory receiving conifer-needles-albedo.png,
                conifer-needles-normal.png and conifer-impostor.png

Units are metres. The tree is 1.0 m tall in source so instance scale is the
tree height in metres; a mature roadside ponderosa runs 10 to 20 m.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

SEED = 20260902
NEEDLE_TEXTURE_SIZE = 1024
IMPOSTOR_WIDTH = 512
IMPOSTOR_HEIGHT = 1024


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--textures", required=True, type=Path)
    return parser.parse_args(argv)


# ----------------------------------------------------------------- helpers


def material(name: str, color, *, roughness=0.9, metallic=0.0) -> bpy.types.Material:
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    value.diffuse_color = color
    return value


def empty(name, collection, parent=None, location=(0, 0, 0), role=None):
    value = bpy.data.objects.new(name, None)
    collection.objects.link(value)
    value.parent = parent
    value.location = location
    value.empty_display_type = "PLAIN_AXES"
    value.empty_display_size = 0.1
    value["semantic_role"] = role or name
    return value


def mesh_object(name, mesh, collection, parent, surface):
    value = bpy.data.objects.new(name, mesh)
    collection.objects.link(value)
    value.parent = parent
    if surface is not None:
        mesh.materials.append(surface)
    value["semantic_role"] = name
    return value


def ensure_color_layer(bm: bmesh.types.BMesh):
    layer = bm.loops.layers.color.get("Col")
    if layer is None:
        layer = bm.loops.layers.color.new("Col")
    return layer


def ensure_uv_layer(bm: bmesh.types.BMesh):
    layer = bm.loops.layers.uv.get("UVMap")
    if layer is None:
        layer = bm.loops.layers.uv.new("UVMap")
    return layer


# ----------------------------------------------------------------- trunk


def build_trunk(rng: random.Random, segments: int, rings: int, lean: float) -> bpy.types.Mesh:
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    color_layer = ensure_color_layer(bm)
    ring_vertices = []
    lean_direction = Vector((math.cos(lean), math.sin(lean), 0.0))
    for ring in range(rings + 1):
        t = ring / rings
        radius = 0.034 * (1.0 - t) ** 0.9 + 0.004
        if t < 0.08:
            radius += (0.08 - t) * 0.35  # root flare
        wobble = (rng.random() - 0.5) * 0.006 * t
        center = lean_direction * (0.012 * t * t + wobble) + Vector((0.0, 0.0, t))
        row = []
        for segment in range(segments):
            angle = segment / segments * math.tau
            offset = Vector((math.cos(angle), math.sin(angle), 0.0)) * radius
            row.append(bm.verts.new(center + offset))
        ring_vertices.append(row)
    bm.verts.ensure_lookup_table()
    for ring in range(rings):
        for segment in range(segments):
            nxt = (segment + 1) % segments
            a = ring_vertices[ring][segment]
            b = ring_vertices[ring][nxt]
            c = ring_vertices[ring + 1][nxt]
            d = ring_vertices[ring + 1][segment]
            face = bm.faces.new((a, b, c, d))
            face.smooth = True
            for loop in face.loops:
                v = loop.vert
                index_ring = ring if v in (a, b) else ring + 1
                seg = segment if v in (a, d) else segment + 1
                loop[uv_layer].uv = (seg / segments * 2.0, index_ring / rings * 6.0)
                loop[color_layer] = (1.0, 0.7 + 0.3 * (index_ring / rings), 1.0, 0.0)
    top = bm.verts.new(Vector((0, 0, 1.0)) + lean_direction * 0.012)
    for segment in range(segments):
        nxt = (segment + 1) % segments
        face = bm.faces.new((ring_vertices[rings][segment], ring_vertices[rings][nxt], top))
        face.smooth = True
        for loop in face.loops:
            loop[uv_layer].uv = (0.5, 6.0)
            loop[color_layer] = (1.0, 1.0, 1.0, 0.0)
    mesh = bpy.data.meshes.new("TrunkMesh")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


# ----------------------------------------------------------------- needle cards


def add_card(bm, uv_layer, color_layer, base: Vector, direction: Vector, up: Vector, length: float,
             width: float, sway: float, shade: float, ao: float, droop: float):
    """One textured quad from `base` along `direction`, `up` is the card normal side."""
    side = direction.cross(up).normalized() * (width * 0.5)
    tip = base + direction * length - up * droop * length
    mid = base + direction * (length * 0.5) - up * droop * length * 0.35
    corners = [
        base - side,
        base + side,
        tip + side,
        tip - side,
    ]
    verts = [bm.verts.new(c) for c in corners]
    face = bm.faces.new(verts)
    face.smooth = True
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    sways = [sway * 0.35, sway * 0.35, sway, sway]
    for loop, uv, s in zip(face.loops, uvs, sways):
        loop[uv_layer].uv = uv
        loop[color_layer] = (shade, ao, 1.0, s)
    # Bend the card midway so it does not read as a flat plank.
    bmesh.ops.subdivide_edges(bm, edges=[e for e in face.edges if (e.verts[0].co - e.verts[1].co).length > width], cuts=1)
    for v in bm.verts:
        if (v.co - mid).length < width * 0.6 and abs((v.co - base).dot(direction) - length * 0.5) < length * 0.2:
            v.co -= up * droop * length * 0.12


def build_crown(rng: random.Random, whorls: int, cards_per_branch: int, detail: float) -> bpy.types.Mesh:
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    color_layer = ensure_color_layer(bm)
    for whorl in range(whorls):
        t = 0.24 + (whorl / max(1, whorls - 1)) * 0.70
        crown_radius = 0.30 * (1.0 - (t - 0.24) / 0.76) ** 0.85 + 0.02
        branches = max(3, int(round((5 + rng.random() * 3) * detail)))
        base_angle = rng.random() * math.tau
        for branch in range(branches):
            angle = base_angle + branch / branches * math.tau + (rng.random() - 0.5) * 0.35
            radial = Vector((math.cos(angle), math.sin(angle), 0.0))
            tilt = 0.10 + rng.random() * 0.18 - (1.0 - t) * 0.08
            direction = (radial + Vector((0, 0, tilt))).normalized()
            base = Vector((0, 0, t)) + radial * 0.02
            length = crown_radius * (0.95 + rng.random() * 0.35)
            width = length * (0.70 + rng.random() * 0.25)
            shade = 0.82 + rng.random() * 0.18
            ao = 0.55 + 0.45 * t
            for card in range(cards_per_branch):
                roll = (card / cards_per_branch) * math.pi + rng.random() * 0.4
                up = Vector((0, 0, 1)).cross(direction).normalized()
                up = (Vector((0, 0, 1)) * math.cos(roll) + up * math.sin(roll)).normalized()
                add_card(bm, uv_layer, color_layer, base, direction, up, length, width,
                         sway=0.5 + 0.5 * t, shade=shade, ao=ao, droop=0.18 + rng.random() * 0.2)
    # Leader: two crossed cards for the pointed top.
    for roll in (0.0, math.pi / 2):
        up = Vector((math.cos(roll), math.sin(roll), 0.0))
        add_card(bm, uv_layer, color_layer, Vector((0, 0, 0.90)), Vector((0, 0, 1)), up, 0.11, 0.07,
                 sway=1.0, shade=0.95, ao=1.0, droop=0.0)
    mesh = bpy.data.meshes.new("CrownMesh")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def build_impostor() -> bpy.types.Mesh:
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    color_layer = ensure_color_layer(bm)
    half = 0.34
    for angle in (0.0, math.pi / 2):
        right = Vector((math.cos(angle), math.sin(angle), 0.0)) * half
        verts = [
            bm.verts.new(-right),
            bm.verts.new(right),
            bm.verts.new(right + Vector((0, 0, 1.0))),
            bm.verts.new(-right + Vector((0, 0, 1.0))),
        ]
        face = bm.faces.new(verts)
        for loop, uv in zip(face.loops, [(0, 0), (1, 0), (1, 1), (0, 1)]):
            loop[uv_layer].uv = uv
            loop[color_layer] = (1.0, 1.0, 1.0, 0.0)
    mesh = bpy.data.meshes.new("ImpostorMesh")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


# ----------------------------------------------------------------- needle cluster for the card texture


def build_needle_cluster(rng: random.Random, collection, needle_material, twig_material):
    """A twig with spiralling needles, viewed from +Z by the card camera."""
    root = bpy.data.objects.new("NeedleClusterRoot", None)
    collection.objects.link(root)
    bm = bmesh.new()
    twig_bm = bmesh.new()

    def twig(start: Vector, end: Vector, radius: float):
        direction = (end - start).normalized()
        side = direction.cross(Vector((0, 0, 1))).normalized() * radius
        up = direction.cross(side).normalized() * radius
        rings = []
        for point in (start, end):
            rings.append([twig_bm.verts.new(point + side), twig_bm.verts.new(point + up),
                          twig_bm.verts.new(point - side), twig_bm.verts.new(point - up)])
        for i in range(4):
            twig_bm.faces.new((rings[0][i], rings[0][(i + 1) % 4], rings[1][(i + 1) % 4], rings[1][i]))

    def needles_along(start: Vector, end: Vector, count: int, length: float, spread: float):
        axis = (end - start).normalized()
        perp = axis.cross(Vector((0, 0, 1))).normalized()
        for index in range(count):
            t = index / count
            base = start + (end - start) * t
            angle = index * 2.399963 + rng.random() * 0.4  # golden angle spiral
            outward = (perp * math.cos(angle) + axis.cross(perp) * math.sin(angle)).normalized()
            direction = (axis * 0.55 + outward * spread + Vector((0, 0, 0.12 * math.sin(angle)))).normalized()
            tip = base + direction * length * (0.8 + rng.random() * 0.4)
            width = 0.012
            side = direction.cross(Vector((0, 0, 1))).normalized() * width
            v = [bm.verts.new(base - side), bm.verts.new(base + side), bm.verts.new(tip)]
            bm.faces.new(v)
            side2 = direction.cross(side).normalized() * width
            v = [bm.verts.new(base - side2), bm.verts.new(base + side2), bm.verts.new(tip + Vector((0, 0, 0.002)))]
            bm.faces.new(v)

    trunk_start = Vector((-0.46, 0.0, 0.0))
    trunk_end = Vector((0.34, 0.0, 0.0))
    twig(trunk_start, trunk_end, 0.011)
    needles_along(trunk_start + Vector((0.08, 0, 0)), trunk_end, 120, 0.15, 0.9)
    for sign in (-1, 1):
        for k in range(4):
            t = 0.18 + k * 0.22
            base = trunk_start + (trunk_end - trunk_start) * t
            end = base + Vector((0.18, sign * 0.26, 0.0))
            twig(base, end, 0.006)
            needles_along(base + Vector((0.03, sign * 0.04, 0)), end, 70, 0.12, 0.85)
    needle_mesh = bpy.data.meshes.new("NeedleClusterMesh")
    bm.to_mesh(needle_mesh)
    bm.free()
    twig_mesh = bpy.data.meshes.new("NeedleTwigMesh")
    twig_bm.to_mesh(twig_mesh)
    twig_bm.free()
    needles = bpy.data.objects.new("NeedleCluster", needle_mesh)
    needles.data.materials.append(needle_material)
    twigs = bpy.data.objects.new("NeedleTwig", twig_mesh)
    twigs.data.materials.append(twig_material)
    for item in (needles, twigs):
        collection.objects.link(item)
        item.parent = root
    return root


# ----------------------------------------------------------------- rendering


def render_rgba(scene, camera, collection_visible, width, height, path: Path, normal_pass: bool):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.camera = camera
    for collection in scene.collection.children:
        collection.hide_render = collection.name not in collection_visible
    view_layer = scene.view_layers[0]
    if normal_pass:
        # Render world-space normals into colour through an emission material
        # override so the card gets a matching normal map.
        override = bpy.data.materials.get("NormalOverride")
        if override is None:
            override = bpy.data.materials.new("NormalOverride")
            override.use_nodes = True
            nodes = override.node_tree.nodes
            links = override.node_tree.links
            for node in list(nodes):
                nodes.remove(node)
            geometry = nodes.new("ShaderNodeNewGeometry")
            mapping = nodes.new("ShaderNodeVectorMath")
            mapping.operation = "MULTIPLY_ADD"
            mapping.inputs[1].default_value = (0.5, 0.5, 0.5)
            mapping.inputs[2].default_value = (0.5, 0.5, 0.5)
            emission = nodes.new("ShaderNodeEmission")
            output = nodes.new("ShaderNodeOutputMaterial")
            links.new(geometry.outputs["Normal"], mapping.inputs[0])
            links.new(mapping.outputs[0], emission.inputs["Color"])
            links.new(emission.outputs[0], output.inputs["Surface"])
        view_layer.material_override = override
    else:
        view_layer.material_override = None
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    view_layer.material_override = None


# ----------------------------------------------------------------- main


def main() -> None:
    args = arguments()
    args.output = args.output.resolve()
    args.textures = args.textures.resolve()
    rng = random.Random(SEED)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.world = bpy.data.worlds.new("ConiferPreviewWorld")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.65, 0.7, 1.0)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

    asset = bpy.data.collections.new("Asset")
    scene.collection.children.link(asset)
    preview = bpy.data.collections.new("Preview")
    scene.collection.children.link(preview)
    card_stage = bpy.data.collections.new("CardStage")
    scene.collection.children.link(card_stage)

    bark = material("Material_Bark", (0.36, 0.22, 0.14, 1.0), roughness=0.95)
    needles_material = material("Material_Needles", (0.16, 0.30, 0.13, 1.0), roughness=0.85)
    impostor_material = material("Material_Impostor", (0.16, 0.30, 0.13, 1.0), roughness=0.9)
    needle_render = material("NeedleRender", (0.075, 0.19, 0.06, 1.0), roughness=0.75)
    twig_render = material("TwigRender", (0.18, 0.11, 0.07, 1.0), roughness=0.9)

    root = empty("AssetRoot", asset, role="asset_root")
    root["asset_id"] = "conifer"
    empty("Anchor_Origin", asset, root, role="origin_anchor")
    lod0 = empty("Visual_LOD0", asset, root, role="lod_0")
    lod1 = empty("Visual_LOD1", asset, root, role="lod_1")
    lod2 = empty("Visual_LOD2", asset, root, role="lod_2")
    lod1.hide_render = True
    lod2.hide_render = True

    lean = rng.random() * math.tau
    mesh_object("LOD0_Trunk", build_trunk(rng, segments=10, rings=12, lean=lean), asset, lod0, bark)
    mesh_object("LOD0_Needles", build_crown(rng, whorls=11, cards_per_branch=3, detail=1.15), asset, lod0, needles_material)
    rng_lod1 = random.Random(SEED + 1)
    mesh_object("LOD1_Trunk", build_trunk(rng_lod1, segments=6, rings=5, lean=lean), asset, lod1, bark)
    mesh_object("LOD1_Needles", build_crown(rng_lod1, whorls=5, cards_per_branch=1, detail=0.7), asset, lod1, needles_material)
    mesh_object("LOD2_Impostor", build_impostor(), asset, lod2, impostor_material)

    collision_mesh = bpy.data.meshes.new("CollisionProxyMesh")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.06, radius2=0.03, depth=1.0)
    for v in bm.verts:
        v.co.z += 0.5
    bm.to_mesh(collision_mesh)
    bm.free()
    collision = mesh_object("CollisionProxy", collision_mesh, asset, root, bark)
    collision.hide_render = True
    collision["collision_kind"] = "cylinder"

    # Needle card stage: a cluster on its own, seen from above.
    cluster = build_needle_cluster(rng, card_stage, needle_render, twig_render)
    cluster.location = (0, 0, -20)
    card_camera_data = bpy.data.cameras.new("CardCamera")
    card_camera_data.type = "ORTHO"
    card_camera_data.ortho_scale = 1.12
    card_camera = bpy.data.objects.new("CardCamera", card_camera_data)
    card_camera.location = (-0.04, 0.0, -18.0)
    card_camera.rotation_euler = (0.0, 0.0, 0.0)
    card_stage.objects.link(card_camera)
    for name, energy, location in (("CardKey", 2.2, (1.5, -1.0, -17.0)), ("CardFill", 0.7, (-1.5, 1.2, -17.5))):
        light_data = bpy.data.lights.new(name, "SUN")
        light_data.energy = energy
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        light.rotation_euler = (Vector(location) - Vector((0, 0, -20))).to_track_quat("Z", "Y").to_euler()
        card_stage.objects.link(light)

    # Preview camera and lights for the contact sheet and impostor.
    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    preview.objects.link(camera)
    scene.camera = camera
    camera_data.lens = 50
    impostor_camera_data = bpy.data.cameras.new("ImpostorCamera")
    impostor_camera_data.type = "ORTHO"
    impostor_camera_data.ortho_scale = 1.06
    impostor_camera = bpy.data.objects.new("ImpostorCamera", impostor_camera_data)
    impostor_camera.location = (0.0, -4.0, 0.5)
    impostor_camera.rotation_euler = (math.pi / 2, 0.0, 0.0)
    preview.objects.link(impostor_camera)
    for name, energy, location in (("PreviewKey", 2.6, (3, -4, 5)), ("PreviewFill", 0.9, (-4, -2, 3))):
        light_data = bpy.data.lights.new(name, "SUN")
        light_data.energy = energy
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        light.rotation_euler = (Vector(location) - Vector((0, 0, 0.5))).to_track_quat("Z", "Y").to_euler()
        preview.objects.link(light)

    # Textures: needle card (albedo + normal) from the cluster, impostor from LOD0.
    args.textures.mkdir(parents=True, exist_ok=True)
    render_rgba(scene, card_camera, {"CardStage"}, NEEDLE_TEXTURE_SIZE, NEEDLE_TEXTURE_SIZE,
                args.textures / "conifer-needles-albedo.png", normal_pass=False)
    render_rgba(scene, card_camera, {"CardStage"}, NEEDLE_TEXTURE_SIZE, NEEDLE_TEXTURE_SIZE,
                args.textures / "conifer-needles-normal.png", normal_pass=True)
    # Apply the rendered card to the needle material for the impostor bake only;
    # the runtime binds the same PNG through its own shader, and the source
    # material keeps no image so the export stays texture-free.
    card_image = bpy.data.images.load(str(args.textures / "conifer-needles-albedo.png"))
    bake_material = material("NeedleBake", (1, 1, 1, 1), roughness=0.85)
    nodes = bake_material.node_tree.nodes
    links = bake_material.node_tree.links
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = card_image
    shader = nodes.get("Principled BSDF")
    links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    links.new(tex.outputs["Alpha"], shader.inputs["Alpha"])
    bake_material.blend_method = "CLIP" if hasattr(bake_material, "blend_method") else None
    bake_material.use_backface_culling = False
    needles_object = bpy.data.objects["LOD0_Needles"]
    needles_object.data.materials[0] = bake_material
    hidden = [bpy.data.objects[name] for name in ("LOD1_Trunk", "LOD1_Needles", "LOD2_Impostor", "CollisionProxy")]
    for item in hidden:
        item.hide_render = True
    render_rgba(scene, impostor_camera, {"Asset", "Preview"}, IMPOSTOR_WIDTH, IMPOSTOR_HEIGHT,
                args.textures / "conifer-impostor.png", normal_pass=False)
    for item in hidden:
        item.hide_render = item.name == "CollisionProxy"
    needles_object.data.materials[0] = needles_material
    bpy.data.materials.remove(bake_material)
    bpy.data.images.remove(card_image)
    # The card stage is a build-time fixture, not part of the asset.
    for item in list(card_stage.objects):
        bpy.data.objects.remove(item)
    scene.collection.children.unlink(card_stage)
    bpy.data.collections.remove(card_stage)
    for collection in scene.collection.children:
        collection.hide_render = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=True)
    print(f"CANNONBALL_CONIFER_SOURCE_OK path={args.output}")


if __name__ == "__main__":
    main()
