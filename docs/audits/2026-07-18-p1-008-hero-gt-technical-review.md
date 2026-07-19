# P1-008 Hero GT technical review

- Date: 2026-07-18
- Task: P1-008
- Status: Technical baseline complete; human art-direction and exact rights gate open
- Working choice: Q-020 option A in
  [QUESTIONS_FOR_RANDROID_2026-07-18_AUTONOMOUS.md](../QUESTIONS_FOR_RANDROID_2026-07-18_AUTONOMOUS.md)

## Delivered baseline

The project-original procedural Hero GT replaces the runtime box visual without
changing the authoritative `RigidBody3D`, four-raycast suspension, save state,
or route state. Blender 5.1.2 generates the checksum-locked source; the pinned
exporter produces a glTF 2.0 binary and renderer contact sheet; official Godot
4.7.1 imports the model and a project tool normalizes only the importer's
non-semantic per-node unique IDs into a checked generated scene. The
project-owned wrapper references that normalized scene, while the checksum-
locked GLB remains an excluded build artifact.

The semantic contract resolves 37 required nodes covering the chassis, three
LODs, collision proxy, four wheel pivots, four suspension and contact anchors,
chase and cockpit camera anchors, head and tail lights, exhausts, driver
reference, five material groups, and five damage zones. The C# adapter follows
authoritative steering, wheel rotation, and per-wheel suspension compression.
`--graybox-vehicle` and the automated equivalence stage retain the old box
visual over the same collision and physics body.

## Quantitative result

| Contract | Result | Provisional gate |
| --- | ---: | ---: |
| LOD0 triangles | 7,232 | 24,000 maximum |
| Total source triangles | 7,664 | 30,000 maximum |
| Collision-proxy triangles | 108 | 128 maximum |
| Materials | 9 | 10 maximum |
| External textures | 0 | 0 maximum |
| Wheelbase | 2.84 m | exact contract |
| Track width | 1.64 m | exact contract |
| Wheel radius | 0.34 m | exact contract |
| Suspension travel | 0.62 m | exact contract |

The asset gate rebuilds the GLB and contact sheet twice and compares their
bytes, rejects unapplied-scale, missing-semantic-node, and external-texture
mutations, validates a clean staged import, checks the recursive manifest, and
audits a Linux PCK. The GLB and renderer contact sheet are rebuilt twice and
must be byte-identical; the repository's two-fresh-stage unsigned release gate
remains authoritative for full-package reproducibility. The PCK audit verifies
that the Hero GT wrapper and imported scene ship while Blender source and
validation tooling do not.

## Renderer review

The tracked Blender contact sheet is
`data/assets/vehicles/hero-gt-contact-sheet.png`. The eight-state in-game review
sheet is [p1-008-hero-vehicle-review.png](../images/p1-008-hero-vehicle-review.png)
with SHA-256
`d14204c103999613a2951c2656470a53119132ea197a6a46f2caff2c31f892ea`.
The local 480-frame 60 FPS review movie is
`/tmp/p1-008-hero-vehicle.avi` with SHA-256
`ea60fdb9cac898eb086c007abba99306b32b922061ae1f9c84ed7dcb2c18b463`.

The scenario covers daylight chase framing, night cockpit framing, braking
pitch, steering lock, full suspension travel, all three LODs, damage-zone
highlighting, and graybox equivalence. The automated checks prove semantic and
geometric behavior; they do not approve final silhouette, material richness,
cockpit composition, or driving aesthetics.

## Gate hardening found during review

The first clean pass exposed two false-positive risks and the final gate now
rejects both:

- wrapper validation separately proves the imported GLB semantic hierarchy,
  project-owned C# adapter reference, clean C# build, and runtime adapter
  behavior instead of assuming a GDScript validator can initialize the project
  assembly;
- the release auditor recognizes Godot's exported `.tscn.remap` wrapper while
  still requiring the generated visual scene and excluding build inputs.

The first two-fresh-stage unsigned release build then found that Godot assigns
different `unique_id` values to otherwise identical imported nodes. A complete
text-scene comparison proved that every mesh, material, transform, property,
and hierarchy entry matched and only those non-semantic IDs varied. The
promotion gate now removes only `unique_id` attributes, compares the normalized
scene from independent import caches, and ships that deterministic generated
scene instead of the cache-specific binary import.

The same engine-local IDs were reintroduced when the exporter converted the
tracked text scenes back to binary scenes. The project now disables that
optional conversion so release PCKs carry the reviewed, deterministic text
resources directly. Godot still loads those native text resources at runtime;
the tradeoff is a small increase in PCK size in exchange for reproducible and
auditable scene bytes.

That successful Linux-only gate also exposed a shell-status defect: the build
completed reproducibly, then returned the false Windows-target predicate as its
process status. The platform dispatch now uses explicit conditionals so a
successful single-platform build exits successfully.

The asset-specific PCK audit accepts the deterministic generated `.tscn`
directly as well as the engine's binary/remap forms. It continues to require
both the project-owned wrapper and generated visual while rejecting Blender,
data-manifest, and tooling inputs.

An adversarial runtime pass also found that the first night-cockpit stage moved
the chase camera into the cabin instead of exercising the declared semantic
anchor. The final stage switches to the anchor-owned cockpit camera and asserts
that it, rather than the chase camera, is current. The complete findings and
resolutions are recorded in
[the P1-008 adversarial review](2026-07-18-p1-008-adversarial-review.md).

## Remaining human boundary

P1-008 remains `in_progress`. Q-020 still requires the project owner to select
or approve the production art path and review the exact Hero GT rights record.
The current model is a coherent, fully agentic technical baseline, not a claim
that the low-poly procedural silhouette is the final production vehicle.
