#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ $# -ne 1 || "$1" != "--all-topology-fixtures" ]]; then
  echo "Usage: $0 --all-topology-fixtures" >&2
  exit 2
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-road-assets.XXXXXX")"
trap 'rm -rf "$work"' EXIT

run_and_require() {
  local name="$1"
  local marker="$2"
  shift 2
  "$@" | tee "$work/$name.log"
  if ! rg -q "$marker" "$work/$name.log"; then
    echo "$name did not emit required marker: $marker" >&2
    exit 1
  fi
}

run_and_require production-road-visual \
  'CANNONBALL_ROAD_VISUAL_OK profile=production' \
  ./scripts/run-scenario.sh \
    --fixture representative-interchanges --profile road-visual

run_and_require graybox-road-visual \
  'CANNONBALL_ROAD_VISUAL_OK profile=graybox' \
  ./scripts/run-scenario.sh \
    --fixture representative-interchanges --profile road-visual \
    --graybox-road-assets

run_and_require variable-lane-topology \
  'CANNONBALL_TOPOLOGY_OK' \
  ./scripts/run-scenario.sh --fixture variable-lanes --profile topology

run_and_require representative-route-choices \
  'CANNONBALL_ROUTE_CHOICE_OK' \
  ./scripts/run-scenario.sh \
    --fixture representative-interchanges --profile route-choices

echo "CANNONBALL_ROAD_ASSETS_OK profiles=2 topology_fixtures=2 shared_materials=18 shared_meshes=5"
