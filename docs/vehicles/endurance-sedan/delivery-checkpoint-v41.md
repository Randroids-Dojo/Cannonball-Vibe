# Delivery checkpoint v41

P1-018 remains in progress. On 2026-09-29 the owner asked to finish the sedan
branch, merge a verified model and add a driver-menu entry to the showroom.
This checkpoint replaces the installed production34 prototype with a fresh
bound construction of the current specification. It records every machine
gate it passed, the one source-QA stage it fails, and what stays open.

## What was promoted

`tools/vehicles/build_endurance_sedan.py` built the source from an empty
Blender scene with the committed constructor tree and the current
specification. The newer front, upper, tire and distant-lid stages
(`*_revision40` selectors) stay unselected. The build is not a v40 composition.

| Item | Value |
| --- | --- |
| Construction | fresh-construction 1,531 s and finalize-and-reopen 1,375 s, both exit 0 |
| Source | `endurance-sedan.blend` SHA-256 `c7dcd907…2aef` |
| Binding | `endurance-sedan.source-binding.json` SHA-256 `0c1b94f5…7d15b`, 359 locked constructor inputs |
| Triangles | LOD0 148,452, LOD1 27,362, LOD2 22,524; 198,362 total including 24 collision |
| Budget | 150,000 LOD0 and 200,000 total limits unchanged; passed |
| Materials | 26 of 32 |
| Runtime GLB | `endurance-sedan.glb` SHA-256 `1501414a…5b837` |

The source package installs the blend, binding, construction and lower-LOD
companions, and the complete `endurance-sedan-generation/` tree. New corner and
UV bake locks came from an explicit export of that source. The runtime outputs
were promoted from the candidate gate's verified staging project. The source
package is about 185 MB of Git LFS. Non-asset CI checkouts now skip the
generation tree and construction companions.

## Machine gates

| Gate | Result |
| --- | --- |
| Candidate asset gate | Passed: 62 commands, 24 rejection controls, 18 byte comparisons, all equal |
| Delivered asset gate | Passed: 63 commands, 24 rejection controls, 29 byte comparisons against the installed files, all equal |
| Hero GT asset gate | Passed: two deterministic rebuilds, 3 LODs, 37 semantic nodes |
| Runtime (`verify-endurance-sedan.sh --vehicle all`) | Passed: sedan 17 driving stages and 52 presentation stages, Hero GT 16, graybox 16 |
| Source QA (26 stages) | 25 pass; `static-interfaces` fails (below) |

The source QA runner stops at its first failing stage. The seven stages after
`static-interfaces` (openings, opening containment, tires, wiper glass, wiper
interassembly, wiper containment, negative controls) were run with the same
snapshot tools and inputs as a diagnostic, and all seven passed.

## Open source-QA failure

`static-interfaces` reports seven failures, all at the rear termination of the
roof side rails. `P1-018-QA41-ROOF-RAIL` records the details. Codex's full
source-QA runs on 2026-09-13 and on source60 on 2026-09-14 recorded the same
rail contacts and failed roof joints. No full source-QA pass exists since the
C-quarter construction landed in `ed2a2a2`.

- The rail ends at y = −1.2300 m. The rear roof closure web and the stamped
  C-pillar start at y = −1.2297 m. The rail overlaps both by about 0.3 mm,
  and one rail vertex sits 0.34 mm inside each C-pillar.
- The rail's rear return flange (y −1.0 to −1.23 m) lies outside the only
  declared uncharted-return region (y 0.100 to 0.1051 m). Its clearance below
  the whole roof is 13.7 to 17.5 mm, above the required 1 mm. The roof-return
  negative-control precondition fails for the same reason.

Close Blender renders of the junction show no visible artifact. The owner
chose to merge with this defect open rather than hold the model. The likely
repair is to end the rail about 1.5 mm earlier, or move the closure and C-pillar
front faces back, for at least 1 mm of clearance. The rear return also needs to
be declared or moved inside the roof chart. Either change needs a fresh build
and a full source-QA pass.

## Tooling corrections made for this promotion

- The source-QA tool snapshot did not carry `tire_policy40.py`, so every v2
  run failed at `current-front-field` after `15cf148`. The runner now copies
  the policy into its snapshot and locks it as an input.
- With a bound source installed, the source binding rejects a stale
  specification or exporter before the inventory comparison runs. Those two
  asset-gate controls now expect the binding's diagnostic.
- The new `Meridian_StaticLabels_v26` texture gained its import lock with the
  same parameters as the other six textures.
- The Hero GT manifest refreshed three shared tool hashes. Its art bytes are
  unchanged.
- The shared mirror material probe read the live rear feed after a fixed 12
  frames. The rear mirror draws last on a 15 Hz wall-clock schedule, so fast
  renderers often read it black. That happened on production34 too. The probe
  now also waits 250 ms, and its coverage threshold is unchanged.
- The first hosted run of the full gate passed the Windows asset gate. The
  next project import then scanned that gate's retained evidence inside
  `reports/` and failed its strict diagnostic policy. The verifier now marks
  its evidence directory `.gdignore`, and the sedan job timeout rises from 45
  to 75 minutes.

## Platform scope of the export gate

The bound source's export preflight replays Windows-built native checkpoints
with exact float equality. Hosted Linux and a local WSL run with pinned Linux
Blender 5.1.2 both fail on decoded tire normals that differ by one float32 ULP.
The stored fields, including the normal codes, match exactly. Making those
comparisons tolerant only exposes the next exact replay, first the groove
regeneration and then the current-front native snapshot. The hosted sedan
export step therefore runs on Windows, where the source was built and the
delivered gate passes. The Hero GT step also runs on Windows only. Its GLBs
match byte for byte on Linux, but its tracked contact sheet is a Windows
render. Linux keeps the all-vehicle runtime/import gate, which passes there.
`P1-018-CI41-LINUX-REPLAY` and Q-048 track portable replay.

## Not changed and still open

The uncommitted shared static LOD work, including the draft ADR-0029, is kept
unmerged on local branch `wip/p1-018-shared-static-lod`. The v40 refinements
and the 40 other open defects in `defects.json` remain. So do the art direction,
rights, driving feel and usability human gates. `human_approval_reference`
stays `null`.

Retained evidence: `data/assets/vehicles/endurance-sedan-review/delivery-v41/`.
