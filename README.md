# Cannonball-Vibe

A coast-to-coast driving roguelite about finding the fastest pace the car, route,
and driver can still survive.

The repository now contains the M0/P0 technical slice: a Godot 4.7.1 .NET game,
an engine-independent C# rules layer, a custom raycast-suspension vehicle, a
streamed 25-mile graybox road with local-origin rebasing, versioned saves,
JSONL telemetry, and a public-domain-only geodata pipeline.

This is a prototype foundation, not the complete MVP described in
[gdd.md](gdd.md). Traffic, enforcement, stops, builds, and the continental
route remain later milestones.

## Run the prototype

Requirements:

- Godot 4.7.1 .NET
- .NET SDK 10.0.102 (the game targets .NET 8)
- `uv` 0.9.x for the Python pipeline
- Git LFS

Open `project.godot` in Godot Mono and run the main scene, or use:

```
./scripts/godot.sh --path .
```

Controls: W/right trigger accelerates, S/left trigger brakes, A/D or the left
stick steers, R resets the vehicle, and F5 writes a suspend save.

## Verify everything

```
./scripts/check.sh
```

The check runs xUnit core tests, Python pipeline tests, and a headless Godot
autopilot smoke test. Use `GODOT_BIN=/path/to/godot ./scripts/check.sh` when the
engine is installed elsewhere.

Run a Godot-only scenario through the same exact-version CLI front door:

```
./scripts/run-scenario.sh --smoke-test
./scripts/run-scenario.sh --smoke-test --stress-driver
```

The scenario command builds the C# game assembly before launching Godot, so it
also works from a clean checkout rather than relying on editor-generated state.

Capture a fixed-FPS visual artifact on a machine with a real graphics renderer:

```
./scripts/capture-scenario.sh /tmp/cannonball.avi --smoke-test
```

## Repository map

- `game/` — Godot presentation, vehicle physics, and streamed graybox world.
- `src/Cannonball.Core/` — route, run, save, seed, telemetry, and FlatBuffer code
  without Godot dependencies.
- `schemas/` — versioned runtime route-data contract.
- `tools/map_pipeline/` — deterministic GeoPackage-to-FlatBuffer build.
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
