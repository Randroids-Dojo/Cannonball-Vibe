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
