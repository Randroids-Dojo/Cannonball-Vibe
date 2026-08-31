# Cannonball-Vibe agent contract

These instructions apply to the entire repository. They define how autonomous
work is scoped, verified, evidenced, and handed off.

## Authority

Use repository sources in this order when they conflict:

1. Accepted ADRs in `docs/decisions/`.
2. `docs/DELIVERY_LEDGER.json` for task status, dependencies, and acceptance.
3. `docs/TECH_STACK.md` for current architecture and tool boundaries.
4. `gdd.md` for product intent, milestone outcomes, and unresolved design.
5. README files for operational guidance.

Record new architecture decisions as append-only ADRs. Record unresolved
choices in `docs/OPEN_QUESTIONS.md`. Record dated investigation results in
`docs/audits/`. Do not silently resolve a product or architecture question in
code.

## Current stack

- Godot 4.7.1 .NET, Forward+, Godot Jolt, 120 Hz physics.
- C# 12 targeting .NET 8; the repository pins .NET SDK 10.0.102.
- `Cannonball.Core` is engine-independent.
- Python/uv, GeoPandas, Rasterio, PROJ, GeoPackage, and FlatBuffers implement
  the offline route pipeline.
- JSONL and DuckDB implement local telemetry and analysis.
- Blender produces glTF/GLB assets once the asset pipeline is automated.

Do not replace a selected tool without evidence that it cannot meet a declared
gate and a superseding ADR.

## Architecture boundaries

- `src/Cannonball.Core/` owns authoritative route position, run and economy
  state, deterministic streams, save contracts, telemetry contracts, and the
  portable route reader. It must not depend on Godot.
- `game/` owns Godot input, rigid-body physics, rendering, generated collision,
  local-origin conversion, and runtime orchestration.
- `tools/map_pipeline/` owns source validation, acquisition, normalization,
  elevation, topology, chunk generation, and provenance.
- `schemas/` owns versioned runtime data contracts. Generated schema code is an
  output; change the schema and generator rather than hand-editing generated
  files.
- Shipping route state uses edge ID plus distance-along-edge. Do not make
  ephemeral mesh transforms authoritative.

## Before starting a task

1. Check mainline health: `gh issue list --label red-main --state open`. If
   main is red, the repair is this session's task; new work waits.
