#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$repo_root/scripts/release/constants.sh"
cd "$repo_root"

target="${1:-all}"
output_root="${2:-$repo_root/reports/unsigned-exports}"
case "$target" in linux|windows|all) ;; *) echo "Usage: $0 [linux|windows|all] [OUTPUT_DIRECTORY]" >&2; exit 2 ;; esac

godot_bin="${GODOT_BIN:-$(command -v godot || command -v godot4 || true)}"
if [[ -z "$godot_bin" || ! -x "$godot_bin" ]]; then
  echo "Set GODOT_BIN to the official Godot 4.7.1 Mono executable." >&2
  exit 1
fi
actual_godot="$($godot_bin --version | tr -d '\r\n')"
if [[ "$actual_godot" != "$CANNONBALL_RELEASE_GODOT_VERSION" ]]; then
  echo "Godot version mismatch: expected $CANNONBALL_RELEASE_GODOT_VERSION, got $actual_godot" >&2
  exit 1
fi
[[ "$(dotnet --version)" == "$CANNONBALL_RELEASE_DOTNET_VERSION" ]] || { echo "dotnet version mismatch" >&2; exit 1; }
[[ "$(uv --version | awk '{print $2}')" == "$CANNONBALL_RELEASE_UV_VERSION" ]] || { echo "uv version mismatch" >&2; exit 1; }
[[ "$(node --version | sed 's/^v//')" == "$CANNONBALL_RELEASE_NODE_VERSION" ]] || { echo "Node.js version mismatch" >&2; exit 1; }
python_bin="${PYTHON_BIN:-python3}"
[[ "$($python_bin -c 'import platform; print(platform.python_version())')" == "$CANNONBALL_RELEASE_PYTHON_VERSION" ]] || { echo "Python version mismatch" >&2; exit 1; }
revision="${SOURCE_REVISION:-$(git rev-parse HEAD)}"
[[ "$revision" == "$(git rev-parse HEAD)" ]] || { echo "SOURCE_REVISION must equal the checked-out HEAD." >&2; exit 1; }
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "Release builds require a clean source tree so provenance cannot omit local changes." >&2
  exit 1
fi
epoch="${SOURCE_DATE_EPOCH:-}"
if [[ -z "$epoch" ]]; then epoch="$(git show -s --format=%ct "$revision")"; fi
mkdir -p "$output_root"
export RestoreLockedMode=true ContinuousIntegrationBuild=true DOTNET_CLI_TELEMETRY_OPTOUT=1 NUGET_XMLDOC_MODE=skip
export TZ=UTC LC_ALL=C

build_fixture() {
  local source_root="$1" destination="$2"
  uv run --project "$source_root/tools/map_pipeline" --frozen cannonball-map build \
    --source "$source_root/data/sources/fixtures/nhpn-boulder-us36.geojson" \
    --manifest "$source_root/data/sources/fixtures/nhpn-boulder-us36.manifest.json" \
    --catalog "$source_root/data/sources/catalog.json" \
    --elevation "$source_root/data/sources/fixtures/usgs-13-n40w106-boulder.tif" \
    --elevation-metadata "$source_root/data/sources/fixtures/usgs-13-n40w106-boulder.metadata.json" \
    --acquisition-lock "$source_root/data/sources/source-lock.json" \
    --chunk-meters 100 --output "$destination"
}

