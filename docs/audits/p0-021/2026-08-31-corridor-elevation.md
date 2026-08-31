# Corridor elevation acquisition against the locked 3DEP product declarations

Date: 2026-08-31

Task: P0-021. Executes the slice the
[westbound selection](2026-08-31-westbound-selection.md) prescribed: the bulk
acquisition of all 124 locked 1/3 arc-second 3DEP tiles, verified end to end
against the [product lock](2026-08-31-conflation-and-3dep-lock.md)'s
declarations, and the corridor's first elevation evidence over the locked
westbound directed route.

Status: **all 124 tiles verified and the corridor elevation profile locked.**
Every tile was downloaded from its pinned immutable dated URL inside the
catalog allowlist and held to its locked declaration; the directed route was
sampled at 100 m geodesic stations (101,761 stations, zero nodata) with
per-segment statistics and per-path composition committed in
`data/routes/continental/corridor-elevation-lock.v1.json`, validated
cache-independently by `validate-continental-corridor-elevation` as the tenth
`scripts/validate-continental-route.sh` stage. One genuine anomaly was found
and characterised: TNM's catalog misdeclares the size of exactly 6 of the 124
products (registered as Q-036); no tile failed any content check.

## Acquisition design

`acquire-continental-corridor-elevation` executes the product lock's contract:

- **Verification per tile.** The download URL must be the locked product URL
  inside the catalog allowlist; the streamed byte count must equal the
  discovery declaration (see the census below for the six characterised
  exceptions); the SHA-256 must equal the product lock's pinned hash where it
  pins one (the three sample tiles) and is recorded as the first-acquisition
  pin otherwise; and every tile - not a sample, all 124 - passes the full
  raster inspection from the sample-tile precedent: CRS EPSG:4269, exact
  1/3 arc-second pixels (1 ppm tolerance), a single float32 band, -999999
  nodata, full nominal-cell coverage.
- **Checkpointed and resumable.** Each tile writes a checkpoint (URL, hash,
  byte count, response metadata, acquisition timestamp, raster facts) and
  each cell an extraction checkpoint (station set hash, tile hash, sampled
  elevations), in the exact discipline of the prior acquisitions; a replay
  resumes every cell without re-downloading anything.
- **Disk strategy: verify-and-release.** The machine had 31 GiB free against
  a 52.34 GB corpus, so the acquisition ran with `--release-tiles`: each
  raster is deleted after verification and station extraction, the cache
  retains hashes, raster facts, and elevations, and peak disk usage stayed
  near one tile (~600 MB). The committed artifact records the retention
  policy (`tile_retention: released_after_verification`).
- **Route identity, proven not assumed.** Before any sampling, the directed
  walk is re-derived through the very machinery the directed lock used
  (regenerated NHPN base + supplement caches and NHS fill cache first
  reproduced the committed candidate, fill, and directed locks exactly modulo
  acquisition timestamps), and the stage refuses unless every segment's walk
  record reproduces the committed directed route lock's segment record
  hash-for-hash - elevation cannot be sampled for a different route than the
  one locked.

## The TNM size-declaration census (Q-036)

The first run refused at cell n36w102: the tile carried 370,105,790 bytes
where discovery declared 361,416. Characterisation against the source itself
proved the declaration wrong, not the artifact, and a HEAD census of all 124
locked URLs bounded the defect exactly:

| Cell | Declared (TNM) | Actual (S3 Content-Length) | Character |
| --- | ---: | ---: | --- |
| n36w102 | 361,416 | 370,105,790 | sub-megabyte nonsense declaration |
| n36w103 | 338,581 | 346,722,950 | sub-megabyte nonsense declaration |
| n36w104 | 363,746,466 | 364,271,986 | -0.14% stale |
| n38w080 | 543,397,409 | 486,226,211 | +11.8% stale |
| n42w086 | 430,468,098 | 429,895,986 | +0.13% stale |
| n42w087 | 400,229,668 | 399,510,396 | +0.18% stale |

Every affected S3 object was last modified 2022-12-03 - years before the
product lock's discovery snapshot - so the defect is TNM's catalog size
index, not object drift; live re-discovery still asserts the defective
values (items lastUpdated 2026-06-08), and the S3 objects' own
Content-Lengths match the downloads byte for byte. All six rasters pass the
full inspection. The six tiles are held to characterised pins in
`ELEVATION_DECLARED_SIZE_EXCEPTIONS` - measured bytes **plus SHA-256**,
strictly tighter than the defective declarations they stand in for - the
artifact records each `declared_size_exception`, the validator refuses an
unpinned mismatch anywhere and a pin claimed where none is needed, and the
remaining 118 tiles stay under exact byte equality. Registered as Q-036
(report upstream / retire pins if the catalog is corrected). A corollary:
the previously reported "51.68 GB" corpus size was an aggregate of the
defective declarations; the measured corpus is **52,336,020,282 bytes
(52.34 GB)**.

## Verification results

- 124 of 124 tiles verified: 118 byte-equal to discovery, 6 under
  characterised pins; the three product-lock sample hashes (n34w119,
  n39w110, n42w112) matched end to end; zero raster refusals; zero nodata
  stations; publication dates 2019-09-16 to 2026-08-12 exactly as locked.
