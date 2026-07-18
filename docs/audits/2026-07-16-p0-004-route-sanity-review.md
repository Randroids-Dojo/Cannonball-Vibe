# P0-004 representative route sanity review

- Date: 2026-07-16
- Reviewer: project owner
- Decision: rejected; human gate remains open
- Task: P0-004
- Source revision: `84a9f24a0b5c1a4b40cee311ae0c12d1b9efa9ef`
- Capture time: `2026-07-17T03:07:27Z`

## Review artifact

The review used a deterministic 60-second Godot 4.7.1 capture at 1280x720 and
60 FPS with content version `route-v3-7b29691bf42eabf1`. The scenario completed
3,600 frames, loaded and verified all four fixture chunks through streaming
lookahead, reported zero chunk failures, and passed its packaged-content smoke.
It did not prove that the vehicle crossed every chunk boundary.

The capture loaded route package
`.tools/scenarios/official-corridor/route_graph-b2ada13ecc634df150f24a16ee3ae9b3499e36daf867b855861fe5a73b939f54.cbrg`
with SHA-256
`8ee287814e68d6de3418c9a1469cad9ffd252a25e600859077e4bcf4c52bf485`.

```bash
GODOT_BIN=.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot \
  CANNONBALL_CAPTURE_FPS=60 CANNONBALL_CAPTURE_FRAMES=3600 \
  ./scripts/capture-scenario.sh /tmp/p0-004-route-review.avi \
  --short-corridor-soak
```

| Artifact | Review path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Original MJPEG capture | `/tmp/p0-004-route-review.avi` | 96,390,500 | `8cbdcf43e43c9f7557ca91fa28101c711099d7efe57ed6c1ccc383b9089d10e5` |
| H.264 review copy | `/tmp/p0-004-route-review.mp4` | 1,654,166 | `f222da5732e973b76caf5dc9760f08186cfd24e0ae3bef879102d6e280660588` |
| Six-frame contact sheet | `/tmp/p0-004-route-review-contact-sheet.png` | 71,712 | `662156613d3bba70f93e70eb007141bb1aaa431fbd4047a798b1f7677a60c96c` |

The generated visual artifacts are content-addressed review outputs and are not
committed source files. The original capture command, dimensions, duration, and
all output hashes are recorded here. The H.264 copy and contact sheet were
derived with FFmpeg 8.1; their exact bytes are identified by hash rather than
claimed to be reproducible across toolchains.

```bash
ffmpeg -y -v error -i /tmp/p0-004-route-review.avi \
  -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p -an \
  -movflags +faststart /tmp/p0-004-route-review.mp4

ffmpeg -y -v error -i /tmp/p0-004-route-review.avi \
  -vf 'fps=1/10,scale=640:-1,tile=3x2' -frames:v 1 \
  /tmp/p0-004-route-review-contact-sheet.png
```

These paths are ephemeral local review outputs with no durable publication URL.
The review decision and content hashes are durable; regeneration is required to
inspect the exact scenario again.

## Rejection findings

The project owner selected rejection after reviewing the capture and contact
sheet. The next candidate must correct and prove all of the following:

1. The roadway disappears from most sampled frames.
2. The vehicle appears suspended against empty space after the opening view.
3. Terrain and scenery are insufficient to judge route placement or seams.
4. The capture does not make the reconstructed route geographically
   recognizable, so obvious map mistakes cannot be ruled out.

The technical streaming evidence remains valid, but it cannot substitute for
the rejected visual gate. Diagnose camera framing, streamed road geometry, and
fixture traversal behavior before generating the next review candidate. A
short-fixture recapture can clear the render-integrity defect only. A separate
longer locked corridor capture is required to clear the representative map
sanity gate or claim representative long-route geography.

## Short-fixture repair candidate

- Capture started: `2026-07-17T04:47:51Z`
- Capture completed: `2026-07-17T04:48:06Z`
- Source revision: `ae9e193e6141b769b17cc99b71a15ffd586b27ef`

The rejected capture reused a 166 mph stress scenario on a 363.876-meter
dead-end fixture. The vehicle reached the endpoint in roughly ten seconds and
the chase camera correctly followed it beyond the last road mesh. All four
chunks remained loaded; streaming was not the cause. The runtime also had no
terrain mesh and only sparse dark posts.

