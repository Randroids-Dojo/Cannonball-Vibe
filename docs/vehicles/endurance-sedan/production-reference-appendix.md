# P1-018 production reference review

Reviewed 2026-09-10 against the locked Meridian S8R specification. This appendix
informs construction and inspection; it does not amend the specification, certify
real vehicle modifications, or approve source rights. The editable model keeps
original bodywork, equipment shapes, graphics, and identity under ADR-0012.

The selected photographs and diagrams were actually opened as images. Their
paths, hashes, source URLs, variant limits, and observations are recorded in
[production-reference-evidence.json](../../../reports/p1-018/research/production-reference-evidence.json).
Cached reference images remain research evidence, not runtime textures.

| Assembly | Observed reference and confidence | Meridian production implication |
| --- | --- | --- |
| Engine bay | Audi's 21H7 repair drawings, pp17–18 and 23–25, show the paired turbo assembly above the inner V, the charge-air cooler across the forward upper engine, multiple coolant connections, and a side air-filter housing feeding formed intake ducts. This is factory service material covering the US 2013–2017 S6; high confidence in assembly relationships, no dimensional extraction. [Audi campaign drawings](https://static.nhtsa.gov/odi/rcl/2022/RCRIT-22V178-1437.pdf). | Give the longitudinal engine visible depth beneath its original cover: separate bank covers, inner-valley turbo forms, intake ducts, front charge cooler and hoses. Place the radiator/fan pack ahead of the engine. A cover with unrelated tubes floating on top would not reproduce the observed construction. This is a modeled assembly, not turbo, thermal, or mechanical simulation. |
| AWD structure | Audi of America's 2012 A6 introduction, printed pp20–21, shows a central prop shaft, rear final drive, half-shafts and rear subframe. Its separate 0B5 illustration shows the front final drive near the bellhousing. High confidence for the shared platform architecture; the large front assembly is an earlier A6/0BK illustration, **not** an exact 2016 S6/0B5 drawing. [Audi SSP 990613](https://content.datarunners.net/content/SSP/990613.pdf). | Preserve a continuous longitudinal drivetrain path with CV boots, supports and a distinct rear differential. Shape the Meridian's visible casings and brackets originally; do not attach the front axle to the rear of a generic transmission or copy the illustrated 0BK housing. |
| Underbody and exhaust | AWE's 2014 S6/S7 guide, pp2–3, contains actual installed underside photographs: broad dark covers, a foil-lined center tunnel, cross brace, paired exhaust paths, central resonator and rear mufflers. The overview's rear diagonal braces are specifically **S7-only**. Later detail photographs show AWE replacement pipes and their clearances; these are modified hardware, not factory tube dimensions. [Manufacturer guide, retailer mirror](https://www.tdotperformance.ca/media/instructions/awe-installation_instructions_awe_s6s7_touringedition_exhaust.pdf). | Use substantial undertrays with fastened boundaries, inset heat shields and separate exhaust sections; avoid exposing an empty floor. Keep clearance around the rear anti-roll bar and drivetrain. Retain silencing volumes for the endurance concept. S7-only braces and aftermarket tube sizes are not S6 specification inputs. |
| Factory fuel and body structure | Audi AG's A6/S6 2011–2018 rescue sheet places the factory tank under the rear seating region, the battery farther aft, and reinforcements through the sills and pillars. It is a rescue-location schematic, not a dimensioned tank drawing. [Audi rescue sheet, status 08/2020](https://media.audi.com/is/content/audi/microsites/audi-com/en/rescue/rescue-data-sheets/datenblaetter/a6/Audi_A6__Sedan_2011_4d_GD_EN.pdf). | Keep distinct main and auxiliary stores, a rear bulkhead, sill structure, substantial B-pillars and believable floor depth. The donor's under-rear-seat location is an observation; Meridian's original underfloor pair is a packaging deviation recorded below. The auxiliary cell does not replace the main storage. |
| Auxiliary trunk equipment | The actual fuel-cell photograph inspected is Arne Toman's **2015 E63 build**, with the full-size spare upright behind the cell and access for two filler nozzles. It establishes the builder's packaging approach, not the S6's exact installation. His separate S6 account reports a 45 US gal auxiliary cell (170.34 L). [E63 firsthand build](https://www.arnesantics.com/projects/cannonball-run-world-record-holder-e63-amg/), [S6 firsthand build](https://www.arnesantics.com/projects/current-cannonball-run-record-holder-audi-s6/). | Meridian's locked 100 L nominal cell in a 0.90 × 0.48 × 0.28 m gross box is original. Model a restrained enclosure behind the bench, mounts, a bulkhead boundary, protected fittings and service access. Show remaining luggage space honestly. The 120.96 L outer box volume does not establish usable capacity or installation safety. |
| Cabin | The US 2016 brochure's printed pp20–21 shows an S6 Prestige with Arras Red design equipment: hooded analog instruments, center display above vents, physical climate controls, gear selector and console controls, door armrests, and separate pedal/footrest surfaces. Printed pp10–11 shows an **A6 3.0T Prestige** with individual-contour seating; useful seat-family reference, not the same S6 option photograph. [Audi US brochure](https://cdn.dealereprocess.org/cdn/brochures/audi/2016-a6.pdf). | Preserve an ergonomic hierarchy: shaded driving instruments, reachable physical controls, central storage, knee/foot space, supported seating and padded contact surfaces. Meridian's black upholstery, stitch pattern, instrument graphics, controls and endurance screen arrangement are original. Avoid routing mounts or cables through airbags, sightlines or occupant space in the visual package. |
| Wipers | The factory 2014 A6/S6 quick-reference book's printed p229 shows a transverse motor/linkage assembly beneath the cowl. The US 2016 owner manual, printed pp51–52, distinguishes park, wipe and service positions and prevents service-position activation with the hood open. Factory sweep angles and blade contact profiles were not verified. [Audi service drawing](https://static.nhtsa.gov/odi/tsbs/2013/MC-10203510-9999.pdf), [2016 Audi manual, public mirror](https://www.carmanualsonline.info/audi-s6-2016-owners-manual/?srch=wipers). | Model arms emerging from cowl bosses with distinct blades, a low parking position and coordinated sweeps over the glass. Runtime sweep angles remain the locked fictional choices. Verify full motion against glass, hood and each other; a lever animation alone is not working wipers. |

The Borla A-35611 Rev B underside page was also inspected as corroboration, but
its figures are shared across S4/S5/S6 instructions and do not identify the exact
vehicle per photograph. It is excluded from exact S6 claims. One initially named
`production-s6-gallery-trunk.jpg` proved to be a grille/badge photograph when
opened; it is explicitly excluded from trunk evidence.

## Checks against the locked hardpoints

No specification conflict requiring a dimensional change was established by these
references. The following are implementation checks, not measured factory values
or completed mesh QA:

- Cowl `(Y=.740, Z=.970)` and header `(Y=.140, Z=1.395)` define an approximate
  windshield normal of source `(0, .578017, .816024)`. The locked wiper axes already
  match this direction. World-Z rotation would not stay on this raked surface.
  Each pivot is 11.46 mm above the planar glass at its Y coordinate; the arm boss
  may stand proud, while blade geometry still needs contact compensation.
- The hood hinge is only 5 mm longitudinally and 20 mm vertically from the wiper
  pivot line. Test the hood's full opening with parked arms and check any permitted
  simultaneous movement. These distances alone do not prove an intersection.
- The cockpit eye is 0.76 m above and 0.23 m aft of the driver reference, with an
  eye-to-steering-center distance of 0.671 m; the accelerator is 0.88 m forward of
  that reference. These calculations are consistent with a reclined seating
  concept but do not validate anthropometry, knee clearance, mirrors or view
  obstruction. Perform the actual seated-camera and occupant-envelope review.
- The auxiliary box, rear bench, parcel shelf, rear suspension space and trunk
  hinges must coexist in the finished mesh. Leave room for mounts and fittings
  outside the nominal box; retain the locked mass accounting and fuel capacity.

## Source05 construction rationale and limits

This dated review applies to the constructor snapshot captured at
`2026-09-10T23:31:46.107909+00:00`, identified by
[its input manifest](../../../reports/p1-018/research/production-code-audit-05-inputs/manifest.json).
It records original assembly decisions and their evidence limits, without
changing locked capacities, hardpoints or gameplay parameters. Subsequent
packaging corrections need their own mesh evidence.

The revised engine places two original `WaterToAirChargeCooler` forms over the
forward upper engine, with hot charge pipes, cold pipes into separate intake
plenums, and coolant hoses toward a distinct front `ChargeCoolingRadiator`.
The relationship is consistent with the liquid charge-cooling architecture
shown in [Audi's service drawings, pp17–18 and 23–25](https://static.nhtsa.gov/odi/rcl/2022/RCRIT-22V178-1437.pdf).
The two housing shapes, their dimensions, twin airboxes, brackets and hose paths
are Meridian design choices; the source does not establish them as exact S6
components. The front liquid radiator is not a front air-to-air charge cooler.

These parts represent visible heat exchangers, ducts and plumbing. They do not
establish a complete hydraulic circuit, coolant return routing, pump capacity,
thermostat operation, pressure losses, charge temperature or heat rejection.
No cooling, turbocharger or fuel-transfer simulation is implemented or implied
by this reference review. Instrument RPM and gear presentation remain subject
to the explicitly documented runtime approximation.

The modeled paired downpipes, center silencing volume, rear mufflers and outlet
paths use the arrangement observed in
[AWE's installed S6/S7 photographs](https://www.tdotperformance.ca/media/instructions/awe-installation_instructions_awe_s6s7_touringedition_exhaust.pdf)
as a construction reference. Their dimensions, materials and routing are
original. Visible pipes and mufflers do not establish gas flow, exhaust acoustics,
catalyst performance, emissions compliance or endurance thermal validation.
No S7-only brace is required by the S6 benchmark. Continuous connections and
clearance from fuel, driveline and body remain actual-asset inspection criteria.

The source05 main reservoir uses two original underfloor lobes, each
`0.364 × 1.34 × 0.094 m`, at source centers
`(±0.428, −0.60, 0.188) m`. Their combined rectangular gross envelope is
`91.69888 L` before edge rounding; the locked **combined nominal main capacity
remains 75 L**. This is not two 75 L tanks. A crossover rises through dedicated
floor openings into a hollow console chase. Those features express an intended
protected route; they are not proof of sealing, usable volume or physical
installation safety. Unlike the donor location in
[Audi's rescue schematic](https://media.audi.com/is/content/audi/microsites/audi-com/en/rescue/rescue-data-sheets/datenblaetter/a6/Audi_A6__Sedan_2011_4d_GD_EN.pdf),
this original envelope extends along the cabin floor. It is not a reconstructed
factory tank. The separate 100 L nominal trunk cell and 175 L total remain the
locked fictional values.

Source05 still has packaging defects, including contacts between the main lobes
and existing exhaust/structure. The additional bellhousing connects the engine
and transmission casings, but the front final-drive casing and its connection
to the front half-shafts remain a visible construction item. The detailed
[source05 audit](../../../reports/p1-018/research/production-code-audit-05.json)
and independent QA identify correction work; this appendix grants no assembly,
visual, functional or rights approval.

## Revision 5 ergonomic targets

The earlier hardpoint calculations in this appendix describe the initial
review, not the current revision 5 wheel-to-eye distance. The
[current dimension sheet](dimension-sheet.md) is generated from the canonical
specification. [Packaging revision 5](packaging-revision-v5.md) moves the
instrument anchor from source `(-.430,.550,.958)` m to `(-.430,.400,1.050)` m
and lowers the steering-wheel center from `(-.430,.210,.910)` m to
`(-.430,.210,.855)` m. The resulting eye-to-wheel-center distance is
approximately **0.697155 m**, calculated from the unchanged eye
`(-.430,-.390,1.210)` m. These are original target values; source10 rim
occlusion prompted the correction. They do not establish a readable final
display or occupant clearance without the required new source/runtime views.
The separate telltale and digit-driver defects require independent functional
verification. No exact Audi steering or instrument hardpoints were measured.

## Original material and lettering provenance

The six paint, leather and fabric images are **project-original generated
data**. [microtextures.py](../../../tools/vehicles/endurance_sedan/microtextures.py)
uses SHA-256-derived named seeds (`meridian-s8r-{kind}-v1`), NumPy's seeded
generator, periodic smoothing and authored trigonometric height functions.
Finite differences form tangent-space normals; the same declared height field
modulates a separate roughness image. Thus the two channels are authored from
the same surface field, not statistically independent image sources. Each map
is 512×512 at a 0.25 m repeat (2048 texels/m), stored as an embedded 8-bit PNG
with `Non-Color` data interpretation. Paint normal strength is 0.60; leather
and fabric use 1.0. Material response and physical scale are original choices,
not measured donor finish data. No photograph, scan, downloaded texture or
external image is an input to these constructors.

The [packed-texture diagnosis](../../../reports/p1-018/research/packed-textures/README.md)
retains exact constructor/source hashes, original and corrected packed bytes,
clean-process reopen checks, and unpacked-path verification. The six source10
PNGs equal both isolated constructions byte-for-byte. The verified fix changes
reload/path handling and portable packed metadata; it changes no texture pixel.
Production rebuild/export verification remains distinct from that isolated
result.

Lettering uses a separate provenance chain. The project's
[`text_mesh` helper](../../../tools/vehicles/endurance_sedan/cabin.py) creates a
default Blender `FONT` curve from an original label string and converts its
outline to mesh. It does not load a downloaded font or bake a photograph.
Blender **5.1.2 / ec6e62d40fa9e9d1bea33ad5d00148c99a4f0832** compiles
`release/datafiles/bfont.pfb` into its binary in
[the official datafiles build list](https://github.com/blender/blender/blob/v5.1.2/source/blender/editors/datafiles/CMakeLists.txt#L176).
Its [built-in font implementation](https://github.com/blender/blender/blob/v5.1.2/source/blender/blenkernel/intern/vfont.cc)
loads the registered in-memory font. The exact
[official PFB source](https://github.com/blender/blender/blob/v5.1.2/release/datafiles/bfont.pfb)
is 25,181 bytes, SHA-256
`a33954fdab9fb09b9d308cb7f970518293128922ffc523c0a22b3b314a9a56c6`;
its readable header identifies **Bfont, Regular, version 001.001**. This is
not the historical `bfont.ttf`/DejaVu asset and not proof that those older
font-license texts apply.

Original wording and placement do not make the font outlines project-original.
They are identified as bundled Blender-derived lettering. The sampled PFB
header contains no standalone license notice. A **2026-09-11 primary-source
follow-up supersedes the earlier unresolved source-data notice**: the official
historical [Bfont.c](https://raw.githubusercontent.com/blender/blender/90f443bb86bdf5efc87633816df76b4c3bd49554/source/blender/editors/datafiles/Bfont.c)
has a GPL-2.0-or-later notice covering the whole file and NaN Holding BV
2001–2002 attribution. Its complete 25,181-byte C array decodes byte-for-byte to
the current v5.1.2 PFB identified above. The [retained equality and notice proof](../../../reports/p1-018/research/font-license-review-20260911/license-chain.json)
and [attribution inventory revision 2](../../../reports/p1-018/research/material-provenance-v2/asset-input-inventory.json)
record that exact source-data license notice. This does not automatically settle
the rights treatment of generated glyph meshes, rendered media or the complete
GLB. Human source/asset/output rights review remains open; no blanket CC0,
public-domain status or final distribution approval is asserted.
This provenance explanation covers all meshes made by that helper, including
fixed cabin/equipment labels and separately marked source-preview display
glyphs. Converting a glyph to mesh does not erase its font ancestry. The Godot
runtime's independently drawn instrumentation requires its own runtime evidence.
[Retained source/font evidence](../../../reports/p1-018/research/material-provenance/font-details.json)
and [exact-version tree identity](../../../reports/p1-018/research/material-provenance/official-font-provenance.json).

## Portable footage encoder

[FFmpeg's official download page](https://ffmpeg.org/download.html) distributes
source and links Windows builds to [Gyan](https://www.gyan.dev/ffmpeg/builds/).
The lead-authorized portable essentials ZIP is release **9.0.1**, dated
2026-08-12, from the [versioned publisher release](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1).
The archive SHA-256 equals the
[publisher checksum](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.1-essentials_build.zip.sha256):
`fec81ae03971d9dd4be3ebe02e263bd2ec1d789483f931bdba5f5715e65da2e9`.

The unpacked tools are at
`.tools/ffmpeg-9.0.1/ffmpeg-9.0.1-essentials_build/bin/ffmpeg.exe` and adjacent
`ffprobe.exe`. Both `-version` calls returned 0 and reported
`9.0.1-essentials_build-www.gyan.dev`; the build enables `libx264`. This research
task performed no encoding or GPU/media job and changed no PATH setting. Exact
commands, HTTP metadata, archive/binary hashes and version output are retained in
[tooling/ffmpeg-evidence.json](../../../reports/p1-018/research/tooling/ffmpeg-evidence.json).

Source rights and final visual/functional approval remain human gates. This
reference review and the encoder verification do not satisfy those gates.
