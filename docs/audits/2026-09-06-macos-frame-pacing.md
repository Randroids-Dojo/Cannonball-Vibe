# Mac camera jitter and runtime allocation

Date: 2026-09-06. Task: P1-015. Reference budgets: ADR-0023.

The Mac had the previous stutter fixes, but its camera still mixed physics and
display transforms. New input and route-query allocations also filled the managed
heap during ordinary play. Neither finding establishes a need to replace C# or
Godot. The owner confirms the PC is performant; exact PC revision was requested
but was not available during these measurements.

## Version and art comparison

The original Mac assembly's informational version is
`1.0.0+308a13afed5e14ede734b664e963c76aefd9ff62`. The August fixes are ancestors of
that revision and remain present: physics interpolation, persistent suspension
RayCast3D nodes, camera rebase shifts, throttled HUD updates, gated automation
state, desired-chunk refresh gating, and the lane-layout cache. The running
process also had `DOTNET_GCgen0size=800000` (8 MiB), confirmed by its environment
and runtime counter. The export-launcher gap in P1-014 does not explain this run.

The committed Hero GT body is navy. The Mac's uncommitted material is red and
changes the material shader metadata from `car_paint` to `clearcoat`, with a
Metal016 texture. Both materials were measured on the Mac. The original checkout
and its art changes were preserved; the performance branch does not ship an art
change.

The original session also used an older route package (`be597d8f…`) whose locked
source metadata and elevations differ from a fresh representative-corridor build
(`a88eb43c…`). Every paired capture here uses the same freshly built package.
Live-session traces are diagnostic evidence, not an interchangeable benchmark
baseline for the fresh captures.

## Findings and changes

1. `DrivingInputController.ReadRaw` repeatedly converted string literals to
   finalizable Godot StringName wrappers. Cameras and other input consumers did
   the same. Input action handles are now cached for the process lifetime.
2. Steady lane queries repeatedly sorted lanes, built bounds arrays, and allocated
   result objects. Immutable aligned layouts now retain ordered read-only lane
   views and bounds; distance-specific samples are value types. Route and lane
   selection use bounded scans or binary search. Streaming projection and pose
   lookup preserve selection order without temporary collections.
3. The chase camera followed `GlobalPosition` in `_Process`, then inherited
   automatic physics interpolation. It now follows
   `GetGlobalTransformInterpolated()` and disables interpolation of its own
   render-frame transform. Cockpit look/stabilization explicitly composes the displayed mount pose with
   look rotation, while preserving the vehicle-local hierarchy.
4. Reference autopilot captures previously bypassed normal input polling. They
   now sample that path, while autopilot still supplies deterministic controls.
   The configuration records this, actual CLR version, interpolation, and GC
   environment. Total CLR pause duration is measured without attaching a trace.
5. The input-allocation check now inspects polling helpers as well as callbacks.
   A portable watchdog replaces the capture script's unavailable GNU `timeout`
   dependency on this Mac. Missing Metal GPU timestamps are explicitly unknown,
   rather than being misclassified as evidence of a CPU bottleneck.

The allocation trace attributed 23.7% of sampled bytes to `ReadRaw`, 15.9% to
lane sample construction, and 10.0% to cockpit camera processing. A separate
low-overhead CLR trace recorded pauses of 16.518, 12.303, 16.551, and 11.682 ms.
The verbose allocation trace itself distorted latency and is not used as a
gameplay frame-time baseline. Stack weights are sampling estimates.

## Motion regression

`CameraInterpolationProbe` drives the actual chase rig at a constant 50 m/s,
20 physics ticks/s, and 120 render frames/s. After a three-second settling window,
360 samples measure the displayed camera-target offset. This deliberately
exaggerates the clock mismatch; it is not a claim that normal driving oscillated
by the same distance.

| Code | Relative offset oscillation | 2 cm limit |
| --- | ---: | --- |
| Previous camera | 0.428040 m | Fail |
| Corrected chase camera | 0.000137 m | Pass |
| Intermediate cockpit change, actual render transform | 2.083344 m | Fail |
| Corrected cockpit camera | 0.000000 m | Pass |

