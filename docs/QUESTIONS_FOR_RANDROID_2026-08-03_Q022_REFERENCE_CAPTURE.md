# Questions for Randroid: Q-022 reference Windows capture

Date: 2026-08-03

The first representative production-content performance capture now exists on the
declared reference PC. It was taken natively on the Ryzen 9 5900X / RTX 3080 Ti
Windows 11 machine, windowed and rendered at 2560×1440 through Forward+ and
Vulkan, with V-Sync disabled and warm-up discarded.

Evidence:
[2026-08-03 Q-022 reference Windows capture](audits/2026-08-03-q022-reference-windows-capture.md)
and `evidence/M5/Q-022-reference-windows-capture.json`.

**Q-022 stays open.** This handoff asks you to ratify, adjust, or reject the
*derived* layer-2 subsystem and layer-3 content-class allocations. It does not
ask you to accept the capture as production sign-off, and it does not close any
other human gate.

## What the capture establishes

Frame-pacing percentiles and both memory ceilings passed with large margins:
p95 9.0×, p99 6.9×, GPU memory 51×, working set 20×. **One threshold failed:**
three frames exceeded the 50 ms steady-driving stall limit — 50.80 ms in the
high-speed scenario and 50.20/50.50 ms in the 30-minute run. Render CPU and GPU
were both under 0.6 ms during each, so the cost sits outside rendering. That
failure is reported, not tuned away.

Both *tail* criteria are boundary cases. The failing stalls exceed the limit by
0.4–1.6%, and an earlier execution of the same matrix recorded zero stalls but
failed sustained growth instead. Neither tail verdict should be treated as
settled from one run.

The passing margin is itself the point of this handoff: the current
representative slice uses only a small fraction of the 16.67 ms envelope, so a
pass today is weak evidence about a shipping scene. Two facts bound how far
these numbers can be trusted:

- **There is no traffic.** P0-015 (highway traffic director) is `open`, and
  ADR-0023 explicitly requires representative traffic before production budgets
  are ratified. Nothing in this capture measures traffic cost.
- **There is no weather.** The build has no precipitation, wet-road, fog, or
  volumetric system, so the ADR-0023 weather scenario is recorded as
  **not captured** rather than approximated with overcast lighting.

Two mechanisms explain the tail. Synchronous chunk construction peaked at
41.9 ms and environment construction at 40.5 ms, which is the right magnitude for
the three frames that breached 50 ms. Separately, 79% of measured seconds contain
at least one frame above 16.67 ms, with a median per-second worst frame of
30.29 ms; these track Gen0 garbage collections almost one to one (1,437
collections, 0.80/s over the 30-minute run) driven by roughly 14.4 KB of
allocation per rendered frame.

## Q-022a: ratify the derived subsystem and content-class allocations

The audit proposes provisional layer-3 content-class budgets that are anchored to
measured values, and provisional layer-2 subsystem allocations that are **not**.

Two subsystem isolations were attempted — regional environment via the
balanced-versus-low comparison, and lighting via daylight-versus-night — and
**neither produced a reliable isolated cost**. Both deltas fell within
run-to-run noise, so no layer-2 number in the audit is measurement-derived.
Every layer-2 allocation, including environment and lighting, is a proposed
reserve-based spending limit ordered by the ADR-0023 priority rule.

- **A. Ratify the derived allocations as provisional regression limits
  (working default).** Adopt the proposed subsystem and content-class numbers so
  automated checks can detect regressions now, on the explicit understanding
  that the layer-2 figures are reserve-based rather than measured, that all of
  them are traceable to a traffic-free, weather-free, Debug-build capture, and
  that they will be re-derived once P0-015 traffic exists.
- **B. Ratify with named adjustments.** Tell me which allocations to change and
  to what values, and I will re-record the derived table and the regression
  thresholds against your numbers.
- **C. Re-capture after specified content changes first.** Name the content that
  must exist before allocations are worth ratifying — most plausibly P0-015
  traffic, and optionally a weather implementation — and I will defer the
  derived budgets until a capture that includes them.

## Q-022b: how should per-subsystem attribution be obtained?

Whole-scene attribution is measured (CPU versus GPU, and the non-render
remainder). Per-subsystem attribution is not: the capture cannot currently say
what fraction of GPU time belongs to the road kit versus the hero vehicle.

- **A. Add isolation runs to the harness (working default).** Extend the capture
  script with per-subsystem toggles. Measuring by difference is what this capture
  attempted for environment and lighting; it failed because whole-scene GPU cost
  is currently so far below the envelope that the deltas vanish into noise, so
  isolation runs need denser content or a longer averaging window to be useful.
- **B. Adopt GPU-profiler capture instead.** Introduce an external profiler pass
  (for example RenderDoc or Nsight) as a separate, non-deterministic evidence
  class for per-draw attribution.
- **C. Leave layer 2 unallocated for now.** Keep only whole-scene and
  content-class budgets until traffic and effects exist, and accept that
  subsystem regressions will be diagnosed manually.

## Q-022c: is the V-Sync-disabled, uncapped method the one you want?

The capture ran with V-Sync disabled and no frame ceiling so presented-frame time
could exceed the 119 Hz display refresh and reveal headroom. This is a
measurement-method choice recorded in the audit, not a ratified policy, and it is
not how a player will run the game.

- **A. Keep uncapped captures as the budget-measurement method (working
  default).** Continue measuring headroom uncapped, and add a separate
  V-Sync-on presentation check later for frame-pacing realism.
- **B. Require both modes in every capture.** Every future reference capture runs
  uncapped and at a 60 Hz cap, and both distributions are recorded.
- **C. Switch to capped-only captures.** Measure only at the presentation target,
  accepting that headroom becomes invisible.

## Q-022d: how should the sustained-growth criterion be defined?

ADR-0023 requires "no sustained positive growth" over 30 minutes but does not
quantify it. I applied a **proposed, unratified** operationalisation — a trend
counts as sustained only when it exceeds 1 MiB/min *and* explains at least half
the variance (R² ≥ 0.5) — so ordinary allocator noise cannot fail a run. Against
that rule the 30-minute capture passes at 0.93 MiB/min with R² = 0.45 — just
under both halves. An earlier execution of the same matrix failed it at
1.87 MiB/min with R² = 0.79, so the constants decide the verdict.

- **A. Accept the operationalisation as written (working default).** Keep the
  1 MiB/min and R² 0.5 rule, record that this capture passes it marginally, and
  require a repeat 30-minute run before any budget ratification because the
  verdict has already inverted once.
- **B. Accept the operationalisation but change the constants.** Name the
  slope and R² you want and I will re-evaluate the existing capture data against
  them without re-running.
- **C. Reject the operationalisation.** Specify how "sustained positive growth"
  should be judged — for example absolute growth over the window, or a
  requirement that the trend continue across a longer run — and I will re-derive.

## Autonomous posture

Until you answer, I will keep the capture harness, the provisional whole-scene
thresholds, and the recorded evidence boundaries as they are. I will not ratify
subsystem or content-class budgets, will not present this capture as production
sign-off or as satisfying the Q-028 trip-map or Q-029 camera reviews, will not
mark P1-008, P1-009, or P1-010 complete, and will leave Q-022 open.
