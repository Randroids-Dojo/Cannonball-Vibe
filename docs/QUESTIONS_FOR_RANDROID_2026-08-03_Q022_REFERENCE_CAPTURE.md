# Questions for Randroid: Q-022 reference Windows capture

Date: 2026-08-04

The first clean, reproducible reference-Windows baseline is recorded from
committed revision `5a42ecef4af6f90fe616fceae1e69309471d200e`, using Release
builds and the native RTX 3080 Ti renderer at 2560×1440. See the
[capture audit](audits/2026-08-03-q022-reference-windows-capture.md) and
`evidence/M5/Q-022-reference-windows-capture.json`.

The baseline is **below the declared High content target**: target scenarios
used the `balanced` environment profile (30/12/7 near/mid/distant instances per
chunk, terrain stride 2), not `high` (48/18/10, stride 1). P1-013 therefore
requires a High-profile recapture; this mismatch is not an owner choice and is
not waived by any answer below. A two-build check did prove that all 52 shipping
files in the consumed representative route package were byte-identical.

One evaluated provisional threshold failed: the streaming scenario contained
one 52.404 ms steady-driving frame, not attributed to a route-loop wrap, against
the zero-stalls-over-50-ms limit. The 30-minute sustained-growth check passed at
−0.85 MiB/min with R² 0.29. Percentiles and memory ceilings passed comfortably.

Q-022 remains open. The capture is below target, has no traffic or weather, does
not measure per-subsystem cost, and does not replace human visual or comfort
review.

## Q-022a: how should the streaming stall be treated?

- **A. Treat it as a repeatability trigger (working default).** Keep the
  threshold failed for this matrix, add repeated streaming runs, and require a
  statistically stated result before opening a targeted optimization task.
  Pro: avoids guessing from one event while preserving the failure. Con: delays
  a definitive root-cause task and costs more capture time.
- **B. Treat it as an immediate blocker.** Open a performance task now and do
  not ratify budgets until no streaming run contains a steady stall above 50 ms.
  Pro: strictest frame-pacing posture. Con: one non-render event may be noisy,
  and the current evidence cannot identify its subsystem.
- **C. Accept one isolated stall for this slice.** Record the result but permit
  provisional budget ratification without repeat runs. Pro: fastest progress
  while content is sparse. Con: weakens the already-ratified zero-stall limit.

## Q-022b: ratify the proposed allocations before the High recapture?

- **A. Defer ratification (working default).** Keep the values as proposals until
  a High-profile capture exists, then re-derive again after traffic and weather.
  Pro: avoids turning a below-target baseline into policy. Con: current content
  growth has no ratified fine-grained caps.
- **B. Ratify as provisional regression limits now.** Pro: enables automated
  regression checks immediately. Con: layer-2 values are reserves, and the
  baseline used less environment content than the declared target.
- **C. Ratify with named adjustments.** Provide the values to change. Pro: puts
  owner priorities directly into the limits. Con: still lacks High-profile and
  per-subsystem evidence.

## Q-022c: how should per-subsystem attribution be obtained?

- **A. Add isolation runs (working default).** Add deterministic subsystem
  toggles and measure differences. Pro: automatable and comparable with the
  existing harness. Con: small costs may remain below run-to-run variance.
- **B. Add GPU-profiler evidence.** Use RenderDoc or Nsight for per-draw
  attribution. Pro: deeper render visibility. Con: external, less deterministic,
  and more expensive to reproduce.
- **C. Leave layer 2 as reserves.** Keep whole-scene and content-class gates only.
  Pro: lowest process cost. Con: subsystem regressions remain harder to localize.

## Q-022d: ratify the sustained-growth rule?

The current proposed rule fails a 30-minute run only when working-set slope is
above 1 MiB/min and R² is at least 0.5. This capture passes that rule.

- **A. Ratify the rule (working default).** Pro: gives automation an objective
  noise-resistant gate. Con: the constants have only one clean 30-minute
  baseline run behind them, and it used the balanced profile.
- **B. Change the slope and/or R² constants.** Pro: matches your risk tolerance.
  Con: changing them after seeing one result can overfit the evidence.
- **C. Use an absolute-growth or longer-run rule.** Pro: may map more directly
  to endurance risk. Con: increases runtime and needs a new capture.

## Q-022e: keep the uncapped measurement method?

- **A. Keep uncapped measurement and add a separate presentation check
  (working default).** Pro: preserves headroom visibility and adds player-like
  pacing coverage. Con: doubles relevant capture modes.
- **B. Require uncapped and 60 Hz in every matrix.** Pro: strongest comparison.
  Con: materially increases capture time.
- **C. Switch to capped-only.** Pro: closest to the target presentation mode.
  Con: hides performance headroom.

Until answered, the recorded threshold failure remains a failure, the High
recapture remains required, the proposed budgets remain unratified, Q-022 and
P1-013 stay open, and no related art, rights, readability, or comfort gate is
advanced.
