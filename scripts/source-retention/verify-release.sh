#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
assets_dir=""
tag=""
classify=0
self_test=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --classify-replica-trigger) classify=1; shift ;;
    --self-test) self_test=1; shift ;;
    --assets) assets_dir="$2"; shift 2 ;;
    --tag) tag="$2"; shift 2 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ $classify -eq 1 ]]; then
  node "$repo_root/scripts/source-retention/release-tools.mjs" classify --repo "$repo_root"
fi
if [[ $self_test -eq 1 ]]; then
  node "$repo_root/scripts/source-retention/release-tools.mjs" self-test
fi

cleanup=""
if [[ -n "$tag" ]]; then
  command -v gh >/dev/null || { printf 'gh is required for release verification.\n' >&2; exit 1; }
  cleanup="$(mktemp -d)"
  assets_dir="$cleanup/assets"
  mkdir -p "$assets_dir"
  gh release download "$tag" --repo Randroids-Dojo/Cannonball-Vibe --dir "$assets_dir"
fi

if [[ -n "$assets_dir" ]]; then
  reconstruct_root="${cleanup:-$(dirname "$assets_dir")}/reconstructed"
  node "$repo_root/scripts/source-retention/release-tools.mjs" verify \
    --assets "$assets_dir" --reconstruct "$reconstruct_root"
fi

if [[ -n "$tag" ]]; then
  release_json="$(gh release view "$tag" --repo Randroids-Dojo/Cannonball-Vibe --json isDraft,isImmutable,tagName)"
  is_draft="$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(String(x.isDraft))' "$release_json")"
  is_immutable="$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(String(x.isImmutable))' "$release_json")"
  if [[ "$is_draft" != true && "$is_immutable" != true ]]; then
    printf 'Published release is not immutable: %s\n' "$tag" >&2
    exit 1
  fi
  if [[ "$is_draft" != true ]]; then
    while IFS= read -r asset; do
      verified=0
      for attempt in 1 2 3 4 5 6; do
        if gh release verify-asset "$tag" "$assets_dir/$asset" --repo Randroids-Dojo/Cannonball-Vibe >/dev/null 2>&1; then
          verified=1
          break
        fi
        if [[ $attempt -lt 6 ]]; then sleep 5; fi
      done
      if [[ $verified -ne 1 ]]; then
        printf 'Release attestation verification failed: %s\n' "$asset" >&2
        exit 1
      fi
    done < <(find "$assets_dir" -maxdepth 1 -type f -exec basename {} \; | sort)
  fi
  rm -rf "$cleanup"
  printf 'release-ok: %s (draft=%s immutable=%s)\n' "$tag" "$is_draft" "$is_immutable"
fi

if [[ $classify -eq 0 && $self_test -eq 0 && -z "$assets_dir" ]]; then
  printf 'Usage: %s [--classify-replica-trigger] [--self-test] [--assets DIR | --tag TAG]\n' "$0" >&2
  exit 2
fi
