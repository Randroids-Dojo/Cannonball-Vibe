#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profiles="all"
speed_bands="all"
fixtures="all"
report_directory="${CANNONBALL_VEHICLE_DYNAMICS_REPORT_DIR:-$repo_root/reports/p0-019}"
scenario_timeout_seconds="${CANNONBALL_SCENARIO_TIMEOUT_SECONDS:-300}"
mkdir -p "$report_directory"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profiles)
      profiles="${2:?--profiles requires a value}"
      shift 2
      ;;
    --profiles=*)
      profiles="${1#--profiles=}"
      shift
      ;;
    --speed-bands)
      speed_bands="${2:?--speed-bands requires a value}"
      shift 2
      ;;
    --speed-bands=*)
      speed_bands="${1#--speed-bands=}"
      shift
      ;;
    --fixtures)
      fixtures="${2:?--fixtures requires a value}"
      shift 2
      ;;
    --fixtures=*)
      fixtures="${1#--fixtures=}"
      shift
      ;;
    *)
      echo "Unknown vehicle-dynamics verification argument '$1'." >&2
      exit 2
      ;;
  esac
done

case "$profiles" in
  all) selected_profile="all" ;;
  accessible) selected_profile="Accessible" ;;
  balanced) selected_profile="Balanced" ;;
  raw) selected_profile="Raw" ;;
  *)
    echo "Unknown profile selection '$profiles'." >&2
    exit 2
    ;;
esac

DOTNET_ROLL_FORWARD=Major dotnet test "$repo_root/Cannonball.sln" \
  --filter 'FullyQualifiedName~VehicleDynamics' --nologo |
  tee "$report_directory/core-tests.log"

matrix_log="$report_directory/matrix.log"
CANNONBALL_SCENARIO_TIMEOUT_SECONDS="$scenario_timeout_seconds" \
  CANNONBALL_GODOT_LOG_FILE="$matrix_log" "$repo_root/scripts/run-scenario.sh" \
  --fixture official-corridor \
  --profile vehicle-dynamics \
  "--assist=$selected_profile" \
  "--dynamics-speed-bands=$speed_bands" \
  "--dynamics-fixtures=$fixtures"

if [[ "$profiles" == "all" && "$speed_bands" == "all" && "$fixtures" == "all" ]]; then
  expected_hash=""
  for fixed_fps in 30 60 144; do
    frame_rate_log="$report_directory/fps-$fixed_fps.log"
    CANNONBALL_SCENARIO_TIMEOUT_SECONDS="$scenario_timeout_seconds" \
      CANNONBALL_GODOT_LOG_FILE="$frame_rate_log" \
      "$repo_root/scripts/run-scenario.sh" \
      --fixture official-corridor \
      --profile vehicle-dynamics \
      --assist=Accessible \
      --dynamics-speed-bands=push \
      --dynamics-fixtures=lane-change \
      "--engine-fixed-fps=$fixed_fps"
    marker="$(grep 'CANNONBALL_VEHICLE_DYNAMICS_SUITE_OK' "$frame_rate_log" | tail -n 1)"
    result_hash="$(sed -n 's/.*result_hash=\([0-9a-f]\{64\}\).*/\1/p' <<< "$marker")"
    if [[ -z "$result_hash" ]]; then
      echo "Fixed-FPS run $fixed_fps did not emit a dynamics result hash." >&2
      exit 1
    fi
    if [[ -z "$expected_hash" ]]; then
      expected_hash="$result_hash"
    elif [[ "$result_hash" != "$expected_hash" ]]; then
      echo "Fixed-FPS result hash diverged at $fixed_fps FPS." >&2
      exit 1
    fi
  done
  printf 'CANNONBALL_VEHICLE_DYNAMICS_FRAME_RATE_OK fps=30,60,144 result_hash=%s\n' \
    "$expected_hash"
fi
