# Junction transfer geometry and the backtrack turn-arounds

Date: 2026-08-31

Task: P0-021. Executes the slice the
[endpoint connectors](2026-08-31-endpoint-connectors.md) prescribed: transfer
geometry at the seven cross-segment junctions and the two backtrack
turn-arounds (Barstow, Salt Lake City) the
[westbound carriageway audit](2026-08-31-westbound-carriageway.md) recorded as
deferred transfer geometry — the last route-level geometry before lane
topology and collision can run the deferred ADR-0018 gate battery.

Status: **junction geometry locked.**
`derive-continental-junction-geometry` →
`data/routes/continental/junction-geometry-lock.v1.json` (95 KB,
self-contained movement geometry), validated cache-independently by
`validate-continental-junction-geometry` as the fourteenth
`scripts/validate-continental-route.sh` stage. All **12 movements** across
the locked paths — 10 through transfers at 8 anchors plus the 2 authored
turn-around loops — carry **160 of 160 passing gates**, with the
sourced-vs-authored breakdown recorded per movement.

## Scope: seven junctions, two turn-arounds, twelve movements

The directed lock's path junctions deduplicate to 12 distinct movements at 9
non-endpoint transfer anchors. Seven anchors are plain cross-segment
junctions (Big Springs, Denver, Cove Fort, the I-78/I-81 split, the
I-81/I-40 merge, Ontario, West LA); Barstow and Salt Lake City are the two
backtrack turn-around anchors — Barstow additionally hosts the southern
path's plain I-40→I-15 through movement, so through movements span 8 anchors.
Shared-approach anchors carry one movement per locked (from, to) pair: Big
Springs forks the canonical I-76 and northern I-80 departures from one
arriving trunk; Cove Fort merges the canonical I-70 and northern I-15
arrivals into one departure.

## The through-transfer model (ADR-0013 over ADR-0014)

Each movement is the **westbound offset of the composed chain window**: the
arriving chain's final 250 m and the departing chain's initial 250 m (cut at
the exact interpolated station so the seam lands on locked geometry), joined
across the directed lock's recorded junction continuity gap, conditioned of
reversal-class artifacts, and offset through the identical ADR-0014
round-join machinery as the carriageway model. The derive **refuses unless
the carriageway cache reproduces the committed westbound carriageway lock's
geometry digests** (westbound and eastbound per segment, chain within the
millimetre quantization envelope), so the movements are sourced from locked
geometry, proven not assumed.

ADR-0013 control-line continuity is adjudicated at both attachment seams:
the transfer endpoint must sit on the segment's locked westbound carriageway
(measured ≤ 0.0006 m against the 0.01 m bound) with the identical-window
25 m lens heading agreeing to ≤ 0.001° (0.5° bound). The junction corner
itself is a recorded `junction_transfer_corner` exception site — exactly the
treatment the locked corridor gives its route corners — and its
speed-designed ramp refinement is deferred to lane topology with the
carriageway lock's standing NHPN-noise reason (~80 m vertex class cannot
adjudicate design radii).

### Per-movement results

| Movement (anchor: from → to) | Paths | Provenance | Length (m) | Peak lens turn | Excisions | Notes |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Big Springs: i80-nj → i76 | canonical | derived | 500.012 | 0.06° | 0 | straight mainline continuation |
| Big Springs: i80-nj → i80-slc | northern | derived | 490.824 | 40.45° | 0 | northern fork corner recorded |
| Denver: i76 → i70 | canonical | derived | 502.216 | 3.65° | 0 | |
| Cove Fort: i70 → i15-cb | canonical | derived | 509.238 | 47.13° | 0 | opposing approach 15.33 m recorded |
| Cove Fort: i15-slc → i15-cb | northern | derived | 498.151 | 2.16° | 0 | I-15 continues straight |
| PA: i78 → i81 | southern | derived | 500.044 | 2.69° | 0 | |
| TN: i81 → i40 | southern | derived | 500.894 | 4.33° | 0 | |
| Barstow: i40 → i15-bo | southern | derived | 499.867 | 3.11° | 0 | through movement at the turn-around anchor |
| Ontario: i15-bo → i10 | all three | derived + authored bridge (15.986 m) | 496.425 | 69.60° | 0 | recorded 15.866 m continuity gap |
| West LA: i10 → i405 | all three | derived + authored bridge (24.589 m) | 485.767 | 90.16° | 4 | see below |

- **Sourced vs authored:** 8 movements are wholly derived from locked chain
  geometry (the chains share the snapped junction node — the movement exists
  in the locks). Ontario and West LA legitimately do not exist in the locks:
  their authored ADR-0018 bridge components span the directed lock's
  recorded continuity gaps (within the 2 × 25 m junction limit, the transfer
  lock's characterised cross-facility anchor separations of 15.986 m and
  24.401 m), justified and bounded per record.
