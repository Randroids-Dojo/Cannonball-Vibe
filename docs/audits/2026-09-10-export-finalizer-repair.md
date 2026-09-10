# P0-025: remaining export shutdown crash

Date: 2026-09-10. Claim: [PR #142](https://github.com/Randroids-Dojo/Cannonball-Vibe/pull/142).

The owner requested a new original sedan. Red-main #140 takes precedence under
ADR-0025. The current main commit `4c65817dd5036d1d82e1fbe5940e0e64c31ad66d`
has green CI, assets and Windows soak, but its unsigned-export run
[34171220619](https://github.com/Randroids-Dojo/Cannonball-Vibe/actions/runs/34171220619)
fails on Windows after all functional smoke markers. The retained stack ends in
`godotsharp_internal_object_get_associated_gchandle`, `GodotObject.Dispose(Boolean)`
and `GodotObject.Finalize`, with an AccessViolationException. The console wrapper
reports zero; the existing strict transcript check correctly rejects the fatal.
P0-024 is historical evidence of two passing exports, not proof this failure
cannot recur.

## Ownership and scope

The lead owns the ledger, this audit, structured evidence, release verifier and
CI smoke repetitions. The runtime agent owns application lifetime corrections
and the targeted in-engine shutdown probe. A reference agent inspected the exact
official engine source; an independent QA agent reviews probe acceptance and
artifact retention. The authoritative engine and physics remain unchanged.

## Retained baseline

The original Windows archive SHA-256 is
`d89b801ec674185f2c1968a1d44456442ca4eb1e8395a3f61fa5c50cc4746fa1`.
The archive and logs are retained in `reports/p0-025/upstream/`; upstream job
metadata and failed output are also in `reports/p0-025/upstream-run.json` and
`reports/p0-025/upstream-failure.log`. Twenty unmodified local repetitions passed
(12 default nursery, eight with 64 KiB nursery). This bounds local observation;
it does not reproduce the reported crash or close the defect.

## Verification change

Ten sequential fresh-home package smokes per native CI platform now supplement
the specific lifetime regression. Each must pass the existing content identity,
startup, save, smoke, automation-exclusion, process-status and fatal-output checks.
A failed attempt terminates the job; later success cannot hide it. Every attempted
runtime and verifier transcript lives outside the exact-inventory package and is
uploaded even when the job fails. The structured summary records completed count
against ten required attempts. This is repetition for an intermittent defect,
not retry-to-green.

The full captured fatal transcript is asserted by a verifier unit fixture. These
synthetic fixture results are distinct from actual exported-engine evidence.
Windows process status still comes from the console wrapper. Transcript rejection
covers this known crash; an otherwise silent native abort after all required
markers is a remaining limit of that launcher observation.

## Source analysis and candidate status

The exact official engine source shows a finalizer querying the native GC handle
before clearing its pointer. Its shutdown tracker uses short weak references and
does not drain pending finalizers. A queued wrapper missing that disposal pass is
a plausible race, pending the targeted probe; the stack alone does not identify
the particular object.

- [GodotObject disposal](https://github.com/godotengine/godot/blob/4.7.1-stable/modules/mono/glue/GodotSharp/GodotSharp/Core/GodotObject.base.cs)
- [Native interop](https://github.com/godotengine/godot/blob/4.7.1-stable/modules/mono/glue/runtime_interop.cpp)
- [Shutdown tracker](https://github.com/godotengine/godot/blob/4.7.1-stable/modules/mono/glue/GodotSharp/GodotSharp/Core/DisposablesTracker.cs)
- [Language shutdown](https://github.com/godotengine/godot/blob/4.7.1-stable/modules/mono/csharp_script.cpp)

The claim-only export run [34528486032](https://github.com/Randroids-Dojo/Cannonball-Vibe/actions/runs/34528486032)
also failed on Linux with SIGSEGV and no captured gameplay markers. It is **not
established as a startup failure**: the actual unmodified package on native WSL
Ubuntu 26.04 emitted its engine banner at 0.281 seconds and all gameplay markers
in one buffered chunk at 4.020 seconds, immediately before clean exit at 4.044
seconds. Official release logging disables flush-on-print. The failed CI process
lived about 4.9 seconds, so a shutdown crash with unflushed output remains plausible.
Ten normal and ten debugger launches under WSL passed; Ubuntu 26.04 is distinct
from CI Ubuntu 24.04. Timing evidence is retained in
`reports/p0-025/linux-diagnosis/stdout-timing.jsonl`.

The candidate routes actual application quit requests (including the window
close notification) through one idempotent coordinator. It defers from native
callbacks to an idle frame, stops processing, awaits every pending chunk read and
telemetry close, then collects and asynchronously drains pending finalizers twice
while the native servers remain alive. Each wait has a ten-second bound. It does
not run on reparenting. The ordinary scene teardown remains intact.

The controlled 32-wrapper probe uses both short weak references to prove the
backlog and resurrection-tracking weak references to check completed disposal.
It also checks that repeated quit requests reuse the same task. Four corrected
derived-package runs passed, with all 32 wrappers finalized and shutdown taking
1542-1550 ms. A normal corrected run took 59.436 ms; an intentional invalid-argument
run retained exit 1. These are diagnostic derived packages, not final reproducible
shipping evidence. The earlier negative experimental DLL was not retained and its
exact hash is unavailable; the original archived package was preserved.

The package's independent engine `--quit-after 1200` frame limit could race the
asynchronous coordinator while idle frames advance. It is removed from smoke
launchers; the unchanged external 120-second process watchdog still fails hangs.
The full M0 front door now requires the queued-finalizer probe and rejects any
native error or leak diagnostic after its success markers.

The Computer Use helper could not connect its native pipe on this host. A prior
hidden-window close attempt did not obtain a target window and is not a passed
window-close test. Deterministic notification coverage and actual close remain
separate claims.

Implementation, exact revision checks and recovery evidence remain in progress.
No human gate applies to this bounded repair. No sedan work or human approval is
claimed by this audit.


## Locked implementation verification

At `d42c23c`, the complete local front door passed all 13 steps: 157 Core tests,
345 map tests (one existing skip), protocol/verifier fixtures, the induced finalizer
scenario, camera interpolation and all 13 starter-speed cases. The finalizer
scenario finalized 32/32 wrappers and recorded 1543.203 ms shutdown without native
diagnostics. The later marker-only verifier addition passes four unit fixtures and
requires the ordinary package to report completed managed shutdown as well.

The first local export could not find .NET templates. Installing the exact pinned
archive corrected that machine dependency. Two Windows builds then compared every
packaged byte and produced the same ZIP SHA-256:
`695c7746a7e2a11db3bf1a942fc367b22d975c4d74f2b95f9c0c375850e23021`.

Candidate export run `34530441904` passed ten Linux native smokes. Its synthetic
merge `6890cabcba3d7ff3303c7e8cf7ad222c5a7a74ae` has the identical source tree
`6ae4a7d98bbd87af5e0382117ae06640e62e210c` as implementation `d42c23c`.
Windows/native final checks and mainline recovery remain pending.
