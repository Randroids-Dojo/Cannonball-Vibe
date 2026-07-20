#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

automation_mode="auto"
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 2 || "$1" != "--automation" ]]; then
    echo "Usage: $0 [--automation auto|off]" >&2
    exit 2
  fi
  automation_mode="$2"
fi
if [[ "$automation_mode" != "auto" && "$automation_mode" != "off" ]]; then
  echo "--automation must be auto or off." >&2
  exit 2
fi

DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln \
  --filter 'FullyQualifiedName~TripMap'

CANNONBALL_SCENARIO_TIMEOUT_SECONDS=180 \
  ./scripts/run-scenario.sh --trip-map-review

CANNONBALL_SCENARIO_TIMEOUT_SECONDS=180 \
  ./scripts/run-scenario.sh --profile trip-map-scale

if [[ "$automation_mode" == "auto" ]]; then
  ./scripts/verify-playgodot.sh
fi
