# Q-022 reference Windows performance capture

Date: 2026-08-03
Task: Q-022 (blocking M5); related P1-008, P1-009, P1-010, P0-015
Evidence: `evidence/M5/Q-022-reference-windows-capture.json`
Handoff: [Q-022 ratification handoff](../QUESTIONS_FOR_RANDROID_2026-08-03_Q022_REFERENCE_CAPTURE.md)

This is the first representative production-content performance capture on the
declared reference PC. It moves Q-022 from "thresholds ratified, unmeasured" to
"measured, with derived allocations proposed." **Q-022 remains open.**

## Result in one line

Frame-pacing percentiles and both memory ceilings pass with large margins. The
**no-steady-driving-stall-above-50 ms threshold fails** in the high-speed and
30-minute scenarios, by between 0.4% and 1.6%. Both tail criteria are boundary
cases: an earlier execution of this same matrix inverted both verdicts.

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
worktree created at the exact committed revision that contains the harness**, so
a checkout of the recorded revision reproduces the measured executable.

- Capture revision: `33e6dde69b1b2ac03c7c2a03ef781ace110a1924`
- Worktree: `C:/Dev/cbv-q022-verify`, created fresh and outside any gameplay checkout
- `git status --porcelain` immediately before measuring: **empty**
- `scripts/doctor.sh`: all five pins passed — Godot `4.7.1.stable.mono.official.a13da4feb`,
  .NET SDK `10.0.102`, uv `0.9.24`, Git LFS `3.7.1`, perl available

An earlier execution measured from a worktree that necessarily carried the
then-uncommitted harness. It was reported as non-conforming and its artifacts
were discarded; they are not the evidence recorded here. Every route package is
rebuilt from checksum-locked fixture sources at the start of every run, so no
stale generated output contributes to a measurement.

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

### Harness defects found and corrected before these numbers were taken

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

Three further defects were found in review and fixed before this capture:

3. **The measurement clock started before warm-up snapshot work**, charging that
   setup to the first measured frame as a spurious stall.
4. **Cumulative distance was computed by differencing route position**, which
   resets to zero on every corridor wrap. A 30-minute run reported 22.6 km
   instead of the 71.9 km actually driven. Distance is now accumulated across
   wraps and final route position is reported separately.
5. **Loop-wrap stall attribution was evaluated as stalls were recorded**, so it
   could only ever match wraps that had already happened. A stall in the 0.75 s
   *before* a wrap — the chunk-rebuild spike a wrap is most likely to cause —
   could never match and was miscounted as steady driving. Attribution now runs
   at summary time, when every wrap is known.

`GC.GetTotalAllocatedBytes` was also being read once per emitted field, so the
allocation total, harness share, and per-frame figure came from different
denominators; it is now read once per summary.

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
| daylight | 113,430 | 120.0 | 0.883 | 1.718 | 2.902 | 44.247 | 0 | 945 |
| night | 111,014 | 120.0 | 0.878 | 1.833 | 2.752 | 46.414 | 0 | 925 |
| high-speed | 110,750 | 120.0 | 0.883 | 1.848 | 2.748 | 50.798 | 1 | 923 |
| streaming | 275,652 | 300.0 | 0.893 | 1.798 | 2.843 | 45.699 | 0 | 919 |
| degraded-quality | 110,327 | 120.0 | 0.897 | 1.728 | 2.748 | 42.398 | 0 | 919 |
| steady-state-30m | 1,653,461 | 1800.0 | 0.897 | 1.782 | 2.792 | 50.502 | 2 | 919 |

The three frames above 50 ms are examined under Acceptance below. All other
scenarios recorded zero steady-driving stalls.

## CPU versus GPU attribution

| Scenario | Mean frame ms | Mean render CPU ms | Mean render GPU ms | Mean non-render ms | GPU-bound frames | Bound by |
| --- | --- | --- | --- | --- | --- | --- |
| daylight | 1.058 | 0.299 | 0.391 | 0.667 | 86.4% | gpu |
| night | 1.081 | 0.302 | 0.384 | 0.697 | 84.6% | gpu |
| high-speed | 1.084 | 0.302 | 0.390 | 0.694 | 88.0% | gpu |
| streaming | 1.088 | 0.316 | 0.386 | 0.703 | 82.4% | gpu |
| degraded-quality | 1.088 | 0.297 | 0.394 | 0.694 | 87.5% | gpu |
| steady-state-30m | 1.089 | 0.319 | 0.386 | 0.703 | 82.2% | gpu |

The "bound by" column compares render CPU against render GPU only, and is
misleading alone. **The largest single component of frame time is non-render
main-thread work** (0.67–0.70 ms), which exceeds render GPU time (~0.39 ms) in
every scenario. Simulation, physics synchronisation, HUD update, and garbage
collection dominate, not rendering.

## Memory

