# P1-018 runtime integration plan

Status: lead-approved implementation contract, 2026-09-10. Source values are
locked in `specification.json`; machine and human acceptance remain unverified
until their evidence exists. No agent approval substitutes for a human gate.
Authority: ADR-0012 shared adapter, ADR-0023 measured performance, ADR-0025 integration;
the P1-018 ledger remains the scope and acceptance authority.

## Existing behavior and ownership

`CannonballVehicle` is the authoritative four-raycast `RigidBody3D`. It already
supports conditioned keyboard/controller input, braking/reversing, collision,
reset, chase/cockpit cameras, local-origin conversion and the existing run save.
The `VehicleSetup` speed policy is separate: Starter remains 125 mph and
HighSpeedValidation remains 250 mph. No new engine or transmission simulation
is proposed. Existing force/assist laws are retained; this is a new physical
geometry/setup and a state-driven presentation layer.

At the claim, hardcodes included the Hero GT wrapper and texture sidecar/shader paths;
1450 kg mass; 2.84 m wheelbase, 1.64 m tracks, 0.34 m tire radius; 0.54 m spring
free length; a 1.86 x 0.64 x 4.45 m collision box; fixed spawn/reset heights;
37 base semantic nodes; Hero-specific cockpit exclusions and automation IDs.
The previous adapter had wheel rotation and spring translation, three manually
selected LODs, head/tail illumination and damage-zone highlighting. It has no
six-opening, wiper, mirror, brake/reverse/indicator, pedal or dashboard system.
The existing visual scenario freezes physics and poses the rig. It remains a
Hero regression test and is not evidence of actual sedan driving.

Runtime agent owns `game/Vehicle/` scripts and new setup/wrapper resources,
excluding Hero geometry/assets; narrow selection/lifecycle/state plumbing in
`game/Main.cs`; `game/Automation/EnduranceSedanScenario.cs`;
`game/Automation/EnduranceSedanPresentationScenario.cs`;
`scripts/verify-endurance-sedan.sh`; `tools/vehicles/validate_import.gd`;
narrow approved `game/Input/GameInputMap.cs` shortcuts; this document; and agreed tests. Lead owns
all Blender/source/export/generated geometry, the shared budget contract and
`verify-vehicle-asset.sh`. Input-map or core/save schema changes need explicit
lead coordination. QA owns independent captures and the defect ledger.

## Shared setup resource and locked coordinate contract

Add a project-owned `VehicleRigSetup : Resource` and two `.tres` instances for
Hero GT and endurance sedan. The resource declares asset ID, wrapper and texture
sidecar paths, car-paint shader path, physical dimensions, mass/COM, four wheel
hardpoints, tire radius, spring travel/static compression/rate/damping,
steering lock, chassis collision boxes, visual mount and cockpit exclusions.
Use the existing Hero values as defaults without changing its generated asset.
The separate Core `VehicleSetup` class continues to own gameplay speed limits.

The sedan values below are locked fictional hardpoints; they are not Audi
factory specifications. The canonical specification owns their provenance.

| Item | Contract |
| --- | --- |
| Blender frame | meters; X right, Y forward, Z up; design ground Z=0 |
| Godot frame | X right, Y up, front -Z; `(x,y,z)` maps to `(x,z,-y)` |
| Asset origin | ground plane at the midpoint between axles |
| Rigid-body origin | ground-frame Y=0.650 m; visual local offset `(0,-0.650,0)` |
| Front wheel centers | Godot `(+-0.810,0.3433,-1.460)` m |
| Rear wheel centers | Godot `(+-0.805,0.3433,+1.460)` m |
| Contact markers | corresponding X/Z, ground-frame Y=0 |
| Suspension authoring | pivots at static wheel centers; not full droop |
| Travel | 0.075 m droop / 0.085 m bump; free spring length 0.160 m |
| Ray spring anchor | wheel X/Z, ground-frame Y=0.4283 m, body-local Y=-0.2217 m |
| Static spring compression | 0.075 m; presentation offset = compression - 0.075 |
| Prepared running mass | fixed nominal 2400 kg; not a variable mass/fuel simulation |
| Static spring rates | front 84729.3696 N/m; rear 72177.0304 N/m; each supports its 54:46 corner load at 0.075 m compression |
| COM | ground-frame Godot `(0,0.55,-0.1168)` m; fictional 54:46 axle distribution |
| Front steering envelope | 32 degrees; existing conditioned input remains authoritative |
| Body collider | body ground center `(0,.47,.07)`, size `(1.82,.62,4.72)`; cabin center `(0,1.035,.57)`, size `(1.42,.60,1.50)` |

For the sedan, `Suspension_FL/FR` carries steering and vertical movement;
`Wheel_*` is its child at local zero and carries rolling rotation around X.
Brake rotor/hat belong to the rolling child; calipers belong to suspension.
Steering sign and rolling sign must be verified against actual travel rather
than inferred from display labels. Hero retains its old hierarchy and visual
translation convention through a setup compatibility flag. No collider is
generated from opening panels and opening them does not change vehicle mass.

Retain every existing base semantic node. The following sedan-only nodes are
approved additions; their transforms/pivot axes are exported and validated.

