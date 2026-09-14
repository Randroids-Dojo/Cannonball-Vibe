# P1-018 independent vehicle QA

Prepared 2026-09-10 by the independent QA agent. This is a test and observation
plan, not an asset acceptance or a human approval. No sedan render or runtime
capture had been supplied at preparation time. Every visual and functional row
below starts **pending**. Observations and retests belong in `defects.json` and
`reports/p1-018/qa/`; implementation acceptance remains in the delivery ledger
and the lead-owned specification/acceptance contract.

## Authority, ownership, and thresholds

Apply accepted ADR-0012, ADR-0023 and ADR-0025 before the ledger and TECH_STACK.
The lead is the only writer of the Blender source and exports. QA may read
delivered artifacts and write its own renders, captures and reports, but does
not change the production scene, generated assets or runtime source. Runtime
and Blender jobs share a coordinated exclusive GPU lane for trustworthy timing.

Existing hard requirements include the shared four-raycast RigidBody3D,
original fictional identity, three LODs, source portability, unchanged starter
and validation speed policies, reproducible shipping bytes, and the accepted
performance gates. A successful import, semantic-node inventory, screenshot,
scripted pose or agent judgment does not independently prove actual driving,
motion clearance, representative visual quality, or human approval.

The lead locked `specification.json` on 2026-09-10 and adopted these modeling
and presentation tolerances, with a tighter 0.5 mm wheelbase/track/radius limit.
The specification is authoritative for exact values. These are fictional model
acceptance thresholds, not manufacturer claims, ratified performance allocations
or permission to change the physics:

| Measurement | Proposed check | Classification |
| --- | --- | --- |
| Overall length/body width/height | Blockout within 10 mm; final within 5 mm of the fictional locked specification | Modeling error; source uncertainty is a separate field |
| Wheelbase/tracks/radius | Within 0.5 mm of the locked specification | Model/runtime contract error, separate from reference uncertainty |
| Wheel, contact, suspension, camera and hinge anchor position | Within 2 mm of the locked coordinate contract after Blender-to-Godot conversion; hinge axis within 0.1 degree | Contract implementation tolerance |
| Evaluated mesh validity | No nonfinite coordinates, faces at or below the locked degeneracy-area tolerance, unintended flipped normals, or undeclared open boundaries | Measured technical failure; intended thin sheets identified explicitly |
| Unintended assembly penetration | Fail any signed penetration greater than 1 mm; inspect every smaller visible intersection as a visual defect | Locked numerical tolerance, not permission for visible clipping |
| Tire-to-liner/body envelope | At least 5 mm outside intentional contact, throughout the locked steering/bump/droop envelope | Fictional packaging target; record smallest measured separation and pose |
| Other moving solid assemblies | At least 1 mm outside declared mating/contact surfaces throughout travel | Door seals, wiper rubber and panel stops require explicit contact exceptions |
| Panel gaps | Locked 3.5 mm nominal, 2.5-4.5 mm for exterior closures unless the lead declares an interface-specific exception | Fictional design choice; no assertion that all real panels share one gap |
| Wiper contact/parking | Blade contact offset 0-2 mm for at least 90% of blade span; repeat park angle within 1 degree; record swept mask over the declared driver critical view | Locked visual mechanism thresholds; no claim of simulated rain removal |
| Mirrors | Moving target reflected with correct view/handedness and age no greater than 100 ms at the declared 15 Hz proposal | Locked freshness proxy; implementation cost remains provisional and human review remains open |
| Control presentation | Readback agrees with driving/inspection input and the exported joint contract by the next two rendered frames | Locked presentation latency; raw input conditioning has its existing contract |
| LOD transition | Missing lamps, wheels, windows or unstable materials fail; greater than 2-pixel silhouette jump at the declared transition distance is a review trigger | Diagnostic threshold at 2560x1440, not a substitute for motion review |

Resolve any conflict with the locked lead contract before asserting pass. Record
unresolved values as pending; never silently pick a looser tolerance after a
failure. Dimension confidence intervals describe reference uncertainty and must
not absorb errors between the locked fictional specification and the model.

