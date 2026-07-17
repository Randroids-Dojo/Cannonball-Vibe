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

The rejected capture reused a 166 mph stress scenario on a 363.876-meter
dead-end fixture. The vehicle reached the endpoint in roughly ten seconds and
the chase camera correctly followed it beyond the last road mesh. All four
chunks remained loaded; streaming was not the cause. The runtime also had no
terrain mesh and only sparse dark posts.

The repair separates the technical soak from a moderate-speed
`--render-integrity` traversal. The technical soak now performs controlled
route loops. The review traversal waits for all four chunks and their road,
terrain-shoulder, and scenery meshes; crosses the 100, 200, and 300-meter seams
at a 12 m/s target; and exits before the fixture endpoint. It requires all four
visual chunks throughout the traversal, three ordered seam crossings, at least
three grounded wheels for 90 percent of post-contact physics frames, no more
than 30 consecutive unsupported 120 Hz physics frames, and zero chunk failures.

The renderer-backed Godot 4.7.1 capture completed 1,554 frames at 1280x720 and
60 FPS, for 25.9 seconds. The runtime reported:

```text
CANNONBALL_RENDER_INTEGRITY_OK chunks=4 distance_m=300.1 peak_mph=26.9 seams=3 review_chunks=4 well_grounded_ratio=0.9488 max_unsupported_frames=11 chunk_failures=0
```

```bash
GODOT_BIN=.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot \
  CANNONBALL_CAPTURE_FPS=60 CANNONBALL_CAPTURE_FRAMES=4800 \
  ./scripts/capture-scenario.sh /tmp/p0-004-render-integrity.avi \
  --render-integrity
```

| Artifact | Review path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Original MJPEG capture | `/tmp/p0-004-render-integrity.avi` | 52,400,950 | `46121a3b48ab9f76fd791d5b2805fb85621a165b61b008a47f53ded214371d36` |
| H.264 review copy | `/tmp/p0-004-render-integrity.mp4` | 1,673,083 | `9a145d401c8edf29c61a914481dad72cf42e27640f4a813922a26234a7956d00` |
| Six-frame contact sheet | `/tmp/p0-004-render-integrity-contact-sheet.png` | 209,469 | `b0536ee92d4e2cd8975aee5dc0fe5da471de7b918e4efa32c8fea17d2ffd96c3` |
| 45-frame adversarial sheet | `/tmp/p0-004-render-integrity-45-frame-sheet.png` | 547,724 | `216379c0a48e6dbc8bc808fd60d53812a6f7f7eb6f7b1ac14a2e482664fad64a` |
| Capture log | `/tmp/p0-004-render-integrity.log` | 1,871 | `5f7f7d6e353849a6346fc51884cc0b80602035d8248bd11751bca39902af6ca4` |

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
