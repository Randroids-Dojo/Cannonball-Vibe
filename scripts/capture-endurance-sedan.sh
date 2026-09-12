#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"
exec uv run --project "$repo_root/tools/map_pipeline" --frozen python \
  "$repo_root/tools/vehicles/capture_endurance_sedan.py" "$@"
