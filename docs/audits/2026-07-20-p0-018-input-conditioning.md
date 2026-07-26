# P0-018 input-conditioning implementation review

Date: 2026-07-20

Status: implementation slice verified; completion remains blocked by P0-017

## Outcome

Keyboard and controller input now pass through one deterministic, engine-independent
conditioner before reaching vehicle physics. Keyboard steering ramps toward lock,
returns to center, and reverses direction at bounded rates. Controller steering uses
per-profile deadzones, response curves, and rate limits. All profiles reduce steering
authority progressively above highway speed without touching either camera transform.

Throttle, service brake, reverse, and handbrake are separate channels. Service brake or
handbrake wins over contradictory propulsion, and neutral values snap exactly to zero.
A grounded stationary hold cancels grade force and velocity drift until throttle or
reverse expresses clear intent.

## Declared profile bands

| Profile | Keyboard rise | Controller deadzone | Controller curve | Redline authority |
| --- | ---: | ---: | ---: | ---: |
| Accessible | 2.4/s | 0.16 | 1.60 | 0.26 |
| Balanced | 3.2/s | 0.12 | 1.35 | 0.31 |
| Raw | 5.5/s | 0.08 | 1.00 | 0.40 |

The selected `AssistProfile` already participates in the versioned run-save contract;
the conditioner derives its immutable tuning from that restored profile.

## Input-state safety

- Pause and application focus loss clear conditioned input and require all physical
  channels to return to neutral before accepting new commands.
- Controller disconnect clears a controller-owned state through Godot's official
  `JoyConnectionChanged` signal.
- Reset clears input, reconstructs a neutral state, and snaps the independent chase
  camera to the restored vehicle pose.
- Debug-only PlayGodot joypad motion/button injection uses official `InputEvent` paths,
  remains behind the authenticated input capability, and releases injected state when
  the session closes.

## Automated coverage

- Engine-independent tests cover all three profiles, ramping, direction changes,
  deadzones, curves, high-speed authority, contradictory channels, stationary hold,
  and context clearing.
- Official-engine tests cover keyboard steering and reversal, distinct reverse and
  handbrake channels, controller axes, pause clearing, route-start hold, semantic input
  telemetry, camera independence, and a renderer capture.

## Adversarial findings resolved

- Conditioned propulsion initially decayed for several frames after brake engagement;
  braking now clears throttle and reverse in the same physics frame.
- Floating-point decay could leave a neutral channel near `1e-17`; every channel now
  canonicalizes sufficiently small neutral results to exact zero.
- The first profile draft gave Raw less redline authority than Accessible; the final
  ordering is Accessible 0.26, Balanced 0.31, Raw 0.40.
- Moving player speed sensitivity into the conditioner initially removed the
  autopilot's existing physical steering scale; autopilot now retains that scale while
  player input uses the semantic conditioner.
- Profile tuning records are cached immutable instances rather than physics-frame
  allocations.
- Live assertions initially assumed a fixed number of physics frames would elapse in a
  wall-clock sleep. Hosted macOS and Windows runners legitimately sampled different
  points on the same ramp. The live gate now asserts bounded monotonic integration and
  the exact semantic tuning values, while deterministic per-frame behavior remains in
  the engine-independent suite.
- The Windows ANGLE runner twice connected successfully but exceeded the default
  request timeout before servicing the first gameplay input. The live gate now uses a
  bounded 30-second request window and proves the semantic input controller is
  responsive before injecting input; the client default remains 10 seconds.
- Review hardening made the controller rate authoritative, prevents sub-deadzone
  analog noise from retaining device priority, scopes disconnect cleanup to the
  active physical controller, accepts bounded whole-number JSON device IDs, and
  makes the verification entry point honor narrower device/profile scopes.

## Remaining boundary

At the time of the initial audit, P0-018 was intentionally `in_progress`. Its ledger
scope permits implementation against the verified P0-017 foundation but prohibits a
completion claim until the P0-017 human camera-comfort gate is approved. Physical
wheels, pedals, and force feedback remain out of this baseline.

## 2026-07-23 Windows closeout addendum

The full keyboard-and-controller verification entry point was rerun on the pinned
Windows toolchain while a separate Godot editor process remained open. All 16
engine-independent `DrivingInput` tests, the normal-start package boundary, Ruff, and
all four selected official-engine PlayGodot scenarios passed. The live scenarios
covered keyboard steering and reversal, controller axes, pause clearing, stationary
hold, distinct reverse and handbrake channels, semantic input state, and renderer
inspection.

The retained [renderer capture](../images/p0-018-driving-input-review.png) shows the
Balanced profile in a released neutral state, with the chase camera still independent
of the input controller. Per-process runtime and telemetry isolation supplied by the
verified P0-017 automation foundation allowed this gate to coexist with the open editor
without reusing its telemetry stream.

This is a machine-verification closeout only. P0-018 may advance to `verified_local`,
but it cannot become `complete` until P0-017 is complete following the Q-029 human
camera-comfort and readability decision.

## 2026-07-25 bounded Steam Controller correction

Live owner testing found that the intended Xbox-style labels were not sufficient:
runtime-created joypad events were bound to device 0, so a Steam/XInput controller
enumerated under another Godot device ID could select controller state without driving
the mapped actions. Every controller binding now accepts any connected device. RT and
LT remain independent positive-polarity axes, profile deadzones apply to both triggers,
left-stick Y is unused while driving, and the project ignores joypad input while its
window is unfocused.

