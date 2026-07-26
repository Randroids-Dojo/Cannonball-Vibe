# P0-019 vehicle dynamics local verification

Date: 2026-07-23
Task: P0-019
Milestone: M0
Result: verified locally; completion remains dependency-blocked

## Scope and authority

This pass closes the machine-verifiable portion of P0-019 after the owner
reported a reproducible high-speed incline launch followed by a
hard-landing throttle rollover. It follows the P0-019 ledger acceptance,
the official-engine automation boundary in ADR-0005, and the existing
P0-010/P0-012 route and topology contracts.

P0-019 depends on P0-018. The ledger permits narrow work against the
machine-verified P0-018 foundation, but P0-018 remains in progress until
the P0-017 Q-029 human camera review is approved. P0-019 therefore advances
to `verified_local`, not `complete`.

## Implementation result

The vehicle remains a forgiving high-speed game model. The pass:

- lowers the rigid body's center of mass by 0.30 m;
- separates tilt damping from yaw damping so rollover resistance does not
  erase player yaw intent;
- caps lateral tire force at a declared 14 m/s² chassis acceleration while
  preserving profile-dependent response;
- applies bounded airborne downforce under the existing 1.1g ceiling;
- preserves raycast suspension, drag, braking, and contact-authority
  architecture;
- adds explicit suspension travel and near-bottom-out duration telemetry;
- isolates automation telemetry files so an open editor session cannot lock
  scenario output;
- moves the dynamics runner to the 120 Hz physics callback and adds stable
  result hashing plus 30/60/144 fixed-FPS comparison.

Accessible, Balanced, and Raw retain distinct steering, grip, upright,
damping, airborne, and partial-contact responses. No drivetrain, tire
thermal, damage reconstruction, or route-following steering model was added.

## Declared corpus

The aggregate official-engine corpus runs three profiles at:

- cruise: 31.000 m/s;
- push: 60.000 m/s;
- redline: 89.408 m/s (200 mph).

Eight fixtures cover straight running, braking, lane change, paved-road
departure and controlled re-entry, barrier impact, 15% crest and landing,
disturbed spin/recovery, and reset. Reset runs once per profile; the other
fixtures run at all three speed bands. A repeated Balanced/push lane change
brings the aggregate to 67 runs.

The speed, handling, incline, and recovery limits are constants in
`VehicleDynamicsProfile`. Suspension stroke is limited to the designed
0.620 m raycast travel. Near-bottom-out means at least one wheel is within
0.020 m of full compression; the extreme-landing duration limit is 36
physics frames, or 0.300 seconds at 120 Hz.

## Quantitative result

The final aggregate emitted result hash
`049bc1dcdd1bcedf209d7f8316bf42a73163b089bf81eeeb38940ad160c4c941`.

| Measure | Worst observed | Applicable limit | Result |
| --- | ---: | ---: | --- |
| Straight speed loss | 12.769 m/s | 13.000 m/s redline | pass |
| Braking distance | 119.314 m | 330.000 m redline | pass |
| Braking time | 2.875 s | 10.000 s redline | pass |
| Lane/departure roll | 6.138° | 24°/30°/35° by band | pass |
| Lane/departure yaw rate | 0.798 rad/s | 1.50/1.35/1.20 rad/s | pass |
| Lane/departure slip | 12.652° | 18°/16°/14° | pass |
| Lane/departure lateral acceleration | 16.358 m/s² | 16/17/18 m/s² | pass |
| Incline unsupported duration | 101 frames | 108 frames redline | pass |
| Incline chassis tilt | 5.767° | 55° | pass |
| Incline angular speed | 3.016 rad/s | 4 rad/s | pass |
| Suspension travel | 0.617 m | 0.620 m | pass |
| Near-bottom-out duration | 31 frames | 36 frames | pass |
| Departure final lateral error | 3.442 m | 3.500 m | pass |
| Departure sustained recovery | 1,035 frames | 1,200 frames | pass |
| Disturbed recovery | 452 frames | 480 frames | pass |
| Barrier unsupported duration | 0 frames | 24 frames | pass |

