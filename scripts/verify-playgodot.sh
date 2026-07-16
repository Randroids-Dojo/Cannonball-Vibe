#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
source "$repo_root/scripts/tool-versions.sh"

if [[ -z "${GODOT_BIN:-}" ]]; then
  GODOT_BIN="$(command -v godot || true)"
fi
if [[ -z "$GODOT_BIN" || ! -x "$GODOT_BIN" ]]; then
  echo "P1-004 requires the official Godot 4.7.1 executable in GODOT_BIN." >&2
  exit 1
fi
export GODOT_BIN

actual_version="$($GODOT_BIN --version)"
if [[ "$actual_version" != "$CANNONBALL_GODOT_VERSION" ]]; then
  echo "Expected official Godot $CANNONBALL_GODOT_VERSION, found $actual_version." >&2
  exit 1
fi

"$repo_root/scripts/verify-playgodot-package-boundary.sh"
uv run --project automation/playgodot --frozen ruff check automation/playgodot
uv run --project automation/playgodot --frozen pytest automation/playgodot
