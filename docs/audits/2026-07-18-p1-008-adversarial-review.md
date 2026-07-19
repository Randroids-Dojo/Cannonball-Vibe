# P1-008 adversarial review

- Reviewed revision: `428c9d97642f7c5ee7c72dd88fa6926b968a2ba8`
- Comparison base: `origin/main`
- Scope: Hero GT source and generated assets, manifests, Godot wrapper and C#
  adapter, visual scenario, asset/release validators, release reproducibility,
  runtime fallback, and shipping-package boundaries
- Result: pass with no unresolved actionable finding

## Review method

The review traced the production scene from checksum-locked Blender source
through deterministic glTF export, an isolated official Godot 4.7.1 import,
normalization, the project-owned wrapper, runtime instantiation, and complete
release PCK contents. It separately inspected simulation ownership, node lookup
and transforms, camera selection, LOD and damage behavior, graybox fallback,
command argument handling, temporary-directory cleanup, manifest path and hash
validation, mutation rejection, release exclusions, and clean-stage byte
reproducibility. The tracked renderer sheet was visually inspected, and all
eight renderer stages were exercised in the final movie.

## Findings resolved before acceptance

1. Fresh Godot imports used different non-semantic numeric node IDs. The
   generated text scene now strips only those `unique_id` attributes; two
   independent imported scenes otherwise match in mesh, material, transform,
   property, and hierarchy content.
2. The exporter reintroduced cache-specific IDs while converting text scenes
   to binary. Optional export conversion is disabled, and two fully fresh Linux
   releases now produce identical PCK and archive bytes.
3. The asset PCK audit initially recognized binary/remap forms but not the
   intentionally shipped deterministic `.tscn`. It now accepts all supported
   forms while still requiring the wrapper and generated visual and rejecting
   Blender, data-manifest, and tooling inputs.
4. A successful Linux-only release returned status 1 because the unused
   Windows predicate was the script's final command. Explicit conditionals now
   return the build result correctly.
5. The night cockpit review moved the chase camera near the cabin and did not
   prove the semantic cockpit anchor. The stage now makes the anchor-owned
   cockpit camera current and asserts the chase camera is not current.

## Invariants confirmed

- The Hero GT adapter consumes authoritative steering, longitudinal speed, and
  per-wheel suspension compression. It does not add a physics body, replace the
  existing collision shape, or enter the save schema.
- The project-original runtime visual is the default; `--graybox-vehicle` and
  `ForceGrayboxVisual` preserve a deterministic fallback over the same physics
  contract.
- All 37 required semantic nodes resolve, three LODs and five damage zones are
  exercised, and quantitative asset budgets pass with margin.
- Release packs include the project-owned wrapper and deterministic generated
  visual, exclude source art and validation tools, and contain no PlayGodot
  runtime dependency.
- The full repository gate, legacy asset-pipeline regression, vehicle asset
  gate, eight-stage scenario, renderer capture, and two-fresh-stage unsigned
  Linux release all pass.

## Remaining boundary

Q-020 is deliberately not treated as a technical defect or silently approved.
The project owner must still approve final art direction and the exact rights
record before P1-008 or M5 can be marked complete. The procedural Hero GT is a
ship-capable technical baseline, not an assertion that its current art is the
final production choice.
