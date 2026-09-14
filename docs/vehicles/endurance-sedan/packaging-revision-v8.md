# Meridian S8R packaging revision 8

2026-09-11. Independent source17/18 visual review rejected the exterior hinge pockets as inconsistent with the intended performance sedan. The previous outboard rear axis at X=+/-0.942 m could not fit concealed hardware within the local 0.929 m body half-width.

The native diagnostic in `reports/p1-018/qa/rear-axis-18/results-01.json` compared six rear-axis positions while preserving the existing parked door geometry. X=+/-0.905 m failed, with 268 retained body-contact observations. X=+/-0.915 m and +/-0.925 m at both Y=-0.605 m and -0.585 m had no contact at the 101 sampled poses per side, after excluding precisely the eight obsolete rear pins/leaves. A subsequent triangle-distance check rejected Y=-0.605 m for a 0.971 mm rigid shortfall at 25 percent opening. The selected original position is X=+/-0.915 m, Y=-0.585 m, Z=0.500 m: `clearance-03.json` checked 804,699 near-field triangle pairs and cleared the guarded 1 mm threshold at all 101 poses on both sides, apart from the two separately reported closed rubber-seal interfaces. This result supports rebuilding; it does not certify new hardware or between-pose clearance.

Both pins on each door now sit at Z=0.600 m and 0.840 m. Separate 4 mm-radius pins, 4.5 mm-radius bearing bores and 6.5 mm-radius knuckles replace the exposed blocks. Folded arms reach inward before turning aft into the doorway. Jamb pockets terminate at absolute X=0.923 m so the exterior skin covers the hinge hardware. The precise pin/bore bearing interface has a declared 0.5 mm radial clearance, distinct from the general 1 mm moving-part requirement. New fixed/moving hardware, sheet boundaries and the complete opening sweep must be verified together.

The unchanged closed rear rubber-seal gaps measured 0.520 and 0.558 mm in the diagnostic. Their exact near-closed engagement interval is being measured; these compliant gasket interfaces must be recorded separately from rigid-body clearance, not hidden by a general collision exclusion.

The formed roof-side structure and physical instrument shade are described in `surface-refinement.md`. Small enclosed radiator fins and airbox ribs use a single bevel segment to recover geometry budget for visible construction. This retains their dimensions and chamfer while avoiding redundant submillimeter curvature subdivisions.

Revision7 remains immutable. No factory specification, capacity, driving policy or human approval is changed. Fresh source, exported geometry, clearance and actual native visual/runtime evidence are required before acceptance.
