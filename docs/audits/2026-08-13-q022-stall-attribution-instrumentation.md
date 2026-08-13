# Q-022 stall attribution instrumentation

Date: 2026-08-13

Task: P1-013; question Q-022a

Related: [High-profile capture audit](2026-08-13-q022-high-profile-capture.md)

## Why

The balanced baseline and the High content-profile capture both recorded
steady-driving frames above the 50 ms limit whose render CPU and render GPU
components sat near 1 ms. The cost was outside the measured render path, and the
harness recorded no counter that could localise it. Repetition did not help:
three streaming runs with identical arguments produced 4, 0, and 0 events.

The owner answered Q-022a on 2026-08-13 by choosing instrumentation over further
black-box repetition.

## What was added

The reference-performance harness now samples, once per measured frame:

- .NET garbage collection counts for generations 0, 1, and 2;
- `WorldStreamer` cumulative counters for collision builds, collision removals,
  origin rebases, chunk failures, loaded chunks, and loaded environment chunks;
- whether the streamer's maximum chunk, collision, or environment build time
  advanced during that frame;
- Godot's `TimePhysicsProcess` and `TimeProcess` monitors.

Each recorded stall carries the frame-to-frame delta of those counters. The run
summary adds totals for how many stalls coincided with a garbage collection, with
streaming work, and with neither.

Design constraints observed:

- The counters are read from values the streamer already maintains. Nothing
  reaches into `WorldStreamer`, which this task does not own.
- The per-frame sample is a value struct over existing counters and allocates
  nothing, so the harness self-accounting stays honest.
- The first measured frame primes the baseline and reports no work, because a
  delta against zero would charge the whole warm-up to it.
- A rising build-time maximum shows that the frame produced the most expensive
  build so far. It cannot show that a build merely occurred.

## First observation

A 300-second streaming capture at the High profile, 91 m/s, recorded one
steady-driving stall:

| Field | Value |
| --- | ---: |
| Time into measurement | 78.8 s |
| Frame time | 52.1 ms |
| Render CPU | 0.61 ms |
| Render GPU | 0.39 ms |
| Gen0 collections that frame | 1 |
| Gen1 collections that frame | 1 |
| Gen2 collections that frame | 0 |
| Streaming work that frame | none |
| `TimeProcess` | 20.7 ms |
| `TimePhysicsProcess` | 0.98 ms |

Run totals: one stall, one coinciding with a collection, zero coinciding with
streaming work, zero with no attributable work.

## What this does and does not establish

It establishes that the instrumentation resolves a stall to named work, which the
previous captures could not do.

It does not establish a cause. This is a single event in a single run. The
counters record coincidence, not cost: they show that a Gen0 and Gen1 collection
happened in the same frame as the stall, not that the collection consumed the
frame. The 20.7 ms `TimeProcess` reading also does not account for the full
52.1 ms, and that monitor is a smoothed engine value rather than the monotonic
measurement the harness uses for frame time.

A garbage-collection hypothesis is now worth testing directly, and the earlier
High-profile matrix is consistent with it in one respect: the stalls did not
track streaming counters, whose maxima were effectively identical in runs with
five stalls and runs with none.

## Next

Re-run the High-profile matrix with this instrumentation and report the
coincidence totals across all scenarios. If collections keep coinciding, the
follow-up is allocation-rate reduction on the driving path plus a GC-mode
comparison; the 30-minute run already records 10,991 bytes allocated per rendered
frame. If a material share of stalls lands in the `with_no_attributable_work`
bucket, both leading hypotheses are wrong and the next step is an external
profiler capture triggered on a slow frame, per Q-022c.

The zero-stall threshold stays failed until a cause is found.
