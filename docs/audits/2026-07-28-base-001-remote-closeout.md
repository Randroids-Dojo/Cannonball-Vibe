# BASE-001 remote CI closeout

- Date: 2026-07-28
- Task: BASE-001
- Main revision: `a1642c3874731b19e1b15bce3b7f93525e8f25d8`
- GitHub Actions run: `30423454399`
- Result: success

## Outcome

BASE-001 is complete. Its implementation had remained `verified_local` only
because the same technical slice had not yet been accepted by the required
remote CI. The exact merged `main` revision now passes the complete Ubuntu and
Windows M0 jobs and writes their uploaded evidence.

## Acceptance mapping

| Acceptance criterion | Current evidence |
| --- | --- |
| C# solution builds without warnings or errors | The pinned local Windows M0 gate built with zero warnings; remote Ubuntu and Windows M0 jobs passed. |
| At least the original 8 xUnit tests pass | The current local M0 gate passed 139 C# tests; both remote M0 jobs passed the same checked-out `main` revision. |
| Python pytest suite passes | The current local M0 gate passed 79 map-pipeline tests and 13 PlayGodot unit tests; both remote M0 jobs passed. |
| Godot headless smoke completes and writes a save | The current local smoke emitted `CANNONBALL_SAVE_OK` and `CANNONBALL_SMOKE_OK`; both remote M0 jobs passed and uploaded evidence. |

The original numeric test count is a historical minimum, not a reason to
reduce the current suite or rewrite acceptance.

## Remote evidence

- Workflow run: `30423454399`, conclusion `success`, completed
  `2026-07-29T05:00:22Z`.
- Ubuntu M0 job: `90484750367`, conclusion `success`.
- Windows M0 job: `90484750316`, conclusion `success`.
- Ubuntu, Windows, and macOS PlayGodot jobs: `90484750351`, `90484750343`, and
  `90484750335`, all `success`.
- Ubuntu and Windows deterministic 500-mile jobs: `90484750406` and
  `90484750345`, both `success`.

The additional semantic and long-route jobs are corroborating evidence; only
the two M0 jobs are needed to retire BASE-001's recorded blocker.

## Boundary

BASE-001 has no human gate. Closing this foundational task does not change the
status of P0-013, P0-017 through P0-020, the visual-slice tasks, physical
hardware qualification, signing, spending, or public release.