- **The West LA anchor zigzag.** The two anchor-snapped chain terminals
  overlap longitudinally: the I-405 chain start sits 24.6 m north of the
  I-10 chain end and immediately doubles back past it, so the naive chord
  composition carries reversal-class turns (161.4°, 155.7°, 160.4°, 180.0°).
  These are doubled travel the anchors digitized apart — the same artifact
  class as the carriageway stage's joint back-steps — excised as four
  bounded `junction_anchor_zigzag` records (−59.05 m of doubled centerline).
  The conditioned movement turns once through the recorded 90.16° corner.
- **Plan-view opposing crossings.** The West LA transfer (a left W→S
  movement) crosses each segment's opposing carriageway line exactly once —
  the WB-to-SB flyover of the real grade-separated interchange. The
  `opposing_clearance` gate requires crossings to be transversal
  (point-type, never a linear overlap that would be doubled pavement, at
  most two per line) and non-crossing movements to hold one full
  carriageway offset (10 m) of clearance; measured non-crossing minima are
  19.99+ m everywhere except Cove Fort's recorded 15.33 m left-turn
  approach. Vertical resolution of the crossings is
  lane-topology/collision output, recorded in the deferred-gates reason.
- **Vertical context (ADR-0017).** Boundary elevations come from the two
  segments' committed conditioned profiles at the seam stations; the
  cross-profile agreement at the shared anchor is measured (0.00 m at seven
  junctions, 0.01 m at Ontario, 1.05 m at West LA whose chain ends sit
  24.6 m apart) against a 2.0 m bound, and chord grades span −2.209 % to
  +3.538 % against the 7 % sustained bound. No observed junction elevation
  is claimed.
- **Length accounting.** Each movement records the westbound-carriageway
  length it replaces and its own length; the offset-vs-window
  length-agreement gate is bounded by the measured join-geometry envelope
  (offset × total lens turn plus the trim term). The recorded effects are
  facts inside the locked source-centerline fidelity envelope; the
  published ADR-0024 portal-to-portal figure remains the carriageway
  lock's record (`run_length_effect_claimed: false`).

## The authored turn-arounds (Barstow, Salt Lake City)

The composition rides the reciprocal pair (carriageway lock, reciprocity
gap 0.000 m at both anchors), so the turn-around joins the **arriving
westbound carriageway terminus to the departing westbound carriageway
origin — geometrically the arriving eastbound carriageway — across the
20 m median**. The measured seam poses are exactly anti-parallel
(deviation ≤ 0.0001°) and exactly one reciprocal separation apart
(19.9995/19.9996 m against the locked 20.0 m), as GEOS offsets of
identical reversed lines must be.

Each loop follows the fully eased sine heading profile
θ(u) = Θ·(u − sin(2πu)/(2π)) over arc-length fraction u — an authored
ADR-0018 record (no source asserts geometry for the anchor turn-around),
a pure function of the recorded seam poses that the validator reconstructs
exactly:

| Anchor | Arc length | Turn | Min radius | Seam curvature | Max forward excursion | Closure correction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Barstow (`ca-barstow-i40-i15`) | 51.460 m | 179.9999° | 8.149 m | 0.0015 / 0.0000 | 20.611 m | 0.0004 m |
| Salt Lake City (`ut-salt-lake-i80-i15`) | 51.460 m | 180.0000° | 8.063 m | 0.0003 / 0.0003 | 20.611 m | 0.0002 m |

- **Curvature continuity at both attachment seams** is exact by
  construction (the profile's endpoint curvature is analytically zero;
  discrete seam curvature ≤ 0.0015 1/m against the 0.005 bound, matching
  the near-straight carriageway ends).
- **The design bound is adjudicated now, not deferred**: the loops are
  full-precision authored geometry, so the minimum radius (8.06–8.15 m)
  is gated against the 6.5 m bound (the AASHTO passenger design vehicle's
  6.4 m minimum centerline turning radius, rounded up) at the declared
  15 km/h design speed — a median crossover movement, never claimed as a
  highway-speed ramp.
- Heading progresses monotonically through the turn (jitter bounded by the
  millimetre-quantization envelope), the loop closes onto the exit seam
  within 0.0004 m (0.01 m bound, applied linearly in arc length like the
  span seam registration), intersects the carriageways only at its
  attachment points, and rides level ground (anchor elevation agreement
  0.00 m, grade 0.000 %).

## Gate battery — 160 of 160 passed, 0 failed

