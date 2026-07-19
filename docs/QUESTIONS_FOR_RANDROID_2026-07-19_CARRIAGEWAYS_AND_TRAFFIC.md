# Questions after the carriageway and traffic-direction pass

Engineering continues under ADR-0014. The route package, renderer, and fixtures
can now distinguish reciprocal divided-highway carriageways from unpaired ramps
and one-way roads without guessing. This file contains the remaining product
scope choice; it does not block the safe schema and marking correction.

## Q-026 — Launch support for undivided two-way highways

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

**Autonomous default:** option A. Keep divided mainlines as reciprocal directed
carriageways, keep ramps/true one-way roadways unpaired, and treat undivided
two-way support as a later explicitly designed task rather than an inference.