Content ceiling proposals reuse Q-044: 150,000 active LOD0 triangles, 200,000
total authored triangles, 32 materials, 48 textures, 96,000,000 texture bytes,
and 128 collision triangles. They remain provisional production allocations.
Count active non-LOD-prefixed wheels, cabin, lights and mechanisms in visible
geometry; also report total unique geometry, instantiated/drawn triangles,
surfaces/draw calls, mipmapped GPU texture residency and packed source bytes
separately. A compressed source-file byte count does not measure VRAM. Mirror
resolution, update policy and cost require a separate measured proposal; ADR
subsystem reserves are not approved mirror or vehicle millisecond allocations.

## Evidence contract and capture hooks

Every capture set needs a machine-readable manifest with task, milestone, UTC
start/end, exact Git revision and tree/dirty state, platform/GPU/driver, exact
Blender/Godot/.NET versions, command/exit status, seed and arguments, input
SHA-256 values and output SHA-256 values. Inputs include source blend, generated
GLB/scene, import profile, wrapper, setup, specification and acceptance files.
Record failures, retries and the relationship between original and corrected
captures. Preserve failure outputs; later passes must not overwrite them.

For every still or movie, include actual render size, renderer/preset, active
LOD, lighting ID and world settings, exposure/color transform, camera anchor,
transform, projection/lens/FOV and time. Preserve full frames before making
labeled crops or contact sheets. Generated images, rendered UI mockups and
photographic reference pictures are not Blender or Godot QA evidence.

Runtime needs these hooks under existing debug-only official-engine automation:

1. Explicit `--vehicle=endurance-sedan|hero-gt|graybox`, profile and capture
   output selection. Logs identify the resolved wrapper/setup and loaded asset
   hash, not just the requested argument. Save/resume records selected setup.
2. Distinct **driving** and **posed inspection** modes. Driving uses the actual
   unfrozen rigid body. Every direct placement, artificial impulse, forced
   origin shift or pose override is identified as a fixture operation.
3. Monotonic stage IDs, expected/completed stage inventory, frame/tick/time and
   explicit success/failure completion artifacts. A frame cutoff or zero exit
   without all required observations fails capture completeness. Flush evidence
   outside temporary runtime homes; retain shutdown/fatal/leak diagnostics.
4. Per-frame or per-physics-tick JSONL of input source, raw and conditioned
   controls, signed speed/travel, body pose/velocity/angular velocity, wheel
   angles and roll increments, ray contact/body/point, suspension compression,
   active camera, actual LOD, authoritative route position and local origin.
   Do not substitute repeated labels or requested values for actual readbacks.
5. Named fixed inspection cameras plus operator-accessible controls for each
   opening, wipers, lights, hazards and selector. Record target and actual
   joint angles, lamp emission/illumination state, instrument values and units.
   Include camera eye-envelope bounds and all driving camera ranges.
6. Mirror viewport resolution, update policy, actual update frame/time/count,
   camera transform and hidden layers. A numbered moving target fixture must
   be visible behind the car and outside the main camera, with frame/time ID
   and expected mirror projection. Disable recursive mirror sampling.
7. A distance-driven LOD scenario through each declared threshold in both
   directions; separately expose a manual LOD switch for diagnostic comparison.
   Measure actual active geometry after cockpit/opening overrides.
8. Production Forward+ at an explicitly requested 2560x1440 High capture size;
   an independent native presentation-timing profile using the same vehicle,
   mirrors and lights. Fixed-fps movie rendering is not frame-time evidence.

Raw keyboard/controller action events through the existing InputMap are one
evidence class. Injected conditioned controls are a reproducible physics fixture
and must be labeled as such. Both are useful; the latter does not prove physical
controller accessibility or human driving enjoyment.

## Adversarial feature matrix

The row IDs below should be referenced by the lead's acceptance matrix and the
QA review index. A pass requires the observable evidence as well as any numeric
check; absence of a capture means pending, not implied success.

