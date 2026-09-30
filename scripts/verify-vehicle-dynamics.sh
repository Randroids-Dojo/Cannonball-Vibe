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

validate_identity() {
  node - "$1" <<'NODE'
const fs = require('node:fs');
// BEGIN scoped dynamics identity reader
function checkDynamicsIdentity(text) {
  const rows = text.split(/\r?\n/).filter(line => line.startsWith('CANNONBALL_VEHICLE_DYNAMICS_IDENTITY '));
  if (rows.length !== 1) return ['native Hero dynamics identity missing or duplicated'];
  let r;
  try { r = JSON.parse(rows[0].slice('CANNONBALL_VEHICLE_DYNAMICS_IDENTITY '.length)); }
  catch { return ['native Hero dynamics identity is not JSON']; }
  // The fixed legacy Hero fixture: VehicleDynamicsProfile and HeroGt.tres defaults.
  if (r.asset_id !== 'hero-gt' || r.force_graybox !== false || r.uses_graybox !== false ||
      r.mass_kg !== 1450 || r.center_of_mass_mode !== 'Custom' ||
      !Array.isArray(r.configured_com) || r.configured_com.length !== 3 ||
      r.configured_com[0] !== 0 || r.configured_com[1] !== Math.fround(-0.40) || r.configured_com[2] !== 0 ||
      r.setup_id !== 'high-speed-validation' || r.forward_top_speed_mph !== 250 || r.physics_hz !== 120)
    return ['native Hero dynamics identity/setup differs from the fixed baseline'];
  return [];
}
// END scoped dynamics identity reader

const failures = checkDynamicsIdentity(fs.readFileSync(process.argv[2], 'utf8'));
if (failures.length) { console.error(failures.join('\n')); process.exit(1); }
NODE
}

matrix_log="$report_directory/matrix.log"
CANNONBALL_SCENARIO_TIMEOUT_SECONDS="$scenario_timeout_seconds" \
  CANNONBALL_GODOT_LOG_FILE="$matrix_log" "$repo_root/scripts/run-scenario.sh" \
  --fixture official-corridor \
  --profile vehicle-dynamics \
  --vehicle=hero-gt \
  "--assist=$selected_profile" \
  "--dynamics-speed-bands=$speed_bands" \
  "--dynamics-fixtures=$fixtures"
validate_identity "$matrix_log"

if [[ "$profiles" == "all" && "$speed_bands" == "all" && "$fixtures" == "all" ]]; then
  expected_hash=""
  for fixed_fps in 30 60 144; do
    frame_rate_log="$report_directory/fps-$fixed_fps.log"
    CANNONBALL_SCENARIO_TIMEOUT_SECONDS="$scenario_timeout_seconds" \
      CANNONBALL_GODOT_LOG_FILE="$frame_rate_log" \
      "$repo_root/scripts/run-scenario.sh" \
      --fixture official-corridor \
      --profile vehicle-dynamics \
      --vehicle=hero-gt \
      --assist=Accessible \
      --dynamics-speed-bands=push \
      --dynamics-fixtures=lane-change \
      "--engine-fixed-fps=$fixed_fps"
    validate_identity "$frame_rate_log"
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
