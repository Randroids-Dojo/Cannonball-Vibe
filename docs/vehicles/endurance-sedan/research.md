# P1-018 endurance sedan engineering research

Research date: 2026-09-10 UTC. Scope: engineering reference, configuration verification,
source uncertainty and the lead's original hardpoint lock before blockout. This dossier
does not claim a finished asset, verified handling, a certified fuel-system design or
human rights approval. The lead owns the Blender scene and the final fictional identity.

## Decision and exact comparison vehicles

Use the **2016 US Audi S6, C7 facelift/4G, 7-speed S tronic, quattro**, with Prestige,
Black Optic and Individual Contour Seating as a coherent *reference configuration*.
The option selection is supported by the US brochure; it is not an assertion about
the options installed on the record car. The original model uses a different exterior,
lamp graphics, interior design and 19-inch wheel design. The working fictional identity
is **Meridian S8R**, subject to the lead's final decision and human rights review.
See [Audi US brochure, printed pp43 and 50–51](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf).

| Comparison | Exact reference configuration | Why it matters | Limitation |
|---|---|---|---|
| Selected Audi | 2016 US S6 Prestige, C7 facelift, quattro, 7-speed S tronic; optional comfort seats and Black Optic | The record builder explicitly identifies a 2016 S6; a long wheelbase, adaptive air suspension, four-zone cabin and 75 L tank give the project an evidence-based endurance package. | Record modifications and pandemic traffic are distinct from stock capability. Exact suspension travel, axle loading and wheel offset were not established. |
| Mercedes | 2016 US AMG E63 S **Sedan**, W212 facelift, AMG Performance 4MATIC, 7-speed MCT | Stronger stock output; adaptive suspension with rear air springs. A closely related 2015 E63 was the team's previous Cannonball car. | The firsthand account identifies the 2015 donor as E63 AMG, without independently proving S trim. Do not transfer its modified figures to this 2016 comparison. |
| BMW | 2015 US M5 Sedan, F10 facelift, **DKG7/DCT**, non-Competition, the official sheet's 20-inch wheel configuration | Detailed official hardpoints and mass distribution; long wheelbase, 80 L tank, rear-wheel drive and active rear differential. | This is deliberately the verified 2015 sheet, not a relabeled 2016 model. The famous earlier M5 Cannonball reference belongs to another generation; no F10 record is asserted here. |

