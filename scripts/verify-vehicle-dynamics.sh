#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profiles="all"
speed_bands="all"
fixtures="all"

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

if [[ "$speed_bands" != "all" && "$speed_bands" != "redline" ]]; then
  echo "The current incline regression supports --speed-bands all or redline." >&2
  exit 2
fi
if [[ "$fixtures" != "all" && "$fixtures" != "incline" ]]; then
  echo "The current vehicle-dynamics gate supports --fixtures all or incline." >&2
  exit 2
fi

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
  --filter 'FullyQualifiedName~VehicleDynamics' --nologo

"$repo_root/scripts/run-scenario.sh" \
  --fixture official-corridor \
  --profile vehicle-dynamics \
  "--assist=$selected_profile"
