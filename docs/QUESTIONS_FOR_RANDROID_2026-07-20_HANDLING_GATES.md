# Handling questions for Randroid (2026-07-20)

This file contains only decisions that an agent cannot approve. Implementation and
automated verification continue under the delivery-ledger fixture scopes.

## Q-029 — P0-017 camera comfort and readability approval

The stabilized chase/cockpit camera foundation and all automatable P0-017 scenarios
now pass: grade/chassis isolation, collision compression and recovery, reset, route
transition, local-origin rebase, save/resume, pause, input-device change, bounded
cockpit look, mode transitions, and renderer inspection. P0-017 still requires a human
comfort judgment before it—and therefore P0-018—can be marked complete.

Please drive for at least five minutes in chase view and five minutes in cockpit view,
including sustained steering, braking, a reset, and switching views with `V`.
In cockpit view, also try IJKL or the controller right stick to confirm bounded look and
automatic recentering feel natural.

- **A — Approve both views (recommended if comfortable):** unblocks P0-017 closure
  after its remaining automated scenarios pass. Pro: preserves the current stable,
  decoupled camera. Con: later tuning becomes a refinement rather than an M0 blocker.
- **B — Approve chase only:** keeps useful progress while cockpit remains gated. Pro:
  validates the primary driving view. Con: P0-017 and dependent task completion remain
  blocked.
- **C — Do not approve yet:** record which view and motion causes discomfort or loses
  readability. Pro: prevents an uncomfortable baseline from hardening. Con: the M0
  handling chain remains open while the camera is retuned.

Record the answer here as `Q-029: A`, `Q-029: B`, or `Q-029: C — <finding>`.

## Future human gate (not ready for approval)

P0-020 will later require separate uninterrupted 30-minute keyboard and controller
sessions. Do not perform those sessions yet; the quantitative P0-018/P0-019 handling
baseline must be complete first.
