"""Measure the sun direction of each locked sky HDRI and write the runtime sky presets.

Runs inside the pinned Blender so the HDR decoder is the one the asset
pipeline already trusts. For every preset the brightest cluster of the
equirectangular panorama is located, converted to azimuth and elevation, and
mapped to the Godot DirectionalLight3D rotation that makes shadows fall away
from the visible sun. The output file is loaded at runtime by
game/World/Environment/SkyLighting.cs.

Godot's panorama sky maps direction d to
    u = atan2(d.x, -d.z) / 2pi   (wrapped to [0, 1)),   v = acos(d.y) / pi
so an HDRI column u_sun is the azimuth phi = 2pi * u_sun measured from -Z toward
+X. A DirectionalLight3D with rotation (pitch p, yaw y, 0) travels along
(-cos p sin y, sin p, -cos p cos y); the sun sits opposite that vector, so the
light yaw that puts the sun at phi is y = phi - pi and the pitch is minus the
elevation.

Usage (from the repository root):
  "$BLENDER_BIN" --background --factory-startup --python-exit-code 1 \
      --python tools/environments/analyze_skies.py -- \
      --lock data/assets/environments/sourced-assets.lock.json \
      --output assets/environments/sky-presets.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy

PRESETS = {
    "day": "polyhaven/kloofendal_48d_partly_cloudy_puresky",
    "dawn": "polyhaven/kloppenheim_06_puresky",
    "overcast": "polyhaven/overcast_soil_puresky",
    "night": "polyhaven/kloppenheim_02",
}
# Sky energy scales the panorama so the four presets land on a consistent
# exposure under the AgX tonemapper; overcast and night are dimmer than the
# sun-lit skies by nature and are not boosted back up.
SKY_ENERGY = {"day": 1.0, "dawn": 1.0, "overcast": 0.85, "night": 0.9}


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def sun_direction(path: Path) -> dict:
    image = bpy.data.images.load(str(path), check_existing=False)
    width, height = image.size
    pixels = image.pixels[:]  # RGBA float32, bottom row first
    luminance = [0.0] * (width * height)
    best = 0.0
    for index in range(width * height):
        r, g, b = pixels[index * 4], pixels[index * 4 + 1], pixels[index * 4 + 2]
        value = 0.2126 * r + 0.7152 * g + 0.0722 * b
        luminance[index] = value
        if value > best:
            best = value
    threshold = best * 0.6
    weight_sum = 0.0
    sx = sy = 0.0
    cos_sum = sin_sum = 0.0
    for index, value in enumerate(luminance):
        if value < threshold:
            continue
        x = index % width
        y = index // width
        weight = value - threshold
        weight_sum += weight
        angle = (x + 0.5) / width * 2 * math.pi
        cos_sum += math.cos(angle) * weight
        sin_sum += math.sin(angle) * weight
        sy += (y + 0.5) / height * weight
    u = (math.atan2(sin_sum, cos_sum) / (2 * math.pi)) % 1.0
    # Blender stores rows bottom-up, so the top of the panorama is y = height.
    v = 1.0 - sy / weight_sum
    azimuth_degrees = u * 360.0
    elevation_degrees = 90.0 - v * 180.0
    bpy.data.images.remove(image)
    return {
        "sun_u": round(u, 5),
        "sun_v": round(v, 5),
        "sun_azimuth_degrees": round(azimuth_degrees, 2),
        "sun_elevation_degrees": round(elevation_degrees, 2),
        "peak_luminance": round(best, 3),
        "width": width,
        "height": height,
    }


def main() -> None:
    args = arguments()
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    # Lock paths are repository-relative; Blender's working directory is not the repository.
    repo_root = args.lock.resolve().parents[3]
    assets = {asset["id"]: asset for asset in lock["assets"]}
    presets = {}
    for preset, asset_id in PRESETS.items():
        asset = assets[asset_id]
        record = asset["files"][0]
        path = repo_root / record["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record["sha256"]:
            raise RuntimeError(f"{path} does not match the lock ({digest} != {record['sha256']})")
        measured = sun_direction(path)
        elevation = measured["sun_elevation_degrees"]
        azimuth = measured["sun_azimuth_degrees"]
        # Keep the sun above the horizon for the light even when the HDRI's
        # brightest cluster sits at the horizon glow, and keep moonlight gentle.
        pitch = -max(elevation, 6.0)
        yaw = azimuth - 180.0
        if yaw <= -180.0:
            yaw += 360.0
        presets[preset] = {
            "asset": asset_id,
            "panorama": "res://" + record["path"],
            "sha256": record["sha256"],
            "attribution": asset["license"]["attribution"],
            "light_yaw_degrees": round(yaw, 2),
            "light_pitch_degrees": round(pitch, 2),
            "sky_energy": SKY_ENERGY[preset],
            **measured,
        }
    output = {
        "schema_version": 1,
        "generator": "tools/environments/analyze_skies.py",
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode("ascii"),
        "lock": str(args.lock).replace("\\", "/"),
        "presets": presets,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print("CANNONBALL_SKY_PRESETS_OK " + " ".join(
        f"{name}=az{values['sun_azimuth_degrees']}/el{values['sun_elevation_degrees']}"
        for name, values in presets.items()))


if __name__ == "__main__":
    main()
