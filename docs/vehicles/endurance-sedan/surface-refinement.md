# Meridian S8R surface and cockpit refinement

2026-09-11. Independent review of the actual source17 Cycles images at 2560x1440 found conspicuous exterior hinge pockets, an incomplete roof/window surround, a remaining rippled bumper shoulder highlight and reflected instrument digits in the windshield. A valid collision sweep does not accept those visible construction defects. Source18 remains a geometry-valid diagnostic export while they are corrected.

The roof already uses a C1 monotone profile: an independent native vertex comparison in `reports/p1-018/research/surface-refinement-18/roof-profile-comparison.json` verified that fact. The next construction stage therefore adds formed roof-side rails between the authored roof edge and the upper window envelope instead of replacing the existing interpolator. The rails have an explicit enclosed cross section, painted outer surface and visible depth; they require renewed door/headliner clearance checks.

The instrument cluster receives a physical matte shade above the display, retaining its locked eye and cluster anchors. Its purpose is to block the upward path that produced the large reflected digit image. Native source and runtime views must demonstrate readability and reduced glare; material or reflection shortcuts cannot substitute for that check.

Concealed rear hinge positions are being evaluated against the existing parked geometry with the obsolete hardware explicitly excluded only from that diagnostic. A selected axis must be recorded in the locked specification, followed by reconstructed real hardware and renewed full-assembly clearance evidence. No diagnostic axis is an approved production change on its own.

These original construction choices do not change the engineering benchmark, authoritative vehicle physics or human visual/rights/usability gates. Failed candidates remain available with their exact source and configuration hashes.

The source20 matched paint view shows a small triangular highlight on the front
fender near the denser shoulder-profile transition. Source21 tests the same
creation-time 1.0-radian bevel threshold that removed the earlier bumper bevel
ripple, preserving the fender's 1.2 mm edge radius and panel gap. The source20
fender was already evaluated and baked, so the attempted direct live-modifier
diagnostic could not run and supplies no result. Matched source21 images must
confirm or reject this candidate before delivery.
