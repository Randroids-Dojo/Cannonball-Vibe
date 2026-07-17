# P0-004 representative route sanity review

- Date: 2026-07-16
- Reviewer: project owner
- Decision: rejected; human gate remains open
- Task: P0-004

## Review artifact

The review used a deterministic 60-second Godot 4.7.1 capture at 1280x720 and
60 FPS. The scenario completed 3,600 frames, traversed all four fixture chunks,
reported zero chunk failures, and passed its packaged-content smoke.

```bash
GODOT_BIN=.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot \
  CANNONBALL_CAPTURE_FPS=60 CANNONBALL_CAPTURE_FRAMES=3600 \
  ./scripts/capture-scenario.sh /tmp/p0-004-route-review.avi \
  --short-corridor-soak
```

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Original MJPEG capture | 96,390,500 | `8cbdcf43e43c9f7557ca91fa28101c711099d7efe57ed6c1ccc383b9089d10e5` |
| H.264 review copy | 1,654,166 | `f222da5732e973b76caf5dc9760f08186cfd24e0ae3bef879102d6e280660588` |
| Six-frame contact sheet | 71,712 | `662156613d3bba70f93e70eb007141bb1aaa431fbd4047a798b1f7677a60c96c` |

The generated visual artifacts are reproducible review outputs and are not
committed source files. Their command, dimensions, duration, and hashes are
recorded here.

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
longer locked corridor is still required before claiming representative
long-route geography.
