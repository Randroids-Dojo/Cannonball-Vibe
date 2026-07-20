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

## Remaining boundary

P0-018 is intentionally `in_progress`. Its ledger scope permits implementation against
the verified P0-017 foundation but prohibits a completion claim until the P0-017 human
camera-comfort gate is approved. Physical wheels, pedals, and force feedback remain out
of this baseline.
