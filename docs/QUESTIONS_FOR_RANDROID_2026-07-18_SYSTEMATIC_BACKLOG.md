# Questions after the systematic priority pass

This dated handoff contains only decisions that cannot be closed safely by
machine evidence. Engineering continues against documented defaults, but the
delivery ledger remains authoritative and human gates stay open until an option
is explicitly approved.

## Q-025 — P0-012 geographic plausibility and route-choice review

The machine gate now covers variable lanes, a diamond exit/entrance, a
directional highway transfer, a semi-directional highway transfer, route
concurrency, milepoint changes, signs, all legal paths, save/resume, and eight
intentionally invalid mutations. Review the
[twelve-view contact sheet](images/p0-012-validation-corpus-review.png). Its top
two rows are elevated lane-transition checkpoints; its bottom two rows sample
the four-plan driving capture.

Which disposition should P0-012 receive?

### A. Approve the representative systems corpus (recommended)

- **Pros:** unlocks P0-013, the full-screen trip map; accepts the fixture as a
  geographically plausible systems baseline without claiming that its authored
  lanes or ramps are observed NHPN geography; keeps exact production geography
  and visual polish in their later gates.
- **Cons:** the current graybox does not prove a production interchange asset,
  final sign typography, traffic behavior, or exact real-world lane placement.

### B. Approve the machine corpus but request a visual correction

- **Pros:** preserves all deterministic validation work while documenting a
  specific elevated-view, ramp-shape, sign, or comprehension correction before
  M2 closes.
- **Cons:** P0-013 remains dependency-blocked until the correction is captured
  and approved. Please identify the frame or route decision that needs work.

### C. Reject this representative corpus

- **Pros:** prevents a weak geographic or comprehension baseline from becoming
  the foundation for the trip map.
- **Cons:** requires a replacement fixture direction and likely new authored
  geometry; P0-013 and the M5 road/environment tasks remain blocked on P0-012.

**Autonomous default:** keep P0-012 `in_progress`, ship the complete machine
gate and review candidate, and begin no task that declares P0-012 complete until
you choose A or approve a corrected B candidate.

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
