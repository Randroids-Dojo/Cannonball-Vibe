# P1-018 completed spring-arm observations

2026-09-12. Scope recorded before canonical integration. The existing sedan
claim is draft PR144, branch `feat/P1-018-endurance-sedan`. The live red-main
query returned no issues and the open-PR inventory contained only PR144 before
this scope addition. The lead owns governance and contracts; the runtime agent
owns the six implementation destinations listed below. Human gates are unchanged.

The declared macOS PlayGodot suite failed on commit
`11d80201e79712dd10ac203a982fc1765dded7cd` while comparing the completed native
spring-arm hit with a newer requested length. The recorded hit was
7.50184917449951 m and current request 7.50158739089966 m. The failure is retained
in `reports/p1-018/runtime/macos-ci35-triage01/`; it is not a passing Mac run.

This correction observes the requested and hit lengths from the same completed
native physics cast. Official Godot4.7.1 dispatches its internal physics callback
immediately before the ordinary physics callback for the same node. The existing
debug automation guard selects a small SpringArm3D subclass that reads the
completed pair in the latter callback. Normal gameplay retains SpringArm3D.
There is no new collision query, camera transform, physics priority, requested
length, collision mask, margin, shape, FOV or authoritative state change.

Owned implementation paths:

- `game/Camera/ChaseCameraRig.cs`
- `game/Camera/SpringArmCastObserver.cs`
- `game/Camera/SpringArmCastObserver.cs.uid`
- `automation/playgodot/tests/test_camera_handling.py`
- `automation/playgodot/tests/test_camera_cast_state.py`
- `scripts/check.sh` (one additional unit-test selection argument)

Acceptance requires complete-pair identity, generation, frame and lifecycle
invalidation evidence; malformed/stale observations must reject. Reset, tree
exit/reentry and disabled native processing must immediately invalidate published
automation state. The test keeps its existing timeout and other assertions.
The original and proposed rigs must produce the same physical camera positions
and native request/hit values in the controlled official-engine fixture. Builds
without the debug automation guard must retain the original native arm.

The frozen reports-only proposal is
`reports/p1-018/runtime/macos-camera26-fix01/proposal04.patch`, SHA256
`9067a074a86face6963cbc4d7eab10df893893d119a526f336dadfe3e9cb4267`.
Its `INTEGRATION.md`, `review01.json` and `inventory01.json` record source hashes,
official source references, 19 native fixture stages, factory controls, negative
tests and retained failures/retries. These support implementation selection only.
Canonical verification must include the focused Python tests, C# build, full
`scripts/check.sh` and ordinary PlayGodot platform suites, including macOS.

The separate StringName/PagedAllocator/mutex messages recorded after macOS
launcher termination are outside this observation correction. Do not claim their
resolution, a new Mac pass, final sedan delivery or any human approval from the
fixture results.
