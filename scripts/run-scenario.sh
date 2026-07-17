#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 [--fixture official-corridor] [--distance-miles N] [--smoke-test] [scenario arguments]" >&2
  exit 2
fi

fixture="official-corridor"
distance_miles=""
scenario_args=()
scenario_mode="scenario"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fixture)
      if [[ $# -lt 2 ]]; then
        echo "--fixture requires a value." >&2
        exit 2
      fi
      fixture="$2"
      shift 2
      ;;
    --fixture=*)
      fixture="${1#--fixture=}"
      shift
      ;;
    --distance-miles)
      if [[ $# -lt 2 ]]; then
        echo "--distance-miles requires a value." >&2
        exit 2
      fi
      distance_miles="$2"
      shift 2
      ;;
    --distance-miles=*)
      distance_miles="${1#--distance-miles=}"
      shift
      ;;
    --short-corridor-soak)
      scenario_mode="short-corridor-soak"
      scenario_args+=("$1")
      shift
      ;;
    --render-integrity)
      scenario_mode="render-integrity"
      scenario_args+=("$1")
      shift
      ;;
    --stress-driver)
      scenario_mode="long-route-stress"
      scenario_args+=("$1")
      shift
      ;;
    --smoke-test)
      if [[ "$scenario_mode" == "scenario" ]]; then
        scenario_mode="smoke"
      fi
      scenario_args+=("$1")
      shift
      ;;
    *)
      scenario_args+=("$1")
      shift
      ;;
  esac
done

if [[ -n "$fixture" && "$fixture" != "official-corridor" ]]; then
  echo "Unknown fixture '$fixture'. Supported fixtures: official-corridor." >&2
  exit 2
fi
if [[ -n "$distance_miles" ]] &&
  ! awk -v value="$distance_miles" 'BEGIN { exit !(value ~ /^([0-9]+([.][0-9]*)?|[.][0-9]+)$/ && value > 0) }'; then
  echo "--distance-miles must be a positive number." >&2
  exit 2
fi
if [[ -n "$distance_miles" ]]; then
  distance_miles="$(LC_ALL=C awk -v value="$distance_miles" 'BEGIN { printf "%.15g", value + 0 }')"
fi

route_package=""
unique_route_miles=""
route_repetitions=""
verification_mode=""
verified_chunk_reads=""
if [[ "$fixture" == "official-corridor" ]]; then
  package_directory="$repo_root/.tools/scenarios/official-corridor"
  uv run --project "$repo_root/tools/map_pipeline" --frozen cannonball-map build \
    --source "$repo_root/data/sources/fixtures/nhpn-boulder-us36.geojson" \
    --manifest "$repo_root/data/sources/fixtures/nhpn-boulder-us36.manifest.json" \
    --catalog "$repo_root/data/sources/catalog.json" \
    --elevation "$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.tif" \
    --elevation-metadata "$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json" \
    --acquisition-lock "$repo_root/data/sources/source-lock.json" \
    --chunk-meters 100 \
    --output "$package_directory"

  package_pointer="$package_directory/current-package.json"
  if [[ ! -f "$package_pointer" ]]; then
    echo "Official corridor build did not publish $package_pointer." >&2
    exit 1
  fi
  pointer_paths="$(uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
    "$package_pointer" <<'PY'
import json
import sys

pointer = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(f"{pointer['root_relative_path']}\t{pointer['metadata_relative_path']}")
PY
)"
  IFS=$'\t' read -r root_relative_path metadata_relative_path <<< "$pointer_paths"
  route_package="$package_directory/$root_relative_path"
  route_metadata="$package_directory/$metadata_relative_path"
  if [[ ! -f "$route_package" ]]; then
    echo "Official corridor build did not publish $route_package." >&2
    exit 1
  fi

  if [[ -n "$distance_miles" ]]; then
    probe_metadata="$(uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
      "$route_metadata" "$distance_miles" <<'PY'
import json
import math
import sys

package_path, requested_text = sys.argv[1:]
package = json.loads(open(package_path, encoding="utf-8").read())
unique_miles = sum(float(edge["length_meters"]) for edge in package["edges"]) / 1609.344
requested_miles = float(requested_text)
if unique_miles <= 0:
    raise SystemExit("Official corridor package has no route mileage.")
