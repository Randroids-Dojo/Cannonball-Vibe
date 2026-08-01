# ADR-0024: Canonical continental route graph

- Status: Accepted
- Date: 2026-07-31
- Owner decision: Q-031 direct route-selection instruction

## Context

The MVP requires one canonical 1:1 coast-to-coast path and two major route
alternatives. The route runtime, topology schema, sharding, save contract, and
representative interchange corpus are ready, but the repository previously had
no selected continental corridor to acquire and reconstruct.

The route must feel like a route graph rather than three nearly identical
lines. It must also remain compatible with the public-domain source policy:
NHPN can select route families and coarse topology, while exact playable
geometry, lanes, ramps, and endpoint connectors remain generated or authored
under ADR-0018.

The historical identity of the project supports a westbound trip from East
31st Street in Manhattan to Portofino Way in Redondo Beach. Those addresses are
reference anchors, not permission to enter or reproduce private property.

## Decision

- Lock the westbound Atlantic reference anchor at 142 E 31st Street, New York,
  and the Pacific reference anchor at 260 Portofino Way, Redondo Beach.
- Place playable endpoints on project-authored public-road portals adjacent to
  those anchors. Private driveways, garages, hotel grounds, and marina property
  are outside the required route.
- Select the **Central Rockies** path as canonical:
  East 31st Street connector, Lincoln Tunnel, NJ 495, NJ 3, US 46, I-80,
  I-76 at Big Springs, I-70 through Denver to Cove Fort, I-15, I-10, I-405,
  CA 107, and the authored Redondo Beach finish connector.
- Select the **Northern Plains** major alternative: share the I-80 eastern
  trunk, remain on I-80 from Big Springs through Wyoming to Salt Lake City,
  take I-15 south, and merge with the canonical path at Cove Fort.
- Select the **Southern I-40** major alternative: use the Holland Tunnel and
  I-78 to I-81, take I-81 south to I-40, follow I-40 west to Barstow, and merge
  with the shared I-15 approach to Los Angeles.
- Treat `data/routes/continental/route-selection.v1.json` as the versioned,
  machine-readable route-policy input. It names facilities and transfers but
  contains no authoritative lane geometry.
- Derive exact distance only after the selected NHPN object IDs and authored
  endpoint connectors are checksum-locked. Do not use consumer directions,
  straight-line distance, or an estimated mileage as authoritative run length.
- Acquire and validate only westbound directed carriageways for the first
  complete graph. A reverse-direction mode requires a later explicit product
  decision and its own directed topology validation.
- Preserve all signed concurrency encountered on the selected facilities under
  ADR-0017, including toll-road and overlapping Interstate identities.

## Why this graph

The canonical path reuses the existing Colorado technical investment while
covering dense eastern toll roads, plains, high mountain passes, desert, a
major urban finish, and several meaningful transfers. The northern branch
creates a credible weather, wind, elevation, and service-density trade through
Wyoming. The southern branch is genuinely independent for most of the country,
trading the central Rockies for Appalachia, the mid-South, southern plains, and
the Southwest before the Barstow merge.

All three paths are overwhelmingly controlled-access divided highways. That
fits the high-speed premise and the existing directed-carriageway contract,
while keeping surface-road work limited to the two endpoint service bubbles.

## Consequences

- Continental source acquisition and correction work now has a bounded graph
  instead of an unspecified national scope.
- The canonical path traverses New York, New Jersey, Pennsylvania, Ohio,
  Indiana, Illinois, Iowa, Nebraska, Colorado, Utah, Arizona, Nevada, and
  California.
- The northern alternative substitutes Wyoming for Colorado. The southern
  alternative traverses Maryland, West Virginia, Virginia, Tennessee,
  Arkansas, Oklahoma, Texas, New Mexico, and Arizona after Pennsylvania.
- Route distance, NHPN edge IDs, lane geometry, exits, signs, milepoints,
  services, elevation tiles, correction burden, and current closures remain
  acquisition and production facts, not facts established by this decision.
- The endpoint references require final rights and presentation review before
  public release; this decision does not grant trademark, property, or
  endorsement rights.

## Rejected alternatives

- **Three latitude bands with unrelated endpoints:** maximizes variety but
  weakens the shared coast-to-coast objective and multiplies endpoint work.
- **I-80 all the way to San Francisco:** is a strong northern transcontinental
  route but produces a large California backtrack to the Redondo Beach finish.
- **I-10 from Florida to Los Angeles:** is transcontinental but abandons the
  historical New York anchor and duplicates little of the first two paths.
- **Minor parallel detours around one canonical corridor:** are cheaper but do
  not satisfy the GDD requirement for major alternatives with distinct risk
  profiles.
