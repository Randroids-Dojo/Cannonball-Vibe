# P1-018 visual refinement after source34 inspection

Date: 2026-09-11. Status: scoped; candidates not accepted. Authority: ADR-0012 and P1-018.

The latest user asked which model issues remain. Actual source34 daylight/front3q, open-inspection-worklight/rear_door and neutral-cabin/upholstery renders were inspected at 2560 by 1440. Technical closure and animation certificates do not establish adequate automotive finish.

| Target | Visible issue | Correction and observable acceptance |
| --- | --- | --- |
| VF35-01 | Thin straight window rails and abrupt pillar transitions | Formed, supported cross sections with controlled curvature and coherent roof/pillar joins; no exposed liner or disconnected lip in the same exterior and grazing views. |
| VF35-02 | Rectangular side-mirror boxes and flat cooling fascia | Tapered aerodynamic housings and recessed/layered grille construction, preserving usable mirror optics, camera clearance, cooling openings and original identity. |
| VF35-03 | Broad flat rear-door returns and stepped inner arches | Continuous stamped/trimmed transitions with retained four-door travel, real wall thickness, seals and hidden support; no new intersection or false floating cover. |
| VF35-04 | Blocky seat, armrest and door-card transitions | Shaped cushion and trim contours with grounded seams/piping at physical scale; retain occupant envelope, restraint hardware, pedal and sightline clearance. |
| VF35-05 | Broad bright reflections dominate finish and visibility | Compare materials under the same lights before changing either; retain dielectric black paint and credible glass response. Diagnostic worklights do not define ordinary appearance. |

Lead is sole scene/export writer. Start with separate candidate35 paths. The interactive source34 file is not overwritten. Agent research and QA remain reports-only. Locked engineering hardpoints and budgets remain unchanged. New source requires new source-bound bake inputs, evaluated/exported checks, full affected motion/clearance and LOD validation, native captures and measured performance. Historical evidence is preserved and cannot close changed-source gates. The final art, rights, driving-feel and usability approvals remain human gates.

At23:20UTC, independent native QA identified N34-LOD-01: the rear paint changes
abruptly at the LOD0/1 transition near28m. Direct shipping-GLB analysis finds
large interpolated normal changes with nearly unchanged positions and identical
paint material. Before implementation, the lead scopes a bounded LOD correction
in `endurance_sedan/optimization.py` and a project-owned corner-preservation
helper: keep fixed-body paint vertices with source Y below-2.10m and the complete
separate trunk-paint batch, retaining their exact triangle positions, corner UVs
and original normals. Keep all semantic parents and the200,000-triangle total
budget. The research candidate costs6,808 additional LOD1/2 triangles and has
exact surface positions on11,885 rear rays; maximum sampled normal difference
is0.271051degrees. These are candidate measurements, not final runtime proof.
The final generated source requires complete protected-corner correspondence,
validity, budget checks and actual matching Godot transition footage. Retain
the rejected normal-transfer trials and original visible pop.

At23:48UTC, the independent native LOD probe also finds four zero corner normals
in the clean source34 LOD2 hood paint batch, and nine after rebuilding it. The
installed official glTF exporter substitutes its UP vector for zero normals;
the resulting unit-length GLB normals therefore do not establish a valid
authored hood shading field. Before implementation, extend the exact complete
paint-batch preservation to the hood's existing rigid parent. The source34
candidate adds2,702 triangles across its lower LODs, within the unchanged total
ceiling when combined with the rear correction. Retain the zero-loop inventory,
exporter source/hash, complete native normal guards and actual full-vehicle LOD
comparisons. This does not accept unexamined front/side shading or change the
same-LOD platform bake tolerances.

The native pilot13 latch probe at23:50UTC finds the four latch faces buried
behind their own door returns:7.2045mm on the front pair and58.0728mm on the
rear pair. The scope of VF35-03 therefore includes fitted latch pockets and
visible faceplates/fasteners on the actual return surface, together with the
broader formed recesses. The proposed housing stays under its existing driven
door parent; front/rear latch center heights are.795/.935m and the sideward
center is absoluteX.844m. Fit orientation and depth must come from the rebuilt
panel, with an explicitly measured flange seat and full opening clearances.
This is modeled latch hardware, not a new latch, lock or crash simulation.
Keep the original native observation and any rejected fit candidates.
At2026-09-12T00:20UTC, VF35-01 includes an integral connected A/header return.
The original-design proxy is derived from the actual pilot13 A inner edge and
contains no donor geometry. QA return03 intercepts all84,157 recorded gap pixel
centers and preserves the complete-domain moving and nonmating fixed clearance
bounds. Adopt its exact clipped halves as editable construction inputs. Union
the front half into each A pillar and the rear half into each roof side rail;
their new finite butt lies at float32 Y0.10509999841451645m. Each paired cap has
13 opposite triangles and approximately179.031mm2 area. This is distinct from
the retained A/roof-skin and A/body joints. Actual unions, attachment continuity,
attributes, budgets and rendered appearance must pass before acceptance.

Pilot19's new front latch heads fail the unchanged1mm opening-clearance check
against the structural body at opening fractions.0078125..0234375. The fitted
housing and rear hardware pass that same targeted motion run. Recess the front
and rear screw heads into fitted faceplate seats, within the plate's existing
outer envelope, and rerun the changed hardware plus finite seat checks. Keep
the failed witness records; do not relax the motion threshold.

On2026-09-12, D050 inspection-floor diagnosis finds a source-level receiver
mismatch. `InspectionFloorContact` under `SedanPresentationFixture` has a
separate visible `InspectionFloor` sibling; the contact-shading allowlist
recognizes the gameplay road and integration course only. The historical
presentation evidence has ray contacts and stance, but no live decal snapshot.
Before implementation, scope the exact debug fixture in the existing explicit
receiver allowlist and capture actual contact-shading state in presentation
QA. Runtime owns only `game/Vehicle/VehicleContactShading.cs` and
`game/Automation/EnduranceSedanPresentationScenario.cs` for this correction.
Keep gameplay ride height, opacity, masks, supported renderers and all existing
receiver behavior unchanged. Require positive, nonreceiver and cleanup checks
and a matched actual source34 side render. This fixes fixture eligibility;
visible D050 acceptance still requires review of the rendered result.

The retained source34 A ribbon itself has17 independently verified strict
interior crossing pairs per side; restoring it does not fix the inner-sheet
construction. Separate barycentric/plane arithmetic confirms an11.700179mm
intersection segment between nonadjacent triangles. The cause-guided candidate
keeps the original outer sheet and18mm depth, blending its cross-width inner
directions to one coherent common direction over outer Z1.10..1.24m. The
original Z1.05 body butt is below this transition. Both candidate218-triangle
ribbons pass all23,653 self-pairs, but surrounding fixed/moving clearances and
attachment footprints must be verified before adoption. Reject source20/21
unions and the original self-crossing ribbon despite their earlier incomplete
incidence-only checks; retain all failure evidence and strengthen source QA.