- Total 52,336,020,282 bytes acquired and hashed; every SHA-256 is now
  recorded in the committed artifact (first-acquisition pins for the 121
  the product lock did not sample).
- TNM/S3 transient flakiness: none surfaced (the bounded-retry transport
  from the product-lock stage was in place; no download failed).
- Three interrupted-and-resumed passes (the two declaration refusals, then
  completion) exercised the checkpoint discipline for real: each resume
  re-verified completed cells from checkpoints without re-downloading.

## Corridor elevation profile

Stations lie on each directed segment's geodesic stationing - every 100 m
from the from-anchor node plus the terminal station - positioned by
planimetric interpolation within the containing element at the station's
geodesic fraction; junction gaps carry no stations. Sampling is bilinear
between raster cell centres (the 2026-08-14 interpolation finding), refused
on nodata. Elevations are committed at centimetre precision; every statistic
is recomputed by the validator from the committed values. **No smoothing or
conditioning is applied**: this is the raw 1/3 arc-second baseline profile;
ADR-0017 grade smoothing remains a package-build policy, and grades are
measured on whole-interval legs and windows only (a terminal leg can be
arbitrarily short, where centimetre-rounded elevations quantise into
meaningless grades).

| Segment | Stations | Min m | Max m | Climb m | Descent m | Max sustained (1 km) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| i80-new-jersey-to-big-springs | 25,190 | 88.18 | 1,041.10 | 14,905.01 | 13,958.99 | -10.489% |
| i76-big-springs-to-denver | 3,005 | 1,040.90 | 1,625.68 | 1,541.57 | 960.02 | 3.127% |
| i70-denver-to-cove-fort | 8,079 | 1,232.25 | 3,837.26 | 9,454.23 | 9,239.20 | -43.979% |
| i80-big-springs-to-salt-lake | 9,352 | 1,037.27 | 2,635.07 | 6,330.23 | 6,078.62 | -10.581% |
| i15-salt-lake-to-cove-fort | 2,804 | 1,290.24 | 1,873.22 | 2,109.52 | 1,564.55 | 5.217% |
| i78-holland-tunnel-to-i81 | 2,326 | -1.15 | 256.62 | 2,437.57 | 2,281.90 | 12.910% |
| i81-i78-to-i40 | 8,472 | 92.07 | 804.56 | 7,755.18 | 7,524.89 | 6.824% |
| i40-i81-to-barstow | 33,868 | 49.64 | 2,236.69 | 21,092.41 | 20,808.69 | -6.124% |
| i15-cove-fort-to-barstow | 6,411 | 280.58 | 2,011.35 | 4,210.83 | 5,375.74 | -5.823% |
| i15-barstow-to-ontario | 1,172 | 305.45 | 1,278.03 | 1,019.52 | 1,386.75 | -5.512% |
| i10-ontario-to-i405 | 882 | 21.02 | 358.89 | 564.62 | 823.63 | -5.511% |
| i405-west-la-to-ca107 | 200 | 6.93 | 47.50 | 120.76 | 143.60 | -1.409% |

Path composition (per-segment stationing never spans a junction, so the
composition is exact):

| Path | Distance | Highest point | Total climb | Total descent | Max sustained |
| --- | --- | --- | ---: | ---: | --- |
| central-rockies (canonical, NY→LA) | 2,791.77 mi | 3,837.26 m (i70, station 88.2 km) | 31,816.54 m | 31,887.93 m | -43.979% (i70, station 88.2 km) |
| northern-plains | 2,858.351 mi | 2,635.07 m (i80, station 292.9 km) | 29,260.49 m | 29,331.88 m | -10.581% (i80) |
| southern-i40 | 2,914.917 mi | 2,236.69 m (i40, station 2,832.7 km) | 32,990.06 m | 32,969.46 m | 12.910% (i78) |

## Surface-model artifacts, characterised honestly

The extreme figures above are facts of a bare-surface model sampled along a
centerline, in exactly the class the 2026-08-16 survey-departure
decomposition established, and they are recorded, not road grades:

- **The corridor's highest sample and steepest sustained window are the same
  feature and it is not pavement.** At i70 stations 86-92 km (cell n40w106)
  the profile rises 3,351 → 3,837 m and falls back to 3,402 m within ~3 km:
  the Continental Divide ridge **above the Eisenhower-Johnson Memorial
  Tunnel bore**, whose roadway tops out near 3,401 m. The -43.979% window is
  the west face of that overburden ridge. The canonical path's true
  road-grade profile through here is reconstruction-stage output (tunnel
  vertical alignment), not a raster fact.
- **The -182.72% single-interval extreme** (i70 station ~231.5 km) is a
  ~218 m spike up and back down within ~400 m - a canyon-wall/structure
  class artifact of the kind the ADR-0017 spike-median conditioning exists
  to remove at package build.
- **The southern path's 12.910% sustained window starts at i78 station
  108.3 km - inside the Delaware River fill chord** (stations
  108,171-111,219 m): the chord descends to the river valley and climbs the
  Pennsylvania bank where the real road rides the high bridge. Fill-chord
  profiles sample the terrain under the span; ADR-0026 conflated span
  geometry and reconstruction bridge decks supersede them.
