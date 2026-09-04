# P1-008 Hero GT generation 3, details slice

- Date: 2026-09-04
- Task: P1-008 (Q-020 Option A, project-original grand tourer), following
  [the dash audit](2026-09-04-p1-008-hero-gt-dash.md)
- Evidence: `evidence/M5/P1-008-hero-gt-gen3-details.json`
- Review sheet: `docs/images/p1-008-hero-gt-gen3-details-review.png`

## Outcome

| Question | Answer |
| --- | --- |
| What was missing at close range? | The quarter panel had no fuel flap and the deck lip no third brake light; both are things the eye expects on a road car and reads their absence as a model. |
| What changed? | A fuel flap cut from the right rear quarter as its own aperture piece set 3 mm in with dark walls, so it reads as a shut line; a slim red lens along the trunk lip. |
| Did the contract or budgets change? | No. |

## What changed (`parts.py`, `create_hero_gt.py`, `preview.py`)

- `body_cutters(profiles)`: a 0.17 by 0.17 m rounded cutter at y = 1.62 m,
  z = 0.86 m on the right quarter, applied to the body panel after the
  bumper and lamp cuts; `build_side_parts` takes the aperture dictionary and
  builds `LOD0_FuelFlap` from it with `offset_copy` (3 mm depth, 2.5 mm gap,
  dark walls).
- `build_rear_parts` takes the profiles and adds `LOD0_BrakeLight`, a
  0.34 by 0.022 by 0.014 m red lens seated on the deck lip at
  `TRUNK_REAR_Y - 0.035`.
- The aperture keys keep the cutter suffix (`FuelFlapCutter`); the first
  cut looked up the wrong key and the flap was a hole for one preview.

## Verification

| Check | Result |
| --- | --- |
| `create_hero_gt.py` | `CANNONBALL_HERO_GT_FACES lod0=53121 total=61024 meshes=194` |
| `validate_and_export_hero_gt.py` | `CANNONBALL_HERO_GT_EXPORT_OK triangles=125713 lod0=108513 materials=28` |
| `validate_import.gd` | `CANNONBALL_HERO_GT_IMPORT_OK nodes=231 triangles=125713` |
| `run-scenario.sh --profile vehicle-visual` and `--profile integrated-visual-slice` | pass |
| `capture-scenario.sh --vehicle-visual-review --renderer forward_plus` | 600 frames; review sheet above |
| PlayGodot camera test | pass locally against the production rig |

## Claims not made

- No human approval; Q-020 and Q-043 stay open.
- No badges with lettering, no door mirror indicators, no baked occlusion.
