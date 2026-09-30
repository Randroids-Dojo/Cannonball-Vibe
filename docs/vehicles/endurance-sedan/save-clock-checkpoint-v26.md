# F5 clock checkpoint - 2026-09-12

The selected-vehicle save test now waits for a clock sample produced after the
completed save-file read. This fixes the observed macOS ordering failure without
changing the run clock, save behavior, elapsed-time tolerance or test deadlines.
The [dated audit](../../audits/2026-09-12-sedan-save-clock-observation.md) explains
the cause and the three-file implementation scope.

Windows verification passed all 117 selected host controls, the ordinary
selected-sedan UI test, and all 13 steps of `scripts/check.sh`. The UI test
exercised Hero GT, graybox and Meridian S8R selection and save assertions. It used
installed production34 with official Godot 4.7.1, so these results do not accept
the newer model under construction. New-head macOS CI is still required.

The [review archive](../../../data/assets/vehicles/endurance-sedan-review/save-clock-checkpoint-v26/save-clock-checkpoint-v26.zip)
retains the original macOS artifact, failed and corrected preparations, exact
test proposals, host controls, actual Windows captures, logs and the full local
front door. Its SHA-256 is
`0934fd228b25af314f7e898bec0ee34f2a235edea2dff024a3872a6f6289c289`.
The adjacent manifest lists 354 files totaling 21,285,573 uncompressed bytes.
Two independently written archives are byte-identical; every member checksum
and archive CRC was verified. This proves review retention, not final asset
export reproducibility.

The Windows front door ran from 14:32:07Z to 14:36:30Z against base revision
`a159ba1de94820bc41d50c1cf925c697ce3431b2` plus twelve explicitly hashed working
files: three save-test files and nine source-QA files. The archive retains those
exact bytes. The source-QA changes are separate unfinished construction work;
the full 21-stage source gate has not passed on a final asset.

Mac shutdown diagnostics, final model/export/runtime/platform/performance
evidence and human visual, driving, calibration, usability and rights reviews
remain open. P1-018 stays `in_progress`; PR #144 stays a draft.
