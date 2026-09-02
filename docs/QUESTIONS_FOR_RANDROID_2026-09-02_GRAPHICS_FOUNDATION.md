# Questions for Randroid: graphics foundation after the 2026-09-02 autonomous pass

Date: 2026-09-02
Goal set for the session: raise every model in the game to a properly sourced or
meticulously built, realistic, performant, at-least-AA standard.

This handoff records what the pass delivered, what it deliberately left in your
hands, and the decisions only you can make. Working defaults are stated so
nothing is blocked; none of them closes a human gate.

## What landed (PR "P1-010: rendering foundation")

- Sourced CC0 art with recursive provenance: four Poly Haven sky HDRIs and
  eleven PBR texture sets, acquired by `tools/environments/sourced_assets.py`
  and locked in `data/assets/environments/sourced-assets.lock.json` with
  provider metadata, authors, canonical URLs, declared size and MD5, acquired
  SHA-256, timestamp and response headers.
- Sky-driven lighting shared by every visual scenario: panorama skies, AgX
  tonemapping, SSAO, glow, exponential fog, PSSM shadows, sun directions
  measured from each HDRI (`assets/environments/sky-presets.json`).
- A ground shader blending grass, dry grass, dirt and rock by route weights
  and slope, with two-scale anti-tiling and a far-field convergence, applied to
  the regional ribbons, the road terrain margin, junction seams and the
  backdrop.
- Heightfield massifs and hills with a slope- and altitude-driven rock, forest
  and snow shader replacing the cone and sphere placeholders.
- A project-original Blender conifer (three LODs plus impostor, EEVEE-rendered
  needle cards) through a contract-driven export gate, importer-normalised
  scene, manifest and `scripts/verify-environment-asset.sh`.
- Cell-based near-layer LOD streaming for stands of trees and rocks.
- A pre-existing streamer stall fixed: the environment review's urban-edge
  stage had been failing on main since the per-metre refresh gate landed on
  2026-08-16, because collision builds are capped at one per refresh and a
  stationary review point that needs two never triggered another refresh.

## Q-037 - Rights review for the sourced Poly Haven assets (blocking release inclusion)

Every sourced asset is CC0 1.0 and carries its record in the lock, but Q-023
requires an individual human rights review before a record moves from
`pending-human-review` to `approved`. Until then the runtime directory
`assets/environments/sourced/` is excluded from the Linux and Windows release
presets (`export_presets.cfg`), so exported builds fall back to flat colours
while local and CI scenario runs use the sourced art.

- **A. Approve all sixteen records now (recommended).** Flip each `license.status`
  in the lock to `approved`, remove the two `assets/environments/sourced/*`
  exclusions from the release presets, and record the approval in
  `docs/QUESTIONS_FOR_RANDROID.md` the way Q-023 was recorded. Poly Haven
  publishes everything under CC0 with no attribution requirement; the lock
  keeps attribution anyway.
- **B. Approve per asset.** Same edits for the subset you accept; the rest stay
  excluded and the kit falls back per set (each material checks its own set).
- **C. Reject Poly Haven as a source.** The pipeline is provider-agnostic in
  shape but only implements the Poly Haven API; another provider needs a new
  `plan` branch.

Working default: pending. Nothing ships sourced art until you answer.

## Q-038 - Git LFS budget for sourced art

The sourced files total 61 MB in LFS. Six CI workflows check out with
`lfs: true`, so every workflow run downloads them; GitHub's free LFS bandwidth
is 1 GB per month, which this could exhaust in about fifteen full runs.

- **A. Accept the cost and monitor** (working default), reviewing the LFS
  usage panel after a week.
- **B. Cache LFS objects in CI** with `actions/cache` keyed on the lock hash so
  each runner pulls once per lock change.
- **C. Shrink the payload**: 1K skies (soft at 1440p) or JPEG re-encodes would
  halve it but weaken the art and add a transform stage to the provenance.

## Q-039 - Windows Smart App Control on the reference PC

Verified this session from Code Integrity events 3077/3118: Smart App Control
blocks every newly written unsigned binary, whatever its hash. A fresh
`uv sync` in a new worktree yields a venv whose `pyogrio` extension cannot
load, and uv regenerating the shared venv's `cannonball-map.exe` launcher
produced a blocked launcher in `C:\Dev\Cannonball-Vibe\tools\map_pipeline\.venv`
(that happened during this session; the launcher there is now blocked).

Mitigations landed: `python -m cannonball_map` (a `__main__.py` entry) replaces
the launcher in `scripts/run-scenario.sh` and `scripts/capture-scenario.sh`.
`scripts/capture-reference-performance.sh` and
`scripts/validate-continental-route.sh` still call the launcher and were left
untouched because P1-013 and P0-021 own them.

- **A. Switch the remaining two scripts to `python -m` (recommended)** and note
  the machine constraint in `docs/audits/2026-07-23-reference-windows-hardware.md`.
