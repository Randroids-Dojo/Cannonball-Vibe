# PlayGodot spike protocol v1

The spike uses newline-delimited JSON-RPC 2.0 over a single TCP connection.
The debug-only bootstrap binds an ephemeral port on `127.0.0.1` and reports the
endpoint through inherited stdout. The 256-bit per-run token is inherited via
`PLAYGODOT_TOKEN`; it is never printed or placed in process arguments.

The listener starts only after this process completes its first rendered frame.
`PLAYGODOT_PREPARING_FIRST_FRAME` and `PLAYGODOT_FIRST_FRAME` record that startup
phase before `PLAYGODOT_READY`. First-draw work belongs to the existing bounded
startup window, before interactive request and camera-settling deadlines begin.

The first request must be `session.hello` with protocol `1.0`, the token, and a
subset of the process allowlist (`read`, `input`, `screenshot`, `shutdown`). The server
rejects unknown capabilities rather than silently dropping them. Arbitrary
property reads or writes, method calls, scene changes, script loading, pause,
time-scale changes, filesystem access, and process execution are absent.

Operational selectors accept only a unique lowercase `automation_id`. Scene
paths are returned for diagnostics but are not accepted as selectors. Requests,
responses, JSON depth, tree depth, tree nodes, screenshots, signal waits, and
pending waits all have finite advertised limits.
The handshake names the concurrent pending-wait bound as
`pending_signal_waits`; the server enforces that same value.
Each accepted signal wait owns an independent one-shot connection. One emission
completes every wait already listening to that target and signal, once per
request ID. One wait timing out does not cancel another. A native connection
failure returns `INTERNAL_ERROR` before reserving a pending slot. A destroyed
target follows the existing timeout or session-cancellation path safely.

Node screenshots transform logical `Control` bounds into rendered viewport
pixels before clipping, so project stretch and window overrides do not silently
capture a neighboring UI element.

The implemented methods are:

- `session.hello`, `session.ping`, `session.capabilities`, `session.close`
- `session.quit`, requiring the explicitly granted `shutdown` capability
- `scene.current`, `scene.tree`
- `node.find`, `node.describe`, `node.children`
- `ui.describe`, `ui.focused`
- `signal.wait` for bounded zero-argument signals
- `input.action`, `input.key`, `input.click`, `input.drag`
- `screenshot.viewport`, `screenshot.node`

This is a project spike, not a shipping remote-control surface. It runs only
from `bootstrap.tscn` in a debug build with the explicit `--playgodot` user
argument and a valid inherited token.

## Agent CLI

The Python package owns process launch, generates the token, reads the
stdout-only rendezvous record, negotiates capabilities, correlates concurrent
requests, verifies screenshot hashes, and terminates Godot on exit. Agents do
not need to manage sockets or secrets directly:

```bash
GODOT_BIN=/absolute/path/to/Godot \
  uv run --project automation/playgodot --frozen playgodot \
  --repo "$PWD" \
  --route-package /absolute/path/to/route.cbrg \
  describe hud.speed
```

The other commands are `capabilities`, bounded `tree`, `screenshot`, `click`,
`action`, `key`, and `signal`. The `run` command executes one JSONL plan in a
single process; a plan may mark a wait as `"defer": true`, inject input in the
next line, and then correlate both responses. CLI failures emit a stable JSON
error with separate usage, protocol, remote-operation, and timeout exit codes.

## Failure behavior

Invalid envelopes, malformed JSON, failed authentication, unavailable
capabilities, unknown methods, duplicate automation IDs, timeouts, and limit
violations return machine-readable error names. Only request ID, allowlisted
method name, outcome, and duration enter the optional JSONL transcript. Tokens,
parameters, returned state, and screenshot bytes do not.

TCP input is framed as bytes before UTF-8 decoding. Outbound data uses a bounded
partial-write queue with a slow-reader deadline, and transcripts have a finite
size cap. Disconnect releases session-owned pressed actions and keys and records
pending signal waits as cancelled.

## Owned process shutdown

`session.close` closes only its connection and releases that session's inputs
and pending waits. The same process remains available for another authenticated
connection. Its existing behavior is unchanged.

The process launcher adds `shutdown` to its own child's inherited allowlist;
its ordinary client still requests only the caller's capabilities. During
cleanup a separate short owner session uses the private token and the verified
loopback rendezvous endpoint. `session.quit` accepts an empty parameter object
only, returns `{"quitting":true}`, and stops accepting operations. Wrong tokens,
unauthenticated requests, unavailable capabilities and extra parameters fail
through the existing protocol errors. There is no caller-selected exit code.

After its response queue is flushed (or the accepted peer disconnects), the
server releases pending waits and injected inputs, prints a token-free
`PLAYGODOT_QUIT` resource-count record and calls `SceneTree.quit(0)` on the main
thread. `PLAYGODOT_QUIT_ACCEPTED` marks the start of native shutdown diagnostics.
Accepted authorization survives peer loss. No new listener, arbitrary
method invocation or external process command is exposed.

Owner cleanup has one monotonic eight-second maximum: five seconds for normal
session close (at most one second), owner handshake/quit and native exit; then
at most one second each for terminate, kill and final output drain/bookkeeping.
Connection-turnover retries consume the original deadline. Cancellation waits
for this bounded cleanup before being re-raised. Repeated stop calls share the
same result. Any earlier test/startup exception remains primary, with cleanup
failure information attached.

Successful cleanup requires the actual native exit code 0, a completed quit
resource record, no termination fallback, complete output drain and no shutdown
diagnostics. The full native log is retained with a sibling `.shutdown.json`
native-observation record containing phase timings, acknowledgement, fallback,
exit, EOF, native diagnostic lines and log SHA-256. Its
`owner_finalization_required` field requires the owner's successful return (and
the outer test/command result); the file alone is not cleanup acceptance. Final
bookkeeping shares the drain's one-second deadline on a daemon worker, so a
blocked filesystem cannot keep the owner or its executor alive. A late worker
can write only observations, never a successful final result. The launcher
rejects a new start until that worker finishes. Earlier native errors are recorded separately;
a successful cleanup does not turn an already erroneous log into a clean one.
A live process after bounded kill remains an explicit failure with its PID.
