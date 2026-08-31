# Westbound carriageway model and ADR-0017 vertical conditioning

Date: 2026-08-31

Task: P0-021. Executes the slice the
[corridor elevation acquisition](2026-08-31-corridor-elevation.md) prescribed:
the reconstruction-geometry stage's first bounded cut — ADR-0017 vertical
conditioning of the locked raw profile against its characterised artifact
classes, and the reciprocal directed westbound carriageway model under
ADR-0014 over the locked directed sequence, through the ADR-0018 gate
battery this stage stands up (the deferred overlay-site gates included).

Status: **both locks landed.** The conditioned profile removes every
characterised artifact class as bounded, evidence-linked records — the
post-conditioning corridor maximum sustained kilometre is **−6.939 %**
(i70, the Georgetown-hill class of real mountain grade) against the raw
−43.979 % tunnel-overburden artifact, and the corridor's highest point is
now **3,402.08 m**, one metre above the Eisenhower–Johnson bore's authored
3,401.0 m west portal, not the 3,837.26 m ridge above it. The westbound
carriageway models all 12 segments and 12,582 directed elements —
**6,293.994 westbound miles** — as the reciprocal offset pair with
carriageway direction now CLAIMED, 84 of 84 gates passing, the Quad Cities
77.2° corner honored, and both junction-approach backtracks proven to ride
the reciprocal pair exactly.

## ADR-0017 vertical conditioning

`derive-continental-conditioned-profile` →
`data/routes/continental/conditioned-profile-lock.v1.json` (175 KB), a pure
function of the committed corridor-elevation and directed-route locks — no
cache, raster, or network. `validate-continental-conditioned-profile` (the
eleventh `scripts/validate-continental-route.sh` stage) recomputes the whole
derivation from the committed raw elevations under the locked model
constants: windows, classes, replacement values, statistics, paths, and
summary must all reproduce exactly, so a drifted record, widened bound, or
silent smooth cannot validate itself.

### Model and bounds, justified

- **Physical sustained bound: 7.0 % over the locked 1 km window.** Sustained
  interstate design grades reach 6 %, with mountainous exceptions near 7 %
  (AASHTO maximum grades; the corridor's steepest signed real grades are
  I-70's western approaches). A window a conditioning chord cannot bring
  under the bound is a refusal, never a smooth; after conditioning, **every
  1 km window on all twelve segments sits inside the bound** — no open item
  was needed.
- **Interval trigger: 12.0 % per 100 m leg** — the design envelope plus
  double the per-leg sampling noise of bilinear 1/3 arc-second samples on
  legitimately steep pavement, so only unambiguous artifacts condition.
  Intervals between 7 % and 12 % (max remaining 11.98 %) stay recorded
  raster noise for the ADR-0017 package-build grade policy.
- **Water seeding: 4 identical stations** (≥ 300 m of exactly zero grade).
  Hydro-flattened water repeats the identical centimetre value; the
  corridor-wide census finds no such run anywhere except the characterised
  water crossings (Newark tidal reach, Mississippi at Memphis and the Quad
  Cities, Tennessee River, Platte-class crossings). A conditioning chord may
  not anchor on a flat-pair value — boundaries step past water so the
  replacement is a deck chord roadway-to-roadway, and the corridor-wide
  minimum rose from the raw −1.15 m water surface to −0.49 m (a real
  below-NAVD88-zero tidal-area terrain sample, honestly kept).
- **Method: linear chord** between the window's boundary stations (which
  keep their committed raw values), rounded to the locked centimetre
  precision. Windows merge within 1 km and expand deterministically until
  the boundary chord is plausible. Every record carries interval, class,
  method, detections, before (max above/below chord, max interval grade,
  flat run, raw-slice SHA-256) and after (chord grade, replacement values).

### Corrections by artifact class

| Class | Records | Stations replaced | Window length |
| --- | ---: | ---: | ---: |
| bridge_deck_dip | 115 | 239 | 35.4 km |
| terrain_ridge | 20 | 134 | 15.4 km |
| water_surface | 9 | 63 | 7.2 km |
| interval_spike | 8 | 62 | 7.0 km |
| tunnel_bore | 1 | 26 | 2.7 km |
| fill_span_terrain | 1 | 22 | 2.3 km |
| **Total** | **154** | **546** (0.54 % of 101,761) | **70.0 km** |

- **Tunnel bore (authored context, ADR-0017).** The one authored registry
  entry — the Eisenhower–Johnson Memorial Tunnel with CDOT portal
  elevations (east 3,356.8 m, west 3,401.0 m, bore ≈ 2,720 m) — classifies
  the detected i70 86.3–89.0 km ridge window. Measured agreement: entry
  portal delta +11.66 m, exit +1.08 m, window-to-bore ratio 0.993, chord
  grade +1.245 % (bore-consistent). The derivation refuses a tunnel window
  that disagrees with its authored portals, and refuses an authored tunnel
  no window matches.
