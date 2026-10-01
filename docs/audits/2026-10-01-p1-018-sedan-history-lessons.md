# P1-018 Meridian S8R: lessons from the local-only build history

Date: 2026-10-01. Task: P1-018. Status: retrospective analysis; no model,
gate or acceptance change. Authority: AGENTS.md (dated investigation results).

The sedan took three weeks of agent work: Codex 2026-09-10 to 09-14 and
09-20 to 09-21, then Claude 09-29 to 09-30. Most of what was tried and learned
lives only in gitignored local folders. This note distills it so the model can
be picked up again without rereading 175 GB of reports. It separates what the
evidence shows works, what it shows does not work, and what still needs
evidence either way.

## Sources and how they were read

| Location (local only, gitignored) | Size | Files |
| --- | ---: | ---: |
| `C:/Dev/Cannonball-Vibe-sedan/reports/p1-018/` (Codex) | 124 GB | 330,100 |
| `C:/Dev/Cannonball-Vibe-sedan/.tools/` (pinned tools, staged projects) | 29 GB | 81,253 |
| `C:/Dev/cv-sedan-finish/reports/p1-018/` (Claude delivery) | 19 GB | 29,499 |
| `C:/Dev/scratch/`, `C:/Dev/sedan-builds/` | 3.5 GB | 11,356 |

The read covered every human-written handoff, plan, retry note and review:
1,076 unique Markdown files after de-duplication, and the newest version of
each of 685 document series, plus all failure and retry notes. It also
summarised 5,329 status records and the 1,360-entry command log. On-main
records were used as the backbone: `docs/vehicles/endurance-sedan/defects.json`
(142 defects), the checkpoint documents v21 to v41, and the ledger notes.
Paths below under `reports/p1-018/` refer to the local Codex worktree.

Scale of the effort, for calibration:

- 499 workstream folders; 5,329 machine status records, of which 1,611
  passed, 481 failed and 8 were explicitly rejected. Hundreds more are
  "prepared, not executed" or "unaccepted trial".
- The command log for 09-10 to 09-14 alone has 1,360 recorded commands
  (796 Blender), 15 % nonzero exits and 22.6 hours of recorded wall time.
- A complete fresh construction takes about 24 minutes, finalize, save and
  reopen another 17 minutes, and the full asset gate about 40 minutes.

## Bottom line

1. The pipeline works. The car on main is a reproducible, bound build that passes the asset, runtime and showroom gates. Every pipeline lesson below is about keeping that property.
2. The car still looks unfinished, and the cause is shape, not shading. The upper greenhouse and the front fascia were attacked for two weeks with local patches and normal-field edits. Diagnostics repeatedly showed the defects survive in clay renders and with automatic normals. They need section-level redesign.
3. The triangle budget, not effort, stopped the newer design. The v40 front, upper and tire refinements composed to about 155,000 LOD0 and 207,000 to 212,000 total triangles, against the 150,000 and 200,000 ceilings. Every small-part reserve hunt after 09-13 found little or nothing.
4. Several real engine and runtime bugs were found through the sedan work and fixed for every vehicle. Those are the most transferable wins.

## Timeline

| Dates | Phase | Outcome |
| --- | --- | --- |
| 09-10 | Research (2016 US Audi S6 benchmark), blockout, specification locks | Original fictional Meridian S8R identity; dimension sheet and acceptance matrix |
| 09-10 to 09-11 | Production sources 05 to 34 | production34 installed (149,428 / 26,726 / 10,136 triangles); still the runtime car until 09-29 |
| 09-11 to 09-12 | Refinement35, assembly26, roof/front trials | Many local wins in shading; roof and fascia form rejected repeatedly |
| 09-12 to 09-13 | Showroom, CI hardening, fresh-construction pipeline, LOD port | Showroom accepted; source-generation binding v2 designed; source14 at 197,280 total |
| 09-13 to 09-14 | Cover, upper junction, materials, mirrors, tire-step | Valance cover (source193), mirror and material budget fixes, tire-step physics fix |
| 09-20 to 09-21 | v40 front/upper/tire/lid work, budget recovery, shared-LOD idea | Composition over budget; recovery routes fail; ADR-0029 draft; Codex stops |
| 09-29 to 09-30 | Claude delivery v41 | Fresh bound build of the default specification (no v40 selectors), merged as #144; red-main #146 fixed by #147/#148 |