Barrier collision lateral acceleration is intentionally not compared to the
tire-handling acceleration band because it is an impulse. Barrier validation
instead requires contact without tunneling, shared tilt and angular-speed
safety limits, bounded loss of support, and supported final contact.

The same Accessible/push lane-change state hash
`5beb0f143aa599896c86765a4256329033cf3de4a47a498348cf361cdbee47e5`
was produced at engine fixed rates of 30, 60, and 144 FPS.

## Cross-system regressions

The refreshed 500-mile Windows scenario passed all three assist profiles:

- 455 of 455 chunks verified;
- 64 route transitions;
- 1,362 local-origin rebases;
- nine equivalent save/resume comparisons;
- zero missing chunks, hash failures, road gaps, collision misses, or save
  divergence;
- all three live handling segments retained support for all 180 physics
  frames.

The representative topology command also completed its live validations:

- variable-lane traversal reached 161.1 mph with 12 checkpoints, four lane
  transitions, a gore, six rebases, and at most one unsupported frame;
- four interchange plans traversed 14 legal connectors with 12
  save/resumes, no invalid shortcuts, and at most one unsupported frame;
- route-context semantic validation completed six review points;
- the nested full M0 gate passed.

The P0-012 evidence packager then exited 1 because its Windows Node process
resolves Git Bash `/tmp` paths as `C:\tmp` and requires archived P0-012 review
movies. This occurred after all live validation and M0 checks passed. No
P0-012 evidence or completion state was changed.

## Final verification

The following final commands passed:

- `./scripts/verify-vehicle-dynamics.sh --profiles all --speed-bands all --fixtures all`
- `DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --filter 'FullyQualifiedName~VehicleDynamics'`
- `./scripts/run-scenario.sh --distance-miles 500 --platform current --evidence .tools/evidence/p0-019-long-route-final.json`
- `./scripts/capture-scenario.sh /tmp/p0-019-vehicle-dynamics.avi --fixture representative-interchanges --vehicle-dynamics-review`
- `./scripts/check.sh`
- `bash -n scripts/run-scenario.sh scripts/capture-scenario.sh scripts/verify-vehicle-dynamics.sh`
- `git diff --check`

The final capture is 12,957,102 bytes with SHA-256
`e63acc4e9dc586fd4624fad31a2a4c00ca4fa700f97b0d538ed929ac4d50d3b4`.

M0 passed with .NET SDK 10.0.102, uv 0.9.24, Git LFS 3.7.1, official
Godot 4.7.1 .NET, 108 C# tests, 78 map-pipeline tests, 12 PlayGodot unit
tests, Ruff, and the official-engine smoke.

## Adversarial review

The complete diff was reviewed against the ledger rather than only the
reported incline failure. The review found and corrected:

- an initialization ordering bug that assigned rigid-body state while the
  body was frozen;
- duplicated acceptance values in the scenario;
- a result hash that omitted physical metrics;
- missing recovery-frame evidence;
- missing departure/re-entry and barrier fixtures;
- missing frame-rate comparison;
- shared telemetry file contention with an open Godot editor;
- missing suspension-travel evidence;
- a global 120-second watchdog that could terminate the expanded aggregate.

The suspension investigation also rejected a stiffer spring and higher peak
load as final changes: those variants did not materially reduce full-stroke
duration and the stiffer spring exceeded the existing redline airtime limit.
The original 42 kN/m spring and 6.5g load ceiling were retained.

No unresolved actionable code finding remains. The residual constraints are
external gates, not P0-019 implementation defects:

- Q-029 must close P0-017 before P0-018 and P0-019 can become complete.
- P0-020 separately owns the 30-minute keyboard and controller handling
  sessions and cannot be replaced by this automated corpus.
