# Q-022 High content-profile reference capture

Date: 2026-08-13

Task: P1-013 (blocking M5); question Q-022; related P1-008, P1-009, P1-010, P0-015

Evidence: `evidence/M5/Q-022-high-profile-windows-capture.json`

Supersedes for target-profile purposes: the balanced-profile baseline in
[2026-08-03 reference Windows capture](2026-08-03-q022-reference-windows-capture.md).
That record remains the authoritative history of its own capture and is not
rewritten.

## Outcome

This capture closes the High content-profile gap that the balanced baseline left
open. Nine scenarios were measured sequentially from a fresh detached worktree at
committed revision `de42c82fdd6519895b9164c6d8a11a4f08bd7015`, clean before and
after, using Release builds, the native RTX 3080 Ti Vulkan renderer, Forward+, a
2560×1440 window, and the `high` environment profile (48/18/10 near/mid/distant
instances per chunk, terrain stride 1). Warm-up was discarded.

Two results matter, and they point in opposite directions.

**Frame-time and memory pass with very large margins.** Worst-case p95 across the
uncapped High scenarios was 1.943 ms against the 16.67 ms limit (8.6× headroom)
and worst-case p99 was 3.002 ms against 20 ms (6.7×). Peak GPU memory used 1.97%
of its 9.5 GB limit and peak working set used 5.12% of its 16 GB limit. The
30-minute sustained-growth check passed at 0.56 MiB/min with R² 0.16.

**The ratified zero-stall limit fails, and fails more widely than at balanced.**
Twelve steady-driving frames exceeded 50 ms across four scenarios: daylight (2),
high-speed (1), streaming (4), and steady-state-30m (5). The balanced baseline
recorded one such event in one scenario. No stall was tuned away or rerun
selectively.

## The High profile did not measurably cost frame time

This is the most consequential negative result, and it constrains what any budget
derived from this capture can claim.

| Scenario | Balanced p95 ms | High p95 ms | Balanced p99 ms | High p99 ms |
| --- | ---: | ---: | ---: | ---: |
| daylight | 1.758 | 1.448 | 2.903 | 1.873 |
| night | 1.768 | 1.458 | 2.808 | 1.893 |
| high-speed | 1.893 | 1.637 | 2.913 | 2.562 |
| streaming | 1.728 | 1.943 | 2.808 | 3.002 |
| steady-state-30m | 1.758 | 1.573 | 2.818 | 2.297 |

Raising near-instance density from 330 to 528 per loaded set, mid from 132 to 198,
distant from 77 to 110, and terrain stride from 2 to 1 did not raise percentile
frame time. Four of five target scenarios came in *lower* than their balanced
counterparts. Peak GPU memory was effectively unchanged (170–179 MiB at High
versus 170–181 MiB at balanced).

The correct reading is not that High content is free. It is that the difference
between the two profiles is smaller than run-to-run variation on this hardware at
this content scale, so **neither capture can be used to price environment
density**. A per-subsystem allocation derived from this comparison would be
derived from noise. This directly limits Q-022b and Q-022c.

## Scenario matrix

| Scenario | Profile | Frames | Measured s | p50 ms | p95 ms | p99 ms | max ms | Steady stalls >50 ms | Mean FPS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| daylight | high | 127,023 | 120.0 | 0.818 | 1.448 | 1.873 | **60.106** | **2** | 1059 |
| night | high | 124,559 | 120.0 | 0.818 | 1.458 | 1.893 | 32.789 | 0 | 1038 |
| high-speed | high | 117,326 | 120.0 | 0.833 | 1.637 | 2.562 | **53.998** | **1** | 978 |
| streaming | high | 273,814 | 300.0 | 0.893 | 1.943 | 3.002 | **57.035** | **4** | 913 |
| degraded-quality | low | 123,679 | 120.0 | 0.812 | 1.427 | 2.147 | 31.599 | 0 | 1031 |
| steady-state-30m | high | 1,826,339 | 1800.0 | 0.828 | 1.573 | 2.297 | **57.175** | **5** | 1015 |
| streaming-repeat-2 | high | 316,070 | 300.0 | 0.818 | 1.427 | 2.047 | 30.587 | 0 | 1054 |
| streaming-repeat-3 | high | 316,008 | 300.0 | 0.823 | 1.407 | 1.948 | 40.168 | 0 | 1053 |
| presentation-vsync | high | 14,394 | 120.0 | 8.193 | 10.078 | 10.578 | 29.122 | 0 | 120 |

