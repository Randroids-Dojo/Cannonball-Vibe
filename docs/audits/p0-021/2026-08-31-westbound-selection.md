# Westbound directed edge selection over the closed corridor

Date: 2026-08-31

Task: P0-021. Executes the slice the
[conflation and 3DEP lock](2026-08-31-conflation-and-3dep-lock.md) prescribed:
turn the undirected 12/12 chain into the directed, ordered westbound route with
a locked corridor distance — every segment traversed from its ADR-0024
from-anchor to its to-anchor, every element carrying its orientation against
source geometry, entry/exit measures, and cumulative geodesic stationing.

Status: **directed route locked.** All 12 segments traverse anchor-to-anchor
over exactly the locked closed topology (the derivation refuses any traversal
that does not reproduce the edge-path and chain-connectivity locks to the
millimetre). The corridor's authoritative anchor-to-anchor distance is now
locked: the canonical Central Rockies NY→LA corridor measures
**4,492,918.463 m = 2,791.77 mi** (GRS80 geodesic, `nj-us46-i80` →
`ca-redondo-i405-ca107`). The carriageway-level westbound direction remains
reconstruction-stage output under ADR-0014 and the lock refuses to claim it.
The 1 m endpoint tolerance and 25 m anchor snap limit are unchanged.

## What the directed lock asserts — and what it does not

`derive-continental-directed-route` →
`data/routes/continental/directed-route-lock.v1.json` (validated
cache-independently by `validate-continental-directed-route` as the ninth
`scripts/validate-continental-route.sh` stage) walks each segment's snapped
graph — the edge-path solve for the eight NHPN-connected segments; the bridged
fill/overlay graph with the Q-034c/d edge-split anchor fallback for the four
chained ones — and records the traversal from-anchor to to-anchor in the route
selection's Atlantic-to-Pacific order. Per element it records:

- **kind and provenance**: `nhpn_edge` (12,575), `nhpn_split_edge` (2: the
  Q-034c/d sub-edges at the i78/i80 from-anchors, with their exact
  `part_range_m`), `nhs_fill_chord` (3), `authored_overlay_chord` (2) —
  12,582 elements in all;
- **direction**: `reversed_for_travel` relative to the locked source geometry
  (12,196 of 12,582 elements travel against digitization order — NHPN
  digitizes these corridors predominantly eastbound);
- **entry/exit measures**: NHPN record mileposts oriented by travel for whole
  single-part records; honestly `null` on split sub-edges and multi-part
  records rather than interpolated (measures parametrise and key — never a
  length, per the conflation lock's calibrated-axis finding); NHS state-LRS
  seam measures on fill chords, from the conflation lock's seam
  correspondences;
- **two lengths**: the EPSG:5070 planimetric length the chain and edge-path
  locks already recorded (reproduced exactly, not approximated) and a GRS80
  geodesic length over the locked EPSG:4326 coordinates, with
  `cumulative_geodesic_m` stationing cascading from each segment's from-anchor
  node;
- **cross-check inputs**: the record's own `MILES` assertion prorated by
  traversed metric length, and its `FACILITY_T` code.

Not claimed: lane geometry, a reciprocal westbound carriageway (ADR-0014
reconstruction output — NHPN models these facilities as a single centerline,
and the lock's `westbound_selection.carriageway_direction_claimed` is `false`,
enforced by the validator), and ADR-0024's portal-to-portal run length (the
two authored endpoint connectors remain unlocked; see below).

## The authoritative corridor distance

| Figure | Planimetric (EPSG:5070) | Geodesic (GRS80) |
| --- | ---: | ---: |
| Canonical NY→LA corridor (`central-rockies`, 7 locked segments) | 4,473,876.594 m = 2,779.94 mi | **4,492,918.463 m = 2,791.77 mi** |
| Northern Plains alternative (7 locked segments) | 4,582,040.995 m | 4,600,070.093 m = 2,858.351 mi |
| Southern I-40 alternative (6 locked segments) | 4,668,274.829 m | 4,691,103.585 m = 2,914.917 mi |
| All 12 locked segments | 10,129,345.424 m = **6,294.1 mi** (equals the chained-corridor reference exactly) | 10,174,312.843 m = 6,322.025 mi |

