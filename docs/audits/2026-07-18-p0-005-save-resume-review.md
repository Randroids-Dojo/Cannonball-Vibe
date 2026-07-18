# P0-005 exact save and resume adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `9574315e4eb004bbaf66944b5db8469636667354`
- Result: no unresolved actionable finding; local acceptance passed

## Scope

The review traced a suspended run from runtime capture through schema migration,
package-identity validation, atomic persistence, primary/backup recovery, and
runtime reconstruction. It compared authoritative route, navigation, local
origin, stream residency, vehicle transform and motion, elapsed time, assist,
condition, cash, seed, and enforcement state before the resumed scene advanced.

## Findings resolved during review

1. The previous checksum covered only a content-version string. Schema 3 now
   derives an identity from the exact root bytes, source and elevation artifact
   hashes, acquisition lock, and every manifest chunk's stable metadata and
   SHA-256.
2. Loading a save previously returned data without reconstructing the running
   Godot world. Resume now selects the saved route plan, restores the exact
   streamed visual and collision chunk sets, positions the local origin, and
   restores the vehicle and gameplay systems before physics advances.
3. Save state previously omitted local-origin rebase state, resident chunks,
   collision residency, and vehicle orientation. Schema 3 records all of these,
   while schema-1 and schema-2 migrations supply explicit compatible defaults.
4. Synchronously awaiting repository I/O on Godot's synchronization context can
   deadlock. Initial resume loading is dispatched off that context before scene
   construction.
5. Schema-2 migration could otherwise bless data from the wrong package. It
   first validates the legacy content-version checksum and only then upgrades
   to the exact identity of the already-loaded package.
6. Interrupted writes could expose a partial save. Writes now use a flushed
   temporary file, validate it, advance a verified primary to `.bak`, and
   atomically replace the primary.
7. A corrupt primary could overwrite the last known-good backup during the next
   save. Backup rotation now validates the current primary first and preserves
   an existing good backup when primary validation fails.
8. Failure messages previously lost the distinction between primary and backup
   corruption. Recovery reports whether the backup was used and combines both
   actionable validation errors when neither copy is usable.
9. Small hand-picked round trips would not cover enough state combinations.
   The seeded exact-comparison fuzz test exercises 10,000 authoritative save
   points and is reproducible with seed `20260718`.

## Residual boundaries

- A restored rigid body resumes from the same authoritative transform and local
  linear/angular velocity. Floating-point integration after resume is not
  claimed to be bit-identical across CPU architectures.
- Cloud synchronization, account identity, and cross-device conflict handling
  are outside this local suspend/recovery slice.
- Schema migration is intentionally forward-rejecting: a save newer than the
  running build fails with an actionable unsupported-schema error.

## Verification reviewed

- `./scripts/run-resume-fuzz.sh --cases 10000`: 10,000 exact repository
  comparisons passed with seed `20260718`.
- `./scripts/run-scenario.sh --fixture official-corridor --resume-verify`:
  authoritative runtime equivalence passed at 46.067 route meters with four
  visual chunks, four collision chunks, and zero rebases.
- Representative streaming stress resume: equivalence passed after one local
  origin rebase with 18 visual chunks and eight collision chunks resident.
- Representative route-choice resume: equivalence passed on the receiving
  highway after the selected transfer, with its route plan and active connector
  preserved.
- `./scripts/check.sh`: passed; 54 C# tests, 66 map-pipeline tests, 12 PlayGodot
  unit tests, Ruff, doctor, build, and official Godot 4.7.1 smoke.
- `git diff --check`: passed.
- Protected PR gates passed on Linux, Windows, and macOS, including M0,
  PlayGodot, reproducible exports, and both clean-machine smoke jobs. CodeRabbit
  reached its fair-usage review limit without findings; this adversarial review
  supplied the documented fallback, and PR #23 merged at
  `11b30d69409566943695883196a428b17d3d907e`.
