# Unsigned fixture exports

This pipeline makes reproducible, unsigned Linux and Windows x86_64 packages
with Godot 4.7.1 Mono. Until P0-006 is complete, these packages contain only the
short `official-corridor` fixture and are internal verification artifacts, not a
representative route or a public release.

Run the same build twice and compare every packaged byte:

```bash
GODOT_BIN=/absolute/path/to/Godot ./scripts/release/install-templates.sh
GODOT_BIN=/absolute/path/to/Godot ./scripts/release/build-unsigned.sh
```

Each content-addressed ZIP includes the loose route bundle, checksums, a
CycloneDX SBOM, build provenance, a file inventory, and the verifier used by CI.
The clean-machine jobs download only this ZIP and checksum sidecar, verify the
payload, then launch it with a hostile `--playgodot` argument to prove release
automation is absent.

## Immutable promotion and rollback

Artifacts are named with the SHA-256 of their bytes and uploads use
`overwrite: false`. Promotion means recording or copying an already verified
content-addressed artifact; it never means rebuilding or replacing that name.
Rollback selects the previously recorded SHA-256 and retrieves that exact
artifact. If its sidecar or internal checksums fail, stop: do not repair an
artifact in place.
