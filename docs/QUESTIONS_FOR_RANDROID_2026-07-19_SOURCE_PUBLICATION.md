# Source publication approval

## Q-027 — Publish the authoritative immutable source release?

P1-006 now has a complete GitHub draft independently downloaded and verified by
both a clean hosted runner and a separate local machine. No irreversible action
has been taken.

Candidate package:

- release tag: `source-lock-v1-9a8a9aa07bc8e4f2`
- private collaborator draft:
  <https://github.com/Randroids-Dojo/Cannonball-Vibe/releases/tag/untagged-0be3e542fa7aee6b50e3>
- content package ID:
  `9a8a9aa07bc8e4f2cf311229e60aac4673fefdff34448c38a23bb4f6924289d8`
- final draft manifest SHA-256:
  `735dc00797ea8998a7cd8a49d44c2ac3d4963045675bd95fd97e421783a2f84b`
- draft target revision: `c40b7ec4ce99bfe6aa22e4489cacd1caa0f203e7`
- verified workflow:
  <https://github.com/Randroids-Dojo/Cannonball-Vibe/actions/runs/29697892648>
- unique retained objects: 12 from 14 lock references
- reconstructed bytes: 417,655,374
- sources: public-domain USDOT NHPN and USGS 3DEP
- ADR-0010 recovery-replica triggers: none
- additional service cost: none under the current GitHub primary-store decision

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

**Autonomous default:** option B. Preparing and verifying the draft is within
the agentic delivery contract; publishing it requires your explicit answer.
