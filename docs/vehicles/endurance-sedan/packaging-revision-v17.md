# Meridian S8R restraint revision17

2026-09-11. This supersedes the unbuilt revision16 candidate lock. Before
implementation, native cloth tests found two crossed ribbon corners and a rear
guide whose grip did not cover the complete intended overlap. No source34 was
built from that failed candidate; its exact recipe and diagnostics remain.

Revision17 retains every route, seat and rail-anchor position. The ribbon width
vectors now turn continuously through both center-seat gaps. Rear guide centers
are X±0.704, Y−1.495, Z1.208 m, with 53×19×38 mm envelopes and a 4 mm one-segment
bevel. The original geometry choices and simulation boundary in revision16 apply.

Candidate11 passes six native cloth self-intersection checks and 40 finite
interface rules, with 992 triangles replacing 1,404. The exact recipe and width
vectors are locked under `original_packaging.restraints_revision17`. Rebuilt
source34, precise grip coverage, all-opening clearance, exported correspondence,
rendered inspection and final runtime tests remain separate required checks.
