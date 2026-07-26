# P0-019 owner vehicle-feel follow-up

Date: 2026-07-25
Task: P0-019
Milestone: M0
Result: high-impact machine regressions passed; post-fix owner approval pending

## Owner report and stopping rule

Live keyboard testing reported a wheelbarrow or boat-like pivot, delayed lean and
yaw, escalating left-right oscillation, and high-speed turns that could not be
unwound without braking. Accessible was the only consistently controllable
profile; Balanced was not better than Raw. The owner asked for the concrete
causes to be fixed and then for further subjective tuning to stop unless a severe
safety or playability blocker remained.

This pass treats that decision as a scope limit, not approval of the resulting
feel. P0-020 still owns the sustained keyboard and controller sessions.

## Diagnosis

The audit reproduced four independent problems:

- steering applied a direct world-up chassis yaw torque in addition to forces at
  the front contact patches, so the body could rotate about its center even when
  wheel support and tire load did not justify the response;
- lateral force was proportional to lateral velocity and capped per nominal
  wheel, not derived from slip angle and measured normal load, so unloading and
  weight transfer did not reduce tire authority naturally;
- the 0.62 m ray suspension, -0.30 m center-of-mass offset, strong upright spring,
  and weak tilt damping produced the high-centered lean and delayed correction;
- keyboard reversal used a slow direction-change ramp, allowing a short opposite
  key pulse to spend most of its time merely canceling the previous command.

The lift-off hypothesis was only partly correct. Before the fix, a neutral
Balanced cruise run at 31 m/s lost 4.009 m/s in one second, so physical coast-down
was already excessive rather than insufficient. The real release defect was that
keyboard throttle decayed over approximately 0.200 seconds in Balanced
(0.286 seconds Accessible, 0.125 seconds Raw) before the hidden rigid-body damping
then removed speed aggressively. The combined result felt like delayed propulsion
followed by non-physical drag.

Accessible's advantage came from greater stabilization and lateral response,
not from route-following steering. The common baseline was therefore corrected
first, with assistance layered above it.

## Implementation

- Yaw now comes from steered, load-sensitive tire contact forces. The duplicate
  direct steering yaw torque was removed.
- Tire response uses slip angle, cornering stiffness, measured suspension load,
  and a friction cap. An unloaded wheel produces no lateral force.
- Suspension rest travel is 0.54 m and the center of mass is 0.40 m below the
  body origin. Upright stiffness is lower, while tilt and yaw damping are
  separated.
- A bounded slip-yaw stabilizer aligns the chassis with its actual velocity. It
  is contact-dependent and profile-scaled; it does not steer toward the road or
  an authored route.
- Godot's implicit linear and angular damping are replaced by explicit drag,
  rolling resistance, engine braking, tilt damping, and yaw damping. Longitudinal
  forces act at the grounded contact center so pitch and weight transfer remain.
- Keyboard steering has its own high-speed range and matched ramp rate. Opposite
  commands cross zero within each 0.25-second test pulse, and neutral recenters.
- Keyboard throttle reaches zero within three 120 Hz frames. Controller steering
  authority and controller throttle-release rates retain their prior tuning.

The profiles remain materially different. Accessible has the most yaw, tilt,
slip, and partial-contact stabilization; Balanced is the credible default; Raw
has the least intervention but stays inside the same recoverable physical
baseline.

## Deterministic regression result

The official Godot 4.7.1 .NET runner completed 79 runs across 3 profiles,
3 speed bands, and 12 fixtures. Aggregate result hash:
`7c317143d5d15359a7472379aa4d6988d9222cd5722e68262e878146f9f61159`.
The 30/60/144 fixed-FPS result hash was
`8e01eb2bae85df84860c551ae1479e95dafe72073a290b356ddf2a86b9f76e8b`.

All coast-down runs started at 31 m/s, released keyboard throttle in 3 frames,
used zero brake, and lost 4.016 m/s over 5 seconds. Maximum post-release speed
gain was 0.134 m/s, inside the declared 0.25 m/s transient band.

| Profile | 60 m/s swerve recovery | Final heading error | Peak roll | Peak yaw rate | Peak slip | Final speed ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Accessible | 0 frames | 1.018 deg | 0.436 deg | 0.120 rad/s | 0.857 deg | 0.951 |
| Balanced | 11 frames | 2.492 deg | 1.038 deg | 0.233 rad/s | 1.821 deg | 0.947 |
| Raw | 29 frames | 2.833 deg | 1.769 deg | 0.385 rad/s | 3.324 deg | 0.940 |

Each alternating-swerve run used six full left-right keyboard pulses and then
neutral. Every profile recovered without brake input, stayed above 70% of entry
speed, and ended within 8 degrees of the original heading. The ordering now
matches the owner's observed viable envelope without making the profiles equal.

Slow-turn recovery was 33, 30, and 24 frames for Accessible, Balanced, and Raw.
Moderate-turn recovery was 0, 20, and 37 frames respectively. These fixtures
separate a real change of heading from pathological residual yaw: the vehicle is
not required to return to its original heading after a single turn, only to stop
escalating and stabilize after steering is released.

The refreshed 500-mile regression also passed all three profiles with 455
verified chunks, 64 route transitions, 1,362 rebases, nine equivalent resumes,
and zero missing chunks, hash failures, road gaps, collision misses, or save
divergence. The final repository-wide M0 gate passed with a zero-warning build,
125 C# tests, 78 map-pipeline tests, 13 PlayGodot unit tests, Ruff, and the
official-engine smoke.

Final commands:

- `./scripts/verify-vehicle-dynamics.sh --profiles all --speed-bands all --fixtures all`
- `./scripts/run-scenario.sh --distance-miles 500 --platform current --evidence .tools/evidence/p0-019-owner-feel-long-route.json`
- `./scripts/check.sh`
- `git diff --check`

## Evidence boundary and downstream use

No severe machine-detected safety or playability blocker remains in the reported
scope. This is the good-enough P0-019 machine baseline for downstream art, map,
and gameplay work; further open-ended dynamics tuning is not required before
that work proceeds.

P0-019 remains `verified_local`, not `complete`, because P0-018 remains behind
P0-017 and the Q-029 camera review. P0-020 remains open and still requires the
human 30-minute keyboard and controller sessions. No post-fix owner approval is
claimed by this audit.
