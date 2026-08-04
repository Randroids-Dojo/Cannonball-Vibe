# Q-022 reference Windows performance capture

Date: 2026-08-03
Task: Q-022 (blocking M5); related P1-008, P1-009, P1-010, P0-015
Evidence: `evidence/M5/Q-022-reference-windows-capture.json`
Handoff: [Q-022 ratification handoff](../QUESTIONS_FOR_RANDROID_2026-08-03_Q022_REFERENCE_CAPTURE.md)

This is the first representative production-content performance capture on the
declared reference PC. It moves Q-022 from "thresholds ratified, unmeasured" to
"measured, with derived allocations proposed." **Q-022 remains open.**

## Result in one line

Five of the six ADR-0023 provisional thresholds pass with 9–11× headroom. The
sustained-memory-growth threshold **fails** on the 30-minute run at 1.87 MiB/min
(R² = 0.79, +57.7 MiB, entirely CPU-side).

## Hardware

Verified against the [declared reference machine](2026-07-23-reference-windows-hardware.md);
every attribute matches.

| Attribute | Declared | Observed |
| --- | --- | --- |
| OS | Windows 11 Pro | Microsoft Windows 11 Pro 10.0.26200 |
| CPU | Ryzen 9 5900X 12C/24T | AMD Ryzen 9 5900X, 12 cores / 24 threads |
| GPU | RTX 3080 Ti 12 GB | NVIDIA GeForce RTX 3080 Ti, 12288 MiB |
| Memory | 64 GB | 63.9 GB |
| GPU driver | — | 610.88, VBIOS 94.02.71.80.79 |
| Renderer | Forward+ | Forward+, Vulkan 1.4.341 |

## Workspace and toolchain

Per the ADR-0023 operating addendum, the capture ran from a **fresh clean
worktree** created for this work, not a long-lived gameplay worktree.

- Commit: `7561114427f0348f6cd8f761d1c006f7d1e77e45` (`origin/main`)
- Branch: `agent/q022-reference-windows-capture-20260803`
- `git status --porcelain` when the worktree was created: empty

The worktree was **not** byte-clean at the moment of measurement, and claiming
otherwise would be false. No reference-performance harness existed at the pinned
commit, so it had to be added before anything could be measured. The only
modifications present during capture were the harness itself
(`game/Automation/ReferencePerformanceScenario.cs`, the `Main.cs` wiring, and
`scripts/capture-reference-performance.sh`) plus the documentation deliverables.
What the ADR-0023 addendum guards against — a long-lived dirty gameplay worktree
or stale generated output contaminating a measurement — did not occur: the
worktree is outside any gameplay checkout, and every route package was rebuilt
from checksum-locked fixture sources at the start of every run.
- `scripts/doctor.sh`: all five pins passed — Godot `4.7.1.stable.mono.official.a13da4feb`,
  .NET SDK `10.0.102`, uv `0.9.24`, Git LFS `3.7.1`, perl available

Input artifact SHA-256 values are recorded in the evidence JSON.

## Measurement method

`scripts/capture-reference-performance.sh` drives a windowed, rendered session.
It deliberately does **not** pass `--headless`: the existing `scripts/run-scenario.sh`
runs headless with `gl_compatibility`, which cannot measure presented-frame time,
GPU attribution, or video memory on the native adapter.

| Setting | Value |
| --- | --- |
| Window / 3D render size | 2560×1440 |
| 2D content-scale reference | 1920×1080 (`canvas_items` stretch; 2D only) |
| Rendering method | `forward_plus` |
| V-Sync | disabled |
| `Engine.MaxFps` | 0 (uncapped) |
| Physics | 120 Hz, `physics_jitter_fix` 0.5 |
| Display | 5120×1440 desktop at 119.999 Hz |
| Content | integrated visual slice — production Hero GT, production highway kit, balanced regional environment, `representative-corridor` fixture |
| Warm-up | discarded; ends only once driving on settled visual and environment streaming |

**V-Sync disabled and an uncapped frame rate are a measurement-method choice, not
ratified policy.** They exist so presented-frame time can exceed the 119 Hz refresh
interval and reveal headroom. They are not how a player will run the game; a
V-Sync-on presentation check is proposed as follow-up in the handoff.

Driver-level state at capture time, recorded as observed rather than interpreted:

