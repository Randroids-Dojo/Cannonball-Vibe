#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-lock \
  data/sources/continental-route-lock.json \
  --selection data/routes/continental/route-selection.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-transfers \
  data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --lock data/sources/continental-route-lock.json \
  --catalog data/sources/catalog.json

printf 'continental-route-validation-ok\n'
