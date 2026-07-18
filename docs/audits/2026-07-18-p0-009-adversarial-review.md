# P0-009 adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `dd4d3d4ba5d43dfe1f71e7f562142766a67fe717`
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
8. Unequal boundary lane counts were truncated to the smaller side. Derivation
   now emits complete, non-crossing one-to-many split and many-to-one merge
   mappings, with matching Python and C# ambiguity rules and 2-to-3/3-to-2 tests.
9. Milepoint and marker identity references were only checked globally. Both
   readers now require the identity to belong to the referenced edge, with
   mismatched-identity regression coverage.
10. Semantic provenance accepted arbitrary well-formed source IDs and hashes.
    Validation now binds every record to the package source artifact already
    approved by the catalog and acquisition lock; the shipping source policy
    continues to reject OpenStreetMap ancestry.
11. The C# simplified-map budget used a partial hand estimate. It now measures
    the actual FlatBuffer serialization of the map vector, including strings,
    hashes, offsets, vectors, and alignment.
12. The audit package carried schema-4 semantic references while declaring
    schema 1 or 2, and several optional serializer fields used direct indexing.
    Schema and payload are now atomic; optional fields use runtime-safe defaults.
13. Reproducibility evidence omitted exact commands, inputs, pointer, and chunk
    identities. The evidence now records tool/input hashes, both clean commands
    and outputs, every published artifact path/hash, and byte-identical results.

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
- .NET: 35 tests passed, zero warnings.
- Map pipeline: 66 tests passed; Ruff passed.
- PlayGodot unit layer: 12 tests passed.
- Godot 4.7.1 official headless scenario: `CANNONBALL_SMOKE_OK` on schema 4.
- Two post-review clean fixture builds: every published file byte-identical, including the
  normalized GeoPackage, FlatBuffer root, metadata, and four CBCK chunks.
- Linux and Windows M0, reproducible exports, and Linux/Windows clean-machine
  export smokes passed on the recovery revision.
