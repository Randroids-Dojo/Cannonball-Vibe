# ADR-0023: Reference performance target and layered budgets

- Status: Accepted
- Date: 2026-07-23
- Owner decisions: Q-022 target/method and threshold follow-ups, Options A and A

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
  the gate.
- At the High preset, provisional memory ceilings are 9.5 GB of GPU memory and
  16 GB of process working set, with no sustained positive growth during a
  30-minute steady-state run.
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
