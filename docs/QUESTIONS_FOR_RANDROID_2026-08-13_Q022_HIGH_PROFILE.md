# Questions for Randroid: Q-022 after the High-profile capture

Date: 2026-08-13

**Answered on 2026-08-14. Q-022a, Q-022b, Q-022d and Q-022e are closed.** The
decisions are recorded in
[ADR-0023](decisions/ADR-0023-reference-performance-target-and-layered-budgets.md)'s
2026-08-14 addendum, which is the authority, and the evidence and implementation
in [the ratification audit](audits/2026-08-14-q022-ratification.md).

- **Q-022a — option A2.** Gate machine state and re-measure. The capture front
  door now refuses a contended capture. The zero-stall threshold is *not*
  declared passed; it stays failed until a matrix passing the precondition
  records no stall.
- **Q-022b — option A.** Layer 2 stays unmeasured reserves. Layer-3
  content-class caps are unaffected.
- **Q-022d — ratified.** Slope above 1 MiB/min AND R² at or above 0.5.
- **Q-022e — capped runs judged on cap adherence.** The p95 limit is not
  applicable to a frame-capped run.

**Q-022c is still open** and is now the only Q-022 question outstanding.

The original text follows unchanged.

---

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
worst p99 3.002 ms against 20 ms, peak GPU memory at 1.97% of its limit, peak
working set at 5.12%. The 30-minute run measured 0.56 MiB/min with R² 0.16,
which passes the proposed sustained-growth rule only; Q-022d below still owns
whether those constants are ratified. The two memory
percentages divide raw byte counts by the decimal ADR-0023 limits of
9,500,000,000 and 16,000,000,000 bytes, so the rounded MiB values in the audit
tables will not reproduce them exactly.

## Q-022a update: the stalls did not reproduce at all

Since you chose instrumentation, the full nine-scenario matrix was re-run with it
active. It recorded **zero** steady-driving stalls, against twelve eleven hours
earlier on the same machine, same content, identical arguments. The 30-minute run
went from five stalls and a 57.2 ms worst frame to none and 40.8 ms. See the
[repeat capture audit](audits/2026-08-13-q022-high-profile-repeat-capture.md).

The instrumentation therefore gathered no attribution data — there was nothing to
attribute. That is not a wasted change: it stays in the harness and will resolve
the next stall that occurs. But it means the question in front of you has moved.

Be careful what this does and does not show. Non-reproduction is consistent with
a machine-state, contention, or measurement-method cause, but it excludes none of
them and it does not rule out an intermittent content, code, or driver cause —
that kind of cause is exactly the kind that need not appear in any given matrix.
The instrumentation itself is not excluded either, since its timing cost was
never separately measured.

One repeat run, `streaming-repeat-2`, recorded mean render GPU time about ten
times its sibling runs at identical arguments, with frame rate down by a similar
factor. The harness cannot say why — another GPU client, thermal or power state,
and driver behaviour are all candidates. What it shows is that a capture's GPU
timing can change by an order of magnitude on a metric the workspace policy does
not observe.

So the options below are superseded by a prior question:

- **A2. Gate idle state before measuring (recommended working default).** Add an
  idle-state precondition to the capture front door — verify no other GPU client,
  record contention indicators per run, and fail or flag a contended capture
  rather than publishing it. Then re-run and judge the zero-stall limit on
  captures that are known clean. Pro: makes every future capture comparable and
  directly addresses the demonstrated defect. Con: some captures will be refused.
- **B2. Require N consecutive clean matrices.** Keep the binary limit but define
  it over repeated runs rather than one. Pro: keeps a strict gate while
  acknowledging variance. Con: multiplies capture cost with no idle guarantee.
- **C2. Treat the first capture's stalls as environmental and move on.** Pro:
  fastest. Con: assumes the conclusion. The pair of captures is consistent with an
  environmental cause but excludes no other, and no cause was found.

The original Q-022a options remain below for reference. The zero-stall threshold
is not declared passed by the clean run; one clean matrix does not retire a
failure recorded under the same method.

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

## Q-022e update: the 60 FPS cap check now exists, and it fails on a 3.3 µs margin

The check recommended below has been run; `--max-fps` is now a capture-script
option. See the
[presentation check audit](audits/2026-08-13-q022-presentation-60fps-check.md).
Note this is a 60 FPS **engine frame cap**, not a 60 Hz output mode — display
refresh stays at the 120 Hz reference panel.

The build holds the cap essentially exactly: 60.009 mean FPS, 16.6625 ms p50
against a 16.6667 ms cap period, zero stalls, about 2.7 ms mean render GPU time
inside a 16.67 ms budget.

The same run records `p95_frame_ms` as **failed** at 16.9075 ms. The declared
16.67 ms limit sits 3.3 microseconds *above* a 60 FPS cap period, so it is
attainable in principle — but only if 95% of frames land within 3.3 µs of the
cap. Measured pacing jitter was about 241 µs, roughly 72 times that budget.

So the limit is not unreachable by construction; it is a margin ordinary frame
pacing exceeds. Choosing option A below therefore also requires deciding what
"pass" means for a capped run, because the current acceptance set marks a clean
60 FPS hold as a failure. That restatement is yours; this capture does not change
ADR-0023.

## Q-022e (original): is the presentation check sufficient?

One V-Sync-on run exists: 119.95 FPS, p95 10.078 ms, zero stalls. But the
reference display runs at 120 Hz, so this is a 120 Hz check, not the declared
60 FPS target presentation.

- **A. Add a 60 FPS cap presentation check (recommended working default).**
  Cap the engine to 60 FPS explicitly rather than relying on the display refresh.
  Pro: measures the declared target frame rate. Con: one more capture mode, and a
  frame cap is still not a 60 Hz output mode, which would need a display mode
  change.
- **B. Accept the 120 Hz check as the presentation evidence.** Pro: no more
  capture time. Con: does not measure the stated target.
- **C. Drop the presentation check.** Pro: simplest. Con: reintroduces the gap
  the balanced audit flagged.

## Still open from the previous handoff

- **Q-022c** — how per-subsystem attribution should be obtained. This is now the
  blocking question rather than a follow-up, because Q-022a option A depends on
  it.
- **Q-022d** — whether to ratify the sustained-growth rule (slope >1 MiB/min with
  R² ≥0.5). The High 30-minute run passes that *proposed* rule at 0.56 MiB/min,
  R² 0.16, a second clean data point for the constants. Until you ratify them,
  every "30-minute growth passed" statement in this capture means "passed the
  proposed rule", not "met a ratified requirement".

Until these are answered, the zero-stall threshold remains failed at the declared
target profile, the proposed budgets remain unratified, Q-022 and P1-013 stay
open, and no art, rights, readability, or comfort gate is advanced.