Before the next production build, VF35-05 adopts a bounded original shoulder
fairing in the pre-cut body construction, not an exported-mesh warp. Its
quintic matches position, tangent and curvature at cross-profile parameters
5.65 and6.35, with longitudinal weight rising from0 atY1.90 to1 atY2.20m.
Keep the original evaluator and floating-point operation order outside this
support. The four retained matched candidate images show a smoother upper
highlight; the broader lower highlight knee remains and is not claimed fixed.
Research's whole-profile sampled displacement bound is0.698549mm; the50.050um
local vertical turn is recorded rather than hidden. All downstream lamp cuts,
shared body-surface references and hood construction remain in their existing
order. The rejected post-cut warp tilted an optical return facet; the pre-cut
candidate retains its plane within2.385nm and minimum3.499985mm lamp/hood gap.
Fresh integral-source validity, fits, budget and rendered comparisons remain
required. No exterior identity or real-car dimension change is introduced.

The independent whole-LOD0 self audit of pilot22 on2026-09-12 identifies383
exact crossings in15 meshes, distinct from394 retained approximate-predicate
artifacts. In addition to both A ribbons, they affect four window frames,
four glazing seals, two rear inner hems, Door_FR, FrontBumper splitter-pocket
faces and HandleMount_-1_1. These are original construction defects, not
permission to relax the shared-simplex or triangle-area tolerances. Before
further modeling, VF35-01/03 includes genuine circular corner fillets with
radius exceeding the seal/frame inward section, supported hem bends, and
local pocket/pad repairs. Preserve the original outer engineering envelope,
rig, material identities and runtime budgets; recheck complete self geometry,
fixed assembly seats, moving clearance and actual close views. Lead alone
writes source geometry. Research owns reports-only cause/repair proposals for
the splitter pocket and mounting pad; QA independently reviews the result.

The00:20UTC header-half proposal above is superseded by the validated coherent
18mm A ribbon and refitted complete return03 on pilot25. Join the actual valid
A, full return and roof rail before splitting the entire union atY.1051m.
Independent complete sections are190.980968/190.983642mm2; the old179.031mm2
proxy cap no longer describes the final joint. All85,327 current primary gap
pixel centers are backed by this proposed return, and its front face is buried
at least.134057mm in the real A. Native unions, matched full caps, original
outer-sheet preservation, continuous moving clearances and rendered views
remain required. Pilot25 retains the exact original lower cap in both directions.

The pilot25 window fillets pass exact self checks, but its rear inner hems still
cross at their acute upper rear turn. Native14/18/22mm circular-bend trials all
remove that defect; choose14mm as the smallest tested departure from the original
6mm-radius rolled hem path. Keep the existing514mm arch centerline stations and
material/parent, and verify supporting panel fit and all opening angles. The
single headliner mount repair uses exact shared-edge clipping before one native
float32 encoding, removing spurious internal extrusion walls while retaining
its original footprint and lower seat. These remain modeling corrections within
VF35-01/03, with no new interaction or physics claim.

Pilot27 now has valid combined A/rail topology and exact self geometry, matched
complete finite caps, and retained original A exterior/lower-body seats. Its
shipping LOD0 is151,552 triangles, so it is not budget-eligible. Adopt the
fourteen researched reserve chamfers (research/chamfers35-14-01/handoff01.json,
SHA6a234d61baa82bfdd5fc873080cd1aea412aee9e099ab6b484162600a18e86e6)
to recover896 triangles. They retain every flat mating face and the complete
convex envelope within the unchanged1um guard. Their maximum curved-edge
retreats remain recorded by object; these are deliberate straight manufactured
chamfers, not a hidden budget increase. Further measured savings are required.
The broader exact self gate is now part of the full source front door, with
native malformed-input and independent exhaustive predicate controls. A clean
incidence inventory alone did not detect the retained source34 defects.

The additional16 sub4mm hardware chamfers are now measured and adopted before
fresh construction (research/chamfers35-additional-01/handoff05.json,
SHA6930110ff983f265bb51154b1a88bdc9e8ec8e261e239781d376ebc42f9f3229).
They save1,024 triangles with all96 original flat mounting faces exact and
9,290 complete source/candidate triangle domains checked; maximum whole-surface
retreat is1.267982mm. Rotated wiper-rail/clip corner AABBs shrink as recorded;
physical blade, seating faces, pivots and spring travel remain fixed. Full
fresh wiper and assembly checks are still required.

The stricter final-LOD diagnostic finds inherited and simplification-related
self folds in the historical source34 lower models. It checks every final
index-connected shell and explicitly counts cross-shell pairs outside this
certificate; it does not misuse pre-decimation component ranges. Before final
export, rebuild from the corrected original assemblies and repair remaining
simplification defects within the existing200,000 total ceiling. Keep original
LOD failures and actual transition captures. The source QA front door gains
separate final-shell and controlled finite-finish interface stages as these
checks become reusable; historical14-stage evidence retains its original scope.

At2026-09-12T02:00UTC the fresh revision18 preview01 has149,650 LOD0 triangles,
but the exact whole-mesh scan finds three new crossings in FrontFender_R after
the pre-cut shoulder correction. Preview02 uses the reviewed attributed
Boolean diagonal repair on its three witnessed n-gons: all1,022 vertices,
2,040 triangles and5,928 unaffected corners are exact, with maximum common
normal change0.009890degrees. The left fender is unchanged. Both fenders now
join the existing explicitly named final-panel repair scope; full rebuilt
source self and downstream lamp/body comparisons remain required.

The pilot27 upholstery check independently rejects18 cushion seams, with
unsupported route intervals up to26.72mm and complete1mm thread bands separated
from the pad by1.221..60.606um. The bound on maximum90um penetration alone did
not establish continuous support. Preserve the failures and exact witnesses in
qa/pilot27-upholstery-support-01/02. Preview02 intersects every actual native
pad facet with the intended seam plane, then forms mitered four-point sections
with the same0.6mm radius and15% burial. All20 cushion routes, eight back piping
routes, two finite header butts and12 fitted latch interfaces now pass the
independent complete42-interface stage; eight shifted geometry controls reject
(qa/finish-interfaces-fresh35-preview02-01.json,
SHA341e158514f1d5817babb82b877e97cb99c5c4ca37d5cff53b512846874f6215).
These extra facet knots add768 triangles: preview02 LOD0 is150,418 and remains
over budget. Recover this cost through measured small hardware chamfers before
any final-source or export acceptance; do not increase the ceiling.

