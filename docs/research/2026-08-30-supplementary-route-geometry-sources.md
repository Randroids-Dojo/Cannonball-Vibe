# Supplementary public-domain route-geometry sources

- Date: 2026-08-30
- Scope: P0-021 follow-on. Evidence for a pending owner decision (a future
  ADR-0026); no decision is made here.
- Motivation: [the large-gap probe](../audits/p0-021/2026-08-27-large-gap-probe.md)
  established that 37 of 45 large corridor gaps — 2,400.9 miles of milepost
  space — contain no NHPN records on their key under any sign or state, and
  that no re-acquisition within NHPN's predicate can join the chains.
- Policy frame: [ADR-0002](../decisions/ADR-0002-public-domain-geodata-contract.md)
  and `data/sources/catalog.json` — only verified public-domain sources,
  SHA-256 at ingest, acquisition dates, no OpenStreetMap-derived ancestry.
- Status: research only. This document changes no catalog entry, no ADR, no
  ledger row, and no pipeline code. Every URL, byte count, and measurement
  below was verified against the live source on 2026-08-31 UTC with
  read-only queries; nothing was locked and nothing entered the response
  cache.

## Result

The gap NHPN cannot fill is already filled, in public domain, by NHPN's own
publisher family. FHWA's modern highway datasets — the **NTAD National
Highway System (NHS)** layer and the **HPMS public release** carrying the
**ARNOLD** all-roads LRS geometry — are hosted on the same ArcGIS
organization as the locked NHPN service, carry the same explicit
17 U.S.C. § 101 public-domain statement, use the same sign-route coding
(`SIGN1='I15'` matches on both), and are up to eleven years fresher than
NHPN's 2014 compilation.

The decisive empirical fact: NTAD NHS carries Utah I-15 as a single
state-LRS route (`ROUTEID 0015PM`, milepoints 0.000–400.592) whose interval
union covers **100.0% of both large NHPN gaps** on key `000000001500003`
(0.909–41.865 and 42.716–351.475); its only interior break is the 0.007-mile
sliver at 132.176–132.183 that the I-70 route `0070PM` carries — the Cove
Fort concurrency. Every ADR-0024 facility spot-checked, including the
non-Interstate NJ 495, NJ 3, US 46, and CA 107, exists in the NHS extent.

State DOT LRS portals publish technically superior data (UDOT models every
ramp with measures) but are license-heterogeneous — CC BY 4.0 or no grant at
all in all three states checked — so the rights-clean path to state LRS
geometry is its federal republication through NHS/HPMS. USGS NTD names
commercial HERE data in its lineage and is TIGER-derived anyway; TIGER
itself is public domain but carries no LRS and is no denser than NHPN.
USDA NAIP imagery is verified public domain and is the right ground-truth
layer for adjudicating physical continuity at the six unconnected breaks.

## Per-source evaluation

### 1. NTAD National Highway System (NHS) — FHWA via BTS

- **Publisher and license.** FHWA, republished by USDOT/BTS as an NTAD
  dataset. License text on the live service and the ArcGIS item, verbatim:
  *"The NHS Version 2025.08.08 database, or any portion thereof, can be
  freely distributed as long as this metadata entry is included with each
  distribution. The original metadata entry cannot be modified or deleted
  from any data transfer. This NTAD dataset is a work of the United States
  government as defined in 17 U.S.C. § 101 and as such are not protected by
  any U.S. copyrights. This work is available for unrestricted public
  use."* The metadata-retention sentence is a packaging requirement, not a
  share-alike term.
