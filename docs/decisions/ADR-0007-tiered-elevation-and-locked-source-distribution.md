# ADR-0007: Tiered elevation and locked-source distribution

- Status: Accepted
- Date: 2026-07-16
- Extends: [ADR-0002](ADR-0002-public-domain-geodata-contract.md)

## Context

ADR-0002 selected public-domain geodata and 3DEP elevation but left production
resolution and final distribution approval open. USGS provides a seamless
1/3 arc-second product at approximately 10-meter spacing and higher-detail
1-meter products with route-dependent coverage. The exact locked NHPN service
describes its U.S. government work as available for unrestricted public use,
and the USGS catalog identifies 3DEP products as public domain.

## Decision

- Use seamless 1/3 arc-second 3DEP as the required deterministic elevation
  baseline.
- Permit a locked 1-meter upgrade per corridor only when complete route
  coverage, resolution-transition seams, visual and grade value, package size,
  and acquisition time pass recorded gates.
- Never perform an opportunistic production lookup or silent resolution
  fallback. Every selected elevation artifact remains checksum-locked.
- Public distribution is approved for the exact checksum-locked NHPN and USGS
  3DEP government data and project derivatives reviewed on 2026-07-16.
- Distribution must include source credit, recursive provenance, and a
  no-endorsement statement, and must not use agency logos.
- Any newly introduced source family requires a separate human rights review.

## Consequences

- All corridors retain a reproducible nationwide elevation floor while selected
  corridors may earn higher detail through measurable value.
- Resolution transitions and additional source size become explicit content
  gates rather than hidden pipeline behavior.
- The reviewed source families no longer block public distribution, but public
  release itself remains a separate human gate.
