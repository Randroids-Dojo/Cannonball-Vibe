# P1-018: observe the clock after the completed F5 save

The standard macOS PlayGodot suite at `a159ba1de94820bc41d50c1cf925c697ce3431b2`
failed because the test compared a newly written save with a cached run-clock
sample that could precede that save. The observed values were 50.375 seconds in
the save and 50.355 seconds in the following cached sample. The earlier
1.016-second clock-advancement check passed. The suite reported 113 passes and
one failure; its camera test passed independently.

`Main` samples its automation metadata early in `_Process` and handles F5 later
in the same frame. After reading the completed file, the corrected test observes
that cache once and waits for a strictly newer sample. The saved elapsed value
never controls readiness. The existing 10-millisecond comparison, single
10-second clock wait, ordinary 30-second RPC policy and 240-second outer test
deadline remain unchanged. It retains the exact asserted save bytes and both
clock samples before evaluating the upper-bound assertion.

The authorized implementation owns only
`automation/playgodot/tests/test_endurance_sedan.py`, the new
`automation/playgodot/tests/test_save_clock_state.py`, and one test-selection
argument in `scripts/check.sh`. It changes no engine, runtime, vehicle, save
format or clock behavior. Twenty portable schedule controls exercise the real
test functions, including the old ordering failure, a frozen cache, a future
save, deducted map-pause time and incorrect vehicle reconstruction.

The ordinary Windows selected-sedan UI test passed on installed production34
with the official Godot 4.7.1 Compatibility renderer. Hero GT, graybox and sedan
each completed their saved-clock assertions, all 505 RPCs succeeded, and four
rendered selection generations completed. The 17.79-second test duration is
functional evidence only; CPU construction work could overlap. All 117 selected
host tests, Ruff, build and official-wrapper import passed. Root's subsequent
Windows `scripts/check.sh` front door passed all 13 steps on the exact recorded
working inputs at 2026-09-12T14:32:07Z through 14:36:30Z.

The original macOS artifact, failed/retried diagnostic preparations, exact
proposals, host controls, Windows captures and logs are retained in the
`save-clock-checkpoint-v26` review archive. The archive manifest distinguishes
the tested base revision from the uncommitted file hashes. The original failed
save bytes were not captured by the old test, so the synthetic replay's frame
timestamps are not presented as native Mac observations. Earlier Mac teardown
errors remain separate unresolved evidence.

New-head macOS CI is still required. This checkpoint does not approve the
unfinished source26 model, its export, full source QA, performance, packages or
human visual, usability, driving, calibration and rights gates. P1-018 remains
in progress, and PR #144 remains a draft under ADR-0025.
