# Questions after the systematic priority pass

This dated handoff contains only decisions that cannot be closed safely by
machine evidence. Engineering continues against documented defaults, but the
delivery ledger remains authoritative and human gates stay open until an option
is explicitly approved.

## Q-025 — P0-012 geographic plausibility and route-choice review

Approved 2026-07-19 as Option **A**.

- Unlocks `P0-013`, `P0-015`, `P1-009`, and `P1-010`.
- Evidence reviewed: 12-view validation corpus including lane transitions, exits,
  transfers, concurrency, invalid mutation coverage, and four-plan driving capture.
- Working note: graybox and automated evidence are accepted as the M2 systems baseline; production art
  and downstream quality gates remain in their own tasks.

## Existing later decisions

The following questions remain in their existing authoritative handoffs rather
than being duplicated here:

- Q-019: whether the full-screen trip map pauses solo driving. Working default:
  pause local simulation and the run clock in solo modes.
- Q-020: final Hero GT art direction and acquisition path.
- Q-021: representative M5 region. Working default: Colorado mountain to plains.
- Q-022: minimum target PC and production renderer budgets.
- Q-024: production highway visual language. Working default: contemporary
  Colorado freeway realism without a regulatory-compliance claim.
