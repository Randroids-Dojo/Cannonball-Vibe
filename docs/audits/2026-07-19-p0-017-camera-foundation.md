# P0-017 camera foundation review

Date: 2026-07-19

Status: automated acceptance verified locally; human comfort gate pending

## Outcome

The chase camera no longer inherits the vehicle rigid body's yaw, pitch, or roll.
It is a top-level world-space rig that follows vehicle position and damped horizontal
heading while retaining the collision-aware spring arm. Speed changes follow distance
and field of view conservatively, and teleports or vehicle resets snap the rig back to
a valid pose instead of dragging it across the world.

Follow distance, height, look-ahead, yaw damping, recenter delay, speed response, and
the low/high-speed field of view are now explicit Godot properties rather than hidden
constants. Semantic snapshots expose those settings plus target attachment, spring-arm
hit length, compression, target distance, heading lag, and horizon error.

The existing production cockpit anchor is now usable through `V` on keyboard or the
right-stick button on a controller. The graybox vehicle supplies a fallback cockpit
anchor so camera behavior does not depend on final vehicle art. The cockpit rig stays
vehicle-local while counteracting up to six degrees of chassis pitch/roll, supports
bounded IJKL/right-stick look, and recenters when look input returns to neutral. The
eye offset was raised from 0.28 m to 0.70 m after the renderer capture showed that the
old placement let the hood obscure roughly half of the road view.

## Adversarial findings

- A bounded full-steering probe produced approximately 10.6 degrees of chase-camera
  heading lag at 12.8 m/s while measured horizon roll stayed at 0 degrees. The vehicle
  remained visible and the road horizon remained level in the renderer capture.
- A deliberately excessive 1.5-second full-steering probe drove the current vehicle
  off the roadway. That is vehicle-handling and recovery work for P0-018/P0-019, not a
  reason to make the chase camera inherit chassis rotation again.
- Camera semantic state proves the chase node is top-level, collision mask 1 excludes
  the vehicle body, and cockpit/chase activation is mutually exclusive.
- The deterministic six-stage profile exercised a 9-degree grade/pitch plus 7-degree
  roll, 4.503 m of spring-arm compression, recovery to the configured follow distance,
  an actual vehicle reset, a local-origin rebase, an edge transition onto
  `directional-transfer-ramp`, and cockpit/chase transitions. Horizon error remained
  0 degrees and spring-arm movement stayed below the 0.25 m oscillation limit.
- The saved rebased state reconstructed on the same authoritative route edge with one
  rebase, a 1.985 m camera-to-target distance, and 0-degree horizon error.
- Adversarial review found three stale pre-refactor camera node paths in vehicle,
  topology, and route-context scenarios. Those consumers now use the public camera
  rigs, preventing false-negative captures and stale automation state.
- Clean-runner validation found and removed two hidden test-order/scheduler
  assumptions: the new camera test now consumes the official fixture guaranteed by
  the standalone PlayGodot job, and the steering/camera-independence test polls the
  semantic input state with a one-second bound instead of assuming every hosted
  macOS runner processes injected input within exactly 50 ms.
- A 1280x720, 362-frame official-engine renderer capture was visually inspected. Chase,
  collision-compressed, recovered, rebased ramp, cockpit, and chase-return frames had
  no detached geometry, starting-frame breakup, inversion, or zoom oscillation. The
  raised cockpit eye point leaves only a shallow hood strip while preserving the road
  horizon and HUD.

## Verification

- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/verify-camera-handling.sh --all-scenarios`
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/check.sh`
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/capture-scenario.sh /tmp/p0-017-camera-handling-eye-height.avi --fixture representative-corridor --camera-handling-review`

The focused camera gate passed six deterministic engine stages, save/resume camera
reconstruction, two live PlayGodot camera scenarios, and the normal-start security
boundary. The local M0 gate passed with 91 .NET tests, 78 map-pipeline tests, 12
PlayGodot unit tests, zero build warnings, and the official Godot 4.7.1 smoke. The
required human camera-comfort and readability gate remains pending; this document does
not self-approve it.

## Remaining P0-017 gate

- Record Q-029 after a sustained five-minute chase and five-minute cockpit comfort and
  readability review, then produce the final evidence JSON and mark P0-017 complete.
