# P0-017 camera foundation review

Date: 2026-07-19

Status: implementation slice verified locally; P0-017 remains in progress

## Outcome

The chase camera no longer inherits the vehicle rigid body's yaw, pitch, or roll.
It is a top-level world-space rig that follows vehicle position and damped horizontal
heading while retaining the collision-aware spring arm. Speed changes follow distance
and field of view conservatively, and teleports or vehicle resets snap the rig back to
a valid pose instead of dragging it across the world.

The existing production cockpit anchor is now usable through `V` on keyboard or the
right-stick button on a controller. The graybox vehicle supplies a fallback cockpit
anchor so camera behavior does not depend on final vehicle art.

## Adversarial findings

- A bounded full-steering probe produced approximately 10.6 degrees of chase-camera
  heading lag at 12.8 m/s while measured horizon roll stayed at 0 degrees. The vehicle
  remained visible and the road horizon remained level in the renderer capture.
- A deliberately excessive 1.5-second full-steering probe drove the current vehicle
  off the roadway. That is vehicle-handling and recovery work for P0-018/P0-019, not a
  reason to make the chase camera inherit chassis rotation again.
- Camera semantic state proves the chase node is top-level, collision mask 1 excludes
  the vehicle body, and cockpit/chase activation is mutually exclusive.

## Verification

- `dotnet build Cannonball.sln --no-restore -v:minimal`
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/verify-camera-handling.sh --all-scenarios`
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/check.sh`
- `CANNONBALL_CAPTURE_FRAMES=180 CANNONBALL_CAPTURE_FPS=60 ./scripts/capture-scenario.sh /tmp/p0-017-chase-camera.avi --fixture representative-corridor --smoke-test`

The local M0 gate passed with 75 .NET tests, 78 map-pipeline tests, 12 PlayGodot unit
tests, and the official Godot 4.7.1 smoke. The required human camera-comfort and
readability gate remains pending; this document does not self-approve it.

## Remaining P0-017 work

- Add deterministic reset, collision, grade, local-origin rebase, and save-resume
  camera scenarios.
- Add explicit camera occlusion and spring-arm oscillation measurements.
- Run the sustained human cockpit/chase comfort and readability review.
