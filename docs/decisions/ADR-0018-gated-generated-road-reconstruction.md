# ADR-0018: Gated generated road reconstruction

- Status: Accepted
- Date: 2026-07-23
- Owner decisions: Q-002 Option A and Q-003 Option A

## Context

NHPN supplies useful national route-family topology but does not provide
production lane geometry, modern interchange detail, or consistently drivable
alignment. Using its lines directly would reproduce coarse source error in the
rendered and collision road. Hand-authoring every playable curve and
interchange would not scale coast to coast.

The prior road-junction failures also demonstrate that visually plausible
endpoints are insufficient. A generated connection must agree in position,
heading, curvature, grade, lane topology, collision, and sightline before it
can become playable content.

## Decision

- NHPN remains a route-family and coarse-topology backbone under ADR-0002. It
  never becomes authoritative lane or road-surface geometry.
- Deterministically reconstruct candidate centerlines, lane splines, ramps,
  transitions, and interchange corrections from approved source context and
  authored constraints.
- Accept a generated candidate only when all applicable continuity, endpoint
  pose, curvature, curvature-rate, grade, vertical-curvature, sightline,
  self-intersection, clearance, collision, lane-connection, and drivability
  gates pass.
- Reject failed candidates with machine-readable diagnostics. Do not smooth,
  bridge, or conceal a failed connection only in rendered presentation.
- Use deterministic authored overlays for rejected or exceptional locations.
  Overlays preserve recursive provenance, stable identifiers, validation, and
  content-addressed output.
- Representative elevated, driving, and collision captures remain required for
  each new correction family even when numerical gates pass.
- Automated generation may reduce routine authoring; it does not waive
  corridor-level source comparison, correction-burden measurement, or human
  geographic plausibility review.

## Consequences

- Coast-to-coast production can scale through generation while concentrating
  manual work on measurable exceptions.
- The pipeline must treat validation failure as normal routed work, not as a
  reason to loosen geometry thresholds silently.
- Authored overrides remain first-class deterministic content rather than
  untracked editor fixes.
- Q-002 and Q-003 are resolved. Individual corridors still require evidence
  that the selected sources and correction workload are viable.

## Rejected alternatives

- **Render NHPN lines directly:** is fast but produces coarse, inaccurate, and
  potentially undrivable roads.
- **Hand-author every road and interchange:** gives control but cannot scale
  economically across the intended trip.
- **Trust generated candidates without rejection gates:** recreates the janky
  pose, curvature, and collision transitions that the road contract exists to
  prevent.
- **Hide failed connections with visual patches:** can conceal a seam without
  correcting authoritative path or collision continuity.
