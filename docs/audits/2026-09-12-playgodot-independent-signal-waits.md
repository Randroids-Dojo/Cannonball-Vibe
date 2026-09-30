# P1-018 independent signal-wait lifecycle

The retained hostile-request logs exposed a functional defect: eight admitted
waits on one signal create only one native connection, so one emission completes
only one request. A short wait can disconnect an earlier long wait. A freed
target also throws at a typed assignment before the existing validity guard.
These failures are reproduced in official Godot 4.7.1, independently of shutdown.

Before implementation, extend the runtime writer's scope only to these existing
owned paths:

- `addons/playgodot/server.gd`
- `addons/playgodot/PROTOCOL.md`
- `automation/playgodot/tests/test_live.py`

Apply the bounded candidate03.patch from
`reports/p1-018/runtime/signal-wait26-diagnosis01/`, SHA256
`fac4f440c6f8f3a636bdadca7c92e857f0394b72d1778dce9cb7d6ab5e7a1306`.
Use a distinct closure per pending request, require a successful native connection
before reserving its slot, and read freed-target references as Variant before
the existing validity guards. This corrects the accepted ADR-0005 debug addon;
capacity, timeout, capability and gameplay contracts stay fixed.

Acceptance requires real network delivery to all eight correlated waits,
staggered-timeout isolation, existing capacity and duplicate-ID behavior, freed
target timeout/disconnect cleanup, and explicit failure before reservation on a
native connection error. Retain the original errors and every failed attempt.
The current shutdown, authentication and readiness tests must still pass, with
actual native exit and complete logs checked. Root owns independent review,
full M0, cross-platform CI, evidence retention, governance and commits.

The diagnostic handoff is HANDOFF05.md, SHA256
`6bf3994632995db87e3939823e1ea79a6f91352f9e753a32ec626cacb624f6bf`.
This is scope authorization and a reproduced finding, not final platform evidence.

2026-09-12T17:49:34.796388+00:00: The scoped correction is implemented. Lead reviewed the five-file runtime diff and retained both failures and focused native verification. The full Windows working-input front door passes all13 steps; current96 host,3 headless and7 rendered network tests pass with native logs checked. Exact inputs, commands, failures and independently verified retained bytes are linked in [lifecycle checkpoint](../vehicles/endurance-sedan/lifecycle-checkpoint-v26.md). Standard-platform evidence on the new commit remains pending.
