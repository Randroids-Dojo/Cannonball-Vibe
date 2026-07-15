# Agentic delivery readiness audit

- Date: 2026-07-14
- Scope: runtime, geodata/content, CI/release, and autonomous delivery
- Outcome: conditional go for the selected stack; no-go for claiming autonomous M0-M6 acceptance today
- Related decisions: [ADR-0001](../decisions/ADR-0001-godot-dotnet-prototype-stack.md), [ADR-0002](../decisions/ADR-0002-public-domain-geodata-contract.md), [ADR-0003](../decisions/ADR-0003-agentic-delivery-contract.md)
- Delivery ledger: [DELIVERY_LEDGER.json](../DELIVERY_LEDGER.json)

## Executive finding

Godot 4.6.3 .NET, C#, Jolt, Python/uv, GeoPandas, Rasterio, PROJ,
GeoPackage, FlatBuffers, DuckDB, Blender, and GitHub Actions are suitable for
the planned PC game. No engine or toolchain rewrite is required.

The repository currently automates a short technical slice, not milestone
delivery. Agents can build the implementation toward an unsigned internal
release once the P0 delivery gates below are closed. Subjective driving feel,
physical wheel behavior, accessibility usability, final rights review, signing
credentials, and store approval remain explicit human gates.

## Evidence collected

- `./scripts/check.sh` passed locally:
  - C# build completed with no warnings or errors;
  - 8 xUnit tests passed;
  - 6 pytest tests passed;
  - the Godot smoke wrote a suspend save and completed.
- The stronger headless driver reached 203.6 mph, traveled approximately
  1.9 km, loaded six chunks, rebased once, and used approximately 250 MB peak
  resident memory.
- Repeated fixture builds produced byte-identical JSON and FlatBuffers.
  GeoPackage bytes differed because `gpkg_contents.last_change` is generated.
- Dependency-lock and known-vulnerability checks passed.
- The implementation and workflows had not been committed when audited, so no
  remote CI result existed for this code.

These results demonstrate a credible foundation. They do not demonstrate the
100-500-mile M1 target, continental packaging, exact resume, packaged exports,
or an end-to-end autonomous delivery chain.

## P0 findings

### AR-001: Gameplay does not consume generated route content

`WorldStreamer` constructs procedural `RoadChunk` instances. The runtime never
uses the FlatBuffer route graph or an `IChunkSource` implementation. The current
pipeline also advertises `chunks/*.chunk` paths without writing the payloads.

Required evidence to close:

- independently hashable chunk payloads and a small root index;
- a `FileChunkSource` that rejects absent or corrupt chunks;
- a pipeline-to-C#-to-Godot fixture test;
- a Godot traversal that uses packaged content instead of `RoadMath`.

### AR-002: Exact save/resume is not integrated

The game writes saves but does not load and reconstruct route position, origin,
vehicle state, elapsed time, systems, or streaming state. The content checksum
does not cover the actual route package.

Required evidence to close:

- runtime load and reconstruction;
- route-package checksum validation;
- repeated save/load state-equivalence tests;
- corrupted, interrupted, and migrated-save tests.

### AR-003: The stress harness can report a false-green milestone

The scheduled stress mode runs 3,600 frames and currently covers about 1.9 km.
It asserts speed, one rebase, and chunk count, but not distance completion,
seams, collision misses, frame-time percentiles, chunk latency, memory growth,
or resumed-state equivalence. `scripts/check.sh` also succeeds when Godot is
missing.

Required evidence to close:

- a deterministic, distance-driven scenario runner;
- strict failure when required tools are unavailable;
- a 500-mile Linux and Windows traversal;
- machine-readable performance, continuity, and resume evidence.

### AR-004: The production geodata path is incomplete

The pipeline proves a synthetic transformation only. It has no resumable NHPN
or 3DEP acquisition, no input lockfile, no 3DEP sampling, no multigraph, no
regional sharding, no actual chunk publication, and no nationwide scale test.
Source attributes and directionality are discarded, grade is zero, and node
source coordinates are written as zero.

The audit also found that the NHPN DOI in the source catalog pointed to an
unrelated bridge report. The catalog was corrected to DOI
`10.21949/1522161` as part of documenting this audit.

Required evidence to close:

- catalog-enforced source manifests;
- resumable, paginated acquisition with pinned checksums and response metadata;
- source identifiers, travel direction, relevant attributes, and disconnected
  regions preserved in a multigraph;
- 3DEP elevation sampling with recorded horizontal and vertical datums;
- bounded regional builds and a coast-to-coast content fixture.

### AR-005: The GIS audit artifact can misassociate IDs and geometry

Edges are sorted after construction, while the GeoPackage geometry list retains
input order. The resulting audit artifact can associate a sorted edge ID with a
different source geometry.

Required evidence to close:

- sort complete edge records rather than parallel arrays;
- a reversed-input-order regression test;
- an assertion that each emitted ID maps to its expected geometry and source ID.

### AR-006: There is no packaged export or release path

`export_presets.cfg` is absent, CI installs no export templates, and no workflow
produces or launches Linux or Windows packages. Checksums, attestations, SBOMs,
release rollback, signing, and notarization are not defined.

Required evidence to close:

- exact-version export templates and checked-in presets;
- reproducible unsigned Linux and Windows packages;
- clean-machine launch tests and failure artifacts;
- an immutable artifact manifest and promotion procedure.

### AR-007: Repository-owned agent contracts are absent

At audit time there was no repository `AGENTS.md`, dependency-aware delivery
ledger, evidence schema, generated-output ownership policy, or authoritative
definition of done for agent tasks.

This finding is addressed structurally by the new `AGENTS.md`, decision records,
open-question register, and `DELIVERY_LEDGER.json`. The remaining ledger tasks
must still be implemented and verified.

## P1 findings

- Separate the 2 km collision window from the longer visual window.
- Move chunk construction off the main-thread critical path or enforce a build
  latency budget.
- Add all-assist-profile handling scenarios, road-departure checks, tunneling
  checks, and regression thresholds.
- Add save backup, quarantine, previous-version recovery, and crash injection.
- Add macOS CI before macOS becomes a required milestone platform.
- Pin Blender and automate headless export, import rules, asset budgets,
  provenance, LOD, and collision validation.
- Upload telemetry, saves, logs, metrics, and screenshots on CI failures.
- Pin GitHub Actions by immutable commit SHA and add timeouts, concurrency,
  retention, dependency scanning, and provenance generation.
- Keep official-Godot scenario drivers as the primary automation path.
  PlayGodot remains optional until its custom engine fork is available at the
  exact project version on every required platform.

## Human gates

Automation may prepare evidence for these gates but cannot approve them:

- 30-minute keyboard and controller handling sessions;
- physical Windows wheel calibration and feel;
- player understanding of risk, time, and build trade-offs;
- accessibility usability with representative users;
- final source and asset rights review;
- provisioning and approval of signing, notarization, and store credentials;
- public release approval.

## Decision

Proceed with the selected stack. Close the open P0 ledger items before broad
parallel M1-M6 feature implementation. Do not call a milestone complete unless
its machine-readable acceptance evidence exists and every declared human gate
has been approved.
