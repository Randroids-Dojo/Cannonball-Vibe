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

Five of the six ratified provisional thresholds passed by a very wide margin.
**One failed:** the 30-minute steady-state run shows sustained positive
working-set growth of 1.87 MiB/min (R² = 0.79, +57.7 MiB over the run). GPU
memory was perfectly flat, so the growth is entirely CPU-side, and only ~6 MiB
of it is managed heap — the rest is native. That failure is reported, not tuned
away.

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

Two measured behaviours sit close to thresholds even where they pass. Synchronous
chunk and environment construction produces isolated spikes up to 48 ms against a
50 ms limit. Separately, 81% of measured seconds contain at least one frame above
16.67 ms, with a median per-second worst frame of 29.97 ms; these correlate 1:1
with Gen0 garbage collections (1,475 collections, 0.82/s) driven by the game
allocating 14.4 KB per rendered frame.

## Q-022a: ratify the derived subsystem and content-class allocations

The audit proposes provisional layer-2 subsystem reserve limits and layer-3
content-class budgets derived from this capture. Regional environment and
lighting isolation were both attempted, but neither produced a reliable
subsystem cost: the balanced-versus-low and daylight-versus-night deltas were
within run-to-run noise. Every layer-2 number is therefore a reserve limit, not
a measured allocation.

- **A. Ratify the derived allocations as provisional regression limits
  (working default).** Adopt the proposed subsystem and content-class numbers so
  automated checks can detect regressions now, on the explicit understanding
  that they are traceable to a traffic-free, weather-free capture and will be
  re-derived once P0-015 traffic exists.
- **B. Ratify with named adjustments.** Tell me which allocations to change and
  to what values, and I will re-record the derived table and the regression
  thresholds against your numbers.
- **C. Re-capture after specified content changes first.** Name the content that
  must exist before allocations are worth ratifying — most plausibly P0-015
  traffic, and optionally a weather implementation — and I will defer the
  derived budgets until a capture that includes them.

## Q-022d: how should the sustained-growth failure be treated?

ADR-0023 requires "no sustained positive growth" over 30 minutes but does not
quantify it. I applied a **proposed, unratified** operationalisation — a trend
counts as sustained only when it exceeds 1 MiB/min *and* explains at least half
the variance (R² ≥ 0.5) — so ordinary allocator noise cannot fail a run. Against
that rule the 30-minute capture fails at 1.87 MiB/min with R² = 0.79.

- **A. Accept the operationalisation and treat this as a real failure (working
  default).** Record Q-022 as having one failing threshold, and open a task to
  find the native-side growth before any budget ratification.
- **B. Accept the operationalisation but change the constants.** Name the
  slope and R² you want and I will re-evaluate the existing capture data against
  them without re-running.
- **C. Reject the operationalisation.** Specify how "sustained positive growth"
  should be judged — for example absolute growth over the window, or a
  requirement that the trend continue across a longer run — and I will re-derive.

## Q-022b: how should per-subsystem attribution be obtained?

Whole-scene attribution is measured (CPU versus GPU, and the non-render
remainder). Per-subsystem attribution is not: the capture cannot currently say
what fraction of GPU time belongs to the road kit versus the hero vehicle.

- **A. Add isolation runs to the harness (working default).** Extend the capture
  script with per-subsystem toggles so each subsystem's cost is measured by
  difference, the same way the environment cost was isolated here.
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

## Autonomous posture

Until you answer, I will keep the capture harness, the provisional whole-scene
thresholds, and the recorded evidence boundaries as they are. I will not ratify
subsystem or content-class budgets, will not present this capture as production
sign-off or as satisfying the Q-028 trip-map or Q-029 camera reviews, will not
mark P1-008, P1-009, or P1-010 complete, and will leave Q-022 open.
