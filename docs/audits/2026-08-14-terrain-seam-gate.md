# Terrain seam gate demands a precision float32 cannot deliver

Date: 2026-08-14

Task: P1-010 (in progress). Reported, not fixed: the seam specification is that
task's to set.

Status: superseded on 2026-08-14 by
[the float32-spacing gate](2026-08-14-terrain-seam-float32-gate.md). The owner
set the specification and the gate now asserts against float32 spacing.

The analysis below stands and its central claim is now demonstrated rather than
inferred: every seam pair is an exact integer multiple of the float32 spacing at
its own magnitude. One detail is corrected — the seam is up to five units in the
last place, not one, because both chunks pay five roundings independently.

## Symptom

`scripts/verify-environment-assets.sh` fails on `main`. It is listed in P1-010's
verification, so a declared gate is currently red.

The failure is silent: the script runs under `set -e` and asserts with
`grep -q`, so a failed match exits 1 with no message. The assertion is

```
echo "$marker" | grep -q 'max_terrain_seam_m=0.0000'
```

and the scenario reports `max_terrain_seam_m=0.0005`.

## This is not a regression, and not a geometry defect

The scenario itself passes. Its runtime contract fails only above 0.05 m
(`EnvironmentVisualScenario.cs:124`), and 0.0005 m is two orders inside that.
Only the shell assertion, which demands the formatted value be exactly zero,
disagrees.

The seam is measured between the terrain ribbon's end-edge vertices of one chunk
and the start-edge vertices of the next, as `Position + point` in world space.
Those are `Vector3`, which is float32.

| Distance from origin | float32 representable spacing |
| ---: | ---: |
| 2,000 m | 0.122 mm |
| 5,000 m | 0.488 mm |
| 10,000 m | 0.977 mm |
| 20,000 m | 1.953 mm |

The observed maximum seam is **0.500 mm**, against 0.488 mm at 5 km. The
representative corridor is 24,665 m long. Two chunks arriving at the same
boundary vertex through different `Position + point` decompositions can differ by
one float32 unit in the last place at that magnitude, and that is what the gate
is measuring.

So `max_terrain_seam_m=0.0000` is unachievable for any corridor extending more
than roughly two kilometres from the origin, whatever the geometry does. It was
presumably true when the assertion was written against a shorter span.

Confirmed pre-existing: the same 0.0005 m is reported at `e63abfd`, before the
elevation interpolation change, and with that change applied.

## What P1-010 has to decide

Either the shell gate should assert the contract the runtime already declares —
a seam ceiling rather than exact zero — or the seam should be measured in a frame
where float32 has the resolution to support an exact-zero claim, which is what
local-origin rebasing already exists to provide.

This audit does not choose. Relaxing `0.0000` to match an observed `0.0005` would
be moving acceptance to fit a result, which the P0-019 precedent explicitly
forbids; the case for changing it rests on the number being unreachable in
principle, and that is a specification judgement rather than a measurement.

## Also noted

`scripts/verify-road-assets.sh` cannot run on a machine without `ripgrep`. It
exits 1 with `rg: command not found` before checking anything, so a missing
optional tool presents as a gate failure. The underlying scenario passes; the
marker it looks for is emitted.
