# Meridian S8R dimension sheet

Rebound 2026-09-11T20:21:52.782119+00:00 to locked specification **17**, SHA-256 `e18b9c6aae54be01696ced16fae9be978872a922835a8cbe8ae974e0608813b9`, and actual source34 `0b4220d5c3f0024054de17a3c36add3388a4f52be2046cc2b837f3bac9edf793`. This current sheet carries forward the unchanged revision15 target tables. Native comparison confirms all fourteen stable engineering/runtime fields match source33; the added revision17 restraint section below is the only new local assembly. Historical construction paragraphs keep their original candidate scope. [Canonical specification](specification.json).

The engineering benchmark is the **2016 US Audi S6 Prestige, C7 facelift/4G, 7-speed S tronic, quattro**, with Black Optic and Individual Contour Seating as reference options. The fictional vehicle is **Meridian S8R**. Option selection does not establish the options fitted to the historic record car. [Audi US brochure, pp43 and 50–51](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf).

**F** means a published factory reference; **M** a firsthand modified-car claim; **O** an explicit original design choice; **D** a calculation from declared inputs; **U** an unverified factory value. Factory publication confidence is high unless noted, while its measurement/manufacturing uncertainty remains unstated. Original choices have exact declared targets, not measured factory confidence. Unit conversions do not add source precision. The full source IDs, locators and uncertainties remain in [reference-values.json](reference-values.json).

## Overall proportions

All values below are millimeters. US conversions retain two decimals to expose publication differences; those decimals are not a claim of measurement accuracy. Meridian field names are under `geometry` in the specification.

| Quantity / model field | US 2016 S6 reference (F) | UK MY2016 S6 drawing (F) | Meridian target (O) |
| --- | ---: | ---: | ---: |
| Length / `length_m` | 4925.06 | 4931 | 4940 |
| Body width, no mirrors / `body_width_m` | 1874.52 | 1874 | 1900 |
| Mirror width / `mirror_width_m` | 2085.34 | 2086 | 2100 |
| Wheelbase / `wheelbase_m` | 2913.38 | 2917 | 2920 |
| Front track / `front_track_m` | 1615.44 | 1615 | 1620 |
| Rear track / `rear_track_m` | 1605.28 | 1607 | 1610 |
| Roof height / `roof_height_m` | 1468.12 published height; datum unstated | 1430 roof / 1468 aerial | 1450 roof |
| Front overhang / `front_overhang_m` | U | 924 | 940 |
| Rear overhang / `rear_overhang_m` | U | 1090 | 1080 |
| Static clearance / `ground_clearance_m` | U | U | 135 |

