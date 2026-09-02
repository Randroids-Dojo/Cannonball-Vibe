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

Update 2026-09-02, later: `scripts/verify-playgodot-package-boundary.sh`
was a third caller of the blocked launcher and now uses `python -m
cannonball_map` like the scenario scripts, so the live suite can be verified
locally on the reference PC. `capture-reference-performance.sh` and
`validate-continental-route.sh` still call the launcher.

## Q-040 - Hero GT production art path

Q-020 selected the project-original Hero GT. The current model is beveled boxes
with nine flat materials and no textures; it is the weakest surface on screen
now that the world around it is textured. Reaching AA quality by script alone
is possible for the body (lofted profiles, subdivision, baked AO and curvature,
clearcoat) but a convincing cabin, wheels and light clusters are days of
modelling work.

- **A. Commission or license one car model** under a clear licence and adapt
  it to the existing semantic rig (the rig contract was designed for this).
- **B. Continue the procedural Hero GT** with a substantial remodel next pass
  (recommended if A is off the table; it stays fully agentic).
- **C. Both**: procedural now, replace later.

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
