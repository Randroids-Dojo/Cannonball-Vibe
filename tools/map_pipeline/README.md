# Cannonball map pipeline

This tool turns an explicitly approved public-domain line dataset into three
artifacts:

- `normalized.gpkg` for GIS inspection and corrections;
- `route_graph.json` for audits and diffs;
- `route_graph.cbrg` for the game runtime.

Every source file needs a sidecar manifest:

```json
{
  "source_id": "usdot-national-highway-planning-network",
  "publisher": "U.S. Department of Transportation",
  "source_url": "https://services.arcgis.com/.../FeatureServer/0/query?objectIds=...",
  "acquired_on": "2026-07-16",
  "license_status": "public_domain",
  "license_evidence_url": "https://services.arcgis.com/.../FeatureServer/0",
  "sha256": "64-lowercase-hex-characters",
  "derived_from": []
}
```

Build with:

```bash
uv sync --project tools/map_pipeline --locked
uv run --project tools/map_pipeline cannonball-map validate-lock data/sources/source-lock.json
uv run --project tools/map_pipeline cannonball-map validate-source \
  --source route.gpkg --manifest route.manifest.json
uv run --project tools/map_pipeline cannonball-map build \
  --source route.gpkg --manifest route.manifest.json --output data/processed
```

`source-lock.json` pins the NHPN service/layer, sorted OBJECTID snapshot and
count, the exact 3DEP product edition, remote artifact hashes, CRS and datums,
and every checked-in corridor artifact. `validate-lock` is deliberately offline:
it performs no ArcGIS or TNM discovery and rejects local hash drift. Locked
remote rebuilds accept an exact URL plus SHA-256 only.

Rebuild any raw or derived locked artifact without discovery:

```bash
uv run --project tools/map_pipeline cannonball-map materialize-lock \
  data/sources/source-lock.json --role official-corridor-geojson \
  --output /tmp/nhpn-corridor.geojson
```

Raw downloads are verified before use. Derived JSON and raster windows are
rebuilt recursively from their locked ancestors and deterministic recipes, then
verified against their own SHA-256 values.

NHPN acquisition snapshots and sorts IDs before fetching pages of at most 2,000
features. Page checkpoints are request- and response-hashed, so an interrupted
run can resume without trusting partial output. Retryable transport and service
errors are bounded; counts, IDs, page membership, duplicates, and final feature
counts must reconcile.

When `build` receives `--elevation`, `--elevation-metadata`, and
`--acquisition-lock`, route samples are transformed into the locked raster CRS,
sampled from 3DEP, and assigned signed grade. The schema-2 FlatBuffer preserves
the route and elevation CRS, horizontal and vertical datums, product identity,
artifact hashes, elevations, and grades for the portable C# runtime.

Multi-edge linear corridors apply a deterministic nine-sample median and a
route-wide 7 percent grade projection to reject localized 3DEP surface-model
spikes without changing source provenance. Shared edge endpoints remain equal.
Branched elevation graphs that already satisfy the ceiling remain raw; a branch
that exceeds it fails closed until branch-aware conditioning is implemented.

The pipeline fails closed on sources not in the catalog, catalog identity or URL
drift, unknown licenses, OpenStreetMap ancestry, malformed
dates, missing hashes, changed files, disconnected selected geometry, and exact
duplicate edge IDs. It preserves parallel directed edges in a multigraph.

Source features should expose a stable `source_feature_id`, `source_id`, `id`,
or `OBJECTID` attribute. The normalized GeoPackage and audit JSON retain it as
`source_feature_id` on the complete sorted edge record, distinct from the
dataset-level manifest `source_id`. The build fails closed when none of those
fields exists. Edge identity includes both the dataset and feature identifiers.

Reordering features changes the acquired source bytes and therefore may change
the provenance SHA-256 and `content_version`. Semantic order invariance applies
to the sorted nodes, edges, chunks, and normalized GeoPackage rows; those
records remain equivalent independent of input feature order.

Local JSONL telemetry can be summarized without a service:

~~~
uv run cannonball-map telemetry-summary --telemetry /path/to/prototype.jsonl
~~~