- **B. Turn Smart App Control off or to evaluation** on the reference PC, which
  restores fresh venvs but changes the machine the Q-022 evidence was recorded on.
- **C. Keep one trusted venv** and point worktrees at it with
  `UV_PROJECT_ENVIRONMENT`, `UV_NO_SYNC=1` and `PYTHONPATH`, which is what this
  session did locally.

## Q-040 - Hero GT production art path

Q-020 selected the project-original Hero GT. The third stacked PR of this
pass (P1-008) replaces the beveled-box baseline with a second-generation
procedural model under the unchanged 37-node contract: a lofted, subdivided
grand-tourer body with booleaned arches, a split greenhouse, spoked wheels
with brakes, LED bars, mirrors and a cockpit, with clear-coat paint and
tinted glass restored by the wrapper. It reads as a car now, but a
script-built body cannot reach the panel gaps, trim, badges and interior
detail of a modelled production vehicle.

- **A. Keep iterating the procedural Hero GT** (working default; fully
  agentic, deterministic, rights-clean).
- **B. Commission or license one car model** under a clear licence and adapt
  it to the same semantic rig; the rig contract and gates are ready for it.
- **C. Both**: procedural now, replace later.

Reviewer note: the first-generation Hero GT had been mounted backwards since
2026-07-18. The Blender exporter maps Blender +Y to Godot -Z, the direction
the vehicle drives and where its front axle raycasts sit, while the v1 export
profile assumed -Y did. The nose, headlights and steering wheels therefore
rendered at the tail in every chase capture. The new generator mirrors the
model as its last step, the vehicle lint now asserts the front axle exports
to -Z, and a v3 export profile states the true axis mapping. The P1-002
fixture and the conifer are symmetric and unaffected by the v1 claim.

## Q-041 - Renderer tiers and how the shipped build selects High

The first CI run of this slice showed that reference-PC renderer settings
cannot live in `project.godot`: the software-rendered runners cancelled
Windows M0 at its 15-minute timeout and failed a PlayGodot camera probe.
The project defaults are therefore the Balanced tier (2x MSAA, 8x
anisotropy, 4096 directional shadow atlas, soft-low filtering, low SSAO),
and `RenderQuality.Apply` raises the viewport and rendering server to the
High tier (4x MSAA, 8192 atlas, soft-medium filtering, medium SSAO) when the
game starts with `--environment-quality=high`, the argument that already
scales the environment layers. Textures import VRAM-compressed with mipmaps
on the fast S3TC path; the four HDRIs stay uncompressed RGBE.

What this leaves open: a player on the reference PC gets Balanced unless
something passes that argument. There is no settings menu and no GPU
detection.

- **A. Settings-menu entry in P1-013 (recommended).** The tier becomes a
  saved user setting; automation keeps the command-line argument.
- **B. Auto-select High on first run** when the adapter name matches a
  discrete GPU, with the menu entry as the override.
- **C. Ship High as the default** and give CI an `override.cfg` that pins the
  Balanced tier. Cheapest, but the gates would then run settings the player
  never sees.

## Q-042 - macOS live-suite bounds after the graphics slices

Three PlayGodot live-suite failures landed on the software-rendered runners
the afternoon the slices merged, each a wall-clock bound rather than a wrong
value: the macOS pause wait (the Q-035 class, once), the macOS
`elapsed_seconds < 1` restart bound (twice, at 2.31 s and 1.96 s with every
exact field of the restart matching), and one Ubuntu camera-handling wait.
The suite had slowed from about 90 s to 138 to 195 s on Ubuntu with the
production art on llvmpipe. The follow-up PR runs the suite against the
graybox environment, which is what it ran against before the slices, and
the bounds themselves are untouched. `docs/OPEN_QUESTIONS.md` carries the
run and job ids.

- **A. Root-cause the remaining bounds in the Q-035 style (recommended)**:
  re-express latency-shaped bounds such as `elapsed_seconds` against the
  game clock the run already exposes, so a slow describe cannot fail them.
- **B. Accept graybox as the live-suite environment and leave the bounds**,
  logging further recurrences under Q-042.
- **C. Drop the macOS runner from the live suite** and keep it on the
  packaged smoke only.

## Reviewer notes, not questions

- Cold Godot import of the whole project took 52 s on the workstation with
  BC7 and BC6H encoding and 7 to 9 minutes on the 4-vCPU runners; it takes
  13 s on the workstation after the import settings moved to S3TC and
  uncompressed RGBE. It runs once per CI job now that `run-scenario.sh`
  imports before launch.
- `verify-environment-assets.sh` and `verify-environment-asset.sh` are not in
  any CI workflow; the first would have caught the streamer stall. Adding
  them to the post-merge tripwires is a P1-010 follow-up.
- The scenario capture path still renders through the Compatibility renderer;
  the frames in the audit are therefore below what the Forward+ reference PC
  path shows (no SSAO, no glow).