2. Select an open task from `docs/DELIVERY_LEDGER.json`.
3. Claim the slice before implementing. Check for an existing claim with
   `gh pr list --state open --search "<task-id>"` and
   `git ls-remote origin 'refs/heads/*<task-id>*'`; if another branch or PR
   already names the task's slice, select different work. Otherwise push
   your branch and open a draft PR titled with the task ID as your first
   act — the draft PR is the claim. Two sessions probing the same slice
   concurrently (PR #88 vs #92, 2026-08-30) is the failure this prevents.
4. Confirm that every dependency is `complete` or that the task explicitly
   allows work against a fixture.
5. Declare the files and generated outputs the task owns. Avoid parallel work
   that writes the same schema, generated code, lockfile, or content package.
6. Read the linked ADR, audit finding, open question, and acceptance criteria.
7. Record any necessary scope change in the ledger or a new decision record
   before implementation.

Use separate branches or worktrees for concurrent tasks. Preserve unrelated
changes in a dirty worktree.

### Mainline integration

Integration is PR-only and merges exclusively through auto-merge (ADR-0025).
Open the pull request, run `gh pr merge <number> --auto --squash`, and move
on to the next task; do not wait for the merge. The only merge gates are the
`M0 (ubuntu-latest)` and `M0 (windows-latest)` checks. No human or service
review happens before merge; CodeRabbit is retired.

All other suites — PlayGodot, the deterministic long-route suite, assets,
unsigned exports, source retention, and the Windows soak — are post-merge
tripwires. The `Mainline health` workflow watches the CI, assets, unsigned
exports, and Windows soak workflows on main (PlayGodot and the long-route
suite are CI jobs, so their failures fail the watched CI run) and maintains
a single open issue labeled `red-main` while any watched workflow is
failing. Source retention is not health-watched (ADR-0025); its failures
surface on the PRs that touch its paths.

Fix-forward law: never revert, never force-push, and never bypass-merge to
land work. A red main is repaired with new commits through the same PR flow;
administrator bypass is reserved for governance operations. When the failure
was the daily Windows soak, re-dispatch it after the fix
(`gh workflow run windows-stress.yml`) so the signal clears without waiting
for the next cron run.

Post-merge adversarial review: periodically review every mainline commit
since the cursor recorded in `docs/audits/mainline-review-log.md`. File
actionable findings as new ledger tasks or `docs/OPEN_QUESTIONS.md` entries —
never as merge blocks — and append a log entry recording the reviewed range.

## Required verification

The current local front door is:

```bash
GODOT_BIN=/absolute/path/to/Godot ./scripts/check.sh
```

Run `scripts/doctor.sh` first when diagnosing a machine. It enforces the pinned
.NET SDK, uv, Git LFS, and official Godot versions. `scripts/check.sh` runs the
C# build and xUnit suite, Python lint and pytest suite, and a Godot headless
smoke. It always writes structured results and logs under `reports/m0/`.
`scripts/godot.sh` fails when the editor is absent, unofficial, or stale.

`scripts/check.sh` remains the local pre-push front door. Remotely, only the
Linux and Windows M0 checks gate merges; the remaining suites run as
post-merge tripwires (all except source retention watched by
`mainline-health.yml` per ADR-0025), and their mainline failure creates
immediate repair duty. They remain required for task
completion evidence on their declared platforms (ADR-0008 as narrowed by
ADR-0025), just not for merge.

Use the smallest relevant checks during development, then run the full required
gate before handoff:

```bash
dotnet build Cannonball.sln
DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --no-build
uv run --project tools/map_pipeline ruff check tools/map_pipeline
uv run --project tools/map_pipeline pytest
GODOT_BIN=/absolute/path/to/Godot ./scripts/check.sh
```

Godot runtime behavior is tested through C# unit tests and official-engine
headless scenarios. Do not use the retired custom Godot automation fork or
engine patches. A modern PlayGodot addon may provide stable semantic scene-node
automation for rendered UI under ADR-0005; it must remain debug-only, secure,
and compatible with the official engine. Use Computer Use for black-box
visual/editor validation that cannot be made deterministic through the CLI. An
MCP adapter is optional and must be accepted by ADR before it becomes a required
project dependency.

## Evidence and definition of done

A task is complete only when:

- its implementation and generated outputs are present;
- every declared acceptance criterion is exercised;
- required tests pass on all declared platforms;
- its evidence artifact exists at the ledger path;
- documentation and schemas match behavior;
- no required human gate remains open;
- the ledger status is updated to `complete`.

Evidence JSON must include at least:

- task ID, milestone, git revision, platform, and UTC time;
- exact tool versions and input artifact SHA-256 values;
- deterministic seed and scenario arguments where applicable;
- commands executed and their exit status;
- quantitative metrics and acceptance comparisons;
- output artifact paths and SHA-256 values;
- failure logs, retry count, and recovery result when applicable;
- human-gate approval reference, or `null` when no human gate exists.

Do not call a milestone complete from code review, compilation, a partial smoke,
or agent consensus alone.

## Geodata and provenance

- Shipping geodata must use a source listed in `data/sources/catalog.json`.
- Exact acquired artifacts require a checksum, acquisition timestamp, canonical
  URL or service identifier, response metadata, and recursive ancestry.
- Reject OpenStreetMap-derived ancestry from the shipping route pipeline.
- NHPN is a coarse topology and route-family backbone, not lane geometry.
- 3DEP supplies elevation only after product, resolution, date, horizontal
  datum, and vertical datum are locked.
- Never commit continental source downloads or generated route packages. Store
  them as cached, checksummed build or release artifacts.
- A GeoPackage is an audit artifact. FlatBuffer indices and chunks are runtime
  artifacts.

## Determinism and saves

- Use stable, named random streams. Do not use process-randomized hash values as
  seeds or stable identifiers.
- Build locked content twice and compare every shipping byte before claiming
  reproducibility.
- Content checksums must cover actual package bytes, not a version label alone.
- Save migrations are append-only. Never rewrite a released save version.
- Save/resume verification compares authoritative route and system state plus
  bounded local vehicle reconstruction.

## Runtime and performance

- Preserve local-origin rebasing; do not expand world-coordinate magnitude as a
  substitute for streaming discipline.
- Keep visual streaming and collision streaming independently budgeted.
- Never generate required road geometry synchronously without measuring and
  enforcing chunk-build latency.
- Long-route evidence must report frame-time percentiles, memory high-water and
  steady-state growth, chunk latency, rebases, maximum local coordinate, seam
  checks, collision misses, hash failures, and resume equivalence.

## Human approval boundaries

Agents may prepare builds, tests, telemetry, comparisons, and release
candidates. Humans approve:

- driving enjoyment and 30-minute handling sessions;
- physical wheel calibration and feel;
- player comprehension and accessibility usability;
- final source and asset rights review;
- signing, notarization, and store credentials;
- public release.

Never replace a required human gate with a simulated preference or an automated
proxy. Record the proxy as evidence and leave the gate open.

## Documentation hygiene

- Keep `README.md`, `docs/TECH_STACK.md`, ADRs, the open-question register, the
  delivery ledger, schemas, and behavior consistent.
- Link findings to task IDs and decisions instead of duplicating mutable status
  prose across files.
- Preserve historical ADRs and audit reports. Supersede them with new records.
- Use ISO dates and stable IDs (`ADR-NNNN`, `Q-NNN`, `P0-NNN`).
