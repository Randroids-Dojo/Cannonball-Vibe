# P1-008 Hero GT generation 3, paint and cockpit slice

- Date: 2026-09-04
- Task: P1-008 (Q-020 Option A, project-original grand tourer), following
  [the polish audit](2026-09-04-p1-008-hero-gt-generation-3-polish.md)
- Evidence: `evidence/M5/P1-008-hero-gt-gen3-paint-cockpit.json`
- Review sheet: `docs/images/p1-008-hero-gt-gen3-paint-cockpit-review.png`

## Outcome

| Question | Answer |
| --- | --- |
| Does the paint read as car paint in the engine? | Better. A deep metallic navy (sRGB 0.11, 0.17, 0.33; metallic 0.50, roughness 0.26 under the clear coat) shows the sky and horizon moving over the body in the walk-around, where the mid blue read as flat plastic. Judged by an A/B capture of the same frames before the colour went into the generator. |
| Can the cockpit be reviewed, and does it hold up? | Yes, in a new daylight cockpit stage. The eye point had sat 3 cm behind the steering wheel rim, so the wheel never showed; it now sits 0.25 m behind the wheel centre and 0.55 m above the H-point. With A-pillars, a windshield header, sun visors and a roof-following headliner added as interior parts, the cabin reads as a coupe from inside rather than a convertible. Screens are dark glass with a dim glow instead of flat light-blue slabs, and the suede trim is neutral rather than teal. |
| Did the semantic contract change? | No. 37 nodes; `Camera_Cockpit` moved within the cabin, which the contract allows. |
| Is it AA yet? | Closer, not signed off. The dash is still a rounded slab with boxes on it, the seats are box assemblies, the screens carry no interface, and the exterior has no badges, decals or baked occlusion. Q-020 remains open. |

## What changed

### Paint (`materials.py`, `preview.py`)

`paint_color` is linear (0.0116, 0.0246, 0.0884), metallic 0.50, roughness
0.26; the flake strength and orange-peel strength stay at the polish-slice
values (0.22 and 0.1). The wrapper's paint shader takes the source colour,
metallic and roughness, so no engine-side constant changed. The colour is an
art-direction choice made for review; the handoff note under Q-020 records
it as reversible in one constant.

### Cockpit (`interior.py`, `create_hero_gt.py`)

- `Camera_Cockpit` at (-0.34, 0.30, 1.10): 0.25 m behind the wheel centre,
  0.55 m above the 0.55 m H-point, 0.35 m ahead of the seat back.
- A-pillars: suede bars from the cowl corners to the roof rail, 45 mm inboard
  of the glass, so the cockpit camera (which culls the glass and roof shell)
  still sees the pillar line. A windshield header bar spans the rail.
- Headliner in three panels following the roof profile from the header to the
  backlight; two sun visors folded against the header.
- `Material_Screen`: near-black glass, roughness 0.08, emission (0.05, 0.12,
  0.22) at 0.7 instead of (0.10, 0.35, 0.60) at 2.5.
- `Material_InteriorSuede`: multiplier (0.30, 0.25, 0.21) over the scuba
  suede set, which is blue and had tinted the headliner and pillars teal.

### Review capture (`VehicleVisualScenario.cs`, `capture-scenario.sh`)

A tenth stage, `daylight-cockpit`, switches to the cockpit camera under the
daylight preset and pans 26 degrees to the right over the stage, validated to
use the cockpit camera. The common reset zeroes the cockpit camera child's
rotation so no other stage inherits the pan. The review capture is 600
frames; 540 to 599 are the daylight cockpit.

## Verification

| Check | Result |
| --- | --- |
| `create_hero_gt.py` | `CANNONBALL_HERO_GT_FACES lod0=52390 total=60293 meshes=177` |
| `validate_and_export_hero_gt.py` | `CANNONBALL_HERO_GT_EXPORT_OK triangles=124184 lod0=106984 materials=28` |
| `pack_imported_scene.gd` | 27 texture references detached from 14 materials; no `ext_resource` in the scene |
| `validate_import.gd` | `CANNONBALL_HERO_GT_IMPORT_OK nodes=214 triangles=124184` |
| `validate_manifest.mjs` | `CANNONBALL_ASSET_MANIFEST_OK asset=hero-gt artifacts=10 nodes=37` |
| `run-scenario.sh --profile vehicle-visual` | all ten stages |
| `run-scenario.sh --profile integrated-visual-slice` | pass |
| `capture-scenario.sh --vehicle-visual-review --renderer forward_plus` | 600 frames; review sheet above |
| PlayGodot camera test | production rig, 46 slot bindings from 27 textures, none missing (local) |

## Claims not made

- No human has approved the colour, the design or the rights; Q-020 and
  Q-043 stay open.
- The dash, seats and screens are placeholders in form; only their eye-level
  read was fixed here.
- No badges, decals, baked occlusion or reflection probe; no frame-time
  claim.
