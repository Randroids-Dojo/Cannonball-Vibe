# P0-010 variable-lane generation adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `cc1f2f5f8edf0d6b2db7d3bba443f633a94b3465`
- Result: no unresolved actionable finding; local acceptance and all required
  remote gates passed

## Scope

The review traced the deterministic authored topology overlay through stable
lane-section alignment, RoadChunk visual and collision generation, streaming
and eviction, active-lane targeting, local-origin rebasing, headless topology
checkpoints, a 161.1 mph rigid-body pass through explicit Entrance and
HighwayTransfer successors, probable-branch prewarming and eviction, and the deterministic capture from
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
9. Edge crossing still selected a successor lane from the old section-local
   center calculation. Runtime projection now uses the same aligned geometry
   profile as rendering and follows the explicit lane-to-lane connector when an
   edge changes; the regression observes both Entrance and HighwayTransfer.
10. Probable branch IDs were verified by the package reader but ignored by the
    stream window. Direct visual chunks now expand one bounded prewarm level;
    the authored fixture loads one far verified chunk and proves its later
    eviction without enabling far collision.
11. Independently generated edge ribbons exposed a visible wedge at the sharp
    outbound heading change. A streamed junction seam now fills the paved and
    lane surfaces and activates matching collision only while both adjacent
    collision chunks are active.
12. A first attempt to link same-side barriers across that heading change
    crossed the roadway. The unsafe link was removed; barriers remain edge-local
    until P0-011 has branch-side classification.

## Residual boundaries

- The authored fixture proves generator and streaming behavior without claiming
  that NHPN contains observed lane or interchange geometry.
- Its probable branch is a checksum-verified far-chunk surrogate that isolates
  prewarm and eviction behavior. P0-011 owns true alternative route choice,
  diamond and directional or cloverleaf fixtures, and unchosen branch state.
- Barriers remain edge-local at junction seams. P0-011 must classify branch
  inside/outside boundaries before curved connector guardrails are generated.

## Verification reviewed

- `DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --no-restore --nologo`:
  42 passed.
- `./scripts/run-scenario.sh --fixture variable-lanes --profile topology`:
  12 checkpoints, two-to-four lanes, four transitions, two transition collision
  chunks, 18.9-meter maximum paved width, explicit Entrance and HighwayTransfer
  successors, one branch prewarm and eviction, 161.1 mph, four rebases, one
  maximum unsupported frame, 14.093 ms maximum visual build, 0.957 ms maximum
  collision build, and zero chunk failures.
- `./scripts/capture-scenario.sh /tmp/p0-010-variable-lanes.avi --fixture
  variable-lanes --topology-review`: 480 frames at 60 FPS, six connector and
  transition waypoints, chase and elevated views, SHA-256
  `2ee366bce28639b83f987f7c34ac31f6c7ebcf4f3c8dc7901823698484b192b4`.
- `./scripts/check.sh`: passed; 42 C# tests, 66 map-pipeline tests, 12
  PlayGodot unit tests, Ruff, doctor, build, and official Godot 4.7.1 smoke.
- Protected PR gates: Linux and Windows M0, Linux, Windows, and macOS
  PlayGodot, reproducible exports, and Linux and Windows clean-machine smoke all
  passed on PR #20. The first macOS cold start measured 51.737 ms against the
  unchanged 50.000 ms initial chunk budget; an unchanged rerun passed, so the
  production budget was retained.
- CodeRabbit reached its temporary review limit without producing a review.
  This document is the repository adversarial-review fallback required by the
  delivery practice; it found no unresolved actionable issue.
