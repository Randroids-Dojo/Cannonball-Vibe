# P0-023: Per-process rendered readiness

Date: 2026-09-06. Related: red-main #136, ADR-0005, ADR-0025, P0-022.

Mainline CI run 34069163432 failed two macOS semantic tests at f6a8cf0.
The camera transcript ends after successful hello, description and rear-view
input; its next description never reached the server within the three-second
settling window. The empty timeout result then produced `KeyError`, rather than
evidence of a missing camera field. The hostile-request transcript ends after
its successful reconnect handshake; its first description likewise never
reached the server within the one-second client deadline.

Both retained runtime logs advertise `PLAYGODOT_READY` before
`CANNONBALL_READY`. The bridge is the first bootstrap child and opened its
listener in `_ready`, before the game's first frame. Raising process priority
and warming a different process do not establish first-draw readiness in each
test process. The transcripts locate the response loss between frame polls;
they do not identify an individual driver pipeline as the cause of the stall.

The listener now waits for this process's `RenderingServer.frame_post_draw`
before binding and advertising readiness. The engine documents that signal as
following viewport updates in its [RenderingServer reference](https://docs.godotengine.org/en/stable/classes/class_renderingserver.html#signals).
Preparation duration and process-frame count are logged before readiness.
The existing startup deadline now covers that work. Request, authentication,
cooldown and camera thresholds remain unchanged, with no gameplay retry.
The rendered round-trip test asserts that game initialization and first-frame
evidence precede the ready record.

Verification and exact input/output hashes are recorded in
`evidence/M0/P0-023.json`. A green run validates the new readiness contract;
it does not prove that all possible future renderer stalls are eliminated.