| ID / stage | Required actual evidence | Failure condition |
| --- | --- | --- |
| Q01 / specification | Referenced dimension sheet with exact year/market/trim/configuration, width definitions, units, confidence, stock/modified/fictional labels and model/runtime mapping; comparison with chosen engineering benchmark | Missing key packaging value, inconsistent PS/hp/kW or width definition, unresolved conflicting dimensions, or reference estimate presented as a factory fact |
| Q02 / originality | Lead-authored design rationale and front/rear/profile/cabin comparison with engineering references; provenance inventory for every external input | Unacknowledged borrowed logo/model identity, untracked texture/reference ancestry, or fictional styling represented as a licensed replica; human rights/art gate remains separate |
| B01 / blockout geometry | Fresh blend and exported blockout; orthographic front/rear/left/right/top/underside with scale rulers, wheel/contact/COM/collision/camera/occupant overlays | Scale/axes/origin mismatch, missing fourth door or usable cabin envelope, wrong wheelbase/tracks/radius, mismatch between visible tire and contact markers |
| B02 / blockout driving | Continuous official-engine footage and synchronized telemetry of acceleration, throttle release, braking, reverse, left/right turn and settling after a bump, with rigid body unfrozen | Body transform or wheel telemetry posed to satisfy stage; expected motion/sign absent, sustained unintended slip/contact loss, fall-through, unstable settling or contact supported by wrong geometry |
| B03 / blockout lifecycle | Actual collision, recovery/reset, chase/cockpit/rear-view changes, local-origin shift and save/resume; route/system state comparisons | Collision misses; reset/resume does not restore bounded supported state; origin shift changes authoritative route or causes visible jump; wrong setup after resume; captured camera clips |
| B04 / preserved variants | Equivalent explicit sedan/Hero GT/graybox shared-adapter checks and existing vehicle dynamics/camera/input/save regressions | Hero or graybox cannot load/drive, sedan radius or dimensions leak into another variant, undocumented speed-policy change, missing fallback |
| V01 / proportions | Neutral clay orthographic and matched perspective views before microdetail; same views after each proportion correction | Sedan silhouette/occupant packaging inconsistent with lock, asymmetry not designed, wheels poorly fitted to arches, hidden bad proportions concealed by extreme lens or darkness |
| V02 / surface quality | Full exterior turntable and slow moving grazing reflections; evaluated geometry/normals inspection after modifiers | Pinching, faceting, discontinuous curvature, wavy reflections, shading seams, nonmanifold defects or unintended intersections at gameplay and inspection distances |
| V03 / body construction | Four distinct doors, hood, trunk, roof/pillars/fenders/bumpers/rockers; measured gaps, thickness, jamb/seal/hinge views with openings closed/partial/full | Missing assembly, razor-thin visible edge, inconsistent gap, floating fastener/handle, absent recess, opening reveals void, or unmodeled closure interior |
| V04 / wheels and brakes | Each tire/wheel in side, oblique and inner-barrel views; tread/sidewall/rim/hub/fasteners/disc/caliper details; full steering and bump/droop sequence | Wrong OD/width/offset/rotor size, tire/body contact, detached tire, rotating caliper, static rotor with rolling wheel, reversed roll sign, implausible brake/barrel fit |
| V05 / glazing and seals | Exterior and interior matched views through every window, glass edges and mirror mounts, daylight/overcast/night | Opaque or invisible intended glass, inverted/twice-dark glass, incorrect sorting, missing thickness/seal, exterior reflections obscuring all cabin sightlines, holes exposed by reverse viewpoints |
| V06 / lamps/grille/exhaust | Close-ups of lens/housing/projector/reflector/light guide, genuine grille/opening depth and exhaust termination; five-lighting comparison | Painted-on flat opening, floating lamp component, light leaks through housings, visible backside void, exhaust/grille not connected to plausible depth |
| V07 / black materials | Locked neutral studio clay and material views; paint grazing highlight close-ups; adjacent paint/trim/rubber/leather/fabric/metal/glass swatches in scene | Black crush hides construction under neutral exposure, pure mirror/chrome response on intended paint, flat plastic response, oversized noise, smeared UVs, inconsistent physical texture scale or wrong color space |
| V08 / front cabin | Seated driver eye view, center console, instruments, vents, column/wheel/pedals, door cards/switches, seats/headrests/belts, carpet/headliner and storage | Missing required assembly, clipped controls or sightline, unsupported seat/column, floating belt, inaccessible control, text unreadable at intended view; human comprehension remains open |
| V09 / rear cabin | Both rear-door entry views and rear-seat eye view, seats/headrests/belts, floor, roof/pillars and parcel shelf | Front-only cabin, empty rear shell, insufficient locked occupant envelope, opening exposes missing trim/structure, rear-facing camera or mirror sees cut-away roof |
| V10 / visible systems | Hood/trunk/underside views and inspection motion showing cooling/intake/exhaust, engine/transmission housing, suspension/undertrays, fuel/luggage/endurance equipment packaging | Modeled mechanism has nowhere to fit, fuel/equipment intersects occupants or openings, major visible systems absent, implausible disconnected packaging, or modeled engine bay described as simulated mechanics |
| F01 / input and motion | Keyboard and controller-contract drive segments; wheel steering/rolling/suspension, chassis response, steering wheel and pedals visible with matching runtime readbacks | Input conflict/focus theft, stale/fabricated rig state, wheel rotation inconsistent with signed motion and declared radius, steering/pedal direction wrong, suspension moves past declared stops |
| F02 / lights | Night wall/road illumination plus exterior/cockpit footage: head/tail on/off, brake with lamps off/on, reverse stationary/moving, left/right signals, hazards and cancellation | Emissive-only headlight proof, brake state confused with tail state, wrong side flashes, missing center brake, reverse disagrees with actual selected reverse state, stuck emission after toggle/camera/LOD/reset |
| F03 / instruments | Continuous dashboard close-up during accelerate/shift/brake/reverse, changed saved fuel, low-fuel/damage and implemented warning states; raw state/value/unit overlay in fixture | Static labels, speed/gear/RPM/fuel disagree with explicit source/rounding, display obstructed, values jump on camera switch, fabricated temperature/pressure simulation; estimated gear/RPM must be documented |
| F04 / wipers | At least three uninterrupted sweep/park cycles from driver/exterior/oblique camera, slow diagnostic cycle and swept-area/contact overlay | Incorrect pivot or handedness, blade passes through glass/trim, lifts off claimed contact span, blades collide, misses declared driver critical region, does not repeat park, freezes/jumps after camera/rebase/LOD |
| F05 / mirrors | Each mirror shows the moving numbered off-main-screen target; cabin pan, turn/reverse/rebase, day/night, on/off/update telemetry and cost comparisons | Static/frozen view, wrong side/orientation, target absent despite expected visibility, self-recursion, hidden cabin omitted incorrectly, excessive declared latency or resolution that prevents intended review |
| F06 / openings | Separate and simultaneous continuous four-door/hood/trunk open-close cycles, 0/25/50/75/100% stills and hinge/jamb/strut views; repeated close from partial travel | Wrong pivot, panel/body/inter-panel collision, interior void, detached glass/trim, wrong travel or stop, closure cannot return to recorded pose, UI inaccessible from keyboard/controller |
| F07 / state lifecycle | Lights, wipers, openings, instruments and mirrors across camera change/reset/rebase/selector/save/resume, with documented persistence policy | Presentation stale or leaks between vehicles; existing authoritative save changed unintentionally; fixture changes cannot be distinguished from player operation |
| O01 / LODs | Fixed-camera LOD0/1/2 comparisons at intended sizes and continuous distance crossings in both directions during driving | Functional lights/moving wheels disappear, body/color/glass changes materially, silhouette pops beyond review trigger, wrong cockpit/opening override or uncontrolled threshold chatter |
| O02 / collision and damage | Collision proxies overlaid on closed body; real barrier/ground contacts; damage-zone readback and visible mappings on each LOD | Detailed visual collision replaces declared proxy, excess collision budget, proxy permits obvious ground/wall penetration, wrong or missing semantic damage zones; opening colliders are only claimed if implemented |
| O03 / portable artifacts | Lead's saved blend reopened, dependencies inventory, evaluated mesh/UV checks, two locked exports and every shipping-byte comparison; fresh official Godot import instantiates final project wrapper | Absolute/local-only texture dependency, missing packed assets, stale generated scene, duplicate semantics, material/resource import error, wrapper not exercised, nondeterministic shipping bytes |
| O04 / cost and performance | Active/total content inventory and actual native 1440p Forward+ captures with mirrors/lights/cockpit, standalone timing and 30-minute growth data | Provisional content ceiling exceeded without governance resolution; declared reference gate violated; movie-render throughput or headless FPS substituted for actual presentation cost |
| D01 / delivery | Final source/tooling/runtime/setup/LODs/collision/docs/media/evidence inventory plus exact open/select/inspect/drive instructions replayed by QA | Missing file, stale hashes/revision, undocumented limitation/control, failed required platform check, required human gate marked complete by an agent |

