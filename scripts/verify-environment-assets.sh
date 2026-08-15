#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

region=""
all_quality_levels="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)
      [[ $# -ge 2 ]] || { echo "--region requires a value." >&2; exit 2; }
      region="$2"
      shift 2
      ;;
    --region=*)
      region="${1#--region=}"
      shift
      ;;
    --all-quality-levels)
      all_quality_levels="true"
      shift
      ;;
    *)
      echo "Unknown argument '$1'." >&2
      exit 2
      ;;
  esac
done

if [[ "$region" != "representative" || "$all_quality_levels" != "true" ]]; then
  echo "Usage: $0 --region representative --all-quality-levels" >&2
  exit 2
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
profiles=(high balanced low graybox)
baseline_semantics=""
previous_terrain_triangles=""
for profile in "${profiles[@]}"; do
  log="$tmp_dir/$profile.log"
  args=(--fixture representative-corridor --profile environment-streaming)
  if [[ "$profile" == "graybox" ]]; then
    args+=(--graybox-environment-assets)
  else
    args+=("--environment-quality=$profile")
  fi
  ./scripts/run-scenario.sh "${args[@]}" >"$log" 2>&1
  marker="$(grep 'CANNONBALL_ENVIRONMENT_OK' "$log" | tail -n 1)"
  [[ -n "$marker" ]] || { cat "$log" >&2; echo "Missing environment marker for $profile." >&2; exit 1; }
  echo "$marker" | grep -q "profile=$profile"
  echo "$marker" | grep -q 'stages=5 regions=4'
  echo "$marker" | grep -q 'collision_free=True'
  echo "$marker" | grep -q 'collision_budget=0'
  # The seam must sit inside what float32 can represent at those vertices, which
  # the scenario computes per vertex pair and publishes as a ratio. Asserting an
  # exact 0.0000 metres instead is unreachable beyond about two kilometres from
  # the origin: see docs/audits/2026-08-14-terrain-seam-gate.md.
  seam_ratio="$(echo "$marker" | tr ' ' '\n' | sed -n 's/^max_terrain_seam_float32_ratio=//p')"
  if [[ -z "$seam_ratio" ]]; then
    echo "Missing max_terrain_seam_float32_ratio for $profile." >&2
    exit 1
  fi
  if ! awk -v ratio="$seam_ratio" 'BEGIN { exit !(ratio <= 1.0) }'; then
    echo "Terrain seam exceeds float32 representable spacing for $profile: ratio=$seam_ratio" >&2
    exit 1
  fi
  terrain_triangles="$(echo "$marker" | tr ' ' '\n' | sed -n 's/^terrain_triangles=//p')"
  if [[ ! "$terrain_triangles" =~ ^[0-9]+$ || "$terrain_triangles" -le 0 ]]; then
    echo "Invalid terrain triangle count for $profile: '$terrain_triangles'." >&2
    exit 1
  fi
  if [[ -n "$previous_terrain_triangles" &&
        "$terrain_triangles" -ge "$previous_terrain_triangles" ]]; then
    echo "Terrain quality degradation is not strictly ordered for $profile." >&2
    echo "previous=$previous_terrain_triangles current=$terrain_triangles" >&2
    exit 1
  fi
  previous_terrain_triangles="$terrain_triangles"
  semantics="$(echo "$marker" | tr ' ' '\n' | grep -E '^(stages|regions|observed_chunks|terrain_ribbons|max_terrain_seam_m|collision_free|collision_budget|rebases)=' | tr '\n' ' ')"
  if [[ -z "$baseline_semantics" ]]; then
    baseline_semantics="$semantics"
  elif [[ "$semantics" != "$baseline_semantics" ]]; then
    echo "Environment route/streaming semantics differ for $profile." >&2
    echo "baseline: $baseline_semantics" >&2
    echo "observed: $semantics" >&2
    exit 1
  fi
  echo "CANNONBALL_ENVIRONMENT_PROFILE_OK profile=$profile terrain_triangles=$terrain_triangles $semantics"
done

echo "CANNONBALL_ENVIRONMENT_ASSET_GATE_OK region=$region profiles=${#profiles[@]} semantics_equivalent=true terrain_degradation_ordered=true"
