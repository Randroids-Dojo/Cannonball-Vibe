# ADR-0006: GitHub Releases as the primary immutable source store

- Status: Accepted
- Date: 2026-07-16

## Context

Exact full-size source artifacts must remain retrievable after upstream public
URLs change. Local and CI caches are useful accelerators but are not durable
provenance. GitHub Release assets keep retained inputs alongside the repository
and release history, but each individual asset must remain under 2 GiB and each
release may contain at most 1,000 assets.

## Decision

- Use GitHub Releases as the authoritative primary store for locked full-size
  source artifacts.
- Require GitHub immutable releases to be enabled for the repository. The
  setting was enabled and verified through the repository API on 2026-07-16.
- Address every retained artifact by SHA-256 and record its release tag, asset
  name, byte count, and checksum in the source lock or a recursively locked
  manifest.
- Split any artifact at or above GitHub's per-asset limit into deterministic,
  content-addressed parts with a checked manifest and verified reconstruction.
- Treat local and CI copies only as disposable caches. A successful cache hit
  must still verify against the authoritative checksum.
- Create each release as a draft, attach and verify every asset, and only then
  publish it so GitHub locks the tag and assets and generates the release
  attestation.
- Verify the published release is immutable, verify its attestation, perform an
  independent download, reconstruct split artifacts, and check every checksum
  before a retained artifact is considered published.

## Consequences

- Source retention uses existing GitHub access and release operations without a
  separate storage provider or credential domain.
- Published tags and assets cannot be changed or individually deleted. Deletion
  of an entire release remains an administrative recovery risk, so retention
  operations must include a periodic inventory and recovery check.
- GitHub Releases alone do not constitute disaster recovery. Q-016 remains open
  until an independent recovery replica and restore drill are selected.
- Moving to an object store later requires a superseding ADR and a verified
  migration that preserves every content hash.

## Setting verification

```bash
gh api -H 'X-GitHub-Api-Version: 2026-03-10' \
  repos/Randroids-Dojo/Cannonball-Vibe/immutable-releases
# {"enabled":true,"enforced_by_owner":false}
```
