# P1-008 Hero GT generation 3, polish slice: stance, face, textures that survive the release build

- Date: 2026-09-04
- Task: P1-008 (Q-020 Option A, project-original grand tourer), following
  [the generation-3 audit](2026-09-04-p1-008-hero-gt-generation-3.md)
- Evidence: `evidence/M5/P1-008-hero-gt-gen3-polish.json`
- Review sheet: `docs/images/p1-008-hero-gt-gen3-polish-review.png`

## Outcome

| Question | Answer |
| --- | --- |
| Does the car read as a sports GT from every side in the engine? | Yes, in the new Forward+ walk-around: a low belt, a glasshouse a third of the height, fender shoulders over a dipped hood, a fascia with lamp bars over a wide grille, a low tail with the exhausts and plate on its face. The first cut, judged only from the rear chase view, was a slab-sided wagon. |
| Does the release build still load the vehicle? | Yes. The generated scene no longer names any texture; the packer detaches the references to a sidecar and the wrapper binds those that exist. The packaged smoke had been failing since #116 because the release presets exclude the rights-gated sourced folder and a scene with a missing `ext_resource` fails to load outright. |
| Did the semantic contract, physics numbers or budgets change? | No. 37 nodes, 2.84 m wheelbase, 1.64 m track, 0.34 m wheels, three LODs, the same collision proxy. |
| Is it AA yet? | Not signed off. The stance and face are right; the paint still reads flat under the procedural sky, the wheels and interior have had no second pass, and there is no baked occlusion. Q-020 remains open. |

## What changed

### Stance and surfacing (`spec.py`, `body.py`)

The proportion sheet fixed length, width, height, wheelbase and overhangs, but
the first cut put the beltline at 0.98 to 1.03 m: three quarters of the
1.30 m height, with 0.27 to 0.32 m of glass above it. The walk-around showed
the result plainly, so the profiles were redesigned to the ratios sports GTs
share and the sheet now records:

- belt at 0.90 m at the cowl, 0.89 m at the B-pillar, 0.925 m over the rear
  wheel and 0.93 m at the deck (0.65 of the height), with a shoulder crease
  60 mm below it at weight 0.74;
- glass 0.41 m tall from belt to roof rail, a narrower roof (0.785 m half
  width at the B-pillar) for more tumblehome;
- hood centreline 0.805 m at the front axle under 0.862 m fender crests, a
  0.60 m nose with a creased leading edge (section crease 0.55 at the hood
  front), a broader nose in plan (0.84 m half width, corner factor 0.78);
- deck 0.935 m and tail 0.905 m, ten centimetres lower than before, with a
  0.40 crease at the deck.

The nose and tail end caps now belong to the bumper covers at every station.
They used to hand their upper band to the hood and trunk, which begin well
behind the caps; that band became an island of the hood on the fascia, grew
its own dark rim, and showed as two dark ovals on the nose as soon as the
nose dropped.

### Face and details (`parts.py`)

- Headlamps are 0.44 m bars 82 mm tall on the fascia, centred 0.515 m high
  and 0.56 m from the centreline, swept back 24 degrees around the corner
  and cut from the bumper cover instead of the fender, where the old units
  read as chrome nubs from the front. Each still carries its housing,
  projector, LED strip and cover.
- Grille 1.16 by 0.25 m centred 0.325 m high; outer intakes moved out to
  0.72 m from the centreline.
- Exhaust tips raised to 0.385 m and the plate to 0.56 m: at 0.30 m the
  tips sat on the rolled underside of the bumper and their cavities hung
  below it as black boxes.
- Mirror housings are tapered ellipsoids with a flat glass face instead of
  spheres; wipers sit on the cowl surface (`surface_z`) behind the hood
  shut line rather than at the centreline height, which had left them
  floating over the lower hood.

### Tyres (`wheels.py`, `materials.py`)

The tyre ring has two materials: the tread set on the crown between the
shoulders, with `v` running around the circumference so the pattern rolls in
the driving direction, and a grained rubber (`Material_TireSidewall`,
Plastic012A) on the sidewalls and beads, which had been wearing the tread
texture across the wrong axis.

### Review capture (`VehicleVisualScenario.cs`, `capture-scenario.sh`)