- **The i80 -10.489% window** (~station 497.2-498.2 km) brackets an ~80 m
  valley dip under a bridge crossing; the same class.
- **The corridor's lowest sample, -1.15 m** (i78 station ~9.8 km), is a flat
  run of identical values: tidal water surface near the Newark Bay/Passaic
  crossings, sampled under the viaducts. Slightly-below-NAVD88-zero water is
  plausible and the flat run is self-evidently not pavement.

Total climb figures (e.g. 31,816.54 m NY→LA westbound on the canonical path)
are sums over the raw 100 m profile and include raster noise and the
artifact classes above; they are upper bounds on conditioned road climb.

## Replay and provenance

- Base revision: `8851e11` (main), branch
  `p0-021-corridor-elevation-20260831`, PR #102; macOS 26.7 arm64; uv
  0.9.24, Python 3.13.11, Rasterio 1.5.0, PyProj 3.7.2, Shapely 2.1.2,
  NetworkX 3.6.1.
- The NHPN response cache (base + supplements) and the NHS fill cache were
  regenerated from the live services first and reproduced the committed
  candidate and fill locks exactly modulo acquisition timestamps; a full
  `derive-continental-directed-route` against the regenerated cache
  reproduced the committed directed lock exactly modulo `derived_at`.
- The committed artifact is the fully-resumed replay: a first complete pass
  downloaded and verified everything (38.7 GB in its final leg), and the
  committed lock was then written by a second pass resuming all 124 cells
  from checkpoints. A third replay to a scratch path reproduced the
  committed file **identically except the top-level `acquired_at`**; the
  content digests are stable across all passes:
  `tiles_sha256 c11f8bab5df6…`, `profile_sha256 de99cc59a59d…`,
  `paths_sha256 949f5570ebaf…`. Committed lock SHA-256
  `082a1e0432edac2a89a3c561b1f2ee121692a68fde3226087fdb43631ac4cac7`.
- All rasters, checkpoints, and extractions stay in the ignored
  `.tools/continental/3dep/` cache; nothing continental is committed beyond
  the compact lock, and `data/sources/catalog.json` is untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-corridor-elevation --release-tiles
# exit 0: 124 tiles verified, 101761 stations, highest 3837.26 m

./scripts/validate-continental-route.sh
# exit 0: all ten stages green (candidate, transfer, edge-path, NHS fill,
# break dispositions, reconstruction overlays, NHS conflation, 3DEP
# products, directed route, corridor elevation)
```

## Verification

`ruff` clean; 237 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`; the repository-root bare `pytest` collection
trap is unchanged). New unit tests cover the station-offset grid and
terminal handling, the profile statistics (extremes, climb/descent,
whole-interval grade restriction, tie-to-first, refusals), station-to-cell
resolution with the boundary fallback and its refusal, the directed-walk
geometry sink (travel-direction orientation and chain continuity), the
repository artifact's recorded state, and the validator's semantic-tampering
rejections (raised station, unrounded elevation, sample-hash drift, byte
drift, dropped tile, widened interval, claimed smoothing, summary drift,
stripped declaration exception, unneeded declaration exception).

`GODOT_BIN` resolved to the official 4.7.1.stable.mono editor;
`./scripts/check.sh` passed every step: doctor, warning-free dotnet build,
145 xUnit tests, Ruff, the ten-stage continental validation (candidate,
transfer, edge-path, NHS fill, break dispositions, reconstruction overlays,
NHS conflation, 3DEP products, directed route, corridor elevation), 237
map-pipeline tests, 13 PlayGodot unit tests, and the official-Godot
save-writing smoke (80.7 mph peak, save at 56.1 m, 11.388 ms max chunk
build, 1.204 ms max collision build). Gate summary SHA-256
`52ab1189cb28e8cffff2337050a65706907292fb9867e1b4c52fab7de3f8142a`.

## What P0-021 still needs

1. **Reconstruction geometry** through the full ADR-0018 gate battery:
   reciprocal directed westbound carriageways under ADR-0014, the deferred
   overlay-site gates (Quad Cities 77.2-degree corner constraint), the
   conflated fill spans replacing their chords, transfer geometry at the two
   junction-backtrack anchors, and ADR-0017 vertical conditioning against
   this profile (which now carries the recorded artifact classes to remove).
2. **Authored endpoint connectors**, after which ADR-0024's portal-to-portal
   run length can be published.
3. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`.
4. **Double-build reproducibility and traversals** on both platforms.
5. **Human gates**: geographic plausibility and the coast-to-coast drive.

## Next bounded decision

Reconstruction geometry is now fully unblocked - the directed sequence, the
conflation model, and the corridor elevation are all locked. The next slice
is the reconstruction-geometry stage's first bounded cut: the reciprocal
directed westbound carriageway model under ADR-0014 over the locked directed
sequence, with the ADR-0018 gate battery scaffolding (including vertical
profile conditioning grounded in this profile's characterised artifact
classes).
