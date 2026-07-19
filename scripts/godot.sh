#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"

if [[ -n "${GODOT_BIN:-}" ]]; then
  godot_bin="$GODOT_BIN"
elif [[ -x "$repo_root/.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot" ]]; then
  godot_bin="$repo_root/.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot"
elif [[ -x "$repo_root/.tools/godot-4.7.1/Godot_v4.7.1-stable_mono_win64/Godot_v4.7.1-stable_mono_win64_console.exe" ]]; then
  godot_bin="$repo_root/.tools/godot-4.7.1/Godot_v4.7.1-stable_mono_win64/Godot_v4.7.1-stable_mono_win64_console.exe"
elif command -v godot >/dev/null 2>&1; then
  godot_bin="$(command -v godot)"
elif [[ "${OS:-}" == "Windows_NT" ]]; then
  windows_local_app_data="${LOCALAPPDATA:-}"
  if [[ -n "$windows_local_app_data" ]] && command -v cygpath >/dev/null 2>&1; then
    windows_local_app_data="$(cygpath -u "$windows_local_app_data")"
  fi

  for candidate in \
    "$windows_local_app_data"/Microsoft/WinGet/Packages/GodotEngine.GodotEngine.Mono_*/Godot_v4.7.1-stable_mono_win64/Godot_v4.7.1-stable_mono_win64_console.exe \
    "$windows_local_app_data"/Microsoft/WinGet/Packages/GodotEngine.GodotEngine.Mono_*/Godot_v4.7.1-stable_mono_win64/Godot_v4.7.1-stable_mono_win64.exe; do
    if [[ -x "$candidate" ]]; then
      godot_bin="$candidate"
      break
    fi
  done
fi

if [[ -z "${godot_bin:-}" ]]; then
  echo "Godot 4.7.1 .NET not found. Set GODOT_BIN or install the exact editor." >&2
  exit 1
fi

actual_version="$($godot_bin --version)"
if [[ "$actual_version" != "$CANNONBALL_GODOT_VERSION" ]]; then
  echo "Expected Godot $CANNONBALL_GODOT_VERSION, found $actual_version at $godot_bin." >&2
  exit 1
fi

exec "$godot_bin" "$@"
