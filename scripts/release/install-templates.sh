#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$repo_root/scripts/release/constants.sh"

cache_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/cannonball-godot-templates"
archive="$cache_dir/$CANNONBALL_RELEASE_TEMPLATE_ARCHIVE"
extract_dir="$cache_dir/extracted"

case "${RUNNER_OS:-$(uname -s)}" in
  Windows*) template_root="${APPDATA:?APPDATA is required}/Godot/export_templates" ;;
  Darwin*) template_root="$HOME/Library/Application Support/Godot/export_templates" ;;
  *) template_root="${XDG_DATA_HOME:-$HOME/.local/share}/godot/export_templates" ;;
esac
destination="$template_root/$CANNONBALL_RELEASE_TEMPLATE_VERSION"

mkdir -p "$cache_dir"
if [[ ! -f "$archive" ]] || \
  [[ "$(sha256sum "$archive" | awk '{print $1}')" != "$CANNONBALL_RELEASE_TEMPLATE_SHA256" ]]; then
  rm -f "$archive"
  curl --fail --location --retry 4 --output "$archive" "$CANNONBALL_RELEASE_TEMPLATE_URL"
fi
actual_sha="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$actual_sha" != "$CANNONBALL_RELEASE_TEMPLATE_SHA256" ]]; then
  echo "Godot template archive checksum mismatch: $actual_sha" >&2
  exit 1
fi

rm -rf "$extract_dir" "$destination"
mkdir -p "$extract_dir" "$destination"
unzip -q "$archive" -d "$extract_dir"
source_dir="$extract_dir/templates"
if [[ ! -d "$source_dir" ]]; then
  source_dir="$extract_dir"
fi
cp -R "$source_dir"/. "$destination"/

if [[ "$(tr -d '\r\n' < "$destination/version.txt")" != "$CANNONBALL_RELEASE_TEMPLATE_VERSION" ]]; then
  echo "Installed Godot templates do not report $CANNONBALL_RELEASE_TEMPLATE_VERSION." >&2
  exit 1
fi
for required in linux_release.x86_64 windows_release_x86_64.exe; do
  if [[ ! -f "$destination/$required" ]]; then
    echo "Installed Godot templates are missing $required." >&2
    exit 1
  fi
done

printf '%s\n' "$destination"
