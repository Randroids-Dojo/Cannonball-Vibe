#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 [--fixture NAME] [--distance-miles N] [--platform current] [--evidence PATH] [--smoke-test] [scenario arguments]" >&2
  exit 2
fi

fixture="official-corridor"
fixture_explicit="false"
distance_miles=""
scenario_args=()
scenario_mode="scenario"
requested_platform="current"
evidence_path=""
scenario_seed="20260718"
save_points="100,250,400"
expected_completion="true"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fixture)
      if [[ $# -lt 2 ]]; then
        echo "--fixture requires a value." >&2
        exit 2
      fi
      fixture="$2"
      fixture_explicit="true"
      shift 2
      ;;
    --fixture=*)
      fixture="${1#--fixture=}"
      fixture_explicit="true"
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
    --platform)
      if [[ $# -lt 2 ]]; then
        echo "--platform requires a value." >&2
        exit 2
      fi
      requested_platform="$2"
      shift 2
      ;;
    --platform=*)
      requested_platform="${1#--platform=}"
      shift
      ;;
    --evidence)
      if [[ $# -lt 2 ]]; then
        echo "--evidence requires a path." >&2
        exit 2
      fi
      evidence_path="$2"
      shift 2
      ;;
    --evidence=*)
      evidence_path="${1#--evidence=}"
      shift
      ;;
    --seed)
      if [[ $# -lt 2 ]]; then
        echo "--seed requires a value." >&2
        exit 2
      fi
      scenario_seed="$2"
      shift 2
      ;;
    --seed=*)
      scenario_seed="${1#--seed=}"
      shift
      ;;
    --save-points)
      if [[ $# -lt 2 ]]; then
        echo "--save-points requires a comma-separated value." >&2
        exit 2
      fi
      save_points="$2"
      shift 2
      ;;
    --save-points=*)
      save_points="${1#--save-points=}"
      shift
      ;;
    --expected-completion)
      if [[ $# -lt 2 ]]; then
        echo "--expected-completion requires true or false." >&2
        exit 2
      fi
      expected_completion="$2"
      shift 2
      ;;
    --expected-completion=*)
      expected_completion="${1#--expected-completion=}"
      shift
      ;;
    --profile)
      if [[ $# -lt 2 ]]; then
        echo "--profile requires a value." >&2
        exit 2
      fi
      if [[ "$2" == "streaming" ]]; then
        scenario_mode="streaming"
        scenario_args+=("--streaming-profile")
      elif [[ "$2" == "topology" ]]; then
        scenario_mode="topology"
        scenario_args+=("--topology-profile")
      elif [[ "$2" == "route-choices" ]]; then
        scenario_mode="route-choices"
        scenario_args+=("--route-choice-profile")
      elif [[ "$2" == "signs" ]]; then
        scenario_mode="route-context"
        scenario_args+=("--route-context-profile")
      elif [[ "$2" == "vehicle-visual" ]]; then
        scenario_mode="vehicle-visual"
        scenario_args+=("--vehicle-visual-profile")
      elif [[ "$2" == "road-visual" ]]; then
        scenario_mode="road-visual"
        scenario_args+=("--road-visual-profile")
      elif [[ "$2" == "camera-handling" ]]; then
        scenario_mode="camera-handling"
        scenario_args+=("--camera-handling-profile")
      elif [[ "$2" == "trip-map-scale" ]]; then
        scenario_mode="trip-map-scale"
        scenario_args+=("--trip-map-scale-profile")
      else
        scenario_args+=("--profile=$2")
      fi
      shift 2
      ;;
    --profile=*)
      profile="${1#--profile=}"
      if [[ "$profile" == "streaming" ]]; then
        scenario_mode="streaming"
        scenario_args+=("--streaming-profile")
      elif [[ "$profile" == "topology" ]]; then
        scenario_mode="topology"
        scenario_args+=("--topology-profile")
      elif [[ "$profile" == "route-choices" ]]; then
        scenario_mode="route-choices"
        scenario_args+=("--route-choice-profile")
      elif [[ "$profile" == "signs" ]]; then
        scenario_mode="route-context"
        scenario_args+=("--route-context-profile")
      elif [[ "$profile" == "vehicle-visual" ]]; then
        scenario_mode="vehicle-visual"
        scenario_args+=("--vehicle-visual-profile")
      elif [[ "$profile" == "road-visual" ]]; then
        scenario_mode="road-visual"
        scenario_args+=("--road-visual-profile")
      elif [[ "$profile" == "camera-handling" ]]; then
        scenario_mode="camera-handling"
        scenario_args+=("--camera-handling-profile")
      elif [[ "$profile" == "trip-map-scale" ]]; then
        scenario_mode="trip-map-scale"
        scenario_args+=("--trip-map-scale-profile")
      else
        scenario_args+=("$1")
      fi
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
    --geographic-review)
      scenario_mode="geographic-review"
      scenario_args+=("$1")
      shift
      ;;
    --trip-map-review)
      scenario_mode="trip-map"
      scenario_args+=("$1")
      shift
      ;;
    --camera-handling-review)
      scenario_mode="camera-handling"
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

