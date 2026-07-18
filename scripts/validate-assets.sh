#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

blender_bin="${BLENDER_BIN:-$(command -v blender || true)}"
if [[ -z "$blender_bin" || ! -x "$blender_bin" ]]; then
  echo "Set BLENDER_BIN to the pinned Blender executable." >&2
  exit 1
fi
expected_blender="$(node -p 'require("./tools/assets/toolchain.json").blender.version')"
expected_blender_hash="$(node -p 'require("./tools/assets/toolchain.json").blender.build_hash')"
contact_reference_platform="$(node -p 'require("./tools/assets/toolchain.json").blender.contact_sheet_reference_platform')"
blender_version="$($blender_bin --version | awk 'NR==1 {print $2}')"
blender_hash="$($blender_bin --version | awk '/build hash:/ {print $3}')"
if [[ "$blender_version" != "$expected_blender" || "$blender_hash" != "$expected_blender_hash" ]]; then
  echo "Blender mismatch: expected $expected_blender+$expected_blender_hash, got $blender_version+$blender_hash" >&2
  exit 1
fi

source_asset="data/assets/pipeline-fixtures/sources/graybox-road-module.blend"
tracked_glb="assets/pipeline-fixtures/graybox-road-module/graybox-road-module.glb"
tracked_contact="data/assets/pipeline-fixtures/graybox-road-module-contact-sheet.png"
wrapper="assets/pipeline-fixtures/graybox-road-module/graybox-road-module.tscn"
manifest="data/assets/pipeline-fixtures/graybox-road-module.asset.json"
profile="tools/assets/profiles/gltf2-binary-v1.json"
godot_profile="tools/assets/profiles/godot-4.7.1-v1.json"
for binary in "$source_asset" "$tracked_glb" "$tracked_contact"; do
  if [[ "$(git check-attr filter -- "$binary")" != *": lfs" ]]; then
    echo "$binary must be tracked by Git LFS." >&2
    exit 1
  fi
done

work="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-assets.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/first" "$work/second" reports/assets

export_once() {
  local destination="$1"
  "$blender_bin" --background "$source_asset" --python-exit-code 1 \
    --python tools/assets/validate_and_export.py -- \
    --source "$source_asset" \
    --output "$destination/graybox-road-module.glb" \
    --inventory "$destination/blender.json" \
    --contact-sheet "$destination/graybox-road-module-contact-sheet.png" \
    --profile "$profile"
}

export_once "$work/first"
export_once "$work/second"
cmp "$work/first/graybox-road-module.glb" "$work/second/graybox-road-module.glb"
cmp "$work/first/graybox-road-module-contact-sheet.png" \
  "$work/second/graybox-road-module-contact-sheet.png"
cmp "$work/first/graybox-road-module.glb" "$tracked_glb"
current_platform="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
if [[ "$current_platform" == "$contact_reference_platform" ]]; then
  cmp "$work/first/graybox-road-module-contact-sheet.png" "$tracked_contact"
fi

for mutation in unapplied-scale missing-semantic-node external-texture; do
  invalid="$work/invalid-$mutation.blend"
  "$blender_bin" --background --factory-startup --python-exit-code 1 \
    --python tools/assets/mutate_fixture.py -- \
    --source "$source_asset" --output "$invalid" --mutation "$mutation" \
    >"reports/assets/rejected-$mutation.log" 2>&1
  if "$blender_bin" --background "$invalid" --python-exit-code 1 \
      --python tools/assets/validate_and_export.py -- \
      --source "$invalid" \
      --output "$work/invalid-$mutation.glb" \
      --inventory "$work/invalid-$mutation.json" \
      --contact-sheet "$work/invalid-$mutation.png" \
      --profile "$profile" >>"reports/assets/rejected-$mutation.log" 2>&1; then
    echo "Asset mutation unexpectedly passed: $mutation" >&2
    exit 1
  fi
done

project_stage="$work/project"
mkdir -p "$project_stage"
rsync -a --exclude .git --exclude .godot --exclude .tools --exclude reports \
  --exclude '**/bin' --exclude '**/obj' ./ "$project_stage/"
./scripts/godot.sh --headless --path "$project_stage" --import
./scripts/godot.sh --headless --path "$project_stage" \
  --script res://tools/assets/validate_import.gd -- \
  --wrapper "res://$wrapper" \
  --output "$work/godot.json" \
  --profile "res://$godot_profile"

invalid_manifest="$work/invalid-manifest.json"
node -e '
  const fs = require("node:fs");
  const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  value.unexpected_field = true;
  fs.writeFileSync(process.argv[2], `${JSON.stringify(value)}\n`);
' "$manifest" "$invalid_manifest"
if node tools/assets/validate_manifest.mjs \
    --schema data/assets/manifest.schema.json \
    --manifest "$invalid_manifest" \
    --blender-inventory "$work/first/blender.json" \
    --godot-inventory "$work/godot.json" \
    --output "$work/invalid-report.json" \
    >"reports/assets/rejected-invalid-manifest.log" 2>&1; then
  echo "Schema-invalid manifest unexpectedly passed." >&2
  exit 1
fi

over_budget_inventory="$work/over-budget-inventory.json"
node -e '
  const fs = require("node:fs");
  const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  value.texture_bytes_total = 1;
  fs.writeFileSync(process.argv[2], `${JSON.stringify(value)}\n`);
' "$work/first/blender.json" "$over_budget_inventory"
if node tools/assets/validate_manifest.mjs \
    --schema data/assets/manifest.schema.json \
    --manifest "$manifest" \
    --blender-inventory "$over_budget_inventory" \
    --godot-inventory "$work/godot.json" \
    --output "$work/over-budget-report.json" \
    >"reports/assets/rejected-texture-byte-budget.log" 2>&1; then
  echo "Texture-byte budget violation unexpectedly passed." >&2
  exit 1
fi

dotnet build "$project_stage/Cannonball.csproj" --nologo
./scripts/godot.sh --headless --path "$project_stage" \
  --export-pack "Asset pipeline validation" "$work/cannonball-assets.pck"
node tools/assets/validate_release_pack.mjs "$work/cannonball-assets.pck"
node scripts/release/pck-inspect.mjs "$work/cannonball-assets.pck" --allow-pipeline-fixtures

node tools/assets/validate_manifest.mjs \
  --schema data/assets/manifest.schema.json \
  --manifest "$manifest" \
  --blender-inventory "$work/first/blender.json" \
  --godot-inventory "$work/godot.json" \
  --output reports/assets/p1-002-validation.json

cp "$work/first/blender.json" reports/assets/graybox-road-module.blender.json
cp "$work/godot.json" reports/assets/graybox-road-module.godot.json
echo "CANNONBALL_ASSET_PIPELINE_OK asset=graybox-road-module blender=$blender_version godot=4.7.1 deterministic_rebuilds=2"