## Capture sets and sequence

**Blockout hold point:** review B01-B04 with a fresh imported blockout before
detailed surface production. Numeric fixture success and actual rendered
driving inspection are both required. Retain baseline Hero and graybox evidence
so setup generalization cannot erase a compatibility failure.

**Geometry and material set:** preserve front, rear, both sides, top, underside,
front and rear three-quarter views. Include orthographic clay and neutral
material versions with consistent fit; reference-matched views record lens
uncertainty rather than distorting the model to fit an unknown photograph.
Add fixed-camera close-ups of paint reflections, gaps, lamps, wheel/brakes,
glass/seals, controls, upholstery and every opening mechanism. Inspect full
frames at 2560x1440, the intended chase/cockpit distance and close views; small
contact-sheet thumbnails alone cannot prove finish. Smaller output/accessible
UI layouts require their own readability observations if declared supported.

**Lighting set:** neutral studio, daylight, overcast, dusk and night use the
same recorded camera transforms and explicit fixed exposures. Include front
three-quarter, rear three-quarter, side, cockpit and material close-up in each
condition. Do not fix a night-material failure by silently changing exposure.
Keep clay and a reflection-strip rig available to isolate geometry from finish.

**Motion set:** a complete neutral exterior turntable should be slow enough to
inspect, proposed at least 12 seconds for 360 degrees at 60 encoded fps. No
lighting change halfway through may substitute for complete surface coverage.
Provide a continuous interior inspection including both rows, plus mechanism
movies F04/F06 and a separate real-driving movie. Record complete braking,
reverse, left/right turns, suspension extremes, collision, reset, camera change,
rebase and LOD transitions. Stage durations follow observed settling/travel,
not a universal one-second cutoff. Preserve uncropped footage and source frames.

