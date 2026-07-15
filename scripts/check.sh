#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

dotnet build Cannonball.sln
DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --no-build
uv run --project tools/map_pipeline ruff check tools/map_pipeline
uv run --project tools/map_pipeline pytest

"$repo_root/scripts/run-scenario.sh" --smoke-test
