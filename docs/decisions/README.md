# Architecture decision records

Architecture decision records are append-only. If a decision changes, add a
new ADR that supersedes the old one instead of rewriting history.

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-0001](ADR-0001-godot-dotnet-prototype-stack.md) | Superseded | Godot 4.6.3 .NET prototype stack |
| [ADR-0002](ADR-0002-public-domain-geodata-contract.md) | Accepted | Public-domain-only geodata and portable route packages |
| [ADR-0003](ADR-0003-agentic-delivery-contract.md) | Accepted | Evidence-backed agent delivery with explicit human gates |
| [ADR-0004](ADR-0004-godot-4-7-1.md) | Accepted | Upgrade the active engine pin to Godot 4.7.1 .NET |
| [ADR-0005](ADR-0005-official-engine-agentic-automation.md) | Accepted | Official-engine automation with a modern PlayGodot runtime bridge |
| [ADR-0006](ADR-0006-github-release-source-retention.md) | Accepted | GitHub Releases as the primary immutable full-size source store |
| [ADR-0007](ADR-0007-tiered-elevation-and-locked-source-distribution.md) | Accepted | Tiered 3DEP elevation and guarded distribution of locked government sources |
| [ADR-0008](ADR-0008-required-playgodot-after-ui-value-gate.md) | Accepted | Require modern PlayGodot after the representative rendered-UI value gate |
| [ADR-0009](ADR-0009-s3-object-lock-recovery-replica.md) | Accepted | AWS S3 Object Lock recovery replica with a read-only Vercel health plane |
| [ADR-0010](ADR-0010-defer-independent-source-replica.md) | Accepted | Defer the independent recovery replica until its activation threshold is met |
| [ADR-0011](ADR-0011-lane-topology-route-context-and-trip-map.md) | Accepted | Distance-bounded lane topology, semantic route context, and an authoritative full-screen trip map |
| [ADR-0012](ADR-0012-agentic-visual-asset-pipeline.md) | Accepted | Agentic 3D asset pipeline with replaceable vehicle, road, and environment contracts |
| [ADR-0013](ADR-0013-highway-lane-transition-control-lines.md) | Accepted | Stable highway control lines and speed-designed lane transitions |
| [ADR-0014](ADR-0014-directed-carriageways-and-road-markings.md) | Accepted | Reciprocal directed carriageways and correct yellow/white road-marking semantics |
| [ADR-0015](ADR-0015-route-specific-state-and-subregion-environments.md) | Accepted | Realistic route-specific state and subregion environment profiles |
| [ADR-0016](ADR-0016-state-specific-highway-visual-language.md) | Accepted | Contemporary state-specific American highway realism |
| [ADR-0017](ADR-0017-authoritative-route-context-and-concurrency.md) | Accepted | Authoritative route-context sources and readable concurrency presentation |
| [ADR-0018](ADR-0018-gated-generated-road-reconstruction.md) | Accepted | Gated generated road reconstruction with authored exceptions |
| [ADR-0019](ADR-0019-route-package-budgets-and-audit-reproducibility.md) | Accepted | Route-package size ceilings and semantic GeoPackage reproducibility |
| [ADR-0020](ADR-0020-required-platforms-and-macos-validation.md) | Accepted | Required Linux/Windows delivery with non-committed macOS validation |
| [ADR-0021](ADR-0021-phased-commercial-release-channels.md) | Accepted | Steam commercial authority with itch.io early distribution and GitHub technical releases |
| [ADR-0022](ADR-0022-host-neutral-agent-automation-without-required-mcp.md) | Accepted | Host-neutral CLI, PlayGodot, and Computer Use automation without required MCP |
| [ADR-0023](ADR-0023-reference-performance-target-and-layered-budgets.md) | Accepted | 1440p High at 60 FPS on the reference PC with layered, measured budgets |
