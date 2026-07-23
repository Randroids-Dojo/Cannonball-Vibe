# Questions after the 2026-07-22 autonomous delivery pass

No new architecture or spending decision was created during this pass. The
following existing human gates are the only decisions currently preventing the
next P0/P1 closures. Engineering can continue around them, but agents cannot
answer them by proxy.

## 1. Q-029 — Are both driving cameras comfortable and readable?

### A. Approve chase and cockpit after the five-minute review (recommended if comfortable)

- **Pros:** closes P0-017, permits P0-018 to close, and unlocks quantitative
  P0-019 vehicle-dynamics work.
- **Cons:** requires about ten minutes of hands-on driving and view switching.

### B. Approve chase only and request cockpit changes

- **Pros:** preserves the primary driving view while identifying focused
  cockpit work.
- **Cons:** P0-017 and its dependent handling chain remain open.

### C. Request changes to both views

- **Pros:** avoids accepting discomfort or poor sightlines.
- **Cons:** delays the P0-019/P0-020 handling sequence until another camera
  iteration and review.

Review instructions remain in
[the handling-gates handoff](QUESTIONS_FOR_RANDROID_2026-07-20_HANDLING_GATES.md).

## 2. Q-021 — Continue the Colorado mountain-to-plains environment direction?

### A. Continue this direction (recommended)

- **Pros:** the new terrain-quality capture now proves continuous mountain,
  foothill, plains, and urban-edge relief with zero measured chunk seam.
- **Cons:** it commits later production art to a multi-biome asset set.

### B. Keep the architecture but revise the visual language

- **Pros:** preserves the verified streaming and terrain work while allowing a
  less stylized palette, different geology, or denser vegetation.
- **Cons:** requires a concrete mood/reference direction before final art.

### C. Select another representative region

- **Pros:** may better match the desired fantasy or target audience.
- **Cons:** requires new geodata, art research, and representative captures.

Review artifact:
[terrain-quality contact sheet](images/p1-010-terrain-quality-review.png).

## 3. Q-022 — Which Windows PC should ratify production renderer budgets?

### A. Declare an available intended gaming PC (recommended)

- **Pros:** lets us measure real GPU frame time, memory, draw calls, texture
  residency, and LOD quality instead of guessing.
- **Cons:** requires the machine specification and a later hands-on run.

### B. Declare a conservative minimum specification now

- **Pros:** gives production art an immediate ceiling.
- **Cons:** an unevidenced ceiling may waste quality or fail to represent the
  actual audience.

### C. Defer hardware ratification

- **Pros:** no immediate setup is needed; provisional static budgets remain in
  force.
- **Cons:** P1-009 and P1-010 cannot close their production performance gates.

The recommended working defaults remain A for the regional direction and A
once an intended Windows test machine is available. No cloud service or paid
infrastructure is needed for these choices.