repetitions = math.ceil(requested_miles / unique_miles)
mode = "repeated-transport-verification" if repetitions > 1 else "unique-route-verification"
verified_reads = repetitions * len(package["chunks"])
print(f"{unique_miles:.6f}\t{repetitions}\t{mode}\t{verified_reads}")
PY
)"
    IFS=$'\t' read -r unique_route_miles route_repetitions verification_mode verified_chunk_reads <<< "$probe_metadata"
    scenario_mode="$verification_mode"
    printf 'CANNONBALL_ROUTE_PROBE fixture=official-corridor mode=%s unique_route_miles=%s requested_distance_miles=%s route_repetitions=%s verified_chunk_reads=%s\n' \
      "$verification_mode" "$unique_route_miles" "$distance_miles" "$route_repetitions" "$verified_chunk_reads"
  fi
fi

timeout_seconds="${CANNONBALL_SCENARIO_TIMEOUT_SECONDS:-120}"
timeout_marker="${TMPDIR:-/tmp}/cannonball-scenario-timeout-$$"
rm -f "$timeout_marker"

dotnet build "$repo_root/Cannonball.sln" --nologo

godot_args=(
  --headless
  --rendering-method gl_compatibility
  --path "$repo_root"
)

if [[ -n "${CANNONBALL_GODOT_LOG_FILE:-}" ]]; then
  mkdir -p "$(dirname "$CANNONBALL_GODOT_LOG_FILE")"
  godot_args+=(--log-file "$CANNONBALL_GODOT_LOG_FILE")
fi

godot_args+=(--)
if [[ -n "$route_package" ]]; then
  godot_args+=("--route-package=$route_package")
fi
if [[ -n "$distance_miles" ]]; then
  godot_args+=("--distance-miles=$distance_miles")
fi
if [[ ${#scenario_args[@]} -gt 0 ]]; then
  godot_args+=("${scenario_args[@]}")
fi
"$repo_root/scripts/godot.sh" "${godot_args[@]}" &
scenario_pid=$!

# shellcheck disable=SC2329  # Invoked by the EXIT trap.
cleanup() {
  kill "$watchdog_pid" 2>/dev/null || true
  rm -f "$timeout_marker"
}
trap cleanup EXIT

perl -e '
  use strict;
  use warnings;
  my ($seconds, $pid, $marker) = @ARGV;
  sleep $seconds;
  open my $marker_file, ">", $marker or die "Cannot create timeout marker: $!";
  close $marker_file;
  warn "Godot scenario exceeded ${seconds}s; terminating process ${pid}.\n";
  kill "TERM", $pid;
' "$timeout_seconds" "$scenario_pid" "$timeout_marker" &
watchdog_pid=$!

set +e
wait "$scenario_pid"
scenario_exit=$?
set -e

kill "$watchdog_pid" 2>/dev/null || true
wait "$watchdog_pid" 2>/dev/null || true

scenario_status="passed"
timed_out="false"
if [[ -e "$timeout_marker" ]]; then
  scenario_status="timed_out"
  timed_out="true"
elif [[ $scenario_exit -ne 0 ]]; then
  scenario_status="failed"
fi

if [[ -n "${CANNONBALL_SCENARIO_RESULT_FILE:-}" ]]; then
  mkdir -p "$(dirname "$CANNONBALL_SCENARIO_RESULT_FILE")"
  {
    printf '{\n'
    printf '  "schema_version": 1,\n'
    printf '  "status": "%s",\n' "$scenario_status"
    printf '  "exit_code": %d,\n' "$scenario_exit"
    printf '  "timed_out": %s,\n' "$timed_out"
    printf '  "platform": "%s"' "$(uname -s)"
    printf ',\n  "scenario_mode": "%s"' "$scenario_mode"
    if [[ -n "$fixture" ]]; then
      printf ',\n  "fixture": "%s"' "$fixture"
    fi
    if [[ -n "$distance_miles" && -n "$unique_route_miles" ]]; then
      printf ',\n  "requested_distance_miles": %s,\n' "$distance_miles"
      printf '  "unique_route_miles": %s,\n' "$unique_route_miles"
      printf '  "route_repetitions": %s,\n' "$route_repetitions"
      printf '  "verification_mode": "%s",\n' "$verification_mode"
      printf '  "verified_chunk_reads": %s,\n' "$verified_chunk_reads"
      if [[ "$scenario_status" == "passed" ]]; then
        printf '  "chunk_failures": 0'
      else
        printf '  "chunk_failures": null'
      fi
    fi
    printf '\n'
    printf '}\n'
  } > "$CANNONBALL_SCENARIO_RESULT_FILE"
fi

exit "$scenario_exit"
