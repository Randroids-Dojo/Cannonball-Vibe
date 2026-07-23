# ADR-0016: State-specific highway visual language

- Status: Accepted
- Date: 2026-07-23
- Owner decision: Q-024 Option A

## Context

The first modular highway kit used contemporary Colorado freeway references to
prove procedural roads, signs, markings, barriers, bridges, interchanges, and
streaming behavior. The coast-to-coast game must not apply Colorado's highway
appearance to every state any more than it applies Colorado terrain
everywhere.

Road design is part of regional identity. Sign programs, route shields,
markings, pavement, median treatment, barriers, bridge structures, roadside
furniture, maintenance condition, and surrounding development vary by
jurisdiction and corridor.

## Decision

- Production roads pursue contemporary, state-specific American highway
  realism along the actual playable route.
- Approved federal, state, and local references inform jurisdiction-specific
  signs, shields, markings, barriers, structures, roadside furniture, and
  placement.
- Shared modular assets remain desirable where real practice is shared, but
  state or corridor differences must remain data-driven and replaceable.
- Sign text, typography, hierarchy, contrast, retroreflection, lane assignment,
  and approach distance must be both realistic and legible at gameplay speed.
- Accessibility accommodations may improve presentation without inventing
  false route information or replacing the overall realistic visual language.
- Stable semantic IDs and procedural road topology remain authoritative. Art
  assets present those semantics and may not silently change lane connectivity,
  traffic direction, exits, transfers, or collision.
- Colorado remains the first researched technical baseline. Other states
  require their own reference, provenance, fixture, day/night capture, and
  readability review before production approval.

## Consequences

- The road asset registry and route-context data must support jurisdiction and
  corridor variants instead of one national skin.
- Signage and structures require a larger researched asset library and stronger
  provenance records.
- Production captures must demonstrate ordinary highway, lane changes, exits,
  transfers, bridges, and urban/rural transitions in representative states.
- Q-024 is resolved, but P1-009 remains in progress until the actual production
  assets, renderer budgets, rights records, and representative readability
  captures pass.

## Rejected alternatives

- **Apply the Colorado kit nationwide:** would create a coherent prototype but
  undermine the state-by-state travel experience.
- **Use a broadly stylized American freeway language:** reduces research and
  asset cost but weakens place identity and realism.
- **Use a retro interpretation:** would require a different vehicle, UI,
  infrastructure, and environmental product direction.