| Nodes | Role and authored local axis |
| --- | --- |
| `Door_FL`, `Door_FR`, `Door_RL`, `Door_RR` | hinge pivot; local Z in Blender / Y in Godot; lead records signed angle |
| `Hood_Hinge`, `Trunk_Hinge` | pivot local X; lead records signed angle |
| `SteeringWheel_Pivot` | steering-column-aligned pivot; local Y Blender / -Z Godot |
| `Pedal_Accelerator`, `Pedal_Brake` | pivot local X; recorded travel angle |
| `Wiper_L`, `Wiper_R` | windshield-normal pivot; local Z exported with explicit axis metadata |
| `Mirror_Left`, `Mirror_Right`, `Mirror_Rear` | visible mirror surfaces; normal/UV declared by lead |
| `MirrorCamera_Left`, `MirrorCamera_Right`, `MirrorCamera_Rear` | actual mirror camera anchors |
| `Instrument_Cluster` | dashboard display anchor facing the seated driver |
| `Light_Brake_L`, `Light_Brake_R`, `Light_Brake_Center` | separate brake emissive groups/anchors |
| `Light_Reverse_L`, `Light_Reverse_R` | reverse emissive groups/anchors |
| `Light_Indicator_FL`, `Light_Indicator_FR`, `Light_Indicator_RL`, `Light_Indicator_RR` | independently controllable amber groups/anchors |

Sedan semantic pivots live outside the `Visual_LOD*` empties. Every distributed
render mesh has an `LOD0_`, `LOD1_` or `LOD2_` prefix; the adapter caches these
groups once. LOD0 contains articulated detail; LOD1 retains visible wheel/panel/light motion
where discernible; LOD2 can use a declared closed-body silhouette. The runtime
keeps LOD0 while an opening is active or cockpit inspection is in use, and
switches by distance only after measured thresholds/silhouette QA. Semantic
pivots stay present at all LODs. LOD1 wheel meshes remain under rolling pivots
and LOD1 doors under their hinges. Initial distance thresholds are 28 m/65 m,
pending silhouette/motion QA.

## Presentation state and accessible interaction scope

Add a sedan presentation component under the shared adapter. It consumes the
actual conditioned input, signed longitudinal speed, steering angle, wheel
compression, active camera and the saved `VehicleCondition`. Steering wheel
and pedals use this same state. Speed is measured body speed; gear and RPM are
explicit kinematic presentation estimates using declared ratios/idle/redline,
not authoritative torque/transmission mechanics. Fuel displays the existing
saved liters (82 L initial gameplay state) against the declared 175 L modeled
capacity. Low-fuel/damage/brake/indicator warnings derive from explicit state;
unimplemented temperatures or mechanical faults are not fabricated.

Head/tail/low-beam state, brake and reverse state, left/right turn state and
hazards have independent emissive groups. A small bounded number of real
lights gives headlights/reverse/brake spill where useful. Wipers have parked
and periodic sweep states with authored pivots and sweep endpoints. Six
openings interpolate between verified closed/open rotations, exposing their
actual interiors. Manual inspection while nearly stationary uses a focused
Control panel with labeled buttons/sliders and standard UI keyboard/controller
actions; shortcut registration and focus suppression must not steal driving or
trip-map actions. Every control has readable state and a semantic automation ID.

Mirrors use shared-world SubViewports and rear-facing cameras, with bounded
resolution and refresh rate. Implemented starting sizes: 256x128 each side,
384x128 rear, 15 Hz, cockpit-only updates, no recursive mirror rendering.
This is provisional until actual mirror target visibility/freshness and
frame-time/GPU/VRAM cost are measured. Each viewport exposes resolution,
request frame/count and independently completed FramePostDraw frame/count.
The three updates are staggered across each 1/15-second period. Dummy/headless
rendering cannot increment the completed-image counters. Native capture checks
colored moving target pixels outside the main camera, not just camera frusta.
No static image passes mirror QA. The native real-time benchmark remains the
freshness/frame-budget gate; Movie Maker and pixel-readback runs are inspection
evidence and cannot supply that performance gate.

Selection is explicit `--vehicle=endurance-sedan|hero-gt|graybox` and a visible
parked-vehicle selector. The lead-approved implementation persists the selected
asset ID in `user://vehicle-presentation.cfg` and reinstantiates before loading an existing run;
the versioned authoritative save remains unchanged. Resume uses the same
selected physical setup and verifies route/system state and bounded local
reconstruction. Switching the setup in a running drive performs an explicit
parked reset, so geometry changes cannot silently reuse incompatible wheel
contacts. The command-line selection overrides this preference for its launch
without changing the saved preference. F2 or controller RB opens inspection;
headlights H, wipers T, comma/period indicators and slash hazards also have
focused, labeled controls. Inspection stops driving input and retains the prior
body/autopilot state, then clears latched input through the normal conditioner
when closing.

## Verification and measurable evidence

Before detailed surface work, a new official-engine scenario must prove the
actual unfrozen sedan on collision geometry: acceleration, braking, reverse,
left/right steering, suspension/contact response, collision, reset, camera
switches, rebase and save/resume. It records fixed timestep, seed/setup, actual
input and body state, contact counts, wheel/panel angles, camera, route/origin,
save equivalence, stage markers and failures in JSONL/structured summary. A
separate posed inspection mode proves assembly ranges and fixed-camera renders;
it never substitutes for input-driven driving evidence.

Run the same shared-setup checks for Hero GT and graybox fallback, then retain
their existing dynamics/camera/input/save regressions. The new strict verifier
rejects missing stage markers, fatal/engine errors and leaked resources even
when process exit is zero. Both M0 platforms must exercise the sedan scenario.
Windows actual rendered captures cover the lead/QA acceptance matrix at
2560x1440 High plus inspection views. QA independently inspects actual images
and gameplay footage; mirror proof includes a moving target outside the main
camera view. Root coordinates exclusive GPU/runtime lanes.

Source uncertainty remains in the research sheet, while model/runtime mismatch
is a measured defect. Opening, full steering and bump/droop swept envelopes
must be measured against authored geometry. Asset caps come from the shared
budget contract. ADR-0023 frame/memory gates are not replaced by nominal mirror
budgets or subsystem reserves. Human visual, usability, handling and rights
approval remains outstanding until an actual human reference is recorded.

