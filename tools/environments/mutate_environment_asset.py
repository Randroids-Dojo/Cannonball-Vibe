"""Create intentionally invalid environment-asset sources for gate regression checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--mutation",
        required=True,
        choices=["unapplied-scale", "missing-semantic-node", "external-texture"],
    )
    return parser.parse_args(argv)


def main() -> None:
    args = arguments()
    args.source = args.source.resolve()
    args.output = args.output.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    if args.mutation == "unapplied-scale":
        bpy.data.objects["Visual_LOD0"].scale.x = 1.25
    elif args.mutation == "missing-semantic-node":
        bpy.data.objects["Anchor_Origin"].name = "BrokenAnchor"
    else:
        texture_path = args.output.with_suffix(".png")
        generated = bpy.data.images.new("GeneratedTexture", width=1, height=1)
        generated.filepath_raw = str(texture_path)
        generated.file_format = "PNG"
        generated.save()
        bpy.data.images.remove(generated)
        image = bpy.data.images.load(str(texture_path))
        material = bpy.data.materials["Material_Needles"]
        shader = material.node_tree.nodes.get("Principled BSDF")
        texture = material.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image = image
        material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=True)
    print(f"CANNONBALL_ENVIRONMENT_MUTATION_OK mutation={args.mutation} path={args.output}")


if __name__ == "__main__":
    main()
