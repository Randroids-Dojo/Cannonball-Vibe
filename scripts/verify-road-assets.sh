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
  value="$(printf '%s\n' "$line" |
    rg -o "(^|[[:space:]])${key}=[0-9]+([.][0-9]+)?" |
    cut -d= -f2 || true)"
  if [[ -z "$value" || "$value" == *$'\n'* ]]; then
    echo "Missing or ambiguous metric '$key' in: $line" >&2
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
bridge_decks="$(metric_value "$production_line" bridge_decks)"
overpass_openings="$(metric_value "$production_line" overpass_openings)"
lighting_stages="$(metric_value "$production_line" lighting_stages)"
guide_signs="$(metric_value "$production_line" guide_signs)"
shields="$(metric_value "$production_line" shields)"
standard_shields="$(metric_value "$production_line" standard_shields)"
geometric_lane_arrows="$(metric_value "$production_line" geometric_lane_arrows)"
typography_fallbacks="$(metric_value "$production_line" typography_fallbacks)"
graybox_shared_materials="$(metric_value "$graybox_line" shared_materials)"
graybox_shared_meshes="$(metric_value "$graybox_line" shared_meshes)"
graybox_retroreflective_materials="$(
  metric_value "$graybox_line" retroreflective_materials
)"
graybox_bridge_decks="$(metric_value "$graybox_line" bridge_decks)"
graybox_overpass_openings="$(metric_value "$graybox_line" overpass_openings)"
graybox_lighting_stages="$(metric_value "$graybox_line" lighting_stages)"
graybox_guide_signs="$(metric_value "$graybox_line" guide_signs)"
graybox_shields="$(metric_value "$graybox_line" shields)"
graybox_standard_shields="$(metric_value "$graybox_line" standard_shields)"
graybox_geometric_lane_arrows="$(
  metric_value "$graybox_line" geometric_lane_arrows
)"
graybox_typography_fallbacks="$(
  metric_value "$graybox_line" typography_fallbacks
)"
if [[ "$graybox_shared_materials" != "$shared_materials" ||
      "$graybox_shared_meshes" != "$shared_meshes" ||
      "$graybox_retroreflective_materials" != "$retroreflective_materials" ||
      "$graybox_bridge_decks" != "$bridge_decks" ||
      "$graybox_overpass_openings" != "$overpass_openings" ||
      "$graybox_lighting_stages" != "$lighting_stages" ||
      "$graybox_guide_signs" != "$guide_signs" ||
      "$graybox_shields" != "$shields" ||
      "$graybox_standard_shields" != "$standard_shields" ||
      "$graybox_geometric_lane_arrows" != "$geometric_lane_arrows" ||
      "$graybox_typography_fallbacks" != "$typography_fallbacks" ]]; then
  echo "Production and graybox resource contracts differ." >&2
  exit 1
fi
if (( bridge_decks < 1 || overpass_openings < 1 || lighting_stages != 2 ||
      guide_signs < 1 || shields < 2 ||
      standard_shields != shields ||
      geometric_lane_arrows != guide_signs ||
      typography_fallbacks != guide_signs )); then
  echo "Road structure or day/night coverage is incomplete." >&2
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

printf 'CANNONBALL_ROAD_ASSETS_OK profiles=%s topology_fixtures=%s shared_materials=%s shared_meshes=%s retroreflective_materials=%s bridge_decks=%s overpass_openings=%s lighting_stages=%s guide_signs=%s shields=%s standard_shields=%s geometric_lane_arrows=%s typography_fallbacks=%s\n' \
  "${#visual_profiles[@]}" "${#topology_fixtures[@]}" "$shared_materials" \
  "$shared_meshes" "$retroreflective_materials" "$bridge_decks" "$overpass_openings" \
  "$lighting_stages" "$guide_signs" "$shields" "$standard_shields" \
  "$geometric_lane_arrows" "$typography_fallbacks"
