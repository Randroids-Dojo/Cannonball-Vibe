# Q-022 reference Windows performance capture

Date: 2026-08-03 through 2026-08-04

Task: Q-022 (blocking M5); related P1-008, P1-009, P1-010, P0-015

Evidence: `evidence/M5/Q-022-reference-windows-capture.json`

Handoff: [Q-022 ratification handoff](../QUESTIONS_FOR_RANDROID_2026-08-03_Q022_REFERENCE_CAPTURE.md)

## Outcome

The first conforming reference-Windows matrix is recorded from a fresh, clean,
detached worktree at committed revision
`5a42ecef4af6f90fe616fceae1e69309471d200e`. Every scenario used a Release
build, the native NVIDIA GeForce RTX 3080 Ti Vulkan renderer, a 2560×1440
window, Forward+, V-Sync off, and an uncapped frame rate. Warm-up was discarded.

One evaluated provisional threshold failed: the five-minute streaming scenario
contained one 52.404 ms steady-driving frame against the zero-stalls-over-50-ms
limit. The event occurred 173.386 seconds into measurement at 91.03 m/s and was
not attributed to a corridor-loop wrap. It is reported without tuning or a
selective rerun.

The 30-minute sustained-growth threshold passed. Working-set regression was
−0.85 MiB/min with R² 0.29; the first and last samples were 704.6 and 720.4 MiB.
All p95, p99, GPU-memory, working-set ceiling, and other evaluated stall results
passed. Q-022 remains open for owner ratification and because traffic, weather,
per-subsystem attribution, presentation-mode pacing, and human visual review
are not covered.

## Reproducibility

- Capture worktree: outside the gameplay checkout, created fresh at the exact
  measured commit.
- `git status --porcelain`: empty before measurement and after verification.
- Matrix order: daylight, night, high-speed, streaming, degraded-quality,
  steady-state-30m; all runs were sequential.
- Build: `dotnet restore --locked-mode`, then Release compilation into Godot's
  editor-runtime assembly location.
- Engine: Godot `4.7.1.stable.mono.official.a13da4feb`.
- Runtime: .NET SDK `10.0.102`; physics 120 Hz.
- GPU: NVIDIA GeForce RTX 3080 Ti, Vulkan API `1.4.341`.
- CPU/RAM/OS: Ryzen 9 5900X, 64 GB RAM, Windows 11 Pro 10.0.26200.
- Measurement source: monotonic `Time.GetTicksUsec`, not the smoothed engine
  delta.
- The machine-readable evidence records SHA-256 hashes for harness inputs and
  every captured report.

The solution-wide local gate passed at the measured revision: toolchain doctor,
build, 139 .NET tests, Ruff, continental-route validation, 100 map-pipeline
tests, 13 PlayGodot unit tests, and official-engine Godot smoke. The integrated
visual-slice gate also passed with the Hero GT, production road profile, and
balanced regional environment in one moving runtime.

## Scenario matrix

| Scenario | Build | Frames | Measured s | p50 ms | p95 ms | p99 ms | max ms | Steady stalls >50 ms | Mean FPS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| daylight | Release | 110,754 | 120.0 | 0.878 | 1.758 | 2.903 | 44.171 | 0 | 923 |
| night | Release | 113,473 | 120.0 | 0.848 | 1.768 | 2.808 | 43.881 | 0 | 946 |
| high-speed | Release | 111,211 | 120.0 | 0.873 | 1.893 | 2.913 | 39.119 | 0 | 927 |
| streaming | Release | 282,287 | 300.0 | 0.878 | 1.728 | 2.808 | **52.404** | **1** | 941 |
| degraded-quality | Release | 113,750 | 120.0 | 0.863 | 1.673 | 2.708 | 41.756 | 0 | 948 |
| steady-state-30m | Release | 1,706,409 | 1800.0 | 0.863 | 1.758 | 2.818 | 47.404 | 0 | 948 |

## CPU and GPU attribution

| Scenario | Mean frame ms | Mean render CPU ms | Mean render GPU ms | Mean non-render ms | GPU-bound frames |
| --- | ---: | ---: | ---: | ---: | ---: |
| daylight | 1.083 | 0.300 | 0.416 | 0.667 | 88.8% |
| night | 1.058 | 0.300 | 0.392 | 0.665 | 86.7% |
| high-speed | 1.079 | 0.309 | 0.391 | 0.688 | 83.7% |
| streaming | 1.063 | 0.319 | 0.388 | 0.674 | 82.6% |
| degraded-quality | 1.055 | 0.292 | 0.393 | 0.661 | 88.9% |
| steady-state-30m | 1.055 | 0.317 | 0.384 | 0.670 | 82.4% |

“GPU-bound frames” compares measured render CPU and render GPU only. It does
not mean the whole frame is GPU-bound: mean non-render time is the largest
reported component in every scenario. The streaming stall itself reported
0.588 ms render CPU and 0.386 ms render GPU, so it was outside those measured
render components; the capture does not claim a more specific cause.

## Memory and garbage collection

| Scenario | Peak GPU MiB | Peak working set MiB | Working-set slope MiB/min | R² |
| --- | ---: | ---: | ---: | ---: |
| daylight | 171 | 734 | 10.60 | 0.813 |
| night | 177 | 739 | 16.47 | 0.970 |
| high-speed | 172 | 705 | 4.80 | 0.736 |
| streaming | 181 | 761 | 8.47 | 0.759 |
| degraded-quality | 170 | 728 | 12.32 | 0.966 |
| steady-state-30m | 177 | 759 | **−0.85** | 0.285 |

