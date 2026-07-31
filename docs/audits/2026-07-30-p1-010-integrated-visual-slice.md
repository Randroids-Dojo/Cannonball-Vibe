# P1-010 integrated visual-slice gate

- Date: 2026-07-30
- Task: P1-010
- Code revision: `8301b99d951276eb85a98d8691164e01e5c94a88`
- Platform: Windows 11 x64
- Engine: Godot `4.7.1.stable.mono.official.a13da4feb`
- Renderer capture: Compatibility/OpenGL 3.3, NVIDIA GeForce RTX 3080 Ti

## Outcome

The representative corridor now has one deterministic official-engine profile
that proves the existing Hero GT wrapper, production road-kit contract, and
balanced regional environment are resolved together while the vehicle is
moving. The gate runs in both Ubuntu and Windows M0 CI.

P1-010 remains `in_progress`. The three resolved identifiers describe the
current project-owned technical baselines; they do not mean that P1-008,
P1-009, or P1-010 has passed production-art, rights, human-readability, or
reference-performance approval.

## Same-frame contract

After at least 60 meters of route travel, at least 1 m/s of current vehicle
speed, and settled road and environment streaming, the scenario requires three
consecutive frames with:

- the non-graybox Hero GT wrapper, all 37 semantic nodes, and five damage
  zones;
- the production road profile, resolved chunks, reflectors, barriers,
  guardrails, 18 shared materials, nine shared meshes, and 11
  retroreflective materials; and
- the balanced regional environment with loaded and observed chunks,
  near/mid/distant instances, one terrain ribbon per loaded chunk, nonzero
  terrain geometry, zero environment collision budget, and ordered visibility
  bands.

The renderer-review mode holds the same contract for 120 consecutive frames.
Any prerequisite loss resets the consecutive-frame count. Any missing or
ambiguous completion marker fails the shell gate.

## Verification

`./scripts/verify-integrated-visual-slice.sh` passed at the code revision with:

```text
CANNONBALL_INTEGRATED_VISUAL_SLICE_OK vehicle=hero-gt vehicle_semantic_nodes=37 road=production road_chunks=11 road_materials=18 road_meshes=9 environment=balanced environment_regions=1 environment_chunks=11 terrain_ribbons=11 route_distance_m=60.468 vehicle_speed_mps=43.766 stable_frames=3
```

The complete local M0 gate also passed:

- pinned doctor: .NET SDK `10.0.102`, uv `0.9.24`, Git LFS `3.7.1`, Perl,
  and official Godot `4.7.1`;
- zero-warning solution build and 139 C# tests;
- Ruff and 79 map-pipeline tests;
- 13 PlayGodot unit tests; and
- official Godot smoke.

The Windows App Control policy rejected the map-pipeline `pytest` console
launcher during the first aggregate run. Invoking the same pinned module as
`python -m pytest` passed all 79 tests. Both Python suites now use that
cross-platform module invocation; no test, threshold, or dependency changed.

## Retained renderer capture

The committed review command was:

```text
./scripts/capture-scenario.sh /tmp/p1-010-integrated-visual-slice.avi --fixture representative-corridor --integrated-visual-slice-review
```

The official renderer recorded 480 frames at 1280x720 and 60 FPS. The
120-consecutive-frame completion marker reported 17 road chunks, two observed
environment regions, 17 environment chunks, 17 terrain ribbons, 384.186 meters
of route travel, and 91.039 m/s current vehicle speed. The local AVI is
26,145,924 bytes with SHA-256
`cd40d3ef71ba951e6115246222913b9279a27127f512e9f1d9cfc6929ed0527b`.

The AVI is retained locally rather than committed. No frame-by-frame human
visual inspection was performed in this pass, so this capture proves renderer
execution and contract coexistence only. Its Compatibility renderer,
1280x720 resolution, and short duration also do not satisfy Q-022's High
2560x1440 reference-performance protocol.

## Remaining boundary

The owner's prior choice to wait before Q-028 and Q-029 remains in force.
Current technical profile names are not substitutes for finished production
assets. Trip-map usability, camera comfort, final art direction, rights, and
reference-performance approval remain open and are summarized in
[the autonomous-pass handoff](../QUESTIONS_FOR_RANDROID_2026-07-30_AUTONOMOUS_PASS.md).
