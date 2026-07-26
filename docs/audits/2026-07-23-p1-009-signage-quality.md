# P1-009 signage-quality adversarial review

Date: 2026-07-23

- Reviewed implementation revision: `d11f66a6f87da548237f3f95aa0e98ac9e495566`
- Comparison base: `dbff578` (`P0-019` evidence anchor)
- Scope: procedural sign geometry, information hierarchy, arrow orientation,
  semantic metadata, standards provenance, production/graybox equivalence,
  deterministic renderer review, and completion claims
- Result: pass for this bounded technical slice; P1-009 remains `in_progress`

## Standards boundary

The review used FHWA MUTCD 11th Edition Chapter 2E, FHWA's 2024 Standard
Highway Signs M1-1/M1-4 sheets, and the CDOT 2026 Sign Design Manual as primary
references. The implementation encodes project-original procedural geometry
and source metadata; it does not embed the source artwork or claim certified
sign design, installation dimensions, or traffic-control engineering
compliance.

The CDOT manual's reference to Highway Plus does not establish game
redistribution rights. The runtime therefore records
`godot-default-font-pending-approved-highway-font-rights` on every guide sign
and shield. No external font was imported.

## Findings resolved before acceptance

1. The prior seven-point Interstate and U.S. Route polygons did not preserve
   the distinctive M1-1 crown or M1-4 scalloped silhouette. They were replaced
   by independent procedural meshes based on the official proportion sheets.
2. Interstate signs previously used a blue polygon plus a rectangular red box,
   without the full white outline and divider. The revised assembly has a white
   silhouette, inset blue face, fitted red header, and white divider.
3. Lane arrows were Unicode label glyphs. This coupled sign meaning to font
   coverage and the arrows were downward for left/right exits. They are now
   semantic meshes with upward-left, upward-right, and down variants.
4. The first arrow mesh was viewed from its back face, mirroring right exits to
   the left. The renderer capture exposed the defect; the mesh orientation and
   placement now preserve the declared direction.
5. Route identity was repeated in both shields and destination copy. Route-like
   secondary lines are now suppressed when shields already carry that
   information, leaving the destination as the dominant message.
6. The first corrected right-exit arrow crowded `RIGHT LANE` at close range.
   A second renderer capture drove a smaller, separated symbol placement.
7. The aggregate shell gate parsed `shields=6` ambiguously because it also
   matched `standard_shields=6`. Metric parsing now requires a whitespace or
   line-start boundary and rejects duplicate matches.

## Invariants confirmed

- The `colorado-freeway-v3` kit remains procedural and uses the same generation
  path for production and graybox profiles.
- Each guide root records the standard reference, canonical FHWA source,
  layout profile, and explicit typography status.
- Each route shield records M1-1 or M1-4 design identity and procedural shape
  provenance. U.S. Route shields use the distinctive white silhouette directly
  on the green guide face without a black rectangular field.
- Each guide sign has exactly one geometric lane arrow, and stable automation
  IDs are preserved for guide roots, shields, labels, panels, and arrow meshes.
- `RoadChunk` resolves actual sign nodes and metadata before declaring the
  signage contract complete; counters alone cannot satisfy the contract.
- Production and graybox runs report identical guide-sign, shield, arrow,
  typography-fallback, material, mesh, structure, and lighting counts.
- The renderer contact sheet covers two approaches, combined M1-1/M1-4
  hierarchy, and close-range exit-only arrow spacing.

## Verification

- `dotnet build Cannonball.sln`: passed with zero warnings.
- `./scripts/run-scenario.sh --fixture representative-interchanges --profile road-visual`:
  passed nine chunks, three guide signs, six standards-based shields, three
  geometric arrows, two service icons, and two lighting stages.
- `./scripts/capture-scenario.sh ... --fixture representative-interchanges --sign-review`:
  passed a 280-frame, 60 FPS renderer review.
- `./scripts/verify-road-assets.sh --all-topology-fixtures`: passed two visual
  profiles and two topology fixtures after the first aggregate run exposed the
  ambiguous `shields` parser. The final marker reported three guide signs, six
  standards-based shields, three geometric arrows, and three declared
  typography fallbacks.
- `PATH=<isolated uv 0.9.24 cache>:$PATH GODOT_BIN=<official 4.7.1 console>
  ./scripts/check.sh`: passed doctor, build, 108 C# tests, Ruff, 78 map-pipeline
  tests, 12 PlayGodot tests, and official Godot smoke. The first attempt
  correctly failed doctor when the host exposed uv 0.11.29; the rerun used an
  isolated cached copy of the repository-pinned 0.9.24 without changing the
  repository or machine-wide installation.

Review artifact:
[signage-quality contact sheet](../images/p1-009-signage-quality-review.png).

## Remaining boundary

Q-024 still owns art direction, subjective readability, visual quality, and
final rights approval. Q-022 still owns minimum-PC and quantitative renderer
budgets. Exact approved typography, regional terrain and furniture, support
hardware, weathering, decals, high-speed pop-in measurements, and final rights
records remain open. These questions are collected in
`docs/QUESTIONS_FOR_RANDROID_2026-07-23_P1-009_SIGNAGE.md`.
