# P1-018 Windows save replacement

The required Windows sedan selection/F5 test failed on PR144 head
`1c44669f9efcaaa44b8220251fd2dcb997a3f2bf`. The actual engine log records
`UnauthorizedAccessException` at `JsonRunStateRepository.SaveAsync`'s
`File.Move(temporaryPath, _path, overwrite: true)`. The selected graybox clock
advanced by1.069 seconds over1.069 seconds; the save operation failed before
its completion marker. This was not evidence of a clock reset.

The failure is retained under `reports/p1-018/hosted39-249/`: the Windows UI
job104019762650 in run34857214180 reported1 failed/329 passed. Both M0 jobs,
Linux/macOS UI, both500-mile jobs, and unsigned Windows/Linux smoke jobs passed;
asset generation still failed for the separately documented missing current
source binding. The hosted process holding the destination handle was not
traced. A concurrent reader is a reproduced cause, not an identified hosted
process.

Scope251 records the bounded repair and file ownership before implementation.
The existing draftPR144 was the only open claim; mainline had no red-main issue.
No save schema, migration, route authority, backup validation, UI timeout or
clock assertion changed.

An actual Windows reader opened with `FileShare.ReadWrite` blocks replacement.
The new regression failed on the original code at the same `File.Move` access
error. Original command254 mistakenly left a PowerShell logger semicolon
unquoted; the test still reproduced the native error, but its TRX used the
default folder. The corrected invocation254 retained the same failure at the
intended evidence path. Both command records remain.

The repair retries only Windows access/sharing/lock errors from the final
atomic move: at most21 attempts, with20 cancellable50ms waits. The flushed
temporary file and prior complete primary remain intact during those waits.
A persistent error propagates and the existing cleanup removes the owned
scratch file. Cancellation also preserves the prior primary and backup.
This covers a transient handle without changing file permissions or writing
over the primary in place. These semantics follow the existing atomic local
save contract; [File.Move's documented access errors](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.move?view=net-8.0)
and [FileShare's deletion-sharing flag](https://learn.microsoft.com/en-us/dotnet/api/system.io.fileshare?view=net-8.0)
explain the Windows boundary.

All13 save-repository checks passed after repair, including three native
Windows handle cases: release, persistent lock and cancellation. The release
case verifies exact serialized replacement state and the previous backup;
terminal cases verify unchanged primary/backup bytes and no owned `.tmp` file.
The Windows-specific cases are explicitly skipped on other operating systems.
Evidence: `reports/p1-018/save-replace39-251/{before254,after256}/` and exact
commands under `reports/p1-018/source-pipeline38-01/commands/`.

Full front door 265 passed all 13 steps with all 706 bound inputs unchanged.
The unchanged official-engine inspection/selection test 266 then passed in
19.434 seconds using the newly compiled assemblies and installed production34
asset. Its retained artifacts include actual F5 saves for the sedan, Hero GT
and graybox, four runtime PNGs, and the original clock assertions. Native
shutdown acknowledged the quit request, exited with status 0 in 0.371 seconds,
and reported no diagnostics or fallback. All test-bound inputs remained exact.

Evidence: `reports/p1-018/source39-frontdoor265/summary.json`,
`reports/p1-018/source-pipeline38-01/full-gate265-bindings.json`, and
`reports/p1-018/save-replace39-251/runtime266/result266.json`. This local result
does not declare hosted platform recovery, a clean asset import, final sedan
assets, source rights, driving feel or human usability complete.

Hosted recovery was subsequently verified at revision
`2413b9ee5b4e27105ad9eb425ac4c58be6dbfa29`. CI run34868305673 passed both M0
jobs, Windows/Linux/macOS semantic UI and both 500-mile jobs. The Windows UI
job passed all 330 tests. Its downloaded inspection evidence contains valid
F5 saves for Hero GT, graybox and sedan, each with an advancing run clock and
the expected exact save hash. The inspection process acknowledged normal
shutdown, exited 0 in 1.593 seconds and reported no diagnostics or fallback.
The native-observation record retains `bookkeeping_completed=false`; passing
context/profile cleanup assertions provide separate owner evidence.

Root inspected the four actual hosted images: three full 1028x578 captures
and one 269x338 panel crop. They confirm the inspection panel, opening
silhouettes and Escape behavior, while the small dark car cannot establish
close assembly quality. The terminal CI metadata, full Windows artifact and
save comparisons are retained in `reports/p1-018/hosted39-280/` and
`reports/p1-018/source-pipeline38-01/checkpoint283.json`. Both sedan asset
jobs still fail the separate current-source generation-binding requirement;
the save recovery does not close that asset gate or any human gate.
