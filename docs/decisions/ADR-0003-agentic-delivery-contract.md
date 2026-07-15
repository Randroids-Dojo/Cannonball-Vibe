# ADR-0003: Evidence-backed agent delivery with explicit human gates

- Status: Accepted
- Date: 2026-07-14

## Context

The project is intended to be implementable by autonomous agents. Passing a
short unit or smoke suite is not equivalent to delivering a milestone. Several
product requirements are also inherently subjective, physical, legal, or tied
to credentials that agents should not approve independently.

## Decision

Every delivery task must declare:

- a stable task and milestone ID;
- dependencies and owned files or generated outputs;
- pinned inputs, tools, and deterministic seeds;
- exact implementation and verification commands;
- quantitative acceptance thresholds;
- required evidence artifacts and content hashes;
- retry, checkpoint, and rollback behavior;
- any required human gate.

Machine-verifiable gates are authoritative for builds, data integrity,
determinism, traversal, performance budgets, save equivalence, packaging, and
clean-machine launch behavior. A milestone cannot be called complete while any
required machine gate or human gate is open.

## Human approval boundaries

Human approval is required for driving enjoyment, physical wheel feel,
representative-player comprehension, accessibility usability, final rights
review, credential provisioning, signing/notarization, store submission, and
public release.

## Consequences

- Unsigned internal builds can become fully autonomous.
- Signed public releases remain agent-executed but human-approved.
- `docs/DELIVERY_LEDGER.json` is the machine-readable readiness authority.
- Audit evidence belongs under `docs/audits/`; architectural changes belong in
  new ADRs; unresolved choices belong in `docs/OPEN_QUESTIONS.md`.
- Agents must not substitute code volume or a partial smoke result for the
  declared acceptance evidence.
