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
  --source route.gpkg --manifest route.manifest.json \
  --elevation corridor.tif --elevation-metadata corridor.metadata.json \
  --acquisition-lock data/sources/source-lock.json --output data/processed
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

`build` requires `--elevation`, `--elevation-metadata`, and
`--acquisition-lock`. Route samples are transformed into the locked raster CRS,
sampled from 3DEP, and assigned signed grade. The shipping schema-5 FlatBuffer
preserves the route and elevation CRS, horizontal and vertical datums, product
identity, artifact hashes, elevations, and grades for the portable C# runtime.

Schema 5 also carries the route-semantic contract:

- ordered distance-bounded lane sections, stable lane IDs, lane roles,
  maneuver masks, shoulders, signed direction, and provenance;
- explicit lane connectors for continuation, merge, split, exit, entrance, and
  highway-transfer movement;
- route identities, exits, destinations, services, milepoint anchors, and
  roadside markers;
- independently hashed simplified map geometry at LODs 0–2 for every edge.
- explicit reciprocal divided-carriageway pairs and unpaired one-way roadway
  kinds.

Approved sources or authored overlays may provide `ROADWAY_KIND`,
`CARRIAGEWAY_ID`, and `OPPOSING_ID`. `OPPOSING_ID` names the stable source
feature on the reverse carriageway. A divided pair must resolve uniquely in the
same package, share `CARRIAGEWAY_ID`, and declare opposite signed directions;
the pipeline rejects incomplete metadata instead of pairing nearby geometry.

Validation fails on section gaps or overlaps, invalid provenance, orphan lanes,
crossing or ambiguous connectors, disallowed connector movements, invalid
route-context placement, missing map LODs, hash drift, and the 16 MB simplified
map or 64 MB root budgets. `Cannonball.Core` performs corresponding validation
when it reads the FlatBuffer.

NHPN does not contain authoritative lane geometry. The default build therefore
labels its two-lane sections, shoulders, and index-preserving connectors as
deterministic `derived` graybox data. It preserves route-system hints and source
BEGMP/ENDMP milepoints without presenting those defaults as surveyed lanes or
signage. Corrected lanes and exits must use an approved source or an authored
overlay with a stable override ID and recursive source ancestry under Q-017.

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

The normalized GeoPackage contains `route_*` semantic audit tables alongside
`route_edges`. Each table stores stable record IDs and canonical JSON payloads.
The shipping FlatBuffer, every `CBCK` chunk, and published audit artifacts are
content-addressed; two locked builds must reproduce identical shipping bytes and
equivalent normalized GeoPackage content before reproducibility is claimed.

The representative contract matrix is
`data/routes/fixtures/semantics/representative-contract.json`. It locks the
official fixture inputs and enumerates movement, context, map-LOD, migration,
and malformed-data coverage. Its synthetic junction data is contract evidence,
not a claim about real-world I-70 geometry.

Local JSONL telemetry can be summarized without a service:

~~~
uv run cannonball-map telemetry-summary --telemetry /path/to/prototype.jsonl
~~~
