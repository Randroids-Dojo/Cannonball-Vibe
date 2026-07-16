#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 OUTPUT.avi --smoke-test [scenario arguments]" >&2
  exit 2
fi

output_path="$1"
shift
capture_fps="${CANNONBALL_CAPTURE_FPS:-60}"
capture_frames="${CANNONBALL_CAPTURE_FRAMES:-60}"
timeout_seconds="${CANNONBALL_SCENARIO_TIMEOUT_SECONDS:-120}"
package_directory="$repo_root/.tools/scenarios/official-corridor"

uv run --project "$repo_root/tools/map_pipeline" --frozen cannonball-map build \
  --source "$repo_root/data/sources/fixtures/nhpn-boulder-us36.geojson" \
  --manifest "$repo_root/data/sources/fixtures/nhpn-boulder-us36.manifest.json" \
  --catalog "$repo_root/data/sources/catalog.json" \
  --elevation "$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.tif" \
  --elevation-metadata "$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json" \
  --acquisition-lock "$repo_root/data/sources/source-lock.json" \
  --chunk-meters 100 \
  --output "$package_directory"
route_package="$(uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
  "$package_directory/current-package.json" "$package_directory" <<'PY'
import json
import os
import sys

pointer = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(os.path.join(sys.argv[2], pointer["root_relative_path"]))
PY
)"

dotnet build "$repo_root/Cannonball.sln" --nologo

"$repo_root/scripts/godot.sh" \
  --rendering-method gl_compatibility \
  --path "$repo_root" \
  --write-movie "$output_path" \
  --fixed-fps "$capture_fps" \
  --quit-after "$capture_frames" \
  -- "--route-package=$route_package" "$@" &
scenario_pid=$!

cleanup() {
  kill "$watchdog_pid" 2>/dev/null || true
}
trap cleanup EXIT

(
  sleep "$timeout_seconds"
  echo "Godot capture exceeded ${timeout_seconds}s; terminating process $scenario_pid." >&2
  kill -TERM "$scenario_pid" 2>/dev/null || true
) &
watchdog_pid=$!

wait "$scenario_pid"
