# ADR-0017: Authoritative route context and readable concurrency

- Status: Accepted
- Date: 2026-07-23
- Owner decisions: Q-017 Option A and Q-018 Option A

## Context

Coarse national highway topology cannot establish exact lane counts, exit
numbers, signed destinations, services, or milepoint anchors by itself.
Inventing those details would conflict with the game's state-specific realism
and could display plausible-looking but false route information.

Real highways can also carry several signed route identities concurrently.
Showing every shield on every roadside marker preserves completeness but can
become unreadable at speed. Showing only the player's selected trip route loses
real concurrency and can make numbering resets, exits, and transfers
misleading.

## Decision

- Prefer checksum-locked authoritative public records for lane counts, exits,
  destinations, services, milepoint anchors, signed directions, and route
  concurrency.
- When approved sources omit required playable detail, use a deterministic
  authored overlay with recursive provenance, reviewer-visible source notes,
  and content-addressed output.
- Distinguish observed, derived, and authored values in data and evidence.
  Unknown values remain unknown rather than receiving false precision.
- NHPN may provide route-family topology but is never treated as observed lane,
  ramp, exit, destination, or marker geometry.
- Preserve every signed concurrent route identity in the authoritative route
  package.
- Roadside markers show the locally primary signed designation needed for
  high-speed readability.
- The full-screen map and semantic inspection surfaces expose all concurrent
  identities, directions, numbering discontinuities, and jurisdiction resets.
- The locally primary roadside designation may change deterministically along
  a concurrency when authoritative records or an approved overlay establish
  that change.

## Consequences

- Each production corridor needs a source-comparison and correction pass rather
  than one national inference rule.
- Authored correction work is reproducible and auditable but becomes a real
  content-production cost.
- Renderer simplicity does not discard route truth: complete concurrency
  remains available to navigation, saves, maps, inspection, and automation.
- Representative fixtures must cover concurrent routes, primary-designation
  changes, signed direction, state or jurisdiction resets, missing exact
  values, and deterministic authored overlays.
- Q-017 and Q-018 are resolved. Individual corridor source acquisition,
  correction burden, rendered readability, and production-sign quality remain
  task acceptance work.

## Rejected alternatives

- **Infer missing semantics from coarse linework:** is fast but creates false
  confidence and cannot support state-specific realism.
- **Hand-author everything without structured provenance:** gives control but
  makes corrections difficult to audit and reproduce.
- **Show every concurrent shield on every roadside marker:** preserves truth
  but can overwhelm high-speed readability.
- **Discard non-primary concurrent identities:** simplifies rendering by losing
  information needed for accurate markers, exits, transfers, and maps.
