#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
source "$repo_root/scripts/tool-versions.sh"

test_filter=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --test-filter)
      test_filter="${2:-}"
      shift 2
      ;;
    --test-filter=*)
      test_filter="${1#--test-filter=}"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${GODOT_BIN:-}" ]]; then
  GODOT_BIN="$(command -v godot || true)"
fi
if [[ -z "$GODOT_BIN" || ! -x "$GODOT_BIN" ]]; then
  echo "P1-004 requires the official Godot 4.7.1 executable in GODOT_BIN." >&2
  exit 1
fi
export GODOT_BIN

actual_version="$("$GODOT_BIN" --version)"
if [[ "$actual_version" != "$CANNONBALL_GODOT_VERSION" ]]; then
  echo "Expected official Godot $CANNONBALL_GODOT_VERSION, found $actual_version." >&2
  exit 1
fi

# The suite runs whatever assembly sits in .godot; Godot only builds one when
# none exists, so a checkout that switched branches would test stale code.
dotnet build "$repo_root/Cannonball.sln" --nologo
# The live suite runs production scenes such as the Hero GT wrapper, whose
# sourced textures and generated scene need the importer once per checkout.
# Godot refuses to load a scene with an unimported dependency, so a fresh
# checkout without this step loses the whole vehicle rather than a texture.
# The .godot cache makes later runs a no-op.
"$repo_root/scripts/godot.sh" --headless --path "$repo_root" --import >/dev/null 2>&1 || \
  "$repo_root/scripts/godot.sh" --headless --path "$repo_root" --import

"$repo_root/scripts/verify-playgodot-package-boundary.sh"
uv run --project automation/playgodot --frozen ruff check automation/playgodot
if [[ -n "$test_filter" ]]; then
  uv run --project automation/playgodot --frozen pytest automation/playgodot -k "$test_filter"
else
  uv run --project automation/playgodot --frozen pytest automation/playgodot
fi
