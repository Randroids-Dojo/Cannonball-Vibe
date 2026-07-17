# Source-replica deferral audit

- Date: 2026-07-16
- Decision: [ADR-0010](../decisions/ADR-0010-defer-independent-source-replica.md)
- Scope: activation timing for P1-005

## Current retained-source state

Live repository inspection found no published GitHub Releases:

```bash
gh release list --json tagName,name,isImmutable,publishedAt --limit 10
# []
```

The locked upstream acquisition inventory contains three full source responses:

| Source | Bytes | Recovery information |
| --- | ---: | --- |
| USDOT NHPN feature response | 1,210 | Exact upstream query URL and SHA-256 |
| USGS 3DEP GeoTIFF | 410,392,672 | Exact public object URL and SHA-256 |
| USGS metadata response | 13,110 | Exact upstream URL and SHA-256 |
| **Total** | **410,406,992** | |

The source URLs, response sizes, and hashes are locked in
`data/sources/source-lock.json`. P0-003 evidence records the checksum and
provenance verification, and ADR-0007 records the public-government-source
rights approval. Fixture derivatives are also committed with independent
hashes.

## Risk acceptance

The project accepts that loss of GitHub and all caches would currently require
reacquiring the public upstream responses and verifying them against the locked
hashes. It must not claim independent disaster recovery while P1-005 is
inactive.

This is acceptable now because there is no published authoritative source
release and the locked bytes are public, checksum-addressed, and reproducible
from recorded authorities. P1-006 remains release-critical for the primary
immutable GitHub source publication. P1-005 becomes mandatory before retaining
unique, privately licensed, legally critical, expensive-to-reconstruct, or
unreliable-to-reacquire source material.
