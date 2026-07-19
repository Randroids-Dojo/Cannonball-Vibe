# P1-007 route-context adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `5140222dbdb6b234379cc17e851af366e8fa24ed`
- Technical result: no unresolved actionable finding
- Promotion result: approved by the project owner on 2026-07-18

## Scope

The review traced milepoint anchors, roadside markers, route identities, exits,
lane connectors, destinations, and services from semantic records into the
deterministic planner, streamed Godot scene nodes, automation metadata, and the
five-point visual capture. The authored interchange overlay retains recursive
provenance to the locked representative corridor and is not presented as
observed ramp or sign truth.

## Findings resolved during review

1. The first transfer classifier inferred transfer intent from the destination
   ramp identity. An ordinary exit onto a differently numbered local highway
   could therefore be mislabeled. Classification now requires an explicit
   `HighwayTransfer` lane connector; a regression test preserves the CO 93
   ordinary exit.
2. The first renderer exposed lane IDs and route identities only through scene
   metadata. Sign faces now show stable route-shield text and human-readable
   lane guidance while keeping the source IDs queryable.
3. Sign faces were initially oriented away from the approach camera and were
   too small at the declared preview distance. The final boards face the
   approach, use larger deterministic dimensions and typography, and remain
   readable in 1280-by-720 captures from 102 meters.
4. Double-sided `Label3D` text could render from a sign's rear. Route-context
   labels are now single-sided, shadowless, and natively range-bounded. A review
   point completes only after each expected label asserts visible tree state,
   camera-frustum inclusion, positive forward distance, and declared-range
   compliance; empty chunks retain no diagnostic list.
5. The first error path logged the same route-context exception every frame.
   Automation failures now terminate immediately with a single actionable
   error.
6. Multiple exits on the same approach could select the same placement. The
   planner now shifts subsequent signs in deterministic 60-meter increments and
   omits a sign when both separation and the 1.5-second preview cannot fit.
7. Missing exact milepoint data could invite substituting cumulative trip
   progress. The fixture now requests `marker-us36-missing-anchor` without an
   anchor, and runtime validation asserts its omission ID, edge, route identity,
   authored provenance, and exact-colocation reason. No marker value is invented.
8. Remote cold-start runs initially charged route-context dispatch and per-frame
   diagnostic state to an official corridor with no renderable route context,
   then exposed Godot's first script-object binding cost inside the visual mesh
   timer. Empty chunks now allocate no label or automation lists and skip the
   planner. Engine object binding and one cached deterministic semantic plan per
   edge occur before visual timing; route sampling, lane layout, every road and
   terrain mesh, and all actual sign and marker generation remain inside the
   unchanged 50-millisecond budget.
9. Route-context automation IDs and counts originally described cumulative
   observations as loaded scene state. Loaded-state APIs now add and remove IDs
   with streamed chunks, while separately named seen metrics retain cumulative
   scenario evidence.
10. Fuzzy chunk-boundary ownership could duplicate or drop placements near a
    seam. Ownership is now exactly half-open, except that the final chunk owns
    its endpoint, with regression coverage immediately inside both boundaries.
11. The receiving I-25 lane section inherited an eastbound default that
    contradicted its southbound route identity and milepoint. Fixture lane
    directions now derive south, north, or east from the declared identity.

## Residual boundaries

- The signs, shields, posts, roadway, terrain, and background remain graybox
  assets. Production asset fidelity belongs to the later visual milestone.
- The authored fixture proves semantic and rendering contracts, not the future
  checksum-locked geographic validation corpus owned by P0-012.
- Localization, color-vision review, screen-reader equivalents, and final
  typography are outside this slice.

## Verification reviewed

- Route-context scenario: five review points, four markers, one exit sign, one
  transfer sign, two concurrent markers, four distinct mile values, three exact-
  data omissions, six stable automation nodes, 17.224 ms maximum visual build,
  and zero chunk failures.
- Final visual capture: 309 frames, 1280 by 720, 60 FPS, 5.15 seconds, SHA-256
  `4a766ec01b9abfc58adf3d9b3a6a5d743af1a0a6c3b6ee2e66afd400ad5de50f`.
- Full repository gate: 59 C# tests, 66 map-pipeline tests, 12 PlayGodot unit
  tests, Ruff, doctor, build, and official Godot 4.7.1 smoke passed.
- `git diff --check`: passed.

Review artifact: [route-context contact sheet](../images/p1-007-route-context-contact-sheet.png).

## Final project-owner decision

The project owner approved the tracked contact sheet for current-milestone
high-speed route-context readability on 2026-07-18. Production signage realism,
typography, materials, placement, and night legibility remain P1-009 scope.
