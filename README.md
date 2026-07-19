# Cannonball-Vibe

A coast-to-coast driving roguelite about finding the fastest pace the car, route,
and driver can still survive.

The repository now contains the M0/P0 technical slice: a Godot 4.7.1 .NET game,
an engine-independent C# rules layer, a custom raycast-suspension vehicle, a
verified sharded route runtime with local-origin rebasing, versioned saves,
JSONL telemetry, and a public-domain-only geodata pipeline. The checked-in
official NHPN/3DEP fixture is intentionally short; the continental route remains
a later milestone.

This is a prototype foundation, not the complete MVP described in
[gdd.md](gdd.md). Traffic, enforcement, stops, builds, and the continental
route remain later milestones.

## Run the prototype

Requirements:

- Godot 4.7.1 .NET
- .NET SDK 10.0.102 (the game targets .NET 8)
- `uv` 0.9.24 for the Python pipeline
- Git LFS 3.7.1
- Bash and Perl (included with Git for Windows) for the guarded CLI scripts

### Windows x64 setup

Run the repository commands from Git Bash. On a new Windows workstation, install
the pinned SDK, Python runner, and .NET-enabled Godot editor with WinGet:

```powershell
winget install --id Git.Git --exact
winget install --id Microsoft.DotNet.SDK.10 --exact --version 10.0.102
winget install --id astral-sh.uv --exact --version 0.9.24
winget install --id GodotEngine.GodotEngine.Mono --exact --version 4.7.1
```

Close and reopen Git Bash after installation so it receives the updated PATH,
then run `./scripts/doctor.sh`. The Godot front door also discovers WinGet's
per-user .NET editor when a non-administrator install cannot create the `godot`
command alias.

The main scene requires a built route package. Use the scenario front door,
which builds the locked official fixture before launching Godot:

```
./scripts/run-scenario.sh --fixture official-corridor --smoke-test
```

Controls: W/right trigger accelerates, S/left trigger brakes, A/D or the left
stick steers, R resets the vehicle, and F5 writes a suspend save.

## Verify everything

```
./scripts/doctor.sh
./scripts/check.sh
```

The doctor enforces the exact toolchain. The check runs the doctor, xUnit core
tests, Python lint and tests, and a headless Godot autopilot smoke on both Linux
and Windows CI. It writes JSON, TRX, JUnit XML, engine logs, and step logs under
`reports/m0/`; CI uploads that directory even when verification fails. Use
`GODOT_BIN=/path/to/godot ./scripts/check.sh` when the engine is installed
elsewhere.

Asset authors can run the separately pinned Blender 5.1.2 and Godot 4.7.1
pipeline with `./scripts/validate-assets.sh`; normal graybox development does
not require Blender. See [tools/assets/README.md](tools/assets/README.md).

Run a Godot-only scenario through the same exact-version CLI front door:

```
./scripts/run-scenario.sh --smoke-test
./scripts/run-scenario.sh --short-corridor-soak
./scripts/run-scenario.sh --fixture official-corridor --distance-miles 100
./scripts/run-scenario.sh --distance-miles 500 --platform current --evidence evidence/M1/P0-006.json
./scripts/run-scenario.sh --fixture official-corridor --resume-verify
./scripts/run-resume-fuzz.sh --cases 10000
```

The scenario command builds the locked route package and C# game assembly
before launching Godot, so it also works from a clean checkout. The 100-mile
command is explicitly a repeated transport verification of 0.226102 unique
fixture miles, not a claim that the short fixture is a representative long run.
Likewise, `--short-corridor-soak` is a high-speed packaged-fixture regression;
the 200 mph plus local-origin-rebase stress gate still requires a longer route.
`--resume-verify` loads the fixture's suspended run and checks route position,
stable lane, route plan, local origin, streamed chunk and collision sets,
vehicle transform and motion, elapsed time, systems, and package identity before
the scene advances. The seeded fuzz command performs exact repository
save/load comparisons at the requested number of deterministic save points.

Supplying `--evidence` selects the distance-complete long-route profile. It
derives a checksum-bound, explicitly authored automation corridor from the
locked representative source package and sweeps the requested distance in the
real Godot streamer. The default 500-mile contract uses seed `20260718`, save
points at 100, 250, and 400 miles, expected completion, and Accessible,
Balanced, and Raw assist profiles. Override those inputs with `--seed`,
`--save-points`, and `--expected-completion`. The generated corridor validates
runtime distance, seams, precision, streaming, collision, and reconstruction;
it is not presented as observed highway geography.

Capture a fixed-FPS visual artifact on a machine with a real graphics renderer:

```
./scripts/capture-scenario.sh /tmp/cannonball.avi --smoke-test
```

## Repository map

- `game/` — Godot presentation, vehicle physics, and sample-driven streamed world.
- `src/Cannonball.Core/` — route, run, save, seed, telemetry, and FlatBuffer code
  without Godot dependencies.
- `schemas/` — versioned runtime route-data contract.
- `tools/map_pipeline/` — deterministic GeoPackage-to-FlatBuffer build.
- `tools/assets/` — pinned Blender export, Godot import, provenance, budget, and release-pack gates.
- `data/assets/` and `assets/pipeline-fixtures/` — checksum-locked build inputs and replaceable runtime wrappers.
- `data/sources/catalog.json` — approved public-domain source catalog and policy.
- `docs/TECH_STACK.md` — stack decisions, boundaries, and milestone gates.

## Project records

- [Agent contract](AGENTS.md) — authority, workflow, verification, and human gates.
- [Delivery ledger](docs/DELIVERY_LEDGER.json) — machine-readable tasks,
  dependencies, acceptance criteria, and evidence paths.
- [Agentic-readiness audit](docs/audits/2026-07-14-agentic-readiness.md) — dated
  findings and prioritized delivery blockers.
- [Architecture decisions](docs/decisions/README.md) — append-only ADRs.
- [Agentic Godot automation research](docs/research/2026-07-14-godot-agentic-automation.md)
  — official CLI, C# tests, visual capture, Computer Use, and modern PlayGodot.
- [PlayGodot modernization plan](docs/research/2026-07-15-playgodot-modernization.md)
  — stable scene-node automation on the official engine without a fork.
- [Open questions](docs/OPEN_QUESTIONS.md) — unresolved choices and required
  evidence.
