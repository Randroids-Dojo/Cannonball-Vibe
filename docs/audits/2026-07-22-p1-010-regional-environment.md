# P1-010 regional environment technical and visual review

## Outcome

P1-010 now has a renderer-backed, deterministic Colorado proof-corridor
baseline. It streams collision-free regional scenery alongside authoritative
road chunks, preserves local-origin behavior, and offers high, balanced, low,
and graybox quality profiles with equivalent route and streaming semantics.

The delivery-ledger status is `in_progress`. Final regional art direction,
readability, production asset rights, and target-PC renderer budgets remain the
Q-021/Q-022 human gate; the implementation does not claim those approvals.

## Implemented contract

- Four route-derived regions: mountain, foothill, plains, and urban edge.
- Deterministic procedural placement seeded by content version, chunk identity,
  region, and kit version.
- Near, midground, and distant layers use shared materials, shared meshes, and
  one `MultiMeshInstance3D` per layer per route chunk.
- The environment layer creates no collision objects and cannot alter route
  elevation, road collision, vehicle physics, or save/navigation semantics.
- Environment chunks are attached and evicted with the corresponding direct
  route chunk and shift through every local-origin rebase.
- Quality degrades in ordered instance budgets while preserving all four
  regions, five review stages, semantic nodes, and collision-free behavior.
- A project-original rights registry covers the procedural baseline. Any future
  third-party replacement must add its own rights record.

## Deterministic verification

`GODOT_BIN=/opt/homebrew/bin/godot ./scripts/verify-environment-assets.sh
--region representative --all-quality-levels` passed all four profiles. Each
profile reported five stages, four regions, 49 observed chunks, five rebases,
and equivalent collision-free route/streaming semantics.

`GODOT_BIN=/opt/homebrew/bin/godot ./scripts/run-scenario.sh --fixture
representative-corridor --profile environment-streaming
--environment-quality=balanced` passed with:

- 49 observed regional chunks across the traversal;
- seven shared materials and six shared meshes;
- five deterministic review stages covering dawn, day, overcast weather,
  night, and a stream-boundary return;
- zero environment collision objects;
- 2.857 ms maximum measured environment build time on this run; and
- 14.728 ms maximum total road-visual chunk build time and 1.212 ms maximum
  collision build time.

The renderer capture command produced 533 frames at 1280x720 and 60 FPS using
Godot 4.7.1 Compatibility/OpenGL on Apple M4 Max:

`GODOT_BIN=/opt/homebrew/bin/godot ./scripts/capture-scenario.sh
/tmp/p1-010-regional-environment.avi --fixture representative-corridor
--environment-review --environment-quality=balanced`

Tracked review artifact:
[regional environment contact sheet](../images/p1-010-regional-environment-review.png).

## Visual inspection

The capture was inspected at original resolution and as the tracked six-frame
sheet. It shows a continuous roadway against readable dawn mountains, daylight
foothills, muted overcast plains, a low-cost urban-edge night skyline, and the
daylight stream-boundary return. No exposed void, road/environment vertical
seam, persistent pop-in, or scenery/road collision interference was observed.

The current language is deliberately a stylized technical baseline. Mountain
profiles, vegetation silhouettes, urban massing, terrain materials, weather,
and transition composition need a later art-quality and realism pass after
Q-021. The capture is evidence that the architecture works, not final art.

## Full repository gate

`GODOT_BIN=/opt/homebrew/bin/godot ./scripts/check.sh` passed:

- .NET build with zero warnings;
- 93 C# tests;
- 78 map-pipeline tests;
- 12 PlayGodot unit tests;
- Python lint;
- official Godot 4.7.1 smoke traversal; and
- the M0 doctor/toolchain checks.

## Independent adversarial review

The implementation and capture were reviewed for authority leakage, hidden
collision, nondeterministic seeding, local-origin drift, quality-profile
semantic drift, unbounded node growth, unsupported completion claims, and
visual discontinuities.

One issue was found and fixed before publication: the original 520-frame movie
ended after the four region/lighting scenes but before the explicit
stream-boundary stage completed. The default was raised to 620 frames; the
scenario now exits naturally after all five stages, and the replacement capture
contains 533 frames plus the final success marker.

No unresolved correctness or regression finding remains. The open items are
the declared human art/rights review and representative Windows performance
ratification, documented in
[the focused question handoff](../QUESTIONS_FOR_RANDROID_2026-07-22_REGIONAL_ENVIRONMENT.md).
