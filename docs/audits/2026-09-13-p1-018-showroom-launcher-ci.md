# P1-018 showroom launcher CI correction

The renderer unit test now preserves the configured executable path and
explicitly exercises direct and Linux Xvfb launch prefixes. The production
launcher is unchanged. Linux and macOS virtual environments use executable
symlinks; resolving that expected path in the test incorrectly rejected the
actual launch. Linux semantic CI also legitimately prefixes it with
`xvfb-run -a`.

At revision `00c033dfc5662d1e2495ab683927d6632cfc6219`, those two assertions
were the only semantic-suite failures on Linux and macOS: each had 202 passing
and six skipped tests. The actual showroom and sedan-selection cases passed.
Windows M0 and semantic UI passed. Linux M0 and fixture exports failed on the
same symlink assertion.

The correction passes all 120 launcher cases, Ruff, and all thirteen steps of
the required Windows `scripts/check.sh` front door. Its PlayGodot unit step
passes 186 cases. Seventeen bound source inputs remain unchanged through that
full check. Remote recovery requires the new PR revision's results.

Both current sedan asset jobs still reject the unchanged production34 source
on four invalid raw normal groups: LOD1 OpticalGlass and Trim, LOD2 hood Paint
and fixed-body Paint. The exact stderr and complete artifacts are retained.
New Blender construction remains separate and is not approved by this fix.

The [retained index](../../data/assets/vehicles/endurance-sedan-review/showroom-ci-v30/index.json)
binds original logs, command statuses, tools, source hashes, failed local
invocations, full local results and a byte-verified archive. The task evidence
is [P1-018](../../evidence/M5/P1-018.json). PR #144 remains a draft while model
and asset defects are corrected; P1-018 and all outstanding human gates remain
open.

## Recorded platform recovery

The corrected head `bd57332280ae5846b76066127174224fefc68273` passed both M0 checks and the rendered semantic suites on Linux, macOS and Windows. CI checked the temporary PR merge `a59ecda97e9e6dc94dbbb5e163a41870980bcf8f` against main `827bb14618e99a85d709e89cdd828877b6ff1566`; this is not a mainline merge claim. Semantic totals are206passed6skipped on Linux and macOS,212passed on Windows.

Both fixture exports built twice successfully. Actual clean-package evidence contains10/10 launch smokes and passed sedan driving/presentation summaries on Linux and Windows. The two original sedan asset-export jobs still fail on the installed production34 source; their raw logs remain alongside the recovery evidence. `P1-018-SR29-018` is corrected and verified; final source/art, LODs, performance and human task gates remain open.

The [v31 evidence index](../../data/assets/vehicles/endurance-sedan-review/showroom-ci-recovery-v31/index.json) binds the exact completed jobs, actual package evidence, input hashes, raw failures and archive verification. The archive was built twice and compared byte for byte; this is evidence retention, not new GLB reproducibility.
