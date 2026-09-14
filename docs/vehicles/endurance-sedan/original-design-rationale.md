# Meridian S8R original design rationale

P1-018, refreshed 2026-09-11 against specification revision **17**. This document explains
the vehicle's identity and construction choices. The [production plan](production-plan.md)
owns the workflow; [specification.json](specification.json) owns current targets;
the [dimension sheet](dimension-sheet.md) presents their values. Neither this
rationale nor agent consensus grants final visual or rights approval.

## Engineering reference and fictional identity

**Meridian S8R** is a project-fictional, four-door, left-hand-drive endurance
performance sedan. Its fresh geometry, surface layout, optical assemblies,
wheel pattern, cabin graphics and equipment shapes are authored for this
project. The existing Hero GT is a separate vehicle.

The primary engineering reference is the **2016 US Audi S6 Prestige, C7
facelift/4G, seven-speed S tronic, quattro**, with Black Optic and Individual
Contour Seating as a documented reference configuration. It combines the
requested sedan package with a directly identified Cannonball donor year.
The contemporary E63 S and F10 M5 comparison informs the choice; their dimensions
and ratings are not blended into an imaginary factory configuration.
[Research comparison and source/conflict register](research.md).

Arne Toman's firsthand account identifies a modified 2016 S6 with revised
turbo/cooling hardware, auxiliary fuel storage and crew equipment. It supports
the endurance preparation story, not a guarantee of durability, present record
status, or stock performance. The original vehicle does not reproduce the
record car's body disguises, markings or device interfaces.
[Firsthand S6 build](https://www.arnesantics.com/projects/current-cannonball-run-record-holder-audi-s6/).

## Exterior decisions

The design keeps a readable three-box sedan silhouette: a separate engine
compartment, a substantial four-door cabin and an accessible trunk. A 2.92 m
wheelbase and slightly wider original body give the crew package room without
turning the vehicle into a coupe. The roof, shoulder, bumper curvature and panel
boundaries are original constructions rather than traced donor surfaces.

| Original feature | Intended purpose and reference boundary |
| --- | --- |
| Low horizontal cooling opening and separate side ducts | Show real opening depth, carrier and cooling hardware. Proportions and division are original; no Audi Singleframe, BMW kidney or Mercedes grille is adopted. |
| Split optical pods, paired projectors and thin light guides | Give the car a restrained signature while exposing distinct housing, reflector, optic and cover layers under inspection. Factory lamp graphics are not traced. |
| Curved rear optical covers and separate tail/brake/reverse/indicator elements | Keep the rear face consistent with the rounded body and make each required light state legible. Fit and illumination require actual exported-asset evidence. |
| Four door shells with distinct windows, handle pockets and trim breaks | Make the sedan construction clear from either side and support conventional opening inspection. Shared hinge/export infrastructure does not make the geometry a Hero GT variant. |
| Original nineteen-inch wheel pattern and square tires | The 255/40R19 envelope provides more nominal sidewall than the 255/35R20 reference option. Spokes, barrels, hubs and fasteners are authored geometry; no factory wheel mesh is reused. |
| Dark outlets, restrained sill treatment and uncluttered trunk face | Communicate a prepared road sedan with luggage capacity. Visible depth and connected assemblies take priority over decorative vents or racing graphics. |

Black treatment comes from the complete material palette and subdued component
finishes. The name and lettering remain fictional candidates subject to human
source/asset rights review; this document does not establish trademark clearance.

## Black materials that remain readable

Paint, trim, rubber, leather, fabric, glass and exposed metal use different
material responses. The construction source currently gives paint a dark
blue-neutral base with roughness 0.25 and a separate clearcoat response;
trim, rubber, leather, fabric and carpet use progressively broader reflections
and distinct surface structure. Dark wheel metal and exposed alloy remain
separate metallic groups. Those numerical responses are authored shader inputs,
not measured Audi paint data or final rendering acceptance.

Paint, leather and fabric microtextures are generated from named, repeatable
project seeds at a declared physical scale. Scalar/normal inputs use Non-Color
interpretation. Surface variation is intended to be restrained enough that
neutral studio illumination exposes curvature and panel fit rather than hiding
them in texture. [Material construction](../../../tools/vehicles/endurance_sedan/materials.py),
[microtexture construction](../../../tools/vehicles/endurance_sedan/microtextures.py).

No external photograph supplies a shipping skin, dashboard, upholstery or badge
texture in these constructors. Manufacturer diagrams and photographs remain
research evidence. Letter meshes made by the source's `text_mesh` helper use Blender's bundled Bfont
outlines. The [exact source-data license review](../../../reports/p1-018/research/font-license-review-20260911/REPORT.md)
now traces the current 25,181-byte PFB to a byte-identical historical embedded
C array carrying a GPL-2.0-or-later notice and NaN Holding BV 2001–2002 attribution.
This supersedes the earlier source-specific notice uncertainty. The notice
concerns the font data; it does not automatically settle the rights treatment
of generated glyph meshes, renders or the complete GLB. Human output/asset
rights review remains pending, and the typography is not claimed as original
font design or blanket CC0. Actual
neutral, daylight, overcast, dusk and night comparisons must establish the
finished material response and black-surface readability.

## Cabin and endurance equipment

The cabin uses an original hooded instrument area, a central display, physical
climate controls, a separate selector, supported seats and padded contact
surfaces. The hierarchy follows the functional relationships observed in the
reference cabin while keeping the graphics, labels, stitching and equipment
arrangement original. [Image-backed cabin observations](production-reference-appendix.md).

[Original packaging revision 5](packaging-revision-v5.md) addresses D035, the
actual driver-eye view in which the steering rim obstructed the cluster. The
target instrument anchor moves from source `(-.430,.550,.958)` m to
`(-.430,.400,1.050)` m, while the wheel center moves down from Z `.910` m to
`.855` m; its X/Y remain `(-.430,.210)` m. Column and stalk placement follows
the new wheel center. The 388 mm outside diameter, tilt, ratio, seat and driver
eye are retained. This is an original ergonomic correction, not a measured
Audi adjustment. The intended display position above the visible rim still
requires actual source/runtime confirmation, windshield separation and knee
clearance. Separate telltale and digit-driver defects remain separate from the
physical placement issue; movement of displayed segments does not establish
the displayed number's accuracy.

[Original packaging revision 6](packaging-revision-v6.md) raises the current
instrument anchor another 10 mm to `(-.430,.400,1.060)` m. A fixed-eye source
inspection found a small margin between the fuel digits and steering rim.
The eye, seat and wheel position stay fixed. The revision 5 coordinates above
are historical targets; the current readable dimension sheet and specification
now carry revision 17. The display still requires source and native runtime views
with warning, signal and steering states.

[Original packaging revision 4](packaging-revision-v4.md) moved both rear door
hinge axes to Y `-.625` m, retaining X `±.915` m and Z `.500` m, after the
source10 assembly exposed contact with the closed front-door return. The
bounded source07 shell search was a design aid; it did not certify hinge
hardware, trim or complete door clearance.

Revision 6 subsequently moved both rear hinge axes outward to X `±.942` m,
retaining Y `−.625` and Z `.500` m. It addressed the outer rear-door return
crossing the fixed B-pillar during opening, but later actual visual review
rejected its exposed pockets. Those axes are historical and superseded.

[Original packaging revision 8](packaging-revision-v8.md) selects concealed rear
axes at X `±.915`, Y `−.585`, Z `.500` m: 27 mm inward and 40 mm forward from
revision 7. Both physical pins on each of the four doors now sit at Z `.600`
and `.840` m. Separate 4 mm-radius pins, 4.5 mm-radius bearing bores and
6.5 mm-radius knuckles fit folded arms inside jamb pockets that terminate at
absolute X `.923` m. The named pin/bore interface has 0.5 mm radial clearance;
that specific bearing fit does not waive other moving-part requirements.
Front semantic axes and the other locked camera, occupant and mechanism
anchors stayed fixed in revision 8; revision 9 changes the side camera anchors
as described below. This is original fabrication, not a measured Audi hinge.

The retained native [rear-axis clearance-03 diagnostic](../../../reports/p1-018/qa/rear-axis-18/clearance-03.json)
checks 804,699 near-field triangle pairs across 101 poses per rear side. Its
guarded 1 mm result excludes exactly eight obsolete rear pin/leaf meshes and
separately records both closed rubber-seal interfaces. It supports rebuilding
the selected axis; it does not approve the new hardware, seal exceptions or
clearance between sampled poses. Complete-assembly and actual native visual
checks remain necessary.

[Surface and cockpit refinement](surface-refinement.md) gives the roof/window
envelope formed side rails and adds a physical matte shade above the instruments.
The roof was already C1, so the rail construction addresses an incomplete
assembly instead of changing the existing centerline interpolator. The shade
must reduce the actual windshield digit reflection while preserving the locked
eye and cluster positions. Fresh source and runtime views must demonstrate
both effects.

[Original packaging revision 9](packaging-revision-v9.md) moves the front-door
trailing boundary, glazing, seal, hem and latch forward 64 mm together. The
wider fixed B-pillar provides room for the concealed rear hinge while retaining
its revision 8 axis. A formed outer panel closes the upper pillar. The roof-side
beam returns inward beneath the roof and the shade's front edge retracts 75 mm
to clear the moving glazing and windshield/wiper geometry. These are coordinated
original assembly corrections, not new factory measurements. Every affected
opening, occupant access, mesh and reflection check still applies.

The folded hinge arm joins the outside of its separate bored sleeve
tangentially. This addresses a duplicate triangle produced by the earlier
arm-cap/Boolean triangulation without deleting or waiving invalid geometry.
The front arm knee also moves 12 mm inward. A narrowly recorded rear perimeter
seal engagement zone within 0.41° of the closed stop concerns that named rubber
interface only; it does not excuse unrelated rigid contacts.

Side mirror camera Y moves from `.610` to `.547` m, retaining X `±1.020` and
Z `1.065` m, because actual imported geometry enclosed the old cameras in an
opaque housing. Retained target/projection tests support the candidate position;
the final exported source must repeat them. The rear mirror camera stays at
`(0,.160,1.293)` m.

The detached rearview mirror stem is replaced by an original 3.5 mm-radius
bent arm and a 34 × 26 × 3 mm windshield button. The arm seats on the housing's
rear face and the button's interior face, while the button seats on the actual
inner glass plane. The reflecting surface remains fixed. The [native attachment
diagnostic](../../../reports/p1-018/research/surface-mirror-20/README.md) preserves
both old gaps, the rejected thicker candidate and the selected path's bounded
clearance checks. Complete cabin and runtime mirror evidence remains required;
the modeled glued mounting button does not simulate adhesive strength.

The prepared condition includes three crew within a five-seat interior. A
radio, crew log, tool bag, extinguishing equipment, tank restraints and accessible
service hardware make the endurance role visible. Each item must fit the actual
occupant, door and luggage envelopes; an equipment label alone is not evidence
of credible placement. The auxiliary center display is a branded modeled
display, not a claim of implemented navigation or communications.

The instrument cluster consumes explicit runtime state. Speed and fuel come
from the existing vehicle/run systems; gear and RPM use documented kinematic
estimates. Wipers, lights, pedals, steering and inspection mechanisms have
declared runtime contracts. Their intended behavior and verification evidence
belong to [runtime-plan.md](runtime-plan.md) and the acceptance matrix, rather
than being inferred from their modeled appearance.

## Visible systems and construction limits

The engine bay uses a longitudinal V8, inner-valley turbo forms, upper-engine
water-to-air charge coolers, visible charge paths and a distinct front liquid
radiator. This follows the relationships in the selected service references;
housing shapes, pipes and mounts remain original. Underbody design includes
an AWD driveline path, silencers, heat shields, undertrays, wheel liners and
structural attachment details. [Sourced assembly observations and limits](production-reference-appendix.md).

The main and auxiliary fuel stores remain separate. The original main reservoir
and trunk cell have declared nominal capacities, gross modeled envelopes and
an explicit mass account. Revised positions and pockets solve visual packaging
within the original car; they are not reconstructed factory tanks or certified
real modifications. The current specification, not the donor photograph or an
earlier checkpoint, owns those locations.

Panel gaps, inner returns, seals, hinge leaves and pockets must form a coherent
assembly through motion. Opening doors preserve conventional vertical axes;
hood and trunk use declared rotary hinges. Where a retained checkpoint collides,
the geometry and its attachments need correction. Sliding, teleporting or broad
contact exemptions would not explain the intended construction.

[Original packaging revision 7](packaging-revision-v7.md) raises the hood hinge
from source Z `.972` to `.990` m to clear the cowl near the closed position.
Its arms and bores follow the axis; the hood rear skin edge remains Y `.803` m.
The trunk trailing edge moves forward 47 mm, from Y `−2.432` to `−2.385` m,
with its cutout and hem following it so they clear the fixed optical housings.
Both closure perimeters use the pre-cut upper body surface, including nose bow,
and the hood crown falls to zero at its perimeter. Front fender insets restore
the 3.5 mm nominal hood side gap. These are changes to the original assemblies,
not adjustments to a factory dimensional reference.

The same revision keeps window belts, glazing, speakers and grab handles inside
their intended moving or fixed envelopes, and revises the auxiliary pump and
vent interfaces. Only the named compressible rubber floor gland uses the
declared 1 mm radial interference; rigid metal or unrelated contacts receive
no exemption. Continuous-looking opening motion and dense sampled clearance
checks support each other, but finite pose samples alone cannot prove clearance
at every angle.

The painted front bumper's bevel threshold changes from `.45` to `1.0` rad
after matched native renders isolated a triangular highlight to bevels on
smooth-profile sample joins. The [source15 diagnostic report](../../../reports/p1-018/research/surface-shading-15/README.md)
records the exact one-parameter comparison and a reduced evaluated triangle
count. It establishes a localized correction on that frozen source, while the
new production revision still needs full views and independent visual review.

The independent [source18 shoulder diagnostic](../../../reports/p1-018/research/surface-refinement-18/README.md)
subsequently isolated the remaining broad highlight kink to sparse cross-profile
sampling. Its targeted cross-only candidate improved the actual inspected band
for 884 additional isolated bumper triangles. The production constructor applies
extra samples only to front rings at source Y ≥1.82 m, with an explicit zipper
transition between unequal ring sizes. Source19's failed derived mesh and later
corrections remain retained. The local diagnostic cost cannot be substituted
for a complete revision's total triangle count, contact checks, LOD silhouettes
or final visual acceptance. The source21 front-fender bevel is a separate
creation-time refinement, with actual matched images required to establish its
local effect; an unavailable modifier in the baked source20 prevented the
proposed isolated angle test there.

## Formed joints and measured mounting construction

[Original packaging revision 10](packaging-revision-v10.md) replaces the layered
bright A-pillar rods with a single closed, curved painted ribbon. Its 12 by 3
surface spans, tapered 4 mm crown and 18 mm inboard return give the windshield
and front-door aperture a formed structural boundary. The upper return meets
the roof without changing glass hardpoints. The roof reinforcement is shortened
to source Y −1.230 through +.100 m; fitted headliner relief, trimmed moving-door
inner returns, visors and mount pads preserve the cabin envelope. The factory
photos informed construction relationships, not these original coordinates.

The same revision wraps the headlamp around the actual pre-cut fascia rather
than placing a flat optic against a curved opening. A 442 × 135 mm closed cover
envelope fits a 449 × 142 mm aperture, with a 435 × 127 mm clear lens recessed
2 mm. Side, top and bottom returns and the projectors follow the shared body
surface. The [source22 fit measurement](../../../reports/p1-018/research/lamp-fit-22/README.md)
supports that bounded assembly correction; it is not a factory lamp copy or a
complete-source appearance approval.

[Original packaging revision 11](packaging-revision-v11.md) gives the A-pillar
foot an explicit structural joint. The original closed pillar is divided at
source Z 1.05 m: the lower piece joins the body, and the upper closed piece
meets it on the same planar butt. A convex local fender relief targets a 3.5 mm
gap while preserving the glass and exterior envelope. Existing surface corner
normals are retained on unchanged outer sheet; new butt faces use their own
flat normals. This avoids a shading stripe caused by the semantic split, while
keeping the actual structural mating interface measurable.

The [retained native A-foot study](../../../reports/p1-018/research/a-foot-23/README.md)
found matching closed cap areas and zero shared solid volume, with 3.49819 and
3.49871 mm left/right fender gaps. Its 202 sampled front-door poses support only
that selected geometry scope. A topology dissolve that displaced the exterior
was rejected and retained. Its raw +576 triangles are an isolated cost, not a
substitute for the complete rebuilt source's budget, topology or export checks.

The front protective floor now sits in fitted pockets. Each 4 mm panel spans
Z .1355–.1395 m, with a 2.5 mm perimeter gap and four 12 × 12 × 6 mm spacers per
side reaching a pocket ceiling at Z .1455 m. The splitter is 1.66 m wide and
12 mm thick at Z .207–.219 m. Its curved outline follows the fascia, projects
at most 20 mm, stays behind the original nose limit Y 2.4 m and seats in a
2.5 mm-gap recess on four 4 mm-deep supports. These details explain how the
visible panels attach; they are not simulated aerodynamic load cases.

The concealed front hinge-arm knee moves from 87 to 89 mm inboard of its axis
to correct a measured near-full-open shortfall. The separate closure-arm bore
grows to a 5.3 mm circumradius: its 12-sided opening leaves about 1.1194 mm
minimum radial clearance around a 4 mm pin. The named 4.5 mm-radius bearing
interface keeps its separate 0.5 mm radial mating allowance. This local bearing
allowance does not excuse unrelated rigid contacts.

The original caliper arcs use eight subdivisions over 56° instead of twelve.
At the largest 220.5 mm front-bridge radius their maximum circular chord error
is under .412 mm. This corrects the earlier 219.5 mm/.410 mm calculation;
the front rotor radius is 199.5 mm and its bridge extends another 21 mm.
Endpoints, radii, thicknesses, brake dimensions and every modeled
component stay fixed. This bounded topology saving reserves geometry for real
mounts and body joints; the finished wheel's appearance and complete LOD cost
still require actual inspection and measurements.

## Reflection diagnosis and cockpit warning placement

The later [source22 shoulder experiments](../../../reports/p1-018/research/shoulder-normals-22/README.md)
rejected a normal transfer, structured front cap and several local profile
fairings. They retained the measurable C1 curvature variation, but the diagnosis
of the apparent doubled band changed after actual
[separated-light renders](../../../reports/p1-018/shoulder-fairing-11/light-evidence.json).
The unchanged surface produced one connected highlight from the key and one
from the top strip; the combined image contained both. Independent visual
review did not identify a substantive folded surface in those bounded crops.
The current profile is retained. This does not erase the earlier localized
bevel/sampling defects, adopt a rejected fairing, or waive final full-view review.

Revision 11 moves the runtime warning row to `(16,0,480,28)` pixels in the
512 × 192 instrument viewport, with 20 px type. The Blender preview uses local
U/V `(0,.061)` m and 9 mm lettering. The eye, wheel and instrument anchors and
existing warning thresholds stay fixed. Revision 11 positioned the low-fuel
source preview; revision 12 adds all six existing runtime warning conditions
to source inspection. Their actual glyphs still need source/runtime verification.
Those indications expose declared state, without adding mechanical,
fuel-transfer, thermal or electrical simulation. Fixed-eye source/runtime
captures must establish their actual legibility.

The construction pipeline preserves exact evaluated loop triangles and their
corner normals, UVs and material assignments before subsequent joint/cavity
operations. Retained failed source24 and source25 attempts exposed a null
Boolean material slot and a duplicate evaluated body triangle respectively;
they are failed checkpoints, not accepted outputs. Corrections preserve the
existing material/topology gates. Export tolerances of .05° for normals and
2×10⁻⁶ per UV component remain encoding comparisons, not relaxed geometry limits.

[Original packaging revision 12](packaging-revision-v12.md) records the rear-sill
correction after actual source23 rays found a 45 mm open slot behind the trunk
lid. The concave cavity spans X ±.790 m. Its Y/Z outline is `(-2.430,.295)`,
`(-1.500,.295)`, `(-1.500,.945)`, `(-2.3885,.945)`, `(-2.3885,.880)`,
`(-2.430,.880)` m. Thus its upper portion stops at Y −2.3885 m and leaves a
3.5 mm gap to the unchanged lid edge Y −2.385 m; its lower portion preserves
the authored bag/carpet volume. Adjacent optical cuts retain X/Y and span
Z .8055–.9315 m, with center .8685 m and height .126 m. The independent
source23 candidate supports only its bounded restored sill, including a
1.2858 mm refined trunk clearance lower bound. Full rebuilt geometry, the
visible closed seam, final media and export evidence remain separate checks.

The six warning labels use first-true priority: fuel below 20 L, damage above
.05, cooling condition below .4, tire condition below .3, any opening above
.001, then handbrake above .02. Source inspection controls directly set the
posed opening fraction; runtime considers both current and target fractions.
Default damage/handbrake is zero and cooling/tires is one. The source gear is
manually selected −1/R, 0/N or 1–7; runtime also estimates P. These display
previews do not implement gearbox, fuel-transfer or condition simulation in
Blender, nor replace actual native-state and glyph verification.

[Original packaging revision 13](packaging-revision-v13.md) supersedes the
earlier projecting tail-lamp boxes with a shared fitted optical assembly. All
layers follow the original pre-cut rear body Y(X,Z), rather than a Z-independent
curve. The planar .423 × .320 × .127 m recess is centered at
`(side*.65,-2.4225,.868)` m; Z .8045–.9315 replaces revision12's optical cutter
while preserving its corrected trunk sill. Cover/backplate are .414 × .116 m
at Z .868, with depth offsets 0/.003 and .081/.087 m. Four walls/returns close
each lamp. Guides and emitters sit at depth .018/.023 m; their original X/Z
identity and semantic light anchors stay fixed.

The upper interior tapers by
`Znew=Zold-.010*(depth/.087)*clamp((Zold-.868)/.058,0,1)`, keeping the outward
contour unchanged and lowering the hidden rear edge by10 mm. Upper walls use
the exact17 cover/backplate X stations plus two outer margins. This fixes a
real nonplanar seating overlap: the same full-triangle gate rejects the prior
grid and accepts the shared grid without a larger numerical guard. The
[immutable v4 recipe and failed candidates](../../../reports/p1-018/research/rear-lamps-29/HANDOFF-v4.md)
retain actual matched native crops,231 optical pair checks,24 bounded seats,
1.881516 mm minimum unrelated optical gap and complete opening-domain evidence.
The lamp assembly saves160 triangles; these are candidate measurements, not a
final source/LOD acceptance claim.

The same revision corrects actual rigid strap/tank crossings and a pump OUTLET
route entering the auxiliary tank's lower corner. Strap return centerlines use
rear/front Y −2.171/−1.669 m and bottom/top Z .409/.702 m, preserving8 mm radius
and four sides. The6 mm outlet hose follows
`(.49,-1.99,.460)`, `(.47,-1.99,.400)`,
`(.401333333,-1.997333333,.364)`, `(.35,-1.99,.210)`,
`(.35,-1.36,.210)`, `(.43,-1.27,.210)` m. It rejoins the original gland axis.
A7.5 mm-radius12-sided pump bore extends12 mm inward beyond the hose start.
All tank envelopes,75 +100 L nominal capacities,2,400 kg running mass, floor
passage, pump nominal outer box envelope, global/occupant hardpoints and gameplay policies stay
fixed. The changed Boolean may change evaluated pump bevel vertices; unchanged means its nominal outer box envelope. [Native fixture checks](../../../reports/p1-018/research/packaging-interfaces-29/fixture-candidate03.json)
cover4,786 static pairs and add92 triangles, for a combined candidate delta of
−68 with the lamps. Individual socket, flange, weld and rubber-gland regions
are specified; whole-pair contact exemptions are not acceptance evidence.

Source31's [read-only native input binding](../../../reports/p1-018/research/source-input-binding-31/asset-input-inventory.json)
confirms all six packed original texture payloads and the retained Bfont
ancestry. It remains a verification checkpoint; canonical shipping source/GLB
hashes and final human reviews are pending. The passive modeled fuel hardware
does not implement fluid transfer, pumping, sealing performance or certification.

[Original packaging revision 14](packaging-revision-v14.md) gives both cabin
protective trays real body recesses after actual source31 exposed about1.11945 L
of solid intrusion per tray. Their386 ×1720 mm plan and135 mm ground minimum
stay fixed; the top moves to Z.1399 m, making4.9 mm thickness. A left-then-right
Boolean cut creates1.5 mm perimeter and2.5 mm overhead gaps. Each side has four
separate12 mm-square mounting pads, spanning Z.1399–.1424 m, at absolute X/Y
`(.628,-.90)`, `(.628,-.20)`, `(.35,.45)` and `(.56,.45)` m. Each complete upper
and lower footprint is a measured planar seat. Original evaluated triangles,
corner normals and UVs are frozen once before these cuts; bounded new-vertex
cleanup protects the existing exterior. This is a fitted removable assembly,
not an exemption for a panel inside the body.

The [native recipe and failures](../../../reports/p1-018/research/static-fit-31/HANDOFF-candidate03.md)
retain12,055 tray/pad-versus-all pairs, sixteen full144 mm² contact footprints,
an intrusion negative, and matched actual CPU views. The overlapping black
rectangle in the source31 underside becomes a continuous tray with a narrow
perimeter joint. Its mounting pads are hidden behind the assembled panel in
that view, so their complete-geometry certificate remains separate evidence.
The candidate adds168 triangles and measures149,880 LOD0, leaving120 beneath
the ceiling. This is a component result; all rebuilt source/LOD/export and
continuous-motion checks remain required.

The same revision raises the two top tank straps0.1 mm, lowers only each trunk
offset-arm terminal1.2 mm, retains a vent union8 mm bore with9.7 mm outer radius
and1.7 mm wall, and moves only the rear mirror screen0.1 mm in source−Y. The
trunk hinge/knee, rear camera/anchor, fuel envelopes and capacities remain fixed.
Those changes provide measured nonmating clearance while preserving the
individually declared strap welds, arm bearings and flange seats.

The roof-side reinforcement is explicitly a finite formed welded flange within
the roof skin. It is not a zero-volume seat. Complete evaluated inner/outer
facet proofs bound its contact to absolute X.592–.741 m and Y−1.230–.100 m.
Revision14 permits at most.65 mm penetration from the inner skin and requires
at least.55 mm outer skin remaining, with the unchanged1 µm encoding guard.
Source31 measures.602298/.458956 mm inner penetration and.599820/.742814 mm
remaining outer skin left/right. No rail surface protrudes through the visible
roof; the final shading/appearance review remains separate. The two existing
main-tank crossover connections are finite9 mm-radius coplanar butt seats at
X±.100 m. Full opposing halfspaces exclude solid intrusion, and the10-gon caps
share232.081 mm² contact. These declarations describe assembly construction;
they implement no welding stress, fluid transfer or sealing simulation.

Actual source32 has been reopened and its [input binding](../../../reports/p1-018/research/source-input-binding-32/asset-input-inventory.json)
confirms all six original packed texture hashes and Bfont ancestry. The
[native17-row comparison](../../../reports/p1-018/research/static-fit-31/compare_source32_03.json)
checks actual indexed triangles and all corner normals, UVs and materials;
the maximum corresponding vertex displacement is59.605 nm, within the unchanged
0.1 µm comparison. Shipping source/GLB bytes, complete QA and human
rights/visual/driving approvals remain pending. Earlier checkpoint evidence is
linked to its actual source and is not silently transferred to the rebuilt car.

## Original finish and fabrication revision 15

[Packaging revision 15](packaging-revision-v15.md) replaces the raised tire
shoulder strips with 56 genuine recesses per tire. A closed three-station,
four-sided cutter follows each original shoulder; the 64-segment tire body
and four 4 mm circumferential channels remain. Candidate surface samples
measure 1.147–2.052 mm depth. Original smooth normals transfer only to the
surviving original rubber; cut walls retain actual normals. This describes
visible tire construction, not compound behavior, drainage or tire durability.
The failed dented-normal trial is preserved, and final rolling/clearance
verification remains required.

Twelve existing components provide a measured 1,592-triangle reallocation:
four projector rings and four exhaust lips use 24 rather than 32 path stations,
the steering rim uses 48 rather than 64, and two turbo casings plus the rear
differential use 20 × 10 rather than 24 × 12 UV tessellation. Nominal bounds,
thicknesses and parts remain. Bidirectional vertex, triangle midpoint and
centroid samples differ by at most 2.883 mm, within the existing 5 mm global
modeling tolerance; this is not a continuous Hausdorff proof or a final
appearance pass. These original detail choices keep the fixed triangle
ceilings while supporting actual tire recesses.

Two formed header walls close three actual cabin sightlines that previously
reached the headliner through an unfinished roof-side recess. Each wall stays
within absolute X .662–.668 m and Y −1.230–+.100 m. Four new contour points
are integrated into each existing closed rail section, retaining the roof
flange. The exact 25-station lower tables include B-post relief; the rejected
outward version collided with a rear door window. The isolated inward wall
clears 232 opening domains by at least 13.846 mm. The complete rebuilt rail,
finite roof weld, original sightlines and actual appearance remain separate
source33 checks. [Frozen header handoff](../../../reports/p1-018/qa/roof-header-32/handoff04.json).

The broad windshield ghost was initially described as a reflected rear cabin.
Actual source32 ray and colored-surface isolation instead identifies the
instrument shade and binnacle; removing rear geometry does not remove it.
At night a separate ghost comes from NavigationTitle sharing the headlight
emission driver. The accepted original material candidate uses existing
matte carpet response as flocking on the shade, two shade wings, binnacle,
dashboard upper and navigation surround. Four static navigation/climate/radio
labels receive one dedicated constant-emission 0.2 material, independent of
the lights. The full object list and linear shader values are locked in the
dimension sheet and specification. No navigation, climate or radio operation
is implied.

[The immutable ten-object handoff](../../../reports/p1-018/research/windshield-reflection-32-01/handoff-05.md)
retains the original source32 baselines, all isolation trials, five matched
lighting comparisons and exact input/material hashes. It verifies unchanged
geometry, normals and UVs across all 1,515 mesh objects, adds zero triangles
and changes 23 shipping materials to 24 within the 32-material budget.
Glass, lighting and the rear cabin remain intact. Existing glass is a portable
alpha/transmission approximation, not an exact laminated-glass simulation;
display-referred luma reductions are not physical lux measurements. This
addresses the causal forward-cabin surfaces without claiming reflection-free
glass. Final source33/native visibility and human visual approval are pending.

All research uncertainty, the original engineering benchmark, dimensions,
fuel capacity, fixed mass, occupant/hinge/contact anchors, gameplay policies
and source/font rights boundaries remain unchanged. Prior checkpoint results
retain their actual source bindings; final canonical source, GLB and media
hashes must be rebound after construction and independent QA.

A modeled engine bay does not establish turbo operation, heat rejection,
lubrication, exhaust flow/acoustics, emissions performance, air-spring leveling,
fuel transfer or restraint simulation. The existing custom four-raycast
RigidBody3D remains authoritative, and researched vehicle ratings do not replace
the Starter or HighSpeedValidation policies.

Final approval requires actual source/runtime inspection, the declared machine
and platform checks, and the outstanding human visual, usability, driving-feel
and source/asset rights reviews. This rationale describes design intent and
traceable choices; it does not mark those gates complete.

## Revision17 original restraint construction

The current source34 uses newly routed stowed cloth, finite guide grips, open rectangular lower clamps and small metal tabs on the existing seat rails. The center web and its separate buckle branch pass through the measured empty seat-partition gaps. Existing seats, body, materials, vehicle hardpoints and runtime policy are unchanged. Continuous ribbon width vectors avoid twisting through themselves; this is a closed modeled cloth surface, with no occupant or load simulation. Rejected candidates08–10 and the unbuilt revision16 lock remain as development evidence.

[The source34 native/actual-frame handoff](../../../reports/p1-018/research/source34-handoff-01/handoff.json) verifies only the stated assembly correction. [The final source-input inventory](../../../reports/p1-018/research/source-input-binding-34/asset-input-inventory.json) retains all six unchanged original microtextures and the separate Bfont outline ancestry. [The reference-archive audit](../../../reports/p1-018/research/external-retention-review-01/review.json) distinguishes excluded manufacturer research from existing, separately attributed environment assets. No visual, source/output rights or trademark approval is inferred.
