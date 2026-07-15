# ADR-0005: Official-engine automation with a modern PlayGodot bridge

- Status: Accepted
- Date: 2026-07-14
- Retires: the legacy PlayGodot remote-debugger transport and the
  Randroids-Dojo custom Godot automation fork
- Research: [Godot agentic automation](../research/2026-07-14-godot-agentic-automation.md)

## Context

Legacy PlayGodot depended on a privately maintained engine fork exposing a
custom remote-debugger protocol. That fork is no longer maintained and does not
track the project's engine version. Keeping that transport would make delivery
depend on rebuilding and maintaining an engine rather than the game.

Official Godot exposes the primitives needed by this project: headless scenes,
custom command-line arguments, standalone scripts, deterministic fixed-FPS
runs, movie and frame capture, imports, exports, logs, and debug options. C# can
implement semantic scenario APIs and input injection inside the running game.

Those primitives do not expose a stable external scene-node API for rendered
`Control` UI. CLI evidence can prove state and Computer Use can prove pixels and
real OS interaction, but neither can reliably select a live node, inspect its
semantic state, wait for its signal, or click its rendered bounds. PlayGodot's
public automation concept remains valuable for that gap.

## Decision

Use this automation hierarchy:

1. Pure rules, saves, schemas, and data contracts use xUnit and pytest.
2. Scene, physics, streaming, and run integration use an in-process C# scenario
   runner launched by the official Godot CLI.
3. Visual regression uses deterministic Godot frame or movie capture plus
   machine-readable state evidence.
4. Packaged black-box smoke tests may use Computer Use for real OS keyboard,
   pointer, window, and screenshot interaction.
5. Rendered UI that needs stable semantic automation may use a modern PlayGodot
   runtime bridge implemented as a project addon on the official engine.
6. Human handling, wheel feel, accessibility usability, rights, credentials,
   and release approval remain human gates.

Do not use the retired custom engine fork or reintroduce engine patches. The
modern PlayGodot bridge must:

- run on the unmodified official Godot 4.7.1 .NET build;
- be explicitly enabled only for debug/test processes and absent from release
  exports;
- bind to loopback, use an ephemeral port and per-run authentication token, and
  reject unauthenticated clients;
- expose a versioned protocol with capability negotiation and bounded requests;
- select UI by explicit stable automation IDs, not fragile scene paths alone;
- provide a read-oriented semantic surface and allowlist all mutations and
  method calls;
- preserve machine-readable transcripts and failure artifacts; and
- keep Python, CLI, and optional MCP adapters outside the game process so the
  runtime protocol is not tied to one agent host.

Do not make an MCP editor bridge a required dependency. It may adapt PlayGodot
or assist editor authoring after a separate security, determinism, licensing,
version-compatibility, and measured-value evaluation.

## Consequences

- The official engine is the only Godot runtime agents and CI must install.
- Test-only semantic hooks live in project code, remain versioned with the game,
  and emit stable JSON evidence.
- PlayGodot remains a candidate project-owned automation product, but its legacy
  engine-fork implementation is not a dependency.
- Computer Use is a complementary black-box and visual tool, not the source of
  deterministic milestone truth.
- Scene-level C# testing may adopt GdUnit4Net after a stable release explicitly
  supports the active Godot version; it is not required for the initial runner.
- MCP tools remain replaceable conveniences rather than architectural
  dependencies.

## Sources

- [Godot 4.7 command-line reference](https://docs.godotengine.org/en/4.7/tutorials/editor/command_line_tutorial.html)
- [Godot Input API](https://docs.godotengine.org/en/4.7/classes/class_input.html)
- [Godot TCPServer API](https://docs.godotengine.org/en/4.7/classes/class_tcpserver.html)
- [Godot Control API](https://docs.godotengine.org/en/4.7/classes/class_control.html)
- [Godot Node API](https://docs.godotengine.org/en/4.7/classes/class_node.html)
- [Godot command-line exporting](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_projects.html)
- [GdUnit4 and GdUnit4Net](https://github.com/godot-gdunit-labs/gdUnit4)
