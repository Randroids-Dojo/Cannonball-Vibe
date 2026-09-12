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