| Item | State |
| --- | --- |
| HAGS (`HwSchMode`) | registry value not set (OS default) |
| Game Mode (`AutoGameModeEnabled`) | not set |
| Game DVR (`GameDVR_Enabled`) | 1 |
| Game DVR app capture | not set |
| NVIDIA ShadowPlay overlay | not set |
| Driver frame limiter | none configured; an uncapped run presented 1,029 FPS, which no limiter would permit |

### Why 3D renders at 2560×1440

`GetVisibleRect()` on the root viewport returns 1920×1080. That is the 2D
content-scale reference under `canvas_items` stretch, not the 3D render size.
A resolution-scaling experiment on the same binary confirms the 3D render target
follows the window:

| Window | Mean render GPU ms | Pixel ratio | GPU-time ratio |
| --- | --- | --- | --- |
| 1280×720 | 0.2445 | 1.00 | 1.00 |
| 2560×1440 | 0.4106 | 4.00 | 1.68 |
| 3840×2160 | 0.7916 | 9.00 | 3.24 |

GPU cost tracks window size. The sublinearity shows the scene is not
fill-rate-bound — a large fixed per-frame cost dominates. A `GetTexture().GetSize()`
probe returned values that could not be validated and was removed rather than
published.

### Two harness defects found and corrected before these numbers were taken

Both were caught by inspecting the measurement rather than trusting it, and both
materially changed the results. They are documented here because they are the
reason earlier intermediate numbers should not be reused.

1. **Smoothed frame delta.** The first implementation measured presented-frame
   time from Godot's `_Process(delta)`. Godot smooths that value against the
   120 Hz physics step, quantising it to exact subdivisions — p50/p95/p99 landed
   on precisely 1/1080, 1/840, and 1/600 s. The smoother **understated p95 by
   ~23%** (1.19 ms reported versus 1.54 ms actual). Frame time now comes from the
   `Time.GetTicksUsec()` monotonic clock. Both series are recorded in every
   capture so the discrepancy stays visible.

2. **The instrument distorted what it measured.** Sampling accumulated one
   `List<double>` entry per frame per series. Over 30 minutes that reached ~1.7M
   entries per list (~55.6 MB), repeatedly reallocating multi-megabyte arrays onto
   the Large Object Heap. It accounted for ~34% of the reported working-set growth
   and inflated stall counts through GC pauses. Sampling now uses fixed-width
   histograms and pre-sized buffers with **zero steady-state allocation**;
   measured harness share of process allocation is **0.10%**.

A third, smaller defect — starting the measurement clock before warm-up snapshot
work, charging that setup to the first measured frame as a spurious stall — was
also fixed.

## Scenario matrix

ADR-0023 names daylight, night, weather, high-speed, streaming, and
degraded-quality. Five were captured. One was not.

| Scenario | Captured | Configuration |
| --- | --- | --- |
| daylight | yes | day lighting, 40 m/s cruise, 120 s |
| night | yes | night lighting, 40 m/s cruise, 120 s |
| weather | **no** | see below |
| high-speed | yes | day lighting, 91 m/s autopilot maximum, 120 s |
| streaming | yes | 91 m/s for 300 s, corridor looping enabled to force cold route-start rebuilds |
| degraded-quality | yes | `--environment-quality=low`, 40 m/s, 120 s |
| 30-minute steady state | yes | day lighting, 40 m/s, 1800 s |

**Weather is not captured because the build has no weather system.** There is no
precipitation, wet-road, fog, or volumetric implementation in `game/`. The nearest
existing state is the `plains-weather` stage in `EnvironmentVisualScenario`, which
changes directional-light and ambient colour only. Substituting overcast lighting
for a weather capture would misreport the scenario, so it is recorded as not
captured. No ledger task currently covers a weather implementation.

The representative corridor is 24.665 km. Runs longer than one traversal enable
the existing short-corridor loop, which teleports the vehicle to the route start.
Loop wraps are timestamped and their frames are attributed separately from
steady-driving stalls rather than silently discarded.

## Whole-scene outcomes

| Scenario | Frames | Measured s | p50 ms | p95 ms | p99 ms | max ms | Steady stalls >50 ms | Mean FPS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daylight | 123,515 | 120.0 | 0.823 | 1.488 | 1.838 | 47.989 | 0 | 1,029 |
| night | 112,912 | 120.0 | 0.873 | 1.673 | 2.783 | 41.366 | 0 | 941 |
| high-speed | 112,182 | 120.0 | 0.873 | 1.833 | 2.968 | 42.010 | 0 | 935 |
| streaming | 278,933 | 300.0 | 0.888 | 1.758 | 2.868 | 44.420 | 0 | 930 |
| degraded-quality | 113,400 | 120.0 | 0.853 | 1.812 | 2.897 | 47.608 | 0 | 945 |
| steady-state-30m | 1,700,671 | 1800.0 | 0.863 | 1.748 | 2.763 | 62.924 | 0 | 945 |