Actual pilot27-to30 A/rail indexed geometry is identical. The independent
matched normal/render review confirms the two former first-hit normal errors
near52degrees now agree with their owned wall fields within0.00331degrees,
and the triangular and long-rail reflection artifacts are substantially reduced
(qa/pilot30-header-normal-refs-01/review.json,
SHA8cc5d216d56c3c0a4f9abaf31d811bdb9ab7dfe69705eca1e6ddaeed7fd791ba).
The short folded upper junction remains visible. This fixed-camera result is
bounded evidence, not final multi-light art or human approval.

The final ten measured small optical/plate chamfers on preview02 recover640
triangles, funding all newly supported thread facets with a projected149,778
LOD0 count. All60 complete flat faces are exact; all20 before/after meshes
pass native topology and exact self checks. Complete bidirectional surface
coverage has5,052 terminal domains, zero unresolved, maximum0.845425mm retreat,
and maximum convex-envelope float encoding excursion0.220337um
(research/chamfers35-final10-01/handoff06.json,
SHA5dea8322ae23d5af7b45fe958cb422c87ad001054dd9564217bd82ab98ff7d67).
The exact ten names are declared in `finish_refinement.hardware_chamfers`.
Rebuilt optical seats and matched lamp/emission views remain required.

The new short header return legitimately extends beyond the old roof XY chart;
the full static gate therefore retains its uncovered polygons as a separate
finite region, rather than silently discarding them. Every point lies at
least14.755mm below the complete actual roof. The revised certificate requires
the narrow revision18 header region and a guarded1mm vertical lower bound for
every complete polygon; all original flange-intersection, penetration and
outer-skin limits stay active. Two controlled region/separation failures are
added to the three original fitted-interface controls. The first failed static
run is preserved as source35-fresh-preview02/static-interfaces01.json.

The exact-old-encoding normal comparison is retained as failed. A separate
native same-values roundtrip reproduces every changed A exterior normal
bit-for-bit:61 left/64 right corners, maximum0.0027723/0.0028086degrees. This
attributes the bounded difference to Blender custom-normal encoding, with no
requested exterior-field redesign, rather than calling those bytes identical
(qa/pilot30-header-normal-roundtrip-01.json,
SHA931fdb017b34b6586a44c12f139b7a1e15fbefc79d5a2984705448f0c95f61d6).

The controlled lower-LOD repair now selects16 declared source-parent/material
groups, preserves component identity before simplifying, and batches only
after closed/self-clear candidates are established. Its final component ranges
are constructed after simplification; unmodified batch-wide paths retain only
explicitly labeled original input membership. The actual RotorVane name is
added to the existing subpixel hardware policy, retaining all LOD0 vanes.
Native helper replay and12 ratio/material/parent/fold/cleanup controls pass
(research/lod35-shells-01/recipe09.json,
SHA2ad42a50ad576ec024ddb26b82433224c3d09791c64d26e37a14cac1d6d53a69;
helper SHA1fce28b1ce6532af31faa45aa9abddbd9c55d7e272ca9f536043a2c6c1b2df6e).
The private LOD2 roof at0.26 has five actual zero normals before rebatching;
the0.5 fallback passes, adding244 triangles. Source extraction and pre/post
export-batch checks now reject raw zero/nonfinite/nonunit corner fields before
exporter fallback can conceal them. The unchanged unit-length tolerance is1e-6;
the real positive roof's maximum deviation is1.522808e-7. Rebuilt source35
budgets, all final lower shells and actual motion/lighting remain required.

At2026-09-12T02:35UTC the fresh full03 source measures149,778 LOD0,
32,022 LOD1,17,940 LOD2 and24 collision triangles:199,764 total. Its source
SHA ise5998cd22eda7f2bb72aaf9e21f357c9f0d9d978007d5c283787c99cc27028af.
All evaluated topology counters pass, but the medium static optical-glass
batch retains eight actual zero normals. This is a failed shading baseline,
not a final asset. The seventeenth semantic selection is therefore LOD1,
Visual_LOD0,Material_OpticalGlass, using the independently checked helper09.
The complete17-key handoff is research/lod35-shells-01/handoff16.json,
SHA160a0fa9f2b66f35a6d79144a19006f4e35fd6725358384e5a14e8025dce45b3.
Its210 composed batches and848 indexed shells have finite unit normals and
375,079 passing exact intrashell candidates;47,698 cross-shell candidates
remain explicitly outside that self certificate. Fresh full-source results
must replace these composed pilot measurements before delivery.

The full03 inventory retry is retained: an initial diagnostic request used
one opening step and correctly failed the extractor's minimum-ten assertion.
The retry used the required100 steps and645 native poses, with exit0. An
additional broad Ruff invocation over the historically compact vehicle tools
reports949 mostly one-line-statement/style findings; it is not the declared
map-pipeline lint front door and does not supersede that required check.
Do not silently call this additional lint successful or reformat frozen,
source-bound validation inputs while their independent review is running.

The actual fresh02 visual comparison still shows an exposed squared leading
roof-rail lip, abrupt lower arch/apron terminations and a broad nearly vertical
front fascia. VF35-01/02/03/05 therefore remain open. Before further changes,
bind the visible pixels to native semantic faces, then pilot controlled
formed profiles at fixed cameras. Preserve the measured inner header butt,
roof attachment, front axle/cowl/hood hardpoints, maximum dimensions and
aperture/optical fit. Any new exterior curvature is an original styling
decision and requires updated numerical bounds plus source/runtime evidence.

The next reports-only fascia pilot replaces the terminal body's boundary-only
n-gon with three interior radial stations and a central point, then tests a
C2 front Y/Z roll authored before every cavity and optical fit. The intended
original profile retreats at most38mm below Z0.620m and18mm above Z0.660m,
blending back to the existing longitudinal surface over Y2.050..2.400m.
Z0.640m retains the forward maximum. The axle, cowl, roof, moving hardpoints,
body width, floor height and collision setup remain fixed. The shared actual
front-surface ray still locates the optical stack. This is an unaccepted styling
pilot, not a researched factory dimension or a new aerodynamic claim. Check
actual evaluated topology, apertures, support pads, dimensions and matched
clay/paint views before adopting it; add measured budget savings if required.

Native pixel rays locate the exposed roof lip at Y0.10000000149m, separate
from the already certified Y0.1050999984m inner butt. Its outer depth is
12.325764mm. The reports-only roof pilot blends the two outer lower points
up to a2mm terminal depth over the final55.4167mm, with a C2 weight and three
additional local stations. A new underside knee at absolute X0.679m retains
the original shelf and300um inner-return overlap farther inboard. Raising
that entire shelf would detach the existing inner return by about3.7mm and
is explicitly rejected. Rebuild the fixed return/header unions and check
complete seats, continuity, normals, native self geometry and the same actual
glass-seal view; the section proposal alone cannot certify those assemblies.