The lead-approved D026 repair also owns the narrow look-axis correction in
`game/Camera/CockpitCameraRig.cs`. Right/down input angles retain their existing
positive telemetry convention, while their composed camera rotations account
for Godot's -Z view direction. The shared driving suite uses actual InputMap
right/down and left/up actions with stabilization temporarily zero, then checks
the camera forward vector against chassis right/up for all three variants.
This verifies visible direction independently of angle labels.

## Current evidence and correction history

The frozen blockout passed all 16 actual-engine driving stages for each of the
sedan, Hero GT and graybox. The retained initial results are under
`reports/p1-018/runtime/blockout/{endurance-sedan,hero-gt,graybox}`. The corrected
counter run at `reports/p1-018/runtime/blockout/counter-correction-03` also passed
all 48 stage executions with strict exit/error/resource-leak checks. Its
save/resume telemetry identifies vehicle epoch 1 and retains both the previous
and reconstructed counters; stage reset/rebase deltas are nonnegative. These
are early blockout checks with `--sedan-blockout`, which explicitly omits the
unfinished production presentation. They are not feature or visual completion.

`reports/p1-018/runtime/blockout/capture-01` retains 16 actual Forward+ PNGs and
a 61.07-second OGV with per-stage camera/state/hash metadata. This first capture
is not an acceptance pass: the launcher lost its child exit code, expected the
wrong shutdown marker, encoded 1280x720 video, and its window was clamped to
2526x1421. QA also found terrain obscuring six pad-fixture stages. The visible
streamed terrain now follows its enabled physics scope: both are disabled for
the isolated pad and restored for route traversal. A corrected native capture
must rerun the motion coverage. None of these corrections erase old artifacts.

Import validation now instantiates the real project wrapper, checks required
semantic-name uniqueness, measures source-to-Godot hardpoints and tire/body
dimensions, checks mechanism rest bases and axes, and walks portable resource
dependencies recursively. Positive sedan/default-Hero results are in the
counter-correction directory. Three isolated expected-failure controls under
`reports/p1-018/runtime/import-negative-controls` reject duplicate semantics,
direct build dependencies and transitive build dependencies with exit 1.
Authored triangle counts are separate from hidden runtime damage markers.

The separate presentation suite has 52 posed stages, plus three native mirror
stages when `--sedan-captures` is supplied. It verifies actual opening bases,
material emission, instrument labels, and a small-angle geometric steering-rim
direction check. The corrected rim sign moves its top right when the front tire
points right. This suite is compiled but still awaits the production artifact;
no production interaction or final performance acceptance is claimed here.

Final sedan driving adds a seventeenth stage with an unfrozen car passing a
fixed observer through the 28 m and 65 m LOD boundaries. Posed inspection also
includes fixed rear-cabin and footwell views. Imported convex-proxy dimensions
are compared to the setup; the driving fixture checks the actual rigid-body
shape count, `BoxShape3D` types and dimensions. An external inspection/observer
camera is no longer mistaken for an active cockpit camera just because the
chase camera is inactive; mirror activation follows the actual cockpit view.

Specification revision 2 attaches side mirror surfaces and camera anchors to
the front doors. Imported parenting is checked, and the native door-follow
stage requires actual camera transforms and completed viewport updates while
both doors open. The input-driven suite also checks presentation state across
reset, cameras and rebases. Save/resume reconstructs lights in automatic mode,
wipers/signals/hazards off and openings closed; only the selected asset ID is
persisted in the separate presentation settings. Authoritative fuel/run state
continues through the existing save contract.

The sedan asset front door now dispatches to
`tools/vehicles/verify_endurance_sedan.mjs`. It retains two independent source
exports and clean project imports, compares GLB/normalized scene/texture
sidecar/PNG and imported GPU texture bytes, validates the instantiated wrapper,
and exercises malformed source/dependency controls and release-pack policy.
`--candidate --output PATH` leaves reviewable outputs in isolation and explicitly
defers comparison to canonical delivered files. The default mode requires that
comparison. No contact-sheet reproducibility or rights approval is inferred.
The final production run remains pending the lead's locked source/export.

The lead approved automation save isolation on 2026-09-11 before implementation.
`--run-save-path=PATH` is accepted only with the existing sedan driving or posed
presentation profiles; ordinary play keeps its current save location. The sedan
front door and native capture runner supply a fresh evidence-local path, and
Main logs the resolved path before constructing the unchanged save repository.
This prevents a save/resume fixture from overwriting the player's normal save.
The private synthetic presenter diagnostic also uses its own application name.
No save schema, migration, economy state or normal selection persistence changes.

The assets workflow adds explicit Linux and Windows sedan jobs using the pinned
official tools. They remain post-merge tripwires under ADR-0025, with M0 as the
only merge gates. Two complete normalized-only PCK files are compared here;
native executables and external managed assemblies are additionally covered by
the required `scripts/release/build-unsigned.sh` platform gate. Each normalization
must create its scene and sidecar from absence, and a manifest rejects stale
source, specification, profile, wrapper, validator and dependency hashes.

The isolated synthetic presenter diagnostic passed all 47 posed headless stages
at `reports/p1-018/runtime/synthetic-presenter-05/evidence.json`. It adds explicit
box primitives only for the missing blockout cluster and pedal pads and uses a
private project/save directory. Earlier attempts retain the blink-transition
sampling defect, a 240-second instrumentation watchdog, and the mirror verifier
disposing a shared texture alias. The corrections use a two-frame control
latency, cached semantic-node references with current transform readbacks, one
snapshot per frame, and borrowed-resource reads that do not dispose the owner's
objects. This result is logic corroboration, not production geometry, clearance,
native mirror imagery, visible rendering or gameplay performance acceptance.

