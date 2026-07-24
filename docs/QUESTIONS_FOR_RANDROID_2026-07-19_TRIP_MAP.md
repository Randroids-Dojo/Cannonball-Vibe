# Questions for Randroid: P0-013 trip map

This handoff contains the only current owner-blocking decision for P0-013.
Machine verification and independent adversarial review are recorded in
[the implementation audit](audits/2026-07-19-p0-013-trip-map-review.md) and
[the continental-scale closeout](audits/2026-07-20-p0-013-scale-closeout.md).

Owner scheduling decision, 2026-07-23: defer this review until the selected
visual-quality milestone. This does not approve the map or close Q-028.

## Q-028 — Trip-map comprehension and accessibility review

Please review [the representative trip-map capture](images/p0-013-trip-map.png)
and, when convenient, run:

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