## What works

### Pipeline and process

- **Fresh empty-scene construction plus a source binding.** `build_endurance_sedan.py` builds from an empty Blender scene. The binding locks all 359 constructor inputs and the generation tree. That is what finally made the export reproducible and the CI asset gate meaningful. The 09-14 audit (`qa/source-binding39-audit01`) showed the hosted failure could not be faked away: source, binding, construction companions, generation tree, exports and manifests promote as one unit. Keep that rule.
- **Checking the real artifact, not the intent.** Independent QA on the exported GLB, reopened `.blend`, full-resolution renders and pixel-to-triangle rays found defects that author-side checks passed. Examples: 14 degenerate triangles only visible in the GLB, a floor intersecting the rear tires, climate knobs floating 31 mm from the dash, duct vanes 6.5 mm from anything, 36 cooler fins inside the radiator (136 cm³), a coolant hose through the wheel tub, and a real cabin opening above the rear door that rays saw through to the steering wheel.
- **Complete pair scans over sampled checks.** Exhaustive assembly pair inventories (tens of thousands of pairs per pass) and continuous opening-motion bounds found interferences that spot checks missed, including a brake LOD that cut through the rim only during wheel roll.
- **Cheap causal diagnostics before editing geometry.** These four settled most "is it shape or shading" questions within one render pass:
  - Single-light renders. They showed the 09-12 front fork was two studio reflections, not a mesh defect.
  - Clay versus material branches. On the roof, roughness and IOR changes only moved the glare; the layered section and dark channel stayed (`qa/roof-response26-diagnostic01`).
  - Automatic versus authored normals. The front slab and doubled shoulder highlight were unchanged with automatic normals, so they are form (`qa/front-normal39-review01`, `qa/front-form53-review01`).
  - Pixel-to-triangle ray attribution. It named the exact face behind each artifact.
- **The showroom architecture.** A CanvasLayer with a SubViewport, its own World3D and a frozen display actor reuses the real presenter for hinges, lamps and wipers. It passed functional review on all three platforms. Tighter presets and a studio horizon fill (09-14) fixed most framing complaints.

### Surface and shading techniques

- **Restoring the original field after Booleans.** Capture the native normal and UV field before the first Boolean cut, then restore it on faces still wholly owned by the original sheet. This produced clear visible wins at zero triangle cost:
  - the fender seam ripple;
  - the front arch wedges and the faceted patch beside the headlamp (front-sheet trial, "substantial local improvement");
  - pinches on the columns below the B-pillars;
  - pillow highlights beside the exhausts;
  - bright bars inside the windshield and backlight.
- **Explicit authored fields for machined parts.** Flat axial caps and radial walls on brake rings, hats, hubs, strut tops and fasteners removed lobed reflections. The same went for chamfer fields on the tank and cooler cases. All zero triangles.
- **Authoring normals last.** Encoding before triangulation or later cuts was undone, by up to 18°, by the next topology operation.
- **Budget economies that held up visually:**

  | Change | Saving |
  | --- | ---: |
  | Wheel radial reduction | −2,736 LOD0 |
  | Bevel segments 2 to 1 on 13 parts | −1,266 |
  | Speaker caps | −1,280 |
  | Tire grooves revision38 (4,728 to 4,472 per tire) | −1,024 |
  | Repeated detail (airbox ribs, cooler fins) | −448 |
  | Rotor vanes 30 to 24 | −288 |
  | Detail sampling | −192 / −672 |
  | Distant LOD1 tires | −2,040 lower |

### Runtime and engine (all on main, benefiting every vehicle)

