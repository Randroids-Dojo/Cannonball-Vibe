# NHPN-NHS conflation model and 3DEP product lock

Date: 2026-08-31

Task: P0-021. Executes the slice the
[topology closure](2026-08-31-topology-closure.md) prescribed: the ADR-0026
NHPN-NHS conflation model over the five locked NHS fill spans, and the
ADR-0007 3DEP product lock over the closed continental corridor - the two
inputs the reconstruction-geometry stage needs before the westbound directed
selection can be solved.

Status: **both locks landed.** The conflation model corresponds all ten span
seams within its catalog-grounded bound (max 55.755 m), and the 3DEP lock
pins one exact dated product - URL, publication date, and per-tile datum
evidence - for every 1x1 degree cell the chained corridor traverses, with a
deterministic three-tile sample verified end to end. No direction is
selected, no authoritative distance is claimed, and the 1 m / 25 m
tolerances are untouched.

## Conflation model design

The fill lock records what NHS asserts across the named NHPN voids; nothing
in it was conflated. The model
(`derive-continental-nhs-conflation` -> `data/routes/continental/nhs-conflation-lock.v1.json`,
validated cache-independently by `validate-continental-nhs-conflation` as a
seventh `scripts/validate-continental-route.sh` stage) adds, per fill span:

- **Seam correspondence at both span ends.** Each pinned break-end
  coordinate is corresponded to the NHS route: the nearest fill-group record,
  the perpendicular seam offset, and the interpolated state-LRS measure at
  the seam - against the NHPN side: every locked record endpoint within the
  unchanged 1 m tolerance, and the nearest one's LRS key, record milepost
  interval, and milepost at the seam end where orientation evidence supports
  it (recorded as null where it does not, never guessed - the i15 south seam
  record has no measure-adjacent neighbour on its key and stays null).
