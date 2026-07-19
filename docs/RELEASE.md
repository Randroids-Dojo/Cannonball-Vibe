# Release operations

## Authoritative locked-source publication

P1-006 retains every artifact referenced by
`data/sources/source-lock.json` and
`data/sources/representative-corridor-lock.json` in an immutable GitHub
Release. The package is content-addressed, deduplicated by SHA-256, and
independent of local and Actions caches.

The current inventory contains public-domain USDOT NHPN and USGS 3DEP data.
Its ADR-0010 classifications live in
`data/sources/retention-classification.json`. The verifier fails before upload
if a source is unclassified or if any classification activates P1-005.

### Local validation

```bash
./scripts/source-retention/verify-release.sh \
  --classify-replica-trigger \
  --self-test
```

The self-test forces a small input through the same deterministic splitter used
for release assets. Normal source assets are split only when they exceed
1,900,000,000 bytes, safely below GitHub's 2 GiB per-asset limit.

### Prepare the draft

Run the `Immutable source retention` workflow with `operation=draft`, or run:

```bash
./scripts/source-retention/publish-release.sh --draft
```

The command:

1. verifies that immutable releases are enabled;
2. resolves every lock reference and verifies its exact SHA-256 and byte count;
3. deduplicates identical bytes and creates deterministic content-addressed
   assets, lock copies, a classification copy, a manifest, and `SHA256SUMS`;
4. creates or resumes a draft release without overwriting an existing asset;
5. downloads the complete draft into a new temporary directory, reconstructs
   every retained object, and verifies every checksum.

Draft creation is reversible and is not public release approval. Do not publish
until the owner records approval of the exact draft tag and manifest hash.

### Publish the approved draft

Run the same workflow with `operation=publish` and the durable approval
reference, or run:

```bash
./scripts/source-retention/publish-release.sh \
  --publish \
  --approval-reference 'Q-027 approved YYYY-MM-DD'
```

Publishing is irreversible while immutable releases remain enabled. The script
refuses a missing approval reference. After publication it downloads and
reconstructs the package again, requires GitHub to report the release as
immutable, and verifies GitHub's release attestation for every uploaded asset.

### Recovery from a clean environment

```bash
./scripts/source-retention/verify-release.sh --tag SOURCE_RELEASE_TAG
```

This downloads only GitHub Release assets, validates `SHA256SUMS`, validates
the retained lock copies, reconstructs split and unsplit objects into an empty
temporary directory, and compares their sizes and SHA-256 values to the
manifest. Local downloads under `.tools/source-retention/cache` are disposable
accelerators and are never accepted without checksum verification.

GitHub Release storage and bandwidth do not add a project service bill under
the current decision. ADR-0010 defers the separate AWS/Vercel recovery plane
until its explicit activation conditions are met.

GitHub's current immutable-release and verification behavior is documented in
[Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
and [Verifying the integrity of a release](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity).