The current save-isolated blockout driving regression passed all 48 stages at
`reports/p1-018/runtime/save-isolation-01` for sedan, Hero GT and graybox. Each
variant retains and hashes its own `run-save.json` and checks the resolved path.
It continues to omit the production presenter explicitly with `--sedan-blockout`.

Independent QA found retained Blender runs with Python driver errors despite
exit status zero. The asset verifier therefore rejects positive Blender runs
that report driver/Python failures or missing image dependencies, in addition to
its existing fatal and leak policy. A bounded factory-empty invalid-driver probe
must return zero and still be rejected by the same policy; the corrected driver
must pass. The diagnostic-only CLI retains these commands and hashes without
claiming asset acceptance. Named exporter rejection cases remain intentional
negative controls. This scope is confined to the owned verifier and isolated
report files and does not modify the authoritative scene.

The lead approved two existing reference-performance paths on 2026-09-11:
`scripts/capture-reference-performance.sh` and
`game/Automation/ReferencePerformanceScenario.cs`. The front door will expose
explicit vehicle selection with the current Hero default and graybox alias,
record the loaded setup and asset hashes, and permit a benchmark-only mirrors
on/off comparison. Mirror completion ages, update counts and viewport CPU/GPU
costs will use the existing allocation-conscious native measurement harness.
The approved automation-only save override also covers this reference profile;
its front door supplies a fresh scenario-local file and verifies the saved bytes.
Its monotonic frame clock, warmup, 20 ms stall limit, percentile and memory
criteria and 30-minute growth gate remain unchanged. Movie Maker and posed
pixel-readback diagnostics continue to be separate from this performance gate.
The earlier native capture demonstrated Windows client-size clamping. An
optional benchmark `--fullscreen` flag preserves the default windowed mode,
while the front door requires measured window/3D dimensions to equal the
requested resolution. Final 2560x1440 sedan measurements use this option.
For the approved comparison matrix, production mirrors-on runs measure 1800
seconds at uncapped and 60 FPS. Mirrors-off baselines measure 180 seconds at
the same caps and claim no 30-minute memory result. Fixed-allocation histograms
and frozen mirror counters retain the first 180 seconds of each production run
so cost comparisons use equal windows, separate from full-run acceptance.

To launch manual driving from Git Bash after the production artifacts are
delivered, prepare the existing route fixture and pass the vehicle explicitly:

```bash
./scripts/run-scenario.sh --fixture official-corridor --smoke-test
package="$(node -p 'require("./.tools/scenarios/official-corridor/current-package.json").root_relative_path')"
./scripts/godot.sh --path "$PWD" -- \
  "--route-package=$PWD/.tools/scenarios/official-corridor/$package" \
  --vehicle=endurance-sedan
```

The second invocation is manual driving. W/RT accelerates; S/LT brakes; A/D or
the left stick steers. Q reverses; holding LT at a stop enters reverse under the
existing controller policy. Space/X is the handbrake, R/Y recovers at the current
route point, V/right-stick click switches chase/cockpit, and I/J/K/L or the right
stick looks around. F5 saves and suspends. Add `--resume` to the same manual
launch invocation to restore the saved authoritative run through its unchanged
save contract, keeping the explicit `--vehicle=endurance-sedan` selection.

Stop below 0.5 m/s and press F2/controller RB to open the labeled inspection
panel. Use arrows/D-pad and Enter/Space/A, or the mouse, to operate four doors,
hood, trunk, lights, wipers and cameras. F2/RB/Esc/B closes the panel and clears
held driving input. H cycles auto/on/off headlamps, T toggles wipers, comma and
period toggle the left/right signals, and slash toggles hazards. The parked
selector offers Meridian S8R, Hero GT and graybox; applying a choice reconstructs
at the same route position and saves only the selected presentation ID.

Open `data/assets/vehicles/sources/endurance-sedan.blend` in the pinned Blender
for editable construction and `game/Vehicle/Visuals/EnduranceSedan.tscn` in the
Godot editor for the project-owned runtime wrapper. Source controls and model
inspection instructions are documented by the lead's final model delivery.
These launch instructions are implementation documentation; the final production
runtime and human usability evidence remain separate acceptance rows.

On 2026-09-11, isolated production18 native diagnostics exposed a rotated cluster
UV mapping and a side-mirror moving-target failure. The presentation harness
therefore records actual imported display UV axes, posed ray collider heights,
visual wheel centers, and mirror image/projection samples. Failure summaries and
sample files survive incomplete runs. The lead approved the automation-only
`--sedan-presentation-probe=mirrors` option for four native diagnostic stages;
it has an explicit diagnostic scope and cannot satisfy the unchanged full
then-current 47-stage headless or 50-stage native acceptance inventory. Surface construction
and any physical mirror anchor correction remain with the lead model writer.
Within that native mirror probe only, `--sedan-mirror-camera-source-y=METERS`
may temporarily pose the two side-camera anchors for the lead's packaging
decision. It records the value, preserves door parenting, restores the local
anchor transforms on disposal, and never edits source or exported asset bytes.

The lead approved the reusable native capture front door at
`scripts/capture-endurance-sedan.sh` and
`tools/vehicles/capture_endurance_sedan.py`. It builds and imports with the pinned
official engine, records complete input identities, preserves any existing
`override.cfg`, and owns only a temporary absent-before override for measured
2560x1440 capture. Exact completed stages, clean shutdown, actual PNG dimensions,
FFprobe decoded frame counts and a full movie decode are required. A mirror-only
lighting option adds a separate night diagnostic to the full suite's daylight
proof; neither four-stage diagnostic substitutes for the full production suite.

