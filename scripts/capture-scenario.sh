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

dotnet build "$repo_root/Cannonball.sln" --nologo

"$repo_root/scripts/godot.sh" \
  --rendering-method gl_compatibility \
  --path "$repo_root" \
  --write-movie "$output_path" \
  --fixed-fps "$capture_fps" \
  --quit-after "$capture_frames" \
  -- "$@" &
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
