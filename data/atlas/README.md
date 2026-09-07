# Atlas dataset intake

P1-016's offline pipeline acquires approved source snapshots, normalizes records,
and reports coverage against independent inventories. Its outputs are audit and
compiler interchange data, not runtime tiles. [ADR-0028](../../docs/decisions/ADR-0028-atlas-data-intake-and-coverage.md)
defines the boundary. The existing approved source catalog is unchanged.

## Run the continental gap report

From the repository root, with the pinned toolchain:

```bash
uv run --project tools/map_pipeline --frozen cannonball-map atlas audit \
  data/atlas/continental-job.v1.json --output reports/atlas/continental
uv run --project tools/map_pipeline --frozen cannonball-map atlas verify \
  reports/atlas/continental
```

`audit` returns 0 for complete coverage, 2 for a successfully produced report
with gaps, and 1 for an invalid job or failed operation. `verify` checks output
integrity, not production readiness. A failed invocation does not supersede a
previous successful report; callers must check its exit status and job hash.

The starter report deliberately returns 2. It names all 15 selected segments and
seven feature kinds (105 cells), without fabricating corridor masks, inventories,
observations or source permission. These are gaps in the new atlas intake job,
not a claim that the existing game has no road geometry. `as_of` is a pinned audit
date; reruns do not silently become a current-world survey.

## Inputs and contracts (version 1)

| File | Contract |
| --- | --- |
| `datasets.v1.json` | Candidate profiles, source identity, exact field mappings, adapter, CRS, source-specific age bound and admission notes. Only the approved catalog grants source admission. Discovery/translation templates need exact product URLs and mappings before use. |
| `continental-scope.v1.json` | Every selected segment, required feature kinds/fields, optional reviewed EPSG:4326 Polygon/MultiPolygon corridor mask, and route-selection SHA-256. Masks filter intake; they do not establish road connectivity. |
| `continental-job.v1.json` | Explicit audit date; locked catalog, profiles, route selection and scope; artifact-bundle references; active datasets; independent inventories; optional reviewed entity/access bindings. |
| Acquired `artifacts.json` | Raw and derived input descriptors with IDs, paths, SHA-256, source/catalog identity, canonical URL, UTC acquisition time, observation date or null, response metadata and recursive parent IDs. Paths resolve relative to the bundle. |

Only include the chosen datasets in a production candidate job's `datasets`
array. The starter includes every research candidate so their blocks are visible;
admitting every alternative is not required. Profiles remain available in each
coverage cell's `candidate_profiles`, including profiles not yet acquired.

All config documents require `schema_version: 1`. The parser rejects repeated
JSON keys and non-finite JSON numbers. Input locks cover bytes, not labels.
`atlas lock JOB.json` explicitly updates input hashes after edits; it neither
approves a source nor updates the scope's route-policy binding. A changed route
policy requires reviewing the scope first. Catalog edits therefore also require
updating this job's catalog hash, alongside existing dependent route locks.

## Acquire and attach a source

For example, this bounded NHPN record is in the selected I-70 candidate lock:

```bash
uv run --project tools/map_pipeline --frozen cannonball-map atlas acquire \
  nhpn-road-context --where 'OBJECTID=38283' --output .tools/atlas/nhpn
```

This is coarse road-context evidence only. NHPN is explicitly prevented from
becoming an observed exit/service source. Imagery and elevation continue through
their existing specialized pipeline and are not reinterpreted as semantic POIs.

Acquisition prints the bundle path, SHA-256 and dataset artifact ID. Add a locked
bundle reference to the job's `artifact_manifests`, set the matching dataset's
`artifact_id`, set an appropriate `as_of` date, then run `atlas lock` and `audit`.
Keep custom jobs and downloads in `.tools/atlas/`; make their input paths relative
to the job's directory. Never commit downloaded source files or generated output.

Acquisition checks catalog identity/license before any network request. HTTPS
requests and redirects must stay within approved URL prefixes. ArcGIS uses an
explicit nontrivial route/corridor predicate, a reconciled count and unique ID
snapshot, bounded ID pages, and before/after schema and available edit-stamp
checks. Page caches are keyed by the source edition, query, profile, catalog and
ID set. When no edit stamp is available, pages are fetched again. Incomplete
pages are not cached as successful responses. Transient failures receive bounded
retries; generic URL acquisitions refresh the response. Offline audits never
contact the provider and replay the locked bundle.

Each raw artifact and decoded JSON/text input is capped at 64 MiB; each dataset
at 100,000 records; ArcGIS pages at 500 records or the provider's smaller limit.
Large national files must be acquired/subset through the existing offline
geodata tooling, with full recursive provenance, into bounded intake artifacts.
This module does not promise a server-side transactional snapshot: same-ID edits
without an exposed edit stamp can evade before/after detection. Preserve the
actual response bytes and acquisition timing for reconciliation.

