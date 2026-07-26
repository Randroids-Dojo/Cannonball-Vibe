# Questions for Randroid: P1-009 signage closeout

Date: 2026-07-23

The autonomous signage-quality slice now has reference-informed M1-1
Interstate and M1-4 U.S. Route silhouettes, geometric lane arrows, rounded
guide boards, destination-first hierarchy, retroreflective materials, stable
semantic IDs, and deterministic production/graybox checks.

Review artifact:
[P1-009 signage-quality contact sheet](images/p1-009-signage-quality-review.png)

These decisions remain human-owned. The implementation deliberately records
the current font as a fallback and P1-009 remains `in_progress`.

## Q-024: confirm the visual language

Should the production highway kit continue with contemporary Colorado freeway
realism?

- **A. Approve contemporary Colorado realism (working default).** Continue
  toward a Colorado-specific type, support, furniture, weathering, terrain, and
  rights pass.
- **B. Shift to stylized modern American freeway.** Keep semantic and
  readability rules but exaggerate scale, silhouettes, and contrast.
- **C. Reopen the direction.** Pause production art acquisition and revise the
  broader vehicle, UI, road, and environment visual language together.

## Sign typography and redistribution rights

Which approved font source may be bundled and redistributed with the game?

- **A. Provide or approve a licensed highway-sign font package.** I will add
  its license/provenance record and replace the current Godot fallback.
- **B. Approve research for a redistributable standards-inspired alternative.**
  I will present candidates and license evidence before importing one.
- **C. Keep the fallback for now.** Technical work may continue, but exact
  sign typography and final rights approval remain open.

The CDOT manual references Highway Plus in its SignCAD workflow, but that
reference alone is not redistribution permission. No external font was copied
into the repository.

## Q-022: ratify the target renderer budget

What minimum Windows PC and renderer configuration should own the production
day/night sign-readability and performance gates?

Until this is answered, the automated scenarios continue to enforce the
provisional 50 ms initial chunk/collision construction limits and deterministic
semantic/material counts. They do not claim production GPU frame-time,
draw-call, texture-residency, LOD, or high-speed pop-in acceptance.

## Autonomous posture

Continue improving procedural geometry, fixtures, semantics, provenance, and
non-GPU regressions. Do not import an unapproved font, claim MUTCD/CDOT
engineering compliance, ratify target-hardware budgets, or mark P1-009
complete.
