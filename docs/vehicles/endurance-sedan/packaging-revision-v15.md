# Meridian S8R finish revision15

2026-09-11. This original fabrication revision preserves revision14 and all
failed source32 diagnostic attempts. Dimensions, hardpoints, gameplay limits,
collision, suspension and the150,000/200,000 triangle ceilings stay fixed.
The authoritative recipes and measured25-station header tables are in
`specification.json`, under `original_packaging.finish_revision15`.

Each tire receives56 genuine recessed shoulder cuts from closed three-station
four-sided cutters. The old raised trim tubes are removed. The tire retains
its64-segment body and four actual4mm circumferential channels. Original
rubber corner normals are interpolated only on surviving original surfaces;
cavity walls retain their actual normals. Source32 candidate02 measured
1.147–2.052mm recess at448 samples per tire. Its actual close-up showed dark
incisions without candidate01's surface-normal dents. Final full mesh, rolling
and steering/travel clearance checks remain mandatory.

Twelve existing parts supply1,592 triangles: four projector and four exhaust
rings use24 instead of32 path stations; the steering rim uses48 instead of64;
two turbo casings and the rear differential use20x10 instead of24x12 UV
tessellation. Cross-section thicknesses, component count and nominal extrema
stay fixed. Native bidirectional vertex, triangle-edge-midpoint and centroid
samples measured at most0.360mm on the optical rings,0.334mm on exhaust lips,
0.416mm on the steering rim,1.573mm on turbo casings and2.883mm on the rear
differential. These are sampled comparisons, not continuous Hausdorff bounds.
They remain within the existing5mm global modeling tolerance. Actual close-up
review and rebuilt assembly fits are separate acceptance checks.

Two formed header walls close three actual camera rays that formerly reached
the headliner through an unfinished roof-side recess. Each occupies
`|X|.662.. .668`, `Y-1.230.. .100` meters. Four points enter the existing closed
rail section; the original roof-facing flange remains intact. Lower heights
follow the locked25-station table, including the clearance relief above the
fixed B-post. This is one closed integrated rail, not an intersecting box.
The isolated wall cleared232 complete opening domains by at least13.846mm.
The final rail must re-pass the actual finite roof weld, nonmating separation,
complete opening domain and visual checks. Earlier outward returns collided
with a rear window during opening; those attempts remain evidence.

The large windshield ghost was traced to the instrument shade/binnacle, and
the bright night lettering ghost to NavigationTitle sharing headlight emission.
Six declared forward dashboard panels use the existing matte carpet response
as flocking. Four static labels share one new portable CabinLettering material
with constant emission0.2. Glass, lights and all other materials remain intact.
The source label is independent of headlights. This does not add navigation,
climate or radio simulation. Exact material values and object names are locked
in the specification. Five-light source review and actual Godot visibility
remain required; display-referred luma comparisons are not physical lux claims.

Full final-source QA, export/import reproducibility, runtime demonstrations and
performance measurements remain separate gates. Human visual, rights,
driving-feel and usability approvals remain open.
