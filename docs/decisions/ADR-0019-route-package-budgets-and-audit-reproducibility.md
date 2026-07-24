# ADR-0019: Route-package budgets and audit reproducibility

- Status: Accepted
- Date: 2026-07-23
- Owner decisions: Q-004 Option A and Q-008 Option A

## Context

Continental streaming needs bounded startup data and independently recoverable
chunks without creating so many tiny artifacts that file, request, hash, and
transition overhead dominate. The current pipeline and runtime already enforce
a root index below 64 MB and individual shipping chunks below 16 MB.

Shipping FlatBuffers are content-addressed runtime inputs and must remain
byte-reproducible. GeoPackage is a non-shipping geographic audit artifact.
Equivalent GeoPackage databases can differ in timestamps, metadata ordering,
SQLite page layout, and tool-specific storage details even when every
meaningful feature is identical.

## Decision

- Retain a hard 64 MB maximum for the root route index.
- Retain a hard 16 MB maximum for each independently hashed shipping route
  chunk.
- Treat these values as validated ceilings. Tighten them only when cached and
  cold 500-mile plus coast-to-coast telemetry demonstrates a measurable
  startup, memory, streaming-latency, recovery, or update benefit.
- Shipping FlatBuffer indexes and chunks remain byte-reproducible and
  content-addressed.
- GeoPackage output requires semantic reproducibility across platforms:
  feature IDs, geometry, CRS, attributes, relationships, provenance, and
  content version must compare equivalent.
- Normalize volatile GeoPackage metadata where practical, but do not fail an
  otherwise equivalent audit database solely because its complete file hash or
  SQLite storage layout differs.
- GeoPackage remains an inspectable audit artifact and never becomes an
  authoritative runtime input.

## Consequences

- Startup and stream reads remain bounded by already-proven package limits.
- Future limit changes require evidence rather than arbitrary preference.
- Cross-platform audits compare meaningful geographic content without brittle
  dependence on database implementation details.
- Release verification can continue to use exact hashes for shipping packages
  while recording semantic comparison evidence for GeoPackage.
- Q-004 and Q-008 are resolved.

## Rejected alternatives

- **Aggressively shrink every artifact immediately:** increases file and
  request overhead without current evidence of a net benefit.
- **Relax the ceilings:** risks larger memory spikes, stalls, recovery units,
  and update payloads.
- **Require byte-identical GeoPackage files:** confuses storage-layout
  repeatability with geographic-content repeatability and is brittle across
  platforms.
- **Remove GeoPackage:** would discard a useful standards-based inspection and
  debugging surface.
