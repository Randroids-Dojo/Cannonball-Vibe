# Q-022 ratification: what the owner decided and what changed

Date: 2026-08-14

Task: P1-013; closes Q-022a, Q-022b, Q-022d and Q-022e from
[the High-profile handoff](../QUESTIONS_FOR_RANDROID_2026-08-13_Q022_HIGH_PROFILE.md).
Recorded in [ADR-0023](../decisions/ADR-0023-reference-performance-target-and-layered-budgets.md)'s
2026-08-14 addendum, which is the authority; this audit records the evidence and
the implementation.

Q-022c remains open.

## Q-022a — captures are gated on an idle machine

The owner chose to gate machine state and re-measure, rather than accept the
clean repeat or relax the limit.

`scripts/capture-reference-performance.sh` now refuses to publish a capture that
did not start idle or that saw a new GPU client arrive while it ran.
`--allow-contended` records it as contended evidence instead, and says so in the
run output.

The criterion, in `record_machine_state.py`:

- GPU utilisation at or below 10% immediately before the capture,
- no capture process already holding a GPU context,
- no GPU client count above the pre-run baseline plus one at any point during the
  measurement.

**The zero-stall threshold is not declared passed by any of this.** It remains
failed until a matrix that satisfies the precondition records no stall. This
changes what counts as a measurement, not what counts as a pass.

### Two corrections found by running it rather than reasoning about it

**GPU memory utilisation was in the first criterion and had to come out.** The
first real capture was refused because `utilization.memory` read 16%. That field
is the fraction of the sample period in which device memory was accessed, not
memory occupancy or contention; an idle desktop compositor holds it in the mid
teens. Gating on it refused every capture on an interactive machine while saying
nothing about whether another process was doing sustained GPU work. It is still
recorded. `test_memory_bandwidth_activity_alone_is_not_contention` pins the
behaviour.

**The GPU needs time to settle between scenarios.** A capture immediately after
another was refused at 11% utilisation. A matrix runs nine scenarios back to
back, so without a settle wait the precondition would have measured recency
rather than idleness and refused most of a matrix. There is now a bounded wait —
60 seconds by default, `CANNONBALL_GPU_SETTLE_SECONDS` — after which a machine
that has not settled is reported and assessed as it stands. Waiting cannot mask
real contention, because a genuinely busy machine never settles.

### Why during-run sampling, not just brackets

The samples that existed bracketed the capture. The run that motivated all of
this — mean render GPU time about ten times its siblings at identical arguments —
would not have been caught by brackets if whatever caused it had gone by the time
the run ended. Sampling now runs throughout at 2 s intervals.

Utilisation during the run cannot separate contention from the capture's own
work, since the capture is meant to load the GPU. Client count can: the capture
adds at most one client to the baseline, so a sample above that is a process that
arrived mid-measurement.

A limit worth recording: on this Windows machine `nvidia-smi
--query-compute-apps` reports 35 clients at idle and does not list the capture
itself, because Godot is a graphics client rather than a compute one. The
during-run test is therefore looking for an increase against a large, noisy
baseline. It will catch a new client; it will not attribute one.

## Q-022b — layer 2 is reserves, not measurements

The subsystem millisecond values are labelled unmeasured reserves. Nothing gates
on them, and no automation may cite them as measured.

The evidence is that the balanced-versus-High comparison showed no measurable
percentile difference, so a per-subsystem split derived from it would be derived
from noise. Layer-3 content-class caps are unaffected and remain gateable,
because they are counted rather than inferred.

## Q-022d — the sustained-growth constants are ratified

Slope above 1 MiB/min **and** R² at or above 0.5 over a 30-minute steady-state
run. `criterion_status` in the emitted acceptance changes from
`"proposed operationalisation awaiting Q-022 ratification"` to
`"ratified 2026-08-14 (ADR-0023 Q-022d)"`.

Statements of the form "30-minute growth passed" now mean a ratified requirement
was met. Audits written before this date meant only that a proposed rule was met
and are qualified accordingly; they are not retroactively upgraded.

## Q-022e — capped runs are judged on cap adherence

A frame-capped run is judged on holding the cap: mean FPS within 0.1 of the cap,
p50 within 0.1 ms of the cap period, and no stall above 50 ms. The 16.67 ms p95
limit is not applicable to a capped run.

Verified by running both paths:

| Run | `p95_frame_ms` | `cap_adherence` |
| --- | --- | --- |
| uncapped, 12 s | PASS (1.30 ms measured) | NOT_APPLICABLE |
| capped 60 FPS, V-Sync on, 30 s | NOT_APPLICABLE (16.9025 ms measured) | PASS |

The capped run recorded 60.039 mean FPS and a 16.6575 ms p50 against a
16.6667 ms cap period, with zero stalls. Under the previous rule that same run
reported `p95_frame_ms` as **failed** at 16.9025 ms — a build holding the cap
almost exactly, marked as failing.

`passed` is now **absent** from `p95_frame_ms` on a capped run rather than set to
true. A consumer that reads `passed` without checking `applicable` would
otherwise report a capped run as having passed a limit that was never evaluated.
The threshold reporter prints `NOT_APPLICABLE` for such entries instead of
inventing a verdict.

An engine frame cap is still not a 60 Hz output mode; the reference panel runs at
120 Hz and a true output-mode check would need a display mode change.

## What remains open

- **Q-022c**, per-subsystem attribution. This is what would let layer 2 be
  ratified as measurements.
- **The zero-stall threshold**, which stays failed until a matrix passing the
  idle precondition records no stall. That matrix has not been run.
- **P1-013** cannot complete regardless, because traffic and weather do not
  exist and ADR-0023 requires representative content in those scenarios before
  production budgets are ratified.