The final probe reads `Camera3D.GetCameraTransform()`, the transform used by the
renderer. A preliminary cockpit check using `GetGlobalTransformInterpolated()`
masked a position regression: interpolation disabled on a child also leaves its
parent-derived global position un-interpolated. Explicitly composing the displayed
mount with look rotation fixes that. The original chase camera was retested with
the corrected probe and still oscillated by 0.428040 m.

The new probe runs in `scripts/check.sh`. Core tests also enforce zero allocation
for warmed steady lane/section queries and route-span lookup, while existing
geometry and boundary tests exercise transitions. Camera handling and real input
scenarios remain separate checks; this probe cannot approve driving enjoyment.

## Rendered measurements

Results and exact commands are recorded in `evidence/M5/P1-015.json` and the local
`reports/mac-performance/` artifacts. Captures use the official Godot 4.7.1 .NET
engine, optimized Release game assemblies, Forward+ with native Metal, 120 Hz
physics, 2560x1440 High, a chase camera, 50 m/s autopilot with normal input sampling,
and 20 seconds of discarded warm-up. No visual quality tier was reduced.

The machine is an Apple M4 Max with 40 GPU cores and 128 GB RAM. Its original game
process was suspended only while each capture ran, then resumed. Other desktop
applications remained open. NVIDIA-only contention sampling is unavailable on
Apple Silicon; captures are explicitly diagnostic, not clean-machine Windows
reference acceptance. GPU time returned zero on Metal, so no measured CPU/GPU
bottleneck split is claimed. Frame intervals use Godot's monotonic clock, not an
OS presentation trace. One blue after-capture included Computer Use observation.

| Night capture | Mean FPS | p95 ms | p99 ms | Max ms | Frames >20 ms | Game bytes/frame | Total GC pause ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Before, red / 60 s | 122.3 | 11.35 | 14.88 | 18.14 | 0 | 6244 | 40.24 |
| Before, red / 120 s | 124.9 | 11.49 | 15.47 | 20.45 | 1 | 6051 | 76.48 |
| Before, blue / 60 s | 125.5 | 12.12 | 15.35 | 20.67 | 1 | 6159 | 44.49 |
| Camera + allocation fixes, blue / 60 s | 123.1 | 12.36 | 15.21 | 20.30 | 1 | 1667 | 3.75 |
| Camera + allocation fixes, red / 60 s | 116.1 | 12.08 | 15.71 | 18.76 | 0 | 1744 | 2.33 |
| Final tree fade, red / 120 s | 117.4 | 12.67 | 14.97 | 23.30 | 4 | 1557 | 4.77 |
| Final tree fade + V-Sync, red / 120 s | 109.3 | 12.50 | 14.74 | 19.46 | 0 | 1643 | 5.06 |
| Final cockpit correction + V-Sync, red / 120 s | 101.2 | 14.51 | 17.27 | 23.92 | 21 | 1741 | 2.14 |
| Integrated off-road ground + V-Sync, red / 120 s | 96.8 | 15.53 | 18.68 | 25.64 | 53 | 1828 | 4.09 |
| Integrated + V-Sync + 60 FPS cap, red / 60 s | 59.8 | 18.91 | 20.06 | 23.99 | 41 | 2907 | 2.19 |

The two-minute uncapped comparison reduced game allocation per frame by 74.3%
and total GC pause duration by 93.8%. It did not improve every frame percentile:
the previous camera could visibly oscillate even when frame percentiles passed.
The motion probe and the owner report establish that separate correction.