The single 62.92 ms frame in the 30-minute run occurred at 0.2 m/s during a
corridor-loop teleport and is attributed to the wrap, not to steady driving.

## CPU versus GPU attribution

| Scenario | Mean frame ms | Mean render CPU ms | Mean render GPU ms | Mean non-render ms | GPU-bound frames | Render-side bound by |
| --- | --- | --- | --- | --- | --- | --- |
| daylight | 0.972 | 0.289 | 0.393 | 0.579 | 89.4% | gpu |
| night | 1.063 | 0.293 | 0.399 | 0.664 | 91.9% | gpu |
| high-speed | 1.070 | 0.297 | 0.393 | 0.677 | 87.2% | gpu |
| streaming | 1.076 | 0.313 | 0.397 | 0.678 | 85.1% | gpu |
| degraded-quality | 1.058 | 0.289 | 0.395 | 0.663 | 89.5% | gpu |
| steady-state-30m | 1.058 | 0.312 | 0.385 | 0.673 | 83.9% | gpu |

The "bound by GPU" column compares render CPU against render GPU only, and is
misleading on its own. **The largest single component of frame time is
non-render main-thread work** (0.58–0.68 ms), which exceeds render GPU time
(0.39 ms) in every scenario. Simulation, physics synchronisation, HUD update,
and garbage collection dominate, not rendering.

## Memory

| Scenario | Peak GPU MiB | Peak working set MiB | Working-set slope | R² | Peak texture MiB | Peak buffer MiB |
| --- | --- | --- | --- | --- | --- | --- |
| daylight | 177 | 729 | 9.88 MiB/min | 0.881 | 110 | 48 |
| night | 171 | 727 | 9.15 MiB/min | 0.940 | 110 | 48 |
| high-speed | 178 | 736 | 19.01 MiB/min | 0.811 | 110 | 50 |
| streaming | 175 | 739 | 4.66 MiB/min | 0.753 | 110 | 52 |
| degraded-quality | 176 | 703 | 2.31 MiB/min | 0.943 | 110 | 48 |
| steady-state-30m | 177 | 773 | **1.87 MiB/min** | 0.790 | 110 | 48 |

Short-run slopes are inflated by process warm-up (JIT, caches) and are not
comparable to the 30-minute figure; only the 30-minute run is evaluated against
the threshold.

Over the 30-minute run: working set 700.5 → 758.2 MiB (**+57.7 MiB**), managed
heap 28.3 → 34.4 MiB (+6.1 MiB), **GPU memory 175.8 → 175.8 MiB (flat)**. The
growth is CPU-side and largely *native*, not managed heap.

## Garbage collection

Measured on the 30-minute run:

| Metric | Value |
| --- | --- |
| Total allocated during measurement | 24,451,100,888 bytes |
| Attributable to the capture harness | 23,740,648 bytes (**0.10%**) |
| Attributable to the game | 24,427,360,240 bytes |
| Game allocation per rendered frame | 14,363 bytes |
| Gen0 / Gen1 / Gen2 collections | 1,475 / 1,475 / 15 |
| Gen0 rate | 0.82 per second |

This is the mechanism behind the recurring sub-threshold spike:

| Per-second worst frame, 30-minute run | Value |
| --- | --- |
| Seconds sampled | 1,798 |
| Containing a frame > 16.67 ms | 1,464 (81%) |
| Containing a frame > 30 ms | 887 |
| Containing a frame > 50 ms | 1 |
| Median / p90 / p99 / max | 29.97 / 34.49 / 45.62 / 62.92 ms |

1,475 Gen0 collections against 1,464 seconds containing a >16.67 ms spike is a
near 1:1 correspondence. The game allocates 14.4 KB per rendered frame, and the
resulting Gen0 collections produce a ~30 ms spike roughly once per second. The
harness contributes 0.10% of that allocation, so this is game and engine code.

## Streaming