`degraded-quality` deliberately retains the `low` profile; it is the degraded
comparison point, not a target scenario. It is excluded from the headroom claim,
as is `presentation-vsync`, whose frame time is dominated by vblank wait.

## Memory and attribution

| Scenario | Peak GPU MiB | Peak working set MiB | Working-set slope MiB/min | R² | Mean non-render ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| daylight | 170 | 723 | 10.49 | 0.97 | 0.545 |
| night | 170 | 720 | 7.84 | 0.97 | 0.555 |
| high-speed | 179 | 730 | 11.10 | 0.84 | 0.620 |
| streaming | 175 | 781 | 14.92 | 0.93 | 0.703 |
| degraded-quality | 176 | 719 | 10.54 | 0.93 | 0.576 |
| steady-state-30m | 171 | 763 | 0.56 | 0.16 | 0.588 |
| streaming-repeat-2 | 174 | 729 | 5.12 | 0.83 | 0.554 |
| streaming-repeat-3 | 174 | 753 | 9.75 | 0.80 | 0.551 |
| presentation-vsync | 171 | 695 | 3.21 | 0.97 | 6.605 |

Only the 30-minute run is evaluated for sustained growth. The positive slopes in
the shorter runs are warm-up-shaped fill, not evidence of a leak; the 30-minute
window is what the rule is written against and it passed.

Mean non-render time remains the largest frame component in every uncapped
scenario, as it was at balanced.

## Stall characterisation

All twelve steady-driving events, in full:

| Scenario | t s | Frame ms | Route m | Speed m/s | Render CPU ms | Render GPU ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| daylight | 42.4 | 53.881 | 2555 | 40.0 | 0.499 | 0.393 |
| daylight | 85.5 | 60.106 | 4281 | 40.0 | 0.442 | 0.398 |
| high-speed | 78.7 | 53.998 | 8981 | 91.0 | 0.792 | 0.396 |
| streaming | 118.7 | 54.435 | 12383 | 91.0 | 0.808 | 0.394 |
| streaming | 235.1 | 57.035 | 21796 | 91.1 | 0.411 | 0.367 |
| streaming | 237.7 | 55.037 | 22043 | 91.0 | 0.521 | 0.357 |
| streaming | 271.0 | 53.442 | 36 | 32.8 | 0.463 | 0.386 |
| steady-state-30m | 256.5 | 51.866 | 11515 | 40.0 | 0.473 | 0.382 |
| steady-state-30m | 505.1 | 50.258 | 21458 | 40.0 | 0.739 | 0.369 |
| steady-state-30m | 705.8 | 53.977 | 4795 | 40.0 | 0.480 | 0.398 |
| steady-state-30m | 1043.2 | 52.231 | 18286 | 40.0 | 0.566 | 0.368 |
| steady-state-30m | 1045.6 | 57.175 | 18383 | 40.0 | 0.524 | 0.375 |

What the evidence supports:

- The cost is outside the measured render path. The largest render CPU plus
  render GPU total during any stall was 1.202 ms against stalls of 50–60 ms.
- The event is intermittent, not deterministic. Three streaming runs with
  byte-identical arguments and inputs produced 4, 0, and 0 events. A single run
  cannot establish a rate, and this capture does not claim one.
- Streaming counters do not separate stalling from clean runs. Maximum chunk
  build (30.5–33.7 ms), collision build (2.6–3.1 ms), and environment build
  (36.0–39.0 ms) are effectively identical in runs with five stalls and runs with
  none. Chunk failures were zero everywhere.

What the evidence does not support: any specific cause. The harness has no
per-subsystem timer, so nothing here localises the event to streaming, garbage
collection, driver, or OS scheduling. Q-022c owns how attribution should be
obtained.

