# P0-010 variable-lane generation adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `5cada632adfef0e1f48c8836e7c473c3d9fd21c2`
- Result: no unresolved actionable finding in the implemented mainline slice;
  P0-010 remains in progress because physical branch connector geometry and
  branch prewarming are not yet exercised

## Scope

The review traced the deterministic authored topology overlay through stable
lane-section alignment, RoadChunk visual and collision generation, streaming
and eviction, active-lane targeting, local-origin rebasing, headless topology
checkpoints, a 160.6 mph rigid-body pass, and the deterministic capture from
chase and elevated cameras.

The overlay retains the verified representative corridor package and source
hashes. It replaces only in-memory semantic lane sections on the longest
eligible edge, preserves the two source endpoint lane IDs for existing junction
connectors, and labels the result with authored-override ancestry. It is a
regression fixture, not a claim about observed US 36 lane geometry.

## Findings resolved during review

1. Centering each lane section independently moved stable through lanes when a
   right-hand lane appeared. Section layouts now align recursively by stable
   lane ID and interpolate width, center, and shoulders through bounded tapers.
2. Variable road visuals initially reused fixed-width collision. Road surface,
   paved shoulders, terrain, markings, barriers, scenery placement, and
   trimesh collision now derive from the same lane profile.
3. Continuous interior paint made the highway read as all-solid lanes. Interior
   dividers now use a distance-stable 5-meter dash and 13-meter period while
   road-edge lines remain continuous across chunks.
4. Review placement left the vehicle straddling the road centerline. Review and
   autopilot targets now follow the selected stable lane center without making
   scene transforms authoritative route state.
5. Static checkpoints did not establish high-speed drivability or rebasing.
   The topology profile now follows its 12 settled checks with a 160.6 mph
   rigid-body traversal, two local-origin rebases, and at most one consecutive
   unsupported physics frame.
6. The first guard-barrier implementation applied instance scale in world axes,
   producing cross-road beams. Elevated capture exposed the defect. Scaling the
   local longitudinal basis axis fixed the barrier direction and retained the
   per-segment length.
7. A single chase frame could not establish the shape of every transition. The
   capture now visits all four boundaries and switches deterministically between
   chase and elevated diagnostic views at each waypoint.
8. Fixed diagnostic offsets assumed the selected edge was always long enough.
   The overlay now requires a 1,000-meter source edge and clamps all review and
   traversal offsets to its declared length.

## Residual boundaries

- The fixture proves a mainline entrance-lane addition, auxiliary continuation,
  exit-only split, highway-transfer maneuver role, and lane drops. It does not
  yet contain a physical ramp or diverging highway branch.
- The runtime pass follows a stable through lane. It does not yet traverse an
  actual entrance ramp, exit ramp, or highway-to-highway connector.
- Stream-window loading, collision activation, ordinary eviction, and rebasing
  passed. Probable outgoing branch prewarming and unchosen-branch eviction are
  still pending.
- P0-011 owns interchange route choice and full branch-stream state, but P0-010
  still needs the physical connector-generation fixture required by its own
  acceptance before its ledger status can become `complete`.

## Verification reviewed

- `DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --no-restore --nologo`:
  42 passed.
- `./scripts/run-scenario.sh --fixture variable-lanes --profile topology`:
  12 checkpoints, two-to-four lanes, four transitions, two transition collision
  chunks, 18.9-meter maximum paved width, 160.6 mph, two rebases, one maximum
  unsupported frame, 15.104 ms maximum visual build, 1.050 ms maximum collision
  build, and zero chunk failures.
- `./scripts/capture-scenario.sh /tmp/p0-010-variable-lanes.avi --fixture
  variable-lanes --topology-review`: 360 frames at 60 FPS, four transition
  waypoints, chase and elevated views, SHA-256
  `0e13d53aca03e74e552c0f5eda2112af594671467617e9df0ef8ddc9959b1f17`.
- `./scripts/check.sh`: passed; 42 C# tests, 66 map-pipeline tests, 12
  PlayGodot unit tests, Ruff, doctor, build, and official Godot 4.7.1 smoke.
