# Question for Randroid after the highway-kit baseline

This new handoff records the one art-direction choice that should not be guessed
autonomously. P1-009 can continue technically under the default, but it remains
`in_progress` until the final visual-quality and rights gate is approved.

Review artifact:
[P1-009 highway-kit contact sheet](images/p1-009-highway-kit-review.png)

## Q-024 — production highway visual language

**Resolved 2026-07-23 — Option A, generalized across the trip.** Production
roads pursue contemporary, state-specific American highway realism along the
actual route. Colorado remains the first researched technical baseline rather
than a nationwide skin. See
[ADR-0016](decisions/ADR-0016-state-specific-highway-visual-language.md).

Which visual language should guide the production road, signage, and regional
asset pass?

### A. Contemporary Colorado freeway realism (working default)

- **Pros:** matches the existing Front Range data and current official-reference
  research; gives signs, markings, barriers, and roadside furniture a coherent
  authority; best supports geographic readability.
- **Cons:** raises the quality bar for accurate typography, shield shapes,
  supports, structures, terrain, and jurisdiction details; final assets need a
  careful rights and reference review.

### B. Stylized modern American freeway

- **Pros:** allows stronger silhouette, color, and readability exaggeration;
  reduces pressure to reproduce every Colorado construction detail exactly;
  may age more gracefully as source data changes.
- **Cons:** weakens place identity and makes it easier for inconsistent or
  generic signage to slip through; requires a clear style guide to avoid an
  arbitrary low-detail look.

### C. Retro road-trip interpretation

- **Pros:** could give Cannonball a distinctive nostalgic identity and support
  more expressive roadside architecture and vehicles.
- **Cons:** conflicts with the current contemporary standards baseline and would
  require a broader product, vehicle, UI, prop, and environment rethink; period
  accuracy and rights research add scope.

The visual-language decision is closed. Do not call P1-009
production-complete until sign readability, representative state/corridor
day/night captures, renderer budgets, and exact asset-rights records pass.
