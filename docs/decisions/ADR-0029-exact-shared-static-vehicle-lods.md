# ADR-0029: Exact shared static vehicle geometry across distant LODs

- Status: Proposed
- Date: 2026-09-21
- Extends: ADR-0012 and ADR-0023
- Task: P1-018
- Implementation: not on main. The untested draft (constructor, exporter,
  import adapter, `VehicleVisualRig` and a PlayGodot test) is preserved
  unmerged in commit `af7fc36` on local branch
  `wip/p1-018-shared-static-lod`; see delivery checkpoint v41. Landing it
  changes the source binding's locked constructor tree, so it needs a fresh
  sedan build and the full source, asset and runtime gates.

## Context

The sedan's lower construction contains a static painted assembly with identical
complete native geometry and fields in LOD1 and LOD2. Storing two copies consumes
the vehicle budget without changing either view. The existing runtime assigns
each named mesh to one exclusive LOD list, so data deduplication alone cannot
remove the second physical instance safely.

## Decision

An optional sedan construction profile may consolidate the freshly generated
static paint BoundaryRemainder pair only after exact comparison of geometry,
corner fields, transforms, materials, component ranges and construction state.
Keep one existing LOD1-named mesh, with `lod_index=1`, under the existing
`AssetRoot`. Its exported `shared_lod_levels` declaration must be exactly `[1,2]`.
Remove the proven duplicate generated mesh. Preserve the original LOD0 source,
required semantic LOD nodes and every other assembly. Dynamic assemblies,
glass, lamps, mirrors and protected current-front components are outside this
bounded extension.

The project-owned import adapter validates the complete raw GLB declaration and
imported member domain before normalizing a reserved direct metadata value to
`PackedInt32Array([1,2])`. The wrapper runtime registers these static meshes
separately and assigns visibility once, for level1 or2. Level0, including forced
inspection, cockpit and open-panel views, hides them. Missing declarations
preserve existing behavior. Malformed declarations fail explicitly.

Count actual stored instances once and report complete logical drawn membership
for each level separately. Do not subtract equal hashes from a scene retaining
two nodes. The existing150000 active-LOD,200000 total and32-material ceilings
remain unchanged. Runtime resource counters continue measuring real instances
and native resources. This decision neither approves the vehicle nor changes
Q-044, the human gates, physics or distance-selection policy.

## Verification and consequences

Require fresh exact equality; complete source-member multiplicities; one actual
source, exported and imported instance; source-bound metadata; unchanged fields
and logical draw counts across repeated0-1-2-1-0 transitions; independent
instances and recreation; and rejected malformed metadata/altered geometry.
Re-run absent-declaration, Hero GT and graybox regressions. Compare fixed-camera
renders with the duplicated baseline and exercise actual distance transitions.
The final combined asset must pass deterministic double export, clean import,
literal budgets, platform checks and existing delivery gates.

This introduces a small explicit static visibility role rather than changing
mesh approximation or weakening a budget. The constructor, source validator,
exporter, adapter and runtime must agree; exact legacy fixtures alone cannot
establish savings or acceptance for a changed current source.
