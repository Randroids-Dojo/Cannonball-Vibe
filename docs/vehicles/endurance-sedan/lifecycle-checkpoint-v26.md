# P1-018 debug lifecycle checkpoint

The debug automation launcher now asks its authenticated child process to quit
through the official Godot main loop. Normal teardown requires an acknowledged
owner-only request, actual exit0, completed log drain and clean shutdown
diagnostics. The existing eight-second cleanup bound covers all fallback phases;
a forced exit fails teardown and preserves an earlier test failure. Ordinary
clients retain their previous capabilities and connection-only `session.close`.

Concurrent signal waits now use distinct native callbacks and reserve a slot
only after a successful connection. A short wait cannot disconnect a longer
wait, and freed targets reach the validity guard safely. Native regression
cases verify all eight correlated requests, independent deadlines, the existing
capacity/duplicate-ID rules, target deletion and connection failure.

Windows verification passes96 host tests,3 headless signal cases,7 rendered
network tests and pinned Ruff. The full `scripts/check.sh` front door passes
all13 steps with20 unchanged bound inputs. It ran revision72b225a plus14
working runtime/source-QA files; the exact copies are retained. The source-QA
edits are a separate workstream and are not part of this runtime commit.
Earlier134-per-platform UI results belong to72b225a; they do not certify this
new lifecycle correction on Linux or Mac. New-commit CI remains required.

The [retained manifest](../../../data/assets/vehicles/endurance-sedan-review/lifecycle-checkpoint-v26/manifest.json)
binds893 inputs plus itself. Two54,707,049-byte ZIPs have SHA-256
`8d59a307e58f5e988f2d476e73bec4f87c8e9448c5b2d1370dec1f2e8d527af3`.
The lead independently read every member and checked all SHA/CRC values in both
archives before promotion. It retains actual native failures, retries, all five
original workflow artifact ZIPs and355 explicit cache omissions. See the
[checkpoint handoff](../../../data/assets/vehicles/endurance-sedan-review/lifecycle-checkpoint-v26/HANDOFF02.md)
for exact scope, recipes and external art bindings.

Installed production34 source and assets are unchanged. P1-018 remains in
progress with final geometry, source QA, LOD/export, runtime media, performance,
platform and human gates open. No driving-feel, visual, rights or usability
approval is inferred from the machine evidence.