Sources: [Mercedes US 2016 brochure, PDF p25](https://s3.amazonaws.com/cdn.autoipacket.com/brochures/mercedes-benz/2016/2016-eclass-sedan_opt.pdf),
[BMW US 2015 technical data, DKG7 column](https://www.press.bmwgroup.com/usa/article/attachment/T0141998EN_US/361020),
[BMW F10 launch architecture](https://www.press.bmwgroup.com/usa/article/detail/T0114798EN_US/text.html).

The Audi is selected for the combination of a directly documented donor year,
all-wheel-drive packaging, compliant adjustable suspension, comfortable seating,
and credible room for three crew plus endurance equipment. This is an engineering
and art-direction inference, not a measured claim that it is inherently more reliable
or faster than the other two. Mercedes offers more factory output; BMW offers a
larger factory tank and excellent technical documentation. Those advantages do not
outweigh the S6's direct correspondence with the user's requested endurance story.

## What the Cannonball evidence establishes

Builder/driver Arne Toman's [S6 account](https://www.arnesantics.com/projects/current-cannonball-run-record-holder-audi-s6/)
identifies a 2016 car and a May 2020 elapsed time of 25 hours 39 minutes. It lists RS7
turbochargers, an ALPHA heat exchanger and downpipes, revised calibration, a trunk
auxiliary tank and dual transfer pumps. These are firsthand **modified-car claims**,
with medium confidence in their measurement and no independent certification here.
The historical page title is not evidence that its record is still current.

The owner specifies **45 US gallons auxiliary**, or 170.3435 L. With the nominal
75 L factory tank, the arithmetic total is approximately 245.34 L; neither the sum
nor a rounded 65-gallon description proves usable capacity. Claims elsewhere of
67 gallons *auxiliary* are not adopted. The finished fictional car instead has a
smaller 100 L auxiliary assembly and 175 L nominal total, preserving the rear cabin
and inspectable luggage space.

The [owner's earlier E63 account](https://www.arnesantics.com/projects/cannonball-run-world-record-holder-e63-amg/)
identifies a modified 2015 E63 AMG, 27 hours 25 minutes in November 2019, a 45-gallon
auxiliary tank, a trunk/cabin firewall and an approximately 800 hp claim. Engine
output claims are not interchangeable with wheel horsepower. This supports the
layout of a properly separated trunk equipment bay; it does not license copying
the real car's appearance, disguises, logos or device interfaces.

[Alex Roy's firsthand retrospective](https://www.thedrive.com/news/31367/why-you-need-a-german-sedan-to-break-the-cannonball-run-record)
identifies his 2000 E39 M5 and 2006 run, and explains the importance of crew mass,
dashboard space, spare-wheel/trunk packaging and suspension load. His reported
post-run axle concern is an anecdote, not a technical failure analysis. It supports
the endurance packaging brief; it is not evidence for the later F10's performance.

## Dimension sheet and conflicts

The machine-readable [reference-values.json](reference-values.json) is the value
registry. Each important fact includes source, locator, units, classification,
confidence, uncertainty and a proposed model/runtime parameter. A `reference.*` or
`comparison.*` mapping is descriptive research data, not a live runtime binding.
The final asset/setup contract remains the lead's responsibility.

| Quantity | Audi US 2016 published | Audi UK 2016 S6 drawing | Locked original sedan |
|---|---:|---:|---:|
| Overall length | 193.9 in = 4.92506 m | 4.931 m | 4.940 m |
| Body width, mirrors excluded | 73.8 in = 1.87452 m | 1.874 m | 1.900 m |
| Mirror width | 82.1 in = 2.08534 m | 2.086 m | 2.100 m |
| Height | 57.8 in = 1.46812 m; datum unstated | roof 1.430 m; aerial 1.468 m | roof 1.450 m |
| Wheelbase | 114.7 in = 2.91338 m | 2.917 m | 2.920 m |
| Front/rear tracks | 63.6/63.2 in = 1.61544/1.60528 m | 1.615/1.607 m | 1.620/1.610 m |
| Front/rear overhangs | not stated | .924/1.090 m | .940/1.080 m |
| Ground clearance | not verified | not specified in drawing | .135 m static target |
| Curb mass | 4,486 lb = 2,034.815 kg | different market/mass convention; not substituted | 2,040 kg fictional base with full 75 L factory tank |
| Front load share | not verified | not verified | 54% at fictional 2,400 kg running condition |

The [Audi UK guide](https://cache3.arabwheels.sa/system/brochures/48/original/a6-s6-saloon-avant_compressed.pdf?1762339880=)
was visually verified as Edition 2.3, October 2015, **2016 model year**, with the
S6 Saloon drawing on printed/PDF p81. It is a manufacturer-authored document on an
archival mirror, not an independently measured car. The US table is printed p51,
PDF p27. The UK overhang sum closes exactly: 924 + 2917 + 1090 = 4931 mm.

Resolution rules:

- The US height nearly equals the UK's aerial height. This is a plausible datum
  explanation, not proof of why the US table uses it. Roof and aerial remain separate.
- US versus UK wheelbase, length and rear track differences are preserved. Some
  differences exceed simple 0.1-inch rounding; market, equipment, measurement or
  publication differences were not independently resolved. Never average them.
- UK maximum front headroom is 1046 mm; US front headroom **with sunshade** is
  944.88 mm. These are different definitions, not a 101 mm modeling error.
- UK trunk volume is 530 L by VDA blocks, 995 L with rear seats folded. US cargo
  is 14.1 ft³, about 399.27 L, with no matching method stated. Preserve both.
- A parsed table initially places Mercedes weights adjacent. Visual inspection
  establishes **4,276 lb for AMG E63 S Sedan**, 4,431 lb for E350 wagon and 4,619 lb
  for AMG wagon. Its lower-page dimension sketch depicts the base sedan, so its
  tracks/body width/overhangs are not attributed to the AMG.
- The official [2016 Mercedes operator manual](https://www.mbusa.com/content/dam/mb-nafta/us/owners/manuals/2016/operators/MY16_E-Class_Sedan_Wagon_Operator.pdf)
  lists 66 **or** 80 L for AMG fuel tanks, depending on equipment (printed p338).
  A single exact capacity is not assigned to the comparison car. Its exact
  S-MODEL 4MATIC summer table (p327) verifies 255/35ZR19 front and 285/30ZR19 rear,
  9J/9.5J wheels and 37/52 mm offsets. The generic AMG dimension section (p346)
  differs from the sales brochure; the manual has a 2014 editorial date. Retain
  both records, prioritize the exact 2016 sales table for comparison, and do not
  use either set as the fictional car's locked dimensions.
- US published horsepower remains labeled US `hp`, not `PS`. One mechanical hp
  is 745.6999 W; one PS is 735.49875 W. A European 450 PS label cannot be treated
  as the same quantity as the US brochure's 450 hp. BMW's early launch release
  also contains preliminary mixed hp/kW figures; the exact 2015 data sheet wins.
- The [2016 Audi fluid chart](https://static.nhtsa.gov/odi/tsbs/2015/MC-10128487-9999.pdf)
  still labels its S6 cell CEUC/420 hp, while the brochure says 450 hp. The
  [2017 chart](https://static.nhtsa.gov/odi/tsbs/2016/SB-10092581-0699.pdf) identifies
  CTGE/450 hp. Fluid quantities or engine-code identity are not silently inherited
  across this conflict. No real maintenance procedure is prescribed by this dossier.

## Locked fictional hardpoints and loaded condition

These are deliberate original dimensions accepted by the production lead before
blockout, not human art or handling approval. Blender uses meters, +X right, +Y
forward, +Z up; the origin is the midpoint between axles on the design ground plane.
The export/adapter must implement and test the source-to-Godot axis conversion.

| Anchor | Blender source XYZ, m |
|---|---|
| Front left wheel | (-.810, +1.460, .3433) |
| Front right wheel | (+.810, +1.460, .3433) |
| Rear left wheel | (-.805, -1.460, .3433) |
| Rear right wheel | (+.805, -1.460, .3433) |
| Design contact anchors | same X/Y as wheel centers; Z = 0 |
| Front/rear body extrema | Y = +2.400 / -2.540 |
| Longitudinal center of mass | Y = +.1168; vertical CG remains a separately declared runtime choice |

Square tires are **255/40R19** on original 8.5Jx19 wheels. Nominal diameter is
19 × .0254 + 2 × .255 × .40 = **.6866 m**, radius **.3433 m**, and nominal sidewall
depth .102 m. This is a nominal tire-code calculation, not the dynamic loaded radius.
The Audi's 255/35R20 reference has .08925 m nominal sidewalls; the original 19-inch
choice adds 12.75 mm of sidewall depth. Final tire tread, sidewall shape, barrel,
fasteners and spoke styling are original geometry. Wheel offset requires a declared
original value and measured barrel/caliper/arch clearance.

The geometric inspection envelope is ±32° road-wheel steer, +85 mm bump and
75 mm droop from design ride position. These are fictional targets. The factory's
20 mm selectable air-suspension height adjustment is **not** suspension travel.
An exact stock kingpin axis, caster, camber curve, scrub radius, travel curve and
Ackermann pair were not verified. The custom four-raycast body simulation stays
authoritative; no hidden wishbone simulation is promised by modeled links.

The fictional running mass is exactly:

| Component | kg | Accounting boundary |
|---|---:|---|
| Base curb | 2040 | includes full 75 L factory fuel |
| Preparation | 31 | dry equipment/tank/bracket budget |
| Auxiliary fuel | 74.5 | 100 L × fictional .745 kg/L |
| Three crew | 240 | 3 × 80 kg |
| Luggage | 14.5 | secured portable kit |
| Total | **2400** | do not add factory fuel a second time |

At 54% front load and a 2.92 m wheelbase, the axle-midpoint CG offset is
(.54 − .50) × 2.92 = **+.1168 m**. The fuel-density assumption is an authored constant;
actual gasoline depends on blend and temperature. The 100 L auxiliary assembly has
a .90 × .48 × .28 m gross box, 120.96 L before walls, expansion space and internals.
It sits behind the rear bench in the trunk with a sealed partition and fastening
structure. Its nominal capacity is visual packaging, not engineering certification.

## Mechanical packaging and visible assemblies

The S6 US brochure establishes a longitudinal 3993 cm³ turbocharged V8, 84.5 × 89.0 mm
bore/stroke, aluminum block/heads, 32 valves, variable valve timing and cylinder
deactivation. Factory comparison ratings are 450 hp at 5800–6400 rpm and 406 lb-ft
at 1400–5700 rpm, with a 7-speed dual-clutch gearbox and permanent AWD. A sport rear
differential is optional. These figures inform believable proportions and instrument
ranges; they do not change the repository's starter-speed or validation-profile policy.

The [Audi service campaign 21H7](https://static.nhtsa.gov/odi/rcl/2022/RCRIT-22V178-1437.pdf)
provides legitimate service illustrations covering the 2013–2017 S6. It identifies
coolant hoses at the charge-air cooler (p18), the cooler housing above the inner-V
(p23), airbox/ducts, throttle valve, coolant crossover, harness and turbo oil/coolant
lines. This supports a liquid-cooled charge-air assembly and a densely packaged
engine bay. The same campaign documents the turbo oil-strainer problem, so this
research does not describe the stock package as unconditionally reliable.

Model a structural front carrier, depth behind the radiator openings, a main heat
exchanger/fan plane and a secondary endurance heat-exchanger plane; airflow passages
must have visible exits around the undertray/engine bay. Place the V8 longitudinally,
gearbox into the center tunnel, front half shafts at the front axle, a protected
propeller-shaft tunnel and rear differential/half shafts. Twin exhaust paths run
rearward with heat shields, hangers, silencers and original dark metal outlets.
Show undertrays, wheel liners, front/rear subframes, jack points and attachment
heads where inspection can expose them. Exact pipe routes, core dimensions and
heat-rejection performance are original approximations unless separately sourced.

The [2014 Audi service reference](https://static.nhtsa.gov/odi/tsbs/2013/MC-10203510-9999.pdf)
gives 0B5 family gearing in pp161–162, including 3.692/2.150/1.406/1.025/.787/.625/.519
for several codes, while another listed code differs. This is **pre-facelift family
evidence**, not verification of a 2016 VIN/transmission code. Front combined and rear
bevel ratios differ in the table and cannot simply be swapped. If runtime needs a
gear/RPM presentation model, declare the chosen proxy explicitly and test it.

The published S6 disc diameters are 15.7/14.0 inches (398.78/355.60 mm), ventilated
front/rear. Original caliper envelopes and disc thickness must fit the 19-inch barrel.
The suspension uses five-link front and trapezoidal-link rear architecture with air
springs. Model links, boots and fasteners to explain the visible package; do not
pretend those visual parts carry the physics forces.

For comparison, the [BMW 2015 sheet](https://www.press.bmwgroup.com/usa/article/attachment/T0141998EN_US/361020)
defines 1991 kg US curb mass, 52.5/47.5% distribution, 80 L fuel, 111 mm clearance,
2964 mm wheelbase and 1627/1582 mm tracks. Its DCT ratios and rear final drive are
recorded separately in the JSON. The [F10 launch release](https://www.press.bmwgroup.com/usa/article/detail/T0114798EN_US/text.html)
supports its reverse-flow twin-turbo architecture, liquid charge cooling, active
rear differential, adaptive damping, high-strength steel structure and aluminum
hood/front fenders/doors. Those family descriptions do not override later exact data.

## Cabin, occupant envelope and endurance preparation

The original cabin must retain five modeled seats and three credible occupied
positions for the running-mass condition. The driver's position is left-hand drive.
The Audi US reference supplies 41.3/37.4-inch front/rear legroom and 57.5/56.3-inch
shoulder room. The UK drawing supplies 1527/1491 mm elbow room. These are packaging
checks, not exact H-point coordinates. Driver eye position, seat rail travel, seat
back angle, pedal reach and steering column position must be declared as original
hardpoints and inspected with an occupant proxy before surface detail.

Use separate adjustable-looking front seats with independent headrests, lumbar
volume, stitched bolsters and realistic cushion compression; a rear bench with
three headrests, belts and buckles; footwells and a raised central tunnel. Include
seat rails, front/rear door cards, pull handles, switches, vents, carpet, headliner,
sun visors, grab handles, parcel shelf and rear demister lines. Airbag seams and
seatbelts may be modeled without claiming restraint-system simulation.

The dashboard should provide an original hooded instrument binnacle, physical
climate/audio controls, readable speed/gear/RPM/fuel and specific warning states.
Use an original central display and switch labels; no copied MMI interface or OEM
gauge graphics. Keep low-reflectance dark upper dash surfaces out of the windshield
reflection path. A passenger navigation/comms display should sit below forward
sightlines, on a bracket with a plausible cable route and strain relief. A compact
radio, headset/storage, charging sockets, water bottles, extinguishing equipment
and restrained tool/luggage kit make the preparation legible without filling the
cockpit with decorative screens. Equipment must clear the shifter, doors and seat belts.

The UK drawing's trunk plan is **1176 mm fore/aft × 1050 mm transverse**, with a
949 mm aperture and a 649 mm loading sill; these were read from the actual drawing,
not flattened text order. Keep access to luggage, tank mounts and modeled service
ports visible with the trunk open. A sealed trunk/cabin bulkhead follows the firsthand
E63 preparation account. No real pump flow, vapor containment, crashworthiness or
fuel-transfer control is claimed unless independently implemented and evidenced.

## Original styling and material direction

The benchmark governs engineering plausibility. The exterior is a new sedan with
four distinct doors, an original roof/greenhouse arc, shoulder treatment, sill
section, front/rear bumper volumes and short integrated rear lip. Use an original
split lamp signature, original grille opening proportions, original spoke layout,
mirror supports, door handles and fictional identity. Do not trace the Audi Singleframe,
Mercedes grille, BMW kidneys, OEM lamp signatures, badges, record-car disguises or
cabins. No purchased/restricted mesh is part of this research.

Panel hierarchy: structural cabin shell, roof/pillars, four separate door shells,
hood, trunk, fenders/quarters, bumpers and rockers. Visible openings need inner
skins, folded-looking edges, jambs, latch/hinge anchors, seals, shut faces and
fastening points. Glass must sit in a frame with a seal/frit boundary and credible
thickness, with mirror backing and windshield contact for the wipers. Exact factory
sheet, glass and seal gauges were not verified; those are original visual dimensions.

Black must remain readable in neutral lighting. Use a dark dielectric clearcoated
paint response with restrained roughness variation; distinguish satin painted
metal, black plastic, rubber, leather, textile, bare alloy, brake iron and glass by
roughness, specular behavior and microstructure. Dark paint is not metal merely
because it coats metal. Any future external texture needs source, license, color
space, physical scale and hash; none is supplied or licensed by this research.

## Proposed measurable acceptance, before detail

These proposed tolerances accompany the lead's locked dimensions and should be
adopted into the authoritative feature matrix before production. Source uncertainty
does not enlarge permitted modeling error. For example, an unknown factory offset
does not excuse a wheel intersecting the original design's caliper.

| Feature | Proposed measurement / acceptance | Required evidence |
|---|---|---|
| Body dimensions | each locked principal dimension within 5 mm | evaluated-mesh bounds, orthographic views |
| Axles/tracks/contact anchors | wheelbase/track/anchor coordinates within 2 mm; nominal tire radius within 1 mm | Blender and clean imported GLB measurements |
| Panel fit | 3.5 mm target gap, ±.5 mm local variation; adjoining intended-flush faces within 1 mm | fixed grazing reflections and closeups |
| Moving clearances | at least 8 mm wheel-to-fixed-part clearance throughout declared steering/travel combinations | sampled evaluated geometry plus actual runtime extrema |
| Openings | hinge locations within 2 mm of lock; at least 3 mm rigid-part clearance apart from intended seals | four doors, hood/trunk full sweep captures |
| Wipers | blade contacts windshield within 0–2 mm at sampled sweep positions; reproducible park | closeup plus runtime animation |
| Cabin | at least 40 mm headliner clearance at declared occupant proxy; all required instruments in driver view | occupant/eye anchors, cockpit capture |
| Visibility | no camera inside opaque surfaces; rearward scene actually visible in mirrors | gameplay captures with known moving target |
| State presentation | speed/gear/RPM/fuel and warnings correspond to explicit state; light, wiper and opening changes accessible | scenario assertions and actual rendered captures |

A modeled engine bay is an assembly. A gear display is presentation. Mirrors require
a measured runtime rendering implementation. Thermal behavior, mechanical engine
simulation, air-spring leveling, restraint operation and fuel transfer are separate
claims. Shared rigging and wrapper infrastructure may implement the required features;
research does not authorize replacing the accepted four-raycast simulation.

## Research provenance, verification and remaining decisions

The research agent visually inspected actual PDF pages: Audi US option/technical
spreads, Audi UK S6 wheel/cabin and dimension pages plus the dated back cover,
Mercedes AMG specification column, and BMW's single-page DCT table. This corrected
both the Mercedes weight-column ambiguity and the Audi trunk drawing-axis reading.
The PDF and extracted-text evidence is local under `reports/p1-018/research/`, with
SHA-256 source records. These references are research inputs, not shipping content.

`build_reference_values.py` reconstructs the JSON offline and checks hardpoint sums,
tire arithmetic, mass accounting, CG offset, unique IDs and source references. It
does not test an asset or runtime. The research evidence manifest records exact
revision, UTC time, tool versions, commands, failures and output hashes. Failed
Audi Georgia/DNS, Audi Middle East/403 and erWin missing-document endpoints were
not treated as acquired evidence; the readable dated UK archival brochure and
public NHTSA manufacturer service references were used instead.

Remaining factory unknowns are explicit `null` entries in the value registry:
wheel offset, exact 2016 transmission code/ratios, suspension travel, alignment and
steering-axis geometry, detailed brake envelope, H-points/eye ellipse, CG height,
panel/glass gauges and measured cooling capacity. The lead must resolve the model's
own versions through original dimensions and inspection. Human visual direction,
driving enjoyment, usability, physical-wheel feel and final source/asset rights
reviews remain open; neither the engineering lock nor this research clears them.
