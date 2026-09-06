# P0-022: Preserve startup evidence and prepare the semantic renderer

Date: 2026-09-06. Related: red-main #126, Q-042, ADR-0025.

The Linux job in mainline CI run 33910478508 timed out awaiting
`PLAYGODOT_READY` at the existing 20-second startup deadline. It failed before
connecting the test client, so it is not evidence of a failed camera assertion.

The uploaded `camera-handling-godot.log` misleadingly contains a successful
startup and the transcript contains a successful session. Inspection found that
`test_chase_camera_damps_vehicle_yaw_and_keeps_a_level_horizon` runs later and
writes the same log and transcript as the failed camera-handling test. It erased
the failure evidence. The later test now has separate `chase-camera-damping`
artifacts, and startup timeout exceptions include the last 20 process-output
lines in the test failure itself. A stalled-output unit test exercises the
deadline, retained diagnostics, and cleanup path.

Cold renderer initialization is now an explicit preparation step. The existing
headless import cannot prepare the graphics driver's pipelines; the preparation
launches the same Compatibility renderer and graybox bootstrap used by the
semantic suite, verifies an active camera, and waits for a real screenshot. It
has a separate bounded 180-second total deadline (120 seconds each for process
startup and an individual request), fails the script on error, and retains its
own logs, timing summary and screenshot. The interactive tests keep their
existing 20-second startup, request, camera and input bounds. The implementation
does not change the shipping Forward+ renderer or production art.

Godot documents that headless shader baking cannot use the GPU and that the
Compatibility renderer requires rendering the relevant content to prepare its
shaders: [pipeline compilation guidance](https://docs.godotengine.org/en/stable/tutorials/performance/pipeline_compilations.html).

The overwritten log prevents a definitive retrospective attribution of the
original 20-second delay. The claim-only commit also passed the Linux semantic
suite in PR run 34064437533, before these changes, so a green rerun alone would
not establish a causal fix. This audit records that limitation. P0-022 remains
in progress until the original startup class is sufficiently attributed; the
new instrumentation prevents another occurrence from losing its evidence.

Local verification on the M4 Max, official Godot
`4.7.1.stable.mono.official.a13da4feb`, .NET SDK 10.0.102:

- `scripts/check.sh`: passed, with structured results under `reports/m0/`.
- `scripts/verify-playgodot.sh`: 28 tests passed; explicit renderer preparation
  completed in 2.911 seconds. This preparation overlapped some CPU-only checks,
  so its timing is diagnostic, not a reference performance result.
- All authentication, capability, package-boundary and gameplay assertions
  remain exercised. No timeout was hidden by a retry or waived assertion.

See `evidence/M0/P0-022.json` for local hashes and subsequent remote checks.
