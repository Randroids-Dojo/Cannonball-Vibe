#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if git grep -ni 'playgodot' -- project.godot >/dev/null; then
  echo "PlayGodot must not be a project autoload or normal startup dependency." >&2
  exit 1
fi

scene_references="$(git grep -l 'addons/playgodot/server.gd' -- '*.tscn' || true)"
if [[ "$scene_references" != "addons/playgodot/bootstrap.tscn" ]]; then
  echo "The PlayGodot server must only be referenced by its explicit test bootstrap." >&2
  printf 'Found: %s\n' "${scene_references:-none}" >&2
  exit 1
fi

grep -Eq 'OS\.is_debug_build\(\)' addons/playgodot/server.gd
grep -Eq -- '--playgodot' addons/playgodot/server.gd
grep -Eq 'PLAYGODOT_TOKEN' addons/playgodot/server.gd
grep -Eq 'listen\(0, "127\.0\.0\.1"\)' addons/playgodot/server.gd

runtime_log="$(mktemp "${TMPDIR:-/tmp}/cannonball-playgodot-boundary.XXXXXX")"
transcript="$(mktemp -u "${TMPDIR:-/tmp}/cannonball-playgodot-transcript.XXXXXX")"
trap 'rm -f "$runtime_log" "$transcript"' EXIT

PLAYGODOT_TOKEN=0123456789abcdef0123456789abcdef \
PLAYGODOT_TRANSCRIPT="$transcript" \
  "$repo_root/scripts/run-scenario.sh" --fixture official-corridor --smoke-test --playgodot \
  >"$runtime_log" 2>&1

if grep -Eq 'PLAYGODOT_READY|PLAYGODOT_START_FAILED' "$runtime_log" || [[ -e "$transcript" ]]; then
  echo "Normal project startup exposed a PlayGodot rendezvous or transcript surface." >&2
  sed -n '1,160p' "$runtime_log" >&2
  exit 1
fi

echo "PlayGodot normal-start boundary passed: no autoload, listener, rendezvous, or transcript."
