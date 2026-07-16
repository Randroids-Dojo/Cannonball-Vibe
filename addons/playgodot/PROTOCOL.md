# PlayGodot spike protocol v1

The spike uses newline-delimited JSON-RPC 2.0 over a single TCP connection.
The debug-only bootstrap binds an ephemeral port on `127.0.0.1` and reports the
endpoint through inherited stdout. The 256-bit per-run token is inherited via
`PLAYGODOT_TOKEN`; it is never printed or placed in process arguments.

The first request must be `session.hello` with protocol `1.0`, the token, and a
subset of the process allowlist (`read`, `input`, `screenshot`). The server
rejects unknown capabilities rather than silently dropping them. Arbitrary
property reads or writes, method calls, scene changes, script loading, pause,
time-scale changes, filesystem access, and process execution are absent.

Operational selectors accept only a unique lowercase `automation_id`. Scene
paths are returned for diagnostics but are not accepted as selectors. Requests,
responses, JSON depth, tree depth, tree nodes, screenshots, signal waits, and
pending waits all have finite advertised limits.

Node screenshots transform logical `Control` bounds into rendered viewport
pixels before clipping, so project stretch and window overrides do not silently
capture a neighboring UI element.

The implemented methods are:

- `session.hello`, `session.ping`, `session.capabilities`, `session.close`
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
