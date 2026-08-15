# Grade smoothing prototype: the measured bounce/fidelity tradeoff

Date: 2026-08-14

Task: P0-021; follows
[the ride-height oscillation root cause](2026-08-14-ride-height-oscillation.md)

Status: superseded on 2026-08-14 by
[the ratified 100 m window](2026-08-14-grade-smoothing-window.md). The owner
selected 100 m and it now ships by default.

**The two departure columns below are wrong as labelled.** They measure departure
from the already-conditioned profile, not from surveyed ground; the successor
audit measures against the 3DEP raster and reports 1.95 cm of marginal mean
departure rather than 3.8 cm. Everything else here — ride height, roughness,
package hashes, the false negative — stands and is preserved.

## Why

The ride-height oscillation was traced to the road following bare-earth terrain
with no vertical-curve grading. Real highways are cut and filled; this corridor
takes its profile straight from the surface model, so the suspension reproduces
terrain micro-relief as a bob.

Whether to grade, and how much, is a route-geometry decision that ADR-0017 and
ADR-0024 speak to: smoothing trades ride quality against fidelity to surveyed
ground, and too much of it would be inferring a road that the source does not
describe. This prototype exists so that trade can be measured rather than
argued.

## What it does

`--grade-smoothing-meters` applies a triangular-weighted moving average to the
corridor elevation profile, after the existing spike-median and grade-ceiling
conditioning and before grades are recomputed.

- **Disabled by default.** With the flag absent or zero, the built package is
  byte-identical to the shipped one: `route-v5-c66ac9eeae94346a` in both cases.
- Endpoints are pinned, and the profile is already shared across edges at that
  point in the pipeline, so interior joins stay identical by construction and a
  smoothed corridor still meets its neighbours.

## Measured tradeoff

Ride height is chassis minus tyre contact, captured per physics frame over 30 s
at 40 m/s on the representative corridor. Departure is how far the graded profile
moves from the surveyed elevation at the same points.

The two departure columns are superseded; see the note at the top of this file.

| Window | Ride peak-to-peak | Ride std | Road roughness | Bob reduction | Mean departure | Max departure |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| off | 0.0711 m | 5.26 mm | 41.7 mm | — | 0 | 0 |
| 100 m | 0.0219 m | 1.87 mm | 23.2 mm | 64% | 3.8 cm | 17.1 cm |
| 200 m | 0.0110 m | 1.13 mm | 14.9 mm | 78% | 7.5 cm | 25.4 cm |

A 100 m window removes about two thirds of the bob for under 4 cm of average
departure from surveyed ground. A 200 m window removes about four fifths for
about 7.5 cm. Each run used a distinct package, confirmed by content hash:
`c66ac9ee` unsmoothed, `e6d2d877` at 100 m, `cb031921` at 200 m.

## A false negative worth recording

The first attempt at this measurement reported that smoothing changed nothing:
0%, -2%, -1% across the three windows. That result was an artefact. The patch
threading the flag into the capture front door had silently failed to apply, so
all three runs consumed the same unsmoothed package. The content hash was
identical across all three runs, which is what exposed it.

Had that gone unchecked, this audit would have concluded that the root cause was
wrong and sent the next person looking in the wrong place. Verifying that an
input actually changed before trusting an output is cheap; the same check caught
an identical no-op earlier the same day when a test worktree pulled an
uncommitted file.

## What was not decided here, and has since been decided

Whether to grade at all, and at what window. That was an owner decision, taken on
2026-08-14: 100 m, on by default. The distance question this section raised is
answered in the successor audit — route distance is planimetric, so no window can
alter it, and a test now enforces that.
