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
  last_log="$work/$name.log"
}

metric_value() {
  local line="$1"
  local key="$2"
  local value
  value="$(printf '%s\n' "$line" | rg -o "${key}=[0-9]+([.][0-9]+)?" |
    cut -d= -f2 || true)"
  if [[ -z "$value" ]]; then
    echo "Missing metric '$key' in: $line" >&2
    exit 1
  fi
  printf '%s\n' "$value"
}

visual_profiles=(production graybox)
run_and_require production-road-visual \
  'CANNONBALL_ROAD_VISUAL_OK profile=production' \
  ./scripts/run-scenario.sh \
    --fixture representative-interchanges --profile road-visual
production_log="$last_log"
production_line="$(rg '^CANNONBALL_ROAD_VISUAL_OK ' "$production_log")"

run_and_require graybox-road-visual \
  'CANNONBALL_ROAD_VISUAL_OK profile=graybox' \
  ./scripts/run-scenario.sh \
    --fixture representative-interchanges --profile road-visual \
    --graybox-road-assets
graybox_log="$last_log"
graybox_line="$(rg '^CANNONBALL_ROAD_VISUAL_OK ' "$graybox_log")"

shared_materials="$(metric_value "$production_line" shared_materials)"
shared_meshes="$(metric_value "$production_line" shared_meshes)"
retroreflective_materials="$(metric_value "$production_line" retroreflective_materials)"
graybox_shared_materials="$(metric_value "$graybox_line" shared_materials)"
graybox_shared_meshes="$(metric_value "$graybox_line" shared_meshes)"
graybox_retroreflective_materials="$(
  metric_value "$graybox_line" retroreflective_materials
)"
if [[ "$graybox_shared_materials" != "$shared_materials" ||
      "$graybox_shared_meshes" != "$shared_meshes" ||
      "$graybox_retroreflective_materials" != "$retroreflective_materials" ]]; then
  echo "Production and graybox resource contracts differ." >&2
  exit 1
fi

topology_fixtures=(variable-lanes representative-interchanges)
topology_profiles=(topology route-choices)
topology_markers=(CANNONBALL_TOPOLOGY_OK CANNONBALL_INTERCHANGES_OK)
for index in "${!topology_fixtures[@]}"; do
  fixture="${topology_fixtures[$index]}"
  profile="${topology_profiles[$index]}"
  marker="${topology_markers[$index]}"
  run_and_require "$fixture-$profile" "$marker" \
    ./scripts/run-scenario.sh --fixture "$fixture" --profile "$profile"
done

printf 'CANNONBALL_ROAD_ASSETS_OK profiles=%s topology_fixtures=%s shared_materials=%s shared_meshes=%s retroreflective_materials=%s\n' \
  "${#visual_profiles[@]}" "${#topology_fixtures[@]}" "$shared_materials" \
  "$shared_meshes" "$retroreflective_materials"