### One classification to review

The streaming event at t=271.0 s reports route position 36 m and speed
32.8 m/s, against a 91 m/s target, immediately after that run's single corridor
loop. The harness recorded `attributed_to_loop_wrap: false`, and this audit does
not override that classification. It is flagged because the surrounding state is
consistent with post-wrap re-acquisition rather than steady driving, and the
wrap-attribution heuristic may need a wider window. Excluding it would leave
eleven events across four scenarios and change no verdict.

## Presentation-mode check (Q-022e)

The V-Sync-on scenario closes the "V-Sync-on presentation pacing" gap the
balanced audit recorded as missing. With V-Sync enabled the run locked to
119.95 FPS against a 119.999 Hz display, with p95 10.078 ms, p99 10.578 ms, a
29.122 ms maximum, and zero stalls.

Two cautions. This is a 120 Hz presentation check, not the declared 60 FPS
target presentation, because the reference display runs at 120 Hz. And the
`gpu_bound_frame_ratio` of 100% in this run is an artefact of counting vblank
wait, not evidence that the frame is GPU-bound.

A single clean V-Sync run does not show that the stalls are absent under V-Sync;
four of the eight uncapped runs were also clean.

## Acceptance against ADR-0023 provisional limits

| Scenario | p95 ≤16.67 ms | p99 ≤20 ms | no steady stall >50 ms | GPU ≤9.5 GB | WS ≤16 GB | 30-minute growth |
| --- | --- | --- | --- | --- | --- | --- |
| daylight | PASS | PASS | **FAIL** | PASS | PASS | not evaluated |
| night | PASS | PASS | PASS | PASS | PASS | not evaluated |
| high-speed | PASS | PASS | **FAIL** | PASS | PASS | not evaluated |
| streaming | PASS | PASS | **FAIL** | PASS | PASS | not evaluated |
| degraded-quality | PASS | PASS | PASS | PASS | PASS | not evaluated |
| steady-state-30m | PASS | PASS | **FAIL** | PASS | PASS | PASS |
| streaming-repeat-2 | PASS | PASS | PASS | PASS | PASS | not evaluated |
| streaming-repeat-3 | PASS | PASS | PASS | PASS | PASS | not evaluated |
| presentation-vsync | PASS | PASS | PASS | PASS | PASS | not evaluated |

## Reproducibility

- Capture worktree `C:/Dev/cbv-q022-high`, created fresh at the measured commit,
  outside the gameplay checkout. `git status --porcelain` empty before and after.
- Engine `4.7.1.stable.mono.official.a13da4feb`; .NET SDK `10.0.102`; uv `0.9.24`;
  Git LFS `3.7.1`; toolchain doctor passed.
- The route package was rebuilt from checksum-locked fixture sources before every
  run, and a two-build comparison matched every consumed shipping byte.
- Nine captures ran sequentially, single pass, zero capture failures and zero
  retries. The recorded threshold failures are measured results, not capture
  failures.

## Evidence boundaries and next work

This capture still does not establish traffic cost (P0-015 is open), weather cost
(no weather system exists), per-subsystem GPU cost, visible pop-in, a
repository-defined High *renderer* preset, multi-run statistical confidence
beyond the three streaming runs, production-content readiness, asset rights
approval, or any human readability or comfort gate. It does not close P1-008,
P1-009, P1-010, P1-013, Q-028, or Q-029.

What changed for the owner's decision:

- Q-022's High-profile recapture requirement is satisfied.
- Q-022a's working default A (repeat the runs before opening an optimisation
  task) has been executed. The repeats show the stall is intermittent and is not
  confined to streaming; it now appears in daylight, high-speed, and the
  30-minute run as well.
- Q-022b is weakened by this capture rather than supported: the balanced-versus-
  High comparison shows no measurable percentile cost, so subsystem allocations
  still cannot be derived from measurement.
- Q-022e's presentation check now has one clean data point.

The zero-stall limit remains failed at the declared target profile. That is the
open decision this capture hands back.
