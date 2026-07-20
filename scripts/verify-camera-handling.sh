#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--all-scenarios" ) ]]; then
  echo "Usage: $0 [--all-scenarios]" >&2
  exit 2
fi

temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/cannonball-camera-handling.XXXXXX")"
cleanup() {
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

profile_log="$temporary_directory/profile.log"
resume_log="$temporary_directory/resume.log"

CANNONBALL_GODOT_LOG_FILE="$profile_log" \
  "$repo_root/scripts/run-scenario.sh" --profile camera-handling
grep -q "CANNONBALL_CAMERA_HANDLING_OK" "$profile_log"

CANNONBALL_GODOT_LOG_FILE="$resume_log" \
  "$repo_root/scripts/run-scenario.sh" --profile camera-handling --resume-verify
grep -q "CANNONBALL_CAMERA_RESUME_OK" "$resume_log"

"$repo_root/scripts/verify-playgodot.sh" --test-filter "camera_handling or chase_camera"
