#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--all-scenarios" ) ]]; then
  echo "Usage: $0 [--all-scenarios]" >&2
  exit 2
fi

# Camera handling uses the same official-engine, authenticated semantic bridge
# as the required UI gate. Camera-specific dynamic probes live in its live suite.
"$repo_root/scripts/verify-playgodot.sh"
