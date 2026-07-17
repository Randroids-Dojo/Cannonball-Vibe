# ADR-0009: S3 Object Lock recovery replica with Vercel observation

- Status: Accepted
- Date: 2026-07-16
- Supersedes: Q-016 working default

## Context

ADR-0006 makes immutable GitHub Releases the primary store for exact retained
source artifacts. GitHub locks a published release's tag and assets, but an
administrator can still delete the entire release or repository. An independent
recovery copy is therefore required before the project can claim disaster
recovery.

Vercel was preferred where practical. Vercel Blob has useful CLI and SDK
automation, but its documented interface permits overwriting and deleting blobs
and deleting a complete store. Its recommendation to treat blobs as immutable
is an application convention, not enforced write-once retention. It therefore
cannot be the authoritative recovery replica.

Vercel can assume narrowly scoped AWS roles with short-lived OIDC credentials.
That makes it useful as an independent observer without placing large source
artifacts in a Vercel Function data path or making Vercel a restore dependency.
The supporting comparison is recorded in the
[source-recovery storage research](../research/2026-07-16-source-recovery-storage.md).

## Decision

- Keep immutable GitHub Releases as the authoritative primary source store.
- Replicate every retained source asset, recursive manifest, inventory record,
  and self-contained recovery kit to a dedicated AWS recovery account and an
  Amazon S3 general-purpose bucket.
- Enable S3 Versioning and Object Lock when the bucket is created, with a
  bucket-level default rule of `COMPLIANCE` retention for at least 365 days.
  Verify that every uploaded version inherited the mode and retain-until date.
  Extend retention before fewer than 180 days remain while the corresponding
  source artifact is authoritative. Do not configure automatic expiration.
- Use content-addressed keys of the form
  `sources/<release>/<sha256>/<asset-name>`. Inventory exact S3 version IDs;
  never use a mutable `latest` pointer as recovery authority.
- Sign each accepted inventory with a dedicated asymmetric catalog-signing key
  that the replication writer cannot use. The out-of-band recovery pointer
  holds the public key and the accepted catalog hash and S3 version ID, and
  restoration rejects unsigned or unanchored catalogs.
- Keep new objects in S3 Standard for the first 30 days so initial verification
  and drills are immediate. A later storage-class transition requires measured
  restore-time and cost evidence. Object Lock must remain effective across any
  transition.
- Replicate directly from the release job with GitHub Actions OIDC and multipart
  S3 operations. Complete upload, provider-checksum verification, retention
  verification, catalog signing, and an independent download before publishing
  the draft as an immutable GitHub release.
- Give the replication role only the upload, list, head, and checksum
  permissions it needs. It receives no catalog-signing, object-version deletion,
  bucket administration, governance-bypass, or retention permission.
- Run an AWS-native scheduled retention steward with only list,
  `GetObjectRetention`, and compliance-safe `PutObjectRetention` access. It
  extends every version under the protected `sources/`, `catalogs/`,
  `recovery-kit/`, and `drills/` prefixes before fewer than 180 days remain and
  has no content read, write, delete, signing, or retention-bypass permission.
  Its extension drill must work with GitHub and Vercel unavailable.
- Use SSE-S3 unless a later ADR defines a separately recoverable KMS lifecycle.
  A deleted customer-managed key must not make locked recovery bytes unreadable.
- Use Vercel materially as a read-only health plane: a production-only Vercel
  OIDC role inspects the inventory, S3 version IDs, checksums, retention
  horizon, and latest drill evidence. Vercel must not proxy artifact bytes or be
  required to replicate or restore them.
- Maintain an independent AWS read-only recovery identity and store the restore
  tooling inside the locked bucket. A destructive drill must succeed from a
  clean machine with GitHub, Vercel, upstream source hosts, and local/CI caches
  unavailable.
- Keep a minimal recovery pointer outside AWS, GitHub, and Vercel in two
  human-controlled locations. It records the AWS account and region, bucket,
  exact bootstrap-kit key and version ID, restore-role ARN, independent
  authentication and credential-custody procedure, catalog verification public
  key, accepted catalog hash/version ID, and first CLI bootstrap command.
- Give the drill identity append-only `PutObject` access only under a locked
  `drills/<run-id>/<evidence-sha256>/` prefix. It cannot alter or delete prior
  versions, bypass retention, or write source/catalog prefixes. Consumers use
  the recorded exact version ID instead of an unversioned key. Vercel observes
  the resulting immutable drill evidence.
- Configure monthly AWS budget alerts at USD 5 and USD 10. Replication must stop
  before upload and block release publication when a deterministic estimate for
  the full retention window would exceed USD 10 recurring monthly run rate
  without human approval. Actual cost and alert evidence remain completion
  requirements for P1-005.

## Required inventory

Each immutable inventory entry records at least:

- GitHub repository, release tag, asset name, asset ID, and byte count;
- project SHA-256 and recursively locked manifest SHA-256;
- S3 bucket, key, version ID, provider checksum, and storage class;
- Object Lock mode and retain-until timestamp;
- replication revision, UTC timestamp, role identity, commands, and result;
- independent download and restore-drill evidence references.

## Consequences

- The recovery bytes reside in a provider and credential domain independent of
  GitHub, with retention that a compromised automation role cannot bypass.
- Vercel remains useful for agentic monitoring through short-lived OIDC
  credentials, but losing a Vercel project cannot prevent recovery.
- GitHub remains in the normal write path. The locked recovery kit and an
  independent AWS identity remove GitHub from the disaster restore path.
- S3 account ownership, region, OIDC roles, budget alarms, and break-glass access
  still require human credential and spending setup. P1-005 remains open until
  provisioning, denied-delete evidence, complete replication, and a destructive
  restore drill pass.
- Compliance retention creates a deliberate minimum storage commitment. An
  erroneous upload cannot be deleted early, so draft manifests and hashes must
  be validated before replication.
- Object Lock does not protect against closure or loss of the AWS account,
  billing failure, or provider-wide failure. The dedicated account,
  out-of-band recovery pointer, custody checks, and billing alarms mitigate but
  do not eliminate that residual risk. Cross-account replication remains a
  future escalation if retained volume and risk justify its cost.

## Sources

- [Vercel Blob overview](https://vercel.com/docs/vercel-blob)
- [Vercel Blob CLI management](https://vercel.com/docs/vercel-blob/manage-blob-storage)
- [Vercel OIDC access to AWS and S3](https://vercel.com/docs/oidc/aws)
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [S3 Object Lock and lifecycle considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html)