- **Scope.** The figure is the locked highway corridor anchor-to-anchor. The
  authored endpoint connectors stay excluded and recorded: `nyc-start-to-i80`
  (East 31st Street portal → US 46/I-80 anchor, 40,181.7 m straight-line
  context — the connector spans the Lincoln Tunnel, NJ 495, NJ 3, and US 46)
  and `redondo-access-to-finish` (I-405/CA 107 anchor → Portofino Way portal,
  6,024.2 m). ADR-0024's portal-to-portal run length remains unpublished until
  those connectors are checksum-locked; the previous ledger caution ("no
  authoritative distance until reconstruction") is superseded in this bounded
  sense only — the corridor anchor-to-anchor figure is now derivable from
  locked geometry alone and is claimed, while the run length and the
  carriageway-level refinement remain downstream.
- **Fidelity.** Source-centerline fidelity: traversed fill and overlay chords
  contribute their pinned boundary chords, exactly as the locked chains do.
  Reconstruction replaces the three traversed fill chords with their conflated
  NHS spans (Big-I +10.352 m, Rifle −8.565 m, Delaware River +356.072 m;
  recorded per site, total +357.859 m) and owns junction geometry (see the
  backtrack finding).

### Sanity gates and the stated bound

1. **Planimetric identity (exact).** Per segment, the directed traversal's
   planimetric length equals the locked reference exactly — the eight
   edge-path lock `length_meters` values and the four chain-connectivity
   `chain_length_meters`/per-ancestry values, element sequence included for
   the connected segments — and the 12-segment total re-rounds to precisely
   the locked 6,294.1 mi. The validator enforces all of these as equalities;
   the bound on the planimetric side is zero.
2. **Geodesic-planimetric agreement (1 %).** EPSG:5070 is equal-area, not
   equidistant; inside the corridor's latitude band (33.8–41.3° N, spanning
   the 29.5/45.5 standard parallels) its scale error stays under one percent.
   Bound: |geodesic − planimetric| ≤ 1 % · planimetric + 2 mm rounding, per
   element and per segment. Measured: corridor-wide +0.4439 %, per-segment
   envelope −0.4661 % (i15-salt-lake) to +0.6107 % (i10), worst element
   0.86 % (the Rifle fill chord, whose pinned separation was measured in the
   metric CRS).
3. **Anchor order, no repeats, no gaps.** Each path's anchor sequence is
   validated against the ADR-0024 selection; elements may not repeat within a
   composed path except in the one measured junction-backtrack shape below;
   consecutive elements share snapped nodes by construction, and the seven
   cross-segment junctions record continuity gaps of 0.000 m (five), 15.866 m
   (Ontario), and 24.434 m (West LA) against the 2 × 25 m junction limit —
   each side already within the unchanged anchor snap limit.

## The NHPN MILES cross-check — a characterised divergence

Per the conflation audit's finding, distance is never built on measure deltas;
the cross-check aggregates the source's own per-record `MILES` assertion
(prorated by traversed metric length for splits and multi-part records)
against the same records' geodesic geometry:

- **Corridor aggregate: 6,138.639 MILES-miles = 9,879,181 m vs 10,169,062 m
  NHPN geodesic → −2.85 %.** Per-segment envelope −4.35 % (i80 New Jersey) to
  +3.31 % (i15 Salt Lake).
- Per record (12,575 traversed): median MILES/geodesic ratio 0.9606; only
  8.3 % agree within 1 %, 73.6 % within 5 %, 99.1 % within 10 %; extremes
  0.665–1.612.
- **Finding:** NHPN's MILES field (VERSION-stamped 2014.05 on these records)
  is a coarse length assertion that does not track its own geometry the way
  the NHS/ARNOLD MILES field does (the conflation lock proved ≤ 0.91 % on
  every fill record). This is consistent with NHPN's declared role — coarse
  topology, not measurement. The lock records the aggregation as the source's
  cross-check, bounds it loosely at 6 % (tripping material drift beyond the
  characterised envelope without absorbing the envelope), and keeps distance
  authority with the locked geometry.

## Junction-approach backtracks — a measured anchor-model fact

Composing consecutive segments exposed that two locked anchors sit on pavement
off the through junction, so the arriving traversal's final elements are the
departing traversal's first elements travelled in the opposite orientation:

| Anchor | Shared elements | One-way length | Mechanism |
| --- | ---: | ---: | --- |
| `ca-barstow-i40-i15` | 4 | 485.938 m | The anchor (I-40/I-15 midpoint) resolves to a node 486 m from the I-15 through junction on CA key `000000001501071` (mp 0.0–0.424). |
| `ut-salt-lake-i80-i15` | 6 | 2,337.242 m | The I-80/I-15 anchor sits inside the Salt Lake City I-80/I-15 signed concurrency; both segments' candidate sets carry the concurrency records. |