- **Tire-step limiter.** The explicit small-slip tire gain was about 2.2 at 120 Hz. That made a resting car oscillate in roll at about 0.1 rad/s forever, which exceeds the 0.05 rad/s readiness limit. Bounding each lateral tire impulse by the contact's effective mass about the true centre of mass fixed it (settles in 240 frames). The 79-run dynamics matrix and the 30/60/144 FPS hashes are unchanged.
- **Imported material contract.** The wrapper had silently dropped glTF clearcoat on the sedan's standard paint. Godot's importer also ignores the `KHR_materials_specular` factor; it is now adapted at F0.
- **Material budget fit.** The three mirror materials share one shader with three viewport samplers. That brought the sedan from 33 to 34 active materials down to the 32 ceiling, with zero headroom.
- **Sky reflection filtering.** The "cloudy, forked hood reflections" in the showroom were a sky-filtering artifact: Realtime filtering at radiance 256. Incremental filtering removed them.
- **Lamp material ownership.** Each new rig multiplied the shared source lamp material by 0.12. The legacy path now runs only without a presenter.
- **Rear mirror as a rendering approximation.** The physically placed mirror camera mostly sees headrests: the backlight fills 5 % of the frame at 55°. A fixed camera behind the headrests at 30° clears the cabin at 10 m and 30 m, day and night (with the sourced HDRI sky).
- **Test harness robustness.** These fixes landed:
  - PlayGodot signal waits get distinct callables, because Godot bound callables compare by their method.
  - Shutdown goes through the application's own close request and checks the exit code.
  - First-frame budgets of 60 s cover hosted software renderers, where first frames take 18 to 32 s.
  - Observation-order fixes for camera, save-clock and showroom tests.
  - Several CI "failures" were test races, not game bugs.

## What does not work

### Local patches to a section-level design problem

The roof, rail, C-pillar and window surround is the clearest case. Over 09-11 to 09-21 the sequence was:

- feature-loft;
- closure web;
- bilinear centres;
- resection29;
- outer section50;
- boundary field57;
- long C-skin;
- shallow return;
- exterior roll;
- joined shared surface (+864 triangles);
- the six-part upper junction (+1,368);
- a seal crown;
- the v40 upper (31 input roles, 28 output roles).

Each was rejected visually or physically, or gave only a small local gain. The measured causes are structural:

- the rail outer wall sits 44 mm inboard of the sash top, so lofts between them kept the channel;
- the roof has no transverse crown at the front, and only 25 to 29 mm centre-to-edge drop further back, so it reads as a flat cap;
- the window frame seats keep the surround 14 to 16 mm proud of the glass;
- the old C fore wing already occupies the rail solid, so a cap-only repair cannot clear it.

The same area fails source QA today (`P1-018-QA41-ROOF-RAIL`). The v40 upper (actual100) failed four physical predicates, including 0.06 mm Backlight to C clearance against 1.001 mm required. Preserving old contours "forces the exposed shape back toward the rejected profile" (`research/upper-junction30-proposal01/INTERFACE293.md`).

### Normal-field work past restoration

Field restoration fixes damage the construction did to a good shape. It cannot fix a poor shape. The front fascia proves it: authored and automatic normals look the same. The slab-like upright face, the deep corner wrap, the pointed lower lip and the doubled lamp-shoulder highlight are geometry. The lamp highlight sits on the continuous repaired sheet, where field jumps are at most 0.005°.

### Deformation fields over Boolean meshes

The fascia nose-roll and intake-taper trials took 15 or more numbered retries. Nonlinear bends folded planar opening walls across old diagonals (37 crossings). The taper twisted thin grille ribs, sheared the undertray into the body, and the optical sweep opened the hood shut-line. Each fix needed exact retriangulation. The visual verdicts were "partial" or "rejected".

### Hunting small-part triangle reserves

After 09-13 almost every reserve search failed:

- The hardware inventory found nothing under a 0.1 mm chord limit, because the 330 circular parts are already economical.
- Castings and vent louvers showed visible regressions.
- The brake LOD1 tier interfered with the rim during roll.
- An inboard wheel wall entered the body.
- An exact-plane cabin shell increased cost by 2,024.
- A ratio sweep saved 68 and added a penetration.
- A census found no concealed 2,700-triangle reserve; 694 of 1,014 parts are already LOD0-only.