`--observed-on YYYY-MM-DD` is optional and must come from source evidence.
Never pass today's date just because a file was downloaded today. Record-level
date fields take precedence. A year-only observation retains that precision;
freshness uses January 1 conservatively and never labels it as a surveyed day.
Absent dates, old dates and future observations remain visible gaps.

## Adapters

| Adapter | Accepted input and behavior |
| --- | --- |
| `geojson` | FeatureCollection with property-based stable ID; validates declared CRS and geometry. |
| `arcgis` | Complete JSON feature response; point or polyline geometry, explicit CRS. Polygon exports should use GeoJSON. Acquisition emits EPSG:4326. Truncation/error responses fail. |
| `csv` | UTF-8/BOM text; configurable one-character delimiter, including GNIS pipe files; optional longitude/latitude columns. Missing coordinates remain unlocated records. |
| `ndjson` | One GeoJSON feature per line. JSON/text inputs may be gzip compressed; decoded byte bounds still apply. |
| `geopackage` | Explicit layer and CRS, read through GeoPandas/pyogrio with bounded rows. |
| `geoparquet` | Bounded local Parquet with a WKB geometry column, read through DuckDB. Declared GeoParquet CRS is checked; plain WKB Parquet requires an explicit profile CRS. |

Field mappings use case-sensitive property names and dotted paths, including
array indices (for example `names.primary`). Exit suffixes and leading zeros
are retained. Values, value classes, record IDs, artifact hashes, observation
date and segment assignment are emitted separately. Empty strings/containers
remain unknown. No fuzzy deduplication, name matching, exit-number generation or
direction inference occurs. Exact duplicates collapse; inconsistent duplicates
are excluded. Explicitly bound entities with disagreeing values or geometry are
reported as conflicts.

PDF/HTML inventories use reviewed CSV transcriptions rather than automatic OCR.
Their profiles have `acquisition_mode: manual_reviewed_export`. Retain the exact
approved original PDF/page or HTML snapshot as an acquired ancestor, and make
the CSV a derived/authored artifact with a process/review reference and page/row
identifiers. Retain every intermediary artifact in the graph. A transcription
does not cleanse incompatible rights or ancestry. Overture and contextual
national-product profiles are also bounded-export templates, not web-page
download adapters. Their exact release mappings must be checked before admission.

## Coverage and reconciliation

Each job inventory entry binds `(segment_id, kind)` to a validated artifact whose
JSON payload looks like this **synthetic example**:

```json
{
  "schema_version": 1,
  "segment_id": "example-segment",
  "kind": "exit",
  "complete": true,
  "review_reference": "review-record-of-independent-exit-list",
  "entities": [{"id": "example-exit-1"}]
}
```

The inventory artifact needs provenance and an observation date just like data.
Its acquired source roots must be independent of the contributing feature
artifacts: counting downloaded records cannot establish the denominator.
Unreviewed, incomplete, stale, duplicated or related-source inventories remain
unknown. A reviewed empty inventory explicitly establishes that no features of
that kind are required; a missing inventory does not. Inventory entities may
include verified GeoJSON geometry to locate absent features in `gaps.geojson`.

Default entity IDs are `profile_id:source_record_id`. To reconcile providers,
add a job binding with `profile_id`, `record_id`, `segment_id`, `entity_id` and a
`review_reference`. A binding cannot move a located record outside its corridor
mask or source jurisdiction. Missing masks and unlocated records never prove
coverage. Polygon intersection is only a search/inclusion test.

A required `access` field is satisfied only by a binding's `access` object with
`artifact_id`, `record_reference` and `review_reference`; the evidence artifact
must pass provenance validation. A source text field called `access` or a nearby
business point cannot satisfy that gate. This records documentary access evidence;
playable edge/entrance integration remains a separate route-geometry gate.

The report retains unmatched normalized records for investigation. A coverage
cell counts only expected inventory entities, and reports both present entities
and entities with all required usable fields. Conflicts, stale/unknown dates,
missing locations and missing access cannot inflate the complete count.

## Outputs

- `report.md`: source dispositions, segment/kind coverage matrix, detailed gaps.
- `coverage.json`: the same machine-readable result, input hashes and verified
  recursive artifact descriptors.
- `features.jsonl` and `features.geojson`: normalized records with provenance and
  quality issues. These include incomplete audit candidates; downstream shipping
  compilation must gate on coverage and source disposition.
- `gaps.csv` and `gaps.geojson`: stable gap IDs, segment/kind/entity/field, reason,
  and known geometry; unknown locations remain null.
- `manifest.json`: input hashes and SHA-256 of every output, written last.

Locked offline builds produce identical bytes across output directories. These
outputs do not change route position, approved source catalogs, lane/edge locks,
runtime FlatBuffers, or the map renderer. Source rights and production coverage
remain tracked in Q-045.
