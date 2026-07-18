#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cases=10000

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cases)
      if [[ $# -lt 2 ]]; then
        echo "--cases requires a value." >&2
        exit 2
      fi
      cases="$2"
      shift 2
      ;;
    --cases=*)
      cases="${1#--cases=}"
      shift
      ;;
    *)
      echo "Unknown argument '$1'." >&2
      exit 2
      ;;
  esac
done

if [[ ! "$cases" =~ ^[0-9]+$ ]] || (( cases < 1 || cases > 100000 )); then
  echo "--cases must be an integer from 1 through 100000." >&2
  exit 2
fi

cd "$repo_root"
CANNONBALL_RESUME_FUZZ_CASES="$cases" DOTNET_ROLL_FORWARD=Major \
  dotnet test Cannonball.sln --nologo \
  --filter 'FullyQualifiedName~SeededSavePointsRoundTripEquivalent'
printf 'CANNONBALL_RESUME_FUZZ_OK cases=%s seed=20260718\n' "$cases"