Fascia pilot01 passes actual topology and the complete authored-mesh self scan,
but its neutral close-ups reveal pronounced triangular reflection pinches.
It is rejected visually and retained, including its151,216-triangle LOD0.
The next trial uses an original circular vertical section of radius3.457m
centered at Z0.550m (25mm lower retreat), with a C2 support over original
Y2.230..2.400m. The hood leading edge remains outside that deformation.
The pre-cut cap has explicit interior stations and an analytic normal field;
complete original-facet ownership, rather than nearest-face guessing, restores
that field after the Boolean apertures. Compare geometry and reflections again;
valid normals do not by themselves establish acceptable surface continuity.

The exact-plane StructuralBody investigation cannot supply the required budget
reserve: even before attribute constraints, fixed region boundaries permit at
most118 removed triangles. A separate bounded near-planar investigation may
merge regions only with complete geometric deviation at most0.1um, original
boundary vertices preserved, normal-field error at most0.005degrees and UV
error at most2e-6. These are explicit optimization error bounds, stricter than
the existing export conversion bounds; they do not relax any self, topology,
finite-interface or numerical-guard requirement. Measure the possible savings
before attempting an unsaved prototype; retain the exact-plane negative result.


### 2026-09-12 full04 source gate and roof trial03

Full04 passed all19 source geometry/control stages on Windows with the pinned Blender, including actual current control-fixture replays; evidence `reports/p1-018/source35-full04/qa19-01/evidence.json` SHA256 `6e1964e09ae83b3b41a31f97d551ba95c4244fc0aa387e138fd40c11533d62ef`. Actual counts are149778/32096/17940 plus24collision, total199838;490950 native corner normals are valid. This does not close visual, export, runtime, performance, platform or human gates. The root opened that exact source in a visible Blender5.1.2 window (PID23452, native window title verified) for inspection; the file remains read-only during QA.

Both front fascia pilots01/02 are visually rejected: actual neutral renders show newly introduced triangular dark cap patches. Runtime is binding the patches to actual native faces before any further shape/shading repair. No prototype is adopted. Sky-fill trial evidence `runtime/sky-fill34-01/analysis01/evidence.json` SHA256 `f7ab4381c3b0618bb88795797c165a785aa3dfb0c05375318bdca8518e3c0ffb` isolates sky contribution; the half setting darkens the whole vehicle without decisive grounding, and zero collapses detail. No canonical lighting change is justified.

Roof trial03 uses the frozen actual full04 upper triangles and recipe02 from `research/roof35-upper-seat-preserve-01/handoff04.json` (`e313724b1764fa8213db072ed844b908206fc27ea916e480c8dbb7ed328f035d`). This explicitly supersedes trial02's measured204.696micrometer top-seat drift. It preserves248 of250 original rail vertices and the full upper triangle field within native encoding error, tapers only the two lower tip roles to2mm depth, adds three stations with a retained0.679m knee, and feeds the unchanged250point inner-shelf table to the original inner returns. The root now owns a fresh reports-only source build; complete final joins, sweeps and visuals remain required.

The additional strict near-planar optimization reserve is insufficient: `qa/body-coplanar35-01/near01/review.json` (`27378eccdc0c4f927874f4c82a428fd9ec86f920568ed4c663b4a664eba92661`) bounds fixed-boundary savings at126triangles before normal/UV/contact restrictions. No mesh was simplified and no error threshold was loosened. The measured28-hardware chamfer reserve remains an unadopted alternative for original construction profile choices.


The current working checkpoint passed all13 Windows `scripts/check.sh` steps from03:17:44Z to03:21:23Z on2026-09-12. Exact command `20260912T031744.633970Z-source35-working-checkpoint-frontdoor.json` exited0; complete M0 outputs/logs are retained under `reports/p1-018/source35-checkpoint-frontdoor01/`. A preliminary shell-selector invocation entered WSL and failed tool discovery; `environment35-doctor01/wrong-shell-doctor.json` is retained. Explicit Git Bash then passed the pinned Windows doctor and front door. This is a code checkpoint, not final sedan platform/export evidence; the canonical source/runtime files still carry source34 while source35 refinement proceeds.


### 2026-09-12 molded wheel-liner return trial

The current molded liner uses a constantabsX0.918m outer edge, while the lower painted body retreats inward near the arch ends. The root will test a source-only outer edge at `min(0.918, minimum actual pre-cut bodyabsX at both shell radii minus0.003)m` at each existing angle. Both0.444/0.449m radii, original inboard edge,48spans,216degree arc, axle centers and all suspension/steering inputs remain unchanged. This shrinks the liner volume and adds no triangles; it is an original molded-return design choice, not a revised wheel or factory specification. Compare actual matched front/side views, validate closed surfaces, retainer fit and full steering/travel clearance before any adoption. Existing fascia normal defects are separately diagnosed; this trial does not presume every dark patch is a liner.


Fascia trial03 is a bounded shading-only correction to rejected trial02: actual native adjacent faces4356/4357 share a vertex but had a13.25degree corner-normal jump because only4356 was assigned the curved-cap field. The root tests complete per-reference clipped-piece plane coverage; unchanged1micrometer footprint/plane guards,0.99985 alignment,2micrometer corner correspondence and no discarded remainder remain. Shared `surface_normals.py` and all roof normal behavior stay unchanged. Actual geometry and renders must be compared; a valid unit normal alone cannot approve the result.


### 2026-09-12 original rocker taper trial

After the liner-only front render removes the projecting dark lower-arch flap, the root pilots an independently reviewable side-blade taper. The existing2.07m length/centerabsX0.914m and37mm maximum width remain; four sections atY -1.06,-.98,.93,1.01m reduce the46mm middle height to12mm at both ends, with18mm end width and8-point chamfered sections. End centerZ0.220m versus0.227m at the middle yields a controlled rising lower edge into each arch. Expected60triangles per blade versus108 is a provisional count, not accepted savings. Original planform/finite volume, actual rendered transitions, self and opening/tire checks must be verified. This reports-only trial includes the separately retained liner trial solely for a readable assembled view; its image comparison must isolate the rocker change. No hardpoints, materials or runtime physics change.


### 2026-09-12 post-bevel fascia normal authorship

The unchanged-guard trial03 reproduced exactly564owned faces and does not correct the visual discontinuity. Runtime `fascia35-pilot02-diagnosis03/evidence.json` (`79fd7e42728fe4802b3c05a3ae655a0f82ca84ba6a1bfc93703b3eb31ef06c79`) reproduces six saved boundary vertices exactly after the original1.2mm/two-segment bevel; their36.99?94.13micrometer shifts explain the failed pre-cut reference mapping.

