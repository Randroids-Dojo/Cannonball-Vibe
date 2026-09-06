#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The continental front door: builds one locked P0-021 segment into a runtime
# package from the committed locks (no download, no cache) and launches the
# game on it through the ordinary scenario runner. The segment fixture names
# map to segment ids in scripts/run-scenario.sh; today that is continental-i70
# (i70-denver-to-cove-fort). Every other argument passes through, so
#   ./scripts/run-continental-scenario.sh --smoke-test
#   ./scripts/run-continental-scenario.sh --distance-miles 400
# behave as they do for the fixtures.

fixture="continental-i70"
passthrough=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --segment-fixture)
      if [[ $# -lt 2 ]]; then
        echo "--segment-fixture requires a value." >&2
        exit 2
      fi
      fixture="$2"
      shift 2
      ;;
    --segment-fixture=*)
      fixture="${1#--segment-fixture=}"
      shift
      ;;
    *)
      passthrough+=("$1")
      shift
      ;;
  esac
done

if [[ ${#passthrough[@]} -eq 0 ]]; then
  echo "Usage: $0 [--segment-fixture continental-i70] [scenario arguments, e.g. --smoke-test]" >&2
  exit 2
fi

exec "$repo_root/scripts/run-scenario.sh" --fixture "$fixture" "${passthrough[@]}"
