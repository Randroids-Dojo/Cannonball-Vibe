#!/usr/bin/env bash
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"

report_file="${CANNONBALL_DOCTOR_RESULT_FILE:-$repo_root/reports/m0/doctor.json}"
mkdir -p "$(dirname "$report_file")"

check_names=()
check_expected=()
check_actual=()
check_status=()
failed_checks=0

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  printf '%s' "$value"
}

record_check() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  local status="passed"

  if [[ "$actual" != "$expected" ]]; then
    status="failed"
    failed_checks=$((failed_checks + 1))
  fi

  check_names+=("$name")
  check_expected+=("$expected")
  check_actual+=("$actual")
  check_status+=("$status")
  printf '%-12s %-6s expected=%s actual=%s\n' "$name" "$status" "$expected" "$actual"
}

if command -v dotnet >/dev/null 2>&1; then
  dotnet_actual="$(dotnet --version 2>&1)"
else
  dotnet_actual="missing"
fi
record_check "dotnet" "$CANNONBALL_DOTNET_SDK_VERSION" "$dotnet_actual"

if command -v uv >/dev/null 2>&1; then
  uv_actual="$(uv --version 2>&1)"
  uv_actual="${uv_actual#uv }"
  uv_actual="${uv_actual%% *}"
else
  uv_actual="missing"
fi
record_check "uv" "$CANNONBALL_UV_VERSION" "$uv_actual"

if command -v git >/dev/null 2>&1 && git lfs version >/dev/null 2>&1; then
  git_lfs_actual="$(git lfs version 2>&1)"
  git_lfs_actual="${git_lfs_actual#git-lfs/}"
  git_lfs_actual="${git_lfs_actual%% *}"
else
  git_lfs_actual="missing"
fi
record_check "git-lfs" "$CANNONBALL_GIT_LFS_VERSION" "$git_lfs_actual"

perl_actual="missing"
if command -v perl >/dev/null 2>&1; then
  perl_actual="available"
fi
record_check "perl" "available" "$perl_actual"

godot_output="$("$repo_root/scripts/godot.sh" --version 2>&1)"
godot_exit=$?
if [[ $godot_exit -eq 0 ]]; then
  godot_actual="${godot_output%%$'\n'*}"
else
  godot_actual="$godot_output"
fi
record_check "godot" "$CANNONBALL_GODOT_VERSION" "$godot_actual"

doctor_status="passed"
if [[ $failed_checks -ne 0 ]]; then
  doctor_status="failed"
fi

{
  printf '{\n'
  printf '  "schema_version": 1,\n'
  printf '  "status": "%s",\n' "$doctor_status"
  printf '  "failed_checks": %d,\n' "$failed_checks"
  printf '  "checks": [\n'
  for ((index = 0; index < ${#check_names[@]}; index++)); do
    separator=","
    if [[ $index -eq $((${#check_names[@]} - 1)) ]]; then
      separator=""
    fi
    printf '    {"name":"%s","expected":"%s","actual":"%s","status":"%s"}%s\n' \
      "$(json_escape "${check_names[$index]}")" \
      "$(json_escape "${check_expected[$index]}")" \
      "$(json_escape "${check_actual[$index]}")" \
      "${check_status[$index]}" \
      "$separator"
  done
  printf '  ]\n'
  printf '}\n'
} > "$report_file"

printf 'Doctor report: %s\n' "$report_file"
if [[ $failed_checks -ne 0 ]]; then
  exit 1
fi
