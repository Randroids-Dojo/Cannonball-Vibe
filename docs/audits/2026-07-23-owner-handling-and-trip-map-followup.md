# Owner handling and trip-map follow-up

- Date: 2026-07-23
- Tasks: P0-019, P0-013
- Base revision: `5c9ac2c2a693e9fbba9eac3d259de324fe84562d`
- Platform: Windows 11 x64
- Engine: Godot `4.7.1.stable.mono.official.a13da4feb`

## Owner findings

The owner reported that the car drove acceptably until a high-speed incline
caused prolonged flight, followed by a hard landing and throttle-induced
rollover. The owner also found Trip Overview functionally fine but visually
basic and requested both issues be addressed.

This feedback starts narrow P0-019 dynamics work and a P0-013 presentation
follow-up. It does not close P0-019's broader handling corpus or P0-013's
comprehension and accessibility gate.

## Vehicle investigation and correction

A deterministic official-engine course now drives each assist profile at
70 m/s (156.6 mph) over an 8% grade, crest, landing transition, and powered
runout. Acceptance bands were recorded in `VehicleDynamicsProfile` before
force tuning: at most 0.75 seconds unsupported, 55 degrees chassis tilt,
4 rad/s angular speed, and 1.5 seconds to stable landing recovery.

The baseline Balanced run failed with 110 consecutive unsupported 120 Hz
physics frames (0.917 seconds) against the fixed 90-frame limit. Inspection
also found three mechanisms that amplified the owner's landing:

- aerodynamic load disappeared as soon as the suspension rays lost support;
- suspension damping could request an unbounded hard-landing rebound load;
- one supported wheel immediately restored full throttle, and the drive force
  followed chassis pitch instead of the measured support plane.

The corrected model keeps bounded airborne aerodynamic load, caps per-wheel
suspension load at 6.5 g distributed across four wheels, scales drive and
braking authority by supported-wheel count, projects longitudinal force onto
the support plane, and stabilizes toward the measured support normal when
grounded. It preserves weaker Raw assists without permitting the unexplained
launch to exceed the shared physical safety band.

Final official-engine results:

| Assist | Unsupported frames | Maximum tilt | Maximum angular speed | Recovery frames |
| --- | ---: | ---: | ---: | ---: |
| Accessible | 88 | 10.100 deg | 1.423 rad/s | 114 |
| Balanced | 89 | 11.459 deg | 1.715 rad/s | 118 |
| Raw | 90 | 14.895 deg | 1.823 rad/s | 122 |

## Trip Overview polish

The authoritative Core projection and interaction model remain unchanged. The
Godot presentation now adds:

- a route-status and paused-plan hierarchy;
- an explicit progress bar and completion caption;
- a framed map grid with layered route strokes;
- shape-distinct start, destination, current, exit, transfer, and service
  markers;
- a persistent six-item legend and more legible control hint;
- a bordered information card and corrected 1280x720 text spacing.

The final PlayGodot screenshot is
`reports/p0-013-polish/trip-map.png`, SHA-256
`1713e27a774db3f1e0213877c6238157b31aaac08dde7a683b2116adcbc4951d`.
The report path is local verification output rather than a shipping asset.

## Verification

- `./scripts/verify-vehicle-dynamics.sh --profiles all --speed-bands all --fixtures all`:
  passed; 7 focused Core tests and all three official-engine profiles.
- Trip-map Core tests: 5 passed.
- Official-engine trip-map review and 3,000-mile scale scenarios: passed.
- PlayGodot package boundary: passed with the equivalent native PowerShell
  JSON read because this Windows Git Bash installation does not provide `jq`.
- PlayGodot Ruff: passed.
- PlayGodot suite: 22 passed; the final rendered-layout test was rerun after
  the spacing correction and passed.
- `./scripts/check.sh`: passed using isolated pinned `uv 0.9.24`; 100 C# tests,
  78 map-pipeline tests, 12 PlayGodot unit tests, Ruff, and official Godot
  smoke. Structured output is under `reports/m0/`.

## Remaining gates

- P0-019 remains `in_progress`: the complete speed-band, stopping, curve,
  departure, replay, frame-rate, rebase, and save-resume corpus is not claimed
  by this narrow incline regression.
- P0-013 remains `in_progress`: the owner should review the polished overview
  before Q-028 is resolved.
- P0-020's sustained 30-minute keyboard and controller sessions remain a human
  gate and are not replaced by this deterministic scenario.
