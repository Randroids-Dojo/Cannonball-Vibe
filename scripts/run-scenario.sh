#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 --smoke-test [--stress-driver]" >&2
  exit 2
fi

timeout_seconds="${CANNONBALL_SCENARIO_TIMEOUT_SECONDS:-120}"

"$repo_root/scripts/godot.sh" \
  --headless \
  --rendering-method gl_compatibility \
  --path "$repo_root" \
  -- "$@" &
scenario_pid=$!

cleanup() {
  kill "$watchdog_pid" 2>/dev/null || true
}
trap cleanup EXIT

(
  sleep "$timeout_seconds"
  echo "Godot scenario exceeded ${timeout_seconds}s; terminating process $scenario_pid." >&2
  kill -TERM "$scenario_pid" 2>/dev/null || true
) &
watchdog_pid=$!

wait "$scenario_pid"
