# P1-009 structures and lighting adversarial review

- Reviewed implementation revision: `cc80e02a086328382663212ee489fff27bb67cf2`
- Comparison base: `origin/main` at `2372aacfb69dca0d8814fd5b384552d5055b583f`
- Scope: grade-separated placement derivation, modular bridge/overpass assembly,
  origin-rebase behavior, collision ownership, production/graybox equivalence,
  daylight/night automation, renderer capture, and completion claims
- Result: pass for this bounded technical slice; P1-009 remains `in_progress`

## Review method

The review traced the representative fixture's validated segment intersections
into structure placements, the shared `RoadVisualKit`, `WorldStreamer`
configuration and rebases, the road-visual scenario, profile output, aggregate
shell verification, and the renderer capture. It challenged whether structures
were hard-coded to edge names, whether one crossing was being double-counted,
whether visual supports could take over road collision, whether unloaded chunks
could invalidate a review image, whether graybox used the same generator, and
whether the ledger claimed more than the fixture proves.

## Findings resolved before acceptance

1. The first contract expected separate bridge and overpass objects even though
   the fixture contains one validated grade-separated crossing. The contract now
   reports the two honest views of that single structure: one bridge deck for the
   upper route and one overpass opening for the lower route.
2. The first dedicated structure camera ran after the route-context tour had
   rebased the world and unloaded the bridge's road chunk. The bridge was aligned
   correctly but looked detached over the terrain backdrop. The review now
   returns to the structure's exact upper-edge distance, waits for the streamer
   to settle, and frames it only after its road context is loaded.
3. A road-visual run could have finished before lighting coverage. Final profile
   acceptance now requires both declared lighting stages to finish after all six
   route-context waypoints.
4. Structure meshes initially extended the kit without changing its semantic
   version. The kit is now `colorado-freeway-v2`, and the profile derives its
   nine-mesh total from the shared collection.
5. The review capture's old 360-frame default could stop before the post-tour
   structure stages. Road-visual review now reserves 600 frames and completed in
   555 frames at 60 FPS.

## Invariants confirmed

- Structure IDs derive from sorted upper/lower route relationships and detected
  grade-separated geometry; rendering does not branch on fixture edge names.
- The placement records projected position, direction, upper-edge distance,
  width, span, and measured vertical clearance. The representative crossing
  retains its validated 8.0-meter clearance.
- The structure root and all ten child parts carry unique stable automation IDs
  and the same kit version. No structure node is a collision object; streamed
  road chunks remain the authoritative driving collision.
- Local-origin rebases shift the structure set with road chunks and junction
  seams. The final renderer review returned from a 1.2-kilometer origin to the
  700-meter bridge target with nine road chunks and four collision chunks loaded.
- Production and graybox profiles resolve identical counts: 18 materials, nine
  meshes, 11 retroreflective materials, one bridge deck, one overpass opening,
  11 structure nodes, and two lighting stages.
- Fixture derivation is deliberately explicit. This slice proves the reusable
  runtime placement and rendering contract, not automatic extraction of bridge
  structures from every future production map source.

## Verification reviewed

- `./scripts/verify-road-assets.sh --all-topology-fixtures`: passed two visual
  profiles and two topology fixtures, including all four interchange plans and
  14 connectors.
- `./scripts/run-scenario.sh --fixture representative-interchanges --profile road-visual`:
  passed six route-context waypoints, the bridge/overpass structure contract,
  and both lighting stages.
- `./scripts/capture-scenario.sh /tmp/p1-009-structures-lighting-v4.avi --fixture representative-interchanges --road-visual-review`:
  passed with 555 frames at 1280 by 720 and 60 FPS.
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/check.sh`: passed doctor,
  build, 93 C# tests, Ruff, 78 map-pipeline tests, 12 PlayGodot tests, and the
  official Godot 4.7.1 smoke scenario.
- `git diff --check` and delivery/evidence JSON parsing: passed.

Review artifact:
[structures and lighting contact sheet](../images/p1-009-structures-lighting-review.png).

## Remaining boundary

Q-024 remains the human art-readability, visual-quality, and rights gate. Q-022
still owns the target-PC and quantitative renderer budgets. Production regional
terrain and furniture, weathering and decals, exact sign typography and shield
silhouettes, production-source bridge semantics, high-speed pop-in measurements,
and final rights records remain open. No new owner question was created because
those unresolved decisions are already durable in the question ledger.