- **Fill-span terrain.** The Delaware River window (i78 108.0–110.3 km, the
  raw southern-path 12.91 % artifact) overlaps the locked fill-chord span
  and carries it as evidence; its deck chord reads +1.239 %.
- The −182.72 % Glenwood-canyon interval spike, the i80 bridge dip behind
  the raw −10.489 % window, and every other characterised site fall inside
  the 154 records.

### Post-conditioning profile — the road-shaped numbers

| Path | Max sustained (1 km) | Highest point | Total climb (conditioned) |
| --- | ---: | ---: | ---: |
| central-rockies (canonical) | −6.939 % (i70) | 3,402.08 m | 29,547.0 m (raw 31,816.5) |
| northern-plains | −6.540 % (i80) | 2,635.07 m | 28,317.7 m |
| southern-i40 | −6.124 % (i40) | 2,236.69 m | 31,595.7 m |

Per-segment sustained maxima now span −6.939 % to +5.217 % — interstate
design territory on every segment.

## ADR-0014 reciprocal westbound carriageway

`derive-continental-westbound-carriageway` →
`data/routes/continental/westbound-carriageway-lock.v1.json` (41 KB compact
lock; bulk geometry in the ignored `.tools/continental/carriageway/` cache,
digests committed), validated cache-independently by
`validate-continental-westbound-carriageway` as the twelfth script stage.

- **Route identity, proven not assumed.** The directed walk is re-derived
  through the locked machinery (regenerated NHPN base + supplement caches
  and NHS fill cache first reproduced the committed candidate and fill
  locks exactly modulo acquisition timestamps/resumed-page counters) and
  the stage refuses unless every segment reproduces the committed directed
  route lock hash-for-hash.
- **Model.** Each segment's element chain (joints within the locked 1 m
  endpoint tolerance; max observed 0.935 m, exact elsewhere) offsets ±10 m
  in EPSG:5070 with round joins: westbound to the right of westbound
  travel, eastbound the reciprocal opposite — so the source centerline is
  the median axis on the left of each directed carriageway, carrying
  ADR-0014 marking semantics. The 10 m offset (20 m carriageway-centreline
  separation, a typical rural divided interstate cross-section) is an
  **authored uniform model parameter** under ADR-0017's
  observed/derived/authored discipline — never claimed as observed
  cross-section. Pairing is the deterministic reciprocal rule
  `<segment>:<element>:westbound` ↔ `<segment>:<element>:eastbound` per
  carriageway group, `roadway_kind: divided_carriageway`; no opposing
  geometry is synthesized from proximity. **This stage claims
  `carriageway_direction_claimed: true`** — the claim the directed lock
  refused — and the validator enforces that the directed lock's own flag
  stays `false`.
- **Planimetric conditioning (4 records).** Reversal-class vertex turns
  (> 150°; real corners top out at 143.7°, the characterised back-steps
  measure 173.8–180.0°) are doubled travel the source digitized, excised
  with bounded records: the Omaha authored-overlay 1.011 m out-and-back
  (−2.022 m), NHPN joint back-steps at Council Bluffs (−1.164 m), west of
  Fort Wingate NM (a 64 m record overlap, −128.465 m), and Flagstaff
  (−0.585 m).
- **Corner census (24 sites, 25 m tangent lens, > 20° recorded).** 21
  route corners (river-crossing and interchange corners of the designated
  route: Glenwood Canyon 162.7° summed S-curve, downtown OKC 103.3°, East
  LA 135.7°, the Virgin River Gorge cluster, Cajon Pass, Memphis, Des
  Moines…), 2 junction-backtrack approaches (Barstow 143.7°, Salt Lake
  City 28.9°), and **1 overlay corner: the Quad Cities cluster sums 77.0°
  against the overlay lock's recorded 77.2° end-tangent constraint** (±5°
  gate) — the deferred overlay heading gate, now adjudicated by geometry
  that honors the interchange corner through the round-join arc rather
  than a straight chord.

### Gate battery (ADR-0018) — 84 of 84 passed, 0 failed

Per segment: chain_continuity (≤ 1 m, max 0.935), reversal_excision
(≤ 8, max 2), heading_discipline (no reversal-class turn; every corner
> 20° a recorded site), self_intersection (both offsets single simple
LineStrings), station_monotonicity, reciprocal_separation (≥ 19.0 m;
minimum 19.929 m), length_agreement (≤ 0.2 %; max 0.107 % on the
corner-densest i15 Virgin-River-Gorge segment — the bound is the recorded
join-geometry envelope, and its first draft at 0.1 % **rejected that
segment with machine-readable diagnostics**, standing evidence the gates
reject). The **grade gate is adjudicated against the conditioned profile**
(−6.939 % ≤ 7 %, source recorded); curvature_design_radius,
curvature_rate, vertical_curvature, sightline, clearance, collision,
lane_connection, and drivability are recorded as deferred to the
lane-topology/package-build stage with the reason (NHPN's ~80 m-class
vertex noise cannot adjudicate design radii; corner-class discipline is
adjudicated here).

