#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if git grep -ni 'playgodot' -- project.godot >/dev/null; then
  echo "PlayGodot must not be a project autoload or normal startup dependency." >&2
  exit 1
fi

scene_references="$(git grep -l 'addons/playgodot/server.gd' -- '*.tscn' || true)"
if [[ "$scene_references" != "addons/playgodot/bootstrap.tscn" ]]; then
  echo "The PlayGodot server must only be referenced by its explicit test bootstrap." >&2
  printf 'Found: %s\n' "${scene_references:-none}" >&2
  exit 1
fi

grep -Eq 'OS\.is_debug_build\(\)' addons/playgodot/server.gd
grep -Eq -- '--playgodot' addons/playgodot/server.gd
grep -Eq 'PLAYGODOT_TOKEN' addons/playgodot/server.gd
grep -Eq 'listen\(0, "127\.0\.0\.1"\)' addons/playgodot/server.gd

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-playgodot-boundary.XXXXXX")"
runtime_log="$temp_dir/runtime.log"
transcript="$temp_dir/transcript.jsonl"
trap 'rm -rf "$temp_dir"' EXIT
playgodot_token="$(uv run --project "$repo_root/automation/playgodot" --frozen \
  python -c 'import secrets; print(secrets.token_hex(32))')"

package_directory="$repo_root/.tools/scenarios/official-corridor"
if ! uv run --project "$repo_root/tools/map_pipeline" --frozen cannonball-map build \
  --source "$repo_root/data/sources/fixtures/nhpn-boulder-us36.geojson" \
  --manifest "$repo_root/data/sources/fixtures/nhpn-boulder-us36.manifest.json" \
  --catalog "$repo_root/data/sources/catalog.json" \
  --elevation "$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.tif" \
  --elevation-metadata "$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json" \
  --acquisition-lock "$repo_root/data/sources/source-lock.json" \
  --chunk-meters 100 \
  --output "$package_directory" >"$runtime_log" 2>&1; then
  echo "PlayGodot boundary fixture build failed." >&2
  sed -n '1,160p' "$runtime_log" >&2
  exit 1
fi

route_package="$package_directory/$(jq -r .root_relative_path "$package_directory/current-package.json")"
if [[ ! -f "$route_package" ]]; then
  echo "PlayGodot boundary fixture did not publish its route package." >&2
  exit 1
fi
if ! dotnet build "$repo_root/Cannonball.sln" --nologo >>"$runtime_log" 2>&1; then
  echo "PlayGodot boundary build failed." >&2
  sed -n '1,160p' "$runtime_log" >&2
  exit 1
fi
set +e
PLAYGODOT_TOKEN="$playgodot_token" \
  PLAYGODOT_TRANSCRIPT="$transcript" \
  "$GODOT_BIN" --headless --rendering-method gl_compatibility \
  --path "$repo_root" --quit-after 30 -- \
  "--route-package=$route_package" --playgodot >>"$runtime_log" 2>&1
runtime_exit=$?
set -e

if grep -Eq 'PLAYGODOT_READY|PLAYGODOT_START_FAILED' "$runtime_log" || [[ -e "$transcript" ]]; then
  echo "Normal project startup exposed a PlayGodot rendezvous or transcript surface." >&2
  sed -n '1,160p' "$runtime_log" >&2
  exit 1
fi

# The macOS hosted VM can correctly trip the production 40 ms chunk-build budget
# during first-frame JIT. Accept only that typed Main/WorldStreamer path as the
# sole ERROR record; any additional error or fatal signature remains a failure.
known_budget_exit=false
if (( runtime_exit == 1 )); then
  failure_signature_count="$(grep -Eic \
    '^(ERROR:|SCRIPT ERROR:|FATAL:|PANIC:)|unhandled exception|uncaught exception|segmentation fault|core dumped|libc\+\+abi|BUG:|assertion failed|(^|[[:space:]])abort(ed)?([:[:space:]]|$)' \
    "$runtime_log" || true)"
  if [[ "$failure_signature_count" == "1" ]] && \
    grep -Eq "^ERROR: System\.InvalidOperationException: Route chunk '[^']+' took [0-9]+\.[0-9]{3} ms to build; budget is 40\.000 ms\.$" "$runtime_log" && \
    grep -Fq 'at Cannonball.Game.World.WorldStreamer.AttachChunk' "$runtime_log" && \
    grep -Fq 'at Cannonball.Game.Main._Ready()' "$runtime_log"; then
    known_budget_exit=true
  fi
fi
if (( runtime_exit != 0 )) && [[ "$known_budget_exit" != "true" ]]; then
  echo "Normal project startup failed during the PlayGodot boundary check." >&2
  sed -n '1,160p' "$runtime_log" >&2
  exit 1
fi

echo "PlayGodot normal-start boundary passed: no autoload, listener, rendezvous, or transcript (runtime_exit=$runtime_exit)."