### Byte-exact identity as the default acceptance

Strict equality caught real defects, but a large share of failures were bookkeeping:

- tuple versus list after JSON;
- swapped vertex storage order;
- Godot `int` versus JSON `float` in arrays;
- Blender's runtime matrix cache after reopen;
- the Blender Bevel modifier averaging UVs in pointer-hash order (nondeterministic last bits);
- one-ULP float differences on Linux.

The Linux one-ULP replay difference is why the hosted sedan export gate now runs on Windows only (Q-048, `P1-018-CI41-LINUX-REPLAY`). Exactness belongs on shipping bytes and declared invariants, with correspondence-aware comparison everywhere else.

### Other things that did not work

- **Measuring reference performance on the development PC.** The capture's idle-GPU admission check rejected the run: the GPU was at 39 % with 46 clients against a 10 % ceiling. Fullscreen also picked the 3840×2160 monitor. ADR-0023 reference performance was never measured for any sedan build.
- **Keeping review media in Git LFS.** Export staging hydrated about 14 GB of review media and timed out. The LFS budget ran out from 09-26 to 09-30.
- **The physically correct narrow mirror.** A 4.5° optical corridor shows only a car's roof at 10 m, and is nearly black at night.
- **Fixture identity in moving mirror captures.** Colour markers confused with foliage, codes read through tinted privacy glass, and Windows Application Control blocking the managed helper consumed most of 09-21. None of it changed the car.

## What needs more evidence

Each item states what is unknown and the smallest experiment that would decide it.

| Question | Why open | Smallest deciding evidence |
| --- | --- | --- |
| Can the greenhouse read as a crowned, flush cabin within budget? | Only local trials were built. Research proposed rebuilding Roof, both rails and both C-pillars as one section network, with new frame and seal receivers. | One clay-only prototype of that whole section network at fixed cameras, with its triangle count, before any finite-fit proof. |
| Does a fascia section redesign fix the slab front? | Recommended (outer-corner wrap, tapered lower corner, section carried into the fender), never built | Same: one shared fascia and fender section prototype in clay, then material, at the existing whole-car and grazing cameras |
| Would a guide-surface workflow beat the procedural Boolean constructor for reflective panels? | Hypothesis from a 09-13 research note: keep an uncut guide surface and conform panels to it. Never tried here. The current constructor builds about 1,100 meshes with Booleans and then repairs their fields. | Rebuild one panel family (front fender plus bumper) both ways and compare moving-light strip renders and cost |
| Is 150,000 / 200,000 the right constraint for this car? | Budgets bind every decision, but the ADR-0023 performance they protect was never measured on an idle reference PC | Run the prepared five-case reference capture (69 measured minutes) on an idle machine. If headroom is large, propose a superseding ADR rather than more reserve hunts. |
| Does sharing identical LOD1/LOD2 static geometry pay off? | ADR-0029 (Proposed). LOD1 and LOD2 BoundaryRemainder batches are exact duplicates of 8,926 triangles. Runtime and test exist on `wip/p1-018-shared-static-lod`, untested end to end. | A fresh full build with the policy, plus a 28 m / 65 m transition comparison. Note it lowers the total but not LOD0. |
| Can a baked tire shoulder fund the redesign? | Projected −7,264 LOD0 (148,898 to 141,634), +1 material, 96 MB texture ceiling. Bake coverage verified; texture response acceptance open (Godot ignores the blue normal channel, up to 3.2° difference). | Matched close and distant wheel renders in Godot Forward+ against the geometric tire, plus the texture cost readback |
| Is night black-paint readability lighting or material? | `SR29-010` and `SR29-015` open; studio horizon fill helped daylight and studio views only | Night comparison with exposure, sky energy and paint roughness branches, the same way the roof clay test separated form from shading |
| Does the rear mirror stay useful in motion? | `RUNTIME70-MIRROR-INTERPOLATION`: the effective rear camera lags its assigned pose by up to 0.87 m, inside a headrest while reversing. The proposed interpolation fix was never promoted. | Integrate the mirror camera interpolation fix and rerun the existing moving mirror stages |
| Portable export replay | Linux decodes tire normals one float32 ULP apart from the Windows-built checkpoints | A replay design that compares stored fields, not re-decoded floats (Q-048) |
| What does the owner actually want fixed first? | No human art, driving-feel or usability gate has ever been run. Priorities came from agent visual reviews. | One owner review of the current car in the showroom, ranked against the whole-form priority list (`qa/whole-form39-priority01`) |

