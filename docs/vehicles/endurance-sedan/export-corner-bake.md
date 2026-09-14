# Source-bound ordered-corner encoding

P1-018, 2026-09-11. The exact source34 Linux and Windows raw exports differed
in vertex deduplication and small evaluated floating-point values. Their scene,
material and six embedded image payloads matched. Indexed triangle-corner
comparison measured maximum position distance0.00000011920928955078125m,
normal angle0.020593529degrees and UV component difference0.000000953674317.
The retained comparison is `reports/p1-018/linux-glb34-diagnostic02/evidence.json`.

`endurance_sedan/corner_bake.py` validates the raw GLB before restoring the
explicitly reviewed canonical encoding. It requires the exact source hash,
ordered triangle correspondence, supported accessor layout, finite attributes,
positive triangle area above1e-12m² on both inputs, and matching winding.
Position distance is limited to0.0000002m, normal angle to0.025degrees,
normal length error to0.000001 and each UV component to0.00001. These bounds
cover measured exporter variation; they are separate from modeling tolerances
and reference uncertainty. Geometry is not quantized.

Scene and node semantics, material settings, extension declarations and embedded
image bytes must match exactly. Unsupported, external, overlapping or unused
payloads, stale sources and corrupted lock data fail before output replacement.
Both raw and final GLBs undergo the ordinary mesh validation. The manifest binds
the validator, profile, lock and observed comparison metrics. Thirty-one native
positive/rejection controls exercise the bounded encoding operation.

After an intentional source edit, pass fresh report paths to
`validate_and_export_endurance_sedan.py` with both
`--prepare-corner-bake reports/p1-018/new-corner-bake.json` and
`--prepare-uv-bake reports/p1-018/new-uv-bake.json`. Inspect the actual new source,
raw/final GLBs, correspondence, dimensions and runtime import before promoting
those explicit locks to `data/assets/vehicles/`. Existing locks are never
overwritten by these options. Normal verification rejects a changed source.

This encoding step does not approve visual quality, asset rights or gameplay.
Every shipping byte must still match across two exports and clean imports from
the final locked inputs, with the task's required platform evidence.