build_once() {
  local platform="$1" iteration="$2"
  local stage="$output_root/work/$platform-$iteration"
  local preset binary launcher windows_route runtime_id target_platform source_root export_path
  rm -rf "$stage"
  source_root="$stage/source"
  mkdir -p "$stage/package/content/official-corridor" "$stage/package/verification" "$stage/fixture" "$source_root"
  git archive "$revision" | tar -x -C "$source_root"
  if [[ "$platform" == linux ]]; then
    preset="Linux x86_64"; binary="CannonballRun.x86_64"; launcher="run-cannonball.sh"; runtime_id="linux-x64"; target_platform="linuxbsd"
  else
    preset="Windows x86_64"; binary="CannonballRun.console.exe"; launcher="run-cannonball.cmd"; runtime_id="win-x64"; target_platform="windows"
  fi
  cp "$source_root/packages.$runtime_id.lock.json" "$source_root/packages.lock.json"
  cp "$source_root/src/Cannonball.Core/packages.$runtime_id.lock.json" "$source_root/src/Cannonball.Core/packages.lock.json"
  RuntimeIdentifiers="$runtime_id" dotnet restore "$source_root/Cannonball.csproj" --locked-mode --nologo -p:Configuration=Release -p:GodotTargetPlatform="$target_platform"
  RuntimeIdentifiers="$runtime_id" dotnet build "$source_root/Cannonball.csproj" -c Release --no-restore --nologo -p:GodotTargetPlatform="$target_platform"
  export_path="$stage/package/CannonballRun${platform/linux/.x86_64}"
  if [[ "$platform" == windows ]]; then export_path="$stage/package/CannonballRun.exe"; fi
  RuntimeIdentifiers="$runtime_id" "$godot_bin" --headless --path "$source_root" --export-release "$preset" "$export_path"
  build_fixture "$source_root" "$stage/fixture"
  node "$source_root/scripts/release/package-tools.mjs" copy-content "$stage/fixture" "$stage/package/content/official-corridor"
  route_relative="$(node -p 'require(process.argv[1]).root_relative_path' "$stage/package/content/official-corridor/current-package.json")"
  if [[ "$platform" == linux ]]; then
    {
      printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail'
      # shellcheck disable=SC2016 # Expansion belongs in the generated launcher.
      printf '%s\n' 'root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"'
      # shellcheck disable=SC2016 # Expansion belongs in the generated launcher.
      printf '%s\n' 'engine_args=()' 'if [[ "${CANNONBALL_RELEASE_SMOKE:-}" == "1" ]]; then engine_args=(--headless --rendering-method gl_compatibility --quit-after 1200); fi'
      # shellcheck disable=SC2016 # Expansion belongs in the generated launcher.
      printf 'exec "$root/CannonballRun.x86_64" "${engine_args[@]}" -- "--route-package=$root/content/official-corridor/%s" "$@"\n' "$route_relative"
    } >"$stage/package/$launcher"
    chmod +x "$stage/package/$launcher" "$stage/package/$binary"
  else
    windows_route="${route_relative//\//\\}"
    printf '@echo off\r\nset "ROOT=%%~dp0"\r\nif "%%CANNONBALL_RELEASE_SMOKE%%"=="1" (\r\n  "%%ROOT%%CannonballRun.console.exe" --headless --rendering-method gl_compatibility --quit-after 1200 -- "--route-package=%%ROOT%%content\\official-corridor\\%s" %%*\r\n) else (\r\n  "%%ROOT%%CannonballRun.exe" -- "--route-package=%%ROOT%%content\\official-corridor\\%s" %%*\r\n)\r\n' \
      "$windows_route" "$windows_route" >"$stage/package/$launcher"
  fi
  cp "$source_root/scripts/release/smoke.mjs" "$source_root/scripts/release/pck-inspect.mjs" \
    "$source_root/scripts/release/verify-package.sh" "$stage/package/verification/"
  node "$source_root/scripts/release/package-tools.mjs" metadata "$stage/package" "$source_root" "$platform" "$revision" "$epoch" "$preset" "$binary" "$launcher" \
    "$CANNONBALL_RELEASE_TEMPLATE_SHA256" "$CANNONBALL_RELEASE_TEMPLATE_VERSION" "$CANNONBALL_RELEASE_GODOT_VERSION" \
    "$CANNONBALL_RELEASE_DOTNET_VERSION" "$CANNONBALL_RELEASE_RUNTIME_VERSION" "$CANNONBALL_RELEASE_UV_VERSION" \
    "$CANNONBALL_RELEASE_NODE_VERSION" "$CANNONBALL_RELEASE_PYTHON_VERSION"
  "$source_root/scripts/release/verify-package.sh" "$stage/package"
  "$python_bin" "$source_root/scripts/release/archive.py" "$stage/package" "Cannonball-$platform-x86_64" "$stage/Cannonball-$platform-x86_64.zip"
}

build_target() {
  local platform="$1"
  local final_dir="$output_root/$platform"
  build_once "$platform" 1
  build_once "$platform" 2
  diff -qr "$output_root/work/$platform-1/package" "$output_root/work/$platform-2/package"
  first_sha="$(sha256sum "$output_root/work/$platform-1/Cannonball-$platform-x86_64.zip" | awk '{print $1}')"
  second_sha="$(sha256sum "$output_root/work/$platform-2/Cannonball-$platform-x86_64.zip" | awk '{print $1}')"
  [[ "$first_sha" == "$second_sha" ]] || { echo "Archive reproducibility mismatch for $platform" >&2; exit 1; }
  rm -rf "$final_dir"; mkdir -p "$final_dir"
  archive="$final_dir/Cannonball-$platform-x86_64-$first_sha.zip"
  cp "$output_root/work/$platform-1/Cannonball-$platform-x86_64.zip" "$archive"
  printf '%s  %s\n' "$first_sha" "$(basename "$archive")" >"$archive.sha256"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf '%s_archive=%s\n%s_sha=%s\n' "$platform" "$archive" "$platform" "$first_sha" >>"$GITHUB_OUTPUT"
  fi
  echo "CANNONBALL_REPRODUCIBLE_EXPORT_OK platform=$platform sha256=$first_sha archive=$archive"
}

if [[ "$target" == all || "$target" == linux ]]; then
  build_target linux
fi
if [[ "$target" == all || "$target" == windows ]]; then
  build_target windows
fi
