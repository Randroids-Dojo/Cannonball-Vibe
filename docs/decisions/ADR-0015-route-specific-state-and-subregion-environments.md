# ADR-0015: Route-specific state and subregion environments

- Status: Accepted
- Date: 2026-07-23
- Owner decision: Q-021 Option A

## Context

The Colorado mountain-to-plains corridor was built as a representative
environment-streaming fixture. It proves that one route can transition through
mountain, foothill, plains, and urban-edge presentation without terrain seams,
but it is not an art template for the entire coast-to-coast trip.

The intended experience is a realistic road trip that captures the look and
feel of every state traversed. State borders alone are not sufficient
environment boundaries: large states contain multiple landscapes, cities,
roadside cultures, climates, and highway construction patterns.

## Decision

- Production scenery uses route-specific state and subregion profiles.
- Every traversed state receives researched environmental identity along the
  actual playable corridor.
- A state may contain multiple profiles whenever geography, settlement,
  vegetation, geology, climate, or highway character changes materially.
- Transitions are placed from approved route and environmental evidence rather
  than evenly dividing distance or applying one palette to an entire state.
- Profiles may control terrain, vegetation, roadside development, skyline,
  structures, weather tendencies, lighting character, road furniture, and
  sign presentation while preserving authoritative road and route semantics.
- The Colorado mountain-to-plains corridor remains the first representative
  technical slice because it exercises several transitions economically. It
  does not constrain the appearance of other states.
- The visual target is grounded realism. Procedural and temporary low-detail
  assets remain valid engineering fixtures, but production approval requires
  state- and subregion-appropriate references, assets, rights, and rendered
  review.

## Consequences

- Environment metadata must support more than a state identifier and must
  permit deterministic transitions within a state.
- Art research and asset provenance become corridor-specific production work.
- Shared materials, meshes, and procedural rules should be reused where
  authentic, but convenience cannot flatten meaningful regional differences.
- Performance tiers must preserve regional identity even when reducing density,
  geometry, textures, or distant detail.
- Q-021 is resolved. Individual production assets, final readability, rights,
  and target-hardware performance evidence remain separate human gates.

## Rejected alternatives

- **Use Colorado as the visual model for the entire trip:** would erase the
  identity of other states and contradict the coast-to-coast premise.
- **Use one uniform profile per state:** is simpler but misrepresents states
  whose playable route crosses materially different landscapes.
- **Use only broad multi-state regions:** lowers production cost but loses the
  state-by-state sense of travel the game is intended to deliver.
