# ADR-0006: GitHub Releases for immutable source retention

- Status: Accepted
- Date: 2026-07-16

## Context

Exact full-size source artifacts must remain retrievable after upstream public
URLs change. Local and CI caches are useful accelerators but are not durable
provenance. GitHub Release assets keep retained inputs alongside the repository
and release history, but each individual asset must remain under 2 GiB.

## Decision

- Use GitHub Releases as the authoritative durable store for locked full-size
  source artifacts.
- Address every retained artifact by SHA-256 and record its release tag, asset
  name, byte count, and checksum in the source lock or a recursively locked
  manifest.
- Split any artifact at or above GitHub's per-asset limit into deterministic,
  content-addressed parts with a checked manifest and verified reconstruction.
- Treat local and CI copies only as disposable caches. A successful cache hit
  must still verify against the authoritative checksum.
- Verify upload, independent download, reconstruction when split, and checksum
  before a retained artifact is considered published.

## Consequences

- Source retention uses existing GitHub access and release operations without a
  separate storage provider or credential domain.
- Release-asset deletion remains an administrative risk rather than enforced
  write-once storage, so release publication must include a periodic inventory
  and recovery check.
- Moving to an object store later requires a superseding ADR and a verified
  migration that preserves every content hash.