Independent QA observed a corrugated roof in the forced-rebase capture. The
driving harness now retains render-boundary LOD, camera and displayed-body
positions beside each PNG, separate from physics-frame observations. Diagnosis
first preserves the existing behavior in an isolated historical source 18
project. Any correction must preserve natural rebases, actual distance-based
LOD transitions, and the shared Hero/graybox camera and reset contracts.
The actual native baseline rendered LOD2 at a 9.49 m chase distance because
the earlier presenter callback had used an old camera 1809.67 m away. The
presenter now runs after the camera and selects against the interpolated body
position. A reconstructed body may display its explicit initial LOD0 for its
first process-traversal frame; that state is recorded as uninitialized and must
initialize by the next frame. Every later rendered selection must use the same
frame and camera/body distance observed at the render boundary.

The native front door uses these commands after the existing representative
fixture has been prepared and `GODOT_BIN` points to the pinned .NET executable:

```bash
./scripts/run-scenario.sh --fixture representative-corridor --smoke-test
package="$(node -p 'require("./.tools/scenarios/representative-corridor/current-package.json").root_relative_path')"
route="$PWD/.tools/scenarios/representative-corridor/$package"
./scripts/capture-endurance-sedan.sh --mode driving \
  --route-package "$route" --output reports/p1-018/runtime/native-driving-final
./scripts/capture-endurance-sedan.sh --mode presentation \
  --route-package "$route" --output reports/p1-018/runtime/native-presentation-final
./scripts/capture-endurance-sedan.sh --mode presentation --probe mirrors --lighting night \
  --route-package "$route" --output reports/p1-018/runtime/native-mirrors-night-final
```

Each output directory must be new. For a retained candidate, add
`--project-root reports/p1-018/runtime/production21-native-prepared-05/project`
and `--upstream-evidence reports/p1-018/runtime/production21-native-prepared-05/evidence.json`.
Candidate commands explicitly retain that diagnostic scope and upstream status.
Full-suite and mirror-only target-hidden checks use the same lighting as their
subsequent moving-target stage. Night evidence is a separate four-stage result,
not a replacement for full daylight presentation coverage.

On 2026-09-11 the lead added a separate native 180-second uncapped night,
cockpit, mirrors-on reference-performance diagnostic. It uses the existing
lighting option and keeps both 1800-second daylight runs and matched
180-second mirrors-off baselines. The benchmark now samples actual head/tail
material emission and headlamp beam visibility/energy at the existing
0.5-second memory-sampling interval, with bounded value-type storage and
reported readback overhead. It records initial/final lamp state and rejects
lamp-content mismatches independently of frame-time thresholds. No lamp cost
is inferred solely from a night preset label or from Movie Maker timing.

The final native capture gate also records the viewport's actual MSAA property,
the applied High tier and directional-atlas metadata, and actual environment
preset beside every PNG. Godot exposes no getter for the global directional
atlas/filter configuration, so those values are explicitly applied-call
metadata, not asserted independent server readbacks. The HUD's BALANCED text
describes the driving assist profile and is unrelated to render quality.
The lead requested a separate fixed-camera tire-contact diagnostic using exact
visible mesh vertices and interpolated mesh/floor matrices at both render
boundaries; this remains private evidence, not a lighting change or substitute
for final driving captures.

Independent native QA found the low-fuel warning's lower half hidden behind
the steering rim. The lead approved moving the existing amber 20 px warning
label from viewport rectangle (16,148,480,32) to (16,0,480,28), keeping all
readout positions and vehicle hardpoints unchanged. The native presentation
check projects strong amber glyph pixels from the actual 512x192 instrument
viewport through the imported display UV plane into the actual cockpit PNG.
It requires at least 90% overall matching coverage and 85% in both vertical
halves, allowing a one-pixel search for rasterization differences. The old
layout remains an isolated negative control. This detects the observed
occlusion; independent image review still owns visual readability judgment.

The lead approved five additional named instrument stages before implementation:
DAMAGE, COOLING, TIRES, PANEL OPEN and PARK BRAKE. They exercise existing
condition, opening and input states, adding no mechanical or thermal simulation.
The current full inventory is 52 headless and 55 native presentation stages;
historical 47/50-stage evidence remains unchanged. All six warning states must
match both runtime state and display text, and each native warning capture must
pass the actual glyph-visibility check. Missing logical state and hidden glyphs
are separate bounded negative controls. Sedan/Hero/graybox driving remains
17/16/16 stages.

The all-warning native capture exposed unshadowed omnidirectional brake spill
lighting the cockpit through opaque rear structure. The lead approved a narrow
presentation correction: keep all emitter materials and activation state, omit
the center brake lamp's artificial spill, and use 4 m rear-facing spot spill for
the outer brake/reverse lamps. The spots point 8 degrees downward with a
55-degree cone, retaining energy 0.35/0.65 and adding no shadow maps. Anchors,
source geometry and shared SkyLighting stay fixed. A native Day/Night paired
control retains the old omnidirectional configuration and measures both rear
road illumination and cockpit isolation at fixed cameras.
The existing full presentation stages also retain each actual light's type,
energy, shadow flag, range, cone and basis, and require the four rear spot
directions plus absence of a center spill. This makes the native transport
correction a load-bearing regression without changing the 52/55 inventory.

