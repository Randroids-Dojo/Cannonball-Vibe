"""Create isolated invalid sedan sources to prove the production gate rejects them."""

import argparse
import sys
from pathlib import Path

import bpy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mutation", required=True, choices=[
        "unapplied-scale", "missing-semantic-node", "external-texture",
        "unparked-control", "hardpoint-drift", "degenerate-triangle",
    ])
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.output.resolve() == args.source.resolve():
        raise ValueError("A negative-control output must not overwrite its source")
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    if args.mutation == "unapplied-scale":
        mesh = sorted((obj for obj in bpy.data.collections["Asset"].all_objects
                       if obj.type == "MESH" and obj.name.startswith("LOD0_")), key=lambda obj: obj.name)[0]
        mesh.scale.x = 1.25
    elif args.mutation == "missing-semantic-node":
        bpy.data.objects["Camera_Cockpit"].name = "BrokenCockpitAnchor"
    elif args.mutation == "external-texture":
        texture_path = args.output.with_suffix(".png").resolve()
        generated = bpy.data.images.new("NegativeExternalTexture", width=2, height=2)
        generated.filepath_raw = str(texture_path)
        generated.file_format = "PNG"
        generated.save()
        bpy.data.images.remove(generated)
        image = bpy.data.images.load(str(texture_path))
        material = bpy.data.materials["Material_Paint"]
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        material.node_tree.links.new(node.outputs["Color"], material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"])
    elif args.mutation == "unparked-control":
        bpy.data.objects["RigControls"]["Door_FL_open"] = 0.5
    elif args.mutation == "hardpoint-drift":
        bpy.data.objects["Camera_Cockpit"].location.x += 0.02
    elif args.mutation == "degenerate-triangle":
        mesh = bpy.data.meshes.new("NegativeDegenerateGeometry")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [], [(0, 1, 2)])
        mesh.uv_layers.new(name="UVMap")
        obj = bpy.data.objects.new("LOD0_NegativeDegenerateTriangle", mesh)
        bpy.data.collections["Asset"].objects.link(obj)
        obj.parent = bpy.data.objects["AssetRoot"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), compress=True)
    print("CANNONBALL_SEDAN_NEGATIVE_SOURCE_CREATED mutation=" + args.mutation)


if __name__ == "__main__":
    main()