All captures without a manual FPS cap met the diagnostic p95 <=16.67 ms and
p99 <=20 ms comparisons.
The final uncapped tree capture had four 21.0-23.3 ms frames, so its zero-stall
comparison failed. None coincided with a GC, rebase, chunk attachment, or recorded
streaming build. The initial V-Sync capture had no >20 ms frame over two
minutes. The final cockpit-correction capture had 21 frames above 20 ms, up to
23.924 ms, despite only 2.141 ms of GC pause over the entire two minutes. None
of those frames coincided with GC or recorded streaming work. The variability
does not establish a cockpit GPU regression or a fix for all presentation stalls;
GPU timing and desktop contention remain unknown. The zero-stall target is open.
V-Sync was requested and reported enabled; these are engine frame intervals,
not direct display-present timestamps. No global V-Sync default was changed.

Mean draw calls in the paired two-minute uncapped runs changed from 1,386 to
1,394 (0.5%). The fade adds bounded overlap at LOD boundaries. Both runs retain
High quality, 9 shared environment materials, and all tree placements. GPU timing
is unavailable, so the exact GPU cost of this overlap is not isolated.


## Research and architecture recommendation

The camera correction follows Godot's documented manual camera interpolation
model: follow the displayed target and avoid automatic interpolation of a camera
already moved each render frame. Enabling project-wide interpolation alone does
not fix a manually smoothed camera reading physics transforms.
[Godot camera interpolation](https://docs.godotengine.org/en/stable/tutorials/physics/interpolation/advanced_physics_interpolation.html).

Godot's C# guidance calls out native interop and repeated string conversions;
its CPU optimization guidance supports reducing allocation and selectively moving
measured CPU work to native code. The engine's rendering and physics already run
in native code. A whole-game C++ rewrite would not correct this camera algorithm
or eliminate a GPU/presentation bottleneck. Keep the selected stack; consider a
bounded GDExtension only if a remaining measured managed subsystem exceeds its
budget after optimization.
[C# interop](https://docs.godotengine.org/en/stable/tutorials/scripting/c_sharp/c_sharp_basics.html),
[CPU optimization](https://docs.godotengine.org/en/stable/tutorials/performance/cpu_optimization.html),
[GDExtension](https://docs.godotengine.org/en/stable/tutorials/scripting/cpp/about_godot_cpp.html).

An open upstream report describes unstable uncapped Metal presentation on macOS
26 and improvement with V-Sync. It is a reason to compare presentation modes,
not proof that every remaining frame here has that cause. The missing Metal GPU
timestamps also have an upstream report and were independently observed here.
[macOS uncapped presentation report](https://github.com/godotengine/godot/issues/110600),
[Metal timing report](https://github.com/godotengine/godot/issues/102968).

This task does not close P1-013's unfinished production-content/long-duration
budgets, P1-014's exported GC configuration, minimum hardware specification, or
the owner's handling and enjoyment gates. Any remaining frame-budget failures
stay visible in the evidence.

## Tree transitions requested during review

After seeing the updated run, the owner reported: "Looks way smoother" and then
identified obvious tree LOD pop-in. This is confirmation of improved motion,
not the separate 30-minute handling/enjoyment approval.

Tree groups previously used instantaneous visibility switches with 12 m
hysteresis. The Forward+ path now transitions across a 60 m band (30 m on either
side of each existing threshold). All three LODs use the same bounding box so
their distance tests agree despite different silhouettes. Positions, density,
three-level instancing, and the LOD distances remain unchanged.

The needle shader previously overwrote incoming ALPHA, including the renderer's
visibility fade. It and the impostor now preserve fade as dithered pixel coverage
before applying the texture's cutout mask. Adjacent LODs use complementary
patterns through one parameter per MultiMesh; materials remain shared. The native
renderer owns fade progression, with no C# update loop. The Compatibility/Mobile
paths retain hysteresis because native range fading requires Forward+.
[Godot visibility ranges](https://docs.godotengine.org/en/stable/tutorials/3d/visibility_ranges.html).

The initial native-fade-only experiment is retained separately; its frame metrics
are not evidence that cutout foliage faded correctly. The final shader version
is identified explicitly in the evidence and receives fresh rendered captures.

A small rendered diagnostic uses both production foliage shaders on a MultiMesh
card, keeping its screen area constant with an orthographic camera. Native range
fading produces visible coverage of 100%, 84.3%, 49.9%, 15.3%, and 0% at five
positions across the band. Both dither polarities pass. The first diagnostic
incorrectly expected linear opacity; it was corrected against the official
Forward+ smoothstep curve, with the initial failure retained. This verifies
actual shader fade behavior, not the owner's subjective judgment of the whole
forest transition.
[Forward+ fade calculation](https://github.com/godotengine/godot/blob/4.7/servers/rendering/renderer_rd/forward_clustered/render_forward_clustered.cpp#L978-L992).

## Validation and packaging corrections

The full Mac front door passed: 146 C# tests, 279 pipeline/script tests, 13
PlayGodot unit tests, the official corridor smoke, and the new camera probe.
The rendered PlayGodot suite passed all 28 before the final cockpit correction.
The final full run passed 27 and missed a controller camera-toggle press; that
scenario passed unchanged on an isolated retry. Both artifacts are retained.
The helper holds the button for 30 ms, but the precise cause of this missed event
is unproven. Final remote suite results are recorded separately. Camera handling
passed all six stages, including collision recovery, rebase, reset, and mode
switches. The environment scenario passed five stages across four regions,
with zero terrain seam error and no added collision budget.

The first implementation CI exposed two integration errors: Python on Windows
cannot directly execute a `.sh` file, and all-resources exports included the new
camera test scene. The first correction resolved bare `bash` to the Windows WSL stub. Watchdog
callers now use the current Bash executable via `$BASH`, and all
export presets exclude `game/Automation` resources. The existing PCK inspection
remains unchanged; a local export passes it after the exclusion. Remote results
and recovery runs are recorded in the task evidence. These corrections do not
change the measured gameplay implementation.

The final performance implementation `9dbc526` passed Linux and Windows M0,
all three platform PlayGodot suites, both deterministic 500-mile suites, the asset
pipeline, reproducible unsigned exports, and Linux/Windows clean-machine smokes.
Mainline `5135062` added off-road collision and recovery while this work was in
progress. It is merged into the performance branch and receives an additional
Mac gate and capture; these integrated measurements are labeled separately from
the paired allocation comparison.

A new mainline health issue (#134) recorded a separate hostile-request test
`ui.describe` timeout after reconnecting. That helper retains a 1-second request
timeout. The failed job was rerun without changing assertions to assess whether
the failure reproduces. A passing retry would recover the health signal, not
establish a durable repair of the test's scheduling sensitivity.

The integrated `c978d8b` run averaged 96.8 FPS with p95 15.53 ms and p99 18.68 ms.
It recorded 53 frames above 20 ms (25.64 ms maximum), so it also fails zero-stall
acceptance. It had only 4.09 ms total GC pause and no failed chunks. Collision
build high-water reached 17.84 ms. The off-road additions and desktop variability
are not separated by these captures; no causal claim is made from the sequence.
`pmset` reports AC power, a charged battery, and no recorded thermal/performance
warning, but does not supply GPU clocks or prove absence of GPU throttling.

Mainline issue #134's failed Mac job passed on retry (run 34067043259, attempt 2),
and the health issue cleared. The reconnect/request timing concern remains in
this audit; no authentication assertions or deadlines were changed to recover it.

A final presentation experiment requested the existing 60 FPS cap with V-Sync.
It averaged 59.83 FPS, with p99 20.06 ms and 41 >20 ms frames in one minute. It
fails cap adherence, p99, and zero-stall comparisons, so it is not adopted as a
Mac default. The uncapped presentation mode, original quality settings, and all
unsuccessful experiments remain visible in the evidence. The camera and tree
transition defects are corrected; remaining presentation outliers require further
profiling under P1-013 rather than an unsupported C++ rewrite.

The combined `c978d8b` implementation also passed all remote checks: Linux and
Windows M0, PlayGodot on Linux/Windows/macOS, both deterministic 500-mile jobs,
assets, unsigned fixture exports, and both clean-machine smokes. The full local
gate and all six off-road ground probes passed on the combined source.
