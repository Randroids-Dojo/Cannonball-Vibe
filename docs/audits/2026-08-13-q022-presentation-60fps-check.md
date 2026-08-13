# Q-022e 60 FPS cap presentation check

Date: 2026-08-13

Task: P1-013; question Q-022e

Evidence: `evidence/M5/Q-022-presentation-60fps-check.json`

## Why

Both High-profile captures measured uncapped, and the V-Sync run locked to the
reference display's 120 Hz rather than the declared 60 FPS target. Q-022e
recorded a 60 FPS presentation check as missing. The game already accepted
`--reference-max-fps`; the capture front door simply never exposed it, so this
adds `--max-fps` and runs the check.

This is a **60 FPS engine frame cap**, not a 60 Hz output mode. `--max-fps` sets
`Engine.MaxFps`. It does not change display refresh, which remains the 120 Hz
reference panel, and V-Sync stays off. A true 60 Hz output-mode check would need
a display mode change and is not covered here.

## Result

The build holds the cap essentially exactly.

| Metric | Value |
| --- | ---: |
| Mean FPS | 60.009 |
| p50 frame time | 16.6625 ms |
| Cap frame period | 16.6667 ms |
| p99 frame time | 17.0575 ms |
| Maximum frame time | 35.732 ms |
| Steady-driving stalls >50 ms | 0 |
| Mean render GPU time | 2.7 ms |

Mean non-render time is dominated by the frame limiter sleeping, not by work.
Actual GPU cost sits near 2.7 ms inside a 16.67 ms budget.

## The p95 limit leaves a 3.3 microsecond margin under a cap

The same run records `p95_frame_ms` as **FAILED**: 16.9075 ms against the
16.67 ms limit.

The arithmetic that matters:

| Quantity | Value |
| --- | ---: |
| 60 FPS cap frame period | 16.666667 ms |
| Declared p95 limit | 16.670000 ms |
| Limit **minus** cap period | **+0.003333 ms** (3.3 µs) |
| Measured p95 jitter above the cap period | 240.8 µs |
| Measured jitter ÷ permitted jitter | ≈72× |

The limit sits 3.3 microseconds **above** the cap period, so it is attainable in
principle: a capped run passes if 95% of frames land within 3.3 µs of the cap
period. It is **not** unreachable by construction, and this record makes no such
claim.

What it is, is a margin so thin that ordinary frame pacing exceeds it — measured
jitter was roughly 72 times the permitted budget. In practice a 60 FPS-capped run
fails this threshold unless pacing is very nearly perfect.

That is a statement about applying an uncapped-measurement threshold to a capped
run, not about the build's performance. Uncapped, the same limit means "95% of
frames leave headroom against a 60 FPS budget", which this build meets with 8.6×
margin. Capped, it means "95% of frames beat the cap you imposed to within
3.3 µs". Whether the limit should be restated for capped runs is Q-022e and
belongs to the owner. Nothing here changes ADR-0023.

## Consequence for Q-022e

The choice was between adding a 60 FPS check, accepting the 120 Hz V-Sync run as
the presentation evidence, or dropping the check. The check now exists and is
cheap. What it exposes is that choosing it also requires deciding what "pass"
means for a capped run, because the current acceptance set marks a clean 60 FPS
hold as a failure on a 3.3 µs technicality.

## Machine state recording

This capture is also the first to record the machine's own state. The repeat
matrix contained a run whose mean render GPU time was about ten times its
siblings on a metric nothing observed. Every capture now writes GPU utilisation,
clock, temperature, and power draw, plus a count of processes holding a GPU
context, sampled immediately before and after the run, hash-locked into the
evidence.

This run recorded 34 GPU clients before and after, with utilisation at 0% before
and 15% after. That count is the ordinary desktop session — shell, compositor,
and background applications all hold GPU contexts — which is why the record
states that a non-zero count is not by itself evidence of contention.

Only the **count** is retained. Process identifiers, image paths, and executable
names are all discarded: `nvidia-smi` reports absolute image paths, and even
reduced to a basename those amount to an inventory of the owner's installed
software, which must not enter committed evidence.

The samples bracket the capture rather than covering it, so a transient load
during measurement can still go unobserved. The record enforces nothing and never
fails or reclassifies a capture, because whether machine state should gate a
capture is Q-022a, still open.
