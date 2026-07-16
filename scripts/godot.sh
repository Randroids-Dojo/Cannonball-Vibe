#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"

if [[ -n "${GODOT_BIN:-}" ]]; then
  godot_bin="$GODOT_BIN"
elif [[ -x "$repo_root/.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot" ]]; then
  godot_bin="$repo_root/.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot"
elif command -v godot >/dev/null 2>&1; then
  godot_bin="$(command -v godot)"
else
  echo "Godot 4.7.1 .NET not found. Set GODOT_BIN or install the exact editor." >&2
  exit 1
fi

actual_version="$($godot_bin --version)"
if [[ "$actual_version" != "$CANNONBALL_GODOT_VERSION" ]]; then
  echo "Expected Godot $CANNONBALL_GODOT_VERSION, found $actual_version at $godot_bin." >&2
  exit 1
fi

exec "$godot_bin" "$@"
