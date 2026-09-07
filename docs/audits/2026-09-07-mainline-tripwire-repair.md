# P0-024: mainline runtime tripwire repair

Date: 2026-09-07

Task: P0-024. Claim: PR #141. Trigger: red-main #140 after P1-017 merged
in PR #138 (`36035a5`), persisting at `01dd47d`.

## Retained failures

- Main CI run `34075477248`: macOS
  `test_pause_clears_held_input_until_neutral` failed with suppression sequence 2,
  last reason `pause`, neutral raw input, suppression false and stationary hold
  false. The vehicle was still moving at 0.593 m/s. The menu was paused.
- Main unsigned exports run `34075477269`: Linux exited with SIGSEGV before
  readiness; Windows printed all smoke success markers, then crashed in
  `GodotObject.Finalize` / `godotsharp_internal_object_get_associated_gchandle`.
- Claim-only revision `ca45d99`, unsigned exports run `34168681979`: Linux passed;
  Windows reproduced the same native finalizer stack after all success markers.
  Its console wrapper reported exit zero, but the package verifier correctly
  rejected the accompanying engine error output.

Original workflow logs, macOS test artifacts and the checksummed Linux package
are retained under `reports/p0-024/upstream/`. The Linux archive SHA-256 is
`1b47cb54b7c844095969ab172e28711ad661d32f70469d9a31b030f25d4f3342`.
An attempted Linux gdb reproduction in an amd64 container on the local arm64 Mac
could not start the inferior because emulated ptrace register access failed.
That attempt is diagnostic failure evidence, not a runtime result.

## Changes

`DrivingInputController.Read` can continue while paused because its subtree uses
`ProcessMode.Always`. Previously any neutral sample cleared suppression, even
while the menu remained open. Neutral input now clears suppression only after
the simulation resumes. The rendered regression checks neutral input while
paused, a fresh press in the pause menu, resume with that key held, and the final
release. Each stage requires zero conditioned throttle and suppression until
resume plus neutral input.

The starter governor introduces a `PhysicsDirectBodyState3D` managed wrapper.
The official pinned engine owns its native state in `JoltBody3D`, which deletes
it with the body. The vehicle now retains that wrapper and disposes its managed
binding on `NotificationPredelete`, before the native body is destroyed. This
follows the repository's existing explicit wrapper-lifetime practice; no
per-frame wrapper allocation or physics change is introduced. The speed probe
now checks that each destroyed vehicle has no remaining native state binding,
collects pending finalizers between cases, and scopes its road-shape wrapper.

The package verifier now checks error markers without case sensitivity. The
claim-only Windows failure showed a native `Fatal error` followed by a zero
launcher status. Before this change, only separate `ERROR:` lines made that
particular run fail. Three executable fixture tests cover a clean shutdown, a
fatal stack after success markers with exit zero, and a nonzero exit after
success markers. `scripts/check.sh` runs them as `release-smoke-unit`.

Pinned engine source inspected:

- [JoltBody3D ownership and destruction](https://github.com/godotengine/godot/blob/4.7.1-stable/modules/jolt_physics/objects/jolt_body_3d.cpp)
- [Managed object binding disposal](https://github.com/godotengine/godot/blob/4.7.1-stable/modules/mono/glue/runtime_interop.cpp)

The finalizer stack establishes the failure class, but does not identify the
particular managed object. Cross-platform export results are required before
attributing recovery to the lifetime correction. The early Linux startup crash
has not yet been reproduced locally and is not assumed to share that cause.

## Verification

In progress; exact revisions, commands, artifacts and platform results belong in
`evidence/M0/P0-024.json`. No human gate applies to this bounded repair. The
starter cap remains 125 mph and the high-speed scenario setup remains 250 mph.
