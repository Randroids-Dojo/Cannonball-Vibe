# Godot agentic automation research

- Date: 2026-07-14
- Updated: 2026-07-15 after inspecting the current PlayGodot repository and
  official-engine addon prototypes in GoDig and GoPit
- Scope: replace the unmaintained custom engine fork while preserving any
  uniquely valuable PlayGodot capabilities
- Decision: official Godot CLI plus a versioned C# scenario runner is the
  required baseline; a modern PlayGodot addon is the semantic rendered-UI layer;
  Computer Use is a black-box visual complement; MCP is optional

## Answer

We can implement and validate the engineering portion of Cannonball-Vibe
agentically without maintaining a Godot fork. The official 4.7.1 .NET editor,
project-owned C# scenario code, normal process control, and artifact inspection
cover deterministic gameplay, physics, streaming, saves, input actions,
performance metrics, visual capture, imports, exports, and packaged launch
smokes.

Computer Use can operate the actual editor or packaged game through keyboard,
pointer, accessibility data, and screenshots. It is useful for visual and OS
integration checks, but it should not replace deterministic state assertions or
CI because rendered 3D content and custom game UI do not expose the same stable
semantic tree as a browser DOM.

If Cannonball's rendered `Control` UI needs stable external selectors, property
inspection, signal waits, and node-relative input, CLI and Computer Use alone
are insufficient. That is the reason to modernize PlayGodot. The modernization
does not require an engine fork: existing local GoDig and GoPit prototypes
already implement a WebSocket JSON-RPC autoload using official `TCPServer`,
`WebSocketPeer`, `Input.parse_input_event`, scene-tree APIs, viewport capture,
and `Control.get_global_rect()`.

No automation stack can honestly approve subjective driving feel, physical
wheel behavior, representative-player comprehension, accessibility usability,
rights review, credential provisioning, or public release. Those remain human
gates.

## Selected automation layers

| Need | Selected solution | Why |
| --- | --- | --- |
| Portable rules, saves, schemas | xUnit | Fast, deterministic, normal .NET tooling, no engine process. |
| Geodata and content builds | pytest plus CLI fixtures | Reproducible source locks, topology, packaging, and provenance. |
| Godot scene and physics integration | Official `godot --headless` plus C# scenario runner | Runs the real engine without a fork and can emit semantic JSON evidence. |
| Input automation | Scenario commands plus Godot `Input` event/action injection | Tests action mappings and gameplay behavior while remaining in project-owned code. |
| Long traversal and performance | Distance-driven headless scenarios | Supports acceleration, checkpoints, metrics, save/resume, and bounded failure artifacts. |
| Visual regression | Fixed-FPS frame/movie capture with a real renderer | Produces deterministic artifacts suitable for image comparison and agent inspection. |
| Export and package verification | `--import`, `--export-release`, and launched exported binaries | Uses the shipping path and exact official templates. |
| Editor and packaged black-box checks | Computer Use | Exercises actual windows, focus, keyboard, pointer, dialogs, and visual output. |
| Rendered UI semantic checks | Modern PlayGodot addon | Stable automation IDs, node state, signals, node-relative input, and screenshots on the official engine. |
| Subjective/product acceptance | Human sessions with telemetry | Enjoyment and physical-device feel are not machine-verifiable facts. |

## Official CLI coverage

Godot 4.7.1 supports:

- `--headless` for engine and scene execution without a display server;
- `--path` and `--scene` for exact project and scene selection;
- `--` for project-owned scenario arguments;
- `--fixed-fps`, `--time-scale`, and `--quit-after` for controlled runs;
- `--write-movie` for deterministic visual artifacts;
- `--log-file`, debug overlays, and verbose output for diagnostics;
- `--import` for headless asset import;
- `--export-release`, `--export-debug`, and `--export-pack` for CI packaging;
- standalone engine scripts for batch import, validation, and authoring tasks;
- `--accessibility` for exercising accessible runtime surfaces.

Movie Maker mode requires a real renderer. Local validation found that combining
`--write-movie` with the macOS dummy headless renderer crashed Godot 4.7.1,
while the same 60-frame, 1280x720 capture completed with the compatibility
renderer. Simulation CI should remain headless; visual capture jobs need a GPU
or virtual/display-backed renderer and a separate failure budget.

The CLI does not provide a browser-like node selector or public remote-control
protocol. It remains sufficient for simulation and milestone state evidence.
Rendered UI is different: a debug-only PlayGodot addon should expose a narrow,
stable semantic surface from inside the process without modifying Godot.

## Input and UI testing design

Use two distinct levels:

1. Semantic scenarios call the same input abstraction used by keyboard and
   controller paths, or inject Godot input events/actions. They assert route,
   vehicle, systems, UI model, and save state directly.
2. Black-box scenarios launch a packaged build and use Computer Use to send real
   OS input, inspect the resulting frame, and confirm focus, scaling, dialogs,
   controller-visible prompts, and accessibility output.

Tests should prefer stable action names and domain outcomes over screen
coordinates. Computer Use evidence should include platform, resolution, window
mode, input sequence, screenshots, and the matching semantic telemetry run.

