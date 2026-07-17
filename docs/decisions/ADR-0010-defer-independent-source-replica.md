# ADR-0010: Defer the independent source recovery replica

- Status: Accepted
- Date: 2026-07-16
- Amends: ADR-0009 activation timing

## Context

ADR-0009 defines a sound independent disaster-recovery architecture: S3
Versioning and `COMPLIANCE` Object Lock for retained source bytes, with Vercel
as its required read-only health plane upon P1-005 activation. The current retained-source corpus is
small, consists of public government data that can be reacquired from recorded
upstream URLs, and is protected by exact checksums and recursive manifests.
The project has not yet published its first immutable GitHub source release.

The storage charge would be negligible, but a second provider introduces
credentials, billing, retention stewardship, restore drills, and an additional
operational plane before there is unique or irreplaceable material to recover.
That work does not currently reduce the highest delivery risk.
The current inventory and accepted reacquisition risk are recorded in the
[source-replica deferral audit](../audits/2026-07-16-source-replica-deferral.md).

## Decision

- Keep content-addressed immutable GitHub Releases, exact checksums, recursive
  manifests, and recorded upstream URLs as the required source-retention path.
- Do not provision AWS, Vercel monitoring, or an independent replica now.
- Preserve ADR-0009 and its research as the approved implementation design if
  an independent recovery replica is activated later.
- Supersede ADR-0009's requirement to replicate below-threshold public sources
  before publishing an immutable GitHub release. All other ADR-0009 controls,
  including its Vercel health plane, apply if P1-005 is activated.
- Treat P1-005 as conditional backlog rather than a release dependency.
- Activate P1-005 before retaining any source that is unique, privately
  licensed, legally critical, expensive to reconstruct, or no longer reliably
  reacquirable from its recorded upstream authority.
- Reassess activation when retained-source recovery value exceeds the ongoing
  credential, billing, monitoring, and drill burden, or when the project owner
  explicitly approves the additional recovery plane.

## Consequences

- The current release path has no AWS or Vercel storage cost and no recovery
  credentials to administer.
- A GitHub or repository-loss event requires reacquiring public source bytes
  and verifying them against the locked checksums. It does not have an
  independent one-command replica restore.
- The first immutable GitHub source release and its reconstruction evidence
  remain release-critical through P1-006; this decision does not weaken
  checksum, provenance, or release-immutability requirements.
- If an activation trigger occurs, ADR-0009 supplies the default architecture,
  but credentials, spend, provisioning, and a destructive restore drill still
  require explicit evidence before disaster recovery may be claimed.
