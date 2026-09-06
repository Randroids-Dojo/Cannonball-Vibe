#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -gt 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-off-road-ground.XXXXXX")"
cleanup() {
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

profile_log="$temporary_directory/off-road-ground.log"

# The headless scenario drops the car onto the terrain margin either side of
# the paved edge on the official corridor and checks the ground contract
# (terrain colliders on every collision chunk and seam, every ground mesh
# facing up) before the drops.
CANNONBALL_GODOT_LOG_FILE="$profile_log" \
  "$repo_root/scripts/run-scenario.sh" --profile off-road-ground

for marker in CANNONBALL_GROUND_CONTRACT_OK CANNONBALL_OFF_ROAD_GROUND_OK; do
  if ! grep -q "$marker" "$profile_log"; then
    echo "$marker is missing from the off-road ground scenario log." >&2
    exit 1
  fi
done
grep -E "CANNONBALL_(GROUND_CONTRACT|OFF_ROAD_GROUND_STAGE|OFF_ROAD_GROUND)_OK" "$profile_log"
