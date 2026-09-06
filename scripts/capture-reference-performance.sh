#!/usr/bin/env bash
set -euo pipefail

# Q-022 reference performance capture (ADR-0023).
#
# Unlike scripts/run-scenario.sh this front door deliberately runs a WINDOWED,
# RENDERED session on the native renderer. A headless gl_compatibility run cannot
# measure presented-frame time, GPU attribution, or video memory on the declared
# RTX 3080 Ti, so this script never passes --headless.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"
cd "$repo_root"

usage() {
  cat >&2 <<'USAGE'
Usage: capture-reference-performance.sh --scenario NAME [options]

  --scenario NAME            Capture identifier recorded in the artifacts (required).
  --lighting daylight|night  Scenario lighting state (default: daylight).
  --camera chase|cockpit     Camera the run drives from (default: chase).
  --resolution WxH           Capture resolution (default: 2560x1440).
  --speed-mps N              Autopilot cruise target (default: 40).
  --warmup-seconds N         Warm-up discarded before measuring (default: 20).
  --measure-seconds N        Steady-state measurement duration (default: 120).
  --environment-quality Q    high|balanced|low|graybox (default: balanced).
  --vsync                    Enable V-Sync (default: disabled).
  --max-fps N                Cap presented frames (default: 0, uncapped).
  --fixture NAME             Route fixture (default: representative-corridor).
  --output-dir DIR           Artifact directory (default: reports/q022).
  --no-loop                  Disable short-corridor looping.
  --resample-meters N        Route sample spacing (default: pipeline default).
  --graybox-vehicle          Drive the box stand-in instead of the Hero GT rig.
  --allow-contended          Publish even if the machine was not idle.
USAGE
}

scenario=""
lighting="daylight"
camera="chase"
resolution="2560x1440"
speed_mps="40"
warmup_seconds="20"
measure_seconds="120"
environment_quality="balanced"
vsync="false"
max_fps="0"
fixture="representative-corridor"
output_dir="$repo_root/reports/q022"
loop_corridor="true"
allow_contended="false"
# Station spacing the route mesh is built from. The default matches the shipped
# package; varying it is how the speed sweep separates mesh faceting from terrain.
resample_meters=""
graybox_vehicle="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario) scenario="${2:?--scenario requires a value}"; shift 2 ;;
    --scenario=*) scenario="${1#--scenario=}"; shift ;;
    --lighting) lighting="${2:?--lighting requires a value}"; shift 2 ;;
    --lighting=*) lighting="${1#--lighting=}"; shift ;;
    --allow-contended) allow_contended="true"; shift ;;
    --graybox-vehicle) graybox_vehicle="true"; shift ;;
    --resample-meters) resample_meters="${2:?--resample-meters requires a value}"; shift 2 ;;
    --resample-meters=*) resample_meters="${1#--resample-meters=}"; shift ;;
    --camera) camera="${2:?--camera requires a value}"; shift 2 ;;
    --camera=*) camera="${1#--camera=}"; shift ;;
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
    --max-fps) max_fps="${2:?--max-fps requires a value}"; shift 2 ;;
    --max-fps=*) max_fps="${1#--max-fps=}"; shift ;;
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
case "$camera" in
  chase|cockpit) ;;
  *) echo "--camera must be chase or cockpit." >&2; exit 2 ;;
esac
if [[ ! "$max_fps" =~ ^[0-9]+$ ]]; then
  echo "--max-fps must be a non-negative integer; found '$max_fps'." >&2
  exit 2
fi
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
  ${resample_meters:+--resample-meters "$resample_meters"} \
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
  ${resample_meters:+--resample-meters "$resample_meters"} \
  --output "$repro_directory"

route_repro_path="$output_dir/route-package-reproducibility-$fixture.json"
route_repro_revision="$(git rev-parse HEAD)"
route_repro_verified_at_utc="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
route_repro_uv_version="$(uv --version)"
route_build_command="uv run --project tools/map_pipeline --frozen cannonball-map build --source data/sources/fixtures/nhpn-boulder-westminster-us36.geojson --manifest data/sources/fixtures/nhpn-boulder-westminster-us36.manifest.json --catalog data/sources/catalog.json --elevation data/sources/fixtures/usgs-13-n40w106-boulder-westminster.tif --elevation-metadata data/sources/fixtures/usgs-13-n40w106-boulder-westminster.metadata.json --acquisition-lock data/sources/representative-corridor-lock.json --chunk-meters $fixture_chunk_meters --output"
uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
  "$package_directory" "$repro_directory" "$route_repro_path" \
  "$repo_root" "$route_repro_revision" "$route_repro_verified_at_utc" \
  "$route_repro_uv_version" "$route_build_command" <<'PY'
import hashlib
import json
import platform
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


first_root, second_root, output_path, repo_root = map(Path, sys.argv[1:5])
git_revision, verified_at_utc, uv_version, build_command = sys.argv[5:9]
first = shipping_files(first_root)
second = shipping_files(second_root)
differences = sorted(
    path for path in set(first) | set(second) if first.get(path) != second.get(path)
)
if differences:
    raise SystemExit(f"Representative route package is not reproducible: {differences}")