Sources: [US technical table, p51](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf) and [UK Edition 2.3, October 2015, MY2016 S6 Saloon drawing, p81](https://cache3.arabwheels.sa/system/brochures/48/original/a6-s6-saloon-avant_compressed.pdf?1762339880=). Do not average the market differences. The US height is close to the UK aerial height, but this does not prove its measurement datum. Meridian's overhangs close exactly: 940 + 2920 + 1080 = 4940 mm (D).

## Source coordinates and contact geometry

Meters throughout the following tables. Blender is **+X right, +Y forward, +Z up**. The origin is the axle midpoint at design ground. Godot maps `(x,y,z)` to `(x,z,−y)`. These are O hardpoints, not extracted Audi H-points. Current revisioned values supersede early authored hardpoints retained in the research history.

| Anchor / `hardpoints_source_m` | Source XYZ, m |
| --- | --- |
| `Wheel_FL` | `(-0.81, 1.46, 0.3433)` |
| `Wheel_FR` | `(0.81, 1.46, 0.3433)` |
| `Wheel_RL` | `(-0.805, -1.46, 0.3433)` |
| `Wheel_RR` | `(0.805, -1.46, 0.3433)` |
| `Contact_FL` | `(-0.81, 1.46, 0)` |
| `Contact_FR` | `(0.81, 1.46, 0)` |
| `Contact_RL` | `(-0.805, -1.46, 0)` |
| `Contact_RR` | `(0.805, -1.46, 0)` |
| `Driver_Reference` | `(-0.43, -0.16, 0.45)` |
| `Camera_Cockpit` | `(-0.43, -0.39, 1.21)` |
| `Camera_ChaseTarget` | `(0, -0.1, 0.88)` |

`Suspension_*` shares the corresponding static wheel center; each `Wheel_*` child rolls at local zero. The rigid-body origin is source `(0, 0, 0.65)` m and the visual offset is Godot `(0, -0.65, 0)` m. The ray anchor is source Z `0.4283` m. These different origins are deliberate; [runtime-plan.md](runtime-plan.md) defines their binding.

## Wheels, brakes and steering

| Item | Reference / uncertainty | Meridian target and parameter (O unless D) |
| --- | --- | --- |
| Tires | US Black Optic: 255/35 summer tires on 20-inch wheels (F); UK S6 equipment: 255/40R19 (F) | Square **255/40R19**, `tire_width_m=0.255` |
| Nominal rolling dimensions | Loaded rolling radius depends on tire, pressure and load (U) | Diameter **686.6 mm**, radius **343.3 mm**, sidewall 102 mm (D); `wheel_radius_m` |
| Rim | UK 8.5J×19 reference (F); exact US option offset unverified (U) | Original 8.5J×19; `rim_diameter_m=0.4826`, `rim_width_m=0.2159`, declared `wheel_offset_m=+0.04` |
| Front/rear discs | US 15.7/14.0 in = 398.78/355.60 mm, ventilated (F) | `front_brake_diameter_m=0.399` / `rear_brake_diameter_m=0.356` |
| Rotor thickness | Exact donor thickness not adopted as a verified source value (U) | Front/rear `36/22` mm |
| Road-wheel lock | Donor caster, kingpin, Ackermann and full travel curves unverified (U) | `steering_lock_deg=±32` |
| Steering-wheel ratio | US published 16.1:1 (F); optional dynamic system is not modeled | Original presentation ratio `14.5:1`; not a donor steering calibration |
| Suspension | Audi five-link front / trapezoidal-link rear, adaptive air (F) | Static compression 75 mm; bump 85 mm; droop 75 mm; free length 160 mm |

Sources: [US S6 specifications/options, pp43 and 50–51](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf), [UK S6 equipment, p28](https://cache3.arabwheels.sa/system/brochures/48/original/a6-s6-saloon-avant_compressed.pdf?1762339880=). Nominal diameter calculation: `19 × 25.4 + 2 × 255 × 0.40 = 686.6 mm`. A selectable 20 mm factory ride-height change is not suspension travel. The original 19-inch tire adds 12.75 mm nominal sidewall depth over 255/35R20; this is a packaging choice, not measured ride-comfort proof.

## Mass, fuel and trunk equipment

Audi US curb mass is 4486 lb, approximately 2034.815 kg (F), from [p51](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf); its axle distribution was not verified. Meridian uses an original fixed nominal running condition:

| Component / `mass_and_fuel` | kg | Definition |
| --- | ---: | --- |
| Base curb | 2040 | Includes full 75 L main tank |
| Preparation, dry | 31 | Authored equipment, mounts and tank allowance |
| Auxiliary fuel | 74.5 | 100 L × 0.745 kg/L; fictional density |
| Crew | 240 | Three people at 80 kg |
| Luggage | 14.5 | Restrained portable kit |
| **Total** | **2400** | Main fuel is counted once |

The O front/rear split is **54:46**. Its D longitudinal CG offset is `0.1168` m forward of the axle midpoint; CG height is the O value `0.55` m. Runtime keeps this fixed mass while the saved fuel state changes; the preserved initial gameplay fuel is **82 L**, not a full-tank spawn. This is explicit gameplay policy, not a variable-mass fuel simulation.

Main capacity is **75 L**, auxiliary **100 L**, total **175 L** (O). The original auxiliary outer box is `(0.9, 0.48, 0.28)` m at source `(0, -1.92, 0.56)` m; its gross rectangular envelope is **120.96 L** (D). The two current center fields agree. The location was revised during packaging; current placement comes from [packaging revision 3](packaging-revision-v3.md), not the historical initial layout.

The stock reference publishes 19.8 US gal and 75 L in different-market brochures (rounded F values). Arne Toman reports **45 US gal auxiliary = 170.3435 L** for his modified 2016 S6 (M; medium confidence, usable capacity unverified). Meridian's 100 L auxiliary cell is a separate original choice. Gross modeled volume does not certify usable capacity, ullage, wall thickness, vapor containment, structural safety or transfer performance. [Firsthand S6 build](https://www.arnesantics.com/projects/current-cannonball-run-record-holder-audi-s6/).

## Cabin envelope and inspection mechanisms

Factory cabin references (F) are front/rear legroom **41.3/37.4 in**, shoulder room **57.5/56.3 in**, and headroom **37.2/37.8 in with sunshade**. [US p51](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf). UK maximum front headroom **1046 mm**, trunk plan **1176 × 1050 mm**, opening **949 mm** and loading sill **649 mm** use other definitions. UK cargo **530 L VDA** and US **14.1 ft³ ≈399.27 L** are not interchangeable methods. [UK drawing, p81](https://cache3.arabwheels.sa/system/brochures/48/original/a6-s6-saloon-avant_compressed.pdf?1762339880=). Meridian's remaining usable cargo volume has not been assigned a factory-derived number.

Five seats are modeled; the nominal running load is three crew. The original front hip/eye envelopes use X ±.430, hip Y/Z −.160/.450 and eye Y/Z −.390/1.210 m, with 105 mm head radius. Rear outer envelopes use X ±.430, hip Y/Z −1.080/.480 and eye Y/Z −1.340/1.170 m, with 100 mm head radius. These are authored inspection proxies; final occupant fit and usability require actual views and human review.

All following pivots are O values under `hardpoints_source_m`; angles and spaces come from `mechanisms`. Door axes remain conventional vertical hinges.

| Mechanism | Source pivot, m | Travel / axis |
| --- | --- | --- |
| `Door_FL` | `(-0.915, 0.72, 0.5)` | -62° about parent-source Z |
| `Door_FR` | `(0.915, 0.72, 0.5)` | 62° about parent-source Z |
| `Door_RL` | `(-0.915, -0.585, 0.5)` | -58° about parent-source Z |
| `Door_RR` | `(0.915, -0.585, 0.5)` | 58° about parent-source Z |
| `Hood_Hinge` | `(0, 0.77, 0.99)` | 68° about parent-source X |
| `Trunk_Hinge` | `(0, -1.996, 0.99)` | -72° about parent-source X |
| `Pedal_Accelerator` | `(-0.28, 0.72, 0.28)` | -18° about parent-source X |
| `Pedal_Brake` | `(-0.47, 0.72, 0.28)` | -12° about parent-source X |
| `SteeringWheel_Pivot` | `(-0.43, 0.21, 0.855)` | Rest X -20°; rotate about local-rest Y |
| `Wiper_L` / `Wiper_R` | `(-0.53, 0.735, 0.985)` / `(0.06, 0.735, 0.985)` | -78° / -74°, 1.35 s period |

The windshield spans cowl Y/Z `0.74/0.97` to header `0.14/1.395` m. Wiper rest X is −35.31° and the source normal is approximately `(0,.578,.816)`; factory blade profiles and sweep angles remain U. New hood/trunk pivots and current door axes require full-assembly post-build confirmation. The [bounded source07 hinge study](../../../reports/p1-018/research/hinge-study-07/README.md) only supports its stated shell tests.

Mirror surface anchors are left/right `(-0.977, 0.6, 1.043)` / `(0.977, 0.6, 1.043)` and rear `(0, 0.2, 1.293)` m. Side mirrors and their cameras follow the front doors. Instrument cluster anchor is `(-0.43, 0.4, 1.06)` m. All camera/light anchors remain enumerated in the canonical specification; mirror resolution/freshness is a measured runtime requirement, not a factory dimension.

[Packaging revision 4](packaging-revision-v4.md) moved rear-door hinge Y from −.580 to −.625 m to clear the closed front-door return and upper hinge leaf, retaining its then-current X ±.915 and Z .500 m. Revisions 6 and 8 later change these targets as described below; the table above lists the current axes. The earlier shell-only hinge candidate did not establish full-assembly clearance.

[Packaging revision 5](packaging-revision-v5.md) addressed steering-rim occlusion observed at the declared driver eye. Its historical target moved the cluster from `(−.430,.550,.958)` to `(−.430,.400,1.050)` m and lowered the wheel center from Z `.910` to `.855` m. The column and stalks followed. The 388 mm outside wheel diameter, tilt, ratio, seat and eye stayed fixed. The current eye-to-wheel-center distance is **0.697155 m** (D); this does not establish knee clearance or readability. D035 ergonomic inspection and separate D036/D037 telltale/driver corrections require actual source/runtime confirmation. These values are O, not Audi cabin measurements.

[Packaging revision 6](packaging-revision-v6.md) raised the cluster another 10 mm to current `(-0.43, 0.4, 1.06)` m after source inspection found a small rim margin beneath the fuel digits. Its historical rear-door hinge target moved X from ±.915 to ±.942 m while retaining Y −.625 and Z .500 m. Revision 8 supersedes that rear axis. Neither the change nor a sampled no-contact result establishes complete occupant fit or continuous clearance.

### Current concealed hinge construction (O)

[Packaging revision 8](packaging-revision-v8.md) responds to rejected exposed hinge pockets. Rear axes move inward 27 mm to X ±.915 m and forward 40 mm to Y −.585 m; semantic axis Z remains .500 m. Front semantic axes, the driver eye, cluster, wheels, hood and trunk anchors remain unchanged. Physical pin heights are separate from that semantic pivot origin. The current revision retains these hinge targets.

| Quantity / specification field | Revision 8 target retained in the current revision |
| --- | --- |
| Rear left / right axes / `hardpoints_source_m.Door_RL`, `Door_RR` | `(-0.915, -0.585, 0.5)` / `(0.915, -0.585, 0.5)` m |
| Both physical pin heights, all four doors / `mechanisms.Door_*.hardware_pin_heights_m` | `0.6` / `0.84` m |
| Pin / bore / knuckle radius / `original_packaging.door_hardware` | `4` / `4.5` / `6.5` mm |
| Bearing radial clearance (D) | `0.5` mm; only the named pin/bore interface |
| Jamb pocket outer absolute X / `jamb_pocket_outer_x_m` | `0.923` m |

The native [rear-axis clearance-03 diagnostic](../../../reports/p1-018/qa/rear-axis-18/clearance-03.json) checked 804,699 near-field triangle pairs across 101 poses per rear side, using the retained source18 geometry and selected axes. It cleared a guarded 1 mm lower bound after excluding exactly eight obsolete rear pin/leaf meshes and separately reporting the two closed rubber-seal interfaces. This does not validate new hardware, approve seal exceptions or prove clearance between sampled poses. Fresh complete-assembly and native visual checks remain required.

[Surface and cockpit refinement](surface-refinement.md) records formed roof-side rails and the physical instrument shade. The independent [source18 shoulder diagnosis](../../../reports/p1-018/research/surface-refinement-18/README.md) supports targeted cross-profile sampling and confirms the roof was already C1. Its +884 triangles are an isolated bumper measurement, not the full rebuilt vehicle cost or a production pass.

### Revision 9 assembly corrections (O)

| Quantity / specification or construction record | Current target |
| --- | --- |
| Front-door trailing assembly shift / `original_packaging.front_door_trailing_shift_m` | `64` mm forward, with glazing, seal, hem and latch following |
| Side mirror camera left / right / `hardpoints_source_m.MirrorCamera_Left`, `MirrorCamera_Right` | `(-1.02, 0.547, 1.065)` / `(1.02, 0.547, 1.065)` m; Y moves rearward 63 mm from .610 m |
| Rear mirror camera / `hardpoints_source_m.MirrorCamera_Rear` | `(0, 0.16, 1.293)` m, unchanged |
| Interior mirror attachment / packaging revision 9 | 3.5 mm-radius bent arm; 34 × 26 × 3 mm windshield button; exact points in native diagnostic |
| Instrument shade front edge / packaging revision 9 | Retracts 75 mm; locked eye and cluster anchors stay fixed |

[Packaging revision 9](packaging-revision-v9.md) widens the fixed B-pillar by moving the front-door trailing assembly forward, returns the roof-side beam inward of moving glazing, and joins the folded hinge arm tangentially to its separate bored sleeve. The front arm knee moves 12 mm inward. These construction corrections require fresh complete door, wiper and mesh checks; they do not change the researched dimensions or fixed gameplay mass.

The side-camera move follows an actual opaque-housing obstruction and retained native target/projection tests. It must be verified in the final exported source. The [rear-mirror diagnostic](../../../reports/p1-018/research/surface-mirror-20/README.md) measures both missing stalk attachments in source20 and the isolated candidate's ≥1.609 mm windshield-plane clearance. It preserves the reflecting face and rear camera. A modeled glued button is an original visible attachment, not adhesive-strength or mechanical simulation evidence.

The separately measured rear door/rubber-seal interface crosses 1 mm separation between 0.3944° and 0.4002° opening. Revision 9 describes its named compliant zone within 0.41° of the closed stop; this narrow interface record is not a general rigid-clearance exception and needs renewed complete-assembly confirmation. [Native seal engagement evidence](../../../reports/p1-018/qa/rear-axis-18/seal-engagement-01.json).

### Current closure packaging (O)

| Quantity / specification field | Revision 7 target retained in the current revision |
| --- | --- |
| Hood hinge / `hardpoints_source_m.Hood_Hinge` | `(0, 0.77, 0.99)` m; raised 18 mm from revision 6 |
| Hood skin rear / leading Y / `original_packaging.hood_skin_hinge_edge_y_m`, `hood_skin_leading_y_m` | `0.803` / `2.226` m |
| Trunk hinge / `hardpoints_source_m.Trunk_Hinge` | `(0, -1.996, 0.99)` m |
| Trunk skin leading / trailing Y / `original_packaging.trunk_skin_leading_y_m`, `trunk_skin_trailing_y_m` | `-2.02` / `-2.385` m; trailing edge moves forward 47 mm from −2.432 m |
| Trunk skin longitudinal extent (D) | `0.365` m; this is not a luggage-capacity measurement |

[Packaging revision 7](packaging-revision-v7.md) aligns both closure perimeter heights with the original pre-cut upper body, including its front bow; hood crown falls to zero at the perimeter. Front fender insets target a 3.5 mm hood side gap. Moving hinge arms, ribs and hem boundaries follow their revised assemblies. The front bumper paint bevel threshold changes from 0.45 to 1.0 rad to avoid beveling smooth profile sample joins. These original corrections require new evaluated geometry and matched visual evidence; the isolated [source15 surface diagnosis](../../../reports/p1-018/research/surface-shading-15/README.md) supports only its bounded native comparisons.

Revision 7 also records glazing/belt/seal clearances and auxiliary pump, vent and gland fit corrections. Only the explicitly compressible rubber floor gland has a declared 1 mm nominal radial interference; that local mating policy does not excuse rigid intersections elsewhere. These are original assembly decisions, not newly verified donor dimensions or certified fuel hardware.

The current original construction record is [packaging revision 15](packaging-revision-v15.md); source uncertainty and modeling tolerances remain separate from each revision's acceptance evidence.

## Formed shell and attachment details (O)

[Packaging revision 10](packaging-revision-v10.md) fits the 442 × 135 mm outer headlamp cover inside a 449 × 142 mm aperture. The 435 × 127 mm clear lens sits 2 mm behind that cover envelope; full side/top/bottom returns and projectors follow the same pre-cut body surface. These are original optical dimensions, not factory lens measurements. [Actual source22 lamp fit](../../../reports/p1-018/research/lamp-fit-22/README.md).

The same revision uses one closed A-pillar ribbon with 12 longitudinal and 3 cross spans, an 18 mm formed return and a tapered 4 mm crown. Roof reinforcement stops at Y −1.230/+0.100 m; the headliner half-width is .625 m with a 25 mm edge-relief function against the original width profile. The 10 mm maximum inner front-door trailing relief tapers to zero at the outer skin. Original glass, roof and door-axis hardpoints remain fixed. [Revision 10 construction and fixed-cabin interfaces](packaging-revision-v10.md).

[Packaging revision 11](packaging-revision-v11.md) adds measurable structural joints and mounts. Values below are declared constructor targets; the earlier isolated candidate evidence does not establish acceptance of a later complete source.

| Assembly / `original_packaging` field | Current original target |
| --- | --- |
| A-pillar split / `a_pillar_structural_joint.split_plane_z_m` | Z 1.05 m; lower foot unioned into body, upper foot closed on the same planar butt |
| A-pillar/fender relief / `fender_relief_nominal_m` | 3.5 mm nominal; original external corner normals retained only on unchanged surfaces |
| Front folded hinge-arm knee / `door_hardware.front_folded_arm_knee_inboard_m` | 89 mm inboard of axis; 2 mm beyond revision 10 |
| Closure arm bore / `closure_offset_arm_bore_radius_m` | 5.3 mm radius; 12-sided bore gives 1.119407 mm radial clearance to a 4 mm pin (D) |
| Front protective floor / `front_floor_panels.panel_z_m` | Z 0.1355–0.1395 m; 4 mm thickness |
| Floor pocket / `pocket_ceiling_z_m`, `perimeter_gap_m` | Ceiling Z 0.1455 m; 2.5 mm perimeter gap |
| Floor spacers / `mount_spacers_per_side`, `spacer_size_m` | 4 per side; (12, 12, 6) mm; top meets pocket ceiling |
| Front splitter / `front_splitter.width_m`, `z_m` | 1.66 m wide, Z 0.207–0.219 m; 12 mm thick |
| Splitter projection / `maximum_projection_m`, `nose_limit_y_m` | ≤20 mm beyond fascia, tapering at corners; source nose Y ≤2.4 m |
| Splitter pocket/supports / `pocket_perimeter_gap_m`, `support_count`, `support_depth_m` | 2.5 mm gap; 4 supports, 4 mm depth |
| Caliper arcs / `caliper_arc_subdivisions` | 8 steps over 56°; maximum front-bridge radius 220.5 mm; maximum chord error 0.411277 mm (D) |

The [native source23 A-foot study](../../../reports/p1-018/research/a-foot-23/README.md) measured a coincident closed Z=1.05 m butt with zero shared solid volume. Left/right fender gaps were 3.49819/3.49871 mm, within the declared 2.5–4.5 mm panel-gap range; 202 sampled front-door poses had no guarded 1 mm failure in the selected scope. Its raw +576 triangles and rejected dissolve trials are retained. New complete-source topology, motion, export-normal and budget checks remain separate.

The floor and splitter use fitted pockets with bounded planar mounting faces, not unexplained overlapping plates. Eight caliper steps preserve the 56° endpoints, radii, thickness and every brake component while reducing topology. The front bridge radius is the 199.5 mm rotor radius plus 21 mm: the corrected 220.5 mm radius gives a bound below .412 mm, superseding the earlier 219.5 mm/.410 mm arithmetic. This is a geometric sampling bound, not a braking-performance or final appearance test. [Exact constructor rationale and retained failures](packaging-revision-v11.md).

### Shoulder reflection diagnosis

Matched source22 experiments rejected a normal transfer, structured cap and several profile fairings. The later unchanged-source light isolation showed that the doubled band combined two separate studio emitters; each produced one connected highlight. The measured C1 curvature variation remains a valid observation, but it does not make the two-light reflection alone a geometry defect. The existing profile is retained. [Full rejected trials and corrected interpretation](../../../reports/p1-018/research/shoulder-normals-22/README.md), [actual separated emitters](../../../reports/p1-018/shoulder-fairing-11/light-evidence.json). This does not waive final full-view visual review.

### Warning display placement and behavior boundary

The runtime warning row uses a 512 × 192 px viewport, row `(x,y,w,h)=(16, 0, 480, 28)` px and 20 px type. The source preview uses local U/V `(0, 0.061)` m and 9 mm type. Revision 11 positioned the low-fuel-only source preview. Revision 12 adds the six existing runtime warning conditions to source inspection; actual source/native glyph coverage remains a verification requirement. These are display previews, not new engine, fuel-transfer, thermal or electrical simulation. [Display placement](packaging-revision-v11.md), [revision 12 conditions](packaging-revision-v12.md).

Normal-vector export error of 0.05° and UV component error of 2×10⁻⁶ are encoding comparisons; neither changes position, clearance or panel-gap tolerances. [Revision 10 export encoding contract](packaging-revision-v10.md).

The labels are mutually exclusive; the first true condition in the following order is shown. These are explicit current conditions, not factory warning-system thresholds.

| Priority | Label | Source/runtime condition |
| ---: | --- | --- |
| 1 | LOW FUEL | `fuel_l < 20` |
| 2 | DAMAGE | `damage > .05` |
| 3 | COOLING | `cooling_condition < .4` |
| 4 | TIRES | `tire_condition < .3` |
| 5 | PANEL OPEN | `any opening fraction > .001; runtime also considers target` |
| 6 | PARK BRAKE | `handbrake > .02` |

Source preview defaults are 0 mph, 750 RPM, 82 L, gear 0/N, damage 0, cooling 1, tire condition 1 and handbrake 0. The source gear control is a manual inspection value: −1/R, 0/N or 1–7. Runtime gear/RPM is an existing presentation estimate and can also display P; this is not identical mechanical transmission simulation. Source opening properties set posed fractions, while runtime warnings also consider commanded target fractions during animation.

### Revision 12 rear-sill fit

[Packaging revision 12](packaging-revision-v12.md) replaces the upper rear portion of the original trunk cavity with a concave Y/Z prism extruded over X `(-0.79, 0.79)` m. In order, its Y/Z vertices are: `(-2.43, 0.295)`, `(-1.5, 0.295)`, `(-1.5, 0.945)`, `(-2.3885, 0.945)`, `(-2.3885, 0.88)`, `(-2.43, 0.88)` m.

The upper cavity stops at Y −2.3885 m while the fixed lid edge stays Y -2.385 m, leaving the declared 3.5 mm seam (D). The lower cavity still reaches Y −2.430 m below Z .880 m, preserving the authored bag/carpet envelope. This replaces the source23 approximately 45 mm open slot; it is not a reduction in global length or a new luggage-capacity claim.

The adjacent optical cutter keeps its X/Y and lower Z 0.8055 m; its upper Z is 0.9315 m, center 0.8685 m and height 0.126 m (D). The independent source23 candidate supports its bounded restored sill and opening clearances, including a 1.2858 mm refined trunk lower bound. The full rebuilt source, visible closed seam, export, final media and acceptance evidence remain pending their own checks.

### Revision 13 fitted rear optics and fuel fixtures

[Packaging revision 13](packaging-revision-v13.md) supersedes the earlier tail-lamp box and cutter while preserving the revision12 trunk sill. These are original fictional construction choices (O), supported by measured candidate geometry (D), not manufacturer specifications. Global dimensions, all vehicle/occupant hardpoints, 75 + 100 L nominal fuel capacity, 2,400 kg fixed running mass and gameplay limits remain fixed.

| Current parameter / `original_packaging` mapping | Locked value |
| --- | --- |
| `tail_optics.cut` | Center Y/Z `(-2.4225, 0.868)` m; size X/Y/Z `(0.423, 0.32, 0.127)` m |
| `tail_optical_cut_z_m` | `(0.8045, 0.9315)` m; this replaces revision12 lower Z .8055 m |
| `tail_optics.cover` / `backplate` | Width/height .414/.116 m, center Z .868 m; depth offsets `(0, 0.003)` / `(0.081, 0.087)` m |
| `tail_optics.top_bottom_walls` / `side_returns` | Walls .418 × .004 m at Z .808/.928 m; returns .002 × .116 m at lamp-center X ± .208 m; depth 0/.087 m |
| `tail_optics.emitter_guide_front_back_depth_m` | `(0.018, 0.023)` m; original X/Z layout retained |
| `tail_optics.formed_upper_interior_relief.map` | `Znew = Zold - .010*(depth/.087)*clamp((Zold-.868)/.058,0,1)` |
| `tail_optics.tessellation` | Cover/backplate 16 × 4; lower wall/guides/emitters 16 × 1; side returns 1 × 4; upper walls use the same 17 cover X stations plus two outer margins, 18 × 1 |
| `auxiliary_fixture_fit.strap_return` | Rear/front Y `(-2.171, -1.669)` m; bottom/top Z `(0.409, 0.702)` m; radius 8 mm, 4 sides |
| `auxiliary_fixture_fit.outlet_line_radius_m` / `pump_outlet_bore_radius_m` | 6 mm hose radius; 7.5 mm bore radius, 12 sides, cutter starts 12 mm inward opposite the first tangent |

The pump preserves its nominal outer dimensions and position; the changed Boolean can change evaluated bevel vertices. The six outlet line stations are `(0.49, -1.99, 0.46)`, `(0.47, -1.99, 0.4)`, `(0.401333, -1.997333, 0.364)`, `(0.35, -1.99, 0.21)`, `(0.35, -1.36, 0.21)`, `(0.43, -1.27, 0.21)` m. The third station rejoins the unchanged floor-gland axis; tank envelopes, pump nominal outer box envelope, top straps, floor passage and main-reservoir endpoint remain fixed.

The [immutable rear-optics handoff](../../../reports/p1-018/research/rear-lamps-29/HANDOFF-v4.md) reports 231 independent optical pair checks, 24 fully measured seats, minimum unrelated optical gap 1.881516 mm and a 160-triangle saving. The [four-fixture candidate](../../../reports/p1-018/research/packaging-interfaces-29/fixture-candidate03.json) checks 4,786 static pairs and adds 92 triangles: the combined candidate delta is −68. These component results are not final whole-vehicle counts or source acceptance.

Actual source31 was reopened read-only and its [input provenance inventory](../../../reports/p1-018/research/source-input-binding-31/asset-input-inventory.json) retains all six original packed texture byte hashes and the Bfont-derived label attribution. The checkpoint is still a verification candidate; canonical source/GLB binding and final runtime/media/human approvals remain pending. Modeled plumbing and optical layers do not implement fluid transfer, pumping or mechanical lamp operation.

### Revision 14 cabin trays and finite construction interfaces (O)

[Packaging revision 14](packaging-revision-v14.md) preserves the global engineering targets and corrects actual source31 local intersections. Values below are original assembly choices, not factory dimensions. Earlier revision descriptions retain their historical scope; the top-strap position and rear screen offset below are current.

| Current parameter / `original_packaging` mapping | Locked value |
| --- | --- |
| `static_fit_revision14.cabin_trays.center_abs_xyz_m` / `size_xyz_m` | Center `(0.446, -0.271, 0.13745)` m with signed X; size `(0.386, 1.72, 0.0049)` m; bevel 1 mm |
| `cabin_trays.bottom_top_z_m` | `(0.135, 0.1399)` m; 135 mm ground minimum retained |
| `cabin_trays.pocket_center_abs_xyz_m` / `pocket_size_xyz_m` | `(0.446, -0.271, 0.0212)` / `(0.389, 1.723, 0.2424)` m; Z `(-0.1, 0.1424)` m |
| `cabin_trays.perimeter_clearance_m` / `overhead_clearance_m` | 1.5 / 2.5 mm (D from locked envelopes) |
| `cabin_trays.pad_centers_abs_xy_m` / `pad_size_xyz_m` | Four per side at `(0.628, -0.9)`, `(0.628, -0.2)`, `(0.35, 0.45)`, `(0.56, 0.45)` m; size `(0.012, 0.012, 0.0025)` m; Z `(0.1399, 0.1424)` m; LOD0 only |
| `static_fit_revision14.top_tank_strap_center_z_m` | `0.7041` m; 0.1 mm above revision13 |
| `static_fit_revision14.trunk_arm_terminal_below_closure_z_m` | `closure_z − 0.0114` m; terminal only lowers 1.2 mm; hinge, knee, terminal Y, tube and bore remain fixed |
| `static_fit_revision14.vent_union_outer_inner_radius_m` | `(0.0097, 0.008)` m; wall 1.7 mm |
| `static_fit_revision14.rear_mirror_surface_additional_y_offset_m` | `-0.0001` m; rear screen only, semantic camera/anchor unchanged |
| `roof_reinforcement_joint` | Finite welded flange at absolute X `(0.592, 0.741)`, Y `(-1.23, 0.1)` m, between actual evaluated skin facets; at most 0.65 mm inner penetration and at least 0.55 mm outer skin remaining |
| `main_tank_crossover_seats` | X planes `(-0.1, 0.1)` m; Y/Z center `(-0.745, 0.421)` m; radius 9 mm, 10-sided caps |

The [immutable native handoff](../../../reports/p1-018/research/static-fit-31/HANDOFF-candidate03.md) records source31 tray/body intrusion of about 1.11945 L per side and a real Boolean pocket correction. The [full pad certificate](../../../reports/p1-018/research/static-fit-31/pad_certificate01.json) passes all sixteen 144 mm² planar footprints and rejects a 0.1 mm intrusion. The [roof/crossover certificate](../../../reports/p1-018/research/static-fit-31/joint_certificate02.json) proves complete actual triangles: remaining outer roof skin is at least .599820/.742814 mm left/right, and the crossover caps contact over 232.081 mm². These are measured source31/candidate values (D); the roof limits above are original acceptance targets (O). Only the specific finite joints allow contact.

Matched [actual source31](../../../reports/p1-018/research/static-fit-31/actual31-tray-close.png) and [isolated candidate](../../../reports/p1-018/research/static-fit-31/candidate03-tray-close.png) CPU captures show the corrected tray perimeter. The composed candidate measures 149,880 LOD0 triangles, +168, leaving 120 beneath 150,000. The exact clean helper reproduces all 17 replacement/new rows including normals and UVs. [Actual source32 correspondence](../../../reports/p1-018/research/static-fit-31/compare_source32_03.json) then verifies the same indexed triangles with a maximum 59.605 nm vertex displacement and the unchanged per-corner encoding limits. Its [reopened input inventory](../../../reports/p1-018/research/source-input-binding-32/asset-input-inventory.json) retains all six packed original texture hashes and Bfont ancestry. Other LODs, aggregate budget, exports, motion and final media remain independently checked stages; canonical shipping hashes and human approvals remain pending. This sheet does not imply production acceptance.

### Revision 15 tire surface, formed header and dashboard finish (O)

[Packaging revision 15](packaging-revision-v15.md) retains all global dimensions, contact/occupant/hinge anchors, fuel capacities, fixed mass and gameplay policies. The following local fabrication and response choices are original; they add no factory measurement or mechanical simulation claim.

| Current `original_packaging.finish_revision15` parameter | Locked value / evidence boundary |
| --- | --- |
| `tire_shoulder_cuts.cuts_per_tire` / `angular_stations` | 56 actual recesses per tire, 224 total; 28 angular stations on both shoulders |
| `axial_abs_stations_m` / `angular_sweep_rad` | Absolute X `(0.083, 0.0995, 0.11)` m; angular sweep `0.026` rad |
| `cutter_center_below_nominal_profile_m` / `cutter_radius_m` / `cutter_sides` | 0.7 mm below profile; 1.2 mm radius; 4 sides |
| `candidate_observed_sample_recess_m` | 1.146986–2.05213 mm at sampled candidate points (D), not a continuous tread-depth certificate |
| `tessellation_reallocation` | Four projector and four exhaust rings: 24 path × 6 cross-section sides; steering rim: 48 × 10; two turbo casings and rear differential UV segments/rings `(20, 10)` |
| `measured_candidate_triangle_savings` | 1,592 triangles across 12 components; this is an isolated saving, not final whole-vehicle cost |
| `maximum_sampled_surface_change_m` | 2.882039 mm across bidirectional vertex/edge-midpoint/centroid samples; existing 5 mm global tolerance remains fixed; not a continuous Hausdorff bound |
| `formed_header_wall.abs_x_m` / `y_domain_m` | Absolute X `(0.662, 0.668)` m; Y `(-1.23, 0.1)` m, 25 stations per side |
| `lower_z_by_side_m` | Left 1.333985–1.414411 m; right 1.333985–1.414411 m. The exact 25-value tables in the specification, including B-post relief, are authoritative |
| `candidate_minimum_complete_opening_separation_m` | 13.8465 mm in 232 isolated wall domains; rebuilt rail/roof joint and all openings still require final verification |
| `dashboard_glare_control.existing_flocked_material` | Existing `Material_Carpet` assigned to six declared forward panels; no geometry change |
| `lettering_material` / `base_and_emission_rgb_linear` | One new `Material_CabinLettering`, RGB `(0.5, 0.65, 0.75)`; constant emission 0.2, roughness 0.6, metallic 0, IOR 1.5, alpha 1, transmission 0 |

The tire operation removes the old raised shoulder trim, retains the 64-segment tire body and four 4 mm circumferential channels, and subtracts a closed disconnected cutter assembly. Original corner normals are transferred only on surviving original surfaces; true cut walls keep their actual normals. The earlier dented normal-transfer attempt remains a failure. Final evaluated validity, rolling appearance and continuous steering/travel clearances are separate checks.

Each header becomes one closed 10-point rail section by inserting four wall points into the existing six-point section. The original roof-facing flange remains intact. Its top follows the existing underside; the fixed 25-station lower tables close three measured headliner sightlines while relieving the B-post. The former outward return collided with a rear door window and was rejected. [Exact QA header handoff](../../../reports/p1-018/qa/roof-header-32/handoff04.json).

The six flocked meshes are `LOD0_InstrumentShade`, `LOD0_InstrumentShadeWing_-1`, `LOD0_InstrumentShadeWing_1`, `LOD0_InstrumentBinnacle`, `LOD0_DashboardUpper`, `LOD0_NavigationSurround`. The four static lettering meshes are `LOD0_NavigationTitle`, `LOD0_ClimateSetpoint_-0.143`, `LOD0_ClimateSetpoint_0.143`, `LOD0_RadioDisplay`.

Actual ray/tag isolation traced the broad windshield ghost to the instrument shade/binnacle and the night ghost to the navigation title sharing headlight emission. [The immutable material handoff](../../../reports/p1-018/research/windshield-reflection-32-01/handoff-05.md) retains matched source32 baselines and all trials. The five-light candidate leaves glass, light sources and all geometry intact, removes the headlight driver from these four labels, and uses a matte flocked surface on the forward panels. Existing glass remains a portable alpha/transmission approximation, not an exact laminated-glass optical model. Label emission is a shader parameter; display-referred luma statistics are not lux or luminance claims.

The isolated ten-object material operation changes no triangle, vertex, normal or UV and raises shipping material use from 23 to 24 of 32. It adds no navigation, climate, radio or rear-cabin simulation. The 150,000 LOD0 and 200,000 total triangle ceilings remain unchanged; final evaluated cost, all source/export/native comparisons and human visual/rights/usability/handling approvals are pending. Source32 evidence is not transferred automatically to source33 or canonical shipping artifacts.

## Powertrain reference and gameplay boundary

The US S6 reference is a longitudinal **3993 cm³ V8**, 84.5 × 89.0 mm bore/stroke, aluminum block/heads, **450 US hp at 5800–6400 rpm**, **406 lb-ft at 1400–5700 rpm**, seven-speed dual-clutch transmission and permanent AWD (F). [US p50](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf). Keep US hp separate from PS: 1 mechanical hp = 745.6999 W, 1 PS = 735.49875 W. Factory acceleration, 155 mph limiter and drag coefficient are reference facts, not implemented performance targets.

Audi service drawings support hot-V turbo placement and liquid-cooled upper-engine charge cooling. Exact 2016 gearbox code/final-drive arrangement, oil/coolant service fills, coolant heat rejection, pipe sizes and detailed suspension geometry remain unresolved reference values. A pre-facelift 0B5 table is not an exact 2016 drivetrain specification. [21H7 service drawings](https://static.nhtsa.gov/odi/rcl/2022/RCRIT-22V178-1437.pdf), [2014 family service reference, pp161–162](https://static.nhtsa.gov/odi/tsbs/2013/MC-10203510-9999.pdf).

The original instrument proxy ratios are `3.6, 2.19, 1.52, 1.15, 0.9, 0.72, 0.59`, reverse `3.4`, final drive `3.76`, idle/redline **750/6500 rpm**. These estimate the displayed gear/RPM. Existing custom four-raycast physics remains authoritative; Starter stays **125 mph**, HighSpeedValidation **250 mph**. Visible cooling/exhaust/fuel assemblies do not implement mechanical or thermal simulation.

## Modeling tolerances versus source uncertainty

The following are acceptance limits for the original target, separate from uncertainty in donor research:

| Check | Declared requirement |
| --- | --- |
| Overall final dimensions | ±5 mm |
| Hardpoint positions | ±2 mm |
| Wheelbase, tracks, radius | ±0.5 mm |
| Hinge axis | ±0.1° |
| Panel gap | Nominal 3.5 mm; range 2.5–4.5 mm |
| Glass / panel skin / hem | 4.5 / 1.2 / 3 mm O targets |
| Tire clearance through steering/travel | ≥5 mm |
| Moving solid clearance | ≥1 mm |
| Unintended penetration rejection threshold | >1 mm; this is not permission to ignore observed contacts |
| Wiper rubber/glass | 0–2 mm over ≥90% of span |

Unknown factory clearance, axle distribution, wheel offset, exact travel/steering geometry and usable modified fuel capacity stay unknown. They do not widen the original model's acceptance tolerances. Final visual, usability, driving-feel and source/asset rights approval remain pending human gates.

## Revision17 stowed restraints and current source binding

Revision16 was locked but never built: its candidate10 had two center-ribbon self-crossings and an incomplete rear guide grip. Revision17 adopts candidate11 before source34 construction. These are **O original fabrication choices**, not factory Audi dimensions. Source uncertainty and the measured mesh tolerance remain separate.

| Field under `original_packaging.restraints_revision17` | Locked value |
| --- | --- |
| `web_width_m` / `buckle_branch_width_m` / `closed_web_thickness_m` | 0.045 / 0.025 / 0.004 m |
| `model_tolerance_m` / `nonmating_clearance_guard_m` | 0.0001 / 0.001001 m |
| Front top/bottom, source XYZ | [[0.696, -0.622, 1.155], [0.737, -0.622, 0.44]]; mirror X for left |
| Rear guide, source XYZ | [0.704, -1.495, 1.208]; mirror X for left |
| Rear guide envelope / one-segment bevel | [0.053, 0.019, 0.038] m / 0.004 m |
| Center guide / buckle / release, source XYZ | [0.1, -1.2285, 1.025] / [-0.1, -0.98, 0.5365] / [-0.1, -0.942, 0.5365] m |
| Full cloth routes and continuous across vectors | Exact arrays in `restraints_revision17`; `tools/vehicles/endurance_sedan/restraints.py:build` implements them |

Actual source34 passes 40 complete finite/interface rules, all six exhaustive cloth triangle-pair self checks and two complete 44-plane rear guide containment checks. All 1,093 authored LOD0 triangle-coordinate multisets equal source33 plus the exact tested recipe. The recipe saves 412 triangles (1,404 replaced, 992 authored). Its completed candidate export reports 149,428 / 26,726 / 10,136 shipping LOD triangles. [Source34 handoff](../../../reports/p1-018/research/source34-handoff-01/handoff.json).

The physical package remains an unoccupied stowed cabin. Belt latching, textile dynamics, retractor mechanics, occupant motion and load certification are not implemented. Final platform, export reproducibility, full media and human gates remain separately owned.
