#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

vehicle=""
all_lods="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vehicle)
      vehicle="${2:-}"
      shift 2
      ;;
    --vehicle=*)
      vehicle="${1#--vehicle=}"
      shift
      ;;
    --all-lods)
      all_lods="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done
if [[ "$vehicle" != "hero-gt" || "$all_lods" != "true" ]]; then
  echo "Usage: $0 --vehicle hero-gt --all-lods" >&2
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

source_asset="data/assets/vehicles/sources/hero-gt.blend"
tracked_glb="assets/vehicles/hero-gt/hero-gt.glb"
tracked_contact="data/assets/vehicles/hero-gt-contact-sheet.png"
tracked_blender_inventory="data/assets/vehicles/hero-gt.blender.json"
tracked_godot_inventory="data/assets/vehicles/hero-gt.godot.json"
wrapper="game/Vehicle/Visuals/HeroGt.tscn"
import_settings="assets/vehicles/hero-gt/hero-gt.glb.import"
manifest="data/assets/vehicles/hero-gt.asset.json"
profile="tools/assets/profiles/gltf2-binary-v1.json"
godot_profile="tools/assets/profiles/godot-4.7.1-v1.json"
for binary in "$source_asset" "$tracked_glb" "$tracked_contact"; do
  if [[ "$(git check-attr filter -- "$binary")" != *": lfs" ]]; then
    echo "$binary must be tracked by Git LFS." >&2
    exit 1
  fi
done

work="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-hero-gt.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/first" "$work/second" reports/assets

export_once() {
  local destination="$1"
  "$blender_bin" --background "$source_asset" --python-exit-code 1 \
    --python tools/vehicles/validate_and_export_hero_gt.py -- \
    --source "$source_asset" \
    --output "$destination/hero-gt.glb" \
    --inventory "$destination/blender.json" \
    --contact-sheet "$destination/hero-gt-contact-sheet.png" \
    --profile "$profile"
}

export_once "$work/first"
export_once "$work/second"
cmp "$work/first/hero-gt.glb" "$work/second/hero-gt.glb"
cmp "$work/first/hero-gt-contact-sheet.png" "$work/second/hero-gt-contact-sheet.png"
cmp "$work/first/hero-gt.glb" "$tracked_glb"
cmp "$work/first/hero-gt-contact-sheet.png" "$tracked_contact"
node -e '
  const fs = require("node:fs");
  const fresh = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  const tracked = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  for (const key of ["required_nodes", "triangles", "triangle_total", "lod0_triangle_total", "collision_triangle_total", "materials", "textures", "texture_bytes_total", "budgets", "bounds_meters", "vehicle_metrics"]) {
    if (JSON.stringify(fresh[key]) !== JSON.stringify(tracked[key])) throw new Error(`Blender inventory drift: ${key}`);
  }
  if (fresh.glb.sha256 !== tracked.glb.sha256 || fresh.contact_sheet.sha256 !== tracked.contact_sheet.sha256) {
    throw new Error("Tracked Hero GT renderer outputs drifted");
  }
' "$work/first/blender.json" "$tracked_blender_inventory"

for mutation in unapplied-scale missing-semantic-node external-texture; do
  invalid="$work/invalid-$mutation.blend"
  "$blender_bin" --background --factory-startup --python-exit-code 1 \
    --python tools/vehicles/mutate_hero_gt.py -- \
    --source "$source_asset" --output "$invalid" --mutation "$mutation" \
    >"reports/assets/hero-gt-rejected-$mutation.log" 2>&1
  if "$blender_bin" --background "$invalid" --python-exit-code 1 \
      --python tools/vehicles/validate_and_export_hero_gt.py -- \
      --source "$invalid" \
      --output "$work/invalid-$mutation.glb" \
      --inventory "$work/invalid-$mutation.json" \
      --contact-sheet "$work/invalid-$mutation.png" \
      --profile "$profile" >>"reports/assets/hero-gt-rejected-$mutation.log" 2>&1; then
    echo "Hero GT mutation unexpectedly passed: $mutation" >&2
    exit 1
  fi
done

project_stage="$work/project"
mkdir -p "$project_stage"
rsync -a --exclude .git --exclude .godot --exclude .tools --exclude reports \
  --exclude '**/bin' --exclude '**/obj' ./ "$project_stage/"
./scripts/godot.sh --headless --path "$project_stage" --import
dotnet build "$project_stage/Cannonball.csproj" --nologo
./scripts/godot.sh --headless --path "$project_stage" --import
./scripts/godot.sh --headless --path "$project_stage" \
  --script res://tools/vehicles/validate_import.gd -- \
  --wrapper "res://$wrapper" \
  --glb "res://$tracked_glb" \
  --import-settings "res://$import_settings" \
  --output "$work/godot.json" \
  --profile "res://$godot_profile"
node -e '
  const fs = require("node:fs");
  const fresh = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  const tracked = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  for (const key of ["required_nodes", "all_required_nodes_resolved", "script_reference_present", "automation_id", "glb_sha256", "import_settings_sha256", "wheelbase_meters", "track_meters", "lod_count", "damage_zone_count"]) {
    if (JSON.stringify(fresh[key]) !== JSON.stringify(tracked[key])) throw new Error(`Godot inventory drift: ${key}`);
  }
' "$work/godot.json" "$tracked_godot_inventory"

node tools/vehicles/generate_manifest.mjs --output "$work/hero-gt.asset.json"
cmp "$work/hero-gt.asset.json" "$manifest"
node tools/assets/validate_manifest.mjs \
  --schema data/assets/manifest.schema.json \
  --manifest "$manifest" \
  --blender-inventory "$work/first/blender.json" \
  --godot-inventory "$work/godot.json" \
  --output reports/assets/p1-008-validation.json \
  --task-id P1-008 \
  --milestone M5 \
  --validation-preset "Hero GT validation" \
  --command "./scripts/verify-vehicle-asset.sh --vehicle hero-gt --all-lods" \
  --human-gate-name "Hero vehicle art direction and final rights approval" \
  --human-question Q-020

./scripts/godot.sh --headless --path "$project_stage" \
  --export-pack "Linux x86_64" "$work/hero-gt.pck"
node tools/assets/validate_release_pack.mjs "$work/hero-gt.pck" --asset=hero-gt
node scripts/release/pck-inspect.mjs "$work/hero-gt.pck"

cp "$work/first/blender.json" reports/assets/hero-gt.blender.json
cp "$work/godot.json" reports/assets/hero-gt.godot.json
echo "CANNONBALL_HERO_GT_ASSET_OK vehicle=hero-gt blender=$blender_version godot=4.7.1 deterministic_rebuilds=2 lods=3 semantic_nodes=37"
