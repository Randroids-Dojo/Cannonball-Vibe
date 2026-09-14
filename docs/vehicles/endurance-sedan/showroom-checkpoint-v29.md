# P1-018 interactive showroom checkpoint

The showroom provides full orbit, pan and zoom, eleven exterior/compartment
viewpoints, automatic turntable, and independent operation of all four doors,
hood and trunk. It includes studio/daylight/night lighting, headlights, hazards,
wipers, and UI-free photos of the actual car viewport. The interface and
procedural studio are original. It displays the installed production34 vehicle.

The dedicated scene is `game/Vehicle/Showroom/VehicleShowroom.tscn`. During a
drive, stop, press **F2**, and choose **Explore in showroom**. Its private display
world pauses the run; closing returns to the existing parked inspection panel.
See [launch and controls](README.md#select-and-drive) and the
[scope declared before implementation](showroom-plan.md).

## Verified Windows result

The final unchanged `scripts/check.sh` front door passed all thirteen steps on
2026-09-13 UTC. Tool checks verified official Godot 4.7.1 .NET `a13da4feb`,
.NET SDK 10.0.102, uv 0.9.24 and Git LFS 3.7.1. The viewer source inputs stayed
byte-identical through that check.

The complete rendered interaction sequence passed in Compatibility at
1280×720 and Forward+ at 2560×1440. It exercises all six actual hinge angles,
eleven views, keyboard/controller controls, photo files, modal enter/return,
reopen, and suppression of held driving input. The original run's measured
route, body, presentation and elapsed time remain unchanged while the viewer
is open. The separate unmodified sedan → Hero GT → graybox → sedan regression
also passed. Later focused Forward+ comparisons verify the final lighting,
bounded photo notice and downward cockpit framing.

Independent QA inspected actual screenshots and photo files. The final
1280×720 full-UI cockpit shows the entire steering wheel above the lower
controls. The 2560×1440 cockpit photo is UI-free: its full-UI screenshot exceeds
the existing RPC PNG size limit. This distinction also applies to five
full-sequence photo recoveries; they are not full-UI layout evidence. The
returned-driving screenshot in that Forward+ sequence was unavailable after
the same limit, while its numeric return checks passed. Earlier actual
Compatibility return imagery remains separately retained.

An actual Windows cleanup failure was traced to long generated shader-cache
paths. The launcher now uses extended absolute Windows paths for its owned
disposable profile, preserving strict error reporting, containment checks and
the existing deadline. All 129 launcher/client controls pass. Subsequent actual
native processes exit zero, reach EOF and complete cleanup; the original
failed profile and failure records are preserved.

## Limits and continuing work

Night lighting now gives more body definition, but broad black panels remain
poor for close inspection. Strong lamp/window reflections and existing vehicle
form/material defects remain open. The newer Blender repairs are separate
unexported candidates. This checkpoint does not approve their geometry or art.

Actual mouse drag/wheel, focus loss and live window resize have not received
black-box verification. The configured native Computer Use pipe was unavailable;
the existing semantic drag helper does not supply the relative motion consumed
by this viewer. Keyboard/controller tests are distinct evidence. Human
comprehension/accessibility and final visual review remain pending.

The 1440p full sequence retained fourteen short diagnostic metrics windows:
frame p95 17.62–18.03 ms, sampled process working-set highs 921.5–934.9 MiB,
render-video highs 590.6–609.0 MiB and 83–157 private-viewport draws. These
include the debug observer, VSync and concurrent user applications. They do not
measure GPU execution time or establish a reference-PC performance pass.
The separate proposed 60 FPS showroom budget remains Q-047; the driving budget
and starter/validation speed policies are unchanged.

The retained index is
[`showroom-checkpoint-v29/index.json`](../../../data/assets/vehicles/endurance-sedan-review/showroom-checkpoint-v29/index.json).
Its archive member paths reproduce the original reports, failed attempts,
source snapshots, exact hashes and commands. `evidence/M5/P1-018.json` is the
structured task record. Remote platform evidence for this revision and all
required human gates remain separate. P1-018 stays `in_progress`; PR #144 stays
a draft while known asset defects are repaired.
