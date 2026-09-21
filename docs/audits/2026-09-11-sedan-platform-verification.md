# P1-018 platform verification repair, 2026-09-11

PR144 head `637c29aa5c1003188229aa95e956943879096f54` was tested by the
GitHub PR merge revision `d615a3ab5fb3950f46f6b538fea69c9106967462`.
The two M0 jobs passed. Required broader evidence exposed the following faults;
their original logs and exact API-digest-verified artifact ZIPs are retained in
`reports/p1-018/remote34-01/retrieval.json`.

| Run | Observed failure | Repair scope |
|---|---|---|
| 34649080001, Linux sedan asset | UV-only bake rejects non-UV layout differences | Lead: source-bound ordered-corner encoding bake and real corruption controls |
| 34649080001, Windows sedan runtime | Missing `.godot/imported` textures in a fresh checkout; scenario itself reaches all17 stages | Runtime: explicit official-engine fresh import before the functional suite |
| 34649079946, Linux and Windows packages | Natural-rebase traversal stalls on the default short corridor before900m | Runtime: package and declare the existing locked representative fixture for the69-stage verifier; preserve default launcher/smokes |
| 34649080047, Windows PlayGodot |30s `run.session` request timeout after selecting Hero GT under ANGLE software rendering | Lead: diagnose actual loading/response evidence before correction |

The raw Linux and Windows exports contain identical scene, node, material and
image metadata. Comparing indexed triangle corners, rather than deduplicated
vertex row numbers, finds at most0.00000011920928955078125m position difference,
0.020593529degrees normal difference and0.000000953674317 UV difference.
All triangle counts and ordered corner correspondence are retained in
`reports/p1-018/linux-glb34-diagnostic02/evidence.json`; the first row-index
diagnostic remains as a documented incomplete comparison. A bounded corner bake
must verify those attributes and every unchanged non-geometric payload before
restoring a reviewed canonical encoding. It must not accept missing geometry,
changed winding, arbitrary material edits or a changed source hash.

These repairs remain within ADR-0012's original-art asset pipeline and the
existing custom vehicle architecture. They do not change physics, speed policy,
Core save schemas, performance gates or human approval requirements. Passing M0
is merge eligibility only. Subsequent measurements and corrective evidence are
recorded in the P1-018 ledger artifact; this dated failure record stays intact.

The isolated diagnostic run34658981204 uses the same source637 and official
Godot4.7.1 under ANGLE's Microsoft Basic Render Driver. Its first post-Hero
request takes29,366.876ms; matching frame-pre/post-draw checkpoints enclose
29,356.721ms of that delay in the same rendered frame182. This identifies a
first-render readiness gap after reconstruction; it does not identify shader
compilation as its internal cause. The original full-suite timeouts are retained.

Before implementation, authorize a bounded PlayGodot readiness correction in
exactly `addons/playgodot/bootstrap.gd`,
`automation/playgodot/src/cannonball_playgodot/launcher.py`,
`automation/playgodot/tests/test_launcher.py`, and
`automation/playgodot/tests/test_endurance_sedan.py`. The debug fixture records
an actual same-instance first completed rendered frame after selection. A
monotonic generation and exact requested asset/body/panel identity prevent a
previous selection satisfying readiness. The launcher waits on its existing
stdout drain before the existing RPC assertions, using the test's existing60s
startup allowance as a separate first-render bound. All ordinary30s RPC limits,
the240s outer test deadline and original functional assertions remain intact.
Require stale/wrong/pre-only/malformed/missing/exit/cancellation controls,
bounded state, debug-only activation, callback cleanup, and actual delayed-frame
positive/no-wait-negative cases. Then rerun the original full local and remote
UI suites. Bootstrap telemetry is test readiness evidence, not gameplay or
performance acceptance; production C# and server/client RPC behavior stay intact.
At2026-09-12T00:20UTC, the readiness repair scope includes one additional
positional test file in the existing `pytest-playgodot-unit` M0 step:
`automation/playgodot/tests/test_launcher.py`. Its fake-stream and subprocess
controls require no native renderer. Keep the existing step, limits, report
paths and all other test selections unchanged. The full rendered suite and
new committed-head Windows/Linux/macOS evidence remain separate requirements.

At2026-09-12T00:36:28Z the five readiness files are frozen and locally verified.
The unfiltered PlayGodot suite passes81 tests in53.69s; the front door takes
75.861s and the sedan test16.72s. Full M0 passes all13 steps in200.821s,
including157 .NET tests,345 map tests with one existing skip and64 automation
units. The command envelope is
`reports/p1-018/runtime/windows-ui-retry34-01/full-ui-01/evidence.json`, SHA256
`2e45a25a7317910293e26ffad8ba142a6127bcafec616f901a874fda72edea0c`.
Its469 scoped input hashes are unchanged and71 output artifacts are recorded.
Independent review `qa/readiness34-reviewed-03/review.json` has SHA256
`d40125cc9ea63dff1bd5d2c74dd50345327f0e7322acb7807a78897001aa3b65`.
The actual31s delayed-render case passes; no-wait and premature-ready controls
fail at the unchanged30s RPC deadline. No engine process remains. This is
source34 runtime preparation evidence on local NVIDIA Compatibility, not the
new source35 model, remote Microsoft backend or reference performance result.
