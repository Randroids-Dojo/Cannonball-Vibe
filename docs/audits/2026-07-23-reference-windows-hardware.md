# Reference Windows performance hardware

Date declared: 2026-07-23
Decision: Q-022 Option A plus performance follow-up Options A and A

## Declared machine

- OS: Windows 11 Pro 64-bit
- CPU: AMD Ryzen 9 5900X, 12 cores / 24 threads
- GPU: ASUS TUF GeForce RTX 3080 Ti OC, 12 GB GDDR6X
- Motherboard: ASUS ROG Strix X570-E Gaming
- Memory: 64 GB G.Skill Trident Z RGB DDR4-3600
- Primary storage: 2 TB Inland Performance Plus PCIe 4.0 NVMe
- Secondary storage: 2 TB WD Blue SATA SSD
- Power supply: ASUS ROG Strix 850 W 80 Plus Gold
- Cooling: NZXT Kraken Z63 280 mm AIO
- Case: Corsair iCUE 4000X RGB

## Role

This is the first declared reference machine for representative Windows
renderer captures and production-budget measurement. It is not yet the minimum
supported PC and its specifications are not themselves a performance result.

The selected production reference target is 2560×1440 at the High quality
preset with a stable 60 FPS. The 60 FPS target establishes a 16.67 ms frame-time
envelope after warm-up; average FPS alone is not sufficient evidence. The
provisional production-stable gate requires:

- p95 presented-frame time at or below 16.67 ms;
- p99 presented-frame time at or below 20 ms;
- no steady-driving stall above 50 ms after warm-up;
- no more than 9.5 GB of GPU memory at the High preset;
- no more than 16 GB of process working set; and
- no sustained positive memory growth during a 30-minute steady-state run.

Budgets are layered across:

1. whole-scene CPU/GPU frame time, frame pacing, memory, and streaming outcomes;
2. vehicle, road, traffic, environment, effects, lighting, and UI subsystems;
3. content-class geometry, draw calls, materials, textures, instancing, LOD,
   and visible pop-in.

Fixture measurements may establish provisional regression limits. Production
limits require representative content and an owner-ratified capture on this
machine; see
[ADR-0023](../decisions/ADR-0023-reference-performance-target-and-layered-budgets.md).

The existing Windows workstation audit already proves that the repository,
Godot 4.7.1 .NET, Forward+, and Vulkan run on an RTX 3080 Ti system. Q-022
remains open only until representative production scenes record and ratify
these thresholds plus derived subsystem and content-class allocations,
CPU/GPU attribution, streaming latency, draw calls, triangles, material and
texture residency, and LOD quality on this machine.

## Evidence acquisition

The owner selected a live, agent-operated remote session on the declared
Windows PC instead of a user-run evidence bundle or manual profiler screenshots.
The session must still use reproducible scripts and preserve complete
machine-readable outputs; remote control changes who operates the capture, not
the evidence standard.

The owner must initiate and authorize the session. Do not create standing remote
access, store remote-control credentials in the repository, collect unrelated
machine data, or treat remote availability as permission to publish, install
unrelated software, or change account/security settings. The exact remote
mechanism and session timing remain owner-coordinated.