For each movie, verify dimensions, fps/timebase, actual frame count, duration,
decode/seek integrity and completion marker alignment. Independently inspect
the complete sequence for unintended holds, skipped states, shimmer, flashes,
clipping and LOD pops. A valid container/CRC does not establish motion quality.
The review index records the actual watched frame/time ranges and frame IDs of
findings. Extracted sheets support that review; they do not replace it.

**Clearance sweep:** use evaluated geometry after modifiers, correct hierarchy
and final imported pivots. Sweep steering across the locked range and all four
wheels through independent bump/droop extrema; include combined lock/bump and
diagonal articulation. Sample sufficiently finely (proposal <=1 degree joint
increments and <=5 mm suspension increments), report minimum signed distances
and witness points, and inspect continuous motion for missed intermediate
collisions. For each opening/wiper, include endpoints, intermediate fractions,
return motion and relevant simultaneous neighbor movements. State whether the
method is sampled or a conservative continuous envelope; sampling alone is not
a mathematical all-time collision proof. Intentional seal/tire/road contacts
must be named exceptions rather than globally suppressed intersections.

## Actual-driving and lifecycle assertions

Use the current core/dynamics profile thresholds for acceleration, braking,
turning, recovery and deterministic equivalence. Do not force real-car target
times into the unchanged gameplay policy. Distinguish the 125 mph starter and
250 mph HighSpeedValidation profile; benchmark references remain documentary.

Current reset regression checks include horizontal error <=0.1 m, at least
three supported wheels, speed <=0.1 m/s and angular speed <=0.1 rad/s after the
allowed settling interval. Its existing 0.5-1.5 m body-origin height band is a
coarse recovery check, not proof of sedan tire ride height; also measure contact
locations and the sedan's locked suspension/static-origin geometry. Preserve
existing bounds unless an explicit accepted change is required.

Save/resume compares the existing authoritative route/run/system contract and
its bounded local reconstruction, including selected physical setup. Capture
the save artifact hash and before/after state. Demonstrate at least one actual
local-origin rebase in driving; a forced diagnostic rebase may exercise the
path early but must be labeled separately. Report maximum local coordinate,
route equivalence and visible body/camera/mirror continuity across the event.

Keyboard and controller fixtures must exercise pressed/released controls,
steering both directions, trigger/brake/reverse behavior, camera switching,
inspection focus and return to driving. Simulated InputMap events prove the
software mapping path, not physical device calibration. Human physical wheel
feel, 30-minute enjoyment, and accessibility usability remain open reviews.

## Performance and platform verification

Use the reference-performance front door on the declared Ryzen 9 5900X,
RTX 3080 Ti 12 GB, 64 GB Windows reference PC with the native production
renderer at 2560x1440 High. Record actual hardware/driver/preset rather than
assuming it from the machine name. Honor idle-machine admission; no Blender,
movie encoding or competing GPU client during acceptance captures. Dirty-tree,
contended, diagnostic and lower-resolution captures may help debugging but
must be identified and do not replace exact-revision reference evidence.

