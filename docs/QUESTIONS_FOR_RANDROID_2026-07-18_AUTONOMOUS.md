# Questions for Randroid after the autonomous M5 pass

This dated handoff collects choices that still require human judgment while
letting deterministic engineering continue. The authoritative question status
remains in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

## Q-020 — first hero grand tourer

Which art direction and acquisition path should replace or promote the
project-original procedural **Hero GT** baseline created for P1-008?

### A. Refine the project-original procedural Hero GT (working default)

- **Pros:** fully redistributable source and ancestry; deterministic Blender
  rebuilds; semantic rig and budgets already match the game; lowest cash cost;
  agents can iterate without waiting on a third party.
- **Cons:** needs deliberate human art direction and a later modeling/material
  quality pass to avoid a generic procedural look; final polish will consume
  internal iteration time.

### B. Commission an original vehicle around the existing semantic rig

- **Pros:** strongest chance of a distinctive production silhouette and
  authored detail; the technical contract gives an artist a precise target.
- **Cons:** highest cash cost and scheduling risk; requires source-file,
  redistribution, revision, and rights terms; delivered work still has to pass
  deterministic export and runtime budgets.

### C. Acquire a clearly redistributable model and transform it substantially

- **Pros:** potentially faster route to higher geometric detail; may be cheaper
  than a commission.
- **Cons:** license and ancestry review is more complex; semantic re-rigging can
  erase the time savings; a recognizable donor design may weaken the fictional,
  unbranded identity.

**Autonomous default:** proceed with A as a technical and visual baseline. Keep
P1-008 `in_progress` until you approve the final silhouette, cockpit/chase
visibility, damage presentation, and exact project-original rights record.

## Q-021 — representative M5 region

### A. Colorado mountain-to-plains corridor (working default)

- **Pros:** extends the existing proof data, offers strong visual variety, and
  minimizes new geodata risk.
- **Cons:** mountain and urban-edge assets broaden the environment workload.

### B. High-plains interstate corridor

- **Pros:** simpler terrain and lower asset density make streaming budgets
  easier to establish.
- **Cons:** less visual variety and weaker stress coverage for grades, cuts,
  fills, and distant terrain.

### C. Defer region selection until road and vehicle art are approved

- **Pros:** avoids premature environment art.
- **Cons:** delays representative renderer and streaming evidence; provisional
  budgets remain less trustworthy.

**Autonomous default:** continue fixture work with A without closing Q-021.

## Q-022 — minimum target PC and production budgets

### A. Ratify after measurements on available Windows hardware (working default)

- **Pros:** evidence-based; static CI budgets can tighten now while real GPU
  captures determine the final floor.
- **Cons:** M5 cannot close until the machine and test session are declared.

### B. Declare a conservative minimum PC now

- **Pros:** gives art production an immediate fixed ceiling.
- **Cons:** an arbitrary floor may force needless quality cuts or miss the
  actual audience hardware.

### C. Use hosted CI as the target

- **Pros:** easy to reproduce for CPU and memory checks.
- **Cons:** hosted runners are not a representative game GPU and cannot ratify
  presentation performance.

**Autonomous default:** use A; enforce provisional static budgets and leave the
hardware ratification gate open.