### The junction backtracks ride the reciprocal pair

The reciprocal model resolves the two recorded junction-approach
backtracks exactly: the departing chain opens with the arriving chain's
coordinates mirrored (13 and 19 vertices; lengths 485.939 m and
2,337.242 m against the locked 485.938/2,337.242 within the 5 mm
tolerance), and over that run the departing **westbound** carriageway is
identically the arriving **eastbound** carriageway — Hausdorff gap
**0.000 m at both Barstow and Salt Lake City** — while the two directions'
westbound carriageways hold 20.0 m separation. The doubled travel
occupies each physical roadway once per direction; the anchor turn-around
stays recorded as deferred transfer geometry, never bridged silently.

## Provenance and replay

- Base revision: `995a3d1` (main), branch
  `agent/p0-021-westbound-carriageway-20260831`, PR #103; macOS 26.7
  arm64; uv 0.9.24, Python 3.13.11, Shapely 2.1.2, PyProj 3.7.2,
  GeoPandas 1.1.4, NetworkX 3.6.1.
- Conditioned profile lock SHA-256
  `a3de91ffbe1fecb38cdbdfb0be2ca60805b1f7201c0c25e4400c6f11b2554d9f`;
  westbound carriageway lock SHA-256
  `4607550702f6042412f99c45e12008a7a5c299c817deb62bb70cf29cde570c5b`.
- Replay: `derive-continental-conditioned-profile` and
  `derive-continental-westbound-carriageway` to scratch outputs reproduce
  both committed locks **identically except the top-level `derived_at`**
  (`segments_sha256`/`paths_sha256` stable across passes).
- Nothing continental is committed beyond the two compact locks; the NHPN
  response cache, NHS fill cache, and carriageway geometry stay in the
  ignored `.tools/continental/`; `data/sources/catalog.json` and every
  upstream lock are untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-conditioned-profile
# exit 0: 154 conditioning records over 546 stations, max sustained -6.939%

uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-westbound-carriageway
# exit 0: 12 segments, 12582 elements, 6293.994 westbound miles,
# 24 corner sites, 2 junction backtracks

./scripts/validate-continental-route.sh
# exit 0: all twelve stages green
```

## Verification

`ruff` clean; 250 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`; the repository-root bare `pytest` collection
trap is unchanged). New unit tests cover the conditioning seeds (trigger and
flat-run detection, terminal-leg exclusion), window expansion off flat
pairs, classification and chord replacement per class (ridge, dip,
fill-span evidence), the authored-tunnel agreement refusal, the resampler
and turn census, reversal excision (records, overlay classification, the
removal-cap refusal), corner-site classification (overlay lens, backtrack
span, the surviving-reversal refusal), degenerate/split offset refusals,
backtrack reciprocity (mirror discovery, drifted-length and non-mirror
refusals), both repository locks' recorded state, and both validators'
semantic-tampering rejections (drifted replacement, dropped record, widened
trigger, silent-smooth claim, drifted authored tunnel, digest drift,
summary drift; unclaimed direction, failed gate, narrowed separation,
unknown corner class, reversal-graded corner, drifted/dropped backtrack,
widened model).

`GODOT_BIN` resolved to the official 4.7.1.stable.mono editor;
`./scripts/check.sh` passed every step on commit `6f2183a`: doctor,
warning-free dotnet build, 145 xUnit tests, Ruff, frame-allocation scan,
the twelve-stage continental validation, 250 map-pipeline tests, 13
PlayGodot unit tests, and the official-Godot save-writing smoke (80.7 mph
peak, save at 56.4 m, 12.113 ms max chunk build, 1.868 ms max collision
build). Gate summary SHA-256
`570ba4c1121a12f10d8f04c3cdd8cf3ce57da9426fd9e8c5a2a2b304aedb55e8`.

## What P0-021 still needs

1. **Junction and span geometry**: the conflated NHS spans replacing the
   three traversed fill chords, transfer geometry at the seven
   cross-segment junctions and the two backtrack turn-arounds, and the
   authored endpoint connectors (after which ADR-0024's portal-to-portal
   run length can be published).
2. **Lane topology, ramps, and collision** over the carriageway model with
   the deferred ADR-0018 gates, then the GeoPackage/FlatBuffer package
   build (which materializes the cached carriageway geometry) under
   ADR-0019 budgets.
3. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`.
4. **Double-build reproducibility and traversals** on both platforms.
5. **Human gates**: geographic plausibility and the coast-to-coast drive.

## Next bounded decision

The authored endpoint connectors plus the conflated-span replacement of the
three fill chords — the two remaining geometry inputs that close the
portal-to-portal corridor. The connectors publish ADR-0024's run length;
the conflated spans replace the last chord-class geometry on the directed
chain with source-asserted road geometry, both through the same gate
battery this stage stood up.
