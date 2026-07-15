# ADR-0001: Godot 4.6.3 .NET prototype stack

- Status: Superseded by [ADR-0004](ADR-0004-godot-4-7-1.md)
- Date: 2026-07-14
- Supersedes: GDD decision D-008

This record preserves the version that was validated during the initial M0
audit. It is historical and no longer defines the active engine pin.

## Context

The GDD originally recommended Unreal Engine while requiring the route graph,
run state, saves, and simulation rules to remain engine-independent. The M0
implementation and readiness audit validated Godot 4.6.3 .NET for the required
desktop prototype, headless testing, high-speed graybox driving, origin
rebasing, and portable C# contracts.

## Decision

Use Godot 4.6.3 .NET for the serious prototype with:

- C# 12 targeting .NET 8;
- Godot Jolt and a 120 Hz physics loop;
- Forward+ as the shipping renderer;
- `Cannonball.Core` as the engine-independent rules and data layer;
- a custom four-raycast `RigidBody3D` vehicle rather than engine-specific
  vehicle-wheel abstractions.

Keep route content, authoritative run state, deterministic streams, saves, and
telemetry portable. Reconsider the engine only if a measured prototype gate
cannot be met without engine-specific risk or unacceptable maintenance.

## Consequences

- Desktop C# builds and headless automation are first-class.
- Web export is outside the product target.
- Cross-platform Jolt physics is not assumed to be bit-identical; saves retain
  authoritative route state plus bounded local vehicle state.
- Runtime, export templates, and automation must use the exact Godot version.
- The older Unreal recommendation is historical, not current guidance.
