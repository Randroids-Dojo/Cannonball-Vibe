#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
repo="Randroids-Dojo/Cannonball-Vibe"
mode="draft"
approval_reference=""
output_root="${CANNONBALL_SOURCE_RELEASE_DIR:-$repo_root/.tools/source-retention/release}"
cache_root="${CANNONBALL_SOURCE_CACHE_DIR:-$repo_root/.tools/source-retention/cache}"
part_size="${CANNONBALL_SOURCE_PART_SIZE:-1900000000}"
allow_unverified_immutable_setting_for_draft=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --draft) mode="draft"; shift ;;
    --publish) mode="publish"; shift ;;
    --approval-reference) approval_reference="$2"; shift 2 ;;
    --output) output_root="$2"; shift 2 ;;
    --cache) cache_root="$2"; shift 2 ;;
    --part-size) part_size="$2"; shift 2 ;;
    --allow-unverified-immutable-setting-for-draft)
      allow_unverified_immutable_setting_for_draft=1
      shift
      ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

command -v gh >/dev/null || { printf 'gh is required.\n' >&2; exit 1; }
command -v node >/dev/null || { printf 'node is required.\n' >&2; exit 1; }
if [[ "$mode" == publish && -z "$approval_reference" ]]; then
  printf 'Immutable publication requires --approval-reference with the recorded owner approval.\n' >&2
  exit 2
fi

immutable=""
if immutable="$(gh api -H 'X-GitHub-Api-Version: 2026-03-10' "repos/$repo/immutable-releases" --jq .enabled 2>/dev/null)"; then
  if [[ "$immutable" != true ]]; then
    printf 'Immutable releases are not enabled for %s.\n' "$repo" >&2
    exit 1
  fi
elif [[ "$mode" == draft && $allow_unverified_immutable_setting_for_draft -eq 1 && "${GITHUB_ACTIONS:-}" == true ]]; then
  printf 'warning: Actions token cannot read the immutable-release setting; draft-only preparation may continue.\n' >&2
else
  printf 'Unable to verify the immutable-release setting for %s; refusing %s.\n' "$repo" "$mode" >&2
  exit 1
fi

revision="$(git -C "$repo_root" rev-parse HEAD)"
source_date="$(git -C "$repo_root" show -s --format=%cI HEAD)"
node "$repo_root/scripts/source-retention/release-tools.mjs" prepare \
  --repo "$repo_root" \
  --output "$output_root" \
  --cache "$cache_root" \
  --part-size "$part_size" \
  --revision "$revision" \
  --source-date "$source_date"

tag="$(node -p 'require(process.argv[1]).release_tag' "$output_root/result.json")"
manifest_sha="$(node -p 'require(process.argv[1]).manifest_sha256' "$output_root/result.json")"
notes="$output_root/release-notes.md"
{
  printf '# Cannonball source lock %s\n\n' "$tag"
  printf 'Authoritative content-addressed source retention package for repository revision %s.\n\n' "$revision"
  printf -- '- Manifest SHA-256: %s\n' "$manifest_sha"
  printf -- '- Policy: ADR-0006; recovery classification: ADR-0010\n'
  printf -- '- Sources: public-domain USDOT NHPN and USGS 3DEP\n'
  printf -- '- No agency endorsement is implied.\n'
  if [[ -n "$approval_reference" ]]; then
    printf -- '- Publication approval: %s\n' "$approval_reference"
  fi
} > "$notes"

if ! gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
  gh release create "$tag" --repo "$repo" --draft --target "$revision" \
    --title "Cannonball source lock ${tag#source-lock-v1-}" --notes-file "$notes"
fi

existing="$output_root/existing-assets.txt"
gh release view "$tag" --repo "$repo" --json assets --jq '.assets[].name' | sort > "$existing"
while IFS= read -r asset; do
  name="$(basename "$asset")"
  if ! grep -Fxq "$name" "$existing"; then
    gh release upload "$tag" "$asset" --repo "$repo"
  fi
done < <(find "$output_root/assets" -maxdepth 1 -type f | sort)

"$repo_root/scripts/source-retention/verify-release.sh" --tag "$tag"

if [[ "$mode" == publish ]]; then
  release_json="$(gh release view "$tag" --repo "$repo" --json isDraft,isImmutable)"
  is_draft="$(node -e 'process.stdout.write(String(JSON.parse(process.argv[1]).isDraft))' "$release_json")"
  if [[ "$is_draft" == true ]]; then
    gh release edit "$tag" --repo "$repo" --draft=false --notes-file "$notes"
  fi
  "$repo_root/scripts/source-retention/verify-release.sh" --tag "$tag"
fi

gh release view "$tag" --repo "$repo" --json tagName,isDraft,isImmutable,publishedAt,url > "$output_root/github-release.json"
printf 'source-release-ok: %s (%s)\n' "$tag" "$mode"
