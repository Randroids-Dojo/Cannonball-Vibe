# Q-022e 60 FPS presentation check

Date: 2026-08-13

Task: P1-013; question Q-022e

Evidence: `evidence/M5/Q-022-presentation-60fps-check.json`

## Why

Both High-profile captures measured uncapped, and the V-Sync run locked to the
reference display's 120 Hz rather than the declared 60 FPS target. Q-022e
recorded a forced-60 Hz presentation check as missing. The game already accepted
`--reference-max-fps`; the capture front door simply never exposed it, so this
adds `--max-fps` and runs the check.

## Result

The build holds a 60 FPS cap essentially exactly.

| Metric | Value |
| --- | ---: |
| Mean FPS | 60.012 |
| p50 frame time | 16.6625 ms |
| Cap frame period | 16.6667 ms |
| p99 frame time | 17.0375 ms |
| Maximum frame time | 38.359 ms |
| Steady-driving stalls >50 ms | 0 |
| Mean render GPU time | 2.675 ms |
| Mean non-render time | 13.989 ms |

Mean non-render time is dominated by the frame limiter sleeping, not by work.
Actual GPU cost is 2.675 ms inside a 16.67 ms budget.

## The threshold cannot be met under a cap

The same run records `p95_frame_ms` as **FAILED**: 16.9025 ms against the
16.67 ms limit, an exceedance of 0.2325 ms.

That is a threshold-applicability result, not a performance result.

A 60 FPS cap has a frame period of 16.6667 ms, which is already 0.0033 ms above
the declared 16.67 ms limit. Half of a capped run therefore sits at or above the
limit before any jitter is considered, and p95 must exceed it. **The limit is
unreachable under a 60 FPS cap regardless of how well the build performs.**

This does not show the limit is wrong. It shows the limit was derived for
uncapped measurement, where it means "95% of frames leave headroom against a
60 FPS budget", and that it cannot be carried unchanged into a capped
presentation run, where it would mean "95% of frames beat the cap you imposed".
Restating it for capped runs is Q-022e and belongs to the owner. Nothing here
changes ADR-0023.

## Consequence for Q-022e

The choice in the handoff was between adding a forced-60 Hz check, accepting the
120 Hz V-Sync run as the presentation evidence, or dropping the check. The check
now exists and is cheap. What it exposes is that picking it also requires
deciding what "pass" means for a capped run, because the current acceptance set
marks a clean 60 FPS hold as a failure.

## Machine state recording

This capture is also the first to record the machine's own state. The repeat
matrix contained a run whose mean render GPU time was about ten times its
siblings on a metric nothing observed. Every capture now writes GPU utilisation,
clock, temperature, power draw, and the list of processes holding a GPU context,
sampled immediately before and after the run.

This run recorded 34 GPU clients both before and after, with utilisation at 3%
before and 14% after. That client count is the ordinary desktop session — shell,
compositor, and browser processes all hold GPU contexts — which is exactly why
the record states that a non-zero count is not by itself evidence of contention.

The samples bracket the capture rather than covering it, so a transient load
during measurement can still go unobserved. The record enforces nothing and
never fails or reclassifies a capture, because whether machine state should gate
a capture is Q-022a, still open.
