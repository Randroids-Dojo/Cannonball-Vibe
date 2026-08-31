#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/tool-versions.sh"
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

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-edge-paths \
  data/routes/continental/edge-path-lock.v1.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-nhs-fills \
  data/routes/continental/nhs-fill-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-break-dispositions \
  data/routes/continental/break-disposition.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --nhs-fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-reconstruction-overlays \
  data/routes/continental/reconstruction-overlay-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --nhs-fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-nhs-conflation \
  data/routes/continental/nhs-conflation-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-3dep-products \
  data/routes/continental/3dep-product-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-directed-route \
  data/routes/continental/directed-route-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --conflation-lock data/routes/continental/nhs-conflation-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-corridor-elevation \
  data/routes/continental/corridor-elevation-lock.v1.json \
  --dem-lock data/routes/continental/3dep-product-lock.v1.json \
  --directed-lock data/routes/continental/directed-route-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --conflation-lock data/routes/continental/nhs-conflation-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-conditioned-profile \
  data/routes/continental/conditioned-profile-lock.v1.json \
  --elevation-lock data/routes/continental/corridor-elevation-lock.v1.json \
  --dem-lock data/routes/continental/3dep-product-lock.v1.json \
  --directed-lock data/routes/continental/directed-route-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --conflation-lock data/routes/continental/nhs-conflation-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-endpoint-connectors \
  data/routes/continental/endpoint-connector-lock.v1.json \
  --directed-lock data/routes/continental/directed-route-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --conflation-lock data/routes/continental/nhs-conflation-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-westbound-carriageway \
  data/routes/continental/westbound-carriageway-lock.v1.json \
  --conditioned-lock data/routes/continental/conditioned-profile-lock.v1.json \
  --elevation-lock data/routes/continental/corridor-elevation-lock.v1.json \
  --dem-lock data/routes/continental/3dep-product-lock.v1.json \
  --directed-lock data/routes/continental/directed-route-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --conflation-lock data/routes/continental/nhs-conflation-lock.v1.json \
  --connector-lock data/routes/continental/endpoint-connector-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-junction-geometry \
  data/routes/continental/junction-geometry-lock.v1.json \
  --carriageway-lock data/routes/continental/westbound-carriageway-lock.v1.json \
  --conditioned-lock data/routes/continental/conditioned-profile-lock.v1.json \
  --elevation-lock data/routes/continental/corridor-elevation-lock.v1.json \
  --dem-lock data/routes/continental/3dep-product-lock.v1.json \
  --directed-lock data/routes/continental/directed-route-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --conflation-lock data/routes/continental/nhs-conflation-lock.v1.json \
  --connector-lock data/routes/continental/endpoint-connector-lock.v1.json \
  --catalog data/sources/catalog.json

uv run --project tools/map_pipeline --frozen \
  cannonball-map validate-continental-lane-topology \
  data/routes/continental/lane-topology-lock.v1.json \
  --junction-lock data/routes/continental/junction-geometry-lock.v1.json \
  --carriageway-lock data/routes/continental/westbound-carriageway-lock.v1.json \
  --conditioned-lock data/routes/continental/conditioned-profile-lock.v1.json \
  --elevation-lock data/routes/continental/corridor-elevation-lock.v1.json \
  --dem-lock data/routes/continental/3dep-product-lock.v1.json \
  --directed-lock data/routes/continental/directed-route-lock.v1.json \
  --selection data/routes/continental/route-selection.v1.json \
  --route-lock data/sources/continental-route-lock.json \
  --transfer-lock data/routes/continental/transfer-node-lock.v1.json \
  --policy data/routes/continental/transfer-node-policy.v1.json \
  --edge-path-lock data/routes/continental/edge-path-lock.v1.json \
  --fill-lock data/routes/continental/nhs-fill-lock.v1.json \
  --disposition data/routes/continental/break-disposition.v1.json \
  --overlay-lock data/routes/continental/reconstruction-overlay-lock.v1.json \
  --conflation-lock data/routes/continental/nhs-conflation-lock.v1.json \
  --connector-lock data/routes/continental/endpoint-connector-lock.v1.json \
  --catalog data/sources/catalog.json

printf 'continental-route-validation-ok\n'