| Scenario | Peak GPU MiB | Peak working set MiB | Working-set slope | R² | Peak texture MiB | Peak buffer MiB |
| --- | --- | --- | --- | --- | --- | --- |
| daylight | 177 | 779 | 7.29 MiB/min | 0.884 | 110 | 48 |
| night | 176 | 738 | 12.97 MiB/min | 0.970 | 110 | 48 |
| high-speed | 178 | 742 | 13.37 MiB/min | 0.854 | 110 | 49 |
| streaming | 175 | 723 | 6.02 MiB/min | 0.966 | 110 | 52 |
| degraded-quality | 176 | 730 | 14.48 MiB/min | 0.852 | 110 | 48 |
| steady-state-30m | 177 | 763 | **0.93 MiB/min** | 0.453 | 110 | 48 |

Short-run slopes are inflated by process warm-up (JIT, caches) and are not
comparable to the 30-minute figure; only the 30-minute run is evaluated against
the threshold.

Over the 30-minute run: working set 710.3 → 747.2 MiB (**+36.9 MiB**), managed
heap 19.9 → 29.3 MiB (+9.4 MiB), **GPU memory 175.8 → 175.6 MiB (flat)**. Any
growth is CPU-side; GPU residency is stable.

## Garbage collection

| Scenario | Game bytes/frame | Gen0 | Gen0/s | Gen2 | Harness share of allocation |
| --- | --- | --- | --- | --- | --- |
| daylight | 14,208 | 97 | 0.81 | 1 | 0.10% |
| night | 14,256 | 95 | 0.79 | 1 | 0.10% |
| high-speed | 16,274 | 108 | 0.90 | 2 | 0.09% |
| streaming | 15,773 | 262 | 0.87 | 2 | 0.09% |
| degraded-quality | 14,263 | 95 | 0.79 | 1 | 0.10% |
| steady-state-30m | 14,391 | 1,437 | 0.80 | 14 | 0.10% |

This is the mechanism behind the recurring sub-threshold spike:

| Per-second worst frame, 30-minute run | Value |
| --- | --- |
| Seconds sampled | 1,798 |
| Containing a frame > 16.67 ms | 1,425 (79%) |
| Containing a frame > 30 ms | 996 |
| Containing a frame > 50 ms | 2 |
| Median / p90 / p99 / max | 30.29 / 34.13 / 45.41 / 50.50 ms |

1,437 Gen0 collections against 1,425 seconds containing a >16.67 ms spike is a
near 1:1 correspondence. The game allocates ~14.4 KB per rendered frame, and the
resulting Gen0 collections produce a ~30 ms spike roughly once per second. The
harness contributes 0.10% of that allocation, so this is game and engine code.

**The per-frame figure is an upper bound.** Any profile that sets `_smokeTest` —
including this one — also runs `Main.UpdateRunAutomationState()` every frame,
marshalling ~35 values into a Godot `Dictionary`. That automation bookkeeping is
not gameplay work but is counted in `game_allocated_bytes`.

## Streaming

| Scenario | Cumulative distance m | Final route position m | Max chunk build ms | Max collision build ms | Max env build ms | Rebases | Loops | Chunk failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daylight | 4,800 | 5,660 | 41.907 | 3.252 | 39.346 | 5 | 0 | 0 |
| night | 4,801 | 5,661 | 37.280 | 2.806 | 40.476 | 5 | 0 | 0 |
| high-speed | 10,686 | 12,499 | 35.281 | 3.152 | 40.519 | 11 | 0 | 0 |
| streaming | 25,425 | 2,573 | 40.170 | 3.685 | 39.671 | 26 | 1 | 0 |
| degraded-quality | 4,801 | 5,661 | 34.180 | 3.148 | 40.446 | 5 | 0 | 0 |
| steady-state-30m | 71,931 | 23,861 | 35.628 | 3.099 | 40.213 | 72 | 2 | 0 |

Cumulative distance is tracked across corridor wraps; final route position is
reported separately because a wrap resets it to zero. The 30-minute run drove
71.9 km, which matches 40 m/s sustained for 1800 s.

Zero chunk failures and zero seam or collision anomalies across every scenario.
Synchronous chunk construction peaked at 41.9 ms and environment construction at
40.5 ms, against the 50 ms stall limit.

## Content class

| Scenario | Peak draw calls | Mean draw calls | Peak primitives | Env profile | Near/Mid/Distant instances | Road materials | Env materials |
| --- | --- | --- | --- | --- | --- | --- | --- |
| daylight | 429 | 322 | 1,330,366 | balanced | 330/132/77 | 18 | 8 |
| night | 430 | 333 | 1,332,602 | balanced | 330/132/77 | 18 | 8 |
| high-speed | 430 | 323 | 1,332,602 | balanced | 540/216/126 | 18 | 8 |
| streaming | 530 | 350 | 1,332,602 | balanced | 540/216/126 | 18 | 8 |
| degraded-quality | 428 | 321 | 1,308,438 | low | 176/77/44 | 18 | 8 |
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
| high-speed | PASS | PASS | **FAIL** | PASS | PASS | not evaluated (<30 min) |
| streaming | PASS | PASS | PASS | PASS | PASS | not evaluated (<30 min) |
| degraded-quality | PASS | PASS | PASS | PASS | PASS | not evaluated (<30 min) |
| steady-state-30m | PASS | PASS | **FAIL** | PASS | PASS | PASS (0.93 MiB/min, R² 0.45) |

