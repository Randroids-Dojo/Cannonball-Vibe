# V25 construction checkpoint - 2026-09-12

The editable full10 source passes all 20 selected native source checks and the
Windows `scripts/check.sh` front door passes all 13 steps. This is a construction
checkpoint for P1-018. Internal assembly repairs are still being developed;
the installed production34 Blender source and Godot GLB are unchanged.

The [retained archive](../../../data/assets/vehicles/endurance-sedan-review/production35-checkpoint-v25/source-checkpoint-v25.zip)
contains the source, exact construction inputs, measured density trials, actual
comparison renders, independent reviews, failed attempts and completed checks.
The adjacent `manifest.json` and `index.json` bind every file by SHA-256 and
record two independently written, byte-identical archives. Archive equivalence
does not establish final shipping export equivalence.

Extract the ZIP into a new, empty review directory. Open
`reports/p1-018/source35-full10/source.blend` using Blender 5.1.2. Its SHA-256 is
`26b7fc239a3d88854f00ddfc71dde9bfe25e80e1432255e8ea0236e4348de53e`.
Select the `Asset` collection and use `RigControls` as described in
[README.md](README.md). The source QA evidence is in the neighboring
`qa20/evidence.json`; the Windows results are in
`reports/p1-018/source35-v25-frontdoor01/m0/summary.json`.

The full10 cost is 142,828 / 30,272 / 17,576 LOD triangles plus 24 collision
triangles, totaling 190,700 with 24 materials. Native extraction checks 1,303
meshes and 495,582 normal corners. The largest raw normal length error is
0.000000201735, below the existing 0.000001 guard. These are measurements
against provisional Q044 content ceilings, not budget ratification.

Revisions 22-25 preserve the wheel dimensions and hardpoints while reducing
unnecessary tessellation, omitting 22 explicitly named small details only at
distance, and correcting distant brake-hat simplification. The original turbo
housings remain after their simplified version visibly lost quality. Full09's
four failing distant brake shells and their corrected pilot are retained;
full10 passes every selected stage on one unchanged source hash.

The newer floor, seats, wheelhouses, cabin supports, roof ends, paint and cooling
core are outside this checkpoint. Full assembly fit, final source/export
correspondence, new Godot imports, runtime footage, measured performance,
declared platform checks and human visual/rights/handling/usability reviews
remain required. P1-018 stays `in_progress`.