pointer = json.loads((first_root / "current-package.json").read_text(encoding="utf-8"))
input_paths = [
    Path("data/sources/fixtures/nhpn-boulder-westminster-us36.geojson"),
    Path("data/sources/fixtures/nhpn-boulder-westminster-us36.manifest.json"),
    Path("data/sources/fixtures/usgs-13-n40w106-boulder-westminster.tif"),
    Path("data/sources/fixtures/usgs-13-n40w106-boulder-westminster.metadata.json"),
    Path("data/sources/representative-corridor-lock.json"),
    Path("data/sources/catalog.json"),
]
input_artifacts = []
for relative in input_paths:
    data = (repo_root / relative).read_bytes()
    input_artifacts.append(
        {
            "path": relative.as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    )

result = {
    "schema_version": 1,
    "task_id": "P1-013",
    "question_id": "Q-022",
    "milestone": "M5",
    "status": "passed",
    "fixture": "representative-corridor",
    "git_revision": git_revision,
    "verified_at_utc": verified_at_utc,
    "platform": {
        "os": platform.platform(),
        "architecture": platform.machine(),
    },
    "tool_versions": {
        "uv": uv_version.removeprefix("uv "),
        "python": platform.python_version(),
        "map_pipeline": "locked project environment",
    },
    "commands": [
        {"command": f"{build_command} <first>", "exit_status": 0},
        {"command": f"{build_command} <second>", "exit_status": 0},
    ],
    "input_artifacts": input_artifacts,
    "content_version": pointer["content_version"],
    "root_relative_path": pointer["root_relative_path"],
    "metadata_relative_path": pointer["metadata_relative_path"],
    "same_platform_rebuilds": 2,
    "same_platform_shipping_byte_diff_count": 0,
    "comparison_scope": (
        "current-package pointer, root, metadata, and every chunk; "
        "non-shipping GeoPackage audit output excluded"
    ),
    "output_artifacts": list(first.values()),
    "metrics": {
        "same_platform_rebuilds": 2,
        "same_platform_shipping_byte_diff_count": 0,
    },
    "failures": {
        "build_failures": 0,
        "comparison_failures": 0,
        "retries": 0,
    },
    "human_gate": None,
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
  "--reference-camera=$camera"
  "--reference-resolution=$resolution"
  "--reference-speed-mps=$speed_mps"
  "--reference-warmup-seconds=$warmup_seconds"
  "--reference-measure-seconds=$measure_seconds"
  "--reference-vsync=$vsync"
  "--reference-max-fps=$max_fps"
  "--reference-loop-corridor=$loop_corridor"
  "--reference-summary=$summary_path"
  "--reference-samples=$samples_path"
  "--environment-quality=$environment_quality"
  "--telemetry-path=$output_dir/telemetry-$scenario.jsonl"
)
# The visual rig moves wheel and suspension anchors by per-wheel compression, so
# perceived bumpiness can exceed measured chassis motion. The box stand-in shares
# the same collision shape and suspension, isolating rig motion from chassis motion.
if [[ "$graybox_vehicle" == "true" ]]; then
  godot_args+=("--graybox-vehicle")
fi

printf 'CANNONBALL_REFERENCE_CAPTURE_START scenario=%s configuration=%s resolution=%s lighting=%s camera=%s quality=%s vsync=%s max_fps=%s warmup_s=%s measure_s=%s timeout_s=%s\n' \
  "$scenario" "$build_configuration" "$resolution" "$lighting" "$camera" "$environment_quality" \
  "$vsync" "$max_fps" "$warmup_seconds" "$measure_seconds" "$timeout_seconds"

machine_state_path="$output_dir/machine-state-$scenario.json"
sample_gpu() {
  # Never fail a capture over a diagnostic sample.
  nvidia-smi \
    --query-gpu=utilization.gpu,utilization.memory,clocks.current.graphics,temperature.gpu,power.draw \
    --format=csv,noheader,nounits 2>/dev/null || echo "unavailable"
}
sample_clients() {
  nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader 2>/dev/null || true
}
# A matrix runs scenarios back to back, and the GPU has not returned to idle the
# instant the previous capture exits. Without this wait the precondition would
# measure recency rather than idleness and refuse most of a matrix. Waiting cannot
# mask real contention: a machine that is genuinely busy never settles, and the
# wait is bounded so it fails rather than hanging.
settle_seconds="${CANNONBALL_GPU_SETTLE_SECONDS:-60}"
# The ceiling comes from record_machine_state.py itself - default, override, and
# validation included - so the settle wait and the recorded verdict cannot
# disagree, and a malformed CANNONBALL_IDLE_GPU_CEILING_PERCENT fails here rather
# than after the capture has already run. Raising it is the owner's call and is
# recorded in the machine-state document rather than applied silently.
idle_ceiling="$(uv run --project "$repo_root/tools/map_pipeline" --frozen python -c \
  "import sys; sys.path.insert(0, sys.argv[1]); import record_machine_state; print(record_machine_state.idle_ceiling_percent())" \
  "$repo_root/scripts")"
settle_deadline=$((SECONDS + settle_seconds))
while true; do
  gpu_utilization="$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo unknown)"
  if [[ ! "$gpu_utilization" =~ ^[0-9]+$ ]] ||      awk -v value="$gpu_utilization" -v ceiling="$idle_ceiling"        'BEGIN { exit !(value <= ceiling) }'; then
    break
  fi
  if (( SECONDS >= settle_deadline )); then
    printf 'CANNONBALL_REFERENCE_GPU_NOT_SETTLED scenario=%s utilization=%s waited_s=%s\n' \
      "$scenario" "$gpu_utilization" "$settle_seconds"
    break
  fi
  sleep 2
done

gpu_before="$(sample_gpu)"
clients_before="$(sample_clients)"

# Bracketing samples missed the 2026-08-13 run whose GPU time was ten times its
# siblings, because whatever caused it was gone by the time the run ended. Sample
# throughout instead, so a client that arrives mid-measurement is recorded.
during_samples_path="$output_dir/machine-state-during-$scenario.csv"
: >"$during_samples_path"
sample_during() {
  local started elapsed
  started="$SECONDS"
  while true; do
    elapsed=$((SECONDS - started))
    printf '%s,%s,%s\n' \
      "$elapsed" \
      "$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo 0)" \
      "$(sample_clients | grep -c . || true)" \
      >>"$during_samples_path"
    sleep 2
  done
}
sample_during &
during_sampler_pid="$!"
# The sampler outlives a failed capture otherwise, and an orphaned nvidia-smi loop
# is itself a contending GPU client for whatever runs next.
trap 'kill "$during_sampler_pid" 2>/dev/null || true' EXIT

set +e
uv run --project "$repo_root/tools/map_pipeline" --frozen python \
  "$repo_root/scripts/run_with_timeout.py" "$timeout_seconds" \
  bash "$repo_root/scripts/godot.sh" "${godot_args[@]}" 2>&1 | tee "$log_path"
capture_exit="${PIPESTATUS[0]}"
set -e

kill "$during_sampler_pid" 2>/dev/null || true
wait "$during_sampler_pid" 2>/dev/null || true
trap - EXIT

gpu_after="$(sample_gpu)"
clients_after="$(sample_clients)"
set +e
uv run --project "$repo_root/tools/map_pipeline" --frozen python \
  "$repo_root/scripts/record_machine_state.py" \
  "$machine_state_path" "$scenario" "$gpu_before" "$gpu_after" \
  "$clients_before" "$clients_after" "$during_samples_path"
machine_state_exit="$?"
set -e
# Exit 3 means the capture did not start idle or saw a new GPU client arrive.
# ADR-0023's Q-022a addendum makes that a refusal rather than a footnote: a
# contended capture is not comparable with the others and must not be published.
if [[ "$machine_state_exit" -eq 3 ]]; then
  if [[ "$allow_contended" == "true" ]]; then
    printf 'CANNONBALL_REFERENCE_CONTENDED_ACCEPTED scenario=%s reason=--allow-contended\n' \
      "$scenario"
  else
    echo "Refusing to publish a contended capture. Close other GPU clients and re-run," >&2
    echo "or pass --allow-contended to record it as contended evidence." >&2
    exit 3
  fi
elif [[ "$machine_state_exit" -ne 0 ]]; then
  echo "Machine-state record failed with status $machine_state_exit." >&2
  exit "$machine_state_exit"
fi
machine_state_sha256="$(sha256sum "$machine_state_path" | cut -d' ' -f1)"
printf 'CANNONBALL_REFERENCE_MACHINE_STATE_SHA256 scenario=%s sha256=%s bytes=%s path=%s
'   "$scenario" "$machine_state_sha256"   "$(wc -c < "$machine_state_path" | tr -d ' ')" "$machine_state_path"

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
for artifact in "$summary_path" "$samples_path" "$route_repro_path" \
  "$machine_state_path"; do
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
    # An entry carries no verdict when it does not apply to this run: cap_adherence
    # on an uncapped run, and the p95 limit on a capped one. Reporting those as
    # PASS would claim a check ran that did not.
    if result.get("applicable") is False or "passed" not in result:
        print(f"CANNONBALL_REFERENCE_THRESHOLD {name}=NOT_APPLICABLE")
        continue
    evaluated = result.get("evaluated", True)
    verdict = "PASS" if result["passed"] else "FAIL"
    if not evaluated:
        verdict = "NOT_EVALUATED"
    print(f"CANNONBALL_REFERENCE_THRESHOLD {name}={verdict}")
PY

printf 'CANNONBALL_REFERENCE_PERFORMANCE_GATE_OK %s\n' "$marker"
