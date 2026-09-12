# Meridian S8R

An original four-door endurance sedan built for Cannonball-Vibe. Its engineering
benchmark is the documented 2016 US Audi S6 configuration in [research.md](research.md);
the identity, exterior, cabin and preparation layout are fictional. The existing
Hero GT remains available.

The authoritative completion record is [P1-018](../../DELIVERY_LEDGER.json).
Machine verification and the required human art, rights, handling and usability
reviews are separate. This vehicle is a review candidate until those gates close.

## Open and inspect the model

From the repository root in PowerShell:

```powershell
$sedanBlender = 'C:\Program Files\Blender\blender-5.1.2-windows-x64\blender.exe'
& $sedanBlender 'data/assets/vehicles/sources/endurance-sedan.blend'
```

`Asset` contains the model, editable LOD0 assemblies, semantic pivots and derived
LOD1/LOD2 meshes. `Preview` contains the original studio, camera and source-only
illumination. Units are meters; +Y points forward and +Z points up. The origin is
on the ground midway between the axles. Godot converts source `(x,y,z)` to `(x,z,-y)`.

Select `RigControls` in the Outliner and edit **Object Properties → Custom
Properties**. Set `Door_FL_open`, `Door_FR_open`, `Door_RL_open`, `Door_RR_open`,
`Hood_Hinge_open` or `Trunk_Hinge_open` between 0 and 1. `steering` spans -1 to 1;
`wheel_roll` is radians and `suspension` spans -0.075 to +0.085 meters. The
`accelerator`, `brake`, lamp and signal properties preview their named functions.
Use `wiper_sweep` for a fixed pose or `wipers_running=1` and play the timeline.
`source_sim_*` properties preview dashboard values. These are editable inspection
controls; Godot supplies actual runtime state through the imported pivots.

Edit the individual LOD0 meshes and modifier stacks. Derived LODs and export
batches can be regenerated. Return all ordinary preview controls to zero before
export; the exporter rejects an unparked source. No script-handler installation,
linked library or external texture folder is needed to inspect the saved source.

The readable [dimension sheet](dimension-sheet.md), locked
[specification](specification.json), [design rationale](original-design-rationale.md)
and [acceptance matrix](acceptance.json) distinguish factory values, source
uncertainty, original choices and modeling tolerances.

## Select and drive

Use Git Bash with the pinned prerequisites described in the main repository
README. Build the official fixture, then launch manual driving:

```bash
./scripts/run-scenario.sh --fixture official-corridor --smoke-test
package="$(node -p 'require("./.tools/scenarios/official-corridor/current-package.json").root_relative_path')"
./scripts/godot.sh --path "$PWD" -- \
  "--route-package=$PWD/.tools/scenarios/official-corridor/$package" \
  --vehicle=endurance-sedan
```

| Action | Keyboard | Controller |
| --- | --- | --- |
| Accelerate / brake | W / S | RT / LT |
| Steer | A / D | Left stick |
| Reverse | Q | Hold LT at a stop |
| Handbrake / recover | Space / R | X / Y |
| Chase / cockpit | V | Right-stick click |
| Look / rear view | I J K L / hold B | Right stick / hold LB |
| Save checkpoint | F5 | No existing binding |
| Parked inspection | F2 | RB |

Stop below 0.5 m/s to inspect. The labeled panel operates all four doors, hood,
trunk, lights, wipers and cameras. Navigate with arrows/D-pad and Enter/Space/A
or the mouse. F2/RB/Esc/B returns to driving. Its selector changes between
Meridian S8R, Hero GT and graybox at the current route position. The selected
presentation is saved separately from authoritative run state. F5 saves a
checkpoint while driving continues. Wait for `CANNONBALL_SAVE_OK` in the
console before closing. Add `--resume` to the same manual launch command to
load the saved checkpoint.

H cycles auto/on/off headlights; T toggles wipers; comma/period toggle left/right
indicators and slash toggles hazards. Brake and reverse lamps follow driving
state. Cockpit instruments show speed in mph, gear, RPM, fuel in liters and
relevant indications. Mirrors render live rearward views while the cockpit is
active; their implementation and measured costs belong to the runtime evidence.

Open `game/Vehicle/Visuals/EnduranceSedan.tscn` in Godot to inspect the owned
wrapper. The existing custom four-raycast rigid-body simulation remains
authoritative. Starter and HighSpeedValidation policies are unchanged. Modeled
engine, transmission, cooling, fuel-cell and underbody assemblies are inspection
geometry; they do not implement thermodynamics, mechanical engine internals or
auxiliary fuel-transfer simulation. No physical-wheel calibration is implied.

## Reproduce and verify

The constructor starts with an empty Blender scene and reads the locked
specification plus the recorded early integration proof. Use a fresh output
path to preserve edited sources:

```powershell
& $sedanBlender --background --factory-startup --python-exit-code 1 `
  --python tools/vehicles/create_endurance_sedan.py -- `
  --output reports/p1-018/reconstruction.blend --stage production
```

