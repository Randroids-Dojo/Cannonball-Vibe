# Open questions

This register contains unresolved choices that can materially change scope,
architecture, validation, or release. Defaults permit progress; they are not
final answers. Close a question by recording evidence and linking the resulting
ADR, GDD decision, or delivery-ledger change.

| ID | Priority | Blocking milestone | Owner | Question | Working default | Evidence required |
| --- | --- | --- | --- | --- | --- | --- |
| Q-001 | P0 | M3 | Product | Is 1:1 travel the main commercial mode or an endurance variant? | Build 1:1 first while preserving data and scoring for compression. | Long-run retention tests at 1:1, 3:1, and selective cruise compression. |
| Q-002 | P0 | M2 | Geodata | Is NHPN's coarse and aging topology acceptable for geographically inspired corridors? | Use NHPN as a route-family backbone, never as lane geometry. | Official-source corridor fixtures, measured correction burden, and human map sanity review. |
| Q-003 | P0 | M2 | Geodata | Can deterministic spline reconstruction and generated interchange corrections eliminate routine hand authoring? | Allow generated overrides only when continuity, grade, curvature, collision, sightline, and self-intersection gates pass. | Representative divided-highway, ramp, overpass, border, and parallel-edge fixtures. |
| Q-004 | P0 | M1 | Runtime | What root-index and chunk-size budgets keep continental streaming bounded? | Root index under 64 MB and individual chunks under 16 MB. | Cached 500-mile and coast-to-coast traversals with latency and memory telemetry. |
| Q-006 | P1 | M1 | Input | Which physical wheel defines the MVP calibration baseline? | One common force-feedback-capable Windows wheel; force feedback remains optional. | Device selection, calibration protocol, and a recorded human handling session. |
| Q-007 | P1 | M5 | Release | Which release channel is authoritative: GitHub Releases, itch.io, or Steam? | Produce unsigned CI artifacts before choosing a storefront. | Audience, patching, signing, telemetry, cost, and approval requirements compared in an ADR. |
| Q-008 | P1 | M2 | Geodata | Must GeoPackage be byte-reproducible or only semantically reproducible? | Treat it as a non-shipping audit artifact and normalize volatile timestamps where practical. | Cross-platform comparison proving stable feature IDs, geometry, CRS, attributes, and content version. |
| Q-009 | P1 | M1 | Platform | When does macOS become a required validation and export platform? | Linux and Windows are required for M1; add macOS before public platform commitment. | Target-platform decision and available clean-machine CI/export capacity. |
| Q-010 | P1 | M3 | Product | How dense must meaningful driving and route decisions be? | Target one meaningful tactical or strategic change every few minutes with deliberate quiet periods. | Telemetry and player recall from representative 45-60 minute sessions. |
| Q-012 | P2 | M3 | Automation | Does an MCP adapter or editor bridge add unique value beyond the PlayGodot protocol, CLI, filesystem tools, and Computer Use? | Keep the runtime protocol host-neutral and do not require MCP. | Exact 4.7.1 support, security review, transactional edits, audit logs, narrow tool profile, and a measured workflow improvement. |

## Recently resolved

| Decision | Resolution |
| --- | --- |
| Prototype engine | Godot 4.7.1 .NET; see [ADR-0004](decisions/ADR-0004-godot-4-7-1.md). |
| Runtime route format | FlatBuffer index and independently hashable chunks; see [ADR-0002](decisions/ADR-0002-public-domain-geodata-contract.md). |
| Fully agentic acceptance | Machine gates may be autonomous; subjective, physical, legal, credential, and release gates require humans; see [ADR-0003](decisions/ADR-0003-agentic-delivery-contract.md). |
| Legacy PlayGodot engine fork and debugger transport | Retired; modern PlayGodot may return as a debug-only official-engine addon for semantic rendered-UI automation; see [ADR-0005](decisions/ADR-0005-official-engine-agentic-automation.md). |
| Q-011 PlayGodot adoption | Required project test infrastructure after the first representative interactive menu demonstrates lower diagnosis cost or unique defect coverage versus CLI evidence plus Computer Use. Until that final threshold is measured, it remains optional, debug-only, and non-shipping; see [ADR-0008](decisions/ADR-0008-required-playgodot-after-ui-value-gate.md). Decision recorded 2026-07-16. |
| Q-013 source rights | Approved for public distribution of the exact checksum-locked NHPN and USGS 3DEP government data and project derivatives, with source credit, provenance, a no-endorsement statement, and no agency logos. See [ADR-0007](decisions/ADR-0007-tiered-elevation-and-locked-source-distribution.md). Human approval recorded 2026-07-16. |
| Q-014 production elevation | Use seamless 1/3 arc-second 3DEP as the deterministic required baseline. Permit a locked 1-meter upgrade per corridor only when coverage, seam, visual/grade value, package-size, and acquisition-time gates pass; see [ADR-0007](decisions/ADR-0007-tiered-elevation-and-locked-source-distribution.md). Decision recorded 2026-07-16. |
| Q-015 immutable source retention | Use content-addressed immutable GitHub Release assets as the authoritative primary store; deterministically split artifacts that exceed the per-asset limit and keep local/CI copies as caches only. Independent disaster recovery is conditional under ADR-0010. See [ADR-0006](decisions/ADR-0006-github-release-source-retention.md). Decision recorded 2026-07-16. |
| Q-016 independent recovery replica | Defer provisioning while retained sources remain public, checksum-locked, and reliably reacquirable. If the activation threshold is met, use the ADR-0009 S3 Object Lock design and its required read-only Vercel health plane. See [ADR-0010](decisions/ADR-0010-defer-independent-source-replica.md). Decision recorded 2026-07-16. |
