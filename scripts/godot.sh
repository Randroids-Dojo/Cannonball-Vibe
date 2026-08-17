#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"

# Nursery size for the .NET GC, in hex bytes: 0x800000 is 8 MB.
#
# The game's per-frame garbage is dominated by Godot wrappers, which carry
# finalizers and so cannot die in gen0 - they are promoted by construction, which
# is why every collection is a gen1 collection. Pause length therefore tracks how
# much has to be promoted, and the nursery size sets how much that is.
#
# Measured on the representative corridor at 50 m/s over 60 s: the dynamic default
# gave 9 collections with a 39.7 ms worst frame, 8 MB gave 17 collections with a
# 24.5 ms worst frame, and 64 MB gave 2 collections with a 116.5 ms worst frame.
# More frequent, smaller pauses win because a 116 ms freeze is far more visible
# than several short ones. See docs/audits/2026-08-16-frame-stutter-root-cause.md.
#
# This has to be an environment variable. Godot hosts the runtime itself, so the
# System.GC.Gen0Size property in a runtimeconfig template is never read - verified
# by measurement, not assumed. An exported build needs the same variable set by
# whatever launches it.
export DOTNET_GCgen0size="${DOTNET_GCgen0size:-800000}"

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
