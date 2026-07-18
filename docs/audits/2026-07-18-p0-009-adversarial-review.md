# P0-009 adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `a5acf8106e89920f73ed389d756beaa08b75e485`
- Result: no unresolved actionable findings

## Scope

The review traced the schema-4 route-semantic contract from NHPN/3DEP input,
through normalized JSON and GeoPackage tables, FlatBuffer generation and
publication, the portable C# reader, route-position migration, save capture,
and the official-engine smoke scenario. Generated bindings were regenerated
from `schemas/route_graph.fbs` before review.

## Findings resolved during review

1. Python and C# distance-boundary validation used different equality rules.
   Both readers now accept the same 1e-9 tolerance for lane-section and map
   endpoints, and runtime lane lookup applies that tolerance with deterministic
   next-section selection at boundaries.
2. Connector successor uniqueness included the movement label, allowing the
   same lane pair to be declared twice under contradictory movement names.
   Exact pairs are unique in both languages; one-to-many splits and many-to-one
   merges are accepted only with the corresponding movement.
3. Python could accept connectors to a non-terminal lane section even though
   the C# runtime rejected them. Python now resolves only the incoming edge's
   final section and outgoing edge's first section.
4. Exit string collections and duplicate node IDs could fail later with generic
   serialization errors. They now fail in semantic validation with contextual
   messages.
5. New suspend saves still captured only a lane-count-derived legacy index.
   World projection now resolves the active vehicle lane from lateral position;
   save capture validates its index and stable ID against the active section.
   Old saves without that field retain deterministic index migration.
6. Connector movements were not checked against their source lane's allowed
   maneuver mask. Both validators now enforce the relationship.
7. The reproducible release packager still asserted schema 3 after the shipping
   package moved to schema 4. Its package-boundary assertion now requires schema
   4, and the copy step is covered by the same content-integrity checks.

## Residual boundaries

- The official corridor proves package transport and deterministic derivation,
  not continental completeness.
- NHPN-derived lane counts, shoulders, and connectors are explicit graybox
  defaults, not observed lane geometry.
- Authoritative lane counts, exits, destinations, services, and corrected
  milepoints remain governed by Q-017 and require approved source data or a
  deterministic authored overlay with recursive provenance.
- Variable-lane road mesh generation and rendered signs/map UI remain separate
  dependency-gated delivery tasks.

## Verification reviewed

- `./scripts/check.sh`: passed at the reviewed revision.
- .NET: 31 tests passed, zero warnings.
- Map pipeline: 60 tests passed; Ruff passed.
- PlayGodot unit layer: 12 tests passed.
- Godot 4.7.1 official headless scenario: `CANNONBALL_SMOKE_OK` on schema 4.
- Two clean fixture builds: every published file byte-identical, including the
  normalized GeoPackage, FlatBuffer root, metadata, and four CBCK chunks.
- Linux and Windows M0, reproducible exports, and Linux/Windows clean-machine
  export smokes passed on the recovery revision.