The composition permits exactly this shape — mirrored suffix/prefix, opposite
orientation, consecutive segments — and refuses any other repetition. The
canonical figure therefore includes 971.876 m of doubled junction-approach
travel at Barstow (the northern alternative adds 4,674.484 m at Salt Lake
City); the doubled lengths are recorded per junction, and junction/transfer
geometry is reconstruction-stage output. This is a genuine finding about the
`midpoint_between_segments` anchor derivation, recorded, not forced.

## Direction evidence coverage

Primary evidence is anchor-to-anchor chain continuity on the locked closed
topology — a simple path forces every element's orientation. Corroboration and
its gaps, all recorded in the lock:

- **Milepost trend**: 12,188 of 12,577 NHPN elements decrease along travel
  (the dominant westbound signature on these LRS axes), 386 increase in 37
  contiguous key-local runs (key-direction facts — e.g. CA I-15/I-405 runs
  where the state axis runs against the travel direction), 1 is flat
  (zero-width milepost interval on i80 New Jersey), 2 are unmeasured (the
  Q-034c/d split sub-edges, whose mileposts are honestly null).
- **NHS seam measures**: all three traversed fill chords read decreasing
  measure along travel (Big-I 159.370→158.147, Rifle 85.328→85.133, Delaware
  River 2.669→0.212).
- **FACILITY_T census**: 12,557 elements code 2, 17 code 4, 3 code 0 — NHPN
  offers no per-carriageway direction attribute on this corridor, confirming
  the 2026-08-14 correction: the directed westbound carriageway must come from
  ADR-0014 reconstruction, not from this source.
- **Thin sites (5 elements)**: the two authored overlay chords (authored
  geometry, no source direction — 1.011 m and 9.190 m), the two split
  sub-edges, and the one flat-milepost record. Each is listed by element index
  in its segment's `thin_direction_elements`; none is load-bearing beyond
  chain continuity.

## Fill spans on and off the directed chain

Traversed (3): the Big-I, Rifle, and Delaware River chords — exactly the fills
whose NHPN voids are real. Locked but not on the directed chain (2):
`i15-salt-lake-to-cove-fort--component-00-02` (the segment is NHPN-connected
since the Payson acquisition; the conflation lock records no NHPN void over
the span) and `i40-i81-to-barstow--component-02-03` (locked NHPN carries the
traversal across the span; the conflation lock measured every station within
the 80 m lens). Both stay locked and recorded with the reason.

## Per-segment directed breakdown

| Segment | Solve | Elements | Planimetric m | Geodesic m | Geo−plan | MILES div. |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| i80-new-jersey-to-big-springs | chain (2 overlays, 1 split) | 1,936 | 2,504,070.528 | 2,518,867.855 | +0.59 % | −4.35 % |
| i76-big-springs-to-denver | NHPN | 264 | 299,259.270 | 300,331.444 | +0.36 % | −2.24 % |
| i70-denver-to-cove-fort | chain (Rifle fill) | 487 | 804,576.944 | 807,795.394 | +0.40 % | −2.29 % |
| i80-big-springs-to-salt-lake | NHPN | 504 | 930,447.931 | 935,038.076 | +0.49 % | −3.64 % |
| i15-salt-lake-to-cove-fort | NHPN | 246 | 281,552.684 | 280,240.380 | −0.47 % | +3.31 % |
| i78-holland-tunnel-to-i81 | chain (Delaware fill, 1 split) | 274 | 231,084.599 | 232,462.650 | +0.60 % | −3.96 % |
| i81-i78-to-i40 | NHPN | 763 | 845,898.683 | 847,004.485 | +0.13 % | −0.55 % |
| i40-i81-to-barstow | chain (Big-I fill) | 6,558 | 3,366,484.933 | 3,386,648.789 | +0.60 % | −3.49 % |
| i15-cove-fort-to-barstow | NHPN | 617 | 641,163.238 | 640,936.071 | −0.04 % | +0.40 % |
| i15-barstow-to-ontario | NHPN | 316 | 117,306.271 | 117,022.005 | −0.24 % | +1.76 % |
| i10-ontario-to-i405 | NHPN | 460 | 87,564.209 | 88,098.974 | +0.61 % | −3.92 % |
| i405-west-la-to-ca107 | NHPN | 157 | 19,936.134 | 19,866.720 | −0.35 % | +2.49 % |

## Provenance and replay

