# P0-021: the package-build stage, one segment first

Date: 2026-09-06. Related: P0-021, ADR-0019, ADR-0024, ADR-0026.

## Where the chain stands

Sixteen cache-independent stages are locked under `data/routes/continental/`,
ending at `collision-chunk-lock.v1.json` (status
`collision_ribbons_locked_package_pending`: 26 hosts, 5,109 chunks, 815,044
triangles, zero open seams). `scripts/validate-continental-route.sh` threads
every upstream digest and ends at `validate-continental-collision`. Nothing
yet turns a locked segment into the sharded runtime package the game loads
through `--route-package=`, and none of the runtime paths the ledger reserves
for P0-021 (`src/Cannonball.Core/Routes/Continental/`,
`game/World/Continental/`, `game/Automation/ContinentalRouteScenario.cs`,
`scripts/run-continental-scenario.sh`) exist. In play the route still ends at
the 25-mile Boulder fixture.

## This slice

Add `build-continental-package --segment <id> --output DIR` to the
map-pipeline CLI. It reads the locks the chain already committed (directed
route and conditioned profile for the centreline and elevation, westbound
carriageway and lane topology for widths, junction geometry and endpoint
connectors for the joins, collision chunks for the chunk boundaries) and
emits a package through the existing `write_sharded_package` writer, so the
ADR-0019 ceilings (64 MB root, 16 MB chunk) are enforced by the same code
the fixture build uses. The command threads the upstream lock digests the
way the `validate-continental-*` commands do and records them in the
package provenance.

One segment first, `i70-denver-to-cove-fort`: the largest single segment,
roughly 500 miles against a 25-mile fixture, on the Colorado ground the
representative corridor already exercises. A one-segment build measures the
per-mile root cost before the whole 6,294-mile westbound chain is attempted
and keeps every failure attributable to one segment. The same command then
takes `--all-segments`.

`scripts/run-scenario.sh` gains a `continental-i70` fixture that builds the
segment package and launches the game on it, so the segment can be driven
and smoked like the fixtures. The known NHPN jitter site on this segment
(`max_sustained_grade` -43.979 % over a 1,000 m window, 13.78 m lane easing
departure) is documented upstream and will be visible in-game; it is not
this slice's to fix.

## Not in this slice

The other eleven segments, the ADR-0019 double-build byte comparison, the
coast-to-coast walker and bot gates, the continental runtime scenario and
save-resume across segment joins. Each follows on the proven path.