The final-source runtime capture sequence is retained at
`reports/p1-018/runtime/final-source-capture-plan.md`, with the current 101
headless stage executions and 17/55/4 native driving/presentation/night-mirror
inventories. It requires a lead-frozen source/export/runtime input set, fresh
evidence directories, actual media hashes and decoded dimensions, and separate
native frame-performance evidence from fresh worktrees. Earlier bounded
diagnostics remain historical evidence and do not replace this final sequence.

The final platform audit identified the new parked `Control` surface as subject
to ADR-0008's existing PlayGodot requirement on Linux, Windows and macOS. The
lead approved `automation/playgodot/tests/test_endurance_sedan.py`, narrow
explicit-vehicle and isolated-user-data options in
`automation/playgodot/src/cannonball_playgodot/launcher.py`, and corresponding
launcher-option tests in `automation/playgodot/tests/test_launcher.py` before
implementation. No fixture registry or conftest change is needed. Existing
vehicle panel metadata gains its actual visible window/status, opening angles,
equipment state and selected visual ID so the test can compare visible labels,
focus, input effects and actual body state. The semantic UI test uses the
existing bounded official-engine bridge and cannot replace native art/feel QA.
Selection persistence is exercised only when the actual Godot user-data path
is inside the disposable test directory; real player settings stay untouched.

The first rendered test found that uppercase/underscore opening automation IDs
violated the existing bridge grammar; only those debug identifiers became
lowercase/hyphen IDs. A second actual test found that the later-created HUD
consumed Escape before inspection's unhandled-input handler, opening the driver
menu behind the frozen panel. Inspection now handles close shortcuts in the
shortcut phase after GUI popups and before HUD unhandled input. The test checks
that both panels are closed and the previous body state is restored. Normal
pause behavior outside inspection remains covered by the existing UI suite.
The selector uses PopupMenu's supported arrow navigation, measured focused-item
readback and the existing <=0.5 m/s parked guard after vehicle reconstruction;
unsupported Home navigation was a test assumption, not a selection defect.

The same audit adds the already-required Hero GT `--all-lods` regression to
both existing sedan asset workflow platforms and retains its reports. Explicit
selected-sedan execution of each delivered Linux/Windows package supplements
the existing ten default package smokes. The lead retains canonical package
construction and integration ownership.

The lead approved `tools/vehicles/verify_packaged_sedan.py` and
`scripts/verify-packaged-sedan.sh` before implementation. They execute the
selected sedan's existing 17 driving and 52 headless presentation stages through
the delivered platform launcher, using a disposable user-data directory and
evidence-local save paths. Package inventory bytes are hashed before and after
the run; output paths must remain outside that immutable package. The verifier
rejects missing stage/summary/shutdown records, timeout, fatal/warning/leak
diagnostics and any package mutation, even when a launcher returns zero.
The existing presentation summary assumed repository C# and GLB files always
exist on disk. Packaged runs instead report which source files are physically
available, while the external verifier binds the actual PCK, assemblies and
package manifest. Missing repository source files are never represented by
invented hashes or treated as packaged source-retention evidence.

The package verifier also binds the observed native executable to the manifest's
declared binary: the official Windows `.console.exe` launcher has the exact
adjacent `.exe` child; Linux runs its declared binary directly. Presentation
summaries now include loaded vehicle identity, physics rate and the exact number
of written frame samples. User-data logs are retained before temporary-directory
cleanup even when launch or the bounded timeout cleanup raises an exception.

The lead approved a driving-only `--blockout` option on the capture frontend for
a later revalidation of the still-frozen canonical blockout. It passes the
existing `--sedan-blockout` scenario flag, requires exactly the existing sixteen
functional stages, and labels the omitted production presentation explicitly.
The earlier failed/null-exit capture and the successful early headless evidence
stay unchanged. This new decoded 1440p movie documents the corrected capture
fixture and runtime against the historical blockout; it does not backdate a
production presentation or final asset acceptance claim.

The 2026-09-11 historical blockout revalidation is retained at
`reports/p1-018/runtime/blockout/native-revalidation-05/process.json`. The prior
04 attempt remains failed because the capture frontend incorrectly required
production LOD-selection metadata from an intentionally omitted presenter.
The corrected blockout-only check requires fixed LOD0 and absent presentation
selection metadata; production captures retain the full distance/frame check.
The fresh 05 run completed all sixteen stages, native exit/shutdown and full
1440p movie decode against unchanged historical source/export bytes. This is
later evidence, separate from the original early headless blockout proof.

Contact rendering remains a private diagnostic, with no shipping change to
SkyLighting, tires or physics. The first 0.275×0.22 m ORM-only decal comparison
(`production23-contact-decal-01`) had negligible visible effect and was not
recommended by independent QA. Albedo-only strengths 0.25/0.45/0.65 at that
same footprint (`production23-contact-shading-01`) produced measured monotonic
pixel darkening but still little visible grounding. Most of the soft mask lay
behind the tire. These are not visual passes. The lead authorized a separate
0.34×0.24 m plateau/feather comparison with strengths 0.45/0.65; its result must
be judged from actual native images before any runtime adoption proposal.
The albedo-only approach is explicitly contact shading, not physical ambient
occlusion, and does not write the road's roughness/metallic channels.

