# ADR-0028: Atlas data intake and coverage audits

- Status: Accepted
- Date: 2026-09-06
- Task: P1-016, offline data pipeline slice; claim PR #139
- Authority: owner request to build incorporation, validation, and explicit gap
  reporting for the researched datasets.
- Preserves: ADR-0002, ADR-0017, ADR-0026 and Q-045. Does not accept the proposed
  renderer in ADR-0027 or admit any new shipping source.

## Decision

1. Add an offline atlas intake module to the existing Python map pipeline.
   Versioned dataset profiles map GeoJSON, ArcGIS JSON, delimited text,
   GeoPackage and GeoParquet records into a common, source-addressable audit
   representation. PDF tables enter through reviewed transcription with the
   original document retained as an ancestor; automatic OCR is not truth.
2. Keep candidate profiles separate from the approved source catalog. The
   catalog remains authoritative. Uncataloged, non-public-domain, unknown or
   OSM-derived sources are blocked before acquisition/normalization. A profile
   is discovery metadata, never permission to use a source.
3. Lock input bytes, catalog, profiles, route selection and coverage scope.
   Every acquired artifact records UTC acquisition time, canonical and final
   URL, response metadata, SHA-256 and explicit ancestry. Derived artifacts
   retain their input artifacts recursively. Acquisition uses bounded requests,
   validated redirects, page reconciliation and checksummed resume caches.
4. Normalize source values without inventing exit numbers, route direction,
   business entrances or connection topology. Preserve observed/derived/authored
   classification, nulls, original record IDs and observation dates. Acquisition
   date does not establish freshness. Same-ID disagreements and explicitly bound
   cross-source disagreements remain conflicts, not last-writer wins.
5. Clip inclusion to reviewed corridor polygons keyed to selected policy
   segments. These polygons are acquisition/audit masks, not approved road
   geometry. Missing masks are gaps. Spatial proximity never proves service
   access or adds playable edges. Exact reviewed bindings may reconcile source
   IDs to a common inventory entity; automatic fuzzy matching is deferred.
6. Measure coverage against a separately sourced, checksummed and explicitly
   reviewed inventory for each segment and feature kind. Its original sources
   must be independent of the contributing feature artifacts. Without that
   inventory, denominator and percentage stay null. Explicitly reviewed empty
   inventories distinguish no required features from no downloaded features.
7. Emit deterministic normalized GeoJSON/JSONL, coverage JSON, gap CSV/GeoJSON,
   Markdown and output checksums. These are offline audit/interchange outputs;
   runtime tiles remain a later FlatBuffer compiler slice. A strict audit returns
   a nonzero status while gaps remain, including rights, acquisition, geometry,
   freshness, inventory, missing fields, conflicts and unverified access.

## Verification and boundaries

Synthetic fixtures exercise each adapter, approved and denied sources, recursive
ancestry, tampered bytes, redirects, partial pages, duplicate IDs, CRS handling,
scope clipping, unknown/empty inventories, conflict and stale-data behavior, and
two-build byte equality. A continental starter job names every selected segment
and reports unknown coverage rather than generating fictional records.

No continental downloads or generated reports are committed. New-source rights
review and full corridor coverage remain open in Q-045; the atlas renderer and
human comprehension/accessibility gates remain unfinished in P1-016.
