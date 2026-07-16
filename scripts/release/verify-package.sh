#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
package_root="${1:-}"
if [[ -z "$package_root" || ! -d "$package_root" ]]; then
  echo "Usage: $0 PACKAGE_DIRECTORY [--smoke]" >&2
  exit 2
fi
package_root="$(cd "$package_root" && pwd)"
smoke="${2:-}"

(cd "$package_root" && sha256sum --check metadata/SHA256SUMS)

node - "$package_root" <<'NODE'
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const root = process.argv[2];
const manifest = JSON.parse(fs.readFileSync(path.join(root, "metadata/manifest.json"), "utf8"));
if (!manifest.artifact.fixture_scoped || manifest.artifact.public_release_ready || manifest.artifact.signed) {
  throw new Error("Package scope or signing declarations are unsafe.");
}
for (const item of manifest.files) {
  const file = path.resolve(root, item.path);
  if (!file.startsWith(`${root}${path.sep}`) || !fs.existsSync(file)) throw new Error(`Missing inventory path: ${item.path}`);
  const digest = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
  if (digest !== item.sha256 || fs.statSync(file).size !== item.bytes) throw new Error(`Inventory mismatch: ${item.path}`);
  if (process.platform !== "win32") {
    const mode = (fs.statSync(file).mode & 0o777).toString(8).padStart(4, "0");
    if (mode !== item.mode) throw new Error(`Inventory mode mismatch: ${item.path}`);
  }
}
const actual = [];
function walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Package contains symlink: ${file}`);
    if (entry.isDirectory()) walk(file);
    else actual.push(path.relative(root, file).split(path.sep).join("/"));
  }
}
walk(root);
const inventoryPaths = manifest.files.map((item) => item.path).sort();
const expectedInventory = actual.filter((item) => item !== "metadata/manifest.json" && item !== "metadata/SHA256SUMS").sort();
if (JSON.stringify(inventoryPaths) !== JSON.stringify(expectedInventory)) throw new Error("Manifest inventory does not exactly cover the package.");
const checksumPaths = fs.readFileSync(path.join(root, "metadata/SHA256SUMS"), "utf8").trim().split("\n").map((line) => line.slice(66)).sort();
const expectedChecksums = actual.filter((item) => item !== "metadata/SHA256SUMS").sort();
if (JSON.stringify(checksumPaths) !== JSON.stringify(expectedChecksums)) throw new Error("SHA256SUMS does not exactly cover the package.");
if (manifest.content.unique_route_miles >= 1) throw new Error("Fixture package unexpectedly claims representative mileage.");
NODE

shipping_list="$package_root/verification/shipping-files.txt"
find "$package_root" -type f \( -name '*.pck' -o -name '*.dll' -o -name '*.exe' \) -print >"$shipping_list"
if [[ ! -s "$shipping_list" ]]; then
  echo "No shipping binaries were found." >&2
  exit 1
fi
for forbidden in PLAYGODOT_READY PLAYGODOT_TOKEN addons/playgodot bootstrap.tscn server.gd; do
  if while IFS= read -r shipping_file; do LC_ALL=C grep -a -F -i -l -- "$forbidden" "$shipping_file"; done <"$shipping_list" | grep -q .; then
    echo "Release payload contains forbidden PlayGodot marker: $forbidden" >&2
    exit 1
  fi
done
rm -f "$shipping_list"
pck_file="$(find "$package_root" -maxdepth 1 -type f -name '*.pck' -print -quit)"
if [[ -z "$pck_file" ]]; then
  echo "Release payload has no external PCK." >&2
  exit 1
fi
pck_inspector="$repo_root/scripts/release/pck-inspect.mjs"
if [[ -f "$package_root/verification/pck-inspect.mjs" ]]; then
  pck_inspector="$package_root/verification/pck-inspect.mjs"
fi
node "$pck_inspector" "$pck_file"

data_directory="$(find "$package_root" -maxdepth 1 -type d -name 'data_Cannonball*' -print -quit)"
if [[ -z "$data_directory" ]]; then
  echo "Release payload is missing the self-contained .NET data directory." >&2
  exit 1
fi
for runtime_file in Cannonball.dll Cannonball.Core.dll Cannonball.runtimeconfig.json Cannonball.deps.json System.Private.CoreLib.dll; do
  if [[ -z "$(find "$data_directory" -type f -name "$runtime_file" -print -quit)" ]]; then
    echo "Self-contained .NET payload is missing $runtime_file." >&2
    exit 1
  fi
done
if [[ -z "$(find "$data_directory" -type f \( -name 'hostfxr.dll' -o -name 'libhostfxr.so' \) -print -quit)" ]] || \
  [[ -z "$(find "$data_directory" -type f \( -name 'hostpolicy.dll' -o -name 'libhostpolicy.so' \) -print -quit)" ]]; then
  echo "Self-contained .NET payload is missing hostfxr or hostpolicy." >&2
  exit 1
fi

if [[ "$smoke" == "--smoke" ]]; then
  binary_relative="$(node -p 'require(process.argv[1]).artifact.binary' "$package_root/metadata/manifest.json")"
  launcher_relative="$(node -p 'require(process.argv[1]).artifact.launcher' "$package_root/metadata/manifest.json")"
  if [[ "$(uname -s)" != MINGW* && "$(uname -s)" != MSYS* ]] && \
    { [[ ! -x "$package_root/$binary_relative" ]] || [[ ! -x "$package_root/$launcher_relative" ]]; }; then
    echo "Linux package entrypoints are not executable as distributed." >&2
    exit 1
  fi
  smoke_script="$repo_root/scripts/release/smoke.mjs"
  if [[ -f "$package_root/verification/smoke.mjs" ]]; then
    smoke_script="$package_root/verification/smoke.mjs"
  fi
  smoke_log="$(mktemp "${TMPDIR:-/tmp}/cannonball-release-smoke.XXXXXX")"
  trap 'rm -f "$smoke_log"' EXIT
  node "$smoke_script" "$package_root" "$smoke_log"
fi

echo "CANNONBALL_PACKAGE_OK root=$package_root smoke=$([[ "$smoke" == "--smoke" ]] && echo true || echo false)"
