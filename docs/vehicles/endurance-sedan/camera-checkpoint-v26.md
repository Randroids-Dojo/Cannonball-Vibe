# Camera observation checkpoint — 2026-09-12

The shared camera observation correction passes the full Windows
`scripts/check.sh` front door:13 steps, all exit0, from12:57:19 to13:00:47 UTC.
This checkpoint does not replace the sedan model or establish a macOS pass.

The [archive](../../../data/assets/vehicles/endurance-sedan-review/camera-checkpoint-v26/camera-checkpoint-v26.zip)
retains610 files: the original Mac failure investigation, source proposals,
actual official-engine fixture results, bounded negative controls, integration
failures and corrections, the focused Windows UI test, and full Windows results.
Its adjacent `manifest.json` lists every input hash; `index.json` records two
byte-identical ZIP writes and verification of every member hash and CRC.
Archive SHA256 is
`a052365a52246b4bb9890adfce4d22cf9f3583e018f253ae1c5ff04f542dbb81`.

Extract into a new empty review directory. The exact integrated change is
`reports/p1-018/runtime/macos-camera26-integration01/final.patch`.
`HANDOFF02.md` in that folder explains the evidence and limits. Full results are
in `reports/p1-018/camera26-frontdoor01/m0/summary.json`; the native08 fixture
retains detailed completed-cast/lifecycle values. The ordinary Windows camera
test uses the red graybox in the official corridor and OpenGL Compatibility.
Its two actual screenshots verify the shared camera fixture, not sedan cockpit
quality or Forward+ performance. The ordinary transcript records successful RPCs
and assertion execution, not raw numerical response payloads or the engine exit
code. The observed Windows log is clean; macOS shutdown diagnostics remain open.

The M0 report records base revision
`11d80201e79712dd10ac203a982fc1765dded7cd` with the six integrated working files.
The manifest and final patch bind those exact tested bytes; this is not a claim
that the unchanged base commit contained the correction. No assertion or timeout
was relaxed. The separate scope audit records the debug-only observation design.

CI must rerun the declared platforms, including macOS, on the checkpoint commit.
The sedan's roof closure, combined geometry, final LOD/export/runtime/media and
performance work remains open. Human art, rights, handling and usability gates
remain pending. P1-018 remains `in_progress`.
