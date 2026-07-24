# Open questions

This register contains unresolved choices that can materially change scope,
architecture, validation, or release. Defaults permit progress; they are not
final answers. Close a question by recording evidence and linking the resulting
ADR, GDD decision, or delivery-ledger change.

The current multiple-choice handoff for Q-022 is
[here](QUESTIONS_FOR_RANDROID_2026-07-18_AUTONOMOUS.md), plus the latest
[systematic-backlog handoff](QUESTIONS_FOR_RANDROID_2026-07-18_SYSTEMATIC_BACKLOG.md).
The exact source-release publication handoff is
[Q-027](QUESTIONS_FOR_RANDROID_2026-07-19_SOURCE_PUBLICATION.md).
The current trip-map usability handoff is
[Q-028](QUESTIONS_FOR_RANDROID_2026-07-19_TRIP_MAP.md).
The current camera-comfort handoff is
[Q-029](QUESTIONS_FOR_RANDROID_2026-07-20_HANDLING_GATES.md).

| ID | Priority | Blocking milestone | Owner | Question | Working default | Evidence required |
| --- | --- | --- | --- | --- | --- | --- |
| Q-002 | P0 | M2 | Geodata | Is NHPN's coarse and aging topology acceptable for geographically inspired corridors? | Use NHPN as a route-family backbone, never as lane geometry. | Official-source corridor fixtures, measured correction burden, and human map sanity review. |
| Q-003 | P0 | M2 | Geodata | Can deterministic spline reconstruction and generated interchange corrections eliminate routine hand authoring? | Allow generated overrides only when continuity, grade, curvature, collision, sightline, and self-intersection gates pass. | Representative divided-highway, ramp, overpass, border, and parallel-edge fixtures. |
| Q-004 | P0 | M1 | Runtime | What root-index and chunk-size budgets keep continental streaming bounded? | Root index under 64 MB and individual chunks under 16 MB. | Cached 500-mile and coast-to-coast traversals with latency and memory telemetry. |
| Q-006 | P1 | M1 | Input | Which physical wheel defines the MVP calibration baseline? | One common force-feedback-capable Windows wheel; force feedback remains optional. | Device selection, calibration protocol, and a recorded human handling session. |
| Q-007 | P1 | M5 | Release | Which release channel is authoritative: GitHub Releases, itch.io, or Steam? | Produce unsigned CI artifacts before choosing a storefront. | Audience, patching, signing, telemetry, cost, and approval requirements compared in an ADR. |
| Q-008 | P1 | M2 | Geodata | Must GeoPackage be byte-reproducible or only semantically reproducible? | Treat it as a non-shipping audit artifact and normalize volatile timestamps where practical. | Cross-platform comparison proving stable feature IDs, geometry, CRS, attributes, and content version. |
| Q-009 | P1 | M1 | Platform | When does macOS become a required validation and export platform? | Linux and Windows are required for M1; add macOS before public platform commitment. | Target-platform decision and available clean-machine CI/export capacity. |
| Q-012 | P2 | M3 | Automation | Does an MCP adapter or editor bridge add unique value beyond the PlayGodot protocol, CLI, filesystem tools, and Computer Use? | Keep the runtime protocol host-neutral and do not require MCP. | Exact 4.7.1 support, security review, transactional edits, audit logs, narrow tool profile, and a measured workflow improvement. |
| Q-017 | P0 | M2 | Geodata | Which approved sources and authored processes establish lane counts, exit numbers, destinations, and milepoint anchors? | Prefer checksum-locked public-domain records; otherwise use deterministic authored overlays with recursive provenance and never infer false lane or marker precision from NHPN. | Source comparison on representative corridors, field completeness, correction burden, rights review, and reproducible overlay builds. |
| Q-018 | P1 | M2 | Product + geodata | How should roadside markers present route concurrency, direction-specific numbering, discontinuities, and jurisdiction resets? | Preserve each signed route reference; render the locally primary designation roadside and expose concurrent identities in inspection and the full-screen map. | Representative multi-state and concurrent-route fixtures compared with approved reference records and human readability review. |
| Q-022 | P1 | M5 | Runtime + art | What quantitative budgets should production vehicle, road, terrain, vegetation, materials, and textures meet? | Measure and ratify budgets on the declared Ryzen 9 5900X / RTX 3080 Ti / 64 GB Windows 11 reference PC; do not treat it as the minimum supported PC without a separate decision. | CPU/GPU frame-time percentiles, memory high-water, streaming latency, draw calls, triangles, material/texture residency, and LOD quality comparisons on the [declared reference hardware](audits/2026-07-23-reference-windows-hardware.md). |
| Q-028 | P0 | M3 | Product + accessibility | Does the P0-013 first-pass trip map communicate route progress, alternatives, exits, transfers, services, and controls clearly without relying only on color? | Keep P0-013 in progress while the machine-verified build and capture await owner review. | Owner review of the representative capture and keyboard/controller interaction; see the Q-028 handoff. |
| Q-029 | P0 | M0 | Product + accessibility | Are the stabilized chase and cockpit cameras comfortable and readable during sustained driving, braking, resets, and view changes? | Keep P0-017 and dependent P0-018 in progress until both views receive an explicit owner decision. | Five-minute owner review in each view using the Q-029 handoff. |

## Recently resolved