Only the 30-minute run is evaluated for sustained growth. Its video-memory
first/last samples were 175.8/175.8 MiB, and managed-heap first/last samples
were 19.5/22.6 MiB. During measurement, the game allocated 18,754,392,464 bytes
(10,991 bytes per rendered frame); the harness accounted for 0.13% of process
allocation. Gen0/Gen1/Gen2 counts were 1,133/1,133/11. These are optimization
signals, not evidence that garbage collection caused the single streaming
stall.

## Streaming

Distance traveled is cumulative and is reported separately from route position,
which wraps on the finite representative corridor.

| Scenario | Cumulative route m | Final route position m | Max chunk build ms | Max collision build ms | Max env build ms | Rebases | Loops | Chunk failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| daylight | 4,800 | 5,660 | 39.708 | 3.161 | 40.861 | 5 | 0 | 0 |
| night | 4,800 | 5,660 | 40.186 | 2.956 | 40.565 | 5 | 0 | 0 |
| high-speed | 10,686 | 12,498 | 34.775 | 2.853 | 40.374 | 11 | 0 | 0 |
| streaming | 25,404 | 2,576 | 36.140 | 2.964 | 40.567 | 26 | 1 | 0 |
| degraded-quality | 4,801 | 5,661 | 35.019 | 2.847 | 39.711 | 5 | 0 | 0 |
| steady-state-30m | 71,881 | 23,861 | 35.152 | 3.481 | 40.348 | 72 | 2 | 0 |

Every scenario recorded zero chunk failures plus collision build/removal counts.
The harness does not emit an independent seam-check or collision-miss counter,
so this capture makes no claim about those outcomes beyond the recorded fields.

## Content class

| Scenario | Peak draw calls | Mean draw calls | Peak primitives | Environment | Near/Mid/Distant instances |
| --- | ---: | ---: | ---: | --- | --- |
| daylight | 429 | 324 | 1,330,366 | balanced | 330/132/77 |
| night | 430 | 334 | 1,332,602 | balanced | 330/132/77 |
| high-speed | 430 | 323 | 1,332,602 | balanced | 540/216/126 |
| streaming | 530 | 350 | 1,332,602 | balanced | 540/216/126 |
| degraded-quality | 428 | 321 | 1,308,438 | low | 176/77/44 |
| steady-state-30m | 525 | 349 | 1,330,366 | balanced | 300/120/70 |

Peak texture residency was 110 MiB; peak buffer residency was 48–52 MiB. The
harness records LOD inventory but does not detect visible pop-in.

## Acceptance against ADR-0023 provisional limits

| Scenario | p95 ≤16.67 ms | p99 ≤20 ms | no steady stall >50 ms | GPU ≤9.5 GB | WS ≤16 GB | 30-minute growth |
| --- | --- | --- | --- | --- | --- | --- |
| daylight | PASS | PASS | PASS | PASS | PASS | not evaluated |
| night | PASS | PASS | PASS | PASS | PASS | not evaluated |
| high-speed | PASS | PASS | PASS | PASS | PASS | not evaluated |
| streaming | PASS | PASS | **FAIL** | PASS | PASS | not evaluated |
| degraded-quality | PASS | PASS | PASS | PASS | PASS | not evaluated |
| steady-state-30m | PASS | PASS | PASS | PASS | PASS | PASS |

Worst-case p95 headroom is 8.8× and p99 headroom is 6.9×. Peak GPU memory used
2.0% of its limit, and peak working set used 5.0%. These metric-specific ratios
are intentionally separate. The zero-stall threshold is binary and has no
headroom ratio; it failed once in streaming.

The proposed sustained-growth operationalization is a slope above 1 MiB/min
with R² at least 0.5 over a 30-minute window. ADR-0023 does not yet ratify those
constants; Q-022 keeps that choice with the owner.

## Provisional budgets

The balanced-versus-low environment comparison and daylight-versus-night
lighting comparison are within observed run variance, so neither supports a
measured subsystem allocation. Layer-2 values remain reserve limits:

| Subsystem | Proposed reserve of 16.67 ms |
| --- | ---: |
| Road and route context | 3.0 ms |
| Traffic | 3.0 ms |
| Regional environment | 2.5 ms |
| Hero vehicle | 1.5 ms |
| Lighting and shadows | 2.0 ms |
| Effects | 1.0 ms |
| UI and HUD | 0.7 ms |
| Unallocated reserve | 3.0 ms |

Layer-3 proposals are anchored to the recorded whole-scene content: peak 530
draw calls against a proposed 2,000, peak 1.33 M primitives against 8 M, 18 road
materials against 40, 9 road meshes against 30, 8 environment materials against
24, 110 MiB textures against 4 GiB, and 52 MiB buffers against 1 GiB. These are
proposals for owner ratification, not accepted production budgets.

## Evidence boundaries and next work

This capture does not establish traffic cost (P0-015 is open), weather cost (no
weather implementation exists), per-subsystem GPU cost, V-Sync-on presentation
pacing, visible pop-in, a repository-defined High renderer preset, multi-run
statistical confidence, production-content readiness, asset rights approval, or
any human readability/comfort gate. It does not close P1-008, P1-009, P1-010,
Q-028, or Q-029.

The next technical slice is to add repeat/multi-run stall characterization and
per-subsystem isolation, then recapture with traffic and weather when those
systems exist. The owner handoff asks whether to treat the single streaming
stall as a blocker or a repeatability trigger and whether to ratify the proposed
budgets and measurement method.