### The failure

Three frames exceeded 50 ms after warm-up:

| Scenario | t (s) | Frame ms | Render CPU ms | Render GPU ms | Speed m/s |
| --- | --- | --- | --- | --- | --- |
| high-speed | 29.3 | 50.80 | 0.298 | 0.391 | 91.0 |
| steady-state-30m | 686.1 | 50.20 | 0.386 | 0.387 | 40.0 |
| steady-state-30m | 1537.6 | 50.50 | 0.542 | 0.392 | 40.0 |

Render CPU and GPU are both under 0.6 ms in every case, so essentially the whole
stall is outside rendering. Maximum synchronous chunk build reached 41.9 ms and
environment build 40.5 ms in the same matrix — the right magnitude to explain
them. None is attributed to a corridor wrap.

### Headroom per metric

| Threshold | Limit | Worst measured | Headroom |
| --- | --- | --- | --- |
| p95 presented-frame time | 16.67 ms | 1.848 ms | 9.0× |
| p99 presented-frame time | 20 ms | 2.902 ms | 6.9× |
| GPU memory | 9.5 GB | 0.187 GB | 51× |
| Process working set | 16 GB | 0.817 GB | 20× |

### Both tail criteria are marginal

The percentile and memory-ceiling passes are genuine and large. The two tail
criteria are not, and a single run should not be read as settling either.

| Criterion | This capture | Earlier execution of the same matrix |
| --- | --- | --- |
| no steady stall >50 ms | **FAIL** (3 stalls, 50.20–50.80 ms) | PASS (0 stalls) |
| sustained growth | PASS (0.93 MiB/min, R² 0.45) | **FAIL** (1.87 MiB/min, R² 0.79) |

Both verdicts inverted between runs, and in this capture the growth figures sit
just under both halves of the proposed rule (0.93 against 1 MiB/min; R² 0.45
against 0.5). Treat both as boundary behaviour requiring repeat measurement, not
as settled outcomes. Repeat-run confidence is a named evidence boundary below.

## Derived budget proposals — all provisional

### Layer 2, subsystem allocations: cannot be derived from this capture

Two subsystem isolations were attempted by difference:

| Comparison | Mean render GPU ms | Delta |
| --- | --- | --- |
| balanced environment (daylight) vs low environment (degraded-quality) | 0.3908 vs 0.3939 | +0.0031 |
| day lighting vs night lighting | 0.3908 vs 0.3835 | −0.0073 |

Both deltas are **below run-to-run noise**: mean render GPU across all six
scenarios spans 0.384–0.394 ms despite substantially different content, so a
0.003–0.007 ms difference is not a measurement. The night delta is even negative,
which is a clear sign of noise rather than signal. Halving environment instance
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
| Max synchronous chunk build | 41.9 ms | 16 ms | **tightening required** |
| Max synchronous environment build | 40.5 ms | 16 ms | **tightening required** |
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
- **Shipping-build performance.** Godot loads the assembly built for the running
  editor configuration, so every number here comes from a **Debug** build with
  unoptimised IL and different JIT behaviour from a shipping export. Frame times,
  GPU attribution, and especially per-frame allocation are all affected. Budgets
  derived from these numbers should be re-derived against an exported Release
  build before they are treated as production limits.
- **A clean separation of game allocation from automation bookkeeping.** Any
  profile that sets `_smokeTest` — including this one — also runs
  `Main.UpdateRunAutomationState()` every frame, marshalling roughly 35 values
  into a Godot `Dictionary`. That work is automation, not gameplay, but it is
  counted in `game_allocated_bytes`. The 14 KB-per-frame figure is therefore an
  **upper bound** on real game allocation, and the Gen0 rate it drives is
  correspondingly an upper bound.
- **Any human gate.** This capture does not satisfy the Q-028 trip-map review or
  the Q-029 camera review, and does not advance the P1-008, P1-009, or P1-010
  art, rights, or readability gates.
- **Multi-run statistical confidence.** Each scenario was captured once per
  matrix execution. Both tail criteria inverted between executions, so neither
  the stall failure nor the sustained-growth pass is a stable result. A repeat
  30-minute run is required before either is treated as settled.

## Recommended follow-up, in priority order

1. Find the native-side working-set growth behind the sustained-growth failure.
   GPU memory is flat and managed heap accounts for a small fraction of it.
2. Reduce per-frame managed allocation from 14.4 KB toward the proposed 2 KB.
   This is the mechanism behind the once-per-second ~30 ms spike.
3. Move chunk and environment construction off the synchronous frame path, or
   bound it below 16 ms. Environment build reached 48.8 ms against a 50 ms limit.
4. Re-capture once P0-015 traffic exists; until then layer-2 allocations are
   reserve-based rather than measured.
5. Add per-subsystem isolation toggles so layer-2 costs become measurable.
6. Re-capture against an exported Release build; every number here is from a
   Debug build.
7. Separate automation bookkeeping from gameplay allocation so the per-frame
   figure stops being an upper bound.