Before the next root-only trial, the authored field scope is changed coherently: tag original cap faces before cuts, use pinned Blender `FSTR_ALL` to distinguish retained faces (`__mod_weightednormals_faceweight=16384`) from generated edges/corners (0/-16384), retain only these declared FACE INT layers when freezing evaluated triangles, and author the analytic curved-cap normal field on retained cap faces after all bevels/cuts. Shared generated-bevel corners receive the same adjoining cap tangent; unrelated actual normal encodings remain exact. This is a new original surface-field authorship step, not a looser claim of pre-cut preservation. Existing1micrometer geometry/fit guards and export correspondence tolerances remain unchanged. The actual new cap continuity must be within0.025degree and actual neutral images must eliminate the rejected macro patches before adoption.


Post-bevel trial04 failed before production because adding a Blender FACE attribute invalidated cached loop-triangle RNA; trial05 snapshots plain IDs first. Trial05 then failed its stronger exact-unrelated-vector assertion after assigning the new cap field and restoring old INT16 normal codes. Trial06 will retain both actual decoded alternatives for every unrelated loop: fresh encoding of its unchanged target vector and its original code under the updated normal fan. It will choose the closer actual vector and reject a target error above0.025degree; this explicitly measured native representation step does not change any target outside the authored cap/bevel corners. Both prior failures and their failed scenes remain retained. Existing geometry/contact and final export correspondence gates remain unchanged.


### 2026-09-12T04:06:28.694684+00:00 - Native fascia field and perimeter trial

Pilot06 completed actual native construction and three fixed neutral renders. The retained cap field now covers650 actual faces/3027 corners, including1005 shared bevel corners, with zero shared-cap normal disagreement and0.004146921-degree maximum unrelated native reencoding. The large front triangle bands are reduced, but a visible cap-to-shoulder boundary above the lamp remains. This is not final visual acceptance. Pilot04 invalid RNA and pilot05 old-code-only restoration failures remain retained. The next reports-only root trial adds an actual18mm, three-segment formed perimeter before optical cuts, preserving the shared pre-cut fitting order; the trial is not a locked or shipping change. Native topology, assembly fit, geometry budgets and actual matched renders must pass before adoption. No material/lighting change hides this defect.

Pilot07 correctly failed the actual splitter-to-fascia ray guard at X-0.830/Z0.207m: rounding the entire front perimeter removes the lower return that supports the existing splitter. Source.failed.blend/log retained. Pilot08 limits the18mm formed radius to the upper perimeter, with a C2 edge-weight ramp over Z0.670..0.770m; the lower splitter seating region remains unrounded. No guard or existing splitter fit target is relaxed.

The initial interpretation of pilot07 was too narrow: readback of pilot08 shows empty front/rear bumper meshes and a damaged structural shell before the splitter query. Thus the missing ray is a downstream symptom, not proof of a local lost splitter seat. A native per-operation trace now checks the rounded shell and identifies the first damaging Boolean; no workaround or weakened splitter guard is accepted.

Native trace02 measured282 degenerate triangles on the weighted-radius output before the first Boolean. Applying the existing bounded sliver cleanup immediately after native triangulation yields6190 closed triangles, no exact self intersections, and all eight initial body Boolean cuts retain valid topology. Pilot09 moves that existing cleanup before the pre-cut BVH and all optical/body fitting. Its exact tool/log evidence is retained; this is still an unaccepted trial.


### 2026-09-12T04:25:01.299033+00:00 - Cabin inspection follow-up

Five native full04 cabin stills use an explicitly recorded20W camera work light, so comparisons against prior0W images are not matched-light claims. Root and independent QA both observe that the two named cupholders are closed oval pads; they need actual receiving cavities in the console. A reports-only hollow molded-cup candidate will preserve existing centers(+/-0.068,-0.113m), fixed console envelope and nearby controls, cut real console pockets, and verify closed geometry and complete finite flange/pocket fit. Proposed circular lip radius44mm, receiving radius40mm, receiving depth60mm, with a closed3mm bottom. Final recipe requires a new specification lock before canonical adoption.

The thread geometry passes its complete pad-contact gate, but the pale smooth strips read as isolated pinstripes in the close inspection. A separate charcoal-thread material trial will use the same geometry and20W camera setup, with no new external material inputs; actual visibility must be checked before any material choice is adopted. Segmented seat/bolster finish remains a visual review item, not an established new solid intersection.

Independent native09 measurement withdraws any achieved18mm fillet claim: the requested radius was clamped at a duplicate final ring. Python stations2.4 and2.4000000000000004 encode to the same native coordinates; all72 zero edges join their corresponding vertices, with no other zero edges.114 probes on the38 nonzero full-weight perimeter edges remain within0.252881um of both sides, rather than showing a formed18mm radius. Pilot10 removes only native-coincident longitudinal stations before construction and retains the ordinary bevel/cleanup/fit order. It builds against the newly locked specification19 roof/liner/rocker/chamfer changes; no unaccepted fascia recipe is canonical yet.

The root cabin form pilot retains separate material-only and material-plus-form Blender files. Charcoal thread uses original linear base(.040,.045,.050), roughness0.78, with the supported geometry unchanged. The back bolsters currently stand vertically beside9/18-degree raked seat backs; the form pilot aligns eight explicit oval sections to those existing rakes, retains each original lowestZ and maximum111mm width, and gives their ends finite rounded cross sections.16 points per section should reduce geometry while replacing the long pointed ellipsoid ends. All affected assembly/motion and actual visual checks remain required; no canonical cabin change is made.
# 2026-09-12 revision19 assembled-source LOD repair

The fresh full05 source (SHA256
`cb1990ebefdff0445e1013f4f0d3ba5640d79d59214d659c1db59c8e78731403`)
passes extraction, source self-intersection and negative self controls, but the
fourth source gate rejects two folded wheel-liner shells in the LOD2 static
Rubber group. The measured totals are148362/31948/17964 visual triangles plus24
collision triangles (198298 shipping triangles). The failure is retained in
`reports/p1-018/source35-full05/qa19-01/`, recorded command
`20260912T043625.005849Z-source35-full05-nineteen-stage-qa` (exit1).

Before correction, this scope authorizes adding that existing semantic group
to the same independently checked per-component adaptive LOD construction used
by the other17 groups. This changes no source shape, material, threshold or
acceptance guard. A new assembled source must pass the unchanged full gate.
The unaffected full05 motion/fit checks may run separately; they cannot convert
the failed full19 result into a pass.

## 2026-09-12T04:54:18.330070+00:00 revision20 cabin construction lock

