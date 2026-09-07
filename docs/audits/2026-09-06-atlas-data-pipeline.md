# P1-016: Atlas dataset intake and gap reporting

- Date: 2026-09-06 local / 2026-09-07 UTC
- Claim: PR #139, `feat/P1-016-atlas-data-pipeline`
- Decision: [ADR-0028](../decisions/ADR-0028-atlas-data-intake-and-coverage.md)
- Owner request: build incorporation, validation, and explicit gap reporting for
  the researched map datasets.
- Evidence: [P1-016-data-pipeline.json](../../evidence/M3/P1-016-data-pipeline.json)

## Delivered behavior

`cannonball-map atlas` provides `acquire`, `lock`, `audit` and `verify` commands.
The [workflow and v1 contracts](../../data/atlas/README.md) document bounded
snapshots, recursive source validation, six adapters, reviewed ID reconciliation,
source age, required fields and independent coverage inventories.

Candidate profiles preserve the researched endpoints and field mappings for
Utah, Colorado, Pennsylvania and Iowa, plus business, operator, transcription
and contextual-product templates. They are separate from source admission.
The existing approved catalog and route locks are byte-unchanged. Public-domain
claims awaiting an exact product lock, permissive sources, and uncertain rights
remain blocked; the pipeline neither guesses permission nor imports OSM ancestry.

Every selected policy segment appears in the starter job. Required exit,
service, place, water, boundary, road and toll information is assessed separately.
Geometry masks, inventories, source data and source rights have distinct gaps.
Normalized records preserve provenance, original IDs, semantic value classes,
observation dates and unknowns. Same-ID conflicts are quarantined even if one
duplicate lies outside a mask. Explicit cross-source bindings expose value and
geometry conflicts. No source wins through ordering.

## Quantitative checks

| Exercise | Result |
| --- | --- |
| Focused fixture suite | 59 tests pass on Windows, including all six formats, negative provenance/ancestry cases, CRS and semantic type checks, stale/unknown dates, partial-page recovery, source-edition changes, missing fields, independent/empty inventories, documentary access evidence and CLI exit status. |
| Continental starter | 15 policy segments, 105 segment/kind cells, 135 explicit gaps, no fabricated features. All 105 denominators remain null. |
| Approved live source | NHPN OBJECTID 38283, selected I-70 candidate source record, acquired through the new bounded ArcGIS path with no retries. Normalizes one road-context record. |
| Live audit | 105 cells, 122 gaps; retains the record's old observation date and missing atlas assignment. A successful acquisition does not establish complete or current atlas data. |
| Offline repeatability | Both complete synthetic coverage and the incomplete live audit produce identical bytes in all seven outputs across separate output directories. |
| Output verification | Every output's actual bytes are checked against `manifest.json`; tampering is detected. |

The generated starter report is `reports/atlas/continental/report.md`, with
`coverage.json`, `gaps.csv`, `gaps.geojson`, normalized feature outputs and a hash
manifest beside it. Live response bodies and the input job remain under ignored
`.tools/atlas/`. No acquired source or generated report is committed.

Exact full-gate commands, versions, revisions, statuses and artifact hashes are
recorded in the evidence JSON. These are data-pipeline checks, not a rendered
atlas readability or performance result.

## Remaining data work

Q-045 remains open. Product-specific source rights/ancestry reviews, exact
national-product exports, reviewed corridor masks, independent inventories and
real source-to-entity/access reconciliation are necessary before coverage can be
completed. The business and operator feeds are not blanket-approved by this
implementation. Download time never substitutes for an observation date.

The GeoParquet/GNIS/contextual profiles are bounded-export templates; original
release headers, geometry column, CRS and lineage must be verified before source
admission. PDF/HTML tables require reviewed transcription with original document
ancestry. The source services do not promise transactional snapshots; available
edit stamps, schema and ID sets are checked, and actual response bytes retained.

The parent P1-016 task stays in progress for runtime tiles, full production
coverage, cartographic readability/performance and the new human gates.

## Mainline health during the slice

Mainline was healthy when PR #139 claimed this work. Later, issue #140 reported
CI failure at `36035a576be407c2d33fc7e594afa327ee6f3807`: a Windows camera test
compared a cached spring hit of 7.50187492370605 m against 7.50183773040771 m.
The same mainline revision's Linux unsigned-export smoke also terminated with
SIGSEGV before readiness. The pipeline's files do not touch either runtime path.
Those findings are not atlas validation failures and are not marked repaired by
this data-pipeline slice; no new task was selected after that health signal.