| Scenario | Distance m | Max chunk build ms | Max collision build ms | Max env build ms | Rebases | Loops | Chunk failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| daylight | 4,801 | 34.011 | 2.836 | 39.068 | 5 | 0 | 0 |
| night | 4,801 | 35.067 | 2.893 | 40.525 | 5 | 0 | 0 |
| high-speed | 10,685 | 36.773 | 2.859 | 41.489 | 11 | 0 | 0 |
| streaming | 760 | 34.630 | 3.690 | 48.796 | 26 | 1 | 0 |
| degraded-quality | 4,800 | 34.566 | 3.001 | 39.738 | 5 | 0 | 0 |
| steady-state-30m | 22,597 | 34.853 | 3.180 | 40.409 | 72 | 2 | 0 |

Zero chunk failures and zero seam or collision anomalies across every scenario.
Synchronous environment construction peaked at **48.796 ms against the 50 ms
stall limit** — the closest approach to a frame-pacing threshold in the whole
capture, and the second identified risk after GC.

## Content class

| Scenario | Peak draw calls | Mean draw calls | Peak primitives | Env profile | Near/Mid/Distant instances | Road materials | Env materials |
| --- | --- | --- | --- | --- | --- | --- | --- |
| daylight | 429 | 323 | 1,330,366 | balanced | 330/132/77 | 18 | 8 |
| night | 430 | 334 | 1,332,602 | balanced | 330/132/77 | 18 | 8 |
| high-speed | 430 | 323 | 1,332,602 | balanced | 540/216/126 | 18 | 8 |
| streaming | 530 | 350 | 1,332,602 | balanced | 540/216/126 | 18 | 8 |
| degraded-quality | 428 | 322 | 1,308,438 | low | 176/77/44 | 18 | 8 |
| steady-state-30m | 525 | 349 | 1,330,366 | balanced | 300/120/70 | 18 | 8 |

Texture residency was 110 MiB and buffer residency 48–52 MiB in every scenario.
No visible pop-in was measured; the harness records LOD instance counts and
streaming settle state but does not detect pop-in, and no automated pop-in check
exists yet.

## Acceptance against the ADR-0023 provisional gate

| Scenario | p95 ≤16.67 ms | p99 ≤20 ms | no steady stall >50 ms | GPU ≤9.5 GB | Working set ≤16 GB | Sustained growth |
| --- | --- | --- | --- | --- | --- | --- |
| daylight | PASS | PASS | PASS | PASS | PASS | not evaluated (<30 min) |
| night | PASS | PASS | PASS | PASS | PASS | not evaluated (<30 min) |
| high-speed | PASS | PASS | PASS | PASS | PASS | not evaluated (<30 min) |
| streaming | PASS | PASS | PASS | PASS | PASS | not evaluated (<30 min) |
| degraded-quality | PASS | PASS | PASS | PASS | PASS | not evaluated (<30 min) |
| steady-state-30m | PASS | PASS | PASS | PASS | PASS | **FAIL** |

ADR-0023 requires "no sustained positive growth" but does not quantify it. This
capture applies a **proposed, unratified** operationalisation: a trend counts as
sustained only when slope > 1 MiB/min **and** R² ≥ 0.5, so ordinary allocator
noise cannot fail a run. The 30-minute run fails at 1.87 MiB/min with R² = 0.79.
Ratifying, adjusting, or rejecting that rule is Q-022d in the handoff.

### How comfortable are the passes?

Not very, for the stall criterion. Worst frames reached 42–48 ms against a 50 ms
limit, and 81% of measured seconds contain a frame above the 16.67 ms envelope.
Earlier matrix executions carried out with the defective harness recorded 1–5
steady stalls in the high-speed, streaming, and 30-minute scenarios. Those runs
are not evidence, but they show the criterion sits close enough to the boundary
that its outcome varies between runs. **The no-stall pass should be read as
marginal, not comfortable.**

The percentile and memory-ceiling passes are genuinely comfortable: 9–11×
frame-time headroom and roughly 1.9% of the GPU-memory ceiling.

## Derived budget proposals — all provisional

### Layer 2, subsystem allocations: cannot be derived from this capture

Two subsystem isolations were attempted by difference:

| Comparison | Mean render GPU ms | Delta |
| --- | --- | --- |
| balanced environment (daylight) vs low environment (degraded-quality) | 0.393 vs 0.395 | +0.002 |
| day lighting vs night lighting | 0.393 vs 0.399 | +0.006 |

Both deltas are **below run-to-run noise**: mean render GPU across all six
scenarios spans 0.385–0.399 ms despite substantially different content, so a
0.002–0.006 ms difference is not a measurement. Halving environment instance
counts (330/132/77 → 176/77/44) changed primitives by 1.6% and GPU time not at
all.