After the plateau images, independent QA observed a small contact edge at 0.45
without a conspicuous painted patch in the reviewed sedan views. The separated
directional shadow remained visible, so D050 stays open. On 2026-09-11 the lead
authorized one private 0.45 motion experiment and matched 180-second native
off/on cost runs. These use reports-owned C# and runner inputs in an isolated
copy of the existing source-23 diagnostic project. The motion case retains the
existing seventeen-stage actual driving scenario and its complete movie gate;
additional readbacks cover actual ray contacts, rendered decal/tire alignment,
interpolation, airborne disabling, reset, save reconstruction and rebase.
The cost cases use the same visible private floor, vehicle and native High
settings with 20 seconds of warmup. They report frame/CPU/GPU percentiles and
the component's measured cost without claiming ADR-0023 production approval.
No arbitrary road receiver policy, source geometry, stance, shared lighting or
shipping contact-shading implementation is authorized by these experiments.
Any later adoption is sedan-only unless separately justified and scoped.
The lead also approved a diagnostic-only receiver whitelist for the motion
suite's streamed-road stages: the contacted chunk's `RoadSurface`,
`PavedShoulders` and `TerrainShoulders`, plus the private pad/bump. The probe
adds one otherwise-unused render-layer bit and records each receiver path;
materials and collision remain unchanged. This permits actual visible rebase
coverage without asserting a general shipping receiver policy.

The first private motion trace exposed a verification gap: natural and forced
rebases could occur two physics ticks apart, leaving no intervening 30 Hz movie
frame. The lead authorized a shared scenario correction before final captures:
retain at least three observed process/render frames after each distinct rebase,
capture the natural event after it actually happens, and require increasing
counter/frame identities in the frontend. Explicit fixture `Place` teleports
also reset interpolation after the next physics updates and before drawing;
their events remain labeled fixture operations. The observed 41 mm transient
was confined to those fixture placements. The first trace did not establish a
playable reset/rebase interpolation defect, so gameplay physics is unchanged.

The fourth private motion capture now retains separate actual natural/forced
rebase frames, but a newly regained ray contact can place the decal one physics
tick ahead of the interpolated tire. On 2026-09-11 the lead authorized a private
render-stage correction: retain the authoritative ray point, surface normal and
receiver eligibility, then project the actual interpolated wheel center onto
that contact plane immediately before drawing. Only the cosmetic transform is
derived; contact loss still disables it. Raw, derived and displayed points,
normal/tangential alignment and the separate rebase observations are retained.
This remains a reports-only candidate requiring actual movie review and matched
off/on cost measurements before any shipping proposal.

The first projection attempt (private motion 05) exposed the exact engine
update boundary: Godot 4.7.1 completes its second scene-tree interpolation
traversal before `FramePreDraw`, so assigning a visual transform in that signal
leaves the cached displayed transform at its earlier position. The correction
assigns the same cosmetic projection in late `_Process` and uses `FramePreDraw`
only to verify actual wheel/decal transforms after the native traversal. Both
attempts and the official source references are retained; no engine changes or
global interpolation changes are involved.

QA's native negative fixture also emitted an exit-zero Blender
`ERROR Division by Zero in Driver` diagnostic without `PyDriver`. The asset
verifier now includes a bounded same-line ERROR/Driver rule and exercises both
native error forms against a corrected constant-expression fixture. Retained
log replay establishes the previous classifier miss; this does not allege a
driver failure in production source 31.

The lead also approved a narrow verifier-copy exclusion for
`data/assets/vehicles/endurance-sedan-review/`: its historical review media is
already outside Godot import and release data, and copying it into two clean
runtime stages consumes several gigabytes without exercising the asset. Only
that exact directory is excluded; adjacent authoritative source/derived assets,
documents, contracts and QA tools remain copied and hash-locked. A bounded
filesystem fixture exercises the real stage-copy function and confirms both
the exclusion and preservation of adjacent inputs.

Independent source review on 2026-09-11 found that parked vehicle selection
carried elapsed run time into a new clock interval while retaining map pauses
already deducted from that elapsed value. The lead approved a narrow Main.cs
clock-epoch correction and a real map-pause, selection, elapsed/save regression
in the existing PlayGodot sedan case. Old source and failing evidence are
retained before the correction; Core save/schema contracts are unchanged.

The same review found that the legacy Hero visual scenario and PlayGodot's
production-vehicle mode could inherit the player's selected sedan or graybox.
The lead approved explicit Hero identity in scripts/run-scenario.sh and the
existing PlayGodot launcher, with command-boundary tests and actual-engine
regression under conflicting persisted selection. Ordinary gameplay still
uses its saved selection, and the new three-vehicle scenarios remain explicit.
The legacy `--graybox-vehicle` flag also selects the original graybox setup,
instead of merely hiding whichever saved vehicle's art happened to load.
Contradictory explicit IDs are rejected. Both the run and movie launchers pin
the Hero visual scenario; PlayGodot pins its intended Hero or graybox variant.
The inherited Hero wheel yaw/roll signs will first be checked through actual
transformed tire-plane and contact-point witnesses, preserving Hero source and
export bytes. Any proven correction stays in the shared adapter/setup and its
verification scenario; it does not alter the four-raycast force model.

The official-engine witnesses confirmed both inherited Hero presentation signs:
at 0.2 rad steering its actual tire plane opposed the force heading by 22.9183
degrees, and forward travel moved the bottom tread forward rather than backward
relative to the wheel center. The shared legacy presentation now preserves the
imported rest basis and uses the same physical steering direction; the default
rolling sign is negative. Sedan articulation already used those directions.
The Hero visual scenario checks actual transformed tire/rim vertices, and two
isolated mutations independently restore each old sign to prove rejection.
`vehicle-wheel-geometry-native-02/evidence.json` retains all five passing
positive/negative-control cases under `reports/p1-018/runtime/`. The unchanged
three-vehicle blockout driving suite also passes all 48 stages after these
corrections. These checks do not change Hero geometry or driving-force policy.

