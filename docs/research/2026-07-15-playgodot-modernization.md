# PlayGodot modernization plan

- Date: 2026-07-15
- Status: implementing M1 spike
- Decision owner: Automation
- Related: [ADR-0005](../decisions/ADR-0005-official-engine-agentic-automation.md),
  [Q-011](../OPEN_QUESTIONS.md), and delivery task `P1-004`

## Outcome

Modernize PlayGodot if Cannonball's rendered UI needs browser-like semantic
automation. Preserve its external scene-node API and client ergonomics, but
replace the custom Godot fork and remote-debugger patches with a debug-only
runtime addon on the official Godot 4.7.1 .NET build.

This fills a real gap. The official CLI is authoritative for deterministic
simulation and exports. Computer Use validates real windows, focus, OS input,
accessibility exposure, and pixels. Neither supplies stable semantic selection
of a live rendered game node. PlayGodot can connect those layers without making
the engine itself a project-maintained dependency.

## Existing evidence

The current `Godot/PlayGodot` repository has a mature Python-facing API and
tests for node access, properties, methods, scene trees, input, screenshots,
signals, time control, and scene lifecycle. Its current native transport still
depends on custom RemoteDebugger messages in the old Godot fork.

The sibling GoDig and GoPit workspaces each contain an
`addons/playgodot` prototype that already runs on official Godot. It uses:

- a runtime autoload with `TCPServer` and `WebSocketPeer`;
- JSON-RPC request and response envelopes;
- scene-tree queries and common node serialization;
- property reads and writes plus dynamic method calls;
- `Input.parse_input_event` for keyboard, mouse, action, touch, and gesture
  injection;
- frame, duration, and signal waits; and
- viewport capture with node cropping based on `Control.get_global_rect()`.

This proves the no-fork architecture. The two copies have diverged and the
prototype currently grants excessive authority, so it should be consolidated
and hardened rather than copied into Cannonball as-is.

## Proposed architecture

```text
agent or test
  -> Python API / CLI / optional MCP adapter
  -> authenticated JSON-RPC over 127.0.0.1 on an ephemeral port
  -> PlayGodot debug-only Godot addon
  -> stable automation registry
  -> live SceneTree, Control state, signals, Input, and viewport capture
```

The runtime protocol is the stable boundary. Python is the reference client and
compatibility surface. A CLI makes it shell- and CI-friendly. MCP may be a thin
adapter later; it must not become the only client or enter the game process.

## Minimum protocol

Every session starts with `session.hello`, carrying a per-run token, protocol
version, engine version, project revision, build type, and requested capability
set. Unknown versions or capabilities fail closed.

The first useful read-only surface is:

- `session.capabilities`, `session.ping`, and `session.close`;
- `scene.current`, `scene.tree`, and `scene.wait_changed`;
- `node.describe`, `node.children`, `node.find`, and `node.wait`;
- `ui.describe`, `ui.focused`, and `ui.wait_state`;
- `signal.wait` with a timeout;
- `input.action`, `input.key`, `input.click`, and `input.drag`; and
- `screenshot.viewport` and `screenshot.node`.

`node.describe` and `ui.describe` return a normalized contract rather than raw
Godot Variants: automation ID, class, scene path for diagnostics, visibility,
enabled/focus state, text/value where applicable, global bounds, selected
accessibility metadata, and explicitly exported test state.

Arbitrary `set_property` and `call_method` are not baseline capabilities. A
project can register named commands or allowlisted properties and methods for a
specific test profile. Requests have payload, depth, execution-time, and
response-size limits.

## Stable selector contract

Scene paths are useful diagnostics but poor long-lived test selectors. Every
interactive or asserted UI element receives a unique, explicit automation ID,
for example `hud.speed`, `pause.resume`, or `route.choice.east`. The ID is stored
as node metadata or registered through a small `AutomationTarget` component and
must be unique in the live tree.

Selectors support automation ID first, then an explicitly marked unique scene
name, then a raw path only for diagnostics and migration. Class names, display
text, child indices, wildcard paths, and screen coordinates are not stable
primary selectors.

## Security and shipping boundary

- Bind explicitly to `127.0.0.1`; Godot documents `"*"` as the `TCPServer`
  default, which listens on every available IPv4 and IPv6 address.
- Select an ephemeral port and write the port plus a cryptographically random
  token to a permission-restricted rendezvous file or inherited pipe.
- Require the token during the initial handshake and rate-limit failures.
- Start only when a debug build receives an explicit automation flag and token.
- Keep the addon out of release export resources and add a package test proving
  that the server, symbols, and rendezvous behavior are absent.
