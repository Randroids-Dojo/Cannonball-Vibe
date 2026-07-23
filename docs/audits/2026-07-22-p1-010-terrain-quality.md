# P1-010 continuous regional terrain quality pass

## Outcome

The regional environment now has collision-free terrain ribbons outside the
authoritative road margin. The ribbons follow route elevation, blend relief and
color continuously from mountain to urban edge, ground procedural vegetation
and structures, and remain exactly connected across streamed chunk boundaries.

P1-010 remains `in_progress`. This pass improves the autonomous technical and
visual baseline but does not approve Q-021 art direction, final asset rights, or
Q-022 target-Windows-PC renderer budgets.

## Runtime contract

- The road mesh, road elevation, and road collision remain authoritative and
  unchanged.
- Each direct-route environment chunk adds one render-only terrain ribbon from
  132 to 460 meters on both sides of the road.
- Relief is a stable function of authoritative route distance, so independently
  built chunks share identical boundary vertices.
- Vertex-color blending avoids a material change at biome boundaries.
- Trees, rocks, foothills, mountains, and urban massing now sample the same
  terrain-height function instead of floating at road elevation.
- Local-origin rebases shift the terrain with its owning environment chunk.
- High, balanced, low, and graybox profiles use sample strides 1, 2, 4, and 8;
  the resulting terrain geometry decreases strictly while route and streaming
  semantics remain identical.

## Deterministic measurements

`GODOT_BIN=/opt/homebrew/bin/godot ./scripts/verify-environment-assets.sh
--region representative --all-quality-levels` passed with:

| Profile | Loaded terrain triangles | Loaded ribbons | Maximum seam |
| --- | ---: | ---: | ---: |
| High | 3,656 | 24 | 0.0000 m |
| Balanced | 1,880 | 24 | 0.0000 m |
| Low | 984 | 24 | 0.0000 m |
| Graybox | 536 | 24 | 0.0000 m |

Every profile preserved five review stages, four regions, 49 observed chunk
identities, five local-origin rebases, zero environment collision budget, and
the same route/streaming semantics.

The final balanced renderer capture reported 24 terrain ribbons, 5,640 terrain
vertices, 1,880 terrain triangles, eight shared materials, six shared instance
meshes, zero collision objects, a 5.871 ms maximum environment build, a 14.784
ms maximum total road-visual chunk build, and a 1.312 ms maximum road-collision
build on Apple M4 Max. These are development measurements, not Q-022 production
budgets.

## Renderer review

The official Godot 4.7.1 Compatibility renderer captured 534 frames at
1280x720 and 60 FPS:

`GODOT_BIN=/opt/homebrew/bin/godot ./scripts/capture-scenario.sh
/tmp/p1-010-terrain-quality.avi --fixture representative-corridor
--environment-review --environment-quality=balanced`

Tracked artifact:
[terrain-quality contact sheet](../images/p1-010-terrain-quality-review.png).

Original-resolution inspection confirmed continuous relief in dawn, day,
overcast, night, and stream-boundary scenes. No exposed void, terrain/road
vertical wall, persistent pop, collision interaction, or visible inter-chunk
terrain crack was observed. The broad relief reads more naturally than the
flat baseline while retaining the deliberate low-detail proof-corridor style.

## Remaining limits

- The procedural relief and palette are not production terrain art.
- Occlusion, texture residency, production material count, and GPU budgets
  remain provisional until Q-022 supplies representative Windows hardware.
- Bridge-specific cut/fill art and authored urban landmarks remain future art
  work; the current ribbon does not change bridge or road collision.
- Final vegetation, geology, skyline, weather, and asset-rights approval remains
  part of Q-021.

## Review status

The complete diff was checked for route-authority leakage, accidental collision,
chunk-boundary discontinuity, non-stable seeds, local-origin drift, inverted
quality ordering, unbounded geometry, object grounding, triangle winding, and
unsupported completion claims. The first renderer inspection found that
instances still used road elevation after the terrain ribbon was added; the
placement contract was corrected to use the shared terrain-height function.
The subsequent geometry review found that identical winding on both lateral
sides produced downward normals on one ribbon; side-aware winding now keeps
both surfaces upward-facing. Both findings were corrected before final capture.
No unresolved actionable finding remains at local review time.