For uncapped warmed steady driving, ADR-0023 requires p95 <=16.67 ms, p99
<=20 ms, and zero stalls above the current **20 ms** limit. GPU memory must not
exceed 9.5 GB and process working set must not exceed 16 GB. Sustained growth
fails only when the 30-minute fitted slope exceeds 1 MiB/min **and** R-squared
is at least 0.5. Report the actual series, slope, fit and high-water values.
For capped presentation use accepted cap-adherence metrics (mean within
0.1 FPS and p50 within 0.1 ms of the period), with the later 20 ms stall
addendum. Older 50 ms prose is tracked in the defect ledger and must not lower
the new run's acceptance standard.

Measure matched mirror-off/on configurations, individual mirror and all-three
cost where useful, cockpit/exterior, day/night lamps, moving openings and LOD
transitions. Record viewport sizes/refreshes, drawn primitives/surfaces/calls,
memory/residency, presentation percentiles and relevant measured counters.
Whole-scene delta with repeated controlled runs supports cost estimation;
it does not automatically ratify a per-subsystem reserve. Include the highest
observed-cost representative configuration in the required 30-minute run.

Root coordinates the complete required M0 front door, sedan asset verifier,
runtime/variant regression and all ledger-declared platform checks. Linux or
software-rendered CI behavior is distinct from native Windows visual/performance
acceptance. Reopen/import/export proof must use the delivered artifacts at the
reported revision, not a convenient earlier build or editor cache.

## Defects, retests, and human handoff

Each defect has an observed artifact/source location, severity, expected versus
actual behavior, affected acceptance IDs, reproducible conditions, assigned
owner, correction/revision and confirming evidence. Technical failures and
visual defects share the ledger but remain distinguishable from missing QA
coverage and unresolved human decisions. A documentation mismatch is an
observed defect; missing not-yet-produced images are a pending review, not an
invented model flaw.

Severity: **critical** blocks safe/reliable execution or destroys state;
**major** breaks a promised feature, accepted budget, compatibility or plainly
visible construction; **minor** is a localized visual/documentation defect
without loss of the core feature. Human taste questions can remain review
notes without alleging an objective defect. A source-only proposed correction
does not close a runtime or visual defect.

After a correction, rerun affected technical checks and capture the same
camera/light/frame or input sequence with the new revision. Inspect both
full-context and close-up evidence. Preserve the failing original and record
any unavoidable configuration difference. Broaden regression when a shared
adapter, shader, export contract or lifecycle changed.

Human art direction, final source/asset rights, 30-minute driving enjoyment,
physical wheel calibration/feel and player comprehension/accessibility require
actual human approval references. Agent QA supplies findings and a concrete
review package; it does not approve these gates. Public release and signing
remain their own boundaries. P1-018 cannot be marked complete while any of its
required human gates or machine evidence is outstanding, regardless of merge
eligibility under ADR-0025.

## Preparation source audit

The preparation audit and source hashes are retained under
`reports/p1-018/qa/preparation-audit.json`. These are read-only source findings,
not runtime or rendered observations:

- `VehicleVisualScenario` freezes the car, directly poses physics presentation,
  and uses ten 60-frame stages. Its one-second orbit splits day/night halfway;
  its cockpit pan covers only part of the cabin. Preserve it as a Hero fixture,
  and use new full-motion and actual-driving evidence for P1-018.
- `capture-scenario.sh` defaults to Compatibility and fixed-fps movie output
  with a frame cutoff. Explicit Forward+, actual size, sufficient stage time
  and completion validation are required; this path cannot prove presentation
  performance.
- `verify-vehicle-asset.sh` accepts only Hero GT. Existing Blender inventory
  uses hardcoded bounds and `LOD0_` name-prefix accounting; existing importer
  instantiates the generated scene and checks wrapper source, rather than
  exercising wrapper behavior. Generalized checks must measure the sedan's
  evaluated bounds and active assemblies, reject duplicate semantics, and
  instantiate the actual final wrapper.
- The native reference-performance script already provides useful timing,
  idle-machine and reproducibility infrastructure, but requires explicit sedan
  and mirror configuration plumbing to price this delivered vehicle.