- Default to read-only capabilities; grant input and mutations separately.
- Log request IDs, methods, durations, outcomes, client identity, and artifact
  hashes without logging secrets.
- Parse and execute commands on the main thread with bounded queues and cancel
  outstanding waits during scene changes or shutdown.

## Delivery sequence

1. Consolidate the Python API and official-engine addon in the PlayGodot
   repository; keep the old transport behind a temporary compatibility layer.
2. Define protocol fixtures and golden transcripts before changing clients.
3. Harden transport, lifecycle, serialization, selectors, timeouts, and
   capability enforcement.
4. Add a tiny official-Godot fixture project with representative `Control`, 2D,
   and 3D nodes and run it on macOS, Linux, and Windows.
5. Add the CLI and preserve high-value Python client calls as wrappers over the
   new protocol.
6. Integrate the addon into Cannonball only when its first interactive UI scene
   can prove the Q-011 value threshold.
7. Compare semantic PlayGodot tests, CLI scenarios, and Computer Use for flake
   rate, diagnosis time, execution time, and unique defect coverage.
8. Consider an MCP adapter only after the host-neutral protocol and CLI are
   stable.

## Acceptance threshold

PlayGodot becomes required Cannonball infrastructure only if the spike proves:

- unmodified official Godot 4.7.1 on macOS, Linux, and Windows;
- stable automation-ID selection across harmless scene refactors;
- deterministic node state, signal waits, node-relative input, and screenshots;
- bounded timeouts with useful transcripts and failure artifacts;
- no listener without explicit enablement and no non-loopback binding;
- rejected unauthenticated, oversized, malformed, and disallowed requests;
- release packages contain no enabled automation server; and
- materially lower flake rate or diagnosis cost, or unique rendered-UI defect
  detection, compared with CLI plus Computer Use alone.

## Spike implementation and measured result

The Cannonball spike now implements the smallest useful official-engine slice:

- `addons/playgodot/bootstrap.tscn` is an explicit test scene, not an autoload;
- `server.gd` binds `127.0.0.1:0`, requires a 256-bit-equivalent inherited
  token and protocol handshake, and exposes only named read, input, wait, and
  screenshot operations;
- `automation/playgodot` provides an asyncio client and an agent-facing CLI;
- the prototype HUD exposes stable IDs such as `hud.speed`; and
- hostile-input and live-engine tests exercise authentication, bounds,
  capability denial, semantic state, concurrent signal/input correlation,
  screenshots, and redacted transcripts.

The adversarial pass added byte-framed UTF-8 handling, a bounded nonblocking
outbound queue, capped selector/state traversal, terminal signal transcripts,
latched-input cleanup, strict handshake/response validation, process-group
cleanup, and a one-session JSONL action-plan CLI. Visual artifact inspection
also found and corrected logical-to-render-pixel crop drift; a solid-color
fixture now checks the actual cropped pixels on every live run.

On local macOS with official Godot 4.7.1, ten complete seven-test runs produced
zero failures in 30 wall-clock seconds (0% observed flake rate, about three
seconds per fresh-engine run). A direct CLI query returned the live speed
label's stable ID, normalized text, visibility, focus, and global bounds in one
fresh process. That is unique semantic coverage: the existing deterministic
scenario CLI reports run/streaming state but cannot identify or assert a
rendered `Control`, while pixel-oriented Computer Use cannot reliably name the
underlying node or wait on its signal.

The spike does not yet justify making PlayGodot required infrastructure. CI
must reproduce the live suite on macOS, Linux, and Windows, P0-007 must provide
a real release package for absence inspection, and a representative interactive
menu must compare diagnosis time against Computer Use. Until then, PlayGodot is
an optional debug-only semantic layer and the deterministic CLI remains the
milestone authority.

## Deliberately excluded legacy authority

The spike does not copy the legacy NativeClient/Variant transport, fixed ports,
wildcard binding, arbitrary property mutation, arbitrary method calls, remote
scene loading, filesystem access, pause/time-scale control, or permanent
autoload. Those surfaces were convenient in the old fork but are unnecessary
for the current semantic-UI question and materially widen risk.

## Primary Godot references

- [TCPServer binding behavior](https://docs.godotengine.org/en/4.7/classes/class_tcpserver.html)
- [Input event injection](https://docs.godotengine.org/en/4.7/classes/class_input.html)
- [Node groups and unique names](https://docs.godotengine.org/en/4.7/classes/class_node.html)
- [Control geometry](https://docs.godotengine.org/en/4.7/classes/class_control.html)
