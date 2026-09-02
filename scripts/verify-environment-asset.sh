#!/usr/bin/env bash
# Deterministic gate for one Blender-built environment asset (P1-010).
#
#   ./scripts/verify-environment-asset.sh --asset conifer
#
# Exports the locked Blender source twice with the pinned Blender and compares
# the GLB bytes and Blender inventory, checks the tracked GLB, contact sheet and
# inventory have not drifted, rejects three intentionally invalid source
# mutations, imports the GLB with official Godot in an isolated project copy,
# proves the tracked importer-normalised scene is reproduced byte for byte,
# validates the generated scene's semantic nodes and LODs, regenerates the
# manifest and compares it to the tracked one, then runs the manifest validator.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

asset=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --asset) asset="${2:-}"; shift 2 ;;
    --asset=*) asset="${1#--asset=}"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ "$asset" != "conifer" ]]; then
  echo "Usage: $0 --asset conifer" >&2
  exit 2
fi

blender_bin="${BLENDER_BIN:-$(command -v blender || true)}"
if [[ -z "$blender_bin" || ! -x "$blender_bin" ]]; then
  echo "Set BLENDER_BIN to the pinned Blender executable." >&2
  exit 1
fi
expected_blender="$(node -p 'require("./tools/assets/toolchain.json").blender.version')"
expected_blender_hash="$(node -p 'require("./tools/assets/toolchain.json").blender.build_hash')"
blender_version="$($blender_bin --version | awk 'NR==1 {print $2}')"
blender_hash="$($blender_bin --version | awk '/build hash:/ {print $3}')"
if [[ "$blender_version" != "$expected_blender" || "$blender_hash" != "$expected_blender_hash" ]]; then
  echo "Blender mismatch: expected $expected_blender+$expected_blender_hash, got $blender_version+$blender_hash" >&2
  exit 1
fi

asset_dir="data/assets/environments/trees"
runtime_dir="assets/environments/trees/$asset"
source_asset="$asset_dir/sources/$asset.blend"
tracked_glb="$asset_dir/derived/$asset.glb"
tracked_generated_scene="$runtime_dir/$asset.generated.tscn"
tracked_contact="$asset_dir/$asset-contact-sheet.png"
tracked_blender_inventory="$asset_dir/$asset.blender.json"
tracked_godot_inventory="$asset_dir/$asset.godot.json"
contract="$asset_dir/$asset.contract.json"
import_settings="$asset_dir/$asset.glb.import"
manifest="$asset_dir/$asset.asset.json"
profile="tools/assets/profiles/gltf2-binary-v2.json"
godot_profile="tools/assets/profiles/godot-4.7.1-v1.json"
automation_id="environment.asset.$asset"
for binary in "$source_asset" "$tracked_glb" "$tracked_contact"; do
  if [[ "$(git check-attr filter -- "$binary")" != *": lfs" ]]; then
    echo "$binary must be tracked by Git LFS." >&2
    exit 1
  fi
done

work="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-$asset.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/first" "$work/second" reports/assets

# rsync is absent from Git for Windows; tar preserves the same exclusions.
stage_project() {
  local destination="$1"
  mkdir -p "$destination"
  tar --exclude=.git --exclude=.godot --exclude=.tools --exclude=reports \
    --exclude='*/bin' --exclude='*/obj' --exclude='bin' --exclude='obj' \
    -cf - . | tar -xf - -C "$destination"
}

export_once() {
  local destination="$1"
  "$blender_bin" --background "$source_asset" --python-exit-code 1 \
    --python tools/environments/validate_and_export_environment_asset.py -- \
    --source "$source_asset" \
    --contract "$contract" \
    --output "$destination/$asset.glb" \
    --inventory "$destination/blender.json" \
    --contact-sheet "$destination/$asset-contact-sheet.png" \
    --profile "$profile"
}

export_once "$work/first"
export_once "$work/second"
cmp "$work/first/$asset.glb" "$work/second/$asset.glb"
cmp "$work/first/$asset-contact-sheet.png" "$work/second/$asset-contact-sheet.png"
cmp "$work/first/$asset.glb" "$tracked_glb"
node -e '
  const fs = require("node:fs");
  const fresh = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  const tracked = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  for (const key of ["required_nodes", "triangles", "triangle_total", "lod_triangles", "lod0_triangle_total", "collision_triangle_total", "materials", "textures", "texture_bytes_total", "budgets", "bounds_meters"]) {
    if (JSON.stringify(fresh[key]) !== JSON.stringify(tracked[key])) throw new Error(`Blender inventory drift: ${key}`);
  }
  if (fresh.glb.sha256 !== tracked.glb.sha256) throw new Error("Tracked GLB drifted from a fresh export");
