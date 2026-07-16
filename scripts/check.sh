#!/usr/bin/env bash
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root" || exit 1

report_root="${CANNONBALL_REPORT_DIR:-$repo_root/reports/m0}"
rm -rf "$report_root"
mkdir -p "$report_root/logs" "$report_root/dotnet" "$report_root/python" "$report_root/godot"

started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
overall_exit=0
step_results=()

run_step() {
  local name="$1"
  shift
  local log_file="$report_root/logs/$name.log"

  printf '\n== %s ==\n' "$name"
  "$@" 2>&1 | tee "$log_file"
  local step_exit=${PIPESTATUS[0]}
  local step_status="passed"
  if [[ $step_exit -ne 0 ]]; then
    step_status="failed"
    overall_exit=1
  fi
  step_results+=("{\"name\":\"$name\",\"status\":\"$step_status\",\"exit_code\":$step_exit,\"log\":\"logs/$name.log\"}")
}

run_step "doctor" env \
  CANNONBALL_DOCTOR_RESULT_FILE="$report_root/doctor.json" \
  "$repo_root/scripts/doctor.sh"
run_step "dotnet-build" dotnet build Cannonball.sln --nologo
run_step "dotnet-test" env DOTNET_ROLL_FORWARD=Major \
  dotnet test Cannonball.sln --no-build --nologo \
  --logger "trx;LogFileName=core-tests.trx" \
  --results-directory "$report_root/dotnet"
run_step "ruff" uv run --project tools/map_pipeline --frozen \
  ruff check tools/map_pipeline
run_step "pytest" uv run --project tools/map_pipeline --frozen \
  pytest --junitxml "$report_root/python/junit.xml"
run_step "godot-smoke" env \
  CANNONBALL_GODOT_LOG_FILE="$report_root/godot/godot.log" \
  CANNONBALL_SCENARIO_RESULT_FILE="$report_root/godot/scenario.json" \
  "$repo_root/scripts/run-scenario.sh" --smoke-test

finished_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
check_status="passed"
if [[ $overall_exit -ne 0 ]]; then
  check_status="failed"
fi

{
  printf '{\n'
  printf '  "schema_version": 1,\n'
  printf '  "status": "%s",\n' "$check_status"
  printf '  "platform": "%s",\n' "$(uname -s)"
  printf '  "commit": "%s",\n' "$(git rev-parse HEAD 2>/dev/null || printf unknown)"
  printf '  "started_at": "%s",\n' "$started_at"
  printf '  "finished_at": "%s",\n' "$finished_at"
  printf '  "steps": [\n'
  for ((index = 0; index < ${#step_results[@]}; index++)); do
    separator=","
    if [[ $index -eq $((${#step_results[@]} - 1)) ]]; then
      separator=""
    fi
    printf '    %s%s\n' "${step_results[$index]}" "$separator"
  done
  printf '  ]\n'
  printf '}\n'
} > "$report_root/summary.json"

printf '\nM0 verification %s. Reports: %s\n' "$check_status" "$report_root"
exit "$overall_exit"
