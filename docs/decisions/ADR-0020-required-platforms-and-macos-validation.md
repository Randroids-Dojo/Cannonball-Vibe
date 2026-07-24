# ADR-0020: Required platforms and macOS validation

- Status: Accepted
- Date: 2026-07-23
- Owner decision: Q-009 Option A

## Context

Cannonball is PC-first. Linux and Windows already carry required build, test,
deterministic traversal, clean-machine, and export responsibilities. macOS is a
regular development environment and already catches useful Godot, rendering,
filesystem, input, and PlayGodot differences, but a public macOS product
commitment would add signing, notarization, packaging, device coverage, and
ongoing support obligations.

## Decision

- Linux and Windows remain required engineering and delivery platforms for the
  current milestones.
- Continue macOS build, runtime, renderer, and semantic-UI regression coverage
  where suitable runners and local machines are available.
- A passing macOS engineering check does not claim public macOS support.
- Do not make public macOS packages, signing, notarization, clean-machine
  installation, graphics coverage, input-device coverage, or support response
  release blockers until a later explicit platform-promotion decision.
- Keep core route, simulation, save, automation, and asset contracts portable
  so adding public macOS support does not require product-state rearchitecture.

## Consequences

- Apple-specific defects remain visible early without expanding the current
  public release promise.
- Linux and Windows failures remain release-blocking; opportunistic macOS
  checks may be required for the workflows that already declare them without
  implying distribution support.
- A future public macOS decision must declare signing and notarization
  authority, minimum hardware and OS, renderer coverage, clean-machine
  installation, input support, performance budgets, and support policy.
- Q-009 is resolved.

## Rejected alternatives

- **Commit to public macOS support immediately:** adds release and support scope
  before the primary game loop and Windows target budgets are complete.
- **Remove macOS validation:** wastes an available development platform and
  delays detection of cross-platform defects.
