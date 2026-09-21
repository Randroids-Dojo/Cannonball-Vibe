# P1-018 shutdown deadline test correction — v33

On commit a7dccc85, the macOS PlayGodot job failed a host test after intentionally stuck shutdown had already been rejected. Its measured wall duration was 8.324299 seconds, exceeding the test's 8.3-second dispatch allowance. The other 205 cases passed, six were skipped, and the actual showroom scenario passed.

The test now observes the actual absolute phase deadlines at 5, 6, 7 and 8 seconds and verifies the failed child/output state. Four public cleanup cases prove that completion at 7.99 and 8.0 seconds succeeds, while 8.000001 and 8.324299 seconds fails with every other success prerequisite present. The production launcher remains byte-exact; its eight-second limit and cleanup behavior are unchanged. The retained index contains its full SHA-256.

A controlled Windows callback stall reproduced the old wall assertion failure at 8.3888835 seconds. The new oracle passed at 8.3980282 seconds while still observing a failed production cleanup owner. This demonstrates dispatch sensitivity; it does not establish the exact macOS delay cause.

Focused launcher/client validation passed 135 cases. The complete Windows `scripts/check.sh` front door passed all 13 steps from 09:04:41 to 09:09:24 UTC, including 190 PlayGodot unit cases. Pytest reports one `record_property`/xunit2 compatibility warning; elapsed diagnostics and successful results are retained. All bound code inputs stayed unchanged during the full run. The final full gate exercised the final test bytes.

The original failure, induced reproduction, successful controls, lint correction, commands, hashes and full front-door reports are retained in [the v33 index](../../../data/assets/vehicles/endurance-sedan-review/ci-deadline-v33/index.json). Two archive builds compared every byte; every member was reread and compared with its source. The archive also preserves new art scope records; no in-progress art proposal is marked complete. The archived retention script's initial prose formatter was corrected in this checked-in document because it inserted spaces into identifiers; this does not change the archived test evidence.

New-revision Linux, Windows and macOS recovery is pending the push. The two M0 jobs alone govern merge eligibility under ADR-0025. Existing sedan asset failures and final art, rights, usability and driving approval gates remain open. This correction does not update the installed production34 model.
