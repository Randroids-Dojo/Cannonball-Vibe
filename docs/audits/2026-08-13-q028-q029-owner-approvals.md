# Q-028 and Q-029 owner approvals

Date: 2026-08-13

Questions: Q-028 (trip-map comprehension and accessibility usability),
Q-029 (cockpit and chase camera comfort and readability)

Tasks affected: P0-013, P0-017, P0-018, P0-019

## Trigger condition

Both reviews were deferred on 2026-07-23 as Q-028/Q-029 Option C, and the exact
trigger was selected on 2026-07-26 as Option A: perform the reviews once a single
build integrates the representative Hero GT, the production highway kit, and one
regional environment slice, before final polish.

That trigger was met by the integrated visual slice merged in PR #51. The gate
script `scripts/verify-integrated-visual-slice.sh` passes on the reviewed
revision, reporting `vehicle=hero-gt road=production environment=balanced`.

## What the owner reviewed

Renderer captures taken on 2026-08-13 at Forward+, 1920×1080, on the
`representative-corridor` fixture with the Hero GT, the production road profile,
and the regional environment:

| Surface | Capture | Conditions |
| --- | --- | --- |
| Chase camera | acceleration sweep, 0 to 204 mph | default scene lighting |
| Chase camera | daylight sweep, 0 to 101 mph | daylight, High environment profile |
| Cockpit camera | cockpit-chase transition stage | default scene lighting |
| Trip overview | full-screen trip map | `representative-interchanges` fixture |

Two limitations were disclosed to the owner before the decision:

- The cockpit is the accepted graybox placeholder recorded under P0-018. It has
  no interior art; the capture shows the driver-eye anchor with cockpit-
  obstructing exterior layers culled.
- The cockpit capture is not in daylight. At review time the camera-handling
  contract scenario was the only path that reached cockpit view and it accepts
  no lighting argument. This audit's own follow-up adds
  `--reference-camera=chase|cockpit` so a daylight cockpit capture is reachable.

## Decision

The owner reviewed the captures and approved both gates on 2026-08-13.

Verbatim: *"The views are fine for today, but I reserve the right to tweak more
later. Map looks good."*

Asked how to record that reservation against the delivery contract, the owner
selected, for both questions, that the gates close as approved and that any later
polish is raised as new work rather than reopening the gate.

| Question | Result | Consequence |
| --- | --- | --- |
| Q-029 | Approved | P0-017 human gate closes; P0-017, P0-018, P0-019 may complete |
| Q-028 | Approved | P0-013 human gate closes; P0-013 may complete |

## Boundaries

This approval covers camera comfort and readability, and trip-map comprehension,
on the reviewed integrated slice. It does not:

- approve production vehicle, cockpit interior, highway kit, or environment art;
- close P1-008, P1-009, or P1-010;
- advance any rights, performance, or Q-022 budget gate;
- replace P0-020's sustained 30-minute handling sessions, which remain a separate
  pending human gate;
- constitute an accessibility conformance review beyond the owner's own reading
  of the captured surfaces.

The owner's reservation is recorded as a standing right to request camera or map
presentation changes. Under the recorded decision those requests are new tasks
against P0-017 or P0-013 rather than a reopening of Q-028 or Q-029.