- **Orientation as evidence, not assumption.** NHS serves no M values, so
  record geometry direction relative to the measure axis is proven by
  measure-adjacency: records whose measures abut are digitized end-on, and
  the shared boundary vertex votes for each record's orientation. A scoped
  margin acquisition per span (the group's route records within 0.25 mi of
  measure margin, acquired with the full paging/checkpoint/page-hash
  discipline and refused outright if the live service metadata hash drifts
  from the fill lock's) guarantees even a single-record span has a
  neighbour on record. Margin records are orientation evidence only - not
  fill geometry, not candidates, not lock members. Conflicting votes are a
  machine-readable refusal. All 100 span records across the five sites
  resolved `forward` (NHS digitizes in measure direction - now recorded
  evidence rather than an assumption).
- **Oriented span geometry seam to seam**, assembled from the records'
  measure-clipped, orientation-corrected pieces (max piece joint gap 0.0 m
  at every site against the 5 m adjacency tolerance), content-addressed with
  a geometry digest.
- **Geometric agreement.** Every 50 m station along the span is measured
  against the segment's locked NHPN candidate lines under the same 80 m
  lens the probes used: within-lens stations record the two datasets'
  lateral agreement; beyond-lens stations are the NHPN void the fill exists
  for, characterised as contiguous runs and never absorbed.

Reuse per ADR-0026: every correspondence is keyed on the ARNOLD LRS
identity - `(STFIPS, ROUTEID, measure)` - and nothing on NHS-only fields, so
the model transfers unchanged if HPMS (the same ARNOLD substrate) is adopted.

### Bounds

| Bound | Value | Grounding |
| --- | --- | --- |
| Seam offset | <= 80 m | The seam coordinate is an NHPN endpoint; the catalog documents NHPN horizontal error to ~80 m (the probes' lens). A correspondence, not a snap. |
| Record geometry vs MILES | <= 2% | The source's own per-record length assertion agrees with its geometry within ~1% on every locked fill record; the bound trips when conflated geometry is not the geometry the source measured. |
| Piece joint gap | <= 5 m | Same-route NHS records are digitized end-on; far inside the cross-dataset lens. |
| Orientation evidence gap | <= 5 m (votes by the strictly closer end; ambiguous within 1 mm) | A record can be one measure quantum (~1.6 m) long, so both its ends sit inside the tolerance; the shared boundary vertex is still exact (observed 0.0 m). |

**Measure-axis finding (characterised, not absorbed).** The first bound
draft compared span geometry against the measure delta and the Big-I span
failed it at 5.26%. Characterisation against the source's own fields proved
the bound wrong, not the data: the state-LRS measure axis is *calibrated*,
not metric - per-record measure extents diverge from planimetric length by
up to 43% (i40) and by 14.55% over the whole i78 span, while the source's
MILES field agrees with its geometry within ~0.9% on every one of the same
records. The model therefore bounds geometry against MILES, records the
measure-axis distortion per span as characterisation, and states in the
artifact that measures parametrise and key - they are never a length. No
Q-sub-item was needed: nothing failed once the bound measured the claim the
source actually makes.

## Per-span seam results

| Span | Seam offsets (from / to) | NHS measures at seams | Span geometry | Record-vs-MILES max | Measure-axis distortion | NHPN agreement along span |
| --- | --- | --- | --- | ---: | ---: | --- |
| i15 (UT 0015PM) | 40.799 m / 42.527 m | 263.355 / 245.104 | 29,578.9 m, 62 records | 0.91% | 0.71% | all 593 stations within lens (max 40.7 m, mean 3.0 m) - **no NHPN void**: the Payson-supplemented NHPN carries the whole span |
| i40 Big-I (NM I40P) | 0.100 m / 0.066 m | 158.147 / 159.370 | 1,864.4 m, 10 records | 0.86% | 5.26% | void run 100-1750 m (the Albuquerque interchange void, exactly as probed); 5 stations within lens at the ends |
| i40 02-03 (NM I40P) | 0.066 m / 30.168 m | 159.370 / 168.114 | 13,885.9 m, 25 records | 0.85% | 1.32% | all 279 stations within lens (max 0.116 m, mean 0.036 m - the locked candidate set carries near-identical centerline here) |
| i70 Rifle (CO 070A) | 17.422 m / 55.755 m | 85.133 / 85.328 | 311.4 m, 1 record | 0.69% | 0.92% | void run 100-250 m (the west half the census found joins nothing); 4 stations within lens |
| i78 Delaware River (PA "6 48 48B3 - 86216") | 16.353 m / 14.826 m | 0.212 / 2.669 | 3,378.1 m, 2 records | 0.59% | 14.55% | void run 100-3300 m (the river crossing); 4 stations within lens at the banks |

10 of 10 seams pass (max 55.755 m of the 80 m bound - the i70 west break
end, whose NHPN chain end the census already measured as joining nothing).
Total conflated span geometry 49,018.7 m. Margin acquisitions: 66/16/30/3/2
records per site, zero retries, checkpoint-resumed on replay. NHPN seam
correspondences: all ten seams land on a locked record endpoint at 0.000 m;
mileposts at seam resolved for nine (the i15 south seam is honestly null,
see above). The two i40 seams make the correspondence the model exists for:
NHPN milepost 158.31 corresponds to NHS measure 158.147, and 159.479 to
159.370 - the two LRS spaces genuinely differ, and the lock now records by
how much at every seam.

Conflation lock SHA-256:
`4448c547c0a051ac6c58f26c8e37f092d3a4fbd5a33072f807103b5394292251`.

## 3DEP product lock

The geodata law requires product, resolution, date, horizontal datum, and
vertical datum locked before 3DEP supplies elevation. The lock
(`lock-continental-3dep-products` -> `data/routes/continental/3dep-product-lock.v1.json`,
validated offline by `validate-continental-3dep-products` as the eighth
script stage) pins the ADR-0007 1/3 arc-second seamless baseline over the
closed corridor:

- **Coverage: 124 one-degree cells**, derived from the locks themselves -
  the eight connected segments' solved edge paths re-proved against the
  cache before use, the four chained segments' mixed-ancestry chains
  recomputed with the same graph/bridge/split machinery and proved equal to
  the locked chain-connectivity entries to the millimetre (all four match
  exactly: i40 3,366,484.933 m, i70 804,576.944 m, i78 231,084.599 m, i80
  2,504,070.528 m), plus the five locked NHS fill spans (5 cells) and the
  two authored overlay chords (2 cells). Per-segment cell counts range from
  1 (i15-barstow-to-ontario) to 46 (i40).
- **Products: one exact dated staged-product URL per cell** (the historical
  layout's dated files are immutable, so the locked URLs cannot be silently
  replaced the way `current/` objects can), selected deterministically from
  one checkpointed, response-hashed discovery request per cell against the
  catalog's TNM endpoint: the latest publication date among GeoTIFF
  candidates that cover the cell inside the catalog allowlist, lexical
  sourceId tiebreak, all candidates recorded (1 to 10 per cell).
  Publication dates span 2019-09-16 to 2026-08-12 (58 of 124 cells carry a
  2026 edition). The locked corridor raster set totals 51.68 GB - locked,
  not downloaded: the bulk acquisition is a later stage against these exact
  URLs.
- **Datums: per-tile evidence, not a family assumption.** Every selected
  product's own FGDC metadata (the sibling `.xml` beside the tile under the
  allowed `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/` prefix,
  hashed and cached) states `North American Datum of 1983`,
  `North American Vertical Datum of 1988`, `meters`, and the 1/3 arc-second
  cell size, on all 124 tiles; a tile whose metadata says anything else is
  a machine-readable refusal.
- **Sample verification, end to end.** The deterministic sample
  (first/middle/last sorted cell) was downloaded in full, checksummed, and
  raster-inspected - CRS EPSG:4269, exact 1/3 arc-second pixels, one
  float32 band, -999999 nodata, full cell coverage, byte counts equal to
  the discovery declarations:

| Cell | Product | Bytes | SHA-256 (prefix) |
| --- | --- | ---: | --- |
| n34w119 | USGS_13_n34w119_20250826.tif | 77,566,808 | `d550d73b3884` |
| n39w110 | USGS_13_n39w110_20260630.tif | 431,583,064 | `6844bd715ef6` |
| n42w112 | USGS_13_n42w112_20240130.tif | 406,335,575 | `9728241f1ede` |

One tolerance was set by measurement during the sample verification: the
staged products encode the cell size to about nine significant digits
(observed `9.25925927753796e-05` against the exact 1/10800), so the pixel
agreement tolerance is one part per million - the first sample run refused
at 1e-9, which was tighter than the source's own encoding noise.

3DEP product lock SHA-256:
`8863b1cd0445188427e0af597b6599b8f3e855ca43c34e93c664db1e3705860f`.

ADR-0007's 1-metre upgrade path stays gated and is not locked here; the
lock says so explicitly (`one_meter_upgrade` in its source policy).

## Provenance and replay

- Base revision: `993b910` (main), branch
  `agent/p0-021-conflation-3dep-lock-20260831`, PR #98; macOS 26.7 arm64;
  uv 0.9.24, Python 3.13.11, GeoPandas 1.1.4, NetworkX 3.6.1, PyProj 3.7.2,
  Shapely 2.1.2, Rasterio 1.5.x.
- The NHPN response cache (base plus supplements) and the NHS fill cache
  were regenerated from the live services before anything else and
  reproduced the committed candidate and fill locks exactly modulo
  acquisition timestamps (live NHPN metadata still byte-identical to
  `5150b91e…`; live NHS metadata still byte-identical to `a29f96df…`, and
  the fill acquisition was pinned with `--expected-metadata-sha256`).
- The conflation derive refuses outright if the live NHS metadata hash
  differs from the fill lock's - no flag, no override - and additionally
  proves every locked fill record byte-identical between the fill cache and
  the margin acquisition before conflating anything.
- Replay is exact for both new locks: re-deriving the conflation lock
  resumes all five margin acquisitions from checkpoints (zero retries) and
  reproduces it exactly modulo acquisition timestamps; re-running
  `lock-continental-3dep-products` resumes all 124 discovery checkpoints,
  124 metadata checkpoints, and 3 tile checkpoints (re-hashing the cached
  tiles) and reproduces the lock exactly modulo timestamps.
- Two service behaviours are recorded honestly: the hosted NHS layer
  intermittently answered a valid attribute query with HTTP 400 and
  succeeded on the identical retry (observed three times, each request
  verified valid out of band; the margin acquisition carries a bounded,
  documented retry for exactly that), and the TNM discovery API answered
  with intermittent 5xx (the discovery transport retries the standard
  transient set with backoff).
- All responses stay in the ignored `.tools/continental/` caches
  (`nhs-conflation/<hash>/`, `3dep/discovery/`, `3dep/metadata/`,
  `3dep/tiles/`); nothing continental is committed and
  `data/sources/catalog.json` is untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-nhs-conflation
# exit 0: 5 spans, 10/10 seams within 80 m, max seam offset 55.755 m

uv run --project tools/map_pipeline --frozen cannonball-map \
  lock-continental-3dep-products
# exit 0: 124 cells, 124 products, 3 sample tiles verified end-to-end

./scripts/validate-continental-route.sh
# exit 0: all eight stages green (candidate, transfer, edge-path, NHS fill,
# break dispositions, reconstruction overlays, NHS conflation, 3DEP products)
```

## Verification

`ruff` clean; 225 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`; the repository-root bare `pytest` collection
trap is unchanged). New unit tests cover the measure-adjacency orientation
votes (forward, reversed, the quantum-short-record case the first live run
refused, and the conflicting-votes refusal), the margin predicate's exact
construction and quote escaping, measure interpolation under both
orientations, span assembly (clipping, orientation correction, overlap
resolution, and the coverage refusal), the void-run characterisation, the
DEM cell mathematics, the latest-then-lexical product selection and its
covering/allowlist/format filters, the FGDC datum and cell-size parsing
refusals, both repository artifacts' recorded state, and both validators'
semantic tampering rejections (out-of-bound seam, claimed direction,
widened model constant, dropped site, unlocked record, drifted predicate,
geometry-MILES violation, out-of-interval milepost; drifted datum, offsite
URL, stale selection, dropped product, sample byte drift, non-deterministic
sample).

