# The car stutter was garbage collection, not the road

Date: 2026-08-16

Task: P1-013. Supersedes the ride-quality conclusions in
[the ride-height oscillation audit](2026-08-14-ride-height-oscillation.md) and
[the grade smoothing window](2026-08-14-grade-smoothing-window.md) as an
explanation of what the owner was feeling; both remain correct about the road
profile itself.

Status: fixed and measured. Remaining allocation is recorded below.

## What was reported, and what it turned out to be

The owner reported the car bouncing while driving, "like driving over a gravel
road at high speed". Two separate defects were behind it, and neither was the one
investigated for two days.

**1. Constant high-frequency buzz — render/physics clock mismatch.** The vehicle
transform changes only on a 120 Hz physics tick. Rendering ran above 800 fps.
`physics_interpolation` was off, so the car was held for several rendered frames
and then jumped, while `ChaseCameraRig` smoothed on every rendered frame. The
camera glided, the car stepped, 120 times a second.

**2. Periodic hitches — garbage collection.** The game allocated 11.7 KB on every
rendered frame, filling gen0 roughly every two seconds. Each collection stalled a
frame for 30 to 40 ms.

## How it was found, after several wrong turns

Every metric collected over two days sampled *physics state*: ride-height
peak-to-peak and standard deviation, road roughness, mesh tessellation, tyre
envelopment. Changes were measured that moved those numbers substantially — mesh
density cut peak-to-peak 36%, a 400 m grading window cut standard deviation 60% —
**and the owner reported no perceptible difference from any of them.**

That mismatch was the finding, and it was treated as noise for too long. A
measured 2 to 6 mm of chassis motion against a report of an obviously bad ride is
not a small discrepancy to be refined away; it means the instrument is pointed at
the wrong thing. Defect 1 is invisible to physics sampling by construction,
because it is a rendering artefact.

What broke the deadlock was the owner's suggestion: a key that marks the frame
where the problem is seen. Marks were correlated against a rolling buffer of the
preceding 1.5 seconds, since a person presses after noticing.

| | |
| --- | ---: |
| Frames over 20 ms in the covered run | 49 |
| Operator marks | 53 |
| Spike rate | one per 1.53 s |
| Mark rate | one per 1.70 s |
| Marks whose window contained a spike | 52 of 53 |

One run converted "I still see it" into a correlated signal.

## Why the pauses were long enough to see

Recording the work behind those frames showed 32 of 44 coincided with a
gen0 + gen1 collection and **none** with streaming or chunk work.

The important detail is that `gen0` and `gen1` collection counts were *identical*
in every run. Every collection was promoting. That is the signature of
**finalizable objects**: Godot's C# wrappers carry finalizers, so a
`Godot.Collections.Dictionary` returned by `IntersectRay` cannot die in the
nursery — it is queued for finalization and promoted by construction.

This is why nursery tuning could not fix it, and it is the single most useful
thing learned here.

## Fixes, in order of effect

| Change | Allocation per frame | gen0 | Frames over 20 ms | Worst frame |
| --- | ---: | ---: | ---: | ---: |
| baseline | 11,730 B | 32 | 44 | 63.0 ms |
| desired-chunk set gated by distance | 7,907 B | 25 | 27 | 74.5 ms |
| HUD text rebuilt at 20 Hz, not 827 Hz | 7,571 B | 24 | 23 | — |
| automation state gated on PlayGodot | 4,707 B | 14 | 14 | — |
| remaining automation writers gated | 2,127 B | 9 | 10 | 39.7 ms |
| gen0 budget fixed at 8 MB | 2,008 B | 17 | 1 | 24.5 ms |
| persistent `RayCast3D` suspension | 1,563 B | 14 | **0** | **17.3 ms** |
| lane geometry cached per edge | 1,398 B | 13 | 2 | 22.8 ms |

**87% less garbage and no frame over 20 ms in a measured minute.**

The largest single source was `ChaseCameraRig` rebuilding a 20-entry automation
dictionary every rendered frame — 3,072 B/frame. Only `addons/playgodot/server.gd`
reads that state, and it is absent unless the process was launched for PlayGodot.

The suspension was the most instructive: `space.IntersectRay` allocated a
Dictionary and a query object four times per physics tick, 480 finalizable
objects a second. Persistent `RayCast3D` nodes allocate nothing per query and cut
vehicle allocation from 449 B/frame to 11 B.

## A correction worth recording

A larger nursery was predicted to be nearly free, on the reasoning that gen0 cost
scales with survivors rather than with garbage. Measured at 64 MB it was not: two
collections instead of nine, but a **116 ms** worst frame against 39.7 ms. The
owner's independent report — that the big collections felt worse even though
rarer — matched the measurement.

The reasoning failed precisely because of the promotion described above. With
everything surviving the nursery, a bigger nursery means more to promote.
8 MB was measured best; 64 MB and the dynamic default were both worse.

## Enforcement

`scripts/check_frame_allocations.py`, wired into `scripts/check.sh`, fails the
build when a known finalizable-Godot-object allocation appears inside `_Process`
or `_PhysicsProcess`. Suppress with `// frame-alloc-ok: <reason>`; a reason is
required.

Its limits are deliberate. It matches a literal list of call shapes and does not
follow a call graph, so allocation inside a helper called from `_Process` is not
caught. That gap is covered from the other side: reference captures now report
allocation per subsystem, so an unattributed rise is visible even when the shape
is novel.

## Instrumentation added

- Ride height per physics frame, with peak-to-peak and standard deviation.
- Road holding: cross-track error and a count of teleports back onto the route.
  A run with a non-zero reset count is not the steady drive its other metrics
  describe.
- Operator marks on **F8**, dumping the preceding 1.5 seconds of per-frame trace.
- Allocation attributed per subsystem at the same region boundaries as CPU time.
- `CANNONBALL_STALL_THRESHOLD_MS` lowers the stall *recording* threshold for
  diagnosis. Acceptance stays at the ADR-0023 value of 50 ms.

## Open, and owned by the owner

**The 50 ms stall threshold is too high to catch what is visible.** Every frame
the owner marked was between 8 and 46 ms; the gate reported zero stalls for a run
marked 53 times. Against a 1 ms median frame, a 30 ms frame is a 30x spike. The
owner also perceived 8 to 16 ms frames as smaller bumps. Changing an ADR-0023
acceptance threshold is an owner decision and is not taken here.

**Remaining allocation is about 1,400 B/frame**, split roughly 368 B in
orchestration, 299 B in route context, 157 B in road streaming, 96 B in the
camera, and 465 B outside any instrumented region.

`LaneGeometryProfile.Evaluate` was the last large single source: it rebuilt an
edge's aligned layouts and transitions on every call, from the physics tick, when
both depend only on the immutable edge. Caching them per edge through a weak table
cut route-context allocation 42%.

**A limit of these measurements, found while chasing the last of it.**
`Main._Process` skips `UpdateRunAutomationState` while a reference capture is
measuring, so the capture does not exercise the same path as normal play and
under-reports allocation relative to it. Gating that state on PlayGodot is a real
saving in gameplay that no capture number here can show. Any future allocation
work should confirm the path under measurement is the path that ships.

**Exported builds do not get the nursery setting.** `scripts/godot.sh` sets it
for every repo-driven run, but an exported build never runs that script, so a
player sees the default behaviour these captures no longer measure. Tracked as
**P1-014**.

**The GC configuration is not yet shipped.** The 8 MB nursery was set through
`DOTNET_GCgen0size` for measurement. Where that belongs for a shipped build - the
launcher, or a runtimeconfig template - is undecided.
