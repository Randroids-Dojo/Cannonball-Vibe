# Questions after the carriageway and traffic-direction pass

Engineering continues under ADR-0014. The route package, renderer, and fixtures
can now distinguish reciprocal divided-highway carriageways from unpaired ramps
and one-way roads without guessing. This file contains the remaining product
scope choice; it does not block the safe schema and marking correction.

## Q-026 — Launch support for undivided two-way highways

**Resolved 2026-07-23 — Option A.** The first complete corridor proves divided
mainlines, one-way ramps, handling, and directed traffic. Undivided two-way
highways remain planned as P1-011, with an explicit bidirectional cross-section,
centerline, traffic, collision, and junction contract rather than an inference
inside the current one-direction lane model.

Which roadway families should the first playable long-distance corridor support?

### A. Divided mainlines plus one-way ramps first (recommended)

- **Pros:** matches the coast-to-coast high-speed premise; keeps every runtime
  lane moving one direction; makes navigation, traffic, collision, streaming,
  and road paint much easier to verify agentically; still supports exits,
  entrances, transfers, frontage connectors, and true one-way roadways.
- **Cons:** undivided US/state highways and temporary two-way configurations
  cannot be selected until a later bidirectional cross-section slice ships.

### B. Add undivided two-way highways before the first playable corridor

- **Pros:** permits more authentic rural route alternatives and a broader road
  network from the beginning.
- **Cons:** adds a second lane-direction model, centerline passing/no-passing
  rules, much higher head-on traffic and collision risk, new junction templates,
  new signs/markings, and substantially more visual and gameplay validation
  before the core traffic loop is proven.

### C. Use divided mainlines only; omit ramps and other one-way roads initially

- **Pros:** smallest possible geometry and traffic surface.
- **Cons:** removes exits, services, highway transfers, detours, and most route
  strategy—the systems already established by P0-009 through P0-012.

The phased scope is approved. Keep divided mainlines as reciprocal directed
carriageways, keep ramps and true one-way roadways unpaired, and begin P1-011
only after its handling and traffic dependencies complete.