The repair separates the technical soak from a moderate-speed
`--render-integrity` traversal. The technical soak now performs controlled
route loops. The review traversal waits for all four chunks and their road,
terrain-shoulder, and scenery meshes; crosses the 100, 200, and 300-meter
distance thresholds
at a 12 m/s target; and exits before the fixture endpoint. It requires all four
visual chunks throughout the traversal, three monotonic distance thresholds, at least
three grounded wheels for 90 percent of post-contact physics frames, no more
than 30 consecutive unsupported 120 Hz physics frames, and zero chunk failures.

The renderer-backed Godot 4.7.1 capture completed 1,554 frames at 1280x720 and
60 FPS, for 25.9 seconds. The runtime reported:

```text
CANNONBALL_RENDER_INTEGRITY_OK chunks=4 distance_m=300.1 peak_mph=26.9 distance_thresholds=3 review_chunks=4 well_grounded_ratio=0.9509 max_unsupported_frames=11 chunk_failures=0
```

```bash
set -o pipefail
GODOT_BIN=.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot \
  CANNONBALL_CAPTURE_FPS=60 CANNONBALL_CAPTURE_FRAMES=4800 \
  CANNONBALL_SCENARIO_TIMEOUT_SECONDS=180 \
  ./scripts/capture-scenario.sh /tmp/p0-004-render-integrity.avi \
  --render-integrity 2>&1 | tee /tmp/p0-004-render-integrity.log
```

| Artifact | Review path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Original MJPEG capture | `/tmp/p0-004-render-integrity.avi` | 52,400,950 | `46121a3b48ab9f76fd791d5b2805fb85621a165b61b008a47f53ded214371d36` |
| H.264 review copy | `/tmp/p0-004-render-integrity.mp4` | 1,673,083 | `9a145d401c8edf29c61a914481dad72cf42e27640f4a813922a26234a7956d00` |
| Six-frame contact sheet | `/tmp/p0-004-render-integrity-contact-sheet.png` | 209,469 | `b0536ee92d4e2cd8975aee5dc0fe5da471de7b918e4efa32c8fea17d2ffd96c3` |
| 45-frame adversarial sheet | `/tmp/p0-004-render-integrity-45-frame-sheet.png` | 547,724 | `216379c0a48e6dbc8bc808fd60d53812a6f7f7eb6f7b1ac14a2e482664fad64a` |
| Capture log | `/tmp/p0-004-render-integrity.log` | 1,885 | `9836232a80fc5a6818cd71837641b78b5bac9afe708b17aa3f54e011452f0cd5` |

Adversarial inspection sampled 45 evenly spaced frames. Roadway, road-following
graybox terrain shoulders, the vehicle, roadside posts, and cone scenery were
visible in every sample. No sampled frame reproduced the rejected empty-space
failure. The terrain shoulders are presentation context derived from the route
profile, not representative lateral DEM terrain.

This clears the short-fixture render defect for continued engineering work. It
does not change the rejected human geographic gate: a longer locked corridor,
multi-edge traversal support, and a new owner review remain required before
P0-004 can complete.

The initial chunk is constructed synchronously before the first rendered frame
and has a 50 ms cold-start budget to absorb runtime/JIT initialization on hosted
runners. Every later asynchronously streamed chunk retains the 40 ms build
budget.

## Longer representative candidate

- Candidate prepared: `2026-07-17`
- Human decision: accepted for the current graybox milestone on 2026-07-17
- Engine: Godot `4.7.1.stable.mono.official.a13da4feb`
- Content version: `route-v3-59423d9c69671f15`

The replacement candidate is a checksum-locked, continuous US 36 corridor from
the Boulder side toward the Westminster area. It contains 45 directed NHPN
edges, 49 independently verified runtime chunks, and 24,740.282 meters
(15.372898 miles) of unique route. The committed 3DEP crop covers the entire
corridor. Its source lock can be replayed without discovery from the exact NHPN
query and historical USGS tile.

The runtime now constructs a route-wide edge plan instead of selecting one edge
by lexical ID. Streaming, projection, lookahead, local-origin coordinates,
telemetry, and saves use global route distance while persisted positions retain
edge-local distance. Ambiguous branches are rejected rather than silently
choosing a path. The review scenario visits nine distributed corridor positions,
and it does not pass until every one of the 49 chunks has produced road, terrain,
and scenery geometry at least once.

