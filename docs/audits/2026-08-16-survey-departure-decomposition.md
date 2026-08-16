# The 7.36 m survey departure is the median doing its job

Date: 2026-08-16

Task: P0-021. Closes the question raised by
[the grade smoothing window audit](2026-08-14-grade-smoothing-window.md), which
measured the departure and explicitly did not examine whether the conditioning
causing it was correct.

Status: resolved. No conditioning change is proposed.

## The concern

Shipping the 100 m grading window required measuring departure from surveyed
ground for the first time. That measurement found the corridor already departed
**12.58 cm mean and 7.36 m maximum** from the 3DEP raster *before* grading, owned
by the corridor spike median and the 7% Lipschitz grade projection. The audit
recorded it and stopped:

> A 7.36 m worst-case departure predates this change and is owned by the spike
> median and the grade ceiling. It is recorded here because it is now measured,
> not because grading caused it. Nothing in this session evaluated whether a 7 m
> clamp at a cliff is the right conditioning.

This audit evaluates it.

## Decomposition by stage

Each conditioning stage was run against the raw raster samples at the same 1,011
stations of the 24,665 m corridor:

| Profile | Mean | p95 | Max |
| --- | ---: | ---: | ---: |
| median only (9 samples) | 12.17 cm | 48.98 cm | 7.36 m |
| median + 7% grade projection | 12.58 cm | 49.95 cm | 7.36 m |
| median + projection + 100 m grading | 14.52 cm | 51.90 cm | 7.00 m |

**The grade projection contributes nothing to the maximum.** It is identical with
and without — 7.36 m either way — and adds 0.41 cm to the mean. The 7% ceiling
was the more suspicious of the two constants and it turns out not to be
responsible.

The entire worst-case departure is the spike median.

## What the median is removing

At the worst station, 20,699 m, the raw 3DEP profile reads:

| Station | Raw | Median | Raw grade |
| ---: | ---: | ---: | ---: |
| 20,636.7 m | 1620.91 | 1624.01 | −1.2% |
| 20,661.7 m | 1624.15 | 1622.96 | **+12.9%** |
| 20,686.7 m | 1628.53 | 1622.00 | **+17.5%** |
| 20,699.1 m | 1628.57 | 1621.21 | +0.3% |
| 20,724.1 m | 1624.53 | 1620.91 | **−16.1%** |
| 20,749.1 m | 1620.47 | 1620.47 | **−16.2%** |

A 7.7 m rise and fall over about 60 m, at grades of 13 to 17 percent.

The same shape appears at every large departure:

| Station | Departure | Raw prominence | Steepest raw grade |
| ---: | ---: | ---: | ---: |
| 20,699.1 m | 7.36 m | 9.11 m | 17.5% |
| 13,932.2 m | 5.62 m | 9.26 m | 26.3% |
| 24,051.3 m | 5.58 m | 10.61 m | 17.8% |
| 100.0 m | 4.37 m | 5.87 m | 11.9% |
| 12,427.9 m | 3.13 m | 8.99 m | 21.2% |
| 3,873.1 m | 2.45 m | 5.21 m | 13.9% |

**No highway is built to those grades.** US interstate design tops out around 6 to
7 percent, which is where ADR-0023's conditioning ceiling comes from. A raw
profile carrying 26 percent is not the road surface under any interpretation of
which road is on top at a crossing — an overpass the highway climbs would have
highway-legal approach grades, not 17 percent ramps.

So these features are structures the surface model captured beside or above the
centreline, exactly the case
`_condition_linear_corridor_elevations` names in its docstring. The median
rejecting them is the intended behaviour, and the 7.36 m figure is evidence that
it is working rather than evidence of over-conditioning.

## Two filter behaviours found while measuring, now pinned by tests

Neither is a defect, and both would otherwise be rediscovered by whoever next
compares conditioned elevation against survey.

**A median shifts near a spike on a slope.** The window around a spike loses its
outliers to one side, so the median moves toward the far end of the window, by up
to `radius × spacing × grade`. On a 4% grade at 25 m spacing that is 4 m. It is
bounded and small next to the 9 m spike it removes, but it is not zero.

**A median shifts at the corridor ends on a slope.** The window is truncated
there, so on a grade its centre of mass is not the station it is centred on. The
same bound applies. This is why the representative corridor shows a 4.37 m
departure at station 100.0 m, near the start.

## What is not resolved

- **The mean departure of 12.17 cm is not explained here.** It is distributed
  rather than concentrated, and this audit only accounts for the maximum. It is
  plausibly the same two filter behaviours plus genuine micro-relief rejection,
  but that was not measured.
- **Whether a 9-sample window is the right width** is untouched. A wider window
  rejects wider structures and shifts more on slopes; a narrower one does the
  reverse. Nothing here says 9 is optimal, only that what it currently removes is
  not road.
