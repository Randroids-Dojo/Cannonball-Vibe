# ADR-0021: Phased commercial release channels

- Status: Accepted
- Date: 2026-07-23
- Owner decision: Q-007 Option A

## Context

Cannonball needs separate homes for customer-facing commercial builds, early
playable builds, and technical/source artifacts. Treating one service as all
three would either weaken the eventual customer release or impose commercial
store operations on technical retention and provenance workflows.

The current official service terms establish materially different roles:

- [Steam Direct](https://partner.steamgames.com/doc/gettingstarted/appfee)
  charges a USD 100 product-submission fee per app, recoupable after the product
  reaches USD 1,000 in adjusted gross revenue.
- [itch.io](https://itch.io/docs/creators/faq.amp) has no upfront creator fee
  and permits a configurable platform revenue share. Its
  [pricing modes](https://itch.io/docs/creators/pricing) support free,
  paid, pay-what-you-want, and early-access projects.
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
  supports downloadable release assets and remains the project's established
  technical artifact, source-retention, checksum, and provenance surface.

These terms are time-sensitive and must be reverified before any commercial
submission or publication.

## Decision

- Steam is the authoritative commercial customer channel for the premium PC
  release.
- itch.io may host explicitly labeled demos, early builds, or early-access
  builds when doing so improves testing or access before the Steam release.
- GitHub Releases remains the technical channel for source-retention packages,
  checksums, provenance, SBOMs, and suitable engineering artifacts. It is not
  the authoritative commercial storefront.
- Channel-specific packages must come from the same approved, checksum-bound
  release inputs and must preserve version identity across every published
  channel.
- This ADR does not authorize paying the Steam Direct fee, creating storefront
  records, accepting commercial terms, using credentials, uploading a build, or
  publishing anything. Every such action remains explicitly human-gated.

## Consequences

- Product copy, pricing, community operations, patch promotion, and customer
  support can target Steam without overloading the technical release surface.
- itch.io can support low-friction early distribution without becoming the
  authority for the final commercial product.
- GitHub source retention and technical evidence remain independent from store
  availability.
- P1-003 is no longer blocked by an undecided release channel. It remains
  blocked by incomplete dependencies and by its signing, credentials, spending,
  store-submission, and public-release human gates.
- Release preparation must recheck current fees, revenue terms, package limits,
  signing requirements, and platform rules before acting.

## Rejected alternatives

- **Steam only for every artifact:** mixes customer distribution with technical
  provenance and makes early testing unnecessarily store-dependent.
- **itch.io as the final commercial authority:** reduces upfront friction but
  does not match the selected long-term premium-PC storefront strategy.
- **GitHub Releases as the customer storefront:** works for technical downloads
  but does not provide the selected commercial discovery, purchasing, patching,
  and customer-facing release workflow.
