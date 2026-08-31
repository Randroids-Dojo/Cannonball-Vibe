# PlayGodot live-suite stabilization (Q-035 escalation)

- Date: 2026-08-31
- Scope: `automation/playgodot/tests/test_live.py`, its client/launcher harness,
  and the game-side debug bridge that serves it.
- Trigger: Q-035 working default — four distinct live-suite tests flaked in
  ~5 days of continuous-mainline operation, each passing unchanged on re-run.

Status: IN PROGRESS — root-cause analysis and fixes land in this audit as they
are completed. This skeleton commit is the AGENTS.md claim for the draft PR.

## Recorded flake classes

1. `test_trip_map_resume_preserves_vehicle_vertical_stability` — macOS, twice:
   2.077 m vs 2.0 m rise bound; 5.473 m/s vs 5.0 m/s velocity bound.
2. `test_controller_deadzone_curve_and_independent_axes` — windows
   (red-main #93).
3. `test_pause_clears_held_input_until_neutral` — macOS (red-main #93).
4. `test_hostile_requests_fail_closed_and_are_transcribed` — windows,
   `TypeError: 'NoneType' object is not subscriptable` (red-main #100,
   run 33378313324): transcript entry read before it was written.

## Root causes and fixes

(to be completed)

## Threshold decisions

(to be completed — thresholds move only with measured evidence)

## Suite-wide audit

(to be completed)
