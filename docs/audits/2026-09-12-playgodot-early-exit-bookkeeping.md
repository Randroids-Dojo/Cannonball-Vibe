# P1-018 early-exit bookkeeping deadline

CI run 34709448118 on revision 568252ce674997d9d20a6959a557c7922e2fbe91
passed 176 PlayGodot tests on Linux and Mac, including host controls. Windows
passed 175 and failed the sedan
test during teardown, after its functional summary passed. The owned Godot
process acknowledged quit, exited with status 0 in 1.760842 seconds, drained
its output and reported no held input, pending wait or shutdown error.

The launcher nevertheless created a new one-second deadline for final output
and filesystem bookkeeping. The retained observation was written at 2.796074
seconds, just after that local deadline, with more than five seconds remaining
in the already accepted eight-second absolute cleanup budget. This is a
bookkeeping failure; it is not evidence of a native engine leak or crash.

Before implementation, runtime owns only
`automation/playgodot/src/cannonball_playgodot/launcher.py` and
`automation/playgodot/tests/test_launcher.py`. Use the remaining portion of the
existing absolute eight-second deadline after native exit. Do not extend that
deadline, accept forced exits, lose the original test exception, or allow a late
worker or a repeated stop call to turn a recorded failure into success.

The reports-only proposal and original platform evidence are retained under
`reports/p1-018/runtime/lifecycle26-platform02/`. Matched schedule reproduction
fails with the old arithmetic at 2.790 seconds and passes with the proposal at
2.799 seconds. A 5.25-second bookkeeping delay finishes at 7.024 seconds; work
beyond the unchanged absolute deadline fails. The existing controls remain
unchanged and two early-exit controls are added. All 98 selected host controls
and Ruff pass on the proposal. These are local proposal results, not a new
Windows CI pass. Lead review, current native checks, full local front door and
new-commit platform evidence are still required.

Lead additionally owns the corresponding deadline wording in
`addons/playgodot/PROTOCOL.md`. Update its obsolete one-second final-phase
description before running the full front door; this documents the same bounded
implementation and adds no capability or timeout allowance.
