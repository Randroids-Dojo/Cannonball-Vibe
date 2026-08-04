#!/usr/bin/env bash
set -euo pipefail

# Q-022 reference performance capture (ADR-0023).
#
# Unlike scripts/run-scenario.sh this front door deliberately runs a WINDOWED,
# RENDERED session on the native renderer. A headless gl_compatibility run cannot
# measure presented-frame time, GPU attribution, or video memory on the declared
# RTX 3080 Ti, so this script never passes --headless.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

usage() {
  cat >&2 <<'USAGE'
Usage: capture-reference-performance.sh --scenario NAME [options]

  --scenario NAME            Capture identifier recorded in the artifacts (required).
  --lighting daylight|night  Scenario lighting state (default: daylight).
  --resolution WxH           Capture resolution (default: 2560x1440).
  --speed-mps N              Autopilot cruise target (default: 40).
  --warmup-seconds N         Warm-up discarded before measuring (default: 20).
  --measure-seconds N        Steady-state measurement duration (default: 120).
  --environment-quality Q    high|balanced|low|graybox (default: balanced).
  --vsync                    Enable V-Sync (default: disabled).
  --fixture NAME             Route fixture (default: representative-corridor).
  --output-dir DIR           Artifact directory (default: reports/q022).
  --no-loop                  Disable short-corridor looping.
USAGE
}

scenario=""
lighting="daylight"
resolution="2560x1440"
speed_mps="40"
warmup_seconds="20"
measure_seconds="120"
environment_quality="balanced"
vsync="false"
fixture="representative-corridor"
output_dir="$repo_root/reports/q022"
loop_corridor="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario) scenario="${2:?--scenario requires a value}"; shift 2 ;;
    --scenario=*) scenario="${1#--scenario=}"; shift ;;
    --lighting) lighting="${2:?--lighting requires a value}"; shift 2 ;;
    --lighting=*) lighting="${1#--lighting=}"; shift ;;
    --resolution) resolution="${2:?--resolution requires a value}"; shift 2 ;;
    --resolution=*) resolution="${1#--resolution=}"; shift ;;
    --speed-mps) speed_mps="${2:?--speed-mps requires a value}"; shift 2 ;;
    --speed-mps=*) speed_mps="${1#--speed-mps=}"; shift ;;
    --warmup-seconds) warmup_seconds="${2:?--warmup-seconds requires a value}"; shift 2 ;;
    --warmup-seconds=*) warmup_seconds="${1#--warmup-seconds=}"; shift ;;
    --measure-seconds) measure_seconds="${2:?--measure-seconds requires a value}"; shift 2 ;;
    --measure-seconds=*) measure_seconds="${1#--measure-seconds=}"; shift ;;
    --environment-quality) environment_quality="${2:?--environment-quality requires a value}"; shift 2 ;;
    --environment-quality=*) environment_quality="${1#--environment-quality=}"; shift ;;
    --vsync) vsync="true"; shift ;;
    --fixture) fixture="${2:?--fixture requires a value}"; shift 2 ;;
    --fixture=*) fixture="${1#--fixture=}"; shift ;;
    --output-dir) output_dir="${2:?--output-dir requires a value}"; shift 2 ;;
    --output-dir=*) output_dir="${1#--output-dir=}"; shift ;;
    --no-loop) loop_corridor="false"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument '$1'." >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$scenario" ]]; then
  echo "--scenario is required." >&2
  usage
  exit 2
fi
if [[ ! "$scenario" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "--scenario must be a separator-free name using letters, numbers, '.', '_', or '-'." >&2
  exit 2
fi
if [[ ! "$resolution" =~ ^[1-9][0-9]*x[1-9][0-9]*$ ]]; then
  echo "--resolution must be WIDTHxHEIGHT." >&2
  exit 2
fi
case "$lighting" in
  daylight|night) ;;
  *) echo "--lighting must be daylight or night." >&2; exit 2 ;;
esac
case "$environment_quality" in
  high|balanced|low|graybox) ;;
  *) echo "--environment-quality must be high, balanced, low, or graybox." >&2; exit 2 ;;
esac
for numeric in "$speed_mps" "$warmup_seconds"; do
  if ! awk -v value="$numeric" 'BEGIN { exit !(value ~ /^([0-9]+([.][0-9]*)?|[.][0-9]+)$/) }'; then
    echo "Numeric options must be non-negative numbers; found '$numeric'." >&2
    exit 2
  fi