if [[ -n "$evidence_path" ]]; then
  if [[ -z "$distance_miles" ]]; then
    echo "--evidence requires --distance-miles for the deterministic long-route profile." >&2
    exit 2
  fi
  if [[ "$fixture_explicit" == "false" ]]; then
    fixture="representative-corridor"
  fi
  case "$evidence_path" in
    /*|[A-Za-z]:/*) ;;
    *) evidence_path="$repo_root/$evidence_path" ;;
  esac
  scenario_mode="long-route"
  scenario_args+=(
    "--long-route-profile"
    "--platform=$requested_platform"
    "--evidence=$evidence_path"
    "--seed=$scenario_seed"
    "--save-points=$save_points"
    "--expected-completion=$expected_completion"
  )
fi

if [[ "$scenario_mode" == "streaming" && "$fixture_explicit" == "false" ]]; then
  fixture="representative-corridor"
fi
if [[ "$scenario_mode" == "route-choices" && "$fixture_explicit" == "false" ]]; then
  fixture="representative-interchanges"
fi
if [[ "$scenario_mode" == "route-context" && "$fixture_explicit" == "false" ]]; then
  fixture="route-context"
fi
if [[ "$scenario_mode" == "vehicle-visual" && "$fixture_explicit" == "false" ]]; then
  fixture="representative-corridor"
fi
if [[ "$scenario_mode" == "road-visual" && "$fixture_explicit" == "false" ]]; then
  fixture="representative-interchanges"
fi
if [[ "$scenario_mode" == "trip-map" && "$fixture_explicit" == "false" ]]; then
  fixture="representative-interchanges"
fi
if [[ "$scenario_mode" == "camera-handling" && "$fixture_explicit" == "false" ]]; then
  fixture="representative-corridor"
fi

case "$fixture" in
  official-corridor)
    fixture_source="$repo_root/data/sources/fixtures/nhpn-boulder-us36.geojson"
    fixture_manifest="$repo_root/data/sources/fixtures/nhpn-boulder-us36.manifest.json"
    fixture_elevation="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.tif"
    fixture_elevation_metadata="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json"
    fixture_lock="$repo_root/data/sources/source-lock.json"
    fixture_chunk_meters=100
    ;;
  representative-corridor|variable-lanes|representative-interchanges|route-context)
    fixture_source="$repo_root/data/sources/fixtures/nhpn-boulder-westminster-us36.geojson"
    fixture_manifest="$repo_root/data/sources/fixtures/nhpn-boulder-westminster-us36.manifest.json"
    fixture_elevation="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder-westminster.tif"
    fixture_elevation_metadata="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder-westminster.metadata.json"
    fixture_lock="$repo_root/data/sources/representative-corridor-lock.json"
    fixture_chunk_meters=2000
    ;;
  *)
    echo "Unknown fixture '$fixture'. Supported fixtures: official-corridor, representative-corridor, variable-lanes, representative-interchanges, route-context." >&2
    exit 2
    ;;
esac
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
if [[ -n "$fixture" ]]; then
  package_directory="$repo_root/.tools/scenarios/$fixture"
  uv run --project "$repo_root/tools/map_pipeline" --frozen cannonball-map build \
    --source "$fixture_source" \
    --manifest "$fixture_manifest" \
    --catalog "$repo_root/data/sources/catalog.json" \
    --elevation "$fixture_elevation" \
    --elevation-metadata "$fixture_elevation_metadata" \
    --acquisition-lock "$fixture_lock" \
    --chunk-meters "$fixture_chunk_meters" \
    --output "$package_directory"

  package_pointer="$package_directory/current-package.json"
  if [[ ! -f "$package_pointer" ]]; then
    echo "Fixture build did not publish $package_pointer." >&2
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
    echo "Fixture build did not publish $route_package." >&2
    exit 1
  fi

  if [[ -n "$distance_miles" && -z "$evidence_path" ]]; then
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
    printf 'CANNONBALL_ROUTE_PROBE fixture=%s mode=%s unique_route_miles=%s requested_distance_miles=%s route_repetitions=%s verified_chunk_reads=%s\n' \
      "$fixture" "$verification_mode" "$unique_route_miles" "$distance_miles" "$route_repetitions" "$verified_chunk_reads"
  fi
fi

timeout_seconds="${CANNONBALL_SCENARIO_TIMEOUT_SECONDS:-120}"
timeout_marker="${TMPDIR:-/tmp}/cannonball-scenario-timeout-$$"
rm -f "$timeout_marker"

dotnet build "$repo_root/Cannonball.sln" --nologo
export CANNONBALL_GIT_REVISION
CANNONBALL_GIT_REVISION="$(git rev-parse HEAD)"

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
