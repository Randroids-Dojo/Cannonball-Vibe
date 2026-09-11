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