done
if ! awk -v value="$measure_seconds" \
  'BEGIN { exit !(value ~ /^([0-9]+([.][0-9]*)?|[.][0-9]+)$/ && value > 0) }'; then
  echo "--measure-seconds must be a number greater than zero; found '$measure_seconds'." >&2
  exit 2
fi

case "$fixture" in
  representative-corridor)
    fixture_source="$repo_root/data/sources/fixtures/nhpn-boulder-westminster-us36.geojson"
    fixture_manifest="$repo_root/data/sources/fixtures/nhpn-boulder-westminster-us36.manifest.json"
    fixture_elevation="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder-westminster.tif"
    fixture_elevation_metadata="$repo_root/data/sources/fixtures/usgs-13-n40w106-boulder-westminster.metadata.json"
    fixture_lock="$repo_root/data/sources/representative-corridor-lock.json"
    fixture_chunk_meters=2000
    ;;
  *)
    echo "Unsupported fixture '$fixture'. This capture uses representative-corridor." >&2
    exit 2
    ;;
esac

mkdir -p "$output_dir"
summary_path="$output_dir/reference-performance-$scenario.json"
samples_path="$output_dir/reference-performance-$scenario.jsonl"
log_path="$output_dir/reference-performance-$scenario.log"

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

repro_directory="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-q022-route-repro.XXXXXX")"
trap 'rm -rf -- "$repro_directory"' EXIT
uv run --project "$repo_root/tools/map_pipeline" --frozen cannonball-map build \
  --source "$fixture_source" \
  --manifest "$fixture_manifest" \
  --catalog "$repo_root/data/sources/catalog.json" \
  --elevation "$fixture_elevation" \
  --elevation-metadata "$fixture_elevation_metadata" \
  --acquisition-lock "$fixture_lock" \
  --chunk-meters "$fixture_chunk_meters" \
  --output "$repro_directory"

route_repro_path="$output_dir/route-package-reproducibility-$fixture.json"
uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
  "$package_directory" "$repro_directory" "$route_repro_path" <<'PY'
import hashlib
import json
import sys
from pathlib import Path


def shipping_files(root: Path) -> dict[str, dict[str, object]]:
    pointer_path = root / "current-package.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    metadata_path = root / pointer["metadata_relative_path"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    paths = [pointer_path, root / pointer["root_relative_path"], metadata_path]
    paths.extend(root / chunk["relative_path"] for chunk in metadata["chunks"])
    result = {}
    for path in paths:
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        result[relative] = {
            "path": relative,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return result


first_root, second_root, output_path = map(Path, sys.argv[1:])
first = shipping_files(first_root)
second = shipping_files(second_root)
differences = sorted(
    path for path in set(first) | set(second) if first.get(path) != second.get(path)
)
if differences:
    raise SystemExit(f"Representative route package is not reproducible: {differences}")

pointer = json.loads((first_root / "current-package.json").read_text(encoding="utf-8"))
result = {
    "schema_version": 1,
    "fixture": "representative-corridor",
    "content_version": pointer["content_version"],
    "root_relative_path": pointer["root_relative_path"],
    "metadata_relative_path": pointer["metadata_relative_path"],
    "same_platform_rebuilds": 2,
    "same_platform_shipping_byte_diff_count": 0,
    "comparison_scope": (
        "current-package pointer, root, metadata, and every chunk; "
        "non-shipping GeoPackage audit output excluded"
    ),
    "shipping_artifacts": list(first.values()),
}
output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(
    "CANNONBALL_REFERENCE_ROUTE_REPRODUCIBLE "
    f"fixture=representative-corridor files={len(first)} differences=0 "
    f"manifest={output_path}"
)
PY

package_pointer="$package_directory/current-package.json"
if [[ ! -f "$package_pointer" ]]; then
  echo "Fixture build did not publish $package_pointer." >&2
  exit 1
fi
root_relative_path="$(uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
  "$package_pointer" <<'PY'
import json
import sys

pointer = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(pointer["root_relative_path"])
PY
)"
route_package="$package_directory/$root_relative_path"
if [[ ! -f "$route_package" ]]; then
  echo "Fixture build did not publish $route_package." >&2
  exit 1
