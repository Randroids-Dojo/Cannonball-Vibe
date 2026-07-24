# Questions from the 2026-07-17 autonomous delivery run

This file is the handoff point for choices that cannot be resolved safely by
repository authority, deterministic evidence, or the working defaults in
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). Work continues autonomously wherever a
documented default permits it.

## Q-017 and Q-018 resolved 2026-07-23

The owner selected Option A for both route-truth questions. Production route
context uses checksum-locked authoritative public records first and
deterministic authored overlays with recursive provenance where necessary.
Every signed concurrent identity remains authoritative; roadside presentation
shows the locally primary designation while the full-screen map and inspection
surfaces expose all concurrent identities. See
[ADR-0017](decisions/ADR-0017-authoritative-route-context-and-concurrency.md).

## Q-002 and Q-003 resolved 2026-07-23

The owner selected Option A for both road-reconstruction questions. NHPN
remains a national route-family backbone rather than playable geometry.
Deterministic generated corrections must pass strict geometry, collision,
sightline, lane-topology, and driving gates; rejected or exceptional locations
use recursively provenanced authored overlays. See
[ADR-0018](decisions/ADR-0018-gated-generated-road-reconstruction.md).

## No additional blocking questions from this run

P0-009 can proceed with deterministic derived two-lane semantics and explicit
authored-overlay provenance under ADR-0017. No derived value will be presented
as observed lane, exit, destination, or mile-marker truth.

P0-010 required no product choice. Its deterministic authored fixture now
exercises variable lanes, connector traversal, probable-branch prewarming and
eviction, and junction seams. Full alternative interchange routing remains the
separate dependency-gated P0-011 task, so no user decision is required before
continuing.

P0-011 also requires no new product choice. Under the resolved Q-003 policy, its
representative diamond and directional-transfer geometry is an explicitly
authored, checksum-verified regression overlay with recursive source
provenance. It validates the generator and runtime contracts without claiming
that NHPN supplied observed ramp or lane geometry. Corridor correction burden
remains measured production evidence rather than an unresolved architecture
choice.

P0-005 requires no new product choice. Exact resume state, package identity,
atomic replacement, one-generation backup recovery, previous-schema migration,
and deterministic fuzz counts are technical integrity contracts already fixed
by the readiness audit and delivery ledger.

P0-006 requires no new product choice. The distance-complete automation route
is an explicitly authored, checksum-bound fixture used only to validate the
streamer, local-origin precision, collision windows, metrics, and resume
contract. It does not assert invented geometry as observed geography. The
ledger's 30-minute keyboard and controller sessions remain a separate human
handling gate.
