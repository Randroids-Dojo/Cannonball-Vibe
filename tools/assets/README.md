# Deterministic asset pipeline

P1-002 implements the command-line asset contract accepted in ADR-0012. Normal
gameplay and graybox development do not require Blender. Asset creation,
re-export, or promotion requires the exact Blender and Godot builds pinned in
`toolchain.json`.

## Verification front door

```bash
./scripts/validate-assets.sh
```

The gate performs two independent Blender 5.1.2 exports, compares the GLB and
renderer-backed contact-sheet bytes within the current platform, verifies the
checked-in GLB, rejects three intentionally invalid source mutations, imports
the wrapper with official Godot 4.7.1, resolves stable semantic nodes, checks
budgets and recursive provenance, then exports and audits a release PCK. The
Godot stages run in an isolated project copy so verification does not rewrite
source lockfiles or create editor UID sidecars in the worktree.

The tracked contact sheet is a fixed review artifact. Renderer bytes may vary
between approved operating systems or GPU backends, so cross-platform pixel
hashes are diagnostic. Semantic nodes, budgets, manifests, GLB bytes, and
release dependencies are authoritative.

## Fixture regeneration

The project-original road-module fixture can be recreated for inspection:

```bash
blender --background --factory-startup \
  --python tools/assets/create_fixture.py -- \
  --output /tmp/graybox-road-module.blend
```

The checked-in `.blend` remains the checksum-locked source of record. Blender
source files contain application metadata and are not assumed to be
byte-identical when newly saved; deterministic promotion begins from the locked
source and requires identical derived GLB bytes.

## Adding an asset

1. Put checksum-locked source art under a `.gdignore` build-input directory and
   track binary source and derived models with Git LFS.
2. Add a schema-1 manifest with authorship, rights, recursive transformations,
   exact hashes, semantic nodes, and measurable budgets.
3. Export through a versioned profile. Do not hand-edit the derived GLB.
4. Put runtime behavior and automation IDs in a project-owned wrapper scene.
5. Pin the Godot `.import` settings, validate the imported semantic inventory,
   and prove the release PCK contains no Blender source or asset-test tooling.
6. Produce a deterministic contact sheet and leave subjective quality and
   final rights approval to the declared human gate.

Computer Use can supplement the result with a real-editor or packaged-build
inspection. PlayGodot is intentionally not part of 3D asset export or
promotion; it remains reserved for rendered UI automation where stable scene
nodes provide measured value.
