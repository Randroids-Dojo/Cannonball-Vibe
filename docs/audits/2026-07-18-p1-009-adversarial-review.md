# P1-009 highway-kit adversarial review

- Reviewed revision: `4e12f1b854503f7062861e5bdf642f251eb967e9`
- Comparison base: `origin/main`
- Scope: procedural road materials and meshes, route-context sign hierarchy,
  semantic nodes, stream-lifetime evidence, scenario/capture modes, production
  and graybox profiles, topology gates, documentation, and completion claims
- Result: pass for the recorded technical baseline with no unresolved
  actionable finding

## Review method

The review traced the shared `RoadVisualKit` into each streamed `RoadChunk`,
through unload and reload behavior, route-context placement, the five-waypoint
renderer review, and both command-line profiles. It separately challenged
fixture selection, early-exit conditions, cumulative versus loaded metrics,
sign-node identity, resource-count assertions, topology and gore coverage,
shell failure propagation, graybox equivalence, and ledger/evidence claims. The
tracked contact sheet was inspected at original resolution.

## Findings resolved before acceptance

1. The first road-visual profile required gore to appear on the selected
   highway-transfer route itself. That mixed two distinct fixture contracts and
   caused a false timeout even though the variable-lane fixture generated gore.
   The profile now validates the kit and signage across the transfer plan; the
   aggregate verifier separately requires the dedicated topology/gore scenario.
2. Shared resource totals were initially returned as bare numeric properties,
   making the check circular. The kit now owns explicit material, mesh, and
   retroreflective-resource collections and derives the reported totals from
   those collections.
3. Auxiliary sign labels had stable automation IDs but did not carry the kit
   version metadata used on their parent and mesh nodes. Every label now uses
   the same semantic-marker helper as the rest of the visual hierarchy.
4. A current-chunk snapshot could lose proof after a review waypoint unloaded.
   The streamer now records each unique chunk contract and its visual counts
   once, while ordinary loaded route-context APIs remain correctly scoped to
   current scene state.

## Invariants confirmed

- Production and graybox profiles change visual resources without changing
  route topology, sign semantics, automation IDs, physics, collision, or saves.
- Main guide faces remain green with white hierarchy; exit-only panels are
  yellow; services use separate blue panels; US and Interstate references use
  distinct procedural silhouettes.
- Seven observed chunks resolved all required road-visual nodes and kit-version
  metadata. The representative pass observed 546 reflectors, 175 median-barrier
  segments, 175 guardrail segments, four shields, and two service panels.
- Variable topology still proves two-to-four lanes, four transitions, gore,
  entrance and highway-transfer movements, branch streaming, and rebases. All
  three representative interchange plans and twelve connectors pass.
- `set -o pipefail` keeps scenario failures authoritative even though the
  aggregate script also records output through `tee` and checks success markers.
- The ledger and evidence remain `in_progress`; neither fixture output nor the
  renderer sheet is presented as final production art or regulatory compliance.

## Verification reviewed

- `./scripts/verify-road-assets.sh --all-topology-fixtures`: production and
  graybox visual profiles, variable-lane topology/gore, and all representative
  route choices passed.
- Road-visual renderer review: 309 frames at 1280 by 720 and 60 FPS, with every
  declared route-context label inside its visibility envelope.
- Full repository gate: 62 C# tests, 66 map-pipeline tests, 12 PlayGodot unit
  tests, Ruff, doctor, build, and official Godot 4.7.1 smoke passed.
- `git diff --check`: passed.

Review artifact:
[P1-009 highway-kit contact sheet](../images/p1-009-highway-kit-review.png).

## Remaining boundary

Q-024 is not silently approved. Production bridges and overpasses, regional
terrain and furniture, exact sign typography and shield shapes, weathering,
decals, complete rights records, daylight/night high-speed coverage, and Q-022
renderer budgets remain open. The current kit is a deterministic modern
technical baseline, not a claim of final art or MUTCD/CDOT engineering
compliance.
