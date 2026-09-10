# Unsigned fixture exports

This pipeline makes reproducible, unsigned Linux and Windows x86_64 packages
with Godot 4.7.1 Mono. These packages intentionally contain only the short
`official-corridor` fixture and remain internal verification artifacts, not a
representative route or a public release. P0-006 validates the distance-complete
500-mile runtime separately; it does not turn this fixture package into a
release candidate.

Run the same build twice and compare every packaged byte:

```bash
GODOT_BIN=/absolute/path/to/Godot ./scripts/release/install-templates.sh
GODOT_BIN=/absolute/path/to/Godot ./scripts/check.sh
PYTHON_BIN="$(uv python find 3.13.11)" \
  GODOT_BIN=/absolute/path/to/Godot ./scripts/release/build-unsigned.sh
```

Each content-addressed ZIP includes the loose route bundle, checksums, a
CycloneDX SBOM, build provenance, a file inventory, and the verifier used by CI.
The clean-machine jobs download only this ZIP and checksum sidecar, verify the
payload, then launch it with a hostile `--playgodot` argument to prove release
automation is absent.

Each native CI job requires ten consecutive smoke passes with fresh runtime
homes and stops on the first failure. Runtime and verifier transcripts plus a
completed-count summary are uploaded even after failure. For a local retained
transcript, set `CANNONBALL_RELEASE_SMOKE_LOG_FILE` to a path outside the package
when invoking `verify-package.sh ... --smoke`; package-contained paths are rejected.
Functional success markers must be followed by clean process termination and no
fatal/error output. Windows console-wrapper status alone does not prove that.

## Immutable promotion and rollback

Artifacts are named with the SHA-256 of their bytes and uploads use
`overwrite: false`. Promotion means recording or copying an already verified
content-addressed artifact; it never means rebuilding or replacing that name.
Rollback selects the previously recorded SHA-256 and retrieves that exact
artifact. If its sidecar or internal checksums fail, stop: do not repair an
artifact in place.
