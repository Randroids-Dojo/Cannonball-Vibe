# ADR-0012: Agentic visual asset pipeline and replaceable graybox contracts

- Status: Accepted
- Date: 2026-07-17

## Context

Cannonball-Vibe currently proves driving and streaming with a code-generated
graybox vehicle, road ribbon, shoulders, terrain, and scenery placeholders. The
M5 representative vertical slice requires a production-quality hero vehicle,
modular highway surfaces and furniture, and a regional terrain and background
environment. Those assets must improve presentation without making route
topology, collision, vehicle physics, or automated delivery depend on manual
Godot or Blender editor sessions.

Road geometry is still evolving to support variable lane counts, exits,
highway transfers, gore areas, signs, and mile markers. A hand-authored road
mesh or monolithic environment scene created against the current fixed-width
ribbon would be expensive to discard. The visual pipeline therefore needs
stable semantic boundaries, deterministic command-line gates, replaceable
graybox fallbacks, and explicit human approval for subjective art direction and
asset rights.

## Decision

### Source and import contract

- Use Blender source files for original 3D art and glTF 2.0 binary (`.glb`) as
  the Godot interchange format. Pin the validated Blender build, exporter
  scripts, and Godot 4.7.1 import profiles in repository tooling.
- Store binary source art and models with Git LFS. Every source and derived
  asset must have a content hash, creator or publisher, license, acquisition or
  creation date, transformation ancestry, export profile, and redistributable
  status in a machine-readable manifest.
- Treat imported scenes as generated inputs. Put gameplay scripts, collision
  policy, materials overrides, cameras, and automation IDs in project-owned
  wrapper scenes so a re-export cannot silently erase runtime behavior.
- Keep lightweight graybox assets that satisfy the same semantic contracts.
  Core development, headless scenarios, and source builds must remain possible
  when production art is unavailable.

### Hero vehicle contract

- Keep the custom four-raycast `RigidBody3D` simulation authoritative. The
  visual rig follows measured chassis pose, steering, wheel rotation, and
  suspension travel; it does not replace physics with imported animation or an
  engine vehicle abstraction.
- Require stable semantic nodes or bones for the chassis, four wheels,
  suspension and contact anchors, collision proxy, camera targets, lights,
  exhaust, driver reference, material groups, damage zones, and declared LODs.
- Validate scale, forward and up axes, ground contact, wheelbase, track width,
  pivot placement, transforms, material counts, triangle counts, texture
  budgets, collision complexity, and LOD transitions before import promotion.
- Begin with one original fictional grand tourer. Additional vehicles must use
  the same rig adapter and budget contract rather than fork the simulation.

### Road and environment contract

- Keep route semantics and procedural generation authoritative for road width,
  lane centers, markings, shoulders, barriers, gore areas, ramps, junctions,
  signs, collision, and stream boundaries. Production road assets provide
  tiling materials, profiles, meshes, decals, furniture, and placement rules;
  they do not encode navigation topology in opaque authored scenes.
- Build a modular highway kit for pavement states, shoulders, medians,
  barriers, guardrails, bridge and overpass pieces, gore treatments, lane
  markings, reflectors, signs, posts, and roadside props. Modules must tolerate
  variable lane sections, curvature, grade, branches, and local-origin rebases.
- Build environments in three tiers: deterministic near-road terrain and
  objects, streamed regional midground, and low-cost distant terrain or skyline.
  Route packages select region and seed; art assets never become authoritative
  route or save state.
- Prefer instancing, trim sheets, atlases, and shared materials. Near collision,
  visual lookahead, background retention, and degradation order remain
  independently measurable.

### Agentic gates

- Run source lint and export through pinned Blender command-line scripts. The
  pipeline must fail on missing manifests, unexpected node names, unapplied or
  invalid transforms, broken references, nonportable paths, or budget drift.
- Run Godot import and scene validation with the official 4.7.1 command line.
  A validator must instantiate each asset wrapper, resolve every required
  semantic node, and emit machine-readable inventory, hash, import, and budget
  evidence.
- Produce deterministic renderer-backed contact sheets and representative
  driving captures from fixed seeds, cameras, lighting states, and LOD
  distances. Pixel comparisons are diagnostic; semantic and quantitative gates
  remain authoritative when renderer output varies within an approved bound.
- Use Computer Use only as a supplementary black-box check of the real editor
  or packaged build. Modern PlayGodot remains reserved for rendered interactive
  UI where its stable scene-node API has measured value; neither is required to
  export or validate 3D assets.
- Keep art-direction approval, representative visual quality, and final asset
  rights as human gates. Automated checks may prepare comparison artifacts but
  cannot approve taste or legal rights.

## Delivery order

1. Complete the deterministic asset and provenance pipeline in P1-002.
2. Integrate one production-ready hero vehicle through the graybox-compatible
   visual rig adapter in P1-008.
3. Complete variable-lane and route-context semantics before promoting the
   modular highway kit in P1-009.
4. Build the representative regional environment and background system in
   P1-010 after visual and collision streaming have separate budgets.
5. Combine the three slices in the M5 representative-region quality and human
   review gate.

Vehicle art may begin before route semantics finish because its contract is
independent. Road modules may be prototyped against fixtures, but their task
cannot complete until variable lanes, interchanges, signs, and markers exercise
the final generator contract.

## Consequences

- Artists and agents can replace visual assets without changing authoritative
  physics, navigation, saves, or streaming state.
- The repository gains Blender as a pinned build-time dependency for visual
  production, but normal code and headless graybox verification retain a
  lightweight path.
- Production art cannot bypass budget, provenance, import, semantic-node,
  renderer-capture, or rights gates.
- The M5 visual work is split into independently testable vehicle, road, and
  regional environment outcomes instead of remaining one broad asset task.
- Exact visual budgets and final art direction remain open until representative
  assets and target hardware produce evidence.

## Rejected alternatives

- **Hand-build production assets directly in Godot scenes:** weakens source
  portability and makes repeatable lint, export, and reimport harder.
- **Let a monolithic road mesh define topology:** couples visuals to navigation,
  prevents robust variable-lane generation, and undermines chunk streaming.
- **Replace the raycast simulation with a model's animation rig:** makes visual
  authoring authoritative over handling and deterministic runtime state.
- **Require editor clicking for asset promotion:** cannot be reproduced in CI
  or audited as a complete agentic delivery gate.
- **Use Computer Use or PlayGodot as the primary asset pipeline:** both are
  valuable at different presentation layers, but neither replaces deterministic
  Blender export, Godot import, semantic validation, and structured evidence.