The honest conclusion is that **layer-2 subsystem allocations cannot be derived
from measurement today**, because whole-scene cost is ~2.4% of the envelope and
individual subsystem contributions are smaller than variance. The table below is
therefore proposed as *spending limits* ordered by the ADR-0023 priority rule
(road geometry, sign readability, route context, collision, and nearby traffic
comprehension before distant scenery and cosmetic effects) — not as predictions,
and not traceable to a measured per-subsystem cost.

| Layer-2 subsystem | Proposed GPU allocation of 16.67 ms | Basis |
| --- | --- | --- |
| Road and route context | 3.0 ms | ADR-0023 top priority; largest current content class |
| Traffic | 3.0 ms | **unmeasured** — P0-015 open, no implementation |
| Regional environment | 2.5 ms | measured cost currently negligible; reserve for production density |
| Hero vehicle | 1.5 ms | single high-detail actor |
| Lighting and shadows | 2.0 ms | measured cost currently negligible |
| Effects | 1.0 ms | **unmeasured** — no implementation |
| UI and HUD | 0.7 ms | |
| Unallocated reserve | 3.0 ms | protects the p95 gate against the marginal stall behaviour above |

### Layer 3, content-class budgets: anchored to measurement

These are traceable to measured values in this capture, expressed as growth
headroom over the current representative slice.

| Content class | Measured now | Proposed provisional budget | Multiple |
| --- | --- | --- | --- |
| Draw calls per frame (peak) | 530 | 2,000 | 3.8× |
| Primitives per frame (peak) | 1.33 M | 8 M | 6.0× |
| Road shared materials | 18 | 40 | 2.2× |
| Road shared meshes | 9 | 30 | 3.3× |
| Environment shared materials | 8 | 24 | 3.0× |
| Texture residency | 110 MiB | 4 GiB | within the 9.5 GB GPU ceiling |
| Buffer residency | 52 MiB | 1 GiB | |
| Max synchronous chunk build | 34.9 ms | 16 ms | **tightening required** |
| Max synchronous environment build | 48.8 ms | 16 ms | **tightening required** |
| Game allocation per frame | 14.4 KB | 2 KB | **tightening required** |

The last three are deliberately *below* current measurements. They are the three
behaviours this capture identifies as risks, and they cannot be budgeted upward
without accepting the frame-pacing behaviour documented above.

## Evidence boundaries

This capture does **not** establish:

- **Anything about traffic.** P0-015 is `open`; there is no traffic in the scene.
  ADR-0023 requires representative traffic before production budgets are
  ratified. This is the single largest gap.
- **Anything about weather.** No weather system exists; the scenario was not
  captured and was not approximated.
- **Per-subsystem cost.** Isolation deltas were below noise, as shown above.
- **That production content will pass.** The measured slice uses ~2.4% of the
  frame-time envelope and ~1.9% of the GPU-memory ceiling. A pass at this content
  density is weak evidence about a shipping scene.
- **Player-representative frame pacing.** V-Sync was disabled and the frame rate
  uncapped to expose headroom. No V-Sync-on presentation check was run.
- **Visible pop-in or LOD quality.** Instance counts and streaming settle state
  are recorded; no automated pop-in detection exists.
- **A "High quality preset."** The repository has no renderer quality-preset
  system. `project.godot` carries Godot's default Forward+ settings with no
  MSAA, scaling, SSAO, or shadow-atlas configuration. `--environment-quality`
  controls environment *content* density, not renderer quality. The ADR-0023
  phrase "High quality preset" currently has no implementation to point at.
- **Any human gate.** This capture does not satisfy the Q-028 trip-map review or
  the Q-029 camera review, and does not advance the P1-008, P1-009, or P1-010
  art, rights, or readability gates.
- **Multi-run statistical confidence.** Each scenario was captured once. The
  stall criterion in particular varied across executions.

## Recommended follow-up, in priority order

1. Find the native-side working-set growth behind the 1.87 MiB/min failure. GPU
   memory is flat and managed heap accounts for only 6 of 57.7 MiB.
2. Reduce per-frame managed allocation from 14.4 KB toward the proposed 2 KB.
   This is the mechanism behind the once-per-second ~30 ms spike.
3. Move chunk and environment construction off the synchronous frame path, or
   bound it below 16 ms. Environment build reached 48.8 ms against a 50 ms limit.
4. Re-capture once P0-015 traffic exists; until then layer-2 allocations are
   reserve-based rather than measured.
5. Add per-subsystem isolation toggles so layer-2 costs become measurable.