The bounded controller layout is RT accelerate, LT service brake, left-stick X steer,
B reverse, X handbrake, Y recover in place, R3 camera mode, hold LB rear view, View map,
and Menu pause. Driver-menu navigation uses D-pad/left stick, A confirm, and B back.
Steam Controllers must use Steam Input's Gamepad template; a WASD-emulation template is
indistinguishable from keyboard input and will intentionally make stick-up look like W.
Q-030 records the non-blocking subjective mapping retest rather than extending M0 polish.

Recover and Restart Run are now separate. Recover preserves route progress, the run
clock, and camera mode. Restart Run is a twice-confirmed driver-menu action that rebuilds
the initial world and restores route distance zero, the original pose, zero transition
motion, deterministic seed, starting economy/condition/enforcement, assist profile,
timer origin, and chase camera. It does not write or delete the suspend save. Semantic
evidence records both the transition-exact state and the subsequently settling rigid
body, avoiding a false requirement that suspension settling remain numerically frozen.

Both camera modes now support predictable hold-to-look-behind on B/LB. Reverse never
forces a camera change. The rear-view blend preserves free-look state and camera mode,
survives a chase/cockpit switch while held, and returns promptly on release. The cockpit
sightline defect was a double offset from adding a runtime eye displacement beneath an
already-authored `Camera_Cockpit` anchor. The runtime now uses the anchor directly with a
0.05 m near plane. The placeholder exterior cabin, roof spine, and solid interior block
use a cockpit-excluded render layer; the chase camera still renders them.

The retained [cockpit review capture](../images/p0-018-cockpit-controller-review.png)
is 1280x720 and shows an unobstructed road/windshield sightline with one shallow hood
strip and no stacked roof/interior layer. Semantic assertions independently prove three
cockpit-only excluded meshes, a zero local eye offset, and a chase cull mask that still
includes the exterior layer. Left, right, rear, reverse-plus-rear, release, and camera
switch behavior passed from the corrected anchor.

Final Windows verification on the pinned toolchain passed:

- `./scripts/verify-driving-input.sh --devices keyboard,controller --profiles all`:
  22 focused Core cases and six official-engine live scenarios passed.
- `./scripts/verify-camera-handling.sh --all-scenarios`: six deterministic camera
  stages, exact save/resume reconstruction, the normal-start boundary, and both live
  camera tests passed.
- `./scripts/check.sh`: doctor, zero-warning build, 115 C# tests, Ruff, 78 map tests,
  13 PlayGodot unit tests, and the official Godot smoke passed.

The first doctor attempt used WSL Bash and could not see the Windows toolchain; the Git
for Windows retry found every pinned tool except the workstation's upgraded uv. The
final runs prepended the already-cached pinned uv 0.9.24 executable, after which doctor
and every gate passed. Two expected test-development retries tightened device-agnostic
bindings and distinguished transition-exact restart motion from normal suspension
settling. During final handoff verification, three runs reached
`CANNONBALL_SMOKE_OK` and then crashed in Godot's managed finalizer after native engine
teardown. The logs identified existing undisposed `SurfaceTool` builders and the Hero
GT `PackedScene` wrapper. The construction sites now use deterministic `using`
ownership; no mesh, content, or camera behavior changed. A fresh complete gate then
passed cleanly, including process shutdown. No severe controller or camera blocker
remains in machine evidence. P0-018 is again `verified_local`, not `complete`: Q-029
remains an upstream human comfort gate.

The final adversarial diff review also found that a resumed session's diagnostic start
transform had been sampled from the resumed vehicle even though Restart Run rebuilt the
authored route start. The reference now always derives from `InitialRoadForward` and
`InitialVehiclePoint`; the final M0 and save/resume camera gates passed after that fix.

## 2026-07-25 final LT brake-to-reverse schema

The last owner-requested controller refinement makes LT a continuous brake-to-reverse
axis. While forward speed is above 0.35 m/s, shaped LT input is service braking and
cannot command reverse. If LT remains held at or below 0.35 m/s, service brake ramps
down while reverse ramps up through the existing profile rates. Once engaged, reverse
stays latched through small signed-speed noise; an independent 0.75 m/s forward exit
threshold returns LT to braking if the vehicle is pushed forward. Releasing LT clears
the latch and ramps reverse out. B remains a secondary direct-reverse binding and is
not required for normal controller driving.

The semantic state publishes both thresholds and the latch. Focused Core tests cover
the forward-braking phase, exact handoff, overlapping ramp, negative-speed reverse,
near-zero hysteresis, release, and B fallback. The official-engine Steam/XInput probe
uses the actual trigger axis: it first establishes speed above 4 m/s, observes braking,
continues holding LT through zero into negative speed without B, observes brake decay
and reverse rise, then verifies the B fallback separately. The first two live-test
attempts sampled inside the handoff band and then expected the decaying brake to be
instantly zero; the corrected test uses measured speed and asserts the intended smooth
overlap rather than an abrupt channel flip.

The mapping remains RT accelerate, LT brake-to-reverse, left-stick X steer, R3 camera,
hold LB look-behind, Y recover, View map, and Menu pause with A/B menu confirmation and
back. The existing cockpit culling and rear-view evidence remains valid. Its vehicle
body and interior are accepted as a graybox placeholder for this bounded tranche only;
the clear sightline is verified, while production cockpit art remains deferred.
