# Q-022c: per-subsystem attribution by in-engine timers

Date: 2026-08-16

Task: P1-013. Closes Q-022c, the last open Q-022 question. Follows
[the Q-022 ratification](2026-08-14-q022-ratification.md).

Status: implemented and measured. It does not ratify ADR-0023 layer 2, and the
measurements below argue that layer 2 is not the interesting question.

## The decision

The owner chose in-engine per-subsystem timers over an external profiler, Godot's
built-in profiler, and deferring until traffic and weather exist.

`Cannonball.Core.Performance.SubsystemProfiler` times regions at subsystem
boundaries. A reference capture enables it; nothing else does.

## What is instrumented

| Subsystem | Boundary |
| --- | --- |
| Road | `WorldStreamer._Process` — load completion and streaming decisions |
| Route context | `WorldStreamer._PhysicsProcess` — route projection, edge and lane resolution |
| Environment | `RegionalEnvironmentChunk.Create` |
| Vehicle | `CannonballVehicle._PhysicsProcess` |
| UI | `TripMapHud._Process`, charged only while the map is open |

Traffic, effects and lighting hold layer-2 reserves but have no implementation.
They are absent rather than reported as zero, because a confident zero for a
system that does not exist reads as a measurement.

## Two design choices that were not obvious

**Exclusive time, not elapsed.** Environment chunks build inside the streamer's
road region — `_Process` reaches `RegionalEnvironmentChunk.Create` through
`CompletePendingLoads` and `AttachChunk`. Charging elapsed time to both would
report the same milliseconds twice and inflate every subsystem that contains
another. A nested region suspends its parent and resumes it on exit, so the total
is a partition of instrumented time rather than an upper bound. This was found by
tracing the call path rather than assumed: the first version of the code carried
a comment asserting the two did not nest, and that comment was wrong.

**Drain on read, not reset at frame start.** A reset that had to run before every
instrumented subsystem would depend on Godot's node processing order, and any
subsystem processed earlier in the tree than the resetter would have its time
silently discarded. Draining makes each reading self-contained. A test covers the
case where a drain falls inside a long region; the first implementation reported
zero for that region and then charged its whole span to the next interval.

## Measured, on the representative corridor

90 s at 60 m/s, 5,399 m travelled, 2.09 ms mean frame:

| Subsystem | Mean CPU | Worst frame |
| --- | ---: | ---: |
| Road | 0.0207 ms | 26.44 ms |
| Route context | 0.0130 ms | 25.24 ms |
| Environment | 0.0001 ms | 0.56 ms |
| Vehicle | 0.0355 ms | 24.76 ms |
| UI | 0 ms | 0 ms |
| **Total** | **0.0694 ms** | 27.02 ms |

Two results matter more than the numbers themselves.

**The instrumented subsystems account for about 3% of frame time.** Mean total
CPU across all five is 0.069 ms against a 2.09 ms mean frame. Whatever the frame
is spending time on, it is overwhelmingly not the layer-2 subsystems as measured
at these boundaries. Ratifying a per-subsystem millisecond split would be
ratifying a partition of 3% of the frame.

**A single worst frame charges about 25 ms to three different subsystems.** Road
26.4, route context 25.2 and vehicle 24.8 are not three independent costs; they
are one frame in which everything took about 25 ms, charged to whichever region
happened to be open. That is the signature of a suspension outside the process,
and it is consistent with the 2026-08-13 stall evidence where render CPU and GPU
were both near 1 ms inside a 50–60 ms frame.

This is a real limitation of the approach, not a defect in it: an in-process
timer cannot distinguish "this subsystem was slow" from "the process was
descheduled while this subsystem was running". Worst-frame subsystem numbers
should be read with that in mind; the means are unaffected, since such frames are
rare.

## What this does not do

- **It does not ratify layer 2.** Q-022b keeps those values as unmeasured
  reserves and this changes nothing about that. If anything it argues against
  ratifying them, because the split covers 3% of the frame.
- **It does not explain the stalls.** The evidence above says the cost is outside
  the process, which this cannot see. The idle precondition ratified for Q-022a
  addresses that from the other direction, by refusing captures taken on a
  machine that is not idle.
- **It does not split GPU time.** The capture is GPU-bound — 86% of frames in the
  proof run — and nothing here attributes that.

## Verification

- Six unit tests in `SubsystemProfilerTests` cover exclusive nesting, drain
  isolation, mid-region drains, and the disabled path. The nesting test asserts
  the property that motivated the design: the total is the sum of exclusive
  parts, not of elapsed spans.
- `./scripts/check.sh` passes; 145 C# tests.
- Three live captures on the representative corridor produced the table above.