- Base revision: `4ecca99` (main), branch
  `agent/p0-021-westbound-directed-selection-20260831`, PR #99; macOS 26.7
  arm64; uv 0.9.24, Python 3.13.11, GeoPandas 1.1.4, NetworkX 3.6.1,
  PyProj 3.7.2, Shapely 2.1.2.
- The NHPN response cache (base plus supplements) was regenerated from the
  live service before anything else: the base acquisition reproduced the
  twelve committed segment snapshots exactly modulo `acquired_at` and
  `resumed_pages` (15,525 candidates; live metadata still byte-identical to
  `5150b91e…`), and the supplements acquisition reproduced the five scoped
  sites' 28 records (union 15,553).
- The derivation consumes only checksum-locked inputs plus that cache — no
  network access — and validates all eight upstream artifacts before walking.
  Two consecutive derivations produce identical locks modulo `derived_at`
  (`segments_sha256 89aea1e26ea3…`, `paths_sha256 7d837df53e8a…` both stable).
- Directed route lock SHA-256:
  `cd31ea3193a755f06349fdf1cea814775d5de700e04a75113f70e68d18793294`.
- Nothing continental is committed beyond the lock artifact itself; caches
  stay in the ignored `.tools/continental/`; `data/sources/catalog.json` and
  every upstream lock are untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-directed-route
# exit 0: 12 segments, 12,582 elements, corridor 6,322.025 mi geodesic,
# canonical 2,791.77 mi

uv run --project tools/map_pipeline --frozen cannonball-map \
  validate-continental-directed-route
# exit 0: cache-independent; recomputes paths, corridor, and summary through
# the same helpers the derivation used

./scripts/validate-continental-route.sh
# exit 0: all nine stages green
```

## Verification

`ruff` clean; 231 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`; the repository-root bare `pytest` collection
trap is unchanged). New unit tests cover the directed walk's orientation,
milepost, and prorated-MILES semantics on synthetic records, the
increasing-run computation, the junction-backtrack shape (accepting only the
mirrored opposite-orientation form and refusing same-direction,
non-consecutive, and interior overlaps), the geodesic helper against the GRS80
equator degree, the repository artifact's recorded state (corridor tie to
6,294.1 mi, the 2,791.77 mi canonical figure, the two backtracks, the two
off-chain fills), and the validator's semantic tampering rejections (claimed
carriageway direction, widened MILES bound, drifted pin, drifted element
length, broken stationing cascade, unlocked record, drifted fill chord,
drifted seam measure, interpolated split milepost, drifted authoritative
distance, drifted trend census).

`GODOT_BIN` resolved through `scripts/godot.sh` (official 4.7.1.stable.mono);
`./scripts/check.sh` passed every step: doctor, warning-free dotnet build,
xUnit suite, Ruff, frame-allocation scan, the nine-stage continental
validation, 231 map-pipeline tests, 13 PlayGodot unit tests, and the
official-Godot save-writing smoke (80.7 mph peak, save at 56.1 m, 10.767 ms
max chunk build, 1.215 ms max collision build). Gate summary SHA-256
`ceaf42a1833d8adb1e576efe7cccf9fd43ad587131af4fd55b071588650989e9`; doctor
report SHA-256
`33cb1935e7bc974bbc4cc89452ab1f85a6648768cd2301f08b7df88be56e1dca`.

## What P0-021 still needs

1. **Reconstruction geometry**: reciprocal directed westbound carriageways
   (ADR-0014), ramps, lane topology, collision, and endpoint connectors
   through the full ADR-0018 gate battery — including the deferred gates at
   the two overlay sites (Quad Cities carries the recorded 77.2° corner
   constraint), the conflated fill spans replacing their chords, and the two
   junction-backtrack anchors' transfer geometry.
2. **Corridor elevation acquisition** against the locked 3DEP product URLs.
3. **Authored endpoint connectors** for the three non-NHPN segments, after
   which ADR-0024's portal-to-portal run length can be published.
4. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`.
5. **Double-build reproducibility and traversals**: byte-identical double
   builds, walker and high-speed bot traversals on both platforms.
6. **Human gates**: corridor-level geographic plausibility review and the
   coast-to-coast graybox drive.

## Next bounded decision

Corridor elevation acquisition against the locked 3DEP product URLs — the
directed lock now fixes exactly which geometry needs elevation, and the bulk
acquisition (124 cells, 51.68 GB, checksummed against the locked discovery
declarations) is the remaining input the reconstruction-geometry stage needs
before it can build the directed westbound carriageway.
