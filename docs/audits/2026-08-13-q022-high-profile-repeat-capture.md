# Q-022 High-profile repeat capture: the stalls did not reproduce

Date: 2026-08-13

Task: P1-013; question Q-022a

Evidence: `evidence/M5/Q-022-high-profile-repeat-capture.json`

Related: [first High-profile capture](2026-08-13-q022-high-profile-capture.md),
[attribution instrumentation](2026-08-13-q022-stall-attribution-instrumentation.md)

## Outcome

The instrumentation added under Q-022a was meant to answer *what work coincides
with a stall*. Running the full nine-scenario matrix with it produced a different
and more consequential answer: **there were no stalls to attribute.**

| | First capture | Repeat |
| --- | ---: | ---: |
| Window (UTC) | 03:43–04:41 | 14:45–15:44 |
| Steady-driving stalls >50 ms | **12** | **0** |
| Scenarios failing the zero-stall limit | 4 | 0 |
| Evaluated thresholds failed | 1 | 0 |

Identical between the two runs: scenario arguments, environment profile and
content, route-package inputs and their hashes, machine, GPU, driver, and pinned
toolchain. Different: the wall-clock hour, and the repeat build carries the
attribution instrumentation. A before-and-after comparison showed that change to
be allocation-neutral (harness allocation 4,049,950 → 4,001,430 bytes), but
allocation neutrality is not timing neutrality: the added per-frame counter reads
and two `Performance.GetMonitor` calls were never separately timed, so the
instrumentation itself is not excluded as a variable.

## Per-scenario comparison

| Scenario | p95 A | p95 B | max A | max B | Stalls A | Stalls B |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| daylight | 1.448 | 1.353 | 60.11 | 32.08 | 2 | 0 |
| night | 1.458 | 1.623 | 32.79 | 36.40 | 0 | 0 |
| high-speed | 1.637 | 1.573 | 54.00 | 48.02 | 1 | 0 |
| streaming | 1.943 | 1.548 | 57.03 | 41.92 | 4 | 0 |
| degraded-quality | 1.427 | 1.377 | 31.60 | 29.19 | 0 | 0 |
| steady-state-30m | 1.573 | 1.357 | 57.17 | 40.78 | 5 | 0 |
| streaming-repeat-2 | 1.427 | 7.343 | 30.59 | 27.79 | 0 | 0 |
| streaming-repeat-3 | 1.407 | 1.308 | 40.17 | 31.13 | 0 | 0 |
| presentation-vsync | 10.078 | 8.672 | 29.12 | 30.20 | 0 | 0 |

A = first capture, B = repeat.

The 30-minute run is the strongest single comparison: 1,949,836 frames with a
40.783 ms maximum, against 1,826,339 frames with a 57.175 ms maximum and five
stalls. Its sustained-growth slope was 0.16 MiB/min at R² 0.03.

## What this supports, and what it does not

Twelve events became zero with nothing changed that the build controls. That is
consistent with a machine-state, contention, or measurement-method cause.

It does not establish one. The tempting inference — that a content or code cause
would have reproduced — is wrong, because an *intermittent* content, code, or
driver cause is precisely the kind that need not appear in any given matrix. A
rare allocation pattern, a rare timing race, or a driver-side event would all
behave exactly like this. Neither is the instrumentation excluded, since its
timing cost was never measured.

So no hypothesis is favoured here and none is eliminated. The first capture's
twelve events were real measurements taken under the same declared method and are
not withdrawn. What the pair establishes is narrower and still useful: a single
matrix run cannot decide the zero-stall gate in either direction.

## A run whose GPU timing changed by an order of magnitude

`streaming-repeat-2` in the repeat matrix shifted its entire distribution without
producing any stall:

| | streaming | streaming-repeat-2 | streaming-repeat-3 |
| --- | ---: | ---: | ---: |
| Mean render GPU ms | 0.392 | **3.753** | 0.392 |
| Mean FPS | 1,027 | **145** | 1,116 |
| p50 ms | 0.818 | **6.902** | 0.802 |

Mean render GPU time was roughly ten times its sibling runs at identical
arguments while frame rate fell by a similar factor.

The harness cannot say why. Contention from another GPU client is one candidate;
thermal or power state, a driver-side event, and display or compositor behaviour
are others, and nothing recorded distinguishes them. What the run does show is
that a capture's GPU timing can change by an order of magnitude between otherwise
identical runs, without the build changing.

This run is reported, not discarded. Excluding it would improve every summary
number in the repeat record and would hide the measurement-method problem it
demonstrates. It is also why this record's worst-case p95 is 7.343 ms with only
2.3× headroom, against 8.6× in the first capture: one contended run dominates
that statistic.

## Consequences

**For Q-022a.** The chosen answer was to instrument rather than repeat. Doing
both showed the premise was incomplete: the event is not merely intermittent
across runs of the same scenario, it can be absent from an entire matrix. The
question is no longer only "what causes the stall" but "is a binary zero-stall
gate measurable on this reference machine at all". The revised handoff puts that
to the owner.

**For the capture method.** Q-022's workspace policy already requires a fresh
clean worktree per capture. It does not require, or verify, anything about the
machine's state while measuring. `streaming-repeat-2` shows that captures can
differ by an order of magnitude on a metric the policy does not observe, whatever
the underlying reason.

**For the budgets.** Nothing here changes the earlier finding that balanced and
High differ by less than run-to-run variance. This capture strengthens it: the
variance between two runs of the *same* profile is larger than the difference
between profiles.

## What is still not established

No cause for the first capture's twelve stalls, and no exclusion of any
candidate cause. No rate for them. No machine-state verification in the capture
front door, and no timing measurement of the instrumentation's own cost. Traffic, weather, per-subsystem
attribution, a High renderer preset, and a 60 FPS presentation check all remain
absent, exactly as before.

The zero-stall threshold is not declared passed. One clean matrix does not
retire a failure recorded under the same method any more than one failing matrix
condemns a build.
