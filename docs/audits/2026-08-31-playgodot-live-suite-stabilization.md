# PlayGodot live-suite stabilization (Q-035 escalation)

- Date: 2026-08-31
- Scope: `automation/playgodot/tests/` (live suite and harness),
  `addons/playgodot/server.gd`, `game/Vehicle/CannonballVehicle.cs`,
  `game/Vehicle/DrivingInputController.cs`.
- Trigger: Q-035 working default — a fourth distinct live-suite test flaked in
  ~5 days of continuous-mainline operation (red-main #100), escalating the
  suite-wide stabilization question to a repair task.
- Method: CI runners cannot be reproduced locally, so each flake was
  root-caused from the recorded failure values, the attempt-1 CI logs of runs
  [33359788588](https://github.com/Randroids-Dojo/Cannonball-Vibe/actions/runs/33359788588)
  and
  [33378313324](https://github.com/Randroids-Dojo/Cannonball-Vibe/actions/runs/33378313324),
  and the test/bridge/game code — then confirmed by local experiment where
  possible.

## Recorded flake classes and root causes

### 1. `test_trip_map_resume_preserves_vehicle_vertical_stability` (macOS, twice)

Recorded: 2.077 m vs 2.0 m rise bound (run 33113740025); 5.473 m/s vs 5.0 m/s
upward-velocity bound (run 33120558335). Both passed unchanged on re-run.

**Root cause — a real game bug, not a tight threshold.** `Main` runs in
`ProcessMode.Always`, so `CannonballVehicle` (inheriting it) keeps executing
`_PhysicsProcess` while `GetTree().Paused` is set by the trip map or the driver
menu. A paused tree deactivates the physics server, so the space never steps —
but the vehicle kept calling `ApplyForce`/`ApplyTorque`/`ApplyCentralForce`
every physics tick. Applied forces are only cleared when the space steps, so
they accumulated for the entire pause and integrated as one large impulse on
resume. The impulse scales with pause length; the test's pause length is wall
clock (a 0.25 s sleep plus request latencies), so a loaded runner pushed the
resume pop past the bounds. Local confirmation on macOS: extending the paused
interval to 2.0 s produced a resume transient of **3.11 m rise / 11.37 m/s
upward velocity** on the unfixed build.

**Fix (game):** `CannonballVehicle._PhysicsProcess` returns after input
conditioning when the tree is paused — no forces, resets, or visual-rig state
while the space cannot step. Input conditioning still runs so pause
suppression can observe neutral input. With the fix, the same 2.0 s pause
measures **0.075 m rise / 0.52 m/s upward velocity** (was 3.11 m / 11.37 m/s).
This also fixes the untested equivalent after long driver-menu pauses, where
the accumulated impulse grew without bound.

**Fix (test):** the post-resume watch no longer samples a fixed 1.0 s
wall-clock window (which folded a runner-dependent stretch of terrain into the
transient bounds). It samples until the transient has deterministically
settled: the vehicle has demonstrably moved since the pause and two
consecutive grounded samples agree on vertical velocity within 0.25 m/s, under
a generous 8 s deadline that fails with the last sample attached. A resume
impulse defers settling until it has been captured, so the guard is not
weakened. The trip-map toggle is also now held until the map is observed open
before release (the toggle is polled, so releasing on a timer could drop it).

### 2. `test_controller_deadzone_curve_and_independent_axes` (windows, red-main #93)

Recorded: `assert braking["brake_trigger_reverse_engaged"] is False` failed
with `True`.

**Root cause:** the test accelerated to just past 4 m/s, applied full trigger
brake, slept 80 ms of wall clock, and sampled once. Full brake takes the
vehicle from ~4 m/s through the 0.35 m/s brake-to-reverse enter threshold in a
few hundred milliseconds of simulated time; on the loaded ANGLE-rendered
Windows runner the sleep plus describe round-trips spanned enough simulated
time that the single sample landed after the handoff had legitimately engaged.

**Fix:** the probe accelerates to 6 m/s (a scenario parameter widening the
deceleration runway several-fold; no assertion bound changed), then polls for
the first sample with the brake conditioned instead of sleeping. That sample
must land in the pre-handoff phase, which is asserted explicitly with a
diagnostic message (`forward_speed_mps > brake_to_reverse_exit_speed_mps`) so
a sampling failure reads as one. Every other fixed-sleep-then-assert in the
test became a bounded wait on the observable transition (keyboard throttle,
controller device tagging, curved steering, reverse handoff, settled reverse,
secondary reverse, handbrake), each failing with the last observed state.

### 3. `test_pause_clears_held_input_until_neutral` (macOS, red-main #93)

Recorded: `assert paused["stationary_hold"] is True` failed with `False` after
the suppression wait had already observed `suppression_sequence` advance with
reason `pause`.

**Root cause:** `DrivingInputController.ClearAndSuppress` published the
conditioner's default-initialized state (hold `false`) together with the
advanced suppression sequence; the coherent suppressed-empty state (hold
`true`) was only republished by the next `Read()` — one physics tick later. A
paused frame can carry zero physics ticks, so a describe could land inside the
window and satisfy the wait's predicate on the incoherent intermediate state.

**Fix (game):** `ClearAndSuppress` now publishes the same suppressed-empty
state a suppressed `Read()` produces, in one step — the suppression
transition is atomic to observers. **Fix (test):** the wait's predicate also
requires `stationary_hold` to be true, so the test waits for the complete
suppressed steady state rather than asserting an incidental field of whichever
sample first satisfied a partial predicate.

### 4. `test_hostile_requests_fail_closed_and_are_transcribed` (windows, red-main #100)

Recorded: `TypeError: 'NoneType' object is not subscriptable` at the
`wrong_token` raw request (test_live.py:820, run 33378313324 attempt 1).

**Root cause:** not a transcript write race — the attempt-1 log shows
`_raw_request` returned `None` because the bridge closed the connection
without any response. `server.gd::_accept_connection` runs before
`_poll_connection` each frame and judged the previous peer by its stale
status: a client that closed its socket and immediately reconnected (every
`_raw_request` in sequence does this) could be accepted and dropped while the
dead previous peer still reported `STATUS_CONNECTED`. `_raw_request` treated
the resulting empty read as a final answer and returned `None`.

**Fix (bridge):** `_accept_connection` polls the existing peer before judging
it, so a closed previous connection is observed at accept time. The
single-connection policy, auth cooldown, and capability model are unchanged.
**Fix (test):** `_raw_request` treats an empty read / reset / refused
connection as the connection-turnover transient it is and retries within a
bounded 5 s deadline, failing with diagnostics when exhausted. Refused
candidates carry no application data, so a retry cannot double-apply a
request. The oversized-request probe alone passes `allow_empty=True`, because
"closed without a response" is a legitimate outcome for it.

## New failure class found during verification

The stabilization pass itself exposed a fifth race: actions that are
edge-detected by **physics-phase polling** (the camera toggle in
`CannonballVehicle.UpdateCameraInput`) lose a press that lands before any
physics tick has observed the preceding release. One of the first local
verification runs failed exactly there. Toggles polled in the idle phase
(trip map, driver menu) cannot lose the edge because the bridge services
requests before `Main._Process` in the same frame. The round-trip test now
holds the toggle until its effect is observed before releasing, and paces
50 ms between the release and the next press so at least one 120 Hz tick
observes the released state on any runner.

## Suite-wide audit

Every live test was audited for the three anti-patterns (raw sleeps before
positive assertions, unsettled physics sampling, read-after-write races):

- `test_official_engine_semantic_round_trip`: camera toggles converted to
  hold-until-observed; trip-map toggle held until the visibility signal.
- `test_camera_handling_survives_pause_device_reset_and_mode_transitions`:
  the four sleep-then-assert camera-mode/menu transitions now use the
  existing `_settle` helper; blends already used it.
- `test_controller_camera_recover_menu_and_confirmed_restart_are_distinct`:
  cockpit activation, run progress (was a fixed 1.0 s wall-clock drive, now
  drives until `route_distance_m > 0.5`), menu open, focus navigation, and
  restart arming all wait on their observable transitions.
- `test_keyboard_steering_is_progressive_and_camera_independent`: reverse,
  handbrake, and assist-profile cycles wait on the conditioner transition.
- `test_stationary_hold_prevents_uncommanded_route_start_rollback`: the fixed
  0.8 s startup sleep became a settle wait whose conditions are the
  assertions themselves, with an 8 s diagnostic deadline.
- `test_hostile_requests_fail_closed_and_are_transcribed`: the post-cleanup
  action-release check waits on the fixture text instead of a 0.25 s sleep.
- Negative assertions after short sleeps (deadzone/wrong-polarity "nothing
  happens" checks) were left as-is: a late event cannot fail them spuriously,
  so they are not flake sources; making them delivery-proven is guard-strength
  work, not stabilization.
- Transcript end-of-test reads are not racy: the bridge opens, appends, and
  closes the transcript per record, and the suite reads it only after the
  process has exited.
- A shared `wait_for_describe` helper joined `wait_for_conditioner` in
  `tests/input_support.py`; all bounded waits fail with the last observed
  state attached.

## Threshold decisions

**No assertion threshold moved.** The 2.0 m / 5.0 m/s vertical-stability
bounds stay: the recorded exceedances (3.8%, 9.5%) were the accumulated-force
bug, and the fixed build passes the same bounds with ~27x / ~10x margin under
a pause four times longer than the test's. The deadzone test's probe speed
(4 -> 6 m/s) and settle epsilons/deadlines are scenario/sampling parameters,
not acceptance bounds; each is justified inline where it appears.

## Verification

- `uv run --project automation/playgodot --frozen ruff check automation/playgodot`: clean.
- PlayGodot unit subset (`test_client.py`, `test_cli.py`, `_settle` unit
  test): 14 passed.
- `./scripts/verify-playgodot.sh` (package boundary + ruff + full 27-test
  suite, live end-to-end, macOS, `GODOT_BIN` per `scripts/godot.sh`
  resolution): three consecutive green runs after the final fix — 28.38 s,
  28.49 s, 28.64 s suite time (~30.4 s wall each). Pre-change baseline:
  28.79 s — the settle waits added no measurable slowdown, because they
  replace sleeps rather than adding to them.
- `./scripts/check.sh`: green (C# build + xUnit, Python lint + pytest,
  headless smoke).

## Register disposition

Q-035 closed (escalation executed; all four flake classes root-caused and
fixed at the source). Q-032 folded in and closed: its guard's flake was the
accumulated-force bug, and its bounds are unchanged. Recurrence surfaces
through the standing mainline-health tripwires rather than an open register
row. Q-033 (M0 profiler wall-clock test) is outside the live suite and remains
open.