The actual charcoal-thread and rounded-bolster comparison is independently recorded in `reports/p1-018/qa/cabin35-material-form-pilot01-review/review.json` (SHA256 f693d4478098641281f55b92c063388d1be5d4fb8ed679a29ea4b4fab84de1e2). The lead has viewed the actual hollow-cup upholstery and cockpit originals from `cabin35-cup-pilot01`; the cavities read as open receiving pockets. Research handoff03 (SHA256 e656ed60d47ce0790fb1bb535c80aed30b2a88ae90ec2d271f6393d10396dbc9) records complete local insert/pocket clearance and rejection controls. Cup visuals and full assembled geometry remain under independent QA. Revision20 locks those specific recipes before canonical implementation. It does not adopt any fascia or rear wheel-tub cover trial. Existing human gates stay open.

## 2026-09-12T04:56Z rear wheel-tub intrusion investigation

Actual saved-camera native rays confirm the pointed rear-cabin surfaces are the unchanged inner wheel tubs. Native solid intersections also reveal intrusion into six outboard rear-seat parts per side in both full04 and the formed-bolster trial (research/rear-wheel-tub35-01/native01.json). Examples include157.224cm3 at the right cushion frame and169.244cm3 at its back shell. Prior static QA explicitly excluded remaining upholstery assembly construction; its pass does not cover this defect. A cover alone is inadequate. Before any implementation, the research agent is assigned a reports-only complete candidate retaining the authoritative tire/tub envelope and seating/rail/belt hardpoints, forming bounded seat relief and a supported cabin cover. The exact geometry, occupant-space effect, finite interfaces and costs must be measured and locked in a later specification revision before canonical adoption. Revision20 is retained as a local cabin recipe and does not resolve this defect.

## 2026-09-12T04:57:26Z cup capture illumination correction

The first cup trial neutral/upholstery and cockpit renders used0W inspection fill, as the actual command and manifest record. A coordination message incorrectly described them as matched20W. Preserve those originals as0W evidence; a fresh neutral-fill20 folder explicitly requests20W for the matched upholstery comparison. Geometry/readback results are unaffected. The final visual comparison must cite the actual illumination, not the mistaken message.

## 2026-09-12T04:58:16.653582+00:00 rear rail relief scope

Native rails02 confirms both existing rear RailBase solids also penetrate the unchanged wheel tubs (approximately57.986cm3 each). Preserving the already intruding outer surface would preserve a defect. The bounded candidate scope therefore includes finite outboard rail relief while retaining actual mounting positions, semantic supports and a continuous load-support section. Research must report the minimum remaining section. The tire/tub surfaces, seating and belt/rail hardpoints remain fixed; no new mechanical-simulation claim is made.

## 2026-09-12T05:02:16.761323+00:00 complete revision19 motion continuation and local fascia correction

The eight separately recorded full05 fit/motion stages pass: actual opening and motion drivers,231 optical pairs,42 finish interfaces,152 static construction interfaces, complete independent opening domains, initial containment and all four full steer/travel/roll tire envelopes. Evidence SHA256 a1b88f473fee3a002cbbbf34bce0df95716fc25820c97c058c643706246427fd. The original full19 LOD failure remains failed; this result cannot waive it.

Lead-owned pilot11 changes one corrupted retained original-side normal on immutable pilot10, with two explicitly declared local sharp-edge splits. Geometry, UVs, material/provenance and optical recess normals remain unchanged; maximum unselected decoded-corner drift is0.002437deg, within the unchanged0.025deg export correspondence bound. Source SHA256 64b219ed25d3c65579d808954225137d980dfd68f1dd20714f716979a7d7c7cd. Actual matched front_lamps and paint renders show the downward streak is gone, independently confirmed by the runtime agent. The true cap/side crease and forked shoulder highlight remain; the opposite defective endpoint and a measured local shoulder dip still need a reproducible symmetric construction correction. The one-corner diagnostic is not a final production rule.

## 2026-09-12T05:06:21.225244+00:00 revision20 assembled source and LOD repair result

Fresh full06 source SHA256 e34139176f4e053a0367431a5c93c4b458dfd626605a2e699f9808f2c6a6893e builds from the locked canonical revision20 recipes. Actual counts147450/31944/18388 plus24 collision triangles total197806,24 materials. All evaluated topology and raw-normal counters pass;645 native poses are retained. Independent lower-LOD exact self scan passes all210 meshes and848 indexed shells (50332 triangles), including the corrected static Rubber group. The prior source05 failure is retained. This is an affected-source/LOD check, not the final full19/runtime/platform acceptance; rear wheelhouse physical repair is still required.

## 2026-09-12T05:12:36.756431+00:00 rear relief rejected and packaging scope corrected

Root saved candidate04 on actual full06 as rear-cabin35-pilot01 (source84510a98fa15d4053efb59a1e125d451d811b4413ad8ba84569a360f863c56b0). Initial invocation omitted the exact-scan callback and failed before mutation; build-failed01.py and both recorded commands are retained. The corrected invocation succeeds. Actual matched20W rear_seats render still shows a pointed blade-like form. Local fit05 reports rear occupied foam width narrowing465.55 to375.57mm, despite successful tub separation. This physical workaround is not adopted.

The earlier internal instruction freezing all tub geometry was too restrictive; the task fixes wheel hardpoints and full tire envelope, not flawed fictional packaging. Research is now assigned a coherent reports-only proposal that moves the rear inboard tub wall outward only where the complete tire envelope permits, reconciles the cabin floor and supported trim/seat joints, and retains useful rear-seat width. Wheelbase, track, radius, travel and seat/belt/rail mounting positions remain fixed. Exact new geometry and clearance contracts must be locked before canonical adoption. This decision preserves the rejected candidate and does not treat an agent proxy as human comfort approval.

## 2026-09-12T05:12:36.756441+00:00 finite fascia shoulder trial

The actual pilot11 removes the isolated shading streak. Before the next root-owned trial, the runtime agent supplies a symmetric semantic endpoint rule and an exact-rational C2 height correction bounded to0.53125mm in the existing finite shoulder domain. X and endpoint position/first/second derivatives are unchanged. Native/rendered final outcome is still required; neither helper is adopted canonically.

## 2026-09-12T05:24:13.906756+00:00 actual isolated front-reflection diagnosis

Lead viewed all four native2560px paint-camera renders from the unchanged source12. The lower apparent fork branch remains under Key-only illumination; the upper branch remains under TopStrip-only illumination. Thus the remaining combined fork is attributable to two distinct studio-light reflections, rather than sufficient evidence by itself of a remaining surface seam. The earlier polynomial slope reversal was real and corrected; isolated illumination does not revoke that measurement. A smaller ribbed-looking highlight by the bumper/fender upper seam remains under inspection for geometry/normal versus denoising origin. No final surface acceptance is claimed by changing the ordinary review lighting.

