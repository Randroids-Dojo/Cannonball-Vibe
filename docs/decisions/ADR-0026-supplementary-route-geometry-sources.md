# ADR-0026: Supplementary route-geometry sources for corridor continuity

- Status: Accepted
- Date: 2026-08-30
- Owner decision: on 2026-08-30, after reviewing the corridor-gap evidence,
  the owner directed adoption of the best public-domain sources ("use the
  best sources needed") and delegated the selection to the evidence in
  [the source research](../research/2026-08-30-supplementary-route-geometry-sources.md).
- Amends: ADR-0002 (adds catalog sources; the public-domain-only policy and
  OSM rejection are unchanged)

## Context

The milepost-gap probe
([2026-08-27 audit](../audits/p0-021/2026-08-27-large-gap-probe.md)) proved
that NHPN's candidate acquisition was complete for its predicate and that 37
of the 45 large canonical-corridor gaps — 2,400.9 miles of milepost space —
contain no NHPN records on their route key under any sign or state. No
re-acquisition within NHPN can restore corridor continuity. The
[2026-08-30 source research](../research/2026-08-30-supplementary-route-geometry-sources.md)
evaluated seven public-domain candidates online, verifying licensing
statements, live endpoints, geometry grade, provenance fit, and lineage
contamination for each.

Decisive findings: the NTAD National Highway System dataset shares the
locked NHPN source's publisher family, ArcGIS host, acquisition discipline,
sign coding, and verbatim 17 U.S.C. § 101 public-domain statement, is
eleven years fresher, and empirically carries continuous measured state-LRS
routes across both probed Utah gap ranges. State DOT feeds fail the
public-domain predicate (CC BY or no grant, three of three spot-checked).
The USGS National Transportation Dataset names commercial HERE data in its
lineage. HPMS 2024 carries the same ARNOLD substrate with full attribution
but is a 2.44 GB annual snapshot with a documented 2024 New Jersey
attribution hole on the canonical corridor.

## Decision

- **Adopt NTAD NHS** (`usdot-ntad-national-highway-system`) as the
  supplementary corridor-geometry source. NHPN remains the route-family
  and topology backbone and the authority for which facilities are on the
  route (ADR-0002, ADR-0024); NHS supplies continuous state-LRS centerlines
  and milepoints where NHPN keys carry no records.
- **Admit USDA NAIP** (`usda-naip`) as an audit-evidence source only:
  dated, checksummed quads proving physical road continuity at geometric
  breaks before any ADR-0018 correction is authored. NAIP supplies no
  shipping geometry.
- **Stage HPMS 2024 (ARNOLD) as the pre-approved deepening path.** When
  reconstruction needs section attributes (lanes, speed, access control,
  curve/grade classes) or non-NHS surface roads, the HPMS public release
  may be added to the catalog under this ADR without a new decision
  record, provided the lock pins the exact release year and item version
  and characterizes FHWA's documented ARNOLD gaps and overlaps.
- **Census TIGER/Line PRISECROADS is approved in principle** as a
  lineage-independent cross-check witness for contentious break decisions;
  it requires its own catalog entry before first acquisition and never
  supplies shipping geometry.
- **Rejected for shipping geometry**: NTAD North American Roads (coarser
  than the problem), USGS National Transportation Dataset (commercial HERE
  lineage), and direct state DOT feeds (license-blocked). OSM ancestry
  remains rejected per ADR-0002.
- Every acquisition from the new sources follows the existing catalog
  policy: SHA-256 at ingest, acquisition timestamps, canonical URLs,
  recursive ancestry, and the paging/checkpoint/page-hash/service-drift
  discipline established for NHPN.

## Consequences

- `data/sources/catalog.json` gains the NHS and NAIP entries recorded with
  this ADR.
- The living locks pin the catalog's SHA-256 recursively (source lock,
  corridor lock, continental route lock, transfer-node and edge-path
  locks, the representative contract, and the validation-corpus lock);
  accepting this ADR re-blesses that pin chain to the new catalog hash.
  Historical evidence files retain the hashes that were true at their
  verification time and are never rewritten.
- Shipped chunks that draw on NHS geometry cite two ancestries (NHPN
  backbone plus NHS centerlines); provenance records must name both.
- Conflation between NHPN keys and NHS state-LRS routes becomes pipeline
  work; because HPMS extracts the same ARNOLD substrate, that conflation
  model is built once and reused if HPMS is adopted later.
- Per-state NHS geometry vintage and density vary; locks record the
  dataset's YEAR, VERSION, and UPDATE_DAT fields.
- The six geometric breaks remain evidence-gated: NAIP adjudication before
  any authored correction, per ADR-0018.

## Rejected alternatives

- **Re-platform on HPMS 2024 immediately:** heavier acquisition and
  conflation now, with the 2024 New Jersey attribution hole sitting on the
  canonical corridor; staging preserves the option at lower risk.
- **No new source; author every bridge under ADR-0018:** 2,400.9 miles of
  authored overrides with only imagery for evidence — orders of magnitude
  beyond the small, recorded corrections ADR-0018 contemplates, against
  data FHWA already publishes in the public domain.
- **State DOT feeds:** richest geometry but fail the ADR-0002 rights
  predicate (CC BY or no grant).
