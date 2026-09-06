# P1-010: the ground either side of the road collides

Date: 2026-09-06. Related: P1-010, ADR-0023.

## What was wrong

The only collider in the world was the paved ribbon (lanes plus shoulders)
and the route-start barrier. The 120 m terrain margin either side of the
paved edge, the junction terrain quads and the regional ribbons were
mesh-only. A wheel that crossed the shoulder found nothing, the car fell,
and `CannonballVehicle` put it back on the road once its local Y passed
-20 m. That plane was relative to the rebased local origin rather than to
the road, so on a descending route the fall lasted far longer than the two
seconds it implied and on a climbing route it could fail to fire at all.

While under the ground the player saw the underside of the double-sided
ground surface and the conifer needle cards, which read as tall grass.

## What changed

- `RegionalTerrainRibbon.BuildGroundCollisionMesh` builds a collider for a
  run of road stations from each paved edge out to the ribbon's 460 m
  outer band, on the same analytic surface (`SurfaceHeight`) the ribbon
  draws: flat at the near-ground offset to 132 m, rising through the
  middle band to the outer hills. `RoadChunk` adds it as a second
  `CollisionShape3D` named `TerrainCollision` beside the paved trimesh
  whenever the chunk's collision is active, and `JunctionSeam` builds the
  same from its two stations, with the seam's route distances supplied by
  the streamer so its outer rows meet the neighbouring chunks' rows.
  Twelve triangles per segment, a fraction of the paved trimesh.
- Every collider triangle winds clockwise seen from above, which Godot
  treats as the front face. A concave collision shape ignores back faces
  for ray casts by default and the suspension rays cast downward; the
  first off-road drop in the new scenario fell straight through the margin
  while it wound the other way, which is how that was found. The visual
  margin now winds the same way and both terrain shapes enable
  `BackfaceCollision`, so a collider folded on the inside of a tight curve
  still holds the car from either winding.
- One constant, `RegionalTerrainRibbon.NearGroundOffsetMeters` (-0.18 m),
  now sets the road terrain margin, the junction terrain quads and the
  inner plateau of the regional ribbon, which previously sat at -0.34 m
  with the junction quads at -0.16 m. Every near-layer tree and rock
  inside 132 m was anchored 0.16 m below the surface that was drawn, and
  there was a 0.16 m step at the ribbon seam. Both are gone.
- The recovery depth is measured from the tracked road point:
  `CannonballVehicle.FallRecoveryDepthMeters` is 8 m below
  `TargetRoadPoint.Y`. A genuine fall is caught in under 1.3 s wherever
  the route is, and a car on the outer hills 460 m out is still well
  above it.
- `OffRoadGroundScenario` (`--off-road-ground-profile`,
  `./scripts/run-scenario.sh --profile off-road-ground`,
  `./scripts/verify-off-road-ground.sh`) checks the ground contract, then
  drops the car from 1 m onto the ground at 8 m, 100 m and 300 m beyond
  the paved edge on each side of the official corridor 45 m from the
  start, and requires four grounded wheels, no reset, and a resting height
  within 0.45 m of the analytic surface plus the static ride height.
- The ground contract, that every collision chunk and junction seam
  carries its terrain collider, is checked at the end of every
  `--smoke-test` run, so the M0 gate fails a regression on every PR.

## Why the collider reaches 460 m and not 120 m

The first version collided only the 120 m drawn margin. All four drops
passed, then a rendered PlayGodot drive (production Hero GT, graybox
environment, hold accelerate then hold steer right) left the paved edge
at 56 m/s with the balanced profile's 0.11 high-speed steering authority
and ended with the input conditioner reporting `last_suppression_reason
= reset`: at that speed and exit angle the car crossed the 120 m margin
in about two seconds, ran off its outer edge onto the visual-only ribbon
and fell to the recovery depth. With the collider on the ribbon surface
out to 460 m the same drive ends at rest on the ground, far from the
road, with `suppression_sequence = 0` and no reset.

## What did not change, and why

The ground shader stays double-sided. A first version of this slice wound
every ground mesh to face up and switched `ground.gdshader` to `cull_back`,
with the contract reading the generated normals back. The contract failed
on the first regional ribbon of the official corridor with a triangle
whose normal was (0.13, 0.05, 0.99): the ribbon's 260 m and 460 m offset
rows fold on the inside of curves and its short end segments produce
near-vertical slivers. Back-face culling would open holes in the
midground there, and tight interchange ramps fold the 120 m margin the
same way. Back faces cost nothing while the camera is above the ground,
and the ground now collides, so the underside is not reachable in play.
Culling it would need the ribbon rebuilt so its rows cannot cross, which
is a P1-010 geometry change with visual risk and is not attempted here.

Authoritative route elevation and the paved collision ribbon are unchanged.

## Verification

Windows 11 Pro 10.0.26200, official Godot 4.7.1.stable.mono.official.a13da4feb,
.NET SDK 10.0.102, official corridor package, headless:

| Probe | Beyond paved edge | Resting error | Grounded wheels | Resets |
|---|---|---|---|---|
| right-verge | 8 m | 0.060 m | 4 | 0 |
| right-margin-outer | 100 m | 0.015 m | 4 | 0 |
| right-middle-band | 300 m | 0.053 m | 4 | 0 |
| left-verge | -8 m | 0.032 m | 4 | 0 |
| left-margin-outer | -100 m | 0.023 m | 4 | 0 |
| left-middle-band | -300 m | 0.036 m | 4 | 0 |

Ground contract at the route start: 4 collision chunks, 4 with terrain
collision, 3 collision seams. The plain M0 smoke passed with the contract
line, `max_collision_build_ms=2.131` against the 40 ms budget.

Before the winding fix the same scenario reported the right-verge drop
falling through with one reset at frame 196, which is the failure this
scenario exists to catch.

See `evidence/M5/P1-010-off-road-ground.json`.
