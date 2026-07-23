# Reference Windows performance hardware

Date declared: 2026-07-23
Decision: Q-022 Option A — measure on an available Windows gaming PC

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

The existing Windows workstation audit already proves that the repository,
Godot 4.7.1 .NET, Forward+, and Vulkan run on an RTX 3080 Ti system. Q-022
remains open until representative production scenes record and ratify CPU/GPU
frame-time percentiles, memory high-water marks, streaming latency, draw calls,
triangles, material and texture residency, and LOD quality on this machine.
