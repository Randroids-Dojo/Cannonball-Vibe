# P0-011 interchange routing adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `e6dc4878b1397a8a39a8ff3824ebaf6724908298`
- Result: no unresolved actionable finding; local acceptance and full repository
  verification passed

## Scope

The review traced route-choice metadata from semantic graph records into
explicit edge, lane, and connector plans; verified checksum-backed in-memory
fixture chunks; inspected branch prewarming and eviction; followed runtime lane
state through every connector; and round-tripped selected plan, active
connector, and branch-stream state through schema-2 saves and schema-1
migration.

The representative fixture is an authored regression overlay with recursive
ancestry to the locked corridor package. It proves the route and runtime
contracts without presenting its ramp, lane, exit, or destination geometry as
observed NHPN truth.

## Findings resolved during review

1. Runtime projection originally searched every plan edge and could snap onto
   a geometrically nearby future branch. Explicit plans now project only onto
   the current edge and bounded immediate successor, reject projections more
   than 25 meters from the roadway, and retain multi-edge connector accounting
   as a defensive invariant.
2. Nearest-lane geometry could silently replace the lane selected by an
   explicit route plan. Stable lane identity now remains authoritative until a
   validated connector changes it, and review placement explicitly establishes
   the requested lane.
3. A single physics update could cross more than one short route edge while
   recording only the final connector. Runtime traversal now walks and validates
   every intervening connector and lane successor.
4. Coincident edge endpoints produced a zero-area junction collision mesh.
   Junction seams now bridge 0.35 meters along both edge tangents, retaining
   visible and physical continuity without inventing a shortcut.
5. The first fixture used piecewise-linear ramp headings that launched the
   rigid body at corners. Sampled cubic ramps now preserve entry and merge
   tangents while retaining the 8-meter overpass separation.
6. The first route-choice harness completed plans before the retention window
   could evict the unchosen branch. It now settles at the route end and proves
   all four prewarmed branch chunks are removed.
7. Global nearest-edge projection briefly accepted a transfer while the vehicle
   was roughly 295 meters lateral from the destination highway. The bounded
   projection guard now makes such a false transition impossible; the final
   profile reports zero unsupported frames.
8. Synchronously waiting on asynchronous save I/O under Godot's main context
   deadlocked the first resume comparison. The deterministic automation round
   trip now runs its repository I/O away from that context and completes nine
   comparisons.
9. Schema-1 saves lacked navigation state. Schema 2 adds an explicit empty
   migration and tests both legacy upgrade and full navigation round trip.
10. The fixture initially needed filesystem-only chunk loading. The shared
    source contract now supports immutable in-memory payloads with the same
    byte-count, SHA-256, schema, content-version, and FlatBuffer validation.

## Residual boundaries

- P0-012 owns the broader checksum-locked geographic interchange corpus and
  intentionally invalid topology mutations.
- P1-007 owns route-context visuals such as exit signs and mile markers.
- Production vehicle, road, barrier, terrain, and background assets remain
  later art and rigging work; this slice validates graybox routing and collision.
- `dotnet format --verify-no-changes` still reports pre-existing indentation in
  untouched `RouteSemanticsTests.cs` lines 442-449. The P0-011 diff passes
  `git diff --check`, and the repository's required check does not include that
  existing formatter debt.

## Verification reviewed

- `./scripts/run-scenario.sh --fixture representative-interchanges --profile
  route-choices`: three plans, 12 connectors, four maneuver classes, four
  branch prewarms and evictions, nine save/resume comparisons, one
  grade-separated crossing with 8-meter clearance, one parallel carriageway
  pair, zero self-intersections, zero shortcuts, zero unsupported frames,
  13.738 ms maximum visual build, 1.154 ms maximum collision build, and zero
  chunk failures.
- Focused route, save, and verified-memory-source tests: 25 passed.
- `./scripts/check.sh`: passed; 48 C# tests, 66 map-pipeline tests, 12 PlayGodot
  unit tests, Ruff, doctor, build, and official Godot 4.7.1 smoke.
- `git diff --check`: passed.

CodeRabbit is not required to establish the local result. If remote review is
rate-limited or times out, this document is the repository adversarial-review
fallback required by the delivery practice.
