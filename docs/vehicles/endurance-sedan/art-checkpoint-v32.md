# P1-018 combined Blender checkpoint v32

The editable combined pilot is
`reports/p1-018/combined-form29-pilot01/uv04/source.blend`, SHA-256
`27e24adc70da451047181063a0fd29263e4f54a7452928da6ba5054f4710a73b`.
It contains the repaired body/door and front-arch fields, fitted C skins and
supports, corrected rear valance fields, and deterministic hood/trunk UVs.
Its148,898 LOD0 triangles fit the150,000 ceiling. Lower LODs and final
production installation are still pending.

The [retention index](../../../data/assets/vehicles/endurance-sedan-review/art-checkpoint-v32/index.json)
contains3,436 files in10 archives (1,045,828,721 bytes). Every archive was
built twice, directly compared and read back for every member's SHA-256 and
CRC. Ten unchanged payloads reference the retained v26/v27 inventories.
This verifies review-archive reproducibility; final shipping GLB identity
remains a separate gate. The failed preparation and all rejected modeling
trials remain available.

Blender5.1.2 `ec6e62d40fa9` generated the earlier fresh02 foundation from an
empty scene with188 locked inputs. Lead then derived composed02 andUV04
from that source. Fourteen changed meshes have identical evaluated fields
after the composed source reopens;1,090 other raw meshes/modifiers remain
exact. The C receiver field check uses the actual repaired body input.
The fitted supports meet the actual finite body surfaces and retain their
seats, belt guides and26 checked nearby clearances. These are modeled
assemblies and bounded fit evidence, with no strength or mechanical simulation.

Eight actual2560x1440 Cycles renders show the combined result from both
three-quarter views, both sides, top, rear and two front close-ups. The broad
door/body and front-arch reflections remain corrected. Independent QA confirms
the rear-valance shading correction in four separate matched pairs. The lamp
transition still has a forked reflection; upper roof/window/C joins and lower
bumper ends remain visibly unfinished. The
[actual review](../../../reports/p1-018/combined-form29-pilot01/review06.json)
records those limits. Its images use composed02 before the separate UV bake.

The hood/trunk UV correction carries the original authored coordinates through
the unchanged native modifiers, then computes a stable per-vertex mean. It
uses no quantization. Maximum change is9.536743e-7 under the unchanged1e-6
guard, with all non-UV evaluated fields exact. Root bakes exactly those two
modifier pairs and retains the original grids/modifier recipe in construction
witnesses. Source generation will integrate this step before LOD capture.
The old LOD trial's strict UV failure remains historical evidence; it is not
relabeled as passed. Actual current combined LOD totals are still being measured
against the unchanged200,000 ceiling.

To inspect locally, open the source above using the supplied Blender executable.
Select `RigControls` for opening, lighting and wiper properties. The base source,
complete native fields, staged construction scripts and actual images can be
restored from the10 archives into a clean worktree with relative paths preserved.
The bound construction sequence is `front-joined29-pilot01/run02.py`, then
`combined-form29-pilot01/compose02.py`, then `uv04.py`; their output directories
are guarded against overwriting an existing checkpoint. This is the current
reproducible pilot sequence, not the final production constructor.

The implemented game showroom remains available through **F2 → Explore in
showroom**, with orbit/pan/zoom, cabin/engine/luggage views, all six opening
controls, lighting, wipers and photos. It still uses the installed production34
asset. The new pilot will replace it after current-source LOD, export and runtime
checks. Hero GT and graybox behavior remain covered by the retained viewer
regressions.

P1-018 remains in progress. Full final construction, continuous opening/fit
checks, two identical GLBs, clean imports, footage, reference performance and
declared platform asset checks remain required. Human art/rights, driving,
physical-wheel and usability gates remain open.

The full Windows `scripts/check.sh` front door passes all13 steps for this
checkpoint, including doctor, build/unit suites and official Godot scenarios.
Its checked inputs remain identical throughout. Logs, exact tool versions and
structured outputs are retained in [frontdoor-index.json](../../../data/assets/vehicles/endurance-sedan-review/art-checkpoint-v32/frontdoor-index.json).
This repository gate does not close the separate final sedan asset or human gates.