' "$work/first/blender.json" "$tracked_blender_inventory"

for mutation in unapplied-scale missing-semantic-node external-texture; do
  invalid="$work/invalid-$mutation.blend"
  "$blender_bin" --background --factory-startup --python-exit-code 1 \
    --python tools/environments/mutate_environment_asset.py -- \
    --source "$source_asset" --output "$invalid" --mutation "$mutation" \
    >"reports/assets/$asset-rejected-$mutation.log" 2>&1
  if "$blender_bin" --background "$invalid" --python-exit-code 1 \
      --python tools/environments/validate_and_export_environment_asset.py -- \
      --source "$invalid" \
      --contract "$contract" \
      --output "$work/invalid-$mutation.glb" \
      --inventory "$work/invalid-$mutation.json" \
      --contact-sheet "$work/invalid-$mutation.png" \
      --profile "$profile" >>"reports/assets/$asset-rejected-$mutation.log" 2>&1; then
    echo "$asset mutation unexpectedly passed: $mutation" >&2
    exit 1
  fi
done

import_stage="$work/import-project"
stage_project "$import_stage"
mkdir -p "$import_stage/$runtime_dir"
cp "$tracked_glb" "$import_stage/$runtime_dir/$asset.glb"
cp "$import_settings" "$import_stage/$runtime_dir/$asset.glb.import"
./scripts/godot.sh --headless --path "$import_stage" --import >/dev/null 2>&1 || \
  ./scripts/godot.sh --headless --path "$import_stage" --import
./scripts/godot.sh --headless --path "$import_stage" \
  --script res://tools/vehicles/pack_imported_scene.gd -- \
  "res://$runtime_dir/$asset.glb" \
  "res://$runtime_dir/$asset.rebuilt.tscn"
cmp "$import_stage/$runtime_dir/$asset.rebuilt.tscn" "$tracked_generated_scene"

./scripts/godot.sh --headless --path "$repo_root" \
  --script res://tools/environments/validate_generated_scene.gd -- \
  --scene "res://$tracked_generated_scene" \
  --contract "res://$contract" \
  --import-settings "res://$import_settings" \
  --glb "res://$tracked_glb" \
  --automation-id "$automation_id" \
  --output "$work/godot.json" \
  --profile "res://$godot_profile"
node -e '
  const fs = require("node:fs");
  const fresh = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  const tracked = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  for (const key of ["required_nodes", "all_required_nodes_resolved", "automation_id", "glb_sha256", "generated_scene_sha256", "import_settings_sha256", "lod_triangles", "lod_count", "triangle_count", "color_attribute_surfaces"]) {
    if (JSON.stringify(fresh[key]) !== JSON.stringify(tracked[key])) throw new Error(`Godot inventory drift: ${key}`);
  }
' "$work/godot.json" "$tracked_godot_inventory"

node tools/environments/generate_conifer_manifest.mjs --output "$work/$asset.asset.json"
cmp "$work/$asset.asset.json" "$manifest"
node tools/assets/validate_manifest.mjs \
  --schema data/assets/manifest.schema.json \
  --manifest "$manifest" \
  --blender-inventory "$work/first/blender.json" \
  --godot-inventory "$work/godot.json" \
  --output "reports/assets/p1-010-$asset-validation.json" \
  --task-id P1-010 \
  --milestone M5 \
  --validation-preset "Environment asset validation" \
  --command "./scripts/verify-environment-asset.sh --asset $asset" \
  --human-gate-name "Representative-region art direction, readability, and final rights approval" \
  --human-question Q-021

cp "$work/first/blender.json" "reports/assets/$asset.blender.json"
cp "$work/godot.json" "reports/assets/$asset.godot.json"
echo "CANNONBALL_ENVIRONMENT_ASSET_OK asset=$asset blender=$blender_version godot=4.7.1 deterministic_rebuilds=2 lods=3"
