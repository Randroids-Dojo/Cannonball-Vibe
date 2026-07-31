#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

work="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-integrated-visual-slice.XXXXXX")"
trap 'rm -rf "$work"' EXIT

./scripts/run-scenario.sh \
  --fixture representative-corridor \
  --profile integrated-visual-slice |
  tee "$work/integrated-visual-slice.log"

if marker="$(
  grep '^CANNONBALL_INTEGRATED_VISUAL_SLICE_OK ' \
    "$work/integrated-visual-slice.log"
)"; then
  :
else
  grep_status=$?
  if [[ $grep_status -ne 1 ]]; then
    echo "Could not read the integrated visual slice log." >&2
    exit "$grep_status"
  fi
  marker=""
fi
if [[ -z "$marker" || "$marker" == *$'\n'* ]]; then
  echo "Integrated visual slice emitted a missing or ambiguous completion marker." >&2
  exit 1
fi
for required in \
  'vehicle=hero-gt' \
  'road=production' \
  'environment=balanced'; do
  if [[ " $marker " != *" $required "* ]]; then
    echo "Integrated visual slice marker is missing '$required': $marker" >&2
    exit 1
  fi
done

printf 'CANNONBALL_INTEGRATED_VISUAL_SLICE_GATE_OK %s\n' "$marker"
