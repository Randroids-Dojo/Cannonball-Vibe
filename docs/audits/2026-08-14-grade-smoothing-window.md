# Grade smoothing: the 100 m window is ratified and shipped

Date: 2026-08-14

Task: P0-021; ratifies
[the grade smoothing prototype](2026-08-14-grade-smoothing-prototype.md), which
this audit supersedes on its departure figures and preserves otherwise. Follows
[the ride-height oscillation root cause](2026-08-14-ride-height-oscillation.md).

Status: decided. The owner selected the 100 m window on 2026-08-14 from the two
measured alternatives.

## The decision

Vertical-curve grading is on by default at a 100 m window.
`pipeline.GRADE_SMOOTHING_METERS` carries the value and is the default for both
`build_route_graph` and `cannonball-map build --grade-smoothing-meters`. Passing
`0` still reproduces the ungraded profile.

The alternatives put to the owner were 100 m (64% of the ride-height oscillation
removed) and 200 m (78%), against the fidelity cost of each, plus leaving grading
off. This audit does not re-open that choice. It records what shipping it
actually does, including one figure the prototype audit got wrong.

## The ratified default is the measured configuration, not a re-derivation

Building the representative corridor with the new default reproduces the exact
package the prototype audit measured at 100 m, and disabling grading reproduces
the package that shipped before it:

| Build | Content version | Prototype audit called it |
| --- | --- | --- |
| new default | `route-v5-e6d2d877ddc5c52f` | the 100 m package |
| `--grade-smoothing-meters 0` | `route-v5-c66ac9eeae94346a` | the unsmoothed package |

Because the bytes are identical, the ride-height measurement carries over exactly
rather than needing a repeat capture: 71.1 mm peak-to-peak ungraded against
21.9 mm graded at 40 m/s, a 64% reduction.

## Correction: the quoted departure was not departure from surveyed ground

The prototype audit reported 3.8 cm mean and 17.1 cm max departure for the 100 m
window, and the owner chose against those numbers. Both were measured against the
**already-conditioned** profile — after the corridor spike median and the 7%
Lipschitz grade projection — not against the survey. That is the marginal effect
of the smoother, not the fidelity of the road.

Measured directly against the 3DEP raster at all 1,011 stations of the 24,665 m
corridor:

| Profile | Mean departure | p95 | Max |
| --- | ---: | ---: | ---: |
| ungraded (shipped until now) | 12.58 cm | 49.95 cm | 7.36 m |
| graded 100 m (new default) | 14.52 cm | 51.90 cm | 7.00 m |

Three things follow, and the first two argue for the choice more strongly than
the numbers the decision was made on.

- **The marginal cost of grading is 1.95 cm of mean departure**, not 3.8 cm, and
  it sits on top of 12.58 cm that existing conditioning already costs. Grading
  adds about 15% to a fidelity gap that was already there.
- **Grading does not worsen the worst case.** Max departure falls by 35 cm,
  because the smoother rounds the tops of cliffs that the grade projection was
  otherwise clamping into a flat-then-7%-drop shape.
- **The absolute fidelity of the road is much lower than either audit implied.**
  A 7.36 m worst-case departure predates this change and is owned by the spike
  median and the grade ceiling. It is recorded here because it is now measured,
  not because grading caused it.

  **Partly resolved on 2026-08-16.** The whole maximum is the spike median; the
  grade projection contributes nothing to it. Every large departure sits on a raw
  feature carrying 12 to 26 percent grades, which no highway is built to, so what
  the median removes is not road surface. What those features *are*, and whether
  the elevation the median substitutes is correct, remain open and need a
  structure inventory or a bare-earth model. See
  [the decomposition](2026-08-16-survey-departure-decomposition.md).

The prototype audit's ride-height, roughness and package-hash figures are
unaffected — only its two departure columns are superseded.

## Distance is unaffected, and that is now enforced

ADR-0017 left open whether a graded profile may alter the authoritative route
distance. It cannot. Route distance is planimetric:
`PipelineEdge.length_meters` is the projected line length and sample stations are
spaced along it, so elevation conditioning of any kind — median, projection or
grading — cannot move it. `test_grading_window_does_not_change_route_distance`
asserts edge lengths and every sample station are identical between a graded and
an ungraded build, so the invariant fails loudly rather than silently.

Two further tests cover the shipped behaviour:
`test_shipped_grading_window_reduces_corridor_roughness` (the default at least
halves second-difference roughness on a rippled synthetic corridor) and
`test_grading_window_pins_corridor_endpoints` (corridor endpoints are bit-identical
graded and ungraded, which is what keeps a graded corridor meeting its
neighbours).

## What this does not decide

- Whether the 9-sample median window is the right width. The
  [2026-08-16 decomposition](2026-08-16-survey-departure-decomposition.md) shows
  what it currently removes is not road, which answers the open question about
  the 7 m departure, but it does not establish that 9 is the right window. The 7%
  grade ceiling is no longer in question: it contributes nothing to the maximum.
- The continental case. This is measured on one 24,665 m corridor; a 100 m window
  over mountain grades has not been observed.
- Whether grading interacts badly with the grade projection at specific cliffs.
  Grading changes the local grade by up to 5.55 percentage points at three
  stations where the projection was already active. The net effect on both mean
  and worst-case departure is favourable, so this is recorded as an observation,
  not a defect.
