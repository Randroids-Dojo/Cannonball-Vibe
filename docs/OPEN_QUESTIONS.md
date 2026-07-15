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
| Q-005 | P1 | M1 | Automation | Is PlayGodot worth maintaining beside the official-Godot scenario runner? | Use the official engine and in-process scenario runner first. | Exact-version Linux, Windows, and macOS fork availability plus a UI/input test that cannot be covered otherwise. |
| Q-006 | P1 | M1 | Input | Which physical wheel defines the MVP calibration baseline? | One common force-feedback-capable Windows wheel; force feedback remains optional. | Device selection, calibration protocol, and a recorded human handling session. |
| Q-007 | P1 | M5 | Release | Which release channel is authoritative: GitHub Releases, itch.io, or Steam? | Produce unsigned CI artifacts before choosing a storefront. | Audience, patching, signing, telemetry, cost, and approval requirements compared in an ADR. |
| Q-008 | P1 | M2 | Geodata | Must GeoPackage be byte-reproducible or only semantically reproducible? | Treat it as a non-shipping audit artifact and normalize volatile timestamps where practical. | Cross-platform comparison proving stable feature IDs, geometry, CRS, attributes, and content version. |
| Q-009 | P1 | M1 | Platform | When does macOS become a required validation and export platform? | Linux and Windows are required for M1; add macOS before public platform commitment. | Target-platform decision and available clean-machine CI/export capacity. |
| Q-010 | P1 | M3 | Product | How dense must meaningful driving and route decisions be? | Target one meaningful tactical or strategic change every few minutes with deliberate quiet periods. | Telemetry and player recall from representative 45-60 minute sessions. |

## Recently resolved

| Decision | Resolution |
| --- | --- |
| Prototype engine | Godot 4.6.3 .NET; see [ADR-0001](decisions/ADR-0001-godot-dotnet-prototype-stack.md). |
| Runtime route format | FlatBuffer index and independently hashable chunks; see [ADR-0002](decisions/ADR-0002-public-domain-geodata-contract.md). |
| Fully agentic acceptance | Machine gates may be autonomous; subjective, physical, legal, credential, and release gates require humans; see [ADR-0003](decisions/ADR-0003-agentic-delivery-contract.md). |