Run the repository front doors from Git Bash with `BLENDER_BIN` set to the
pinned executable and `GODOT_BIN` set to official Godot 4.7.1 .NET:

```bash
./scripts/check.sh
./scripts/verify-vehicle-asset.sh --vehicle endurance-sedan --all-lods
./scripts/verify-vehicle-asset.sh --vehicle hero-gt --all-lods
./scripts/verify-endurance-sedan.sh --output-root reports/p1-018/fresh-runtime-check
```

Use a fresh evidence directory for each attempt. Preserve failures. The sedan
asset gate reopens the source, exports twice, imports twice into clean staging
projects and compares shipping bytes, including normalized resources and release
packs. It also exercises deliberately invalid source and wrapper controls.
The [ordered-corner encoding bake](export-corner-bake.md) checks raw exported
triangle winding, position, normal and both UV channels against the reviewed
source-bound encoding. Scene, material and embedded-image payloads must match
exactly. Both the raw pre-corner export and the subsequent pre-UV export are
retained. The [evaluated UV bake](export-uv-bake.md) remains a separate check.
A source edit requires explicit new corner and UV bakes and a new review;
neither lock is refreshed implicitly by normal export or verification.
See [qa-plan.md](qa-plan.md) and [defects.json](defects.json) for independent review
requirements and observed defects. A successful command is not human approval.

The independent source gate reopens the delivered Blender file and checks its
evaluated geometry, control/light drivers, complete opening domains, tires,
wipers, named construction interfaces and deliberate rejection controls:

```powershell
python tools/vehicles/endurance_sedan/qa/run.py `
  --source data/assets/vehicles/sources/endurance-sedan.blend `
  --blender $sedanBlender --output reports/p1-018/fresh-source-qa
```

It copies its exact QA tools into the new evidence directory and records all
nineteen required stages, including exact authored-mesh and final lower-LOD
self checks, plus complete formed-header, latch and upholstery interfaces.
Partial output or a successful native process alone
does not satisfy that gate. [Retained construction evidence](../../../data/assets/vehicles/endurance-sedan-review/evidence/README.md)
preserves original checkpoints, before/after images, failures and corrections.

The actual native capture front door uses a fresh output directory and validates
the complete movie, stage inventory, image resolution and unchanged inputs:

```bash
package="$(node -p 'require("./.tools/scenarios/representative-corridor/current-package.json").root_relative_path')"
route="$PWD/.tools/scenarios/representative-corridor/$package"
./scripts/capture-endurance-sedan.sh --mode driving \
  --route-package "$route" --output reports/p1-018/native-driving
./scripts/capture-endurance-sedan.sh --mode presentation \
  --route-package "$route" --output reports/p1-018/native-presentation
./scripts/capture-endurance-sedan.sh --mode presentation --probe mirrors --lighting night \
  --route-package "$route" --output reports/p1-018/native-mirrors-night
```

`tools/vehicles/endurance_sedan/render.py` captures the saved Blender file with
fixed cameras, five named lighting rigs, clay materials and full turntable,
interior, separate-opening or simultaneous-opening sequences. Run it through
the pinned Blender with `--python-exit-code 1`; each new output directory gets
its exact source, configuration and per-frame hashes. It does not save changes
to the source. Capture timing is rendering throughput, not gameplay performance.

`--gpu-denoising` uses OpenImageDenoise on the OptiX GPU. `--technical-overlays`
creates explicitly labeled temporary x-ray views with actual anchors, occupant
envelopes, collision proxies and 0.5/1 meter rulers. `--views swatch_board`
compares nine actual source materials in one fixed scene. These diagnostic
overlays and swatch objects are never saved or exported with the vehicle.

The complete fixed capture recipe is `tools/vehicles/endurance_sedan/capture-recipe.json`.
Run `python tools/vehicles/endurance_sedan/capture_suite.py --help` for the
sequential, resumable Blender capture front door. Supply the locked source,
pinned Blender and FFmpeg executables, and a new output directory. A changed
source, renderer or recipe cannot reuse existing frames. Each complete sequence
is encoded and fully decoded before the next case starts.

`uv run tools/vehicles/endurance_sedan/review.py --help` describes the review
packer. It verifies source and frame hashes, copies full-size stills unchanged,
creates labeled contact sheets, encodes complete movies, and checks them with
a full decode. Its local `index.html` links the actual media and provenance.
Runtime captures must match the explicitly supplied normalized sedan scene.

To verify a delivered unsigned package on its actual target OS, run its included
standalone Python 3.13 tool:

```bash
python "$package_root/verification/verify_packaged_sedan.py" \
  --package "$package_root" --output "$evidence_root/selected-sedan"
```

This validates the immutable package inventory and runs the selected sedan's
driving and presentation scenarios through the packaged launcher. The equivalent
repository front door is `./scripts/verify-packaged-sedan.sh`. Keep the output
outside the package and use a new directory for each attempt.
