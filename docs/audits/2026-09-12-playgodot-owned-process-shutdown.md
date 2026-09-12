# P1-018 owned-process shutdown

The ordinary PR CI run34701330579 passes134 rendered UI tests on each of Windows,
Linux and Mac for head72b225ab0fd5513a16a6a6045ff27ac86b8c5d77. The tested merge
4fb0a245349867889ff7c5108ec91cc2a46b6b3e has identical scoped runtime/test bytes.
Actual Mac and Linux logs still contain shutdown diagnostics. The launcher
currently closes the RPC connection, signals the process group and discards its
return code. Minimal official4.7.1 GDScript and C# Linux controls distinguish
SIGTERM (143, missing exit-tree marker, cleanup errors) from SceneTree.quit
(0, exit-tree marker, no diagnostic lines). This supports correcting process
ownership cleanup; it does not establish the exact Apple mutex failure cause.

Before implementation, runtime owns exactly:

- `addons/playgodot/server.gd`
- `addons/playgodot/PROTOCOL.md`
- `automation/playgodot/src/cannonball_playgodot/launcher.py`
- `automation/playgodot/tests/test_launcher.py`
- `automation/playgodot/tests/test_live.py`

Implement the frozen PROPOSAL09.md in
`reports/p1-018/runtime/macos-save-clock26-rerun01/`, SHA256
eeac9ee49726ef28daa23fac5db219cf1405d318b8f240821ac018ef6ed980c8.
This extends the accepted debug-only, authenticated loopback addon under ADR0005;
it introduces no engine patch, dependency or gameplay architecture. An owner-only
shutdown capability authorizes zero-parameter session.quit. Ordinary capabilities
and connection-only session.close remain unchanged. The launcher privately retains
its own token and verified child endpoint. Tokens must never enter logs or evidence.

One absolute eight-second cleanup ceiling allocates five seconds to normal close,
owner authentication, acknowledgement and native exit; one second each to terminate,
kill and final drain. Retries consume the same remaining deadline. Accepted quit
survives peer loss. A normal cleanup requires actual exit0, completed drain and no
shutdown errors. Preserve full output, fallback details and any earlier test error;
unclean teardown fails an otherwise successful test. Cancellation and repeated stop
must preserve bounded ownership and the original result.

Run focused security/lifecycle host and native controls, then unchanged standard
Windows, Linux/Xvfb and Mac/ANGLE suites. Do not suppress the separately observed
raw signal-wait duplicate-connection errors or infer a clean log from pytest success.
Root retains independent review, documentation, evidence retention and PR commits.
The broader sedan geometry, final asset and human gates remain open.

Diagnosis is frozen by HANDOFF11.md and inventory11.json at the same reports path;
all original failures remain retained. Final evidence will distinguish functional
pass, native clean exit and reference-hardware performance.

2026-09-12T17:49:34.796388+00:00: The scoped correction is implemented. Lead reviewed the five-file runtime diff and retained both failures and focused native verification. The full Windows working-input front door passes all13 steps; current96 host,3 headless and7 rendered network tests pass with native logs checked. Exact inputs, commands, failures and independently verified retained bytes are linked in [lifecycle checkpoint](../vehicles/endurance-sedan/lifecycle-checkpoint-v26.md). Standard-platform evidence on the new commit remains pending.
