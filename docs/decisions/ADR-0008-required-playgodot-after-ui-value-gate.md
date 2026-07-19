# ADR-0008: Require PlayGodot after the rendered-UI value gate

- Status: Accepted
- Date: 2026-07-16
- Activated: 2026-07-19
- Extends: [ADR-0005](ADR-0005-official-engine-agentic-automation.md)

## Context

ADR-0005 permits a modern, debug-only PlayGodot bridge on the unmodified
official engine when rendered UI needs stable semantic automation. The spike
now passes on macOS, Linux, and Windows and release inspection proves the bridge
does not ship or activate. Its remaining acceptance fact is a comparison on the
first representative interactive menu against CLI evidence plus Computer Use.

## Decision

- When that representative-menu comparison demonstrates materially lower
  diagnosis cost or unique rendered-UI defect coverage, PlayGodot becomes
  required project test infrastructure.
- The requirement applies to rendered `Control` surfaces that need stable node
  identity, semantic state, signal waits, node-relative input, or scoped
  screenshots. Logic, simulation, content, and export tests continue to use
  their narrower authoritative tools.
- Required rendered-UI suites run against the unmodified official Godot 4.7.1
  build on macOS, Linux, and Windows and become protected CI checks for their
  owning UI surfaces.
- PlayGodot remains debug/test-only, authenticated, loopback-only, capability
  constrained, transcript-producing, and absent from release exports.
- The representative driver-menu comparison passed the activation threshold on
  2026-07-19. Computer Use could operate and capture the official Godot window,
  but macOS exposed only window chrome and no in-game controls. PlayGodot
  identified the menu, focused button, selected action, and normalized status by
  stable ID, correlated open and close signals, and captured the menu node. It is
  therefore required for interactive rendered-UI surfaces from this date.

## Consequences

- Agents get a stable scene-node API wherever rendered UI demonstrates a need,
  while official Godot remains the engine and shipping authority.
- The project accepts maintenance of the addon, protocol, clients, selectors,
  and cross-platform CI once the activation threshold passes.
- Computer Use remains the black-box pixel, window, focus, and OS-input layer;
  deterministic CLI scenarios remain authoritative outside semantic UI.

The measured comparison and artifacts are recorded in
[the P1-004 closeout audit](../audits/2026-07-19-p1-004-menu-comparison.md).
