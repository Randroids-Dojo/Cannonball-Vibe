#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 --smoke-test [--stress-driver]" >&2
  exit 2
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

godot_args+=(-- "$@")
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
    printf '  "platform": "%s"\n' "$(uname -s)"
    printf '}\n'
  } > "$CANNONBALL_SCENARIO_RESULT_FILE"
fi

exit "$scenario_exit"
