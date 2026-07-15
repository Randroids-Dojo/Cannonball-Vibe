# ADR-0002: Public-domain geodata and portable route packages

- Status: Accepted
- Date: 2026-07-14

## Context

The game needs a continental route backbone without creating share-alike or
attribution obligations that are incompatible with the intended content
pipeline. NHPN can provide coarse highway topology and route families, while
USGS 3DEP can provide elevation. Neither source supplies production lane-level
geometry.

## Decision

- Accept only cataloged sources whose license status is verified as public
  domain and whose exact acquired artifacts have checksums and evidence.
- Reject OpenStreetMap-derived ancestry from the shipping route pipeline.
- Use NHPN only as a topology and route-family backbone.
- Use 3DEP for elevation and grade, with recorded horizontal and vertical
  datums.
- Reconstruct deterministic, drivable lane-level splines and validate them
  independently from the source geometry.
- Emit a small FlatBuffer root index plus independently hashable regional or
  route chunks. GeoPackage remains an inspectable audit artifact, not the
  runtime format.
- Preserve provenance recursively from source response through every shipping
  chunk.

## Consequences

- Acquisition, correction, sharding, and publishing must be automated and
  restartable from an input lockfile.
- A source being public domain is necessary but not sufficient; fidelity,
  topology, elevation, and drivability gates still apply.
- Authored overrides are permitted only when their inputs, ownership, and
  machine-checkable validation are recorded.
- Final rights review remains a human release gate.
