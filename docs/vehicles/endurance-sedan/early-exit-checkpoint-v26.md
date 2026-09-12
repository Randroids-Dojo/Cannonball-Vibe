# P1-018 early-exit verification checkpoint

The PlayGodot launcher now uses the remaining portion of its existing absolute
eight-second cleanup deadline after Godot exits. This corrects the Windows
case where a clean native exit was followed by filesystem bookkeeping that
took slightly longer than its separate one-second allowance. Authorization,
fallback rejection, original test exceptions, cancellation and late-worker
failure rules are unchanged. The protocol documentation matches this behavior.

Current Windows checks pass 98 focused host controls, four actual rendered
official-engine cases and Ruff. The full `scripts/check.sh` front door passes
all 13 steps, including 157 C# tests, 345 map-pipeline tests with one declared
skip, and 153 PlayGodot unit tests. The front door ran revision568252c plus the
exact recorded working runtime, source-QA and governance files; all bound inputs
were unchanged at completion. It is not a clean-commit or remote-platform pass.

The [retained handoff](../../../data/assets/vehicles/endurance-sedan-review/early-exit-checkpoint-v26/HANDOFF12.md)
distinguishes the old Windows175-pass/1-fail result from the Linux/Mac176-pass
results. Those counts include host tests. It also retains the original API
archives, actual rendered observations, the bounded schedule reproduction,
negative controls, retries and later changes to rebuilt local Debug DLLs.

The [retention index](../../../data/assets/vehicles/endurance-sedan-review/early-exit-checkpoint-v26/index.json)
binds846 files. Both44,963,804-byte ZIP builds have SHA-256
`3a027dca13ddc634c12437b6cabd264a2a7437fdede68baff74229bea2d3281d`.
Lead compared every byte and reread all member hashes and CRCs in both archives.
Sixteen generated shader-cache files are explicitly omitted with their hashes;
the original native observations and all required failure evidence are retained.

New-commit standard platform evidence remains required. Installed production34
is unchanged. Current Blender construction, final source QA, LOD/export,
runtime media, performance, packages and human gates remain open; this does
not complete P1-018.