A ninth stage, `walk-around`, orbits the car through 360 degrees at static
ride height in daylight with a 38-degree lens from 10.5 m, and validates that
the chase camera and LOD0 are active with the graybox hidden. The chase rig
rewrites the arm rotation and spring length every frame, so the stage switches
its processing off and the common reset switches it back on and restores the
field of view. The review capture is 540 frames; frames 480 to 539 are the
orbit. The 76-degree chase view stays for the driving stages but is no longer
the only exterior view, and it should not be used to judge proportion.

### Textures that survive the release build (`pack_imported_scene.gd`, `VehicleVisualRig.cs`)

The generation-3 scene referenced its 27 composed textures as `ext_resource`
entries under `assets/vehicles/sourced/hero-gt/`, the folder the release
presets exclude until Q-043 clears. Godot refuses to load a scene with a
missing dependency, so the packaged game lost the whole vehicle and the
clean-machine smoke failed on every run since #116. The packer now strips the
texture `ext_resource` lines and every `*_texture = ExtResource(...)`
property, and writes them to `hero-gt.generated.textures.json` (schema 1,
material name to slot to path). `VehicleVisualRig.BindSourcedTextures` runs
before the material polish, binds every path that `ResourceLoader.Exists`,
and publishes `sourced_textures_bound` and `sourced_textures_missing` for the
semantic suite, which asserts bindings present and none missing on a checkout (46 slot bindings from 27 textures). The
packaged build binds nothing and draws the flat-colour materials, which is
the behaviour the rights gate asked for. The sidecar is a tenth manifest
artifact and `verify-vehicle-asset.sh` compares it byte for byte like the
scene.

## Verification

| Check | Result |
| --- | --- |
| `create_hero_gt.py` | `CANNONBALL_HERO_GT_FACES lod0=52228 total=60131 meshes=170` |
| `validate_and_export_hero_gt.py` | `CANNONBALL_HERO_GT_EXPORT_OK triangles=123860 lod0=106660 materials=28` |
| `pack_imported_scene.gd` | `CANNONBALL_PACKED_TEXTURES_DETACHED materials=14 textures=27`; the generated scene has zero `ext_resource` entries |
| `validate_import.gd` | `CANNONBALL_HERO_GT_IMPORT_OK nodes=207 triangles=123860` |
| `validate_manifest.mjs` | `CANNONBALL_ASSET_MANIFEST_OK asset=hero-gt artifacts=10 nodes=37` |
| `run-scenario.sh --profile vehicle-visual` | all nine stages, including `walk-around` |
| `run-scenario.sh --profile integrated-visual-slice` | pass |
| `capture-scenario.sh --vehicle-visual-review --renderer forward_plus` | 540 frames; review sheet above |
| Release-build path | `run-scenario.sh --profile vehicle-visual` with `assets/vehicles/sourced/hero-gt` removed: all nine stages pass, no error lines, nothing bound |
| PlayGodot camera test | production rig binds 46 slots from 27 textures, none missing (local) |

## Defects found and fixed on the way

- The first walk-around did not orbit: the chase rig rewrote the arm every
  frame. It is disabled for the stage.
- Two dark ovals on the nose survived four rounds of moving the lamps; a
  matte re-render proved them geometry, a ray-cast grid proved the surface
  smooth, and a face dump found 320 hood faces with the dark rim material at
  the nose: the end-cap island above.
- The clean-machine smoke workflow had been red since #116 with a parse
  error on the first texture `ext_resource`; the late binding above is the
  fix rather than shipping the rights-gated files.
- The live suite fixes that landed between the two slices (#118, #119,
  #120) are recorded under Q-042 and in the generation-3 audit.

## Claims not made

- No human has approved the design or the rights; Q-020 and Q-043 stay open.
- The paint has not been tuned in the engine beyond a lower base roughness;
  a proper pass (colour, flake, clear-coat response under the game sky, and
  possibly a reflection probe) is the next slice.
- No second pass on wheels, interior, badges or decals; no baked occlusion.
- The PCK audit stage was not run on this machine (no Mono export
  templates); the packaged path was exercised by running the vehicle-visual
  profile with the sourced folder removed.
- No frame-time claim.
