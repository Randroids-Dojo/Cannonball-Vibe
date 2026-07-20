# P0-013 continental scale and compression closeout

## Outcome

The remaining machine-verifiable P0-013 scale work is implemented. The trip
map now selects a deterministic geometry LOD against a point budget, indexes
route semantics instead of rescanning every connector and exit for every route
edge, batches connected rendered paths, and exposes data-driven 1:1, fixed
ratio, and selective-cruise estimates without changing authoritative distance
or route position.

P0-013 remains `in_progress` only because Q-028 requires the project owner's
trip-map comprehension and accessibility review. This audit does not resolve
Q-001 or choose which run-length mode is the commercial default.

## Scale contract

The official Godot 4.7.1 scale scenario constructs a deterministic synthetic
3,000-mile route with 3,000 ordered edges and three immutable map LODs per
edge. It is a load fixture, not a claim of observed geography or continental
content completion.

On the local Apple M4 Max validation host, the scenario reported:

- automatic LOD: `1`;
- projected points: `15,001` against a `20,000` point budget;
- real route distance: `3,000.000` miles;
- initial projection time: `16.453` ms in the full verification run;
- 1:1 remaining estimate: `80,440.378` seconds;
- fixed 3x remaining estimate: `26,813.459` seconds;
- selective-cruise 3x effective estimate: `26,813.459` seconds.

The fixed and selective estimates preserve the same edge, edge distance,
map position, completed distance, and remaining real distance as the 1:1
projection. Compression is an explicit estimate input; no product default or
world-traversal rule is silently selected here.

## Adversarial review

The scale review found two risks in the first-pass implementation:

- selecting LOD 0 unconditionally could exceed a practical continental draw
  budget even though the serialized package remains within its 16 MB limit;
- scanning the complete connector and exit collections inside every route-edge
  iteration made the projection path quadratic on large graphs.

The implementation now intersects available route LODs, selects the most
detailed one that fits the declared point budget, pre-indexes connectors,
exits, and route identities, and reports the chosen LOD and projected point
count through stable automation state. The Godot canvas joins contiguous edge
segments into bounded polyline batches so pan, zoom, and recenter do not issue
one draw call per route edge.

The review also caught the full-screen summary using `TimeSpan.Hours`, which
wraps after 24 hours. It now displays total hours so an endurance-route ETA is
not truncated.

## Verification

- `DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --filter 'FullyQualifiedName~TripMap'`:
  5 passed, including the 3,000-edge scale and compression-invariance tests.
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/run-scenario.sh --profile trip-map-scale`:
  passed on official Godot 4.7.1 with the metrics above.
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/verify-trip-map.sh --automation auto`:
  passed both official-engine scenarios and all 22 PlayGodot tests.
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/check.sh`: passed with 93 C#
  tests, 78 map-pipeline tests, 12 PlayGodot unit tests, and the official-engine
  smoke.
- `GODOT_BIN=/opt/homebrew/bin/godot ./scripts/capture-scenario.sh
  /tmp/p0-013-trip-map-scale-closeout.avi --trip-map-review`: captured 360
  frames at 1280x720. The inspected frame preserves the map and information
  hierarchy without overlap, and the endurance-mode label fits its panel. AVI
  SHA-256: `171d434d97cd4a914305a251fab9b211f1ecf926a67162638f7908c1f9f4bdc5`.

Cross-platform CI remains required before merge.

## Remaining human gate

Review and answer Q-028 in
[the trip-map handoff](../QUESTIONS_FOR_RANDROID_2026-07-19_TRIP_MAP.md).