```json
[
  {
    "light": "Key",
    "manifest_sha256": "3cf3c1f98cea1c44e19b2b4fa548789bcafc071768e282400cd855c80f4554f1",
    "image_sha256": "b578fa1f2907adc4476612b53049b6d01016300ad2f7f4adb0860e6e684a64c3"
  },
  {
    "light": "Fill",
    "manifest_sha256": "005a93402057d28027fafb6ce6b9a065ba31b3a64949afb5fbe60053c30973fb",
    "image_sha256": "6c5abde08a900eb609b0ffc9e11ce6828120cf386aeba5283a531ce688b76dd6"
  },
  {
    "light": "RearStrip",
    "manifest_sha256": "f1d88af47ea989a0ccd2995611a6e042cfb654bcea3547958672a59ee1be5cee",
    "image_sha256": "3ee6c281684702615f6cec9ebe45b5eecc237823dbc64d530b22e6da211d724b"
  },
  {
    "light": "TopStrip",
    "manifest_sha256": "2d8500b68021ad393e4af2adfdabc8a7e73b30b6267c1acc3e514720c6a0c914",
    "image_sha256": "3a74ec1296ff231c7b09f07e49548301acf8bd6f13f3fac283afddaa03f551e7"
  }
]
```

## 2026-09-12T05:38:07.966423+00:00 physical cabin closure scope

Native floor07 reproduces baseline flat-floor interference: transaxle2.65679L, resonator2.36715L, each mid exhaust pipe about1.162L and rear differential0.54798L of modeled overlap. These volumes describe geometric solids, not real component mass. Rear wheelhouse/liner contacts also involve mufflers, trunk carpet, sill/seal parts and the body/floor. The existing selected152-interface certificate was never an all-assembly interference proof. These findings remain failures until physically corrected or proved as explicit finite manufactured joints. Source/full04 historical passes are retained with this scope boundary.

Root authorizes reports-only coherent formed-floor, tunnel, wheelhouse and seat-support investigation before a new canonical packaging lock. Wheel, occupant, seat, rail and belt hardpoints stay fixed. The latest2mm wheelhouse wall proposal at cabinX0.670/tireX0.672 plus1.2mm upholstery retains every seat mesh and gives actual complete-domain5.500019mm tire clearance against the locked5mm requirement. Native08 local topology passes, but adjoining assemblies are unresolved and this is not an accepted source. Root will inspect a separately saved visual pilot. No delivery export or old-source replacement is authorized by the pilot.

Independent cupholder stage is frozen for integration review; two complete receiving wells and finite lip seats have10 actual geometric negative controls. The front fender seam ripple is now bound to alternating inherited cut-edge corner normals, not a proven shape or denoising defect. Runtime develops a symmetric bounded normal-field repair.

## 2026-09-12T05:49:20.674608+00:00 rear visual pilot02 and cup stage integration

Actual2560x1440 rear-seat, rear-cabin and upholstery originals were inspected with the same20W worklight as full06. Thin-wall candidate08 removes the two visible pointed intrusions without narrowing the seat. The separate saved pilot remains unaccepted because the adjoining physical assembly has unresolved interference. Original baseline and rejected pilot01 remain retained. See reports/p1-018/rear-cabin35-pilot02/lead-review.json.

Root reviewed the frozen bbbc837a16b348c315661f94f7c4b80af4742a52fcd48bb77d303ae14d65eaf2 cup reader and wired it as required twentieth stage in qa/run.py and gate.py. The actual full06 certificate passes the integrated host reader; missing pair, missing negative, wrong source, incomplete whole-surface proof and omitted-stage controls all reject. The full twenty-stage checkpoint is running on source06 with copied locked tools. This extends the named fit scope; it does not waive new floor or upholstery defects.

## 2026-09-12T05:59:18.867648+00:00 original fascia revision21 locked before integration

Matched actual source13 paint/front-lamp renders remove the smaller ribbed fender seam region; independent runtime QA viewed all three originals and agrees. Helper03 adds six passed native rejection/atomicity controls while its positive reference and corrected fender geometry are byte-identical to helper02 used by source13. Root adopts this bounded fascia construction and native field into the reproducible builder under packaging-revision-v21.md. Archived specification-v20.json is immutable. Full regenerated source/LOD and all delivery checks remain required.

## 2026-09-12T06:04:01.810849+00:00 full06 twenty-stage checkpoint passes

The complete ordered20-stage source gate passed on full06 at2026-09-12T05:55:08.859622+00:00. Exact evidence SHA256 8521ec4882c902d176b21d6c65c8047d9b7326c59b6e9373aa8fd3914874d8c8. Every source mesh, all lower-LOD indexed shells, saved controls/lights, named optical/finish/static/cup interfaces, complete opening/tire/wiper domains, initial containment and rejection controls in that declared inventory passed. The source and executable remained unchanged. The independent newer floor/driveline/seat interference findings are outside the selected static-interface scope and remain open; this pass does not waive them.

Windows scripts/check.sh also passed at the v20 working checkpoint. Its23 result/log files are copied and hashed in reports/p1-018/source35-v20-frontdoor01/index.json. Fascia revision21 was then integrated and a fresh full source07 construction started; previous source06 results are not relabeled as source07 evidence. Mainline red-main query remains empty.


### 2026-09-12T06:24:54.712012+00:00 - Full07 fascia integration and contact-shading diagnostics

Root constructed the complete v21 source using pinned Blender 5.1.2, including
regenerated LODs. `reports/p1-018/source35-full07/source.blend` has SHA-256
`ea701f2a44b5baaaa0c746c2311c61a348cd58b0bf2f1f18c0d2a8edadcf79bb`. Build and three matched
2560 x 1440 Cycles renders exited 0; the root inspected all original paint,
front-lamp and front three-quarter images. The localized fender reflection
correction survives integration. Independent native geometry comparison and
all connected LOD checks remain in progress. No shipping GLB has been replaced.

The full06 v20 checkpoint completed all 20 current source stages with evidence
SHA-256 `8521ec4882c902d176b21d6c65c8047d9b7326c59b6e9373aa8fd3914874d8c8`.
Its Windows working front door passed. Those results precede v21 and do not
certify the subsequently identified internal floor, driveline or seat contacts.

For D050, an actual Forward+ SSAO debug capture confirms occlusion beneath the
vehicle (`runtime/ssao-contact35-01` under the task reports). The diagnostic
therefore rejects simple absence of SSAO as the explanation. A separate native
trial changes only directional shadow normal bias from 1.8 to 0.2; its side
image still looks weakly connected to the road. Neither trial changes canonical
lighting. Source34 runtime inputs, native readbacks, full captures, commands and
failures are retained in their distinct diagnostic directories. Both native
commands exited 0; visual acceptance is still open.

