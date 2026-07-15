#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

dotnet build Cannonball.sln
DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --no-build
uv run --project tools/map_pipeline ruff check tools/map_pipeline
uv run --project tools/map_pipeline pytest

godot_bin="${GODOT_BIN:-$repo_root/.tools/godot-4.6.3/Godot_mono.app/Contents/MacOS/Godot}"
if [[ -x "$godot_bin" ]]; then
  "$godot_bin" --headless --path . -- --smoke-test
else
  echo "Godot smoke test skipped; set GODOT_BIN to a Godot 4.6.3 Mono executable."
fi
