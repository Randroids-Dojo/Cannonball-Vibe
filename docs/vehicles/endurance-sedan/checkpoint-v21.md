# V21 construction checkpoint ? 2026-09-12

This is a retained production checkpoint for P1-018. It contains the editable
full07 Blender source and its completed local surface/LOD checks. The installed
`data/assets/vehicles/sources/endurance-sedan.blend` and runtime GLB remain the
previous production34 candidate; this archive is not a final replacement asset.

The [archive](../../../data/assets/vehicles/endurance-sedan-review/production35-checkpoint/source-checkpoint-v21.zip)
contains 698 explicitly hashed files. Its two independently written ZIP files
are byte-identical: SHA-256
`7a8594eaa6ce73142bef7ed91c518607beb2ec07eb09b99c33822d85e072f426`,
131,375,014 bytes. The adjacent `manifest.json`, `index.json` and retained command
record identify exact inputs, outputs, tool versions and verification status.
Archive equivalence is evidence retention, not final shipping export equivalence.

Extract the ZIP into a **new, empty review directory**. Open the contained
`reports/p1-018/source35-full07/source.blend` with Blender 5.1.2. Its SHA-256 is
`ea701f2a44b5baaaa0c746c2311c61a348cd58b0bf2f1f18c0d2a8edadcf79bb`.
Use the `Asset` collection and `RigControls` as described in [README.md](README.md).
The original images are under the neighboring `neutral01` directory. The
independent native report is `reports/p1-018/runtime/full07-validation01/HANDOFF.md`.

Completed checkpoint checks:

- Official Blender 5.1.2 construction and native reopening/extraction.
- Zero strict self-crossings in all 1,002 shipping LOD0 meshes and all 848
  connected lower-LOD shells; raw normal and basic topology checks passed.
- Front bumper and both front fenders exactly reproduce the reviewed trial's
  raw/evaluated geometry, UVs and normals. Remaining whole-source differences
  are explicitly bounded in the correspondence report.
- Fixed-camera Cycles paint, front-lamp and front three-quarter renders were
  inspected by the lead and an independent agent.
- Windows `scripts/check.sh` passed on the v21 working construction inputs.
- The earlier full06 source's 20 selected source stages also passed; its exact
  source and reports are retained separately inside the archive.

The full07 cost is 149,180 / 32,264 / 18,474 LOD triangles plus 24 collision
triangles, totaling 199,942 with 24 materials. Newly found internal floor,
driveline, seat and rear wheelhouse fit defects remain unresolved in this
checkpoint. Lower-LOD interassembly acceptance, final optimized exports,
clean Godot import, final runtime/platform/performance evidence and human
art/rights/handling/usability reviews are still required. Task status stays
`in_progress`; no human approval is recorded by this checkpoint.
