# Questions for Randroid: P0-013 trip map

This handoff contains the only current owner-blocking decision for P0-013.
Machine verification and independent adversarial review are recorded in
[the implementation audit](audits/2026-07-19-p0-013-trip-map-review.md) and
[the continental-scale closeout](audits/2026-07-20-p0-013-scale-closeout.md).

On 2026-07-23 the owner found the overview functionally fine but visually
basic and requested a polish pass. The follow-up adds stronger hierarchy,
progress treatment, map framing, layered route strokes, shape-distinct
markers, and a persistent legend. Results and verification are recorded in
[the owner follow-up audit](audits/2026-07-23-owner-handling-and-trip-map-followup.md).
That feedback is actionable direction, not an implicit approval; Q-028 remains
open for review of the updated presentation.

Owner scheduling decisions: defer this review until a representative integrated
visual slice, then review before final polish. The trigger is one build that
combines the representative Hero GT, production highway kit, and one regional
environment slice. This does not approve the map or close Q-028.

## Q-028 — Trip-map comprehension and accessibility review

Do not perform this review until the integrated visual-slice trigger above is
satisfied. Once that build exists, review its trip-map capture and run its
equivalent of:

```bash
GODOT_BIN=.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot \
  ./scripts/capture-scenario.sh /tmp/p0-013-trip-map.avi --trip-map-review
```

Check whether you can quickly identify the current position, planned route,
alternatives, destination, next exit or transfer, services, trip progress, and
the controls without relying only on route color.

### A — Approve the first-pass map (recommended)

Pros: clears the required human gate; preserves the tested interaction and
lets the next pass focus on richer cartography. Continental-scale LOD selection
and data-driven compression estimates are now machine-verified. Cons: accepts
this deliberately utilitarian visual language for the milestone rather than
requiring final art quality now.

### B — Approve with named follow-ups

Pros: clears the core comprehension gate while preserving specific polish or
accessibility work as durable follow-ups. Cons: requires listing the exact
changes so the closeout boundary remains unambiguous.

### C — Request changes before approval

Pros: keeps P0-013 open until the first-pass layout meets your bar. Cons:
blocks milestone closeout and needs concrete problem areas or a marked-up
capture before the next implementation pass.