Through movements (13 gates × 10): entry/exit seam position and heading,
reversal excision (≤ 8), heading discipline (reversal-class refusal at the
25 m lens), self-intersection, station monotonicity, length agreement
(join-geometry envelope), opposing clearance/crossing structure, junction
elevation agreement, transfer grade, anchor proximity (≤ 50 m; measured
≤ 10.9 m). Turn-arounds (15 gates × 2): the seam battery plus entry/exit
curvature continuity, minimum radius, heading monotonicity, closure
correction, seam-separation agreement against the locked reciprocal pair,
carriageway-attachment-only intersection, and the vertical pair.

Refusals are machine-readable JSON (`refusal`, movement context, measured
values); standing refusal paths covered by tests include the zigzag
removal cap, reversal-class lens turns, linear opposing overlap,
beyond-transversal crossing counts, non-anti-parallel or wrong-side
turn-around seams, and failed gate batteries. **No unresolvable site
remained** — the register gains no new entry.

## Validation and tamper resistance

`validate-continental-junction-geometry` is cache-independent: it validates
the full upstream battery (through the westbound carriageway validator),
pins all fifteen input hashes, recomputes every movement's length, digest,
corner census, self-intersection, length-agreement envelope, attachment
headings, and vertical context from the committed profile locks, recomputes
anchor proximity from the transfer lock, reconstructs both turn-around
loops exactly from their recorded seam poses, and requires the gate
batteries, summary, and movement digest to reproduce. Seam and
opposing-clearance measurements against the bulk carriageway geometry are
derive-time facts held to the locked thresholds; their provenance is pinned
through the carriageway lock hash and the derive's cache digest refusal.

## Provenance and replay

- Base revision: `cbb2200` (main), branch
  `p0-021-junction-transfer-geometry-20260831`, PR #105; macOS 26.7 arm64;
  uv 0.9.24, Python 3.13.11, Shapely 2.1.2, PyProj 3.7.2, GeoPandas 1.1.4,
  NetworkX 3.6.1.
- The NHPN response cache (base plus supplements) and the NHS fill cache
  were regenerated from the live services before anything else and
  reproduced the committed candidate and fill locks exactly modulo
  acquisition timestamps; `derive-continental-westbound-carriageway` to a
  scratch output then reproduced the committed carriageway lock
  **identically except `derived_at`**, rebuilding the carriageway cache the
  junction derive verifies digest-for-digest.
- Junction geometry lock SHA-256
  `9ee2bbec8a0024e4249eaea6a89070ef4bf0232b5e1d1bb1b3b0d757290c5c0d`.
- Replay: two consecutive `derive-continental-junction-geometry` runs
  produce identical locks modulo the top-level `derived_at`
  (`movements_sha256` stable).
- Nothing continental is committed beyond the compact lock; the NHPN, NHS
  fill, and carriageway caches stay in the ignored `.tools/continental/`;
  `data/sources/catalog.json` and every upstream lock are untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-junction-geometry
# exit 0: 12 movements, 10 through transfers, 2 turn-arounds,
# 4 corner sites, 160 gates passed

uv run --project tools/map_pipeline --frozen cannonball-map \
  validate-continental-junction-geometry \
  data/routes/continental/junction-geometry-lock.v1.json
# exit 0: cache-independent full recomputation

./scripts/validate-continental-route.sh
# exit 0: all fourteen stages green
```

## Verification

`ruff` clean; 264 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`; the repository-root bare `pytest` collection
trap is unchanged). New unit tests cover the exact-station window cut, the
anchor-zigzag excision (records and the removal-cap refusal), the junction
corner census (recording and the reversal refusal), the turn-around loop
construction (exact endpoint closure, minimum radius, seam curvature,
monotonicity, exact reproduction, and the non-anti-parallel / wrong-side /
short-lateral refusals), the repository lock's recorded state, and the
validator's semantic-tampering rejections (failed gate, drifted geometry
vertex, dropped movement, drifted vertical context, drifted seam pose,
widened threshold, drifted excision class, drifted path coverage, inflated
crossing structure, drifted input hash, drifted summary, drifted model,
unclaimed generation policy, drifted geometry digest).

`./scripts/check.sh` results are recorded in the pull request.

## What P0-021 still needs

1. **Lane topology, ramps, and collision** over the carriageway and
   junction-transfer model with the deferred ADR-0018 gates, then the
   GeoPackage/FlatBuffer package build (materializing the cached
   carriageway geometry) under ADR-0019 budgets.
2. **The Holland Tunnel connector** (`nyc-start-to-i78`), which publishes
   the southern portal-to-portal figure.
3. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`.
4. **Double-build reproducibility and traversals** on both platforms.
5. **Human gates**: geographic plausibility and the coast-to-coast drive.

## Next bounded decision

Lane topology, ramps, and collision over the carriageway and
junction-transfer model — the stage that runs the deferred ADR-0018 gates
(design radius, curvature rate, vertical curvature, sightline, clearance,
collision, lane connection, drivability, and the grade-separation vertical
resolution of the recorded junction crossings) — followed by the ADR-0019
package build.
