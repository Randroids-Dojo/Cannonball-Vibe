# P1-010 regional environment decisions for Randroid

The autonomous technical baseline is implemented and verified. These are the
only decisions that prevent P1-010 from closing. The authoritative status stays
in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md); this file is the focused review
handoff for the new environment capture.

Review artifact:
[regional environment contact sheet](images/p1-010-regional-environment-review.png)

## 1. Is the Colorado mountain-to-plains direction right for the representative slice? (Q-021)

### A. Continue this direction (recommended)

- **Pros:** builds on verified route data; mountain, foothill, plains, and
  urban-edge scenes exercise the broadest streaming and readability range.
- **Cons:** requires more environment art than a single-biome corridor, and the
  current procedural shapes need a later realism pass.

### B. Simplify to a high-plains corridor

- **Pros:** lower asset density and easier production performance targets.
- **Cons:** loses much of the visual identity and the strongest terrain stress
  cases.

### C. Pause environment art until vehicle and road art are final

- **Pros:** avoids polishing scenery around assets that may change.
- **Cons:** blocks representative performance evidence and delays discovering
  composition conflicts between road, vehicle, signs, and terrain.

## 2. How should we ratify production performance budgets? (Q-022)

### A. Measure on an available Windows game PC, then ratify (recommended)

- **Pros:** produces honest GPU, frame-time, memory, draw-call, and LOD limits
  from the intended runtime; provisional quality tiers can keep improving now.
- **Cons:** needs a declared machine and a later hands-on capture session.

### B. Declare a conservative minimum PC now

- **Pros:** gives art production a fixed ceiling immediately.
- **Cons:** the ceiling would be a guess and may either waste quality or miss
  the actual audience hardware.

### C. Treat hosted CI as the target

- **Pros:** automated and repeatable.
- **Cons:** hosted runners are not representative game GPUs, so they cannot
  settle visual-performance quality.

No answer is needed for engineering to continue. Option A remains the working
default for both questions, but P1-010 will remain `in_progress` until the final
art direction, readability, rights, and target-hardware evidence are approved.
