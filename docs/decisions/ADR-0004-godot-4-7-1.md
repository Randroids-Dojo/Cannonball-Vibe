# ADR-0004: Upgrade the prototype to Godot 4.7.1 .NET

- Status: Accepted
- Date: 2026-07-14
- Supersedes: [ADR-0001](ADR-0001-godot-dotnet-prototype-stack.md)

## Context

Godot 4.7.1 stable and `Godot.NET.Sdk` 4.7.1 became available on 2026-07-14.
The project is still at M0, so upgrading before content and scene complexity
grow is cheaper than carrying an older feature branch. Godot's 4.6-to-4.7
migration guide describes the migration as relatively safe for most projects.

The documented Jolt behavior changes affect world-boundary shapes and soft
bodies. Cannonball-Vibe's current custom raycast vehicle uses neither. The
project still re-runs handling and continuity evidence because physics behavior
is validated empirically rather than assumed from API compatibility.

## Decision

- Pin the editor, .NET SDK package, CI, export templates, local wrapper, and
  active documentation to Godot 4.7.1 .NET.
- Require `scripts/godot.sh` to reject absent or mismatched editor versions.
- Preserve the 4.6.3 audit and ADR as historical evidence rather than rewriting
  the version that actually produced those results.
- Rebaseline build, smoke, stress, and handling telemetry on 4.7.1.

## Consequences

- Contributors and agents use the exact official 4.7.1 .NET editor.
- Active CI must install 4.7.1 and, when exports are added, its exact templates.
- A future engine upgrade requires a new superseding ADR and migration evidence.

## Sources

- [Godot 4.7.1 maintenance release](https://godotengine.org/article/maintenance-release-godot-4-7-1/)
- [Godot 4.6 to 4.7 migration guide](https://docs.godotengine.org/en/4.7/tutorials/migrating/upgrading_to_godot_4.7.html)
- [Godot.NET.Sdk package](https://www.nuget.org/packages/Godot.NET.Sdk/)
