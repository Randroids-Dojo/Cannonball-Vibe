# P1-006 immutable source-publication review

- Date: 2026-07-19
- Task: P1-006
- Status: implementation and local reconstruction verified; draft publication
  and owner approval pending

## Outcome

The release tooling maps all 14 authoritative lock references to 12 unique
SHA-256 objects and retains 417,655,374 unique bytes. Identical objects referenced
by both source locks are uploaded once while every originating lock path,
acquisition index, artifact index, source ID, role, expected byte count, and
origin remains in the manifest.

The package also carries exact copies of both source locks, the ADR-0010 source
classification, a versioned manifest, and `SHA256SUMS`. Names are
content-addressed. Inputs over the configured 1.9 GB ceiling are split at exact
byte offsets into ordered content-addressed parts; clean verification rebuilds
every object before comparing its byte count and SHA-256.

## Recovery classification

Both retained sources are public-domain government data with locked authority
URLs and recursive checksums. Neither source is unique, privately licensed,
legally critical, expensive to reconstruct, or currently unreliable to
reacquire. The classification therefore does not activate P1-005. Missing
classifications, unexpected sources, malformed flags, or any activation reason
fail preparation before a release is created.

## Verification performed

- `verify-release.sh --classify-replica-trigger --self-test`: passed; two
  sources classified, 14 references, 12 unique objects, no trigger; forced
  splitter test produced five ordered parts and reconstructed the original hash.
- Full preparation downloaded exact NHPN, 3DEP, and metadata authority bytes,
  verified all checked-in derivations, and produced package
  `9a8a9aa07bc8e4f2cf311229e60aac4673fefdff34448c38a23bb4f6924289d8`.
- `verify-release.sh --assets ...`: passed from a new reconstruction directory;
  all 417,655,374 retained bytes matched.
- A second preparation from the verified cache produced byte-identical release
  assets and an identical result document.
- `actionlint`, Bash syntax checks, Node syntax checks, and `git diff --check`
  passed.
- The full repository front door passed: doctor, clean .NET build, 72 C# tests,
  Ruff, 78 map-pipeline tests, 12 PlayGodot unit tests, and the official Godot
  4.7.1 headless smoke.

## Adversarial review

The review challenged duplicate lock references, oversized objects, cache
trust, stale or missing classifications, partial uploads, shell injection,
mutable releases, draft verification, and clean recovery.

Corrections and controls include:

- workflow inputs cross the shell boundary through an environment variable,
  not direct expression interpolation;
- cache hits are accepted only after exact SHA-256 verification;
- uploads never use overwrite or clobber behavior;
- the complete draft is downloaded and reconstructed before publication;
- downloaded asset names are constrained to safe basenames, the checksum
  inventory must exactly equal the manifest inventory, retained lock copies are
  reparsed to reproduce all references, and the package ID is recomputed;
- the publish mode refuses an empty durable approval reference;
- published verification requires GitHub's `isImmutable` state and verifies the
  release attestation for every asset;
- local validation uses the same builder and verifier as hosted publication.

No unresolved implementation finding remains. The remaining acceptance blocker
is the intentional owner gate in
[Q-027](../QUESTIONS_FOR_RANDROID_2026-07-19_SOURCE_PUBLICATION.md).
