# P0-013 Trip Overview resume stability

- Date: 2026-07-28
- Task: P0-013
- Base revision: `b801ba97612be80c3d079781fed7d28a3a39c17a`
- Regression revision: `11544fb8193c5e12d94707bb4676aabc1dc1a047`
- Platform: Windows 11 x64
- Engine: Godot `4.7.1.stable.mono.official.a13da4feb`

## Outcome

The previously reported low-priority case where returning from Trip Overview
could launch the car skyward does not reproduce on the current integrated
vehicle dynamics. The investigation adds an official-engine PlayGodot
regression so the pause/resume seam is no longer covered only by visibility and
pause-flag assertions.

P0-013 remains `in_progress`. This machine result does not approve Q-028's
trip-map comprehension and accessibility gate.

## Regression contract

The test waits for at least three grounded wheels, holds full keyboard
throttle until the vehicle exceeds 12 m/s, opens Trip Overview while throttle
remains held, and then verifies:

- position and all three linear-velocity components remain unchanged within
  0.001 while the scene tree is paused for 250 ms;
- the first second after returning to drive rises no more than 2.0 m above the
  paused position;
- upward velocity remains at or below 5.0 m/s; and
- angular speed remains at or below 5.0 rad/s.

These bounds were declared before the moving probe was run. `run.session` now
exposes the three linear-velocity components and grounded-wheel count through
stable read-only automation state so failures retain actionable evidence.

## Verification

- Pinned Windows doctor: passed .NET SDK `10.0.102`, uv `0.9.24`, Git LFS
  `3.7.1`, Perl, and official Godot `4.7.1`.
- Focused moving PlayGodot regression: passed.
- `./scripts/verify-trip-map.sh --automation auto`: passed 5 focused Core
  tests, both official-engine trip-map scenarios, zero-warning builds,
  package-boundary checks, Ruff, and all 26 PlayGodot tests.
- The 3,000-edge scale scenario selected LOD 1 with 15,001 projected points and
  completed projection in 31.749 ms on this host.
- `./scripts/check.sh`: passed the pinned doctor, zero-warning build, 139 C#
  tests, Ruff, 79 map-pipeline tests, 13 PlayGodot unit tests, and the official
  Godot smoke. Structured results are under `reports/m0/`.

The first test attempt compared the paused state with a sample taken before the
toggle action had been processed and correctly observed ordinary vehicle
movement during that input window. The probe was corrected to anchor the
invariance comparison after the map reported the scene tree paused. No product
threshold was changed.

## Remaining boundary

The integrated visual-slice trigger for Q-028 is not yet satisfied because
P1-008, P1-009, and P1-010 remain in progress. Once that build exists, the
owner still needs to review map comprehension, accessibility, and visual
quality. This regression neither performs nor substitutes for that review.
