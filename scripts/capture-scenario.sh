#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 OUTPUT.avi --fixture NAME --geographic-review [scenario arguments]" >&2
  exit 2
fi

output_path="$1"
shift
fixture="official-corridor"
scenario_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fixture)
      if [[ $# -lt 2 ]]; then
        echo "--fixture requires a value." >&2
        exit 2
      fi
      fixture="$2"
      shift 2
      ;;
    --fixture=*)
      fixture="${1#--fixture=}"
      shift
      ;;
    *)
      scenario_args+=("$1")
      shift
      ;;
  esac
done
capture_fps="${CANNONBALL_CAPTURE_FPS:-60}"
default_capture_frames=60
if [[ " ${scenario_args[*]} " == *" --topology-review "* ]]; then
  default_capture_frames=480
fi
if [[ " ${scenario_args[*]} " == *" --sign-review "* ]]; then
  default_capture_frames=360
fi
capture_frames="${CANNONBALL_CAPTURE_FRAMES:-$default_capture_frames}"
timeout_seconds="${CANNONBALL_SCENARIO_TIMEOUT_SECONDS:-120}"

case "$fixture" in
  official-corridor)
    fixture_source="$repo_root/data/sources/fixtures/nhpn-boulder-us36.geojson"
    fixture_manifest="$repo_root/data/sources/fixtures/nhpn-boulder-us36.manifest.json"
    fixture_elevation="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.tif"
    fixture_elevation_metadata="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json"
    fixture_lock="$repo_root/data/sources/source-lock.json"
    fixture_chunk_meters=100
    ;;
  representative-corridor|variable-lanes|representative-interchanges|route-context)
    fixture_source="$repo_root/data/sources/fixtures/nhpn-boulder-westminster-us36.geojson"
    fixture_manifest="$repo_root/data/sources/fixtures/nhpn-boulder-westminster-us36.manifest.json"
    fixture_elevation="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder-westminster.tif"
    fixture_elevation_metadata="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder-westminster.metadata.json"
    fixture_lock="$repo_root/data/sources/representative-corridor-lock.json"
    fixture_chunk_meters=2000
    ;;
  *)
    echo "Unknown fixture '$fixture'. Supported fixtures: official-corridor, representative-corridor, variable-lanes, representative-interchanges, route-context." >&2
    exit 2
    ;;
esac

package_directory="$repo_root/.tools/scenarios/$fixture"

uv run --project "$repo_root/tools/map_pipeline" --frozen cannonball-map build \
  --source "$fixture_source" \
  --manifest "$fixture_manifest" \
  --catalog "$repo_root/data/sources/catalog.json" \
  --elevation "$fixture_elevation" \
  --elevation-metadata "$fixture_elevation_metadata" \
  --acquisition-lock "$fixture_lock" \
  --chunk-meters "$fixture_chunk_meters" \
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
  -- "--route-package=$route_package" "${scenario_args[@]}" &
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