The clock correction passes the retained old-source negative control and fresh
native InputMap/save test in `vehicle-clock-native-02/evidence.json`. The actual
Compatibility UI case in `production23-control-ui-clock-07/evidence.json` also
passes keyboard map pause, real popup navigation through all three selections
and F5 saves. Its final summary retains all three saved clock comparisons;
the intermediate observation file deliberately preserves progress on failure.
The earlier private probe's missed F5 pulse remains a failed fixture attempt,
separate from the corrected real-input checks. Final production/platform gates
still need the locked delivered vehicle.

Private contact motion 08 passes its 17-stage capture, shutdown and measured
rendered contact alignment, but adoption remains open. Its matched 180-second
cost pair measured 0 frames over 20 ms with shading off and 17 with shading on
(maximum 98.023 ms), so the on case fails the unchanged zero-stall comparison.
The existing histograms have no individual stall timestamps and cannot identify
their cause. The lead authorized causal investigation before a retry. A fresh
reports-only v3 probe preserves the contact algorithm and adds bounded,
preallocated stall records: actual pre-draw intervals, latest available render
CPU/GPU timings, previous periodic-sampler duration, managed collection and
allocation deltas, available pipeline-compilation counters, object/resource
counts, contact projection/audit costs, and sampled process CPU/working set.
No files are written during measurement. These observations can identify a
reproducible cause but cannot turn correlation or a clean exit into acceptance.
The next matched pair must wait for explicit idle-host coordination after
construction, rendering and evidence compression; all earlier failures remain.

The lead extended the same exact review-media exclusion to the existing Hero
asset verifier's tar staging function. Its archive still includes adjacent
source/derived assets, wrappers, documentation and verification tools. A tiny
actual tar-copy control compares the old and corrected function and requires
the review directory to be omitted while adjacent prefix names and nested
unrelated paths remain present. Hero source, GLB and normalized artifact bytes
are unchanged; this is an input-copy boundary correction only.

Actual UI and consecutive movie review exposed two further lifecycle defects.
Each parked selection requested ordinary road recovery, whose live steering
target advances 20 m before the next physics tick; the selector therefore moved
the run forward despite its current-position label. The correction preserves
the saved horizontal position/orientation, adjusts only vertical chassis-origin
height for the selected setup, and reconstructs at zero linear/angular speed.
Fresh bodies already have fresh contacts; selection does not need the ordinary
recovery reset. That reset and the four-raycast force law remain unchanged.

The save/resume movie also exposed its first reconstructed chase frame at
1.9849434 m from the car, followed by 9.229064 m on the next frame. Godot's native
SpringArm starts its child at zero and performs collision-aware placement on
the physics traversal. The lead approved handling these pending selection and
sedan verification reconstructions in SceneTree.PhysicsFrame before traversal,
so normal SpringArm collision runs before the first draw. The old world stays
visible until that boundary; pause/shutdown guards and one owned event hook
prevent late work. No synthetic physics notification or camera collision bypass
is used. The final driving scenario must retain and validate the first three
consecutive reconstructed camera frames, not merely the later stage PNG.
An isolated wall-compressed arm case supplements the actual open-road movie.

The lead admitted the unchanged motion-08 contact geometry as a candidate for
extended final verification after diagnostic cost 09 did not reproduce the
earlier 17 stalls. Both pairs remain retained; there is no causal explanation
or final performance pass. `game/Vehicle/VehicleContactShading.cs` contains the
sedan-only cosmetic extraction, enabled by its setup resource with Hero and
graybox defaults disabled. It retains the 0.34 x 0.24 m footprint, 24 mm depth,
0.78 mask plateau, 0.45 black albedo strength, 2 mm plane offset and 30–40 m fade.
The four decals use actual ray contacts and interpolated wheel projection;
they alter neither geometry, physics, receiver material nor ORM channels.
Only actual contacted RoadChunk RoadSurface/PavedShoulders/TerrainShoulders and
the declared integration pad/bump receive the reserved render-layer bit.
Receiver caches are pruned as chunks leave, and live owned bits are restored
when the component exits. A generated 64-square mask has no external texture
input. Unsupported renderers omit the effect explicitly. Routine frame updates
retain measured component counters; detailed actual decal/wheel/plane readback
is collected only by verification. Final native source-33 motion and the full
reference-performance matrix must validate this shipping extraction before
visual/performance acceptance. No final contact-shading approval is inferred
from the diagnostic's small static improvement or its clean retry.

Final runtime budget verification inventories actual visible mesh triangles and
distinct active material/texture RIDs after presentation overrides, rather than
assuming the Blender material count also describes instantiated gameplay.
The owned adapter exposes this read-only inventory for functional/capture and
reference evidence; it runs outside measured frame work. Renderer-owned decal
box draws and atlas/buffer costs are reported separately, including the fact
that the ordinary viewport draw-call monitor omits cluster-box submissions.

The native source23 inventory measured37/34/34 active materials across the
three LODs, above the unchanged32 ceiling. Lamp overrides will share only when
their original material RID and independent control channel agree (headlight,
tail, brake, reverse, left indicator or right indicator). Screens retain their
separate viewport textures, and original material responses stay intact.

An actual RoadChunk collision off/on probe also reproduced replacement-contact
failure before the periodic cache prune: the old body was freed while its
visual receivers retained the owned bit. New receiver acquisition therefore
prunes expired owners immediately and preflights all receiver bits before any
mutation; foreign live ownership remains an error. The original failure,
corrected replacement and preservation of unrelated layer bits are retained.

The source33 full presentation rerun exposed a stale harness selector at its
first opening: the UI's accepted semantic IDs use lowercase hyphenated names,
while the posed suite still requested the original Blender node spelling.
The suite now applies the same explicit ID conversion as the verified UI test;
the UI and model contracts remain unchanged. The failed run is retained.
