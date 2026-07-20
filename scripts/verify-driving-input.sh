#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
devices=""
profiles=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --devices)
      devices="${2:-}"
      shift 2
      ;;
    --devices=*)
      devices="${1#--devices=}"
      shift
      ;;
    --profiles)
      profiles="${2:-}"
      shift 2
      ;;
    --profiles=*)
      profiles="${1#--profiles=}"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$devices" != "keyboard,controller" || "$profiles" != "all" ]]; then
  echo "Usage: $0 --devices keyboard,controller --profiles all" >&2
  exit 2
fi

cd "$repo_root"
DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --nologo \
  --filter 'FullyQualifiedName~DrivingInputConditioner'
"$repo_root/scripts/verify-playgodot.sh"