## Recommendations for the next model pass

1. Get an owner ranking first. The agents' consensus top three are the greenhouse cap with heavy bright surround, the slab front fascia, and night or black-panel readability.
2. Measure reference performance on an idle machine before any more triangle work. The budget decides what is possible, and it has never been checked against real frame time.
3. Make one section-level form change at a time, starting in clay. Prototype the shape at fixed cameras before writing finite-fit proofs. Two weeks of proofs on shapes later rejected visually was the largest waste in this history.
4. Keep the delivery pipeline as is: fresh build, source QA, explicit bakes, candidate gate, promotion, delivered gate. Any tool edit needs a rebuild because the binding locks the tools.
5. Use zero-cost shading fixes freely. Original-field restoration after Booleans, and authored fields on machined parts, are proven.
6. Stop hunting small-part reserves. The remaining large levers are the tire shoulder bake, shared static LODs, the RearBumper family (4,188 triangles) and a measured budget review.
7. Move review media out of Git LFS before the next large capture campaign, and back up the local evidence that defect records cite (about 1,200 references).

## Budget history

| Snapshot | LOD0 | LOD1 | LOD2 | Collision | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| production34, installed 09-11 | 149,428 | 26,726 | 10,136 | 24 | 186,314 |
| full07 (09-12) | 149,180 | 32,264 | 18,474 | 24 | 199,942 |
| fresh02 combined29 (09-13) | 148,898 | 29,248 | 22,342 | 24 | 200,512 (fails) |
| current-front36 rebind (09-13) | 148,898 | 27,156 | 22,290 | 24 | 198,368 |
| source14, revised tires (09-13) | 147,874 | 27,156 | 22,226 | 24 | 197,280 |
| source14 with repeated detail (09-13) | 147,426 | 27,156 | 22,226 | 24 | 196,832 |
| **source193 with cover, shipped as v41** | **148,452** | **27,362** | **22,524** | **24** | **198,362** |
| v40 front/upper composition, actual122 (09-21) | 155,318 | 31,646 | 25,278 | 24 | 212,266 (fails both) |

The v41 delivery is the source193 lineage built fresh from the default specification. The v40 work remains on main as unselected `*_revision40` constructor code. Its evidence is listed in `current-source-checkpoint-v40.md` and lives under `reports/p1-018/finish-branch40/`.

## Evidence that exists only locally

The defect, acceptance and sedan documents on main cite about 1,200 paths
under `reports/p1-018/`, most with SHA-256. None is in Git. The most useful folders for a future
pass:

- `qa/whole-form39-priority01`, `qa/front-form53-review01`,
  `qa/front-normal39-review01`: form-versus-shading verdicts and the priority
  ranking.
- `research/upper-junction30-proposal01/`: the full greenhouse trial history,
  including the structural causes listed above.
- `reflective-comparison38-01/external-inputs/reflective-surfaces.md`: the
  guide-surface workflow note.
- `runtime/budget154-01/` and `qa/rear-lod187-proposal01/`: budget census,
  failed recovery routes, shared-LOD evidence.
- `runtime/source-reserve33-proposal01`, `runtime/tire-bake34-proposal01`,
  `runtime/tire-bake35-analysis01`: tire shoulder bake.
- `runtime/final-performance52-01/`: the prepared reference-performance runs.
- `geometry-scope28-01/`: every pre-implementation scope record.

Until those are archived somewhere durable, this note and the on-main defect
records are the only copy of what they established.
