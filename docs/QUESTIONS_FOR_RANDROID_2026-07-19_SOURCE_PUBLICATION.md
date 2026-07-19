# Source publication approval

## Q-027 — Publish the authoritative immutable source release?

P1-006 now has a complete GitHub draft independently downloaded and verified by
both a clean hosted runner and a separate local machine. As approved, it has now
been published as an immutable authoritative source release.

Candidate package:

- release tag: `source-lock-v1-9a8a9aa07bc8e4f2`
- authoritative release:
  <https://github.com/Randroids-Dojo/Cannonball-Vibe/releases/tag/source-lock-v1-9a8a9aa07bc8e4f2>
  
- content package ID:
  `9a8a9aa07bc8e4f2cf311229e60aac4673fefdff34448c38a23bb4f6924289d8`
- authoritative release manifest SHA-256:
  `ad3af30ced3e48fbb9c496827116ace9b238f2536f0459f947cabc424b5a180c`
- target revision: `eeca9743f8a11bd89b54a77df318760b18cba783`
- verified workflow:
  <https://github.com/Randroids-Dojo/Cannonball-Vibe/actions/runs/29697892648>
- unique retained objects: 12 from 14 lock references
- reconstructed bytes: 417,655,374
- sources: public-domain USDOT NHPN and USGS 3DEP
- ADR-0010 recovery-replica triggers: none
- additional service cost: none under the current GitHub primary-store decision

### Decision status

- **Approved 2026-07-19 as Option A**
- **Result:** Published as immutable release `source-lock-v1-9a8a9aa07bc8e4f2`,
  public URL above, draft to immutable status complete.
- **Verified properties:** `isDraft: false`, `isImmutable: true`, published at
  `2026-07-19T18:18:29Z`.

### A. Publish this exact verified draft (recommended)

- **Pros:** completes the authoritative retention path; freezes the tag and
  assets; GitHub generates a release attestation; future clean recovery no
  longer depends on the current upstream URLs continuing to serve exact bytes.
- **Cons:** publication is intentionally irreversible while immutable releases
  are enabled; the public repository gains roughly 398 MiB of release assets.

### B. Keep the verified draft unpublished

- **Pros:** preserves a reversible review window and avoids making the package
  publicly visible yet.
- **Cons:** P1-006 and the later public-release path remain incomplete; upstream
  reacquisition is still the only authoritative-byte recovery path.

### C. Delete the draft and revise the retention decision

- **Pros:** appropriate if the source set, rights approval, public visibility,
  or GitHub primary-store choice should change.
- **Cons:** discards verified preparation work and requires a superseding ADR
  plus a new candidate and reconstruction pass.

**Autonomous default:** executed (Option A) after explicit approval.
