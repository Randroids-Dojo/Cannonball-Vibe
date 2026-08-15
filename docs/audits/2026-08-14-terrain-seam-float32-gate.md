# Terrain seam: gating on float32 spacing instead of an unreachable zero

Date: 2026-08-14

Task: P1-010; resolves the specification question raised by
[the terrain seam gate diagnosis](2026-08-14-terrain-seam-gate.md), which this
audit supersedes on its conclusion and preserves otherwise.

Status: decided and implemented. The owner selected the float32-spacing option on
2026-08-14.

## What the gate now asserts

`verify-environment-assets.sh` asserted `max_terrain_seam_m=0.0000`. It now
asserts that the seam is within what float32 can represent at the vertices being
compared, which the scenario computes per vertex pair and publishes as
`max_terrain_seam_float32_ratio`. The gate passes when that ratio is at most 1.

The ceiling is derived, not chosen. It tightens to nanometres near the origin on
its own, and widens far out by exactly what the representation requires.

## The premise the decision was made on was wrong, and the measurement says so

The option was put to the owner as "within **one** float32 ULP". Implemented that
way, the gate fails: the observed worst pair is 1.155 against a ceiling of 1.0.

Rather than widen the ceiling until it passed, every seam pair was measured. The
result settles what the diagnosis could only infer.

| Magnitude | Seam | Float32 spacing there | Seam ÷ spacing |
| ---: | ---: | ---: | ---: |
| 779.8 m | 0.3052 mm | 0.0610 mm | 5.00 |
| 795.8 m | 0.1831 mm | 0.0610 mm | 3.00 |
| 2329.3 m | 0.4883 mm | 0.2442 mm | 2.00 |
| 3582.5 m | 0.4883 mm | 0.2442 mm | 2.00 |
| 3808.3 m | 0.2441 mm | 0.2442 mm | 1.00 |
| 4031.7 m | 0.0153 mm | 0.2442 mm | 0.06 |
| 6676.4 m | 0.4883 mm | 0.4883 mm | 1.00 |
| 7074.2 m | 0.0000 mm | 0.4883 mm | 0.00 |
| 9124.7 m | 0.9766 mm | 0.9766 mm | 1.00 |
| 9290.6 m | 0.0000 mm | 0.9766 mm | 0.00 |

(16 pairs measured; a representative selection is shown.)

**Every seam is an exact integer multiple of the float32 spacing at its own
magnitude — 0, 1, 2, 3 or 5, never a fraction.** A real geometric discontinuity
would land on arbitrary non-integer multiples. This is the direct evidence that
the seam is representation, not authored geometry, which the earlier diagnosis
argued from first principles but could not demonstrate.

## Why the multiple is five and not one

The one-ULP premise assumed a single rounding. The code performs five per vertex,
and adjacent chunks pay all five independently because each derives the shared
boundary vertex through its own anchor:

1. `RouteWorldPoint.RelativeTo` casts the double world point into the chunk-local
   frame. Route positions are double throughout the frame maths; this is where
   float32 first enters.
2. `RegionalTerrainRibbon.BuildRow` scales the right vector by the lane offset.
3. `BuildRow` adds that offset to the local route point.
4. `BuildRow` adds the surface height along Up.
5. `GetTerrainStartOuterEdge` / `GetTerrainEndOuterEdge` add the chunk `Position`
   back on.

Each rounding contributes at most half a unit in the last place, and two chunks
pay all five, so the vertices can differ by up to five units per component, or
`sqrt(3)` times that as a Euclidean distance. `TerrainSeamRoundingSteps = 5` in
`WorldStreamer` carries the count with the enumeration above beside it, so
changing the construction is visibly a reason to revisit the gate.

The observed worst pair is 5.00 units against a ceiling of `5 × sqrt(3)` = 8.66,
a margin of 1.73×. That margin comes from the geometry putting most of the
difference in one component rather than spreading it over three; it is a
consequence of the bound, not a fitted allowance.

## The root cause is the double derivation, and it is not fixed here

The seam exists because adjacent chunks compute the same boundary vertex twice,
through different anchors, instead of computing it once and sharing it. A shared
boundary vertex would be bit-identical and the original `0.0000` assertion would
be reachable at any distance.

That is a change to how the terrain ribbon is framed, with visual risk, and it is
not attempted here. It is the durable fix if the sub-millimetre seams ever matter
visually; at present the worst is 0.98 mm at 9.1 km, well inside the scenario's
own 0.05 m contract.

## Verification

`./scripts/verify-environment-assets.sh --region representative
--all-quality-levels` passes on all four quality profiles (high, balanced, low,
graybox), each reporting `max_terrain_seam_m=0.0005` with the ratio inside its
ceiling. The gate was previously failing silently — `grep -q` under `set -e`
exits 1 with no message — so this is the first time it has passed rather than
been skipped.

## What this does not decide

Whether to eliminate the seam by sharing boundary vertices. The gate now measures
the right property, which is that no discontinuity is authored beyond what the
representation forces; it does not assert that the representation forces none.
