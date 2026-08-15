# Godot resource wrappers leaking at engine shutdown

Date: 2026-08-14

Task: P1-010. Continues the fix begun in PR #66, which addressed the chunk
collision mesh; this covers the rest of the same pattern.

Status: fixed for every wrapper identified. Whether it ends the intermittent
Linux segfault is not demonstrated — see the limit below.

## Symptom

`scripts/check.sh` on Linux CI intermittently ends in a segmentation fault after
the smoke passes:

```
CANNONBALL_SMOKE_OK chunks=4 distance_m=57.6 ...
ERROR: Leaked unsafe reference to object: ():<Environment#-9223372008954264056>
   at: finalize (modules/mono/csharp_script.cpp:179)
...
scripts/run-scenario.sh: line 475: 3865 Segmentation fault (core dumped)
```

The failing run listed **78** leaked references across 11 types:

| Type | Count | Type | Count |
| --- | ---: | --- | ---: |
| ArrayMesh | 26 | StyleBoxFlat | 4 |
| StandardMaterial3D | 15 | CylinderMesh | 3 |
| BoxMesh | 10 | BoxShape3D | 2 |
| MultiMesh | 8 | World3D | 1 |
| SphereMesh | 7 | PlaneMesh | 1 |
| | | Environment | 1 |

## Cause

One cause for all of them. A Godot resource is `RefCounted`, and its C# wrapper
holds one of those references until the wrapper is disposed or finalised. A
wrapper built inline in a node initializer —

```csharp
AddChild(new MeshInstance3D { Mesh = BuildPlanarFaceMesh(...) });
```

— is unreachable the moment the initializer completes. Nothing disposes it, so it
waits for finalisation, which can run after the engine has torn down. That is
what the message reports, and the segfault follows from finalising a binding
whose engine-side object is already gone.

## Fix

- **`RoadChunk`, `JunctionSeam`** — 17 inline constructions go through `Owned()`,
  which records the wrapper for release in the predelete handler these types
  already have. One token per site, so a construction added later is wrapped the
  same way rather than needing its own disposal path.
- **`RegionalEnvironmentChunk`** — takes ownership of the terrain ribbon mesh
  handed to it by `RegionalTerrainRibbon.Build`, released at predelete.
- **`EnvironmentVisualKit`, `RoadVisualKit`** — plain C# objects holding about 41
  resources between them, which nothing frees when the tree tears down. Both are
  now `IDisposable` and discover their resources by reflection, so adding one to
  a kit cannot silently escape disposal. `WorldStreamer` disposes them at
  predelete.
- **Vehicle chassis, damage indicators, night environment** — scoped with `using`.

Predelete is used rather than `_ExitTree` because `_ExitTree` also fires on
reparenting, where releasing would strand a live node. This matches the choice
made in PR #66.

### What is deliberately not wrapped

Kit-owned materials referenced by chunks, for example
`MaterialOverride = _visualKit.Pavement`. Those wrappers belong to the kit.
Releasing one from a chunk would leave the kit holding a disposed wrapper and the
next chunk using it.

## Why this cannot affect rendering

Disposing a wrapper releases only that reference. The node it was assigned to
holds its own, so the underlying resource survives the call.

Confirmed rather than assumed: `verify-environment-assets.sh` passes on all four
quality profiles with unchanged terrain triangle counts (3656 / 1880 / 984 / 536)
and unchanged streaming semantics.

## The limit of the verification

`check.sh` passes and the environment gate passes, which establishes that nothing
broke. It does **not** establish that the intermittent segfault is gone.

The event rate is low: main's most recent Linux M0 run recorded zero leaks and
passed, and the branch build after this change also recorded zero. A single green
run is therefore not evidence either way.

What this change does establish, by inspection rather than by run, is that
wrappers of exactly the types the failing run named are now released
deterministically instead of at finalisation. The honest signal to watch is the
leak lines disappearing from Linux M0 logs over several runs, not one pass.

## Related deflake

`test_chase_camera_damps_vehicle_yaw_and_keeps_a_level_horizon` failed on Windows
CI during this work and passed on re-run. The failure state showed conditioned
throttle at 0.375 rising at 3.2/s after the full 7 second budget, meaning full
throttle had been held for about 0.12 s — the vehicle had barely started rather
than accelerating slowly.

One deadline covered two unrelated things: getting the throttle held through
focus transitions, which is input latency a loaded runner can stretch, and
accelerating to the probe speed, which is vehicle behaviour. The first could
consume the second, so the test asserted something about the runner. They are now
budgeted separately, with acceleration timed from when throttle engages. No
assertion changed — the speed threshold, heading-lag bounds and horizon check are
untouched.

## Noticed and not addressed

`scripts/verify-road-assets.sh` calls `rg`, which is not present in this
environment, so it fails locally with `rg: command not found`. It is not part of
the M0 gate. Recorded rather than fixed because it is a tooling dependency
question, not a defect in the assets it checks.