fi

build_configuration="Release"
# The editor runtime resolves the managed project from its conventional Debug output
# directory. Compile Release IL into that runtime location so the measured assembly is
# optimized without requiring an exported game package solely for the benchmark harness.
# Restore the full solution against its committed lock files first. A configuration-specific
# Release restore omits GodotSharpEditor and rewrites the Debug-oriented root lock file, which
# would make the exact-commit capture worktree dirty before measurement begins.
dotnet restore "$repo_root/Cannonball.sln" --locked-mode --nologo
dotnet build "$repo_root/Cannonball.csproj" \
  --configuration "$build_configuration" \
  --output "$repo_root/.godot/mono/temp/bin/Debug" \
  --no-restore \
  --nologo
export CANNONBALL_GIT_REVISION
CANNONBALL_GIT_REVISION="$(git rev-parse HEAD)"

# The watchdog must outlast warm-up plus the measured window; a capture killed early
# would silently produce a short, non-comparable distribution.
timeout_seconds="$(awk -v warmup="$warmup_seconds" -v measure="$measure_seconds" \
  'BEGIN { printf "%d", warmup + measure + 300 }')"

godot_args=(
  --rendering-method forward_plus
  --resolution "$resolution"
  --path "$repo_root"
  --
  "--route-package=$route_package"
  --reference-performance-profile
  "--reference-scenario=$scenario"
  "--reference-lighting=$lighting"
  "--reference-resolution=$resolution"
  "--reference-speed-mps=$speed_mps"
  "--reference-warmup-seconds=$warmup_seconds"
  "--reference-measure-seconds=$measure_seconds"
  "--reference-vsync=$vsync"
  "--reference-loop-corridor=$loop_corridor"
  "--reference-summary=$summary_path"
  "--reference-samples=$samples_path"
  "--environment-quality=$environment_quality"
  "--telemetry-path=$output_dir/telemetry-$scenario.jsonl"
)

printf 'CANNONBALL_REFERENCE_CAPTURE_START scenario=%s configuration=%s resolution=%s lighting=%s quality=%s vsync=%s warmup_s=%s measure_s=%s timeout_s=%s\n' \
  "$scenario" "$build_configuration" "$resolution" "$lighting" "$environment_quality" "$vsync" \
  "$warmup_seconds" "$measure_seconds" "$timeout_seconds"

set +e
timeout --foreground --signal=TERM --kill-after=30 "${timeout_seconds}s" \
  "$repo_root/scripts/godot.sh" "${godot_args[@]}" 2>&1 | tee "$log_path"
capture_exit="${PIPESTATUS[0]}"
set -e

if [[ $capture_exit -ne 0 ]]; then
  echo "Reference performance capture exited with status $capture_exit." >&2
  exit "$capture_exit"
fi

if marker="$(grep '^CANNONBALL_REFERENCE_PERFORMANCE_OK ' "$log_path")"; then
  :
else
  grep_status=$?
  if [[ $grep_status -ne 1 ]]; then
    echo "Could not read the reference performance log." >&2
    exit "$grep_status"
  fi
  marker=""
fi
if [[ -z "$marker" || "$marker" == *$'\n'* ]]; then
  echo "Reference performance capture emitted a missing or ambiguous completion marker." >&2
  exit 1
fi
for required in "scenario=$scenario" "resolution=$resolution" "headless=false"; do
  if [[ " $marker " != *" $required "* ]]; then
    echo "Reference performance marker is missing '$required': $marker" >&2
    exit 1
  fi
done
for artifact in "$summary_path" "$samples_path" "$route_repro_path"; do
  if [[ ! -s "$artifact" ]]; then
    echo "Reference performance capture did not write $artifact." >&2
    exit 1
  fi
done

uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
  "$summary_path" <<'PY'
import json
import sys

acceptance = json.loads(open(sys.argv[1], encoding="utf-8").read())["acceptance"]
for name, result in acceptance.items():
    evaluated = result.get("evaluated", True)
    verdict = "PASS" if result["passed"] else "FAIL"
    if not evaluated:
        verdict = "NOT_EVALUATED"
    print(f"CANNONBALL_REFERENCE_THRESHOLD {name}={verdict}")
PY

printf 'CANNONBALL_REFERENCE_PERFORMANCE_GATE_OK %s\n' "$marker"
