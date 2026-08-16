# ADR-0023: Reference performance target and layered budgets

- Status: Accepted
- Date: 2026-07-23
- Owner decisions: Q-022 target Option A, budget-method Option A,
  frame-pacing Option A, and memory Option A; Q-022a, Q-022b, Q-022d and Q-022e
  on 2026-08-14, recorded in the addendum below

## Context

The declared Windows reference PC establishes where representative production
content will be measured, but hardware alone does not define success. The
project also needs a presentation target and a budgeting method that agents can
enforce before every final asset exists.

A single average frame-rate number would hide stutter, streaming spikes, memory
growth, and expensive content. Universal per-asset caps would be equally
misleading because a hero vehicle, bridge, route sign, nearby tree, and distant
terrain do not have the same visual or gameplay value.

## Decision

- The first production reference target is 2560×1440 at the High quality preset
  with a stable 60 frames per second on the declared Ryzen 9 5900X, RTX 3080 Ti
  12 GB, and 64 GB Windows 11 PC.
- After scenario warm-up, the provisional production-stable frame-pacing gate
  requires presented-frame time at or below 16.67 ms at p95, at or below 20 ms
  at p99, and no steady-driving stall above 50 ms. Average FPS alone cannot pass
  the gate. This applies to uncapped runs; a frame-capped run is judged on cap
  adherence instead, per the 2026-08-14 addendum.
- At the High preset, provisional memory ceilings are 9.5 GB of GPU memory and
  16 GB of process working set, with no sustained positive growth during a
  30-minute steady-state run. "Sustained" is defined by the ratified constants
  in the 2026-08-14 addendum.
- Use layered budgets:
  1. whole-scene outcomes for CPU and GPU frame time, frame pacing, working-set
     and GPU-memory high-water, streaming latency, and sustained growth;
  2. subsystem allocations for vehicle, road, traffic, environment, effects,
     lighting, and UI work;
  3. content-class budgets for triangles, draw calls, materials, texture
     residency, instancing, LOD transitions, and visible pop-in.
- Establish provisional budgets from deterministic fixtures and current
  representative captures so automated checks can detect regressions now.
- Ratify production budgets only after representative Hero GT, highway,
  traffic, and regional-environment content runs on the declared Windows
  machine in daylight, night, weather, high-speed, streaming, and degraded
  quality scenarios.
- Preserve road geometry, sign readability, route context, collision, and
  nearby traffic comprehension before spending quality headroom on distant
  scenery or cosmetic effects.
- This reference target is neither the minimum supported PC nor a promise of
  120 FPS or native 4K. Minimum specifications and additional performance modes
  require later evidence.

## Consequences

- Agents can introduce provisional regression thresholds without presenting
  placeholder-content measurements as final production budgets.
- Expensive content can be traced to a scene, subsystem, and content class
  instead of appearing only as a late aggregate frame-rate failure.
- P1-008, P1-009, and P1-010 retain their own visual-quality gates while sharing
  one performance authority.
- Q-022 remains open only for representative Windows measurement, derived
  subsystem/content-class allocations, and owner ratification. Its hardware,
  resolution, preset, frame-rate target, frame-pacing thresholds, memory
  ceilings, and budgeting method are resolved.

## Rejected alternatives

- **1440p High at 120 FPS:** improves latency and motion clarity but halves the
  frame-time envelope before representative traffic and environment density are
  known.
- **4K High at 60 FPS:** prioritizes pixel count over simulation, streaming, and
  regional-world headroom for the first production baseline.
- **Outcome-only budgets:** allow flexible content but identify regressions too
  late and provide weak autonomous diagnosis.
- **Universal per-asset caps:** are simple but allocate detail without regard to
  gameplay importance, screen size, repetition, or residency.
- **Near-hard 60 FPS lock:** produces more consistent motion but consumes too
  much world, traffic, and effects headroom for the first production baseline.
- **Average-only 60 FPS:** is easy to report but hides visible frame-pacing and
  streaming failures.
- **11 GB GPU / 24 GB working-set ceilings:** permit denser content but leave
  little GPU headroom and weaken scalability.
- **No provisional memory limits:** avoids premature constraints but prevents
  early automated detection of residency and growth regressions.

## Operating addendum — 2026-07-26

The owner selected a persistent pinned Windows toolchain and reusable caches
with a fresh clean Git worktree for each reference capture. Evidence records the
exact commit, tool versions, clean status, and input hashes. This avoids repeated
tool installation without allowing a long-lived dirty gameplay worktree or
stale generated outputs to contaminate measurements.

## Ratification addendum — 2026-08-14

The owner answered Q-022a, Q-022b, Q-022d and Q-022e after the High content-profile
capture and its repeat. Evidence:
[capture](../audits/2026-08-13-q022-high-profile-capture.md),
[repeat](../audits/2026-08-13-q022-high-profile-repeat-capture.md),
[presentation check](../audits/2026-08-13-q022-presentation-60fps-check.md),
[decision record](../audits/2026-08-14-q022-ratification.md).