- **Coverage and vintage.** National; Version 2025.08.08 ("updated on
  August 08, 2025"), 492,005 polyline records. NHPN's service describes
  itself as "compiled on May 01, 2014" — NHS is eleven years fresher. A
  per-record `YEAR` field carries the state geometry vintage (2020 in the
  Utah and Iowa samples), and `UPDATE_DAT`/`VERSION` record maintenance.
  FHWA revises the national file several times a year (a 2025-03-27 zip
  sits beside the 2025-08-08 zip on the same page).
- **Geometry density relative to NHPN.** State-dependent, never worse in
  the samples measured. Iowa I-80: 4,035 NHS records at 0.1-milepoint
  granularity, mean vertex spacing **98 ft** versus NHPN's 440 ft on the
  same corridor — 4.5x denser. Utah I-15: 370 ft versus NHPN's 389 ft —
  equivalent. This is coarse-centerline grade, not lane geometry; it feeds
  the ADR-0002 reconstruction pipeline exactly as NHPN does.
- **Access.** REST: `https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_System/FeatureServer/0`
  (same host and query semantics as the locked NHPN service; the existing
  paging/checkpoint/hash acquisition machinery applies unchanged). Bulk:
  `https://www.fhwa.dot.gov/planning/national_highway_system/nhs_maps/nhs_2025-08-08.zip`
  — verified live, 112,830,711 bytes, `Last-Modified: Tue, 12 Aug 2025`.
- **Provenance fit.** Same discipline as the NHPN lock: the FeatureServer
  supports the metadata-hash drift refusal already implemented, and the
  FHWA zip is a single checksummable artifact with a stable versioned name.
- **Composition with NHPN.** Schema is the same family: `STFIPS`,
  `BEGINPOINT`/`ENDPOINT` milepoints, and identical sign coding
  (`SIGN1`/`SIGNT1`/`SIGNN1`; the queries `SIGN1='I15'`, `'U46'`, `'S107'`
  behave as on NHPN). The route key differs: NHS uses the state ARNOLD
  `ROUTEID` (e.g. Utah `0015PM`, Iowa `S001910080E`) instead of NHPN's
  `LRSKEY`. `ROUTEID` is state-scoped, which avoids the cross-state key
  collisions the probe documented in `LRSKEY`; the join to NHPN is
  `(STFIPS, sign route)` plus milepoints or geometry, not a shared key. In
  Utah the milepost basis is demonstrably the same space (both end at
  400.592).
- **Gap-coverage evidence (measured 2026-08-31).** All 557 Utah I-15 NHS
  records were fetched and their milepoint intervals unioned per `ROUTEID`:
  `0015PM` covers 0.000–132.176 and 132.183–400.592; coverage of the NHPN
  gap 0.909–41.865 is 41.0 of 41.0 mi (100.0%) and of 42.716–351.475 is
  308.8 of 308.8 mi (100.0%). Extent checks found NHS records for NJ 495
  (8), NJ 3 (37), US 46 in NJ (94), CA 107 (54), CA I-405 (311).
- **OSM risk.** None found in documented lineage. NHS geometry is extracted
  from state DOT HPMS/ARNOLD submissions (FHWA's own LRS program);
  Interstates and NHS routes are state-inventoried facilities. No OSM
  credit appears in the service metadata, item metadata, or FHWA
  documentation.
- **Limitations.** NHS-extent only — sufficient for every ADR-0024 facility
  (verified above) but not for arbitrary surface streets in the endpoint
  service bubbles; those remain authored or HPMS-sourced. Per-state
  geometry vintage and density vary. `hasM` is false on the hosted layer;
  milepoints live in attributes, not vertex measures.

### 2. FHWA HPMS public release, carrying ARNOLD

- **What ARNOLD is.** Since 2014 FHWA requires every state DOT to submit a
  statewide all-public-roads LRS (the All Road Network of Linear Referenced
  Data). ARNOLD is not published as a standalone national product; it is
  the geometry component of the HPMS public release — the item metadata
  states "The HPMS consists of the All Road Network of Linear Referenced
  Data (ARNOLD) geometry and the Section Data which is the attribution."
  So "HPMS" and "ARNOLD" are one candidate, and HPMS is the successor
  lineage to NHPN's role.
- **Publisher and license.** FHWA, republished by BTS as NTAD. ArcGIS item
  license text, verbatim: *"This NTAD dataset is a work of the United
  States government as defined in 17 U.S.C. § 101 and as such are not
  protected by any U.S. copyrights. This work is available for unrestricted
  public use."* FHWA's own recommended citation for the 2024 spatial data
  says "Public domain." explicitly.
- **Coverage and vintage.** National, all-public-roads (roughly 19.6 M
  records in the 2024 full join), per-state feature classes. HPMS 2024 was
  compiled 2025-12-23 as a snapshot of 2024-12-31; the program is annual
  (2020, 2022, 2023-BETA, and 2024 releases verified on the portal).
- **Geometry.** State ARNOLD centerlines with linear referencing; the
  hosted 2022 full-US layer is M-enabled (`hasM: true`). Same
  drivable-centerline grade as NHS — the two share the ARNOLD substrate —
  with the widest extent of any candidate. Section attributes include
  through lanes, speed limit, access control, surface, IRI, and binned
  curve (A–F) and grade (A–F) classifications: directly useful to later
  reconstruction and validation stages.
- **Access (all verified live).**
  - HPMS 2024 file geodatabase, one zip:
    `https://www.arcgis.com/sharing/rest/content/items/5e6a977c2d7c4ec1bdc82e684d3384f2/data`
    → `HPMS2024.zip`, 2,623,940,113 bytes (portal page:
    `https://geodata.bts.gov/datasets/5e6a977c2d7c4ec1bdc82e684d3384f2`).
  - FHWA data hub (M-enabled state FGDBs and full-join exports):
    `https://data.transportation.gov/stories/s/3uu4-47sa`; the 2024 full
    GeoJSON is documented at 49,034,981,675 bytes with a
    **publisher-stated SHA-256**
    (`a730042bb766978cde6773b558354c55efd71db1744faafe38894db6d81b2713`) in
    `https://github.com/FHWA/HPMS/blob/2024-HPMS/README_2024_HPMS_All.md`.
  - Hosted REST (2022 full-US, M-enabled, thin attributes):
    `https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/HPMS_FULL_US_2022_Sysnomulti_view/FeatureServer/0`
    (257,419 records).
  - Legacy 2018 per-state services: `https://geo.dot.gov/server/rest/services/Hosted/<State>_2018_PR/FeatureServer`.
- **Provenance fit.** Best in class: versioned single-artifact downloads,
  and FHWA itself publishes SHA-256 checksums and generation dates for the
  data-hub exports — the only candidate whose publisher practices the
  catalog's own discipline.
- **Composition with NHPN.** Keys are `(StateId, Route_ID, Begin_Point,
  End_Point)` — state-scoped ARNOLD route IDs identical in kind to the NHS
  layer's, since NHS is extracted from these submissions. NHS is therefore
  a subset view of HPMS/ARNOLD; adopting NHS first and HPMS later composes
  without a second conflation model.
- **OSM risk.** Same lineage as NHS: state DOT LRS submissions under
  federal reporting requirements; no OSM ancestry in any documented
  lineage. Residual risk concentrates in low-order local roads (some
  states build all-roads coverage from county sources), not in the
  Interstate/NHS extent this project consumes.
- **Limitations (from FHWA's own README).** ARNOLD "may contain physical
  spatial gaps" from source digitization or processing; overlapping
  geometry with different route IDs occurs at concurrencies; Iowa codes
  Interstate facility type against the field manual; and the 2024 full join
  is "missing substantial portions of data for ... North Dakota and New
  Jersey" — a live caveat, since New Jersey opens the canonical corridor
  (the NHS layer, a separate extract, showed normal NJ record counts in the
  spot checks above). The FGDB is a 2.4 GB acquisition.

### 3. BTS NTAD North American Roads

- **Publisher and license.** USDOT/BTS. Same NTAD public-domain statement,
  verbatim on the service: *"This NTAD dataset is a work of the United
  States government ... available for unrestricted public use."*
- **Coverage and vintage.** US (incl. AK/HI), Canada, Mexico; compiled
  2020-10-27; 720,055 records; no update since.
- **Geometry.** Nominal **1:100,000** — the same coarse scale as NHPN, no
  milepoint attributes, no measures, `LINKID` keys. It cannot join NHPN
  chains any better than NHPN joins itself; it is a context/basemap layer.
- **Access.** `https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_North_American_Roads/FeatureServer/0`.
- **Lineage caution.** Compiled from Natural Resources Canada, FHWA, and
  the Mexican Transportation Institute. The Canadian portion originates in
  NRCan's National Road Network (Open Government Licence – Canada, an
  attribution license); a US-extent-only acquisition avoids that ancestry
  entirely. No OSM in documented lineage.
- **Verdict.** Fallback/context only; adds nothing over NHS/HPMS for the
  corridor.

### 4. USGS National Transportation Dataset (The National Map)

- **Publisher and license.** USGS NGTOC; public domain as USGS data.
- **Lineage — the disqualifying fact.** The collection's own ScienceBase
  description: *"The USGS Transportation downloadable data from The
  National Map (TNM) is based on TIGER/Line data provided through U.S.
  Census Bureau and supplemented with HERE road data to create tile cache
  base maps."* Roads are TIGER-derived (so the vector product adds nothing
  over acquiring TIGER directly), and commercial HERE data is named in the
  product family's lineage. The statement scopes HERE to the tile-cache
  basemaps, but the vector product's clean separation from HERE would have
  to be proven, per dataset vintage, before ADR-0002 acceptance —
  effort better spent elsewhere given the TIGER redundancy.
- **Access (verified).** Staged products on the same S3 bucket family as
  the cataloged 3DEP prefix:
  `https://prd-tnm.s3.amazonaws.com/StagedProducts/Tran/` (`GDB/`, `GPKG/`,
  `Shape/`, `National/`); e.g. `Shape/TRAN_Utah_State_Shape.zip`,
  189,208,879 bytes, dated 2026-02-12. Refresh is irregular.
- **Verdict.** Skip for roads. If census-family geometry is ever wanted,
  acquire TIGER/Line at the source instead.

### 5. Census TIGER/Line roads (PRISECROADS, MTFCC S1100)

- **Publisher and license.** U.S. Census Bureau. The TIGER/Line technical
  documentation states: *"Copyright protection is not available for any
  work of the United States Government (Title 17 U.S.C., Section 105)"* —
  products are uncopyrighted and freely redistributable.
- **Coverage and vintage.** Annual. TIGER2025 verified:
  `https://www2.census.gov/geo/tiger/TIGER2025/PRISECROADS/` lists 56
  state/territory files; the Utah file `tl_2025_49_prisecroads.zip`
  (2,678,643 bytes) was downloaded to scratch and measured —
  SHA-256 `b736ecd5c107f39fa272ffa45b93231d8d20ee2bcf1ec0924669d6e6edfba7c1`.
- **Geometry and semantics (measured).** Utah I-15: 21 features, 12,703
  vertices over 802.6 mi (both carriageway representations), mean spacing
  **334 ft** — no denser than NHPN. Attributes are `LINEARID`, `FULLNAME`,
  `RTTYP`, `MTFCC` only: **no milepoints, no LRS, no state route IDs**.
  Conflation to the NHPN/NHS milepost world is purely spatial.
- **OSM risk.** None in documented lineage; MAF/TIGER is maintained through
  Census partnership programs with governments. (The well-known data flow
  runs the other way: OSM imported TIGER in 2007.)
- **Verdict.** Clean and effortless to acquire, but it solves neither the
  connectivity problem (no measures) nor the density problem. Its value is
  as an *independent* public-domain cross-check: a second opinion on
  whether a road physically exists along a break, from a lineage disjoint
  from the state-DOT family.

### 6. State DOT LRS portals (spot-checked: Utah, Iowa, Pennsylvania)

The documented gap keys implicate Utah (I-15 Salt Lake–Cove Fort ranges),
Iowa and New Jersey (the I-80 composite key), plus Ohio and Colorado
corridor segments. Three states were checked end to end:

- **Utah (UDOT).** Technically the strongest data seen in this research:
  `https://roads.udot.utah.gov/server/rest/services/Public/UDOT_Routes/FeatureServer/0`
  is a polylineM layer (EPSG:26912) where mainline I-15 is **one measured
  feature** (`ROUTE_ID 0015PM`, mileage 0.000–400.886, 4,376 vertices,
  484 ft spacing) and every ramp, collector, and turnaround is its own
  measured route with exit and ramp numbers (sampled ramps: 49–139 ft
  vertex spacing) — network detail no federal extract carries. But the
  hosting state license regime is not public domain: Utah's UGRC licenses
  SGID data and hosted services under **CC BY 4.0**, and no UDOT-specific
  public-domain dedication was found.
- **Iowa (Iowa DOT RAMS).** Road Network on `data.iowadot.gov` /
  `gis.iowadot.gov` (359,078 records) is published under **CC BY 4.0**.
- **Pennsylvania (PennDOT RMSSEG).** The open-data item carries **no
  license grant at all** — only a "for informational and planning purposes
  only" disclaimer — so public-domain status is unverifiable.
- **Verdict.** 3-for-3 fail against the catalog policy
  (`allowed_statuses: ["public_domain"]`). State works are not federal
  works, so § 105 does not apply; each state is its own negotiation. The
  rights-clean route to exactly this geometry is its federal republication:
  states submit ARNOLD to FHWA, and the resulting HPMS/NHS releases are
  published as US-government works with explicit public-domain statements.
  Per-state adoption should be reconsidered only if a specific break needs
  ramp-grade detail that HPMS lacks — and then under a new, per-state
  license verification recorded in the catalog.

### 7. USDA NAIP aerial imagery — ground truth, not centerlines

- **Publisher and license.** USDA Farm Production and Conservation
  Business Center, Geospatial Enterprise Operations. The data.gov record
  lists the license as `https://www.usa.gov/publicdomain/label/1.0/`
  (public domain).
- **Coverage and cadence.** Conterminous US on a 2–3 year state rotation;
  1 m GSD historically, 0.6 m standard since 2018, 0.3 m in roughly half
  the states by the 2025 cycle.
- **Access.** USGS EarthExplorer (per-quad GeoTIFF downloads —
  checksummable files with acquisition dates); The National Map downloader
  (JP2); REST imagery service
  `https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer`;
  discovery via `https://naip-usdaonline.hub.arcgis.com/`.
- **Role.** NAIP cannot supply topology, but it is the rights-clean
  equivalent of driving the road: for each of the six unconnected chain
  ends, a dated, checksummed NAIP quad showing continuous pavement across
  the break is exactly the evidence an ADR-0018-compliant per-break
  correction record needs. Sub-meter pixels bound the positional error of
  any authored bridge far below NHPN's ~80 m error budget.
- **OSM risk.** None possible; it is imagery flown under USDA contract,
  with no vector lineage.

## Comparison matrix

| Source | Vintage / cadence | Verified license | Geometry vs NHPN | LRS / keys | Bulk + REST access | OSM / 3rd-party lineage risk | Fit for the 37 empty gaps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NTAD NHS 2025.08.08 | 2025 / ~semiannual file, live service | PD, 17 U.S.C. § 101 stated on service | Equal (UT) to 4.5x denser (IA) | State ARNOLD `ROUTEID` + milepoints; NHPN sign coding | 112.8 MB zip + same-host FeatureServer | None documented | **Proven 100% on the probed Utah gaps; all ADR-0024 facilities present** |
| HPMS 2024 (ARNOLD) | 2024 snapshot / annual | PD, stated on item + citation | Same substrate as NHS; all public roads; M-enabled | `Route_ID` + begin/end points per state | 2.44 GB FGDB zip; publisher-stated SHA-256 on hub exports | None documented; local-road residuals | Yes, superset of NHS; NJ/ND 2024 attribution holes noted |
| NTAD North American Roads | 2020, static | PD (US extent); NRCan ancestry in CA extent | Same 1:100k coarseness | None (`LINKID`) | FeatureServer only | OGL-Canada in Canadian portion | No — cannot join what NHPN cannot |
| USGS NTD | Irregular | PD, but HERE named in product lineage | TIGER-derived | None | S3 staged products (verified) | **HERE (commercial) ambiguity**; TIGER-redundant | No — use TIGER directly if ever needed |
| TIGER/Line PRISECROADS | Annual (2025 verified) | PD, § 105 in tech doc | Equal (334 ft spacing, UT) | None (`LINEARID` only) | Per-state zips (verified + hashed) | None documented | Cross-check only; no measures |
| State DOT LRS (UT/IA/PA) | Continuous | **CC BY 4.0 / CC BY 4.0 / no grant** | Denser; ramp-level routes with measures | Native state LRS | State portals + REST | None documented | Blocked by license policy; reaches project via HPMS/NHS instead |
| USDA NAIP | 2–3 yr state cycles | PD (usa.gov PD label) | n/a (imagery, 0.3–1 m) | n/a | EarthExplorer GeoTIFF, TNM, ImageServer | None possible | Verification evidence, not geometry |

## Recommended composition strategy

1. **Fill with NTAD NHS.** Adopt the NHS FeatureServer (same host,
   acquisition discipline, and sign semantics as the locked NHPN source)
   as the supplementary corridor-geometry source. NHPN remains what
   ADR-0002 says it is — the route-family and topology backbone and the
   authority for which facilities are on the route; NHS supplies the
   continuous state-LRS centerlines and milepoints across the 37 ranges
   where NHPN's keys carry nothing.
2. **Verify with NAIP.** For each of the six geometric breaks (and any
   residual seam after NHS conflation), acquire the covering NAIP quads as
   dated, checksummed audit artifacts proving physical continuity before
   any ADR-0018 correction is authored.
3. **Cross-check with TIGER.** Where a break decision is contentious, the
   TIGER PRISECROADS file for that state is a cheap, lineage-independent
   second witness that costs one small hashed zip per state.
4. **Hold HPMS 2024 as the deepening path, not the first step.** When
   reconstruction needs lane counts, speed limits, curve/grade classes, or
   non-NHS surface roads near the endpoint portals, the HPMS FGDB is the
   same ARNOLD substrate with full attribution — adopting NHS first means
   HPMS composes later without a new conflation model.
5. **Do not adopt** North American Roads (coarser than the problem), USGS
   NTD (HERE ambiguity, TIGER-redundant), or direct state DOT feeds
   (license-blocked) for shipping geometry.

## DRAFT catalog entry stubs

Drafts for the top recommendations, for the owner decision only — this
research does **not** modify `data/sources/catalog.json`.

```json
{
  "id": "usdot-ntad-national-highway-system",
  "name": "National Highway System (NHS)",
  "publisher": "U.S. Department of Transportation, Federal Highway Administration (via BTS NTAD)",
  "landing_page": "https://geodata.bts.gov/datasets/usdot::national-highway-system-nhs/about",
  "license_evidence_url": "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_System/FeatureServer",
  "license_status": "public_domain",
  "service_url": "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_System/FeatureServer/0",
  "allowed_url_prefixes": [
    "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_System/FeatureServer/0",
    "https://www.fhwa.dot.gov/planning/national_highway_system/nhs_maps/"
  ],
  "use": "Supplementary corridor centerlines and state-LRS milepoints where NHPN keys carry no records; NHPN remains the route-family backbone",
  "limitations": "NHS extent only; per-state geometry vintage and density vary (record fields YEAR, VERSION, UPDATE_DAT). Redistribution must retain the source metadata entry per the dataset's own license text. Not lane geometry."
}
```

```json
{
  "id": "fhwa-hpms-arnold",
  "name": "Highway Performance Monitoring System (HPMS) public release (ARNOLD geometry)",
  "publisher": "U.S. Department of Transportation, Federal Highway Administration (via BTS NTAD)",
  "landing_page": "https://geodata.bts.gov/datasets/5e6a977c2d7c4ec1bdc82e684d3384f2",
  "license_evidence_url": "https://www.arcgis.com/sharing/rest/content/items/5e6a977c2d7c4ec1bdc82e684d3384f2?f=json",
  "license_status": "public_domain",
  "allowed_url_prefixes": [
    "https://www.arcgis.com/sharing/rest/content/items/5e6a977c2d7c4ec1bdc82e684d3384f2/",
    "https://data.transportation.gov/"
  ],
  "use": "All-public-roads ARNOLD centerlines, measures, and section attributes (lanes, speed, access control, curve/grade classes) for reconstruction and endpoint service bubbles",
  "limitations": "Annual snapshot; 2.44 GB acquisition; FHWA documents possible ARNOLD spatial gaps, overlapping concurrency geometry, and missing 2024 attribution for North Dakota and New Jersey. Pin the exact release year and item version at lock time."
}
```

```json
{
  "id": "usda-naip",
  "name": "National Agriculture Imagery Program (NAIP)",
  "publisher": "U.S. Department of Agriculture, FPAC Geospatial Enterprise Operations",
  "landing_page": "https://naip-usdaonline.hub.arcgis.com/",
  "license_evidence_url": "https://catalog.data.gov/dataset/national-agriculture-imagery-program-naip-imagery",
  "license_status": "public_domain",
  "allowed_url_prefixes": [
    "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/",
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/"
  ],
  "use": "Break-adjudication ground truth only: dated, checksummed quads evidencing physical road continuity for ADR-0018 correction records. Not a geometry source.",
  "limitations": "2-3 year state acquisition cycles; record quad ID, flight date, resolution, and SHA-256 per acquired tile."
}
```

## Decision required (owner)

No option is selected here. Any option except D changes
`data/sources/catalog.json` and therefore needs an accepted ADR (the
pending ADR-0026).

- **Option A — Adopt NTAD NHS as the supplementary geometry source.**
  NHPN stays the route-family authority; NHS fills the empty gap ranges
  and seams. Cheapest integration (same host, same acquisition machinery,
  same sign coding), empirically proven on the probed Utah gaps, covers
  every ADR-0024 facility. Tradeoff: NHS-extent only, and a second source
  joins the provenance chain — every shipped chunk now cites two
  ancestries.
- **Option B — Re-platform corridor geometry on HPMS 2024 (ARNOLD).**
  One modern all-roads source for geometry, measures, and attributes;
  publisher-stated checksums; annual cadence. Tradeoff: 2.44 GB
  acquisitions, a heavier conflation against the locked NHPN candidate
  set, FHWA-documented ARNOLD gaps/overlaps to characterize from scratch,
  and the 2024 New Jersey attribution hole sits on the canonical corridor.
- **Option C — Staged A then B (recommended framing, not a decision).**
  Adopt NHS now to restore corridor continuity; adopt HPMS later, as a
  separate lock, when reconstruction needs section attributes or
  non-NHS surface roads. Tradeoff: two catalog changes and two ADR
  moments, but each is small, and both draw on the same ARNOLD substrate
  so the conflation model is built once.
- **Option D — No new source: author every bridge under ADR-0018.**
  Keeps the catalog at two sources. Tradeoff: 37 gaps spanning 2,400.9
  miles of milepost space becomes authored-override territory with only
  NAIP for evidence — an authoring and validation burden orders of
  magnitude beyond the "small, recorded overrides" ADR-0018 contemplates,
  against source data FHWA already publishes in public domain.

Orthogonal small question: whether to admit **NAIP** to the catalog as an
audit-evidence source (usable under any option, including D). It supplies
no shipping geometry, so its risk surface is limited to the evidence
chain.

## What this research could not verify online

- The internal schema and M-value fidelity of the HPMS 2024 FGDB (a
  2.44 GB download; only its metadata, size, and availability were
  verified).
- Whether the NHS milepoint basis matches NHPN's milepost space in every
  corridor state; it was verified for Utah (identical 400.592 terminus)
  and is structurally expected elsewhere, but the per-state check belongs
  to acquisition, not research.
- Geometric (not milepost-space) closure of the six unconnected NHPN
  chain-end pairs against NHS geometry — that is precisely the spatial
  probe the 2026-08-27 audit already prescribes, now with a named source
  to probe against.
- Whether the USGS NTD *vector* product is fully free of the HERE data
  named in its product-family lineage; unresolved, and moot given its
  TIGER redundancy.
- Any UDOT-specific license term that might differ from UGRC's CC BY 4.0
  hosting regime; no public-domain dedication was found on either portal.

## Primary sources

- [NTAD NHS FeatureServer (license text, version 2025.08.08)](https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_System/FeatureServer)
- [FHWA NHS shapefile downloads (nhs_2025-08-08.zip)](https://www.fhwa.dot.gov/planning/national_highway_system/nhs_maps/)
- [HPMS 2024 on the BTS geodata portal](https://geodata.bts.gov/datasets/5e6a977c2d7c4ec1bdc82e684d3384f2)
- [FHWA HPMS 2024 README (provenance, SHA-256, known limitations)](https://github.com/FHWA/HPMS/blob/2024-HPMS/README_2024_HPMS_All.md)
- [FHWA HPMS data access hub (M-enabled state FGDBs)](https://data.transportation.gov/stories/s/3uu4-47sa)
- [ARNOLD Reference Manual (FHWA, 2014)](https://www.fhwa.dot.gov/policyinformation/hpms/documents/arnold_reference_manual_2014.pdf)
- [HPMS 2018 per-state public release services](https://www.fhwa.dot.gov/policyinformation/hpms/shapefiles.cfm)
- [NTAD North American Roads FeatureServer](https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_North_American_Roads/FeatureServer)
- [USGS NTD collection metadata (TIGER + HERE lineage statement)](https://www.sciencebase.gov/catalog/item/4f70b1f4e4b058caae3f8e16)
- [USGS NTD staged products (verified S3 prefix)](https://prd-tnm.s3.amazonaws.com/StagedProducts/Tran/)
- [TIGER/Line 2025 PRISECROADS directory](https://www2.census.gov/geo/tiger/TIGER2025/PRISECROADS/)
- [TIGER/Line technical documentation (Title 17 § 105 statement)](https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2024/TGRSHP2024_TechDoc.pdf)
- [UDOT public LRS routes FeatureServer](https://roads.udot.utah.gov/server/rest/services/Public/UDOT_Routes/FeatureServer)
- [UGRC licensing (CC BY 4.0 for SGID data)](https://gis.utah.gov/documentation/policy/license/)
- [Iowa DOT RAMS Road Network (CC BY 4.0)](https://data.iowadot.gov/datasets/road-network-portal/about)
- [PennDOT RMSSEG open-data item (no license grant)](https://data-pennshare.opendata.arcgis.com/datasets/PennShare::rmsseg-state-roads/about)
- [NAIP on data.gov (public-domain license label)](https://catalog.data.gov/dataset/national-agriculture-imagery-program-naip-imagery)
- [USGS NAIP imagery REST service](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer)