## Current framework and MCP options

### GdUnit4Net

GdUnit4Net is the current C# implementation of GdUnit4 and integrates with
VSTest. It provides scene runners, assertions, parameterized tests, and optional
Godot runtime tests. Its published compatibility table did not yet list the
4.7.1 stable release during this research, so adopting it as a required gate on
release day would add avoidable version risk. Re-evaluate it when a stable
release explicitly supports 4.7.1.

### Godot MCP addons

Modern MCP addons such as Godot AI, Beckett, GoPeak, Godot MCP Pro, and other
community bridges can inspect scene trees, mutate nodes and resources, run the
project, capture screenshots, and sometimes inject input. Their editor-authoring
surfaces are broader than the legacy PlayGodot client and they run against
official Godot builds rather than requiring an engine fork. They do not remove
the need for a stable, runtime-focused rendered-UI protocol.

They are not selected as required infrastructure yet:

- most are community projects with fast-moving APIs;
- several were released or substantially updated only days before this review;
- they add an editor plugin, local server, broad project mutation permissions,
  and another version/security boundary;
- their core run, screenshot, edit, and error-reading value overlaps with CLI,
  filesystem, build output, and Computer Use capabilities already available;
- milestone CI must remain reproducible without an interactive editor session.

Any editor bridge pilot should be MIT-licensed, actively maintained, support the
exact Godot version, check C# compilation, make transactional scene changes,
retain audit logs, expose a narrow tool profile, and prove value beyond the
PlayGodot runtime protocol. Pilot it in an isolated branch and keep every
mutation reviewable as normal repository changes.

## PlayGodot modernization

The PlayGodot name, client ergonomics, and semantic automation goal remain
valuable. Its legacy `Randroids-Dojo/godot` dependency and custom remote-debugger
messages are retired. Recreating those engine changes would impose engine
compilation, patch rebasing, three-platform binaries, and protocol maintenance.

The replacement is a project addon/autoload running on the official engine. A
local prototype already demonstrates node lookup, property get/set, method
calls, tree queries, scene changes, signal/frame waits, input injection, and
viewport or node screenshots over JSON-RPC. It is proof of feasibility, not yet
production-ready infrastructure:

- it calls `TCPServer.listen(port)` without a bind address; Godot's documented
  default is `"*"`, which listens on all interfaces rather than loopback only;
- it does not authenticate clients or negotiate a protocol version;
- unrestricted property writes and method calls expose more authority than an
  automation client should receive;
- raw node paths and simple wildcards are fragile selectors for changing UI;
- the addon is configured as a normal autoload and needs an enforced
  debug/test-only lifecycle plus release-export exclusion; and
- the GoDig and GoPit copies have diverged, so they need consolidation into one
  maintained PlayGodot source rather than further copying.

The modernization plan is recorded in
[PlayGodot modernization](2026-07-15-playgodot-modernization.md). Implement its
minimum secure protocol before making PlayGodot a required gate.

## Required implementation follow-ups

- Expand `scripts/run-scenario.sh` into a structured scenario CLI with
  route, seed, assist profile, distance, save points, and evidence output.
- Keep the external scenario watchdog and CI job timeout so a successful game
  result followed by a shutdown deadlock cannot occupy a runner indefinitely.
- Add deterministic screenshot/frame capture from named scenario checkpoints.
- Use `scripts/capture-scenario.sh` only on a renderer-backed worker; never add
  `--headless` to Movie Maker capture.
- Emit JSON containing gameplay state, performance percentiles, memory, chunk
  timing, collision misses, rebases, and content hashes.
- Add exported-binary launch smokes on Linux and Windows.
- Add a non-blocking Computer Use protocol for visual/editor and packaged UI
  checks.
- Prototype the modern PlayGodot addon against the first interactive `Control`
  UI and measure reliability against Computer Use alone.
- Re-evaluate GdUnit4Net and one optional MCP adapter only when they support
  4.7.1 and demonstrate unique value beyond the project-owned runner and
  PlayGodot protocol.

## Primary sources

- [Godot 4.7 command-line tutorial](https://docs.godotengine.org/en/4.7/tutorials/editor/command_line_tutorial.html)
- [Godot 4.7 Input API](https://docs.godotengine.org/en/4.7/classes/class_input.html)
- [Godot 4.7 TCPServer API](https://docs.godotengine.org/en/4.7/classes/class_tcpserver.html)
- [Godot 4.7 Node API](https://docs.godotengine.org/en/4.7/classes/class_node.html)
- [Godot 4.7 Control API](https://docs.godotengine.org/en/4.7/classes/class_control.html)
- [Godot 4.7 export automation](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_projects.html)
- [Godot 4.7 features](https://docs.godotengine.org/en/4.7/about/list_of_features.html)
- [GdUnit4 repository](https://github.com/godot-gdunit-labs/gdUnit4)
- [Godot AI repository](https://github.com/hi-godot/godot-ai)
- [Godot Asset Library: Beckett](https://godotengine.org/asset-library/asset/5296)
- [GoPeak repository](https://github.com/HaD0Yun/Gopeak-godot-mcp)