A reports-only Blender trial also places the original crew binder in a formed
console-side pocket with a retaining band. It adds 56 triangles and preserves
its original dimensions; physical support proofs and actual cabin images must
be rebound before any canonical adoption. Seat and floor repairs remain
independent prototypes, with no new human approval recorded.


### 2026-09-12T06:35:00.515435+00:00 - Bounded wheel tessellation trial before adoption

Full07 has only 820 LOD0 and 58 total triangles of headroom. A reports-only
Blender construction will test tire radial divisions 64 to 60, rim divisions
48 to 36, and friction-disc divisions 48 to 36. Factory-reference dimensions,
original cross-section profiles, pivots, material assignments and shoulder
channel construction stay fixed. Maximum ideal-circle chord deficits are
0.471 mm for tires, 0.940 mm for rims and 0.760 mm for front discs. These are
modeling errors, not source uncertainty or changes to rolling radius. Actual
triangle savings after shoulder cuts, topology, normal fields, tire clearance
and a matched wheel close-up must pass before a new specification lock or
canonical implementation. This trial is an optimization candidate, not an
approved loss of inspection quality. Existing human gates remain open.


### 2026-09-12T07:06:40.768637+00:00 - Measured small-cabin distance-LOD trial

Reports-only distance-LOD comparison from the exact wheel tessellation trial: generate an unchanged baseline and a variant that omits the 22 explicitly named small cabin inserts, speakers, low seat hardware, minor controls and stowed items from LOD1/2. All LOD0 geometry and retained console, door-card, seat and parcel-shelf shells stay present. Measure actual costs and native topology, inspect matched exterior renders at the existing 28 m and 65 m runtime boundaries, and require final native transition/cockpit/opening checks before canonical adoption. No specification, ceiling, gameplay or human approval change is made by this trial.


### 2026-09-12T07:24:09.306260+00:00 - Revision22 wheel tessellation locked

The exact independent wheel handoff supports the bounded60/36/36 choice. Root inspected the retained original close-up and whole-car views, and adopts this geometry budget correction under packaging-revision-v22.md. The previous specification bytes and wheel constructor are preserved. The new lock includes no floor, seat or lower-LOD omission candidate and no human approval.


### 2026-09-12T07:59:22.402881+00:00 - Revision23 distance construction lock

Frozen independent review2d315ba supports the exact22 source omissions and two far brake repairs. The previous specification and constructors are retained before editing. The trial's final native transition/cockpit/opening requirements remain shipping-acceptance gates; constructing the next review source does not close them. Geometry caps, gameplay, and human boundaries are unchanged.


### 2026-09-12T08:08:59.918883+00:00 - Black paint response trial scope

D069 remains visible in the latest front-three-quarter image: broad gray reflections flatten the apparent panel form. A reports-only unsaved Blender trial will compare the existing finish with a darker base and tighter roughness/clearcoat response under identical neutral and daylight rigs. No geometry, exposure, lighting or shipping material changes are authorized by the trial itself. Root owns reports/p1-018/paint-response35-pilot01; record exact parameters and original image hashes before choosing the source material.

### 2026-09-12T09:02:29Z - Combined physical and upholstery review source

Root saved `reports/p1-018/assembly35-pilot01/source.blend`, SHA-256
`07de068d712efb10540ef646881917dedea57436bd4b3484de16e9251b679e3e`.
The actual LOD0 count is 148,362 against the unchanged 150,000 ceiling. It
combines the current-source physical14 repair, four coherent seat assemblies,
the document pocket and primitive-density trials. Lower LODs are deliberately
stale in this inspection file and cannot ship. Current-source physical14 has
66 individually valid changed meshes, 115 unchanged hardpoint meshes and
separate outside-field evidence. The seat recipe covers 54 finite interfaces;
rear piping retains a bounded original soft-foam tuck of at most 4 mm.
The old source-field reverse proof still has 181 unresolved domains. None of
these results approves the complete assembly or its final exported artifact.

### 2026-09-12T09:06:04.837267+00:00 - Primitive review and front cooling-core defect

Root and independent QA inspected the ten matched wheel, engine, closure-hinge
and open-door originals. The root also inspected a matched fitted-grille pair.
The root report is `reports/p1-018/hardware-budget35-pilot01/lead-review.json`,
SHA-256 `7c2a4adea00527b0883e956b25f6d9fc1b196a5b3b9c6a5b74e65ed2cd297e43`.
The simplified turbo contour loses visible quality: retain the original two
20 by 10 housings. The remaining 90 component changes save 3,616 LOD0
triangles. Those density choices may enter the next construction lock after
their exact parameters and evidence are recorded. New lower LODs, combined
contacts, source/export correspondence and runtime checks remain required.

The fitted grille view and native camera rays identify a second, independent
defect: `LOD0_CentralRadiator` presents a plain metal slab through the opening.
Root owns a bounded original front-core form/material trial under
`reports/p1-018/cooling-core35-pilot01`. Preserve the existing external package
envelope, grille, lamps, hardpoints and cooling-stack placement. Model a
credible recessed finned face, measure mesh/material cost and actual nearby
clearance, and inspect matched fitted-grille and whole-car views before
construction adoption. This represents visible heat-exchanger construction;
it does not add or claim airflow, cooling or thermal simulation. Existing
geometry and material caps and all human gates remain unchanged.


### 2026-09-12T09:11:42.981172+00:00 - Revision24 primitive construction lock

Root adopts the exact90 selected primitives under packaging-revision-v24.md, after preserving the prior specification and four constructors. No floor, seat, binder, paint, cooling-core or shoulder-field prototype enters this lock. This isolates the measured budget correction before subsequent assembly integration.


### 2026-09-12T09:42:10.946053+00:00 - Revision25 repairs newly generated far brake folds

Full09 passed extraction, LOD0 self geometry and negative controls, then failed four Wheel_FL/FR/RL/RR Material_Alloy LOD2 indexed shells, each with three crossing pairs. The root-owned brake-lod25 pilot applies the existing source-component fallback to only those four meshes:18 to24 triangles each,1299 other native mesh digests unchanged. Every final lower-LOD indexed-shell certificate passes. This record precedes canonical constructor adoption. No geometry threshold, hardpoint, performance budget or human gate changes.


### 2026-09-12T10:10:22.487997+00:00 - V25 completed construction checkpoint

Full10 source SHA-25626b7fc239a3d88854f00ddfc71dde9bfe25e80e1432255e8ea0236e4348de53e passes all20 selected native geometry/control stages. Windows scripts/check.sh passes all13 steps on the same locked working inputs. The source totals190700 shipping triangles and24 materials. Retain the v22-v25 constructors, trials, original images, independent reviews and full09 failure in the separately indexed checkpoint-v25 archive. The newer portable assembly replay remains an unaccepted inspection file with stale lower LODs. Installed production34, final export/runtime/platform/performance and all human boundaries are unchanged.
