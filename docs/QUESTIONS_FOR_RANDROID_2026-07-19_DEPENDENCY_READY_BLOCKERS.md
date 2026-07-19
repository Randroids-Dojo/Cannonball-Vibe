# Questions blocking dependency-ready work (2026-07-19)

This is the short list of questions that currently block additional automated task delivery.

## Q-025 — P0-012 representative lane/interchange corpus approval (required for unblock)

The machine gates for P0-012 are complete, and the human gate remains open in:

[QUESTIONS_FOR_RANDROID_2026-07-18_SYSTEMATIC_BACKLOG.md](QUESTIONS_FOR_RANDROID_2026-07-18_SYSTEMATIC_BACKLOG.md)

Until this is approved, the following remain blocked by dependencies:

- P0-013 — Full-screen trip map and authoritative progress
- P0-015 — Layered deterministic highway traffic director
- P1-009 — Modular production highway visual kit
- P1-010 — Regional terrain and background environment

## Q-027 — Publish immutable source-release draft

Draft is prepared, verified, and currently private/unpublished at:

[docs/QUESTIONS_FOR_RANDROID_2026-07-19_SOURCE_PUBLICATION.md](QUESTIONS_FOR_RANDROID_2026-07-19_SOURCE_PUBLICATION.md)

Until the publication decision is made, full progress on:

- P1-006 — Primary immutable GitHub source publication (completed machine side, human gate pending)
- P1-003 — Signed public release promotion

...cannot complete their remaining delivery gates.

## Working default if no reply

Continue running non-blocked local/CI validation while waiting.
Keep P1-006 as human-gated, keep the draft private, and do not publish immutable
assets or public releases without explicit owner approval.

## Next owner decision order

1. Approve or reject P0-012 (Q-025) with any required visual/topology correction.
2. Approve or hold P1-006 source draft publication (Q-027).
3. Resume blocked dependency tree once both are closed.
