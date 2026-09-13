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