### Q-022a — the zero-stall limit is measured only on captures known to be idle

A capture is now refused unless the machine is idle at its start: no other GPU
client, and contention indicators recorded per run. The zero-stall limit is
judged on captures that pass that precondition, and a contended capture is
refused rather than published.

This is not a relaxation of the limit. It fixes the method that produced twelve
steady-driving stalls in one matrix and zero in a repeat eleven hours later on
the same machine, same content and identical arguments, with one run recording
about ten times its siblings' GPU time at identical arguments. **The zero-stall
threshold remains failed** until a matrix that passes the idle precondition
records no stall; nothing here declares it passed.

### Q-022b — layer 2 is reserves, not measurements

The 3.0/3.0/2.5/1.5/2.0/1.0/0.7 ms subsystem values are labelled **unmeasured
reserves**. They are budget intent, not derived from measurement, and no
automation may cite them as a measured allocation or gate on them.

The reason is evidential: going from 330/132/77 instances and terrain stride 2 to
528/198/110 and stride 1 did not raise p95 or p99, and four of five target
scenarios came in lower than their balanced counterparts. The two profiles differ
by less than run-to-run variance at this content scale, so a per-subsystem
millisecond split derived from that comparison would be derived from noise.

Layer 3 content-class caps are unaffected by this and remain gateable, because
draw calls, primitives, materials, meshes and residency are counted directly
rather than inferred.

Layer 2 becomes ratifiable when per-subsystem attribution exists (Q-022c), not
when more whole-scene captures accumulate.

### Q-022d — the sustained-growth rule is ratified

Sustained memory growth fails when the fitted slope over a 30-minute steady-state
run exceeds **1 MiB/min with R² at or above 0.5**. Both constants are now part of
this ADR rather than proposed.

The R² term is load-bearing: without it the rule fires on ordinary
allocate-and-collect sawtooth, where a run that ends where it started can still
show a positive fitted slope. Two clean data points exist; the High 30-minute run
measured 0.56 MiB/min at R² 0.16.

Statements of the form "30-minute growth passed" now mean a ratified requirement
was met. Before this date they meant only that a proposed rule was met, and
audits written before it are qualified accordingly.

### Q-022e — a frame-capped run is judged on cap adherence

The 16.67 ms p95 limit above applies to uncapped runs. A run with an engine frame
cap is judged instead on whether it holds the cap: mean frame rate within 0.1 FPS
of the cap, p50 frame time within 0.1 ms of the cap period, and no stall above
50 ms.

The p95 limit is not applicable to a capped run, and this is arithmetic rather
than preference. A 60 FPS cap has a 16.6667 ms period, and the declared limit of
16.67 ms sits 3.3 microseconds above it. Passing would require 95% of frames to
land within 3.3 µs of the cap; measured pacing jitter is about 241 µs, roughly 72
times that budget. The limit is attainable in principle and unattainable in
practice, so applying it to a capped run marks a correct build as failing — the
measured run held 60.009 mean FPS with a 16.6625 ms p50, zero stalls, and about
2.7 ms mean render GPU time inside a 16.67 ms budget.

An engine frame cap is still not a 60 Hz output mode. The reference panel runs at
120 Hz; a true output-mode check would need a display mode change and is not
covered here.

## Q-022c addendum — 2026-08-16

The owner chose in-engine per-subsystem timers over an external profiler, Godot's
built-in profiler, and deferring. `Cannonball.Core.Performance.SubsystemProfiler`
times road, route context, environment, vehicle and UI at their own boundaries,
in exclusive time, and reference captures report mean and worst-frame CPU per
subsystem. Evidence:
[the attribution audit](../audits/2026-08-16-q022c-subsystem-attribution.md).

Q-022 is closed. All five questions are answered.

**Layer 2 stays unmeasured reserves, and the measurement is the reason.** Across
90 s on the representative corridor the five instrumented subsystems used 0.069 ms
of CPU per frame against a 2.09 ms mean frame — about 3%. A ratified
per-subsystem millisecond split would be a partition of 3% of the frame, which is
not what the layer-2 reserves are for. Q-022b's answer therefore stands on
measurement rather than on absence of measurement.

Two limits are recorded so later work does not rediscover them:

- **An in-process timer cannot separate a slow subsystem from a descheduled
  process.** One frame in the proof run charged about 25 ms each to road, route
  context and vehicle — one suspension, attributed to whichever region was open.
  Worst-frame subsystem figures must be read with that in mind. Means are
  unaffected.
- **GPU time is not attributed.** The reference workload is GPU-bound, 86% of
  frames in the proof run, and nothing here splits that.

Traffic, effects and lighting keep layer-2 reserves and are deliberately not
instrumented, because timing a system that does not exist reports a confident
zero.
