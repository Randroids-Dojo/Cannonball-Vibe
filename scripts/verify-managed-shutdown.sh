#!/usr/bin/env bash
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"
report_dir="${CANNONBALL_MANAGED_SHUTDOWN_REPORT_DIR:-$repo_root/reports/managed-shutdown}"
mkdir -p "$report_dir"

"$repo_root/scripts/run-scenario.sh" --fixture official-corridor --smoke-test \
  --managed-shutdown-probe 2>&1 | tee "$report_dir/runtime.log"
scenario_exit=${PIPESTATUS[0]}

uv run --project "$repo_root/tools/map_pipeline" --frozen python - \
  "$report_dir" "$scenario_exit" <<'PY'
import json
import re
import sys
from pathlib import Path

report = Path(sys.argv[1])
exit_code = int(sys.argv[2])
transcript = (report / "runtime.log").read_text(encoding="utf-8", errors="replace")
transcript = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", transcript).replace("\r", "")
required = [
    "CANNONBALL_READY engine=4.7.1-stable (official)",
    "CANNONBALL_SAVE_OK",
    "CANNONBALL_SMOKE_OK",
    "CANNONBALL_SHUTDOWN_PROBE_QUEUED wrappers=32 inaccessible=32",
    "CANNONBALL_SHUTDOWN_PROBE_OK wrappers=32 finalized=32",
    "CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true",
]
missing = [marker for marker in required if marker not in transcript]
forbidden = [marker for marker in
             ("FATAL", "ERROR:", "Unhandled exception", "leaked at exit", "resources still in use")
             if marker.lower() in transcript.lower()]
duration = re.search(r"CANNONBALL_SHUTDOWN_OK .*elapsed_ms=([0-9.]+)", transcript)
passed = exit_code == 0 and not missing and not forbidden and duration is not None
result = {
    "status": "passed" if passed else "failed",
    "scenario_exit_code": exit_code,
    "queued_wrappers_required": 32,
    "finalized_wrappers_required": 32,
    "shutdown_milliseconds": float(duration[1]) if duration else None,
    "missing_markers": missing,
    "forbidden_diagnostics": forbidden,
    "evidence_kind": "actual official-engine induced queued-finalizer scenario",
}
(report / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
sys.exit(0 if passed else 1)
PY
exit $?
