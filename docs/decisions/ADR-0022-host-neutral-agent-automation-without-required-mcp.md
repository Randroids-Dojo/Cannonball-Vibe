# ADR-0022: Host-neutral agent automation without required MCP

- Status: Accepted
- Date: 2026-07-23
- Owner decision: Q-012 Option A

## Context

The project already has complementary automation layers:

- deterministic command-line builds, tests, scenario runs, captures, and
  evidence files;
- a modern debug-only PlayGodot addon on official Godot 4.7.1 for stable
  semantic scene-node inspection and bounded interaction; and
- Computer Use for black-box interaction with the real editor or packaged game.

An MCP adapter or editor-specific bridge could wrap some of these capabilities,
but it does not currently provide unique acceptance evidence. Making one
mandatory would add another protocol, security boundary, version matrix, and
operational dependency without replacing the authoritative command-line gates.

## Decision

- Command-line and filesystem contracts remain the authoritative automation
  interface for builds, content generation, tests, scenario execution,
  screenshots, transcripts, and evidence.
- Modern PlayGodot remains the required semantic rendered-UI layer where
  command-line scenarios and black-box inspection cannot expose stable node
  identity, focus, or normalized state.
- Computer Use remains an optional black-box layer for the actual official
  editor and packaged-game windows.
- No MCP adapter, MCP editor bridge, custom Godot fork, or custom editor build
  is required for delivery.
- A future MCP experiment may be proposed only if it preserves the host-neutral
  core and demonstrates all of the following:
  - exact compatibility with the pinned official Godot version;
  - a narrow allowlisted capability profile and reviewed security boundary;
  - transactional or fail-closed edits where mutation is allowed;
  - durable audit logs and reproducible evidence;
  - measurable workflow or defect-coverage value unavailable through the
    existing command-line, PlayGodot, filesystem, and Computer Use layers.

## Consequences

- Agents can deliver through standard tools in local, CI, and remote
  environments without depending on one orchestration host.
- Stable semantic UI coverage remains available without reintroducing the
  retired engine fork or legacy debugger transport.
- MCP integrations remain optional adapters rather than architectural
  dependencies.
- Q-012 is resolved. A future proposal needs new evidence and a superseding ADR,
  not merely an available MCP implementation.

## Rejected alternatives

- **Require an MCP adapter now:** adds infrastructure without proven unique
  coverage or delivery value.
- **Return to a custom Godot fork or editor bridge:** increases maintenance and
  version lag while weakening the official-engine boundary.
- **Use only black-box Computer Use:** cannot reliably expose semantic scene
  state, focus, or stable node identity.
