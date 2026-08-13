# Questions for Randroid: Q-022 after the High-profile capture

Date: 2026-08-13

This supersedes the decision set in the
[2026-08-03 ratification handoff](QUESTIONS_FOR_RANDROID_2026-08-03_Q022_REFERENCE_CAPTURE.md)
for Q-022a, Q-022b, and Q-022e. Q-022c and Q-022d from that document are
unchanged and still need answers.

The required High content-profile recapture is done. See the
[capture audit](audits/2026-08-13-q022-high-profile-capture.md) and
`evidence/M5/Q-022-high-profile-windows-capture.json`. Revision
`de42c82fdd6519895b9164c6d8a11a4f08bd7015`, fresh clean worktree, nine sequential
scenarios, Release, Forward+, 2560×1440, native RTX 3080 Ti.

Two things changed materially.

**The zero-stall limit now fails in four scenarios, not one.** Twelve
steady-driving frames exceeded 50 ms across daylight (2), high-speed (1),
streaming (4), and steady-state-30m (5). The balanced baseline had one event in
one scenario. But three streaming runs with identical arguments produced 4, 0,
and 0 events, so it is intermittent, and every event reports render CPU plus GPU
near 1 ms against a 50–60 ms frame — the cost is outside the render path and
nothing in the harness localises it.

**The High profile cost no measurable frame time.** Going from 330/132/77
instances and terrain stride 2 to 528/198/110 and stride 1 did not raise p95 or
p99; four of five target scenarios came in lower than their balanced
counterparts, and peak GPU memory was unchanged. The two profiles differ by less
than run-to-run variance at this content scale.

Everything else passes with large margins: worst p95 1.943 ms against 16.67 ms,
worst p99 3.002 ms against 20 ms, GPU memory at 1.97% of its limit, working set
at 5.12%, and 30-minute growth at 0.56 MiB/min with R² 0.16. Those two
percentages divide raw byte counts by the decimal ADR-0023 limits of
9,500,000,000 and 16,000,000,000 bytes, so the rounded MiB values in the audit
tables will not reproduce them exactly.

## Q-022a (revised): how should the intermittent stall be treated now?

The previous answer was "repeat the runs before deciding." That has been done and
it did not resolve the question — it showed the event is intermittent and
scenario-independent.

- **A. Open a targeted attribution task (recommended working default).** Accept
  that no further black-box repetition will localise this, and make the next step
  instrumentation: per-subsystem frame timers, or an external GPU/CPU profiler
  capture triggered on a >50 ms frame. Keep the threshold failed meanwhile.
  Pro: the only path that can actually find the cause. Con: real implementation
  cost before any budget work proceeds.
- **B. Keep the threshold failed and defer.** Record the failure, do no further
  work until traffic and weather exist, then recapture. Pro: avoids optimising
  against content that will change. Con: a 60 ms hitch at 40 m/s is a visible
  hitch, and it will be harder to isolate once traffic is added.
- **C. Reclassify the limit.** Change the zero-stall rule to allow a bounded rate
  (for example, none above 50 ms per 10 minutes of steady driving). Pro: matches
  what an intermittent event can realistically be gated on. Con: relaxes an
  already-ratified limit in response to failing it, which the contract treats as
  a decision you must make explicitly rather than something a capture may assume.

## Q-022b (revised): can any subsystem allocation be ratified?

The evidence now argues against ratifying measured allocations at all: the
balanced-versus-High comparison shows no measurable percentile difference, so
layer-2 numbers derived from it would be derived from noise.

- **A. Keep layer 2 as unmeasured reserves (recommended working default).**
  Explicitly label the 3.0/3.0/2.5/1.5/2.0/1.0/0.7 ms values as reserves, not
  measurements, until per-subsystem attribution exists. Pro: honest about what
  the evidence supports. Con: no fine-grained regression gate yet.
- **B. Ratify the layer-3 content-class caps only.** Draw calls, primitives,
  materials, meshes, texture and buffer residency are directly counted rather
  than inferred, so those can be gated now. Pro: gives automation something real
  to enforce. Con: content-class caps do not catch frame-time regressions.
- **C. Ratify both layers as provisional.** Pro: fastest. Con: turns a
  noise-level comparison into policy.

## Q-022e (revised): is the presentation check sufficient?

One V-Sync-on run exists: 119.95 FPS, p95 10.078 ms, zero stalls. But the
reference display runs at 120 Hz, so this is a 120 Hz check, not the declared
60 FPS target presentation.

- **A. Add a forced-60 Hz presentation check (recommended working default).**
  Cap to 60 FPS explicitly rather than relying on the display refresh. Pro:
  actually measures the declared target presentation. Con: one more capture mode.
- **B. Accept the 120 Hz check as the presentation evidence.** Pro: no more
  capture time. Con: does not measure the stated target.
- **C. Drop the presentation check.** Pro: simplest. Con: reintroduces the gap
  the balanced audit flagged.

## Still open from the previous handoff

- **Q-022c** — how per-subsystem attribution should be obtained. This is now the
  blocking question rather than a follow-up, because Q-022a option A depends on
  it.
- **Q-022d** — whether to ratify the sustained-growth rule (slope >1 MiB/min with
  R² ≥0.5). The High 30-minute run passes it at 0.56 MiB/min, R² 0.16, which is a
  second clean data point for those constants.

Until these are answered, the zero-stall threshold remains failed at the declared
target profile, the proposed budgets remain unratified, Q-022 and P1-013 stay
open, and no art, rights, readability, or comfort gate is advanced.