Raw 3DEP samples initially exposed localized 17–26 percent surface-model spikes
near structures. The final package applies a deterministic nine-sample median
and corridor-wide 7 percent grade projection. Shared edge endpoints remain
identical; the original DEM, crop, recipe, and checksums remain the authoritative
provenance. The final profile ranges from 1,618.053 to 1,731.028 meters and has a
maximum absolute signed grade of 7.00 percent.

The source-derived [route and elevation overview](../images/p0-004-representative-corridor-overview.svg)
shows the locked route shape, all nine renderer-backed viewpoints, bounds, and
conditioned profile. It is generated with:

```bash
node scripts/generate-route-review.mjs \
  data/sources/fixtures/nhpn-boulder-westminster-us36.geojson \
  .tools/scenarios/representative-corridor/route_graph-b779b9b9308b5a1285e94db99d4bfb8ca72b006538d9b4bd471e2bd51aea6af7.json \
  docs/images/p0-004-representative-corridor-overview.svg
```

The renderer-backed capture completed 811 frames at 1280x720 and 60 FPS. Godot
reported:

```text
CANNONBALL_GEOGRAPHIC_REVIEW_OK route_miles=15.372898 edges=45 visited_edges=9 review_chunks=49 waypoints=9 chunk_failures=0
```

```bash
set -o pipefail
CANNONBALL_CAPTURE_FPS=60 CANNONBALL_CAPTURE_FRAMES=1200 \
  CANNONBALL_SCENARIO_TIMEOUT_SECONDS=180 \
  ./scripts/capture-scenario.sh \
  /tmp/p0-004-representative-corridor-v2.avi \
  --fixture representative-corridor --geographic-review 2>&1 | \
  tee /tmp/p0-004-representative-corridor-v2.log
```

| Artifact | Review path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Original MJPEG capture | `/tmp/p0-004-representative-corridor-v2.avi` | 27,412,010 | `288a3a365456ec7ec41dfaa9c75ed0e380f8606226c4ce534508e20b45413c6c` |
| H.264 review copy | `/tmp/p0-004-representative-corridor-v2.mp4` | 213,908 | `1000897881e1b228c696eec34f3f15d5c450bc0a6b26ede8c44323eda095e670` |
| Nine-view contact sheet | `/tmp/p0-004-representative-corridor-v2-contact-sheet.png` | 333,333 | `8c3c5c7a8f9049a25fa5e705f941cb3ec75ceea7b5aa7f48145c008f7054a86d` |
| 36-frame adversarial sheet | `/tmp/p0-004-representative-corridor-v2-adversarial-sheet.png` | 218,714 | `17b70822a1ccb59ad5e606ac86081576ebe2203e15d2280cb19842ba5868ee46` |
| Capture log | `/tmp/p0-004-representative-corridor-v2.log` | 2,715 | `25e393f860fc9defe1697827ce59af5354c435b0a8c9a07bf6d7d5ae174e8a38` |

Adversarial inspection sampled 36 frames spanning all nine viewpoints. Roadway,
vehicle, shoulders, lane markings, posts, and scenery remained visible in every
sample. No empty-space regression, missing seam, disconnected edge, or visible
vertical spike was found. The graybox shoulders follow the conditioned route
profile; they are not claimed as representative lateral terrain.

This candidate satisfied the automated prerequisites for a new geographic
review. The project owner subsequently accepted the route shape, grade, seams,
placement, and absence of obvious geographic mistakes for the current graybox
milestone; the durable decision is recorded below.

## Final project-owner decision

- Reviewed: 2026-07-17
- Decision: approved; P0-004 human gate cleared
- Candidate: `route-v3-59423d9c69671f15`
- Approval statement: "Looks good enough for now from what I can tell."

The approval covers the representative graybox sanity gate: the US 36 route
shape and conditioned elevation are plausible enough to continue engineering;
the roadway stays continuous across the reviewed chunks; and the capture shows
no obvious empty-space, suspended-vehicle, placement, seam, or vertical-spike
failure. It does not approve final geographic precision, road materials,
terrain, vegetation, backgrounds, vehicle art, or release quality. Those remain
owned by later route-validation and M5 visual-production tasks.