- At the preparation snapshot, TECH_STACK and the current Q-022 question row
  described older thresholds. The lead corrected both; the later specification
  review retains fresh source hashes and the D001 documentation retest. The
  original preparation audit remains historical evidence.

## Reproducible source QA tooling scope (2026-09-11)

The lead assigned independent QA ownership of `tools/vehicles/endurance_sedan/qa/`
after source23 exposed all-angle clearance shortfalls missed by dense samples.
This directory will consolidate the exercised read-only source inventory,
actual saved-driver contract, moving-assembly interval bounds, fixed interfaces,
tire/wiper envelopes and source-control checks. It accepts a supplied locked
`.blend`, opens it with the pinned official Blender, and writes a fresh evidence
directory with commands, exit statuses, tool/source/script hashes, witnesses and
bounded results. It must not save the input or create shipping exports.

Preserve the 1 mm unrelated rigid-part clearance, 5 mm tire clearance and the
declared wiper/glass range. Named bearing, sealed joint and closed-stop rules
must be individually encoded and measured; material names or broad assembly
prefixes cannot exempt intersections. Independent opening combinations require
interval bounds, not matching-angle samples. Negative controls must demonstrate
rejection of bad topology, invalid drivers, missed-stage evidence and an
intermediate-angle collision or clearance shortfall. An unresolved bound fails
the relevant gate. Existing failed checkpoint evidence remains immutable.

This tooling supplies repeatable machine evidence. Actual final Blender renders,
actual native Godot captures, performance measurements, platform checks and the
required human approvals remain separate acceptance requirements.

The implemented entry point is
[`tools/vehicles/endurance_sedan/qa/run.py`](../../../tools/vehicles/endurance_sedan/qa/run.py),
with the exact command, fourteen ordered stages and scope in its
[`README.md`](../../../tools/vehicles/endurance_sedan/qa/README.md).
It snapshots executable QA inputs into a fresh output directory and fails first;
partial-stage success cannot become overall acceptance. It includes109 source
control states, a separate12-state head/tail/brake/reverse and four-beam check,
all-angle opening/tire/wiper certificates with initial containment, and17 native
rejection/positive controls. Revision14 adds complete finite roof/crossover and
sixteen pad-face certificates, plus three actual copied-geometry intrusions.
Source warning thresholds follow the recorded float32 preview boundary; explicit
source lamp controls are previews, not a mechanical or powertrain simulation.

Failed full-source32 attempt01 remains retained: exact zero pad-plane mismatch
was incorrectly rejected because numerical polygon subtraction left areas of
6.06e-18 and2.67e-18 m². The correction bounds every entire residual polygon
against one original triangle using the convex-distance property and a1e-12 m
arithmetic bound. It does not raise an area tolerance or change the model.
The fresh `reports/p1-018/qa/full-source-32-02/evidence.json` run passed all
fourteen stages against the locked source32 and retained its own executable,
source and script hashes. Independent source/unbatched/batched correspondence
is recorded in `reports/p1-018/qa/batch-correspondence-32/review.json`.

The later source32 still review closes only D013's specific optical/body
discontinuity. The tire shoulder representation, roof/header finish and
windshield reflections have bounded correction proposals; their authoritative
reconstruction and full source/native retest remain required. Historical
blockout movie review records62 actually viewed decoded frames and their PTS,
separately from the complete1852-frame decode and later technical-ruler repair.
These reviews do not replace final motion, performance, platform or human gates.

The locked source33/specification15 passes the unchanged fourteen-stage entry
point at `reports/p1-018/qa/full-source-33-01/evidence.json`. Actual source/GLB
correspondence is `qa/batch-correspondence-33/review.json`; its normal/UV results
are bounded encoding precision, not exact attribute identity. Independent
review of106 additional actual Blender images, the50-station header rebind and
matched cockpit material/pixel comparison is `qa/source33-reviewed/review.json`.
Only the specific D020 raised/floating sipe defect closes here; final films,
native presentation, performance/platform and human gates remain separate.

The historical blockout resume supplement reviews33 consecutive decoded frames
(32new beyond the previous62) and confirms D056 atPTS60.100000 seconds with both
full-resolution adjacent frames. `qa/historical-resume-reviewed-01/review.json`
explicitly preserves this failed visual transition; later runtime repair cannot
retroactively make the historical movie continuous. The one23-byte Blender
shutdown allocation in source33 worklight captures remains recorded separately
from their valid completed PNGs and from Godot runtime memory evidence.
