# Source publication approval

## Q-027 — Publish the authoritative immutable source release?

P1-006 has a fully local-verified candidate. After the implementation PR merges,
the automated workflow will create and independently download a GitHub draft.
This document will then be updated with the exact draft URL and final manifest
SHA-256 before any irreversible action.

Candidate package:

- release tag: `source-lock-v1-9a8a9aa07bc8e4f2`
- content package ID:
  `9a8a9aa07bc8e4f2cf311229e60aac4673fefdff34448c38a23bb4f6924289d8`
- unique retained objects: 12 from 14 lock references
- reconstructed bytes: 417,655,374
- sources: public-domain USDOT NHPN and USGS 3DEP
- ADR-0010 recovery-replica triggers: none
- additional service cost: none under the current GitHub primary-store decision

### A. Publish this exact verified draft (recommended after draft evidence lands)

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

**Autonomous default:** option B. Preparing and verifying the draft is within
the agentic delivery contract; publishing it requires your explicit answer.