| Decision | Resolution |
| --- | --- |
| Prototype engine | Godot 4.7.1 .NET; see [ADR-0004](decisions/ADR-0004-godot-4-7-1.md). |
| Runtime route format | FlatBuffer index and independently hashable chunks; see [ADR-0002](decisions/ADR-0002-public-domain-geodata-contract.md). |
| Fully agentic acceptance | Machine gates may be autonomous; subjective, physical, legal, credential, and release gates require humans; see [ADR-0003](decisions/ADR-0003-agentic-delivery-contract.md). |
| Legacy PlayGodot engine fork and debugger transport | Retired; the modern debug-only addon runs on official Godot 4.7.1 and requires no engine fork; see [ADR-0005](decisions/ADR-0005-official-engine-agentic-automation.md). |
| Q-011 PlayGodot adoption | Activated for interactive rendered-UI surfaces after the representative driver-menu comparison exposed focus and state unavailable through Computer Use. It remains debug-only and absent from release packages; see [ADR-0008](decisions/ADR-0008-required-playgodot-after-ui-value-gate.md). Decision activated 2026-07-19. |
| Q-013 source rights | Approved for public distribution of the exact checksum-locked NHPN and USGS 3DEP government data and project derivatives, with source credit, provenance, a no-endorsement statement, and no agency logos. See [ADR-0007](decisions/ADR-0007-tiered-elevation-and-locked-source-distribution.md). Human approval recorded 2026-07-16. |
| Q-014 production elevation | Use seamless 1/3 arc-second 3DEP as the deterministic required baseline. Permit a locked 1-meter upgrade per corridor only when coverage, seam, visual/grade value, package-size, and acquisition-time gates pass; see [ADR-0007](decisions/ADR-0007-tiered-elevation-and-locked-source-distribution.md). Decision recorded 2026-07-16. |
| Q-015 immutable source retention | Use content-addressed immutable GitHub Release assets as the authoritative primary store; deterministically split artifacts that exceed the per-asset limit and keep local/CI copies as caches only. Independent disaster recovery is conditional under ADR-0010. See [ADR-0006](decisions/ADR-0006-github-release-source-retention.md). Decision recorded 2026-07-16. |
| Q-016 independent recovery replica | Defer provisioning while retained sources remain public, checksum-locked, and reliably reacquirable. If the activation threshold is met, use the ADR-0009 S3 Object Lock design and its required read-only Vercel health plane. See [ADR-0010](decisions/ADR-0010-defer-independent-source-replica.md). Decision recorded 2026-07-16. |
| Q-023 asset rights policy | Permit project-original, CC0, and clearly redistributable assets only after an exact manifest and human rights review. Pending or restricted records remain fixture-only or excluded. The project owner approved the policy and exact graybox fixture rights record on 2026-07-18; future assets still require individual review. |
| Q-025 | P0-012 representative lane/interchange validation corpus geographic plausibility review | Approved 2026-07-19 as Option A in [QUESTIONS_FOR_RANDROID_2026-07-18_SYSTEMATIC_BACKLOG.md](QUESTIONS_FOR_RANDROID_2026-07-18_SYSTEMATIC_BACKLOG.md#q-025--p0-012-geographic-plausibility-and-route-choice-review). |
| Q-027 | P1-006 source publication and immutable release | Approved 2026-07-19 as Option A in [QUESTIONS_FOR_RANDROID_2026-07-19_SOURCE_PUBLICATION.md](QUESTIONS_FOR_RANDROID_2026-07-19_SOURCE_PUBLICATION.md#q-027--publish-the-authoritative-immutable-source-release). Published as `source-lock-v1-9a8a9aa07bc8e4f2`; P1-006 is now complete. |
| Q-021 route-specific regional environments | Approved 2026-07-23 as Option A: pursue grounded realism for every traversed state, with multiple route-specific subregion profiles where the real geography changes. Colorado remains a representative technical slice, not the coast-to-coast art template; see [ADR-0015](decisions/ADR-0015-route-specific-state-and-subregion-environments.md). |
| Q-020 project-original Hero GT | Approved 2026-07-23 as Option A: develop the project-original Hero GT and existing semantic rig into the production vehicle. Final silhouette, cockpit/chase visibility, materials, damage presentation, renderer budgets, and rights evidence remain P1-008 acceptance gates. |
| Q-024 state-specific highway realism | Approved 2026-07-23 as Option A: production roads, signs, structures, markings, and roadside assets pursue contemporary, state-specific American highway realism along the actual route; see [ADR-0016](decisions/ADR-0016-state-specific-highway-visual-language.md). |
| Q-019 solo trip-map pause | Approved 2026-07-23 as Option A: opening the full-screen map in solo play pauses driving and excludes the paused interval from the authoritative run clock. Competitive or challenge modes may use separate explicitly communicated rules later. |
| Q-026 phased undivided two-way highways | Approved 2026-07-23 as Option A: prove divided mainlines, one-way ramps, handling, and traffic first; add explicit undivided two-way cross-sections and opposing-traffic behavior later under P1-011 rather than inferring them in the existing lane model. |
| Q-001 defining run-length mode | Approved 2026-07-23 as Option A: 1:1 Endurance is the defining primary coast-to-coast experience; shorter Standard and Challenge modes remain available from the same authoritative route distance and content. See GDD decisions D-009 and D-013. |
| Q-010 activity density | Approved 2026-07-23 as Option A: target a meaningful speed, route, stop, or risk decision every few minutes on average, with deliberate quiet highway stretches for contrast and authentic pacing. See GDD decision D-013. |
