# Questions for Randroid: 2026-07-28 autonomous pass

No new architecture, spending, credential, rights, or release decision was
created during this pass. Engineering can continue without an answer to this
document.

## Completed machine follow-up

The old report that returning from Trip Overview could launch the car skyward
does not reproduce on the current integrated dynamics. A moving, full-throttle
official-engine regression now protects pause invariance and bounded vertical
and angular motion after resume. See
[the stability audit](audits/2026-07-28-p0-013-trip-overview-resume-stability.md).

## Questions to answer after the existing trigger

Do not perform Q-028 or Q-029 until one review build combines the
representative Hero GT, production highway kit, and one regional environment
slice. P1-008, P1-009, and P1-010 are still `in_progress`, so that trigger is
not yet satisfied.

1. **Q-028 - Trip-map comprehension and accessibility.** Once the trigger is
   met, can you identify current position, planned route, alternatives,
   destination, upcoming exits or transfers, services, trip progress, and
   controls without relying only on color? Use the A/B/C choices in
   [the canonical trip-map handoff](QUESTIONS_FOR_RANDROID_2026-07-19_TRIP_MAP.md).
2. **Q-029 - Camera comfort and readability.** In that same build, complete at
   least five minutes each in chase and cockpit with steering, braking, reset,
   view switching, and cockpit look/recentering. Use the A/B/C choices in
   [the canonical handling handoff](QUESTIONS_FOR_RANDROID_2026-07-20_HANDLING_GATES.md).
3. **Q-022 - Reference Windows performance evidence.** After a reviewed visual
   slice is ready, start the capture from a fresh clean worktree at the exact
   reviewed commit on the declared RTX 3080 Ti Windows host. The provisional
   limits and required evidence remain in
   [the open-question register](OPEN_QUESTIONS.md#open-questions).

## Current autonomous boundary

- P0-013 remains `in_progress` only at its human comprehension/accessibility
  boundary after the machine resume-stability follow-up.
- P0-017 remains `verified_local` pending Q-029.
- P0-018 and P0-019 remain dependency-blocked from completion while P0-017 is
  incomplete.
- P0-020 and P1-012 require sustained or physical human sessions and were not
  started by automation.
- Production art quality, exact asset rights, and reference-renderer budgets
  for P1-008, P1-009, and P1-010 remain human or production-evidence gates.
