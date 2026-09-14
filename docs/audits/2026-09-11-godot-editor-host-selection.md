# Godot editor host selection on the SDK10 workstation

2026-09-11, P1-018. The selected engine, C# target framework, SDK, physics and
performance requirements remain unchanged.

The Windows workstation has only SDK10.0.102 installed. Two identical fresh
copies of the delivered sedan project built without warnings. Running the
repository's Godot import wrapper with `DOTNET_ROLL_FORWARD=Major` then logged
a `System.Runtime, Version=10.0.0.0` assembly-load error despite exiting zero.
The otherwise identical official-default import succeeded. Strict diagnostics
rejected the first run before it could become resource acceptance.
[Actual full-project pair](../../reports/p1-018/final34/workflow-import-diagnostic-01/evidence.json).

Separate actual game-host controls observed .NET8.0.23 with `Major` and
.NET10.0.2 with the official default. Those are host versions; the game still
targets .NET8. The packaged runtime is measured separately. Remote jobs install
SDK8 as well as SDK10, so the local reproduction does **not** prove that those
jobs would necessarily fail. Their actual platform evidence remains required.
[Environment investigation](../../reports/p1-018/runtime/execution-environment-01/evidence.json).
[Installed runtimeconfig and official-source review](../../reports/p1-018/research/dotnet-host-policy-01/review.json)
records the official `LatestMajor` default and its separate target-framework boundary.

`scripts/godot.sh` now removes only the incompatible `Major` override when an
editor, import, build-solutions or export flag occurs in the engine arguments.
It stops at `--`, preserves other override values, and keeps normal game/test
host settings, exact engine validation and the GC nursery policy. The unsigned
builder invokes this same wrapper from its committed source copy, preserving
the resolved executable, target runtime identifier and export arguments.

All25 argument/environment controls passed, including flags after `--`,
other overrides, exact forwarding and rejection of the wrong engine. A fresh
full-project import passed under inherited `Major`; three native controls still
used .NET8.0.23. Independent QA replayed the controls and reviewed the actual
logs and copied inputs. The full local front door and26-comparison/20-negative
delivered asset gate then passed under the declared job environment.
[Wrapper verification](../../reports/p1-018/final34/editor-wrapper-correction-01/evidence.json),
[independent review](../../reports/p1-018/qa/editor-wrapper34-reviewed-01/review.json),
[full local gate](../../reports/m0/p1-018-final34-02/summary.json),
[delivered asset gate](../../reports/p1-018/source34-delivered-gate-03/evidence.json).

This repair establishes editor-host selection and preserves the tested native
host behavior. It does not substitute for final native footage, resource counts,
packaged execution, performance measurements, remote platform results or human
approval. Original failures, unsuccessful hypotheses and retry logs remain
retained in the task's evidence archives.