`GODOT_BIN` resolved to the official 4.7.1.stable.mono editor;
`./scripts/check.sh` passed every step: doctor, warning-free dotnet build,
xUnit suite, Ruff, frame-allocation scan, the eight-stage continental
validation (candidate, transfer, edge-path, NHS fill, break dispositions,
reconstruction overlays, NHS conflation, 3DEP products), 225 map-pipeline
tests, 13 PlayGodot unit tests, and the official-Godot save-writing smoke
(80.7 mph peak, save at 56.1 m, 10.706 ms max chunk build, 1.240 ms max
collision build). Gate summary SHA-256
`0c0cd662fb25258d718f70e99f7ea52e3be6bca3785615ed1c071b8a8aec7ccf`; doctor
report SHA-256
`33cb1935e7bc974bbc4cc89452ab1f85a6648768cd2301f08b7df88be56e1dca`.

## What P0-021 still needs

1. **Westbound directed edge selection** over the closed topology (chains
   remain undirected; a shortest undirected chain can cross between opposing
   carriageways).
2. **Reconstruction geometry**: directed carriageways, ramps, lane topology,
   collision, and endpoint connectors through the full ADR-0018 gate battery,
   including the gates deferred at the two overlay sites (Quad Cities carries
   the recorded 77.2 degree corner constraint) and elevation from the locked
   3DEP products.
3. **Corridor elevation acquisition** against the locked product URLs and
   checksummed expectations (the lock is the contract; the bulk acquisition
   is its own bounded stage).
4. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`.
5. **Double-build reproducibility and traversals**: byte-identical double
   builds, walker and high-speed bot traversals on both platforms.
6. **Human gates**: corridor-level geographic plausibility review and the
   coast-to-coast graybox drive.

## Next bounded decision

The westbound directed edge selection over the closed topology: solve and
lock directed, carriageway-consistent edge sequences anchor-to-anchor for
all 12 segments, with the conflated fill spans and authored overlays as
first-class directed elements, under the unchanged tolerances.
